"""Experiment specification and sweep expansion (T1.16, D-013, D-017).

An `ExperimentSpec` defines a multi-arm, multi-demand, multi-seed experiment:
`controllers x demand_levels x n_seeds` independent runs.

Per D-017 (common random numbers):
- Route files depend on (demand_level, seed) and NEVER on the controller arm.
- For each (demand_level, seed) cell, one route file is built and shared across
  all controller arms.
- Two controllers running with the same seed receive identical vehicle arrivals.

Per T1.10 A4:
- The `sumo_actuated` arm runs natively in SUMO on the net built with `program="actuated"`,
  with no constraint layer and no `apply()`.
"""

from __future__ import annotations

import enum
import functools
import importlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from traffic_lab.backend import TransportName
from traffic_lab.control.actuated import ActuatedController
from traffic_lab.control.controller import Controller
from traffic_lab.control.max_pressure import MaxPressureController
from traffic_lab.control.webster import WebsterController
from traffic_lab.domain.network import Network, TurnDirection, VehicleType
from traffic_lab.experiments.config import RunConfig
from traffic_lab.experiments.runner import RunSpec, run_many
from traffic_lab.experiments.seeds import derive_run_seeds
from traffic_lab.scenarios.demand import build_routes, uniform_demand_spec
from traffic_lab.scenarios.generator import IDS_SUFFIX, NET_STEM, build
from traffic_lab.scenarios.parse import SumoIds
from traffic_lab.scenarios.saturation import per_lane_saturation_flow_vph
from traffic_lab.scenarios.spec import IntersectionSpec


class WarmupDesign(enum.StrEnum):
    """Warm-up design (D-032)."""

    SELF = "self"
    NEUTRAL_SNAPSHOT = "neutral_snapshot"


class ControllerSpec(BaseModel):
    """Specification of a controller arm in an experiment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = ""
    type: Literal["webster", "actuated", "max_pressure", "sumo_actuated", "custom"]
    decision_interval_s: float | None = None
    factory: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if not self.name:
            object.__setattr__(self, "name", self.type)


def car_saturation_lookup(speed_limit_mps: float, turn: TurnDirection) -> float:
    """Look up calibrated saturation flow for passenger cars (D-037)."""
    return per_lane_saturation_flow_vph(VehicleType.CAR, speed_limit_mps, turn)


def make_webster_controller(
    network: Network,
    *,
    demand_level: float,
    decision_interval_s: float = 1.0,
) -> WebsterController:
    """Top-level factory for WebsterController at a specific demand level."""
    demand = uniform_demand_spec(network, demand_level)
    return WebsterController(
        network,
        demand,
        car_saturation_lookup,
        decision_interval_s=decision_interval_s,
    )


def make_actuated_controller(
    network: Network,
    *,
    decision_interval_s: float = 1.0,
    gap_s: float = 2.0,
) -> ActuatedController:
    """Top-level factory for ActuatedController."""
    return ActuatedController(network, decision_interval_s=decision_interval_s, gap_s=gap_s)


def make_max_pressure_controller(
    network: Network,
    *,
    decision_interval_s: float = 5.0,
) -> MaxPressureController:
    """Top-level factory for MaxPressureController."""
    return MaxPressureController(network, decision_interval_s=decision_interval_s)


def _resolve_custom_factory(path: str) -> Callable[[Network], Controller]:
    """Import and return a custom controller factory by qualname."""
    module_name, func_name = path.rsplit(".", 1)
    mod = importlib.import_module(module_name)
    factory = getattr(mod, func_name)
    if not callable(factory):
        raise TypeError(f"custom factory {path!r} is not callable")
    return factory  # type: ignore[no-any-return]


def _load_ids(path: Path) -> SumoIds:
    """Load SumoIds from json."""
    raw = json.loads(path.read_text())
    return SumoIds(
        lanes=tuple(raw["lanes"]),
        edges=tuple(raw["edges"]),
        junctions=tuple(raw["junctions"]),
        intersections=tuple(raw["intersections"]),
        connections=tuple((a, b) for a, b in raw["connections"]),
    )


class ExperimentSpec(BaseModel):
    """Specification of an experiment sweep."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    scenario: IntersectionSpec
    demand_levels: list[float]
    controllers: list[ControllerSpec]
    n_seeds: int
    master_seed: int
    warmup_design: Literal["self", "neutral_snapshot"] | WarmupDesign = "self"
    jobs: int = 0

    # Timing parameters per run
    warmup_s: float = Field(default=60.0, ge=0.0)
    measurement_s: float = Field(default=300.0, gt=0.0)
    cooldown_s: float = Field(default=60.0, ge=0.0)
    step_length_s: float = Field(default=1.0, gt=0.0)
    transport: TransportName = "libsumo"
    name: str = "experiment"

    @field_validator("controllers", mode="before")
    @classmethod
    def _normalize_controllers(cls, v: Any) -> Any:
        if isinstance(v, list):
            out = []
            for item in v:
                if isinstance(item, str):
                    out.append(ControllerSpec(type=item))  # type: ignore[arg-type]
                else:
                    out.append(item)
            return out
        return v

    def model_post_init(self, __context: Any) -> None:
        if not self.demand_levels:
            raise ValueError("demand_levels must be non-empty")
        for d in self.demand_levels:
            if d <= 0.0:
                raise ValueError(f"demand_level must be positive, got {d}")
        if not self.controllers:
            raise ValueError("controllers must be non-empty")
        names = [c.name for c in self.controllers]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate controller names in {names}")
        if self.n_seeds < 1:
            raise ValueError(f"n_seeds must be at least 1, got {self.n_seeds}")
        if self.master_seed < 0:
            raise ValueError(f"master_seed must be non-negative, got {self.master_seed}")
        warmup_str = (
            self.warmup_design.value
            if isinstance(self.warmup_design, WarmupDesign)
            else self.warmup_design
        )
        if warmup_str != "self":
            raise ValueError(
                f"warmup_design={self.warmup_design!r} is not supported until T1.6; "
                f"only 'self' warm-up can be run"
            )
        if self.jobs < 0:
            raise ValueError(f"jobs must be non-negative, got {self.jobs}")


def expand_experiment(spec: ExperimentSpec, out: Path) -> list[RunSpec]:
    """Expand an ExperimentSpec into RunSpecs: controller x demand_level x seed."""
    out.mkdir(parents=True, exist_ok=True)
    networks_dir = out / "networks"
    routes_dir = out / "routes"
    runs_dir = out / "runs"

    needs_static = any(c.type != "sumo_actuated" for c in spec.controllers)
    needs_actuated = any(c.type == "sumo_actuated" for c in spec.controllers)

    net_static_path: Path | None = None
    net_static_obj: Network | None = None
    ids_static: SumoIds | None = None
    if needs_static:
        static_dir = networks_dir / "static"
        static_dir.mkdir(parents=True, exist_ok=True)
        net_static_path, net_static_obj = build(spec.scenario, static_dir, program="static")
        ids_static = _load_ids(static_dir / f"{NET_STEM}{IDS_SUFFIX}")

    net_actuated_path: Path | None = None
    net_actuated_obj: Network | None = None
    ids_actuated: SumoIds | None = None
    if needs_actuated:
        actuated_dir = networks_dir / "actuated"
        actuated_dir.mkdir(parents=True, exist_ok=True)
        net_actuated_path, net_actuated_obj = build(spec.scenario, actuated_dir, program="actuated")
        ids_actuated = _load_ids(actuated_dir / f"{NET_STEM}{IDS_SUFFIX}")

    # Build reference network for route generation
    reference_net = net_static_path if net_static_path is not None else net_actuated_path
    reference_obj = net_static_obj if net_static_obj is not None else net_actuated_obj
    reference_ids = ids_static if ids_static is not None else ids_actuated
    assert reference_net is not None and reference_obj is not None and reference_ids is not None

    end_s = spec.warmup_s + spec.measurement_s + spec.cooldown_s

    # Generate routes once per (demand_level, seed_index)
    route_files: dict[tuple[float, int], Path] = {}
    for d in spec.demand_levels:
        demand_spec = uniform_demand_spec(reference_obj, d)
        for s in range(spec.n_seeds):
            seeds = derive_run_seeds(spec.master_seed, s)
            demand_seed = seeds["demand"]
            route_out = routes_dir / f"d_{d}" / f"seed_{s}"
            route_file = build_routes(
                reference_net,
                reference_obj,
                reference_ids,
                demand_spec,
                demand_seed,
                route_out,
                end_s=end_s,
            )
            route_files[(d, s)] = route_file

    warmup_str = (
        spec.warmup_design.value
        if isinstance(spec.warmup_design, WarmupDesign)
        else spec.warmup_design
    )
    run_specs: list[RunSpec] = []
    for c in spec.controllers:
        for d in spec.demand_levels:
            for s in range(spec.n_seeds):
                run_id = f"{c.name}_d{d}_s{s}"
                run_out = runs_dir / run_id
                route_file = route_files[(d, s)]
                config = RunConfig(
                    name=run_id,
                    master_seed=spec.master_seed,
                    warmup_s=spec.warmup_s,
                    measurement_s=spec.measurement_s,
                    cooldown_s=spec.cooldown_s,
                    warmup_design=warmup_str,
                )

                if c.type == "sumo_actuated":
                    assert net_actuated_path is not None and net_actuated_obj is not None
                    run_specs.append(
                        RunSpec(
                            run_id=run_id,
                            net=net_actuated_path,
                            routes=route_file,
                            network=net_actuated_obj,
                            controller_factory=None,
                            config=config,
                            seed_index=s,
                            transport=spec.transport,
                            step_length_s=spec.step_length_s,
                            output_dir=run_out,
                            controller_name=c.name,
                            demand_level=d,
                        )
                    )
                else:
                    assert net_static_path is not None and net_static_obj is not None
                    factory: Callable[[Network], Controller]
                    if c.type == "webster":
                        dt = c.decision_interval_s or 1.0
                        factory = functools.partial(
                            make_webster_controller, demand_level=d, decision_interval_s=dt
                        )
                    elif c.type == "actuated":
                        dt = c.decision_interval_s or 1.0
                        factory = functools.partial(
                            make_actuated_controller, decision_interval_s=dt
                        )
                    elif c.type == "max_pressure":
                        dt = c.decision_interval_s or 5.0
                        factory = functools.partial(
                            make_max_pressure_controller, decision_interval_s=dt
                        )
                    elif c.type == "custom":
                        if not c.factory:
                            raise ValueError(f"custom controller {c.name} requires factory path")
                        factory = _resolve_custom_factory(c.factory)
                    else:
                        raise ValueError(f"unsupported controller type: {c.type}")

                    run_specs.append(
                        RunSpec(
                            run_id=run_id,
                            net=net_static_path,
                            routes=route_file,
                            network=net_static_obj,
                            controller_factory=factory,
                            config=config,
                            seed_index=s,
                            transport=spec.transport,
                            step_length_s=spec.step_length_s,
                            output_dir=run_out,
                            controller_name=c.name,
                            demand_level=d,
                        )
                    )

    return run_specs


def run(spec: ExperimentSpec, out: Path) -> Path:
    """Expand and execute an ExperimentSpec, returning the experiment parquet path."""
    specs = expand_experiment(spec, out)
    jobs = max(1, (os.cpu_count() or 2) - 1) if spec.jobs == 0 else spec.jobs
    return run_many(specs, out, jobs=jobs)
