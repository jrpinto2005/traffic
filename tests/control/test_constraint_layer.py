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
    PHASE_CONFLICTING,
    build_layer,
    green_intervals,
    green_phase,
    network_with_a_conflicting_phase,
    run_steps,
    stage_of,
)
from tests.domain.factories import INTERSECTION, M_E, M_N, M_S, M_W, PHASE_EW, PHASE_NS
from traffic_lab.control.constraint_layer import SignalStage
from traffic_lab.domain.action import PhaseRequest, RequestOutcome
from traffic_lab.domain.network import PhaseId

CONTROL_DIR = Path(__file__).resolve().parents[2] / "traffic_lab" / "control"


def request(phase: PhaseId) -> PhaseRequest:
    return PhaseRequest(intersection=INTERSECTION, phase=phase)


# --- Invariant 1 ------------------------------------------------------------


def test_invariant_1_green_never_shorter_than_min_green() -> None:
    """Green never shorter than `min_green_s`, under a controller that switches
    as fast as it is allowed to ask.

    Dt is 1 s against a 5 s minimum green -- the most aggressive request pattern
    invariant 9 permits -- and the requested phase alternates every decision
    point, so every green interval is under continuous pressure to end early.
    """
    min_green_s = 5.0
    layer = build_layer(
        min_green_s=min_green_s, max_green_s=40.0, decision_interval_s=1.0, step_length_s=1.0
    )
    times_s = [float(i) for i in range(300)]

    def ask(now_s: float) -> None:
        layer.submit(request(PHASE_EW if int(now_s) % 2 else PHASE_NS), now_s)

    greens = run_steps(layer, times_s, on_step=ask)

    intervals = green_intervals(times_s, greens)
    assert len(intervals) > 10, "too few completed green intervals to prove anything"
    assert min(intervals) >= min_green_s - 1e-9
    assert layer.counters.deferred > 0, "no request was ever blocked by minimum green"


def test_invariant_1_an_early_request_is_deferred_and_says_when_it_can_act() -> None:
    layer = build_layer(min_green_s=5.0, decision_interval_s=1.0, step_length_s=1.0)
    layer.step(2.0)

    result = layer.submit(request(PHASE_EW), 2.0)

    assert result.outcome is RequestOutcome.DEFERRED
    assert result.active_phase == PHASE_NS
    assert result.reason, "a DEFERRED result must carry a reason"
    assert result.seconds_until_actionable == 3.0
    assert not layer.actionable(INTERSECTION)


def test_a_request_at_exactly_min_green_is_granted() -> None:
    layer = build_layer(min_green_s=5.0, decision_interval_s=1.0, step_length_s=1.0)
    layer.step(5.0)

    result = layer.submit(request(PHASE_EW), 5.0)

    assert result.outcome is RequestOutcome.GRANTED
    assert result.reason == ""
    assert result.active_phase == PHASE_EW
    assert layer.actionable(INTERSECTION) is False  # a transition is now in progress


def test_submitting_ahead_of_the_timers_is_refused() -> None:
    """The two-tier structure is a precondition, not a convention."""
    layer = build_layer()
    layer.step(4.0)
    try:
        layer.submit(request(PHASE_EW), 9.0)
    except ValueError as error:
        assert "step()" in str(error)
    else:  # pragma: no cover
        raise AssertionError("submitting at a time the timers had not reached was accepted")


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


# --- Invariant 4 ------------------------------------------------------------


def test_invariant_4_a_conflicting_phase_is_rejected() -> None:
    """A phase containing a `CONFLICTING` pair is REJECTED and never reaches the backend.

    The fixture is deliberately an *invalid* network -- `validate_network()`
    would refuse it under invariant 7 of `05_DOMAIN_MODEL.md` SS8. That is the
    point: the constraint layer is the last line of defence, and it must refuse
    the request on its own reading of the D-023 matrix rather than trusting that
    load-time validation happened.
    """
    layer = build_layer(network=network_with_a_conflicting_phase())
    layer.step(30.0)

    result = layer.submit(request(PHASE_CONFLICTING), 30.0)

    assert result.outcome is RequestOutcome.REJECTED
    assert result.active_phase == PHASE_NS, "the illegal phase must not take effect"
    assert result.reason, "a REJECTED result must carry a reason"
    assert "conflicting movement pair" in result.reason
    assert layer.counters.rejected == 1
    assert layer.counters.granted == 0


def test_invariant_4_the_rejection_names_the_offending_pair() -> None:
    """D-023 requires the error to name the pair, not merely to refuse."""
    layer = build_layer(network=network_with_a_conflicting_phase())
    layer.step(30.0)

    reason = layer.submit(request(PHASE_CONFLICTING), 30.0).reason

    assert str(M_N) in reason or str(M_S) in reason
    assert str(M_E) in reason or str(M_W) in reason


def test_invariant_4_a_conflicting_phase_never_goes_green() -> None:
    layer = build_layer(network=network_with_a_conflicting_phase(), decision_interval_s=1.0)
    times_s = [float(i) for i in range(200)]

    greens = run_steps(
        layer, times_s, on_step=lambda now_s: layer.submit(request(PHASE_CONFLICTING), now_s)
    )

    assert PHASE_CONFLICTING not in set(greens)
    assert layer.counters.rejected == len(times_s)


def test_an_unauthored_phase_is_rejected() -> None:
    layer = build_layer()
    layer.step(30.0)

    result = layer.submit(request(PhaseId(99)), 30.0)

    assert result.outcome is RequestOutcome.REJECTED
    assert "not an authored phase" in result.reason
    assert layer.counters.rejected == 1


# --- Invariant 5 ------------------------------------------------------------


def test_invariant_5_step_never_changes_the_pending_request() -> None:
    """`step()` executes the transition a request committed to; it never retargets it."""
    layer = build_layer(min_green_s=5.0, max_green_s=60.0, decision_interval_s=1.0)
    layer.step(10.0)
    granted = layer.submit(request(PHASE_EW), 10.0)
    assert granted.outcome is RequestOutcome.GRANTED

    for now_s in [float(i) for i in range(11, 40)]:
        layer.step(now_s)
        assert layer.signal_state(INTERSECTION).active_phase == PHASE_EW

    assert green_phase(layer) == PHASE_EW


def test_invariant_5_step_produces_no_request_outcomes_of_its_own() -> None:
    """Except FORCED, which is the layer's own override rather than a request."""
    layer = build_layer(min_green_s=5.0, max_green_s=20.0)

    run_steps(layer, [float(i) for i in range(200)])

    counters = layer.counters
    assert (counters.granted, counters.deferred, counters.held, counters.rejected) == (0, 0, 0, 0)
    assert counters.forced > 0


def test_invariant_5_stepping_does_not_disturb_a_recorded_decision() -> None:
    """The idempotency record is keyed to a decision time, not to step count."""
    layer = build_layer(min_green_s=5.0, decision_interval_s=1.0)
    layer.step(10.0)
    first = layer.submit(request(PHASE_EW), 10.0)

    layer.step(10.0)  # a second step at the same simulated time

    assert layer.submit(request(PHASE_EW), 10.0) == first
    assert layer.counters.granted == 1


# --- Invariant 6 ------------------------------------------------------------


def test_invariant_6_submit_is_idempotent_within_one_decision_interval() -> None:
    """The same request twice at the same `now_s`: same result, applied once."""
    layer = build_layer(min_green_s=5.0, decision_interval_s=1.0)
    layer.step(10.0)

    first = layer.submit(request(PHASE_EW), 10.0)
    started_s = layer.signal_state(INTERSECTION).phase_started_s
    second = layer.submit(request(PHASE_EW), 10.0)

    assert first.outcome is RequestOutcome.GRANTED
    assert second == first
    assert layer.counters.granted == 1
    assert layer.signal_state(INTERSECTION).phase_started_s == started_s


def test_invariant_6_idempotency_holds_for_refusals_too() -> None:
    """A repeated illegal request must not count twice; the count is diagnostic."""
    layer = build_layer(min_green_s=5.0, decision_interval_s=1.0)
    layer.step(2.0)

    first = layer.submit(request(PHASE_EW), 2.0)
    for _ in range(10):
        assert layer.submit(request(PHASE_EW), 2.0) == first

    assert first.outcome is RequestOutcome.DEFERRED
    assert layer.counters.deferred == 1


def test_invariant_6_a_new_decision_time_is_a_new_decision() -> None:
    layer = build_layer(min_green_s=5.0, decision_interval_s=1.0)
    layer.step(2.0)
    layer.submit(request(PHASE_EW), 2.0)
    layer.step(3.0)
    layer.submit(request(PHASE_EW), 3.0)

    assert layer.counters.deferred == 2


# --- HELD -------------------------------------------------------------------


def test_requesting_the_active_phase_is_held_not_deferred() -> None:
    """HELD before the timers: keeping what is running is always available."""
    layer = build_layer(min_green_s=5.0, decision_interval_s=1.0)
    layer.step(1.0)  # inside minimum green

    result = layer.submit(request(PHASE_NS), 1.0)

    assert result.outcome is RequestOutcome.HELD
    assert result.reason == ""
    assert result.active_phase == PHASE_NS
    assert layer.counters.held == 1
    assert layer.counters.deferred == 0


def test_requesting_the_committed_phase_mid_transition_is_held() -> None:
    """During a transition `active_phase` is the target, so naming it is a hold."""
    layer = build_layer(min_green_s=5.0, decision_interval_s=1.0)
    layer.step(10.0)
    layer.submit(request(PHASE_EW), 10.0)
    layer.step(11.0)

    assert layer.signal_state(INTERSECTION).in_transition
    result = layer.submit(request(PHASE_EW), 11.0)

    assert result.outcome is RequestOutcome.HELD
    assert layer.submit(request(PHASE_NS), 11.0).outcome is RequestOutcome.DEFERRED


# --- The legal-action mask (D-020, adopted from PyTSC via T0.1) --------------


def test_allowed_phases_is_every_legal_phase_when_actionable() -> None:
    layer = build_layer(min_green_s=5.0, decision_interval_s=1.0)
    layer.step(10.0)

    assert layer.actionable(INTERSECTION)
    assert layer.allowed_phases(INTERSECTION) == frozenset({PHASE_NS, PHASE_EW})


def test_allowed_phases_excludes_a_conflicting_phase() -> None:
    layer = build_layer(network=network_with_a_conflicting_phase(), decision_interval_s=1.0)
    layer.step(30.0)

    assert PHASE_CONFLICTING not in layer.allowed_phases(INTERSECTION)


def test_allowed_phases_is_the_active_phase_alone_when_blocked() -> None:
    layer = build_layer(min_green_s=5.0, decision_interval_s=1.0)
    layer.step(2.0)

    assert not layer.actionable(INTERSECTION)
    assert layer.allowed_phases(INTERSECTION) == frozenset({PHASE_NS})


def test_allowed_phases_is_never_empty() -> None:
    """A masked action space with no legal action is a stuck policy, not a
    constrained one."""
    layer = build_layer(min_green_s=5.0, max_green_s=12.0, decision_interval_s=1.0)

    for now_s in [i * 0.5 for i in range(200)]:
        layer.step(now_s)
        assert layer.allowed_phases(INTERSECTION)


def test_a_phase_in_the_mask_is_never_refused() -> None:
    """The mask's contract: what it offers, `submit()` accepts.

    This is what lets a controller avoid making an illegal request rather than
    being refused after the fact (D-020).

    One request per decision point, which is what a controller does: the mask
    says which single action would be accepted now, and acting on one of them
    changes the state the rest were computed against.
    """
    layer = build_layer(min_green_s=5.0, max_green_s=25.0, decision_interval_s=1.0)

    for step_index, now_s in enumerate(float(i) for i in range(400)):
        layer.step(now_s)
        mask = sorted(layer.allowed_phases(INTERSECTION))
        assert mask, "the mask must never be empty"
        phase = mask[step_index % len(mask)]
        outcome = layer.submit(request(phase), now_s).outcome
        assert outcome in (RequestOutcome.GRANTED, RequestOutcome.HELD), (
            f"phase {phase} was offered by the mask at {now_s} s but got {outcome}"
        )

    assert layer.counters.rejected == 0
    assert layer.counters.deferred == 0
    assert layer.counters.granted > 0


# --- display() (T1.14, D-034) -------------------------------------------------


def test_display_names_the_phase_being_left_during_yellow() -> None:
    """GREEN shows the active phase; YELLOW the phase being left, although
    `signal_state()` already names the target; ALL_RED shows no phase."""
    layer = build_layer(min_green_s=5.0, max_green_s=60.0, decision_interval_s=1.0)
    shown: list[tuple[float, tuple[SignalStage, PhaseId | None], PhaseId]] = []
    for now_s in (float(i) for i in range(16)):
        layer.step(now_s)
        if now_s == 5.0:
            assert layer.submit(PhaseRequest(INTERSECTION, PHASE_EW), now_s).outcome is (
                RequestOutcome.GRANTED
            )
        shown.append(
            (now_s, layer.display(INTERSECTION), layer.signal_state(INTERSECTION).active_phase)
        )

    by_time = {now_s: (display, active) for now_s, display, active in shown}
    assert by_time[4.0] == ((SignalStage.GREEN, PHASE_NS), PHASE_NS)
    for now_s in (5.0, 6.0, 7.0):  # yellow_s = 3 s, from the grant at 5 s
        assert by_time[now_s] == ((SignalStage.YELLOW, PHASE_NS), PHASE_EW)
    for now_s in (8.0, 9.0):  # all_red_s = 2 s
        assert by_time[now_s] == ((SignalStage.ALL_RED, None), PHASE_EW)
    assert by_time[10.0] == ((SignalStage.GREEN, PHASE_EW), PHASE_EW)


def test_display_follows_a_forced_max_green_override() -> None:
    layer = build_layer(min_green_s=5.0, max_green_s=10.0, all_red_s=0.0)
    displays = []
    for now_s in (float(i) for i in range(30)):
        layer.step(now_s)
        displays.append(layer.display(INTERSECTION))

    assert layer.counters.forced >= 2
    # No all-red stage when all_red_s is 0; each yellow names the phase it ends.
    assert (SignalStage.ALL_RED, None) not in displays
    assert displays[10] == (SignalStage.YELLOW, PHASE_NS)
    assert displays[13] == (SignalStage.GREEN, PHASE_EW)
    assert displays[23] == (SignalStage.YELLOW, PHASE_EW)


def test_display_is_read_only() -> None:
    layer = build_layer()
    layer.step(0.0)
    before = (layer.signal_state(INTERSECTION), layer.counters.forced)
    for _ in range(3):
        layer.display(INTERSECTION)
    assert (layer.signal_state(INTERSECTION), layer.counters.forced) == before
