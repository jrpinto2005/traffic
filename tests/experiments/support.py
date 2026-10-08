"""Building run specs and watching runs from the inside. Test support only.

`instrumented_run` executes `run_one` with three read-only taps -- every
projected `TrueState`, every `ConstraintLayer.display()` answer, every
`SumoBackend.apply()` call -- plus what a `Recording` controller saw. It
patches classes, so it belongs in a process of its own: `in_fresh_process`
runs it in a `spawn` worker that serves one task, as `run_many` does, so the
taps never outlive the run and SUMO's RNG history starts clean (T1.4).
"""

from __future__ import annotations

import multiprocessing
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tests.backend.conftest import Scenario
from tests.experiments.controllers import Decision, Recording
from traffic_lab.backend import SumoBackend, TransportName
from traffic_lab.control.constraint_layer import ConstraintLayer
from traffic_lab.control.controller import Controller
from traffic_lab.domain.network import IntersectionId, Network, PhaseId
from traffic_lab.domain.state import SignalStage, TrueState
from traffic_lab.experiments.config import RunConfig
from traffic_lab.experiments.runner import RunSpec, run_one

#: D-008's N for every test run: five minutes of nothing moving. Large enough
#: that a red phase never trips it on this scenario; not a research value.
TEST_GRIDLOCK_STEPS = 300

#: One minute of warm-up, five of measurement, one of cool-down.
CONFIG = RunConfig(
    name="t1.11", master_seed=42, warmup_s=60.0, measurement_s=300.0, cooldown_s=60.0
)


def make_spec(
    scenario: Scenario,
    output_dir: Path,
    controller_factory: Callable[[Network], Controller],
    *,
    run_id: str | None = None,
    routes: Path | None = None,
    seed_index: int = 0,
    config: RunConfig = CONFIG,
    step_length_s: float = 1.0,
    transport: TransportName = "libsumo",
) -> RunSpec:
    return RunSpec(
        run_id=run_id if run_id is not None else output_dir.name,
        net=scenario.net,
        routes=routes if routes is not None else scenario.routes,
        network=scenario.network,
        controller_factory=controller_factory,
        config=config,
        seed_index=seed_index,
        transport=transport,
        step_length_s=step_length_s,
        output_dir=output_dir,
        gridlock_steps=TEST_GRIDLOCK_STEPS,
    )


Display = tuple[SignalStage, PhaseId | None]


@dataclass(frozen=True)
class Instrumented:
    result: Path
    states: tuple[TrueState, ...]
    #: Every `display()` answer, stamped with the last projected state's time (0 before any).
    displays: tuple[tuple[float, IntersectionId, Display], ...]
    #: Every `apply()` call, stamped the same way.
    applied: tuple[tuple[float, IntersectionId, str], ...]
    #: What the controller saw, if it records (`tests.experiments.controllers.Recording`).
    decisions: tuple[Decision, ...]


def instrumented_run(spec: RunSpec) -> Instrumented:
    """`run_one(spec)`, watched. Call only through `in_fresh_process`."""
    states: list[TrueState] = []
    displays: list[tuple[float, IntersectionId, Display]] = []
    applied: list[tuple[float, IntersectionId, str]] = []

    project = SumoBackend.project
    apply = SumoBackend.apply
    display = ConstraintLayer.display

    def now() -> float:
        return states[-1].time_s if states else 0.0

    def tapped_project(self: SumoBackend) -> TrueState:
        state = project(self)
        states.append(state)
        return state

    def tapped_apply(self: SumoBackend, intersection: IntersectionId, phase_state: str) -> None:
        applied.append((now(), intersection, phase_state))
        apply(self, intersection, phase_state)

    def tapped_display(self: ConstraintLayer, intersection: IntersectionId) -> Display:
        shown = display(self, intersection)
        displays.append((now(), intersection, shown))
        return shown

    patch = pytest.MonkeyPatch()
    patch.setattr(SumoBackend, "project", tapped_project)
    patch.setattr(SumoBackend, "apply", tapped_apply)
    patch.setattr(ConstraintLayer, "display", tapped_display)
    try:
        result = run_one(spec)
    finally:
        patch.undo()
    recorded = Recording.instances[-1].decisions if Recording.instances else []
    return Instrumented(result, tuple(states), tuple(displays), tuple(applied), tuple(recorded))


def in_fresh_process(function: Callable[..., Any], *args: Any) -> Any:
    """`function(*args)` in a new `spawn` process that serves this one call."""
    with ProcessPoolExecutor(
        max_workers=1, mp_context=multiprocessing.get_context("spawn"), max_tasks_per_child=1
    ) as pool:
        return pool.submit(function, *args).result()


def watch(spec: RunSpec) -> Instrumented:
    """`instrumented_run(spec)` in a fresh process."""
    watched: Instrumented = in_fresh_process(instrumented_run, spec)
    return watched
