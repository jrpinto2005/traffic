"""Initial-state snapshot production, keying, and loading (T1.6, D-018, D-032).

Warm-up from empty is how a snapshot is produced; loading a snapshot is how
warm-up wall-clock is avoided on subsequent runs in a sweep.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

from traffic_lab.backend import Backend, BackendConfig, SumoBackend, TransportName
from traffic_lab.control.constraint_layer import ConstraintLayer, ConstraintLayerConfig
from traffic_lab.control.controller import Controller
from traffic_lab.domain.network import IntersectionId, Network, PhaseId
from traffic_lab.domain.state import SignalStage
from traffic_lab.estimation import IdentityEstimator
from traffic_lab.experiments.runner import ORACLE_SENSOR, derive_gridlock_steps
from traffic_lab.sensing import OracleSensor

_TIME_EPS_S = 1e-6


class WarmupDesign(StrEnum):
    """D-032 warm-up designs."""

    SELF = "self"
    """Each arm warms up under its own controller."""

    NEUTRAL_SNAPSHOT = "neutral_snapshot"
    """All arms load one shared snapshot state (e.g. Webster-generated)."""


def snapshot_key(net_hash: str, demand_level: float, seed: int, design: WarmupDesign | str) -> str:
    """Canonical cache key for a snapshot based on network, demand level, seed, and design.

    Keyed strictly on these four fields per T1.6 contract.
    """
    design_str = WarmupDesign(design).value
    return f"{net_hash}_{demand_level}_{seed}_{design_str}"


def produce(
    net: Path,
    routes: Path,
    network: Network,
    warmup_s: float,
    output_path: Path,
    *,
    step_length_s: float = 1.0,
    seed: int = 42,
    transport: TransportName = "libsumo",
    controller_factory: Callable[[Network], Controller] | None = None,
) -> Path:
    """Run warm-up up to `warmup_s`, save state to `output_path`, and return `output_path`.

    Saves simulator state and its sidecar manifest carrying network hash and SUMO version.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if warmup_s <= 0.0:
        raise ValueError(f"warmup_s must be positive to produce a snapshot, got {warmup_s}")

    gridlock_steps = derive_gridlock_steps(network, step_length_s)

    if controller_factory is not None:
        controller = controller_factory(network)
        decision_interval_s = controller.decision_interval_s
    else:
        controller = None
        decision_interval_s = step_length_s

    layer = ConstraintLayer(
        network,
        ConstraintLayerConfig(decision_interval_s=decision_interval_s, step_length_s=step_length_s),
        start_s=0.0,
    )
    sensor = OracleSensor(ORACLE_SENSOR, network)
    estimator = IdentityEstimator(network)
    intersections = tuple(i.id for i in network.signalized_intersections)

    backend = SumoBackend()
    backend.start(
        net,
        routes,
        BackendConfig(
            transport=transport,
            step_length_s=step_length_s,
            seed=seed,
            decision_interval_s=decision_interval_s,
            gridlock_steps=gridlock_steps,
        ),
        network=network,
    )
    try:
        from traffic_lab.experiments.runner import _apply_display_changes

        shown: dict[IntersectionId, tuple[SignalStage, PhaseId | None]] = {}
        _apply_display_changes(backend, layer, network, intersections, shown)

        decisions = 1
        next_decision_s = decisions * decision_interval_s
        state = None

        while state is None or state.time_s < warmup_s - _TIME_EPS_S:
            backend.step()
            state = backend.project()
            now_s = state.time_s

            layer.step(now_s)

            if controller is not None and now_s + _TIME_EPS_S >= next_decision_s:
                obs = sensor.observe(state, now_s)
                own = tuple(layer.signal_state(i) for i in intersections)
                est = estimator.update(obs, own, now_s)
                request = controller.decide(est, now_s)
                layer.submit(request, now_s)
                decisions += 1
                next_decision_s = decisions * decision_interval_s

            _apply_display_changes(backend, layer, network, intersections, shown)

        projector = backend._require_projector()
        projector._counters.arrived_at_sink = 0
        projector._counters.arrived_mid_link = 0
        projector._counters.teleports = 0
        projector._counters.motionless_steps = 0
        projector._counters.gridlock_detected = False

        backend.save_state(output_path)
    finally:
        backend.close()

    return output_path


def load_into(backend: Backend, path: Path) -> None:
    """Load snapshot state into the backend.

    Raises `SnapshotMismatchError` if network hash or SUMO version mismatches,
    or if the sidecar file is missing (D-032).
    """
    backend.load_state(path)
