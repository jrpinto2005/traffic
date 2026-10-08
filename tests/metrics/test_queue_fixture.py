"""The queue metrics on a hand-computed fixture with known halting durations (D-025).

The queue itself is the backend's -- `LaneState.queue_count`, computed by the
projector and owned by T1.4 (invariant 12) -- and the accumulator only averages
and maximises it over the window, so the fixture goes through the real
`Projector`: hand-written `RawStep`s, as `tests/backend/test_state_invariants.py`
does, because a live simulation cannot be made to halt a vehicle for exactly
half a second. The step is 0.5 s so that half-second halt exists at all.
"""

from __future__ import annotations

import pytest

from tests.backend.conftest import Scenario
from traffic_lab.backend.projection import Projector
from traffic_lab.backend.transport import RawStep, RawVehicle
from traffic_lab.domain.network import LaneId, VehicleType
from traffic_lab.domain.state import TrueState
from traffic_lab.domain.trip import TripRecord
from traffic_lab.metrics import MeasurementWindow, MetricAccumulator

STEP_S = 0.5
WINDOW = MeasurementWindow(start_s=1.0, end_s=5.0)
TIMES = [STEP_S * k for k in range(1, 11)]  # 0.5 .. 5.0

#: Per vehicle, the sample times at which it is halted (speed 0); moving
#: (5 m/s) at every other sample. Queue = halting continuously for >= 1 s.
HALTED = {
    "a_half_second": {1.0, 1.5},  # halts 0.5 s: never queued
    "b_one_and_a_half": {1.0, 1.5, 2.0, 2.5},  # queued at 2.0, 2.5
    "c_from_two": {2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0},  # queued from 3.0
    "d_two_seconds": {1.0, 1.5, 2.0, 2.5, 3.0},  # queued at 2.0 .. 3.0
}
#: A vehicle on the other lane that halts for half a second, twice.
OTHER_LANE_HALTED = {"e_twice_briefly": {1.5, 2.0, 3.5, 4.0}}

#: Hand-computed queue on the first lane at each window sample 1.0 .. 4.5:
#:   1.0: 0 (all just halted)      1.5: 0 (a, b, d at 0.5 s)
#:   2.0: 2 (b, d at 1.0 s)        2.5: 2 (b, d; c at 0.5 s)
#:   3.0: 2 (c at 1.0 s, d)        3.5: 1 (c)    4.0: 1    4.5: 1
EXPECTED_QUEUE = [0, 0, 2, 2, 2, 1, 1, 1]


def _states(scenario: Scenario) -> list[TrueState]:
    lane_ids = scenario.built.ids.lanes
    lane, other = lane_ids[-4], lane_ids[-3]  # two approach lanes, both 189.6 m
    projector = Projector(
        lane_sumo_ids=lane_ids,
        lane_lengths_m=tuple(lane.length_m for lane in scenario.network.lanes),
        intersection_sumo_ids=(),
        phase_green_links=(),
        start_s=0.0,
        vehicle_types={"passenger": VehicleType.CAR},
        step_length_s=STEP_S,
        gridlock_steps=1000,
        max_accel_mps2=2.6,
    )
    plan = {vid: (lane, halted) for vid, halted in HALTED.items()} | {
        vid: (other, halted) for vid, halted in OTHER_LANE_HALTED.items()
    }
    states = []
    for t in TIMES:
        vehicles = {
            vid: RawVehicle(
                type_id="passenger",
                lane_id=lane_id,
                lane_position_m=50.0,
                position_x_m=0.0,
                position_y_m=0.0,
                speed_mps=0.0 if t in halted else 5.0,
                time_loss_s=0.0,
                waiting_time_s=0.0,
            )
            for vid, (lane_id, halted) in plan.items()
        }
        states.append(
            projector.project(
                RawStep(
                    time_s=t,
                    vehicles=vehicles,
                    signals={},
                    arrived_ids=(),
                    teleports_ending=0,
                    pending=0,
                    arrived=0,
                )
            )
        )
    return states


def _unfinished(n: int) -> list[TripRecord]:
    return [
        TripRecord(
            vehicle_type=VehicleType.CAR,
            scheduled_depart_s=0.0,
            depart_s=0.0,
            insertion_delay_s=0.0,
            arrival_s=None,
            travel_time_s=None,
            time_loss_s=0.0,
            waiting_time_s=0.0,
            stops=0,
            depart_lane=LaneId(0),
            arrival_lane=None,
            exit=None,
        )
        for _ in range(n)
    ]


def test_queue_mean_and_max_match_the_hand_computation(scenario: Scenario) -> None:
    states = _states(scenario)
    lane = LaneId(len(scenario.built.ids.lanes) - 4)
    other = LaneId(len(scenario.built.ids.lanes) - 3)

    in_window = [s for s in states if WINDOW.contains(s.time_s)]
    assert [s.lanes[lane].queue_count for s in in_window] == EXPECTED_QUEUE

    accumulator = MetricAccumulator(WINDOW, scenario.network)
    for state in states:
        accumulator.accumulate(state)
    result = accumulator.finalize(_unfinished(5), snapshot_mismatch=False)

    assert result.queue_mean_veh[lane] == pytest.approx(sum(EXPECTED_QUEUE) / 8)  # 1.375
    assert result.max_queue_veh[lane] == 2
    # Two half-second halts are never a queue.
    assert (result.queue_mean_veh[other], result.max_queue_veh[other]) == (0.0, 0)
    assert sum(result.max_queue_veh) == 2
    # The state at 5.0 closes the window; it is not a sample.
    assert result.aggregate.still_in_network == 5


def test_a_window_end_between_steps_is_refused(scenario: Scenario) -> None:
    accumulator = MetricAccumulator(MeasurementWindow(start_s=1.0, end_s=4.75), scenario.network)
    with pytest.raises(ValueError, match="must end on a step"):
        for state in _states(scenario):
            accumulator.accumulate(state)


def test_finalize_before_the_window_closes_is_refused(scenario: Scenario) -> None:
    accumulator = MetricAccumulator(MeasurementWindow(start_s=1.0, end_s=60.0), scenario.network)
    for state in _states(scenario):
        accumulator.accumulate(state)
    with pytest.raises(RuntimeError, match="never closed"):
        accumulator.finalize(_unfinished(5), snapshot_mismatch=False)


def test_states_out_of_order_are_refused(scenario: Scenario) -> None:
    states = _states(scenario)
    accumulator = MetricAccumulator(WINDOW, scenario.network)
    accumulator.accumulate(states[1])
    with pytest.raises(ValueError, match="time order"):
        accumulator.accumulate(states[0])
