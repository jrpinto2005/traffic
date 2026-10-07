"""Construction and immutability of the SS3 dynamic state types (D-022, D-025)."""

from __future__ import annotations

import dataclasses

import pytest

from traffic_lab.domain.network import IntersectionId, LaneId, PhaseId, VehicleId, VehicleType
from traffic_lab.domain.state import LaneState, RunCounters, SignalState, TrueState, VehicleState


def _vehicle(halting: bool) -> VehicleState:
    return VehicleState(
        id=VehicleId(0),
        type=VehicleType.CAR,
        lane=LaneId(0),
        position_on_lane_m=10.0,
        position_xy=(1.0, 2.0),
        speed_mps=0.0 if halting else 5.0,
        time_loss_s=1.0,
        waiting_time_s=1.0,
        stop_count=1,
        is_halting=halting,
        halting_since_s=0.0 if halting else None,
    )


def test_true_state_is_frozen_and_holds_its_parts() -> None:
    vehicle = _vehicle(halting=True)
    lane_state = LaneState(
        lane=LaneId(0), queue_count=1, queue_length_m=5.0, vehicle_count=1, mean_speed_mps=0.0
    )
    signal_state = SignalState(
        intersection=IntersectionId(0),
        active_phase=PhaseId(0),
        phase_started_s=0.0,
        green_started_s=0.0,
        in_transition=False,
    )
    counters = RunCounters(
        teleports=0,
        insertion_failures=0,
        gridlock_detected=False,
        arrived_at_sink=0,
        arrived_mid_link=0,
        still_in_network=1,
    )
    state = TrueState(
        time_s=100.0,
        vehicles=(vehicle,),
        lanes=(lane_state,),
        signals=(signal_state,),
        counters=counters,
    )
    assert state.vehicles[0].is_halting is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.time_s = 200.0  # type: ignore[misc]


def test_run_counters_trip_accounting_is_three_way() -> None:
    # D-022: a run's total inserted is arrived_at_sink + arrived_mid_link +
    # still_in_network, all three tracked, none collapsed.
    counters = RunCounters(
        teleports=0,
        insertion_failures=0,
        gridlock_detected=False,
        arrived_at_sink=7,
        arrived_mid_link=2,
        still_in_network=3,
    )
    total_inserted = 12
    assert counters.arrived_at_sink + counters.arrived_mid_link + counters.still_in_network == (
        total_inserted
    )


def test_halting_since_s_is_none_for_a_non_halting_vehicle() -> None:
    vehicle = _vehicle(halting=False)
    assert vehicle.is_halting is False
    assert vehicle.halting_since_s is None
