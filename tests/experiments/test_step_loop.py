"""`run_one`'s step loop against `06_ARCHITECTURE.md` SS6.2 (T1.11 Amendment A2).

Off-by-one errors in decision timing, at the window's edges, or in which signal
view the estimator gets are silent: the run completes and its numbers are
merely wrong. Each is pinned here on a real SUMO run, watched from inside a
fresh process (`tests/experiments/support.py`).
"""

from __future__ import annotations

import functools
import math
from pathlib import Path

import polars as pl
import pytest

from tests.backend.conftest import Scenario
from tests.experiments.controllers import Recording
from tests.experiments.support import CONFIG, Display, Instrumented, make_spec, watch
from traffic_lab.backend import TransportName, display_state
from traffic_lab.domain.network import IntersectionId
from traffic_lab.domain.state import SignalStage


@pytest.mark.parametrize(
    ("step_length_s", "decision_interval_s"), [(1.0, 1.0), (1.0, 5.0), (0.5, 1.0), (0.5, 2.5)]
)
def test_states_every_step_and_decisions_every_dt(
    scenario: Scenario, tmp_path: Path, step_length_s: float, decision_interval_s: float
) -> None:
    """A state at every step from the first to exactly the run's end; a decision at
    every multiple of Dt from Dt on, each on the state of that instant."""
    run = watch(
        make_spec(
            scenario,
            tmp_path / "run",
            functools.partial(Recording, decision_interval_s=decision_interval_s),
            step_length_s=step_length_s,
        )
    )
    end_s = CONFIG.warmup_s + CONFIG.measurement_s + CONFIG.cooldown_s
    n_steps = round(end_s / step_length_s)
    assert [s.time_s for s in run.states] == [k * step_length_s for k in range(1, n_steps + 1)]
    assert run.states[-1].time_s == end_s

    n_decisions = math.floor(end_s / decision_interval_s + 1e-9)
    expected = [k * decision_interval_s for k in range(1, n_decisions + 1)]
    assert [d.now_s for d in run.decisions] == pytest.approx(expected, abs=1e-9)
    state_times = {s.time_s for s in run.states}
    for decision in run.decisions:
        assert decision.now_s in state_times  # decided on a real state, not between two
        assert decision.est_time_s == decision.now_s
        assert decision.lanes_seen == len(scenario.network.lanes)


def test_the_window_is_warmup_end_to_measurement_end(scenario: Scenario, tmp_path: Path) -> None:
    """The row's lane queues are exactly the mean and maximum over the states in
    `[warmup_s, warmup_s + measurement_s)` -- one state more or fewer at either
    edge changes them."""
    run = watch(make_spec(scenario, tmp_path / "run", Recording))
    row = pl.read_parquet(run.result).row(0, named=True)
    start_s, end_s = CONFIG.warmup_s, CONFIG.warmup_s + CONFIG.measurement_s
    assert (row["window_start_s"], row["window_end_s"]) == (start_s, end_s)

    inside = [s for s in run.states if start_s <= s.time_s < end_s]
    assert len(inside) == CONFIG.measurement_s  # 1 s steps
    queues = [[lane.queue_count for lane in s.lanes] for s in inside]
    for lane in range(len(scenario.network.lanes)):
        series = [q[lane] for q in queues]
        assert row[f"queue_mean_veh.lane_{lane}"] == pytest.approx(sum(series) / len(series))
        assert row[f"max_queue_veh.lane_{lane}"] == max(series)
    # Non-vacuous: queues formed, and the edges of the window matter.
    assert any(any(q) for q in queues)
    edge_states = [s for s in run.states if s.time_s in (start_s - 1, end_s)]
    assert any(any(lane.queue_count for lane in s.lanes) for s in edge_states)


def test_the_estimator_gets_the_constraint_layers_signals(
    scenario: Scenario, tmp_path: Path
) -> None:
    """D-033. During a transition the two views differ (D-034): the constraint
    layer names the phase being entered, `TrueState` the phase being left. The
    controller must see the former."""
    run = watch(make_spec(scenario, tmp_path / "run", Recording))
    phases = [p.id for p in scenario.built.intersection.phases]
    by_time = {s.time_s: s for s in run.states}

    # Recording asks for the next phase from 10 s, when minimum green (10 s) has
    # elapsed, so the change is granted at 10 s and the next decision is mid-yellow.
    (own,) = next(d for d in run.decisions if d.now_s == 11.0).signals
    (shown,) = by_time[11.0].signals
    assert own.in_transition and shown.in_transition
    assert own.active_phase == phases[1]  # entering
    assert shown.active_phase == phases[0]  # leaving
    assert own.phase_started_s == shown.phase_started_s == 10.0

    # Every transition the controller saw names the phase being entered.
    seen = [d.signals[0] for d in run.decisions if d.signals[0].in_transition]
    assert seen
    for decision in run.decisions:
        (own,) = decision.signals
        (shown,) = by_time[decision.now_s].signals
        if own.in_transition:
            assert own.active_phase != shown.active_phase
        elif own.green_started_s is not None and own.green_started_s < decision.now_s - 1.0:
            # Settled green: both views agree exactly outside transitions (D-034).
            assert own == shown


def _display_changes(run: Instrumented) -> list[tuple[float, IntersectionId, Display]]:
    """The display answers that differ from the previous answer for that intersection."""
    last: dict[IntersectionId, Display] = {}
    changes = []
    for time_s, intersection, display in run.displays:
        if last.get(intersection) != display:
            changes.append((time_s, intersection, display))
            last[intersection] = display
    return changes


@pytest.mark.parametrize("transport", ["libsumo", "traci"])
def test_the_display_is_applied_only_when_it_changes(
    scenario: Scenario, tmp_path: Path, transport: TransportName
) -> None:
    run = watch(make_spec(scenario, tmp_path / "run", Recording, transport=transport))
    network = scenario.network
    changes = _display_changes(run)

    # One apply() per change of what the layer says to show, carrying exactly it.
    assert len(run.applied) == len(changes)
    for (applied_at, applied_to, string), (changed_at, intersection, display) in zip(
        run.applied, changes, strict=True
    ):
        stage, phase = display
        assert (applied_at, applied_to) == (changed_at, intersection)
        assert string == display_state(network, intersection, stage, phase)
    assert run.applied[0][0] == 0.0  # before the first step
    # Far fewer than one per step -- Recording changes phase as often as minimum
    # green allows, three display changes every 15 s -- through every stage.
    assert 10 < len(run.applied) < len(run.states) / 4
    stages = [display[0] for _, _, display in changes]
    assert {SignalStage.GREEN, SignalStage.YELLOW, SignalStage.ALL_RED} <= set(stages)

    # SUMO keeps showing what it was last sent: whatever was applied after the
    # state at t is what `TrueState` decodes at t + 1.
    current: Display | None = None
    applied_by_time = {t: display for t, _, display in changes}
    checked = 0
    for state in run.states:
        previous_s = state.time_s - 1.0
        if previous_s in applied_by_time:
            current = applied_by_time[previous_s]
        assert current is not None
        stage, phase = current
        (shown,) = state.signals
        if stage is SignalStage.GREEN:
            assert not shown.in_transition and shown.active_phase == phase
            checked += 1
        else:
            assert shown.in_transition
    assert checked > len(run.states) / 2
