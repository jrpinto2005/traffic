"""Max-Pressure (T1.10 A5): the hand-computed maximum-pressure phase on known queues.

The fixture is the generated four-way with the protected plan. Its lanes, from
the built net (two lanes per approach, netconvert's default assignment):
lane 0 of each approach carries through and right, lane 1 through and left.
So, with `k_in_j` / `k_out_j` for lane j of approach k's in / out edge:

| Phase | U (incoming)                    | D (outgoing)                                    |
| ----- | ------------------------------- | ----------------------------------------------- |
| 0     | 0_in_0, 0_in_1, 2_in_0, 2_in_1  | 2_out_0, 3_out_0, 2_out_1, 0_out_0, 1_out_0, 0_out_1 |
| 1     | 0_in_1, 2_in_1                  | 1_out_1, 3_out_1                                |
| 2     | 1_in_0, 1_in_1, 3_in_0, 3_in_1  | 0_out_0, 3_out_0, 3_out_1, 1_out_0, 2_out_0, 1_out_1 |
| 3     | 1_in_1, 3_in_1                  | 2_out_1, 0_out_1                                |

The table is asserted against the network first, so the hand computations below
rest on a checked premise.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from tests.backend.conftest import Scenario
from tests.generated_scenario import Built
from traffic_lab.control.max_pressure import MaxPressureController
from traffic_lab.control.phases import phase_service
from traffic_lab.domain.network import IntersectionId, PhaseId
from traffic_lab.domain.observation import EstimatedState, LaneEstimate
from traffic_lab.domain.state import SignalState

U_D = {
    0: (
        {"0_in_0", "0_in_1", "2_in_0", "2_in_1"},
        {"2_out_0", "3_out_0", "2_out_1", "0_out_0", "1_out_0", "0_out_1"},
    ),
    1: ({"0_in_1", "2_in_1"}, {"1_out_1", "3_out_1"}),
    2: (
        {"1_in_0", "1_in_1", "3_in_0", "3_in_1"},
        {"0_out_0", "3_out_0", "3_out_1", "1_out_0", "2_out_0", "1_out_1"},
    ),
    3: ({"1_in_1", "3_in_1"}, {"2_out_1", "0_out_1"}),
}

#: Queued vehicles per lane, chosen so that two phases tie for the maximum.
QUEUES = {
    "0_in_0": 4, "0_in_1": 6, "2_in_0": 1, "2_in_1": 2,
    "1_in_0": 3, "1_in_1": 5, "3_in_0": 2, "3_in_1": 7,
    "0_out_0": 1, "0_out_1": 0, "1_out_0": 2, "1_out_1": 3,
    "2_out_0": 0, "2_out_1": 4, "3_out_0": 1, "3_out_1": 2,
}  # fmt: skip

#: By hand from the table: 13 - 8, 8 - 5, 17 - 9, 12 - 4.
PRESSURES = {0: 5.0, 1: 3.0, 2: 8.0, 3: 8.0}


def _sumo_lane(short: str) -> str:
    approach, direction, lane = short.split("_")
    return f"approach_{approach}_{direction}_{lane}"


def _estimate(built: Built, queues: Mapping[str, int], active: int) -> EstimatedState:
    by_sumo = {_sumo_lane(k): v for k, v in queues.items()}
    return EstimatedState(
        time_s=100.0,
        lanes=tuple(
            LaneEstimate(
                lane=lane.id,
                queue_count=float(by_sumo.get(built.ids.lanes[lane.id], 0)),
                queue_count_std=0.0,
                last_observed_s=100.0,
                vehicle_count=float(by_sumo.get(built.ids.lanes[lane.id], 0)),
                zone_count=0.0,
            )
            for lane in built.network.lanes
        ),
        signals=(
            SignalState(
                intersection=built.intersection_id,
                active_phase=PhaseId(active),
                phase_started_s=50.0,
                green_started_s=55.0,
                in_transition=False,
            ),
        ),
    )


def test_the_hand_computed_lane_table_is_the_networks(scenario: Scenario) -> None:
    built = scenario.built
    for service in phase_service(built.network, built.intersection):
        incoming, outgoing = U_D[int(service.phase)]
        assert {built.ids.lanes[lane] for lane in service.incoming_lanes} == {
            _sumo_lane(s) for s in incoming
        }
        assert {built.ids.lanes[lane] for lane in service.outgoing_lanes} == {
            _sumo_lane(s) for s in outgoing
        }


def test_pressures_match_the_hand_computation(scenario: Scenario) -> None:
    controller = MaxPressureController(scenario.network)
    pressures = controller.pressures(_estimate(scenario.built, QUEUES, active=0))
    assert {int(p): v for p, v in pressures.items()} == PRESSURES


def test_a_shared_lane_counts_once(scenario: Scenario) -> None:
    """0_in_0 carries both of phase 0's approach-0 movements; its 4 vehicles add 4, not 8."""
    controller = MaxPressureController(scenario.network)
    more = dict(QUEUES, **{"0_in_0": QUEUES["0_in_0"] + 1})
    before = controller.pressures(_estimate(scenario.built, QUEUES, active=0))
    after = controller.pressures(_estimate(scenario.built, more, active=0))
    assert after[PhaseId(0)] - before[PhaseId(0)] == 1.0


@pytest.mark.parametrize(
    ("active", "expected"),
    [
        (0, 2),  # 2 and 3 tie at 8; the current phase is not among them: lowest ID
        (1, 2),
        (2, 2),  # the current phase is among the maxima: kept
        (3, 3),  # likewise -- not the lowest ID
    ],
)
def test_selects_the_maximum_and_breaks_ties_as_specified(
    scenario: Scenario, active: int, expected: int
) -> None:
    controller = MaxPressureController(scenario.network)
    request = controller.decide(_estimate(scenario.built, QUEUES, active), 100.0)
    assert request.intersection == scenario.built.intersection_id
    assert request.phase == PhaseId(expected)


def test_downstream_queues_change_the_choice(scenario: Scenario) -> None:
    """Upstream queues alone favour phase 2 (17 against 13, 8, 12). A downstream queue of
    10 on 1_out_0 -- in phase 2's D and phase 0's -- leaves phase 3 the maximum:
    pressures -3, 3, 0, 8."""
    controller = MaxPressureController(scenario.network)
    blocked = dict(QUEUES, **{"1_out_0": 10})
    est = _estimate(scenario.built, blocked, active=2)
    assert {int(p): v for p, v in controller.pressures(est).items()} == {
        0: -3.0,
        1: 3.0,
        2: 0.0,
        3: 8.0,
    }
    assert controller.decide(est, 100.0).phase == PhaseId(3)


def test_a_unique_maximum_is_chosen_over_the_current_phase(scenario: Scenario) -> None:
    controller = MaxPressureController(scenario.network)
    est = _estimate(scenario.built, dict(QUEUES, **{"1_in_0": 4}), active=3)
    assert controller.decide(est, 100.0).phase == PhaseId(2)  # 9 against 8


def test_a_lane_missing_from_the_estimate_raises(scenario: Scenario) -> None:
    controller = MaxPressureController(scenario.network)
    full = _estimate(scenario.built, QUEUES, active=0)
    used_lane = next(iter(controller._lanes[0][1]))
    partial = EstimatedState(
        full.time_s,
        tuple(lane for lane in full.lanes if lane.lane != used_lane),
        full.signals,
    )
    with pytest.raises(ValueError, match="no estimate for lane"):
        controller.decide(partial, 100.0)


def test_default_decision_interval_is_d020s() -> None:
    from tests.domain.factories import build_valid_network

    assert MaxPressureController(build_valid_network()).decision_interval_s == 5.0


def test_a_network_with_two_signals_is_refused(scenario: Scenario) -> None:
    import dataclasses

    network = scenario.network
    doubled = dataclasses.replace(
        network,
        signalized_intersections=(
            *network.signalized_intersections,
            dataclasses.replace(network.signalized_intersections[0], id=IntersectionId(1)),
        ),
    )
    with pytest.raises(ValueError, match="one signalized intersection"):
        MaxPressureController(doubled)
