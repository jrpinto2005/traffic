"""One test per invariant of `08_AGENT_HANDOFF_PROTOCOL.md` SS9, named for it.

The seven invariants:

1. Green never shorter than `min_green_s`, except during simulation shutdown.
2. Green never longer than `max_green_s` when non-zero; the layer returns FORCED.
3. Every phase change is followed by exactly `yellow_s` then `all_red_s` before
   the next green begins. Transitions are executed by `step()`, never `submit()`.
4. A request whose phase contains a `CONFLICTING` movement pair is REJECTED.
5. `step()` is pure with respect to requests.
6. `submit()` is idempotent within one decision interval.
7. Timers depend only on simulated time, never wall-clock time.

The property-based test the acceptance criteria also require lives in
`test_constraint_properties.py`, because it covers invariants 1 and 4 jointly
over random inputs rather than either one on a fixture.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.control.harness import (
    DEFAULT_ALL_RED_S,
    DEFAULT_YELLOW_S,
    build_layer,
    green_intervals,
    green_phase,
    run_steps,
    stage_of,
)
from tests.domain.factories import INTERSECTION, PHASE_EW, PHASE_NS
from traffic_lab.control.constraint_layer import SignalStage

CONTROL_DIR = Path(__file__).resolve().parents[2] / "traffic_lab" / "control"


# --- Invariant 2 ------------------------------------------------------------


def test_invariant_2_green_never_longer_than_max_green() -> None:
    """Green never longer than `max_green_s` when it is non-zero.

    No request is ever submitted here: the point is that the *layer* ends the
    green on its own, from `step()`, between decision points.
    """
    max_green_s = 20.0
    layer = build_layer(min_green_s=5.0, max_green_s=max_green_s)
    times_s = [float(i) for i in range(200)]

    greens = run_steps(layer, times_s)

    intervals = green_intervals(times_s, greens)
    assert intervals, "the run was too short to complete a green interval"
    assert max(intervals) <= max_green_s + 1e-9


def test_invariant_2_max_green_expiry_is_reported_as_forced() -> None:
    layer = build_layer(min_green_s=5.0, max_green_s=20.0)

    run_steps(layer, [float(i) for i in range(60)])

    assert layer.counters.forced >= 2
    # Nothing was ever requested, so no other outcome can have been produced.
    assert layer.counters.granted == 0
    assert layer.counters.rejected == 0


def test_invariant_2_max_green_of_zero_disables_the_override() -> None:
    """`max_green_s == 0.0` disables the override (`05_DOMAIN_MODEL.md` SS2.7)."""
    layer = build_layer(min_green_s=5.0, max_green_s=0.0)

    greens = run_steps(layer, [float(i) for i in range(500)])

    assert layer.counters.forced == 0
    assert set(greens) == {PHASE_NS}


def test_invariant_2_the_forced_phase_is_the_next_one_in_authored_order() -> None:
    layer = build_layer(min_green_s=5.0, max_green_s=10.0)

    greens = run_steps(layer, [float(i) for i in range(120)])

    served = [phase for phase in greens if phase is not None]
    ordered = [phase for i, phase in enumerate(served) if i == 0 or phase != served[i - 1]]
    assert ordered[:4] == [PHASE_NS, PHASE_EW, PHASE_NS, PHASE_EW]


# --- Invariant 3 ------------------------------------------------------------


def test_invariant_3_a_phase_change_is_exactly_yellow_then_all_red() -> None:
    """Every phase change is followed by exactly `yellow_s`, then `all_red_s`.

    Driven by the max-green override so that the transition is entirely
    `step()`'s doing -- which is the second half of the invariant.
    """
    max_green_s = 10.0
    layer = build_layer(min_green_s=5.0, max_green_s=max_green_s, step_length_s=0.5)

    stages: list[tuple[float, SignalStage]] = []
    for now_s in (i * 0.5 for i in range(60)):
        layer.step(now_s)
        stages.append((now_s, stage_of(layer)))

    yellow = [now_s for now_s, stage in stages if stage is SignalStage.YELLOW]
    all_red = [now_s for now_s, stage in stages if stage is SignalStage.ALL_RED]
    assert yellow, "no yellow interval was executed"
    assert all_red, "no all-red interval was executed"

    # The first transition: yellow starts the step max green expires, all-red
    # follows it, and green resumes after both.
    first_yellow_s = yellow[0]
    assert first_yellow_s == max_green_s
    assert min(all_red) == first_yellow_s + DEFAULT_YELLOW_S
    resumed = [
        now_s for now_s, stage in stages if stage is SignalStage.GREEN and now_s > first_yellow_s
    ]
    assert min(resumed) == first_yellow_s + DEFAULT_YELLOW_S + DEFAULT_ALL_RED_S

    # The whole first transition, stage by stage: 3 s of yellow then 2 s of
    # all-red at a 0.5 s step, and nothing else in between.
    window = {now_s: stage for now_s, stage in stages if 10.0 <= now_s <= 15.0}
    assert window == {
        10.0: SignalStage.YELLOW,
        10.5: SignalStage.YELLOW,
        11.0: SignalStage.YELLOW,
        11.5: SignalStage.YELLOW,
        12.0: SignalStage.YELLOW,
        12.5: SignalStage.YELLOW,
        13.0: SignalStage.ALL_RED,
        13.5: SignalStage.ALL_RED,
        14.0: SignalStage.ALL_RED,
        14.5: SignalStage.ALL_RED,
        15.0: SignalStage.GREEN,
    }


def test_invariant_3_no_phase_is_green_during_a_transition() -> None:
    """The clearance is a gap in service, not a handover.

    This is what makes "no conflicting pair is ever simultaneously green" hold
    for an intersection whose two phases conflict with each other.
    """
    layer = build_layer(min_green_s=5.0, max_green_s=10.0)

    for now_s in (i * 0.5 for i in range(60)):
        layer.step(now_s)
        if layer.signal_state(INTERSECTION).in_transition:
            assert green_phase(layer) is None


def test_invariant_3_a_coarse_step_cannot_shorten_a_transition() -> None:
    """A step length spanning the whole clearance must not truncate it.

    Stage boundaries are scheduled in absolute simulated time, so the transition
    lasts at least `yellow_s + all_red_s` however coarsely it is sampled.
    """
    layer = build_layer(min_green_s=5.0, max_green_s=10.0, yellow_s=3.0, all_red_s=2.0)

    times_s = [float(i) for i in range(0, 60)]
    greens = run_steps(layer, times_s)

    gaps = [now_s for now_s, green in zip(times_s, greens, strict=True) if green is None]
    assert gaps, "no transition occurred"
    # The transition beginning at t = 10 covers the steps at 10, 11, 12, 13, 14
    # and green resumes at 15 = 10 + 3 + 2.
    assert gaps[:5] == [10.0, 11.0, 12.0, 13.0, 14.0]
    assert greens[times_s.index(15.0)] == PHASE_EW


# --- Invariant 7 ------------------------------------------------------------


def test_invariant_7_timers_depend_only_on_simulated_time() -> None:
    """No module in `control/` may import a wall clock.

    Checked by static AST inspection of each module's own imports, in the style
    of `tests/domain/test_import_boundary.py`: importing the package and
    inspecting it would only prove today's transitive closure is clean. D-017's
    reproducibility rests on this -- a timer keyed to `time.monotonic()` would
    make a run's signal timing depend on how fast the machine was.
    """
    forbidden = {"time", "datetime", "timeit", "perf_counter", "monotonic"}
    violations: dict[str, set[str]] = {}
    for path in sorted(CONTROL_DIR.glob("*.py")):
        names: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                names.add(node.module.split(".")[0])
                names.update(alias.name for alias in node.names)
        hit = names & forbidden
        if hit:
            violations[path.name] = hit
    assert not violations, f"control modules import a wall clock: {violations}"


def test_invariant_7_stepping_the_same_simulated_time_twice_advances_nothing() -> None:
    """Repeated `step()` at one simulated time is a no-op, however long it takes.

    The behavioural half of invariant 7: if any timer keyed off anything other
    than `now_s`, calling `step()` a hundred times at the same `now_s` would
    move the machine.
    """
    layer = build_layer(min_green_s=5.0, max_green_s=10.0)
    for now_s in [float(i) for i in range(11)]:
        layer.step(now_s)
    assert stage_of(layer) is SignalStage.YELLOW

    for _ in range(100):
        layer.step(11.0)

    assert stage_of(layer) is SignalStage.YELLOW
    assert layer.counters.forced == 1


def test_invariant_7_two_layers_driven_identically_agree_exactly() -> None:
    """Determinism under D-017: same simulated inputs, same signal history."""
    times_s = [i * 0.5 for i in range(300)]
    first = run_steps(build_layer(min_green_s=5.0, max_green_s=17.5), times_s)
    second = run_steps(build_layer(min_green_s=5.0, max_green_s=17.5), times_s)
    assert first == second


def test_simulated_time_may_not_run_backwards() -> None:
    layer = build_layer()
    layer.step(10.0)
    try:
        layer.step(9.0)
    except ValueError as error:
        assert "backwards" in str(error)
    else:  # pragma: no cover
        raise AssertionError("stepping backwards was accepted")


# --- D-020's known gap ------------------------------------------------------


def test_a_max_green_override_never_fires_during_a_transition() -> None:
    """D-020 leaves open what happens when max green expires mid-transition.

    The provisional answer on file is that the override waits. It is
    implemented, and it is also unreachable: `max_green_s` measures the green
    interval, which is not running during a transition. This test is the
    measurement rather than the claim -- if the case ever becomes reachable the
    counter stops being zero and someone sees it.

    The timing is chosen adversarially: `max_green_s` is *shorter* than the
    clearance that follows it, which is the only shape under which a
    green-interval clock could plausibly still be running mid-transition.
    """
    layer = build_layer(
        min_green_s=2.0,
        max_green_s=4.0,
        yellow_s=3.0,
        all_red_s=2.0,
        decision_interval_s=2.0,
        step_length_s=0.25,
    )

    for now_s in (i * 0.25 for i in range(800)):
        layer.step(now_s)
        assert layer.counters.overrides_deferred_by_transition == 0

    assert layer.counters.forced > 10, "the override never fired; the test proves nothing"


def test_max_green_overshoot_is_recorded_when_it_does_not_fall_on_the_step_grid() -> None:
    """The overshoot D-020 asks to be made visible rather than silent.

    `max_green_s = 10.5` with a 1 s step cannot be honoured exactly: the green
    ends at the first step at or past it, so it runs 11 s. Half a second of
    overshoot, recorded rather than swallowed.
    """
    layer = build_layer(min_green_s=5.0, max_green_s=10.5, step_length_s=1.0)

    run_steps(layer, [float(i) for i in range(40)])

    assert layer.counters.forced >= 2
    assert layer.counters.max_green_worst_overshoot_s == 0.5
    assert layer.counters.max_green_overshoot_s == 0.5 * layer.counters.forced


def test_no_overshoot_is_recorded_when_max_green_falls_on_the_step_grid() -> None:
    layer = build_layer(min_green_s=5.0, max_green_s=10.0, step_length_s=1.0)

    run_steps(layer, [float(i) for i in range(40)])

    assert layer.counters.forced >= 2
    assert layer.counters.max_green_overshoot_s == 0.0
    assert layer.counters.max_green_worst_overshoot_s == 0.0
