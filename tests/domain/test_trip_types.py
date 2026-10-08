"""`TripRecord` (D-035): frozen, slotted, and its three states read off its fields."""

from __future__ import annotations

import dataclasses

import pytest

from traffic_lab.domain.network import LaneId, VehicleType
from traffic_lab.domain.trip import TripExit, TripRecord


def _trip(**overrides: object) -> TripRecord:
    fields: dict[str, object] = {
        "vehicle_type": VehicleType.CAR,
        "scheduled_depart_s": 10.0,
        "depart_s": 11.0,
        "insertion_delay_s": 1.0,
        "arrival_s": 40.0,
        "travel_time_s": 29.0,
        "time_loss_s": 3.5,
        "waiting_time_s": 2.0,
        "stops": 1,
        "depart_lane": LaneId(16),
        "arrival_lane": LaneId(26),
        "exit": TripExit.SINK,
    }
    fields.update(overrides)
    return TripRecord(**fields)  # type: ignore[arg-type]


def test_trip_record_is_frozen_and_slotted() -> None:
    trip = _trip()
    with pytest.raises(dataclasses.FrozenInstanceError):
        trip.stops = 2  # type: ignore[misc]
    assert not hasattr(trip, "__dict__")


def test_the_three_states() -> None:
    finished = _trip()
    unfinished = _trip(arrival_s=None, travel_time_s=None, arrival_lane=None, exit=None)
    undeparted = _trip(
        depart_s=None,
        depart_lane=None,
        arrival_s=None,
        travel_time_s=None,
        arrival_lane=None,
        exit=None,
    )
    assert (finished.inserted, finished.finished) == (True, True)
    assert (unfinished.inserted, unfinished.finished) == (True, False)
    assert (undeparted.inserted, undeparted.finished) == (False, False)


def test_exit_values() -> None:
    assert {e.value for e in TripExit} == {"sink", "mid_link"}
