"""The property the acceptance criteria name, over random inputs.

> For any random sequence of requests at any Dt, no green interval is ever
> shorter than `min_green_s` and no conflicting pair is ever simultaneously
> green.

Both halves are checked on the same runs, because they are the two ways the
same failure shows up: a layer that let a green end early would also be a layer
that could start the next one before the clearance finished.

The request stream deliberately includes phases that do not exist and a phase
that contains a `CONFLICTING` pair, so the property is tested against a
controller behaving badly rather than one behaving well. That is the case the
constraint layer exists for.
"""

from __future__ import annotations

import itertools

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.control.harness import (
    PHASE_CONFLICTING,
    build_layer,
    network_with_a_conflicting_phase,
)
from tests.domain.factories import INTERSECTION, PHASE_EW, PHASE_NS
from traffic_lab.domain.action import PhaseRequest
from traffic_lab.domain.network import (
    Compatibility,
    MovementId,
    Network,
    PhaseId,
    SignalizedIntersection,
    compatibility,
)

STEP_LENGTHS_S = (0.1, 0.25, 0.5, 1.0)
REQUESTABLE_PHASES = (PHASE_NS, PHASE_EW, PHASE_CONFLICTING, PhaseId(7), PhaseId(-1))


def _movements_of_phase(
    intersection: SignalizedIntersection, phase_id: PhaseId
) -> frozenset[MovementId]:
    by_group = {group.id: group.movements for group in intersection.signal_groups}
    phase = next(p for p in intersection.phases if p.id == phase_id)
    return frozenset(movement for group_id in phase.green_groups for movement in by_group[group_id])


def _assert_conflict_free(network: Network, phase_id: PhaseId) -> None:
    intersection = network.signalized_intersections[0]
    conflicts = network.junctions[0].conflicts
    movements = sorted(_movements_of_phase(intersection, phase_id))
    for a, b in itertools.combinations(movements, 2):
        assert compatibility(conflicts, a, b) is not Compatibility.CONFLICTING, (
            f"movements {a} and {b} were simultaneously green under phase {phase_id}"
        )
        assert compatibility(conflicts, b, a) is not Compatibility.CONFLICTING, (
            f"movements {b} and {a} were simultaneously green under phase {phase_id}"
        )


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    min_green_s=st.floats(min_value=1.0, max_value=10.0),
    extra_max_green_s=st.floats(min_value=0.5, max_value=30.0),
    max_green_disabled=st.booleans(),
    yellow_s=st.floats(min_value=0.0, max_value=5.0),
    all_red_s=st.floats(min_value=0.0, max_value=5.0),
    step_length_s=st.sampled_from(STEP_LENGTHS_S),
    interval_multiple=st.integers(min_value=1, max_value=40),
    requests=st.lists(st.sampled_from(REQUESTABLE_PHASES), min_size=1, max_size=40),
    step_count=st.integers(min_value=50, max_value=400),
)
def test_no_green_is_shorter_than_min_green_and_no_conflicting_pair_is_ever_green(
    min_green_s: float,
    extra_max_green_s: float,
    max_green_disabled: bool,
    yellow_s: float,
    all_red_s: float,
    step_length_s: float,
    interval_multiple: int,
    requests: list[PhaseId],
    step_count: int,
) -> None:
    # Dt must be an integer multiple of the step length and at most the minimum
    # green (D-020, invariant 9). Both are config constraints the layer already
    # rejects, so the strategy produces only configurations it would accept --
    # the property is about behaviour, not about validation.
    max_multiple = max(1, int(min_green_s / step_length_s))
    decision_interval_s = (interval_multiple % max_multiple + 1) * step_length_s
    if decision_interval_s > min_green_s:
        decision_interval_s = step_length_s

    network = network_with_a_conflicting_phase()
    layer = build_layer(
        network=network,
        min_green_s=min_green_s,
        max_green_s=0.0 if max_green_disabled else min_green_s + extra_max_green_s,
        yellow_s=yellow_s,
        all_red_s=all_red_s,
        decision_interval_s=decision_interval_s,
        step_length_s=step_length_s,
    )

    next_decision_s = 0.0
    requested = itertools.cycle(requests)

    green_started_s: float | None = None
    current: PhaseId | None = None

    for index in range(step_count):
        now_s = index * step_length_s
        layer.step(now_s)

        if now_s + 1e-9 >= next_decision_s:
            layer.submit(PhaseRequest(intersection=INTERSECTION, phase=next(requested)), now_s)
            next_decision_s += decision_interval_s

        state = layer.signal_state(INTERSECTION)
        green = None if state.in_transition else state.active_phase

        if green is not None:
            _assert_conflict_free(network, green)

        if green != current:
            if current is not None and green_started_s is not None:
                duration_s = now_s - green_started_s
                assert duration_s >= min_green_s - 1e-9, (
                    f"green interval of phase {current} lasted {duration_s} s, "
                    f"shorter than min_green_s = {min_green_s} s"
                )
            current = green
            green_started_s = now_s if green is not None else None

    # D-020's known gap, over every timing the strategy produced.
    assert layer.counters.overrides_deferred_by_transition == 0


def test_the_property_driver_exercises_every_outcome() -> None:
    """Guard against the property test passing because it does nothing.

    A property test over a layer that never switches phase, never refuses a
    request and never completes a green interval would be green and worthless.
    This runs the same driver over four representative configurations and
    asserts that all five outcomes and a good number of completed green
    intervals actually occur.
    """
    seen = {"granted": 0, "deferred": 0, "held": 0, "forced": 0, "rejected": 0, "intervals": 0}
    configurations = [
        # min_green, max_green, yellow, all_red, step, Dt
        (5.0, 40.0, 3.0, 2.0, 1.0, 1.0),
        (2.0, 8.0, 0.0, 0.0, 0.5, 0.5),
        (10.0, 0.0, 5.0, 5.0, 0.25, 5.0),
        (1.0, 3.0, 1.0, 0.0, 0.1, 1.0),
    ]
    for min_green_s, max_green_s, yellow_s, all_red_s, step_length_s, dt_s in configurations:
        layer = build_layer(
            network=network_with_a_conflicting_phase(),
            min_green_s=min_green_s,
            max_green_s=max_green_s,
            yellow_s=yellow_s,
            all_red_s=all_red_s,
            decision_interval_s=dt_s,
            step_length_s=step_length_s,
        )
        requested = itertools.cycle(REQUESTABLE_PHASES)
        next_decision_s = 0.0
        current: PhaseId | None = None
        for index in range(400):
            now_s = index * step_length_s
            layer.step(now_s)
            if now_s + 1e-9 >= next_decision_s:
                layer.submit(PhaseRequest(intersection=INTERSECTION, phase=next(requested)), now_s)
                next_decision_s += dt_s
            state = layer.signal_state(INTERSECTION)
            green = None if state.in_transition else state.active_phase
            if green != current:
                if current is not None:
                    seen["intervals"] += 1
                current = green
        counters = layer.counters
        seen["granted"] += counters.granted
        seen["deferred"] += counters.deferred
        seen["held"] += counters.held
        seen["forced"] += counters.forced
        seen["rejected"] += counters.rejected

    assert all(count > 0 for count in seen.values()), seen
    assert seen["intervals"] > 50, seen
