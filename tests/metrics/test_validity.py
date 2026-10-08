"""The validity gate (D-008) and invariants 13-14, on constructed counters and trips.

The real-run halves of these -- an overloaded run invalid, a trickle valid, the
synchronised shared fixture valid at a close with four vehicles pending,
invariant 14 exact on SUMO's own output -- are in `test_metric_accumulator.py`.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from traffic_lab.domain.network import LaneId, VehicleType
from traffic_lab.domain.state import RunCounters
from traffic_lab.domain.trip import TripRecord
from traffic_lab.metrics import MeasurementWindow
from traffic_lab.metrics.columns import TripColumns
from traffic_lab.metrics.validity import (
    INSERTION_LOSS_THRESHOLD,
    INSERTION_WAIT_THRESHOLD_S,
    InvalidityCause,
    TripAccountingError,
    assess_validity,
    check_trip_accounting,
    insertion_loss,
)

CLEAN = RunCounters(
    teleports=0,
    insertion_failures=0,
    gridlock_detected=False,
    arrived_at_sink=90,
    arrived_mid_link=5,
    still_in_network=12,
)
WINDOW = MeasurementWindow(start_s=300.0, end_s=900.0)


def _trip(scheduled_s: float, depart_s: float | None) -> TripRecord:
    """A trip that is in the network or undeparted; only the departures matter here."""
    return TripRecord(
        vehicle_type=VehicleType.CAR,
        scheduled_depart_s=scheduled_s,
        depart_s=depart_s,
        insertion_delay_s=0.0 if depart_s is None else depart_s - scheduled_s,
        arrival_s=None,
        travel_time_s=None,
        time_loss_s=0.0,
        waiting_time_s=0.0,
        stops=0,
        depart_lane=None if depart_s is None else LaneId(0),
        arrival_lane=None,
        exit=None,
    )


def _on_time(n: int) -> list[TripRecord]:
    """`n` trips scheduled in the window, each inserted the second it was due."""
    return [_trip(WINDOW.start_s + k, WINDOW.start_s + k) for k in range(n)]


def _assess(
    trips: list[TripRecord], run_end: RunCounters = CLEAN, *, snapshot_mismatch: bool = False
) -> tuple[InvalidityCause, ...]:
    return assess_validity(
        run_end=run_end,
        trips=TripColumns.from_trips(trips),
        window=WINDOW,
        snapshot_mismatch=snapshot_mismatch,
    ).causes


def test_a_clean_run_is_valid() -> None:
    validity = assess_validity(
        run_end=CLEAN,
        trips=TripColumns.from_trips(_on_time(200)),
        window=WINDOW,
        snapshot_mismatch=False,
    )
    assert validity.valid and validity.causes == ()
    assert (validity.due_in_window, validity.not_inserted_at_window_close) == (200, 0)


def test_one_teleport_invalidates_invariant_13() -> None:
    teleported = dataclasses.replace(CLEAN, teleports=1)
    assert _assess(_on_time(200), teleported) == (InvalidityCause.TELEPORT,)


def test_a_vehicle_waiting_exactly_30_s_at_the_close_counts_and_29_s_does_not() -> None:
    """D-008 as refined: scheduled at least 30 s before the close, not inserted by it."""
    assert INSERTION_WAIT_THRESHOLD_S == 30.0
    end = WINDOW.end_s
    cases = {
        "undeparted, waited 30 s": (_trip(end - 30.0, None), 1),
        "undeparted, waited 29 s": (_trip(end - 29.0, None), 0),
        "inserted at the close, waited 30 s": (_trip(end - 30.0, end), 1),
        "inserted after the close, waited 30 s": (_trip(end - 30.0, end + 12.0), 1),
        "inserted after the close, waited 29 s": (_trip(end - 29.0, end + 12.0), 0),
        "inserted a step before the close": (_trip(end - 30.0, end - 1.0), 0),
    }
    for label, (trip, expected) in cases.items():
        validity = assess_validity(
            run_end=CLEAN,
            trips=TripColumns.from_trips([trip]),
            window=WINDOW,
            snapshot_mismatch=False,
        )
        assert validity.not_inserted_at_window_close == expected, label


def test_insertion_loss_threshold_is_one_percent_exclusive() -> None:
    assert INSERTION_LOSS_THRESHOLD == 0.01
    waiting = [_trip(WINDOW.end_s - 60.0, None) for _ in range(3)]
    # 2 of 200 = exactly 1 %: valid. 3 of 200: invalid.
    assert _assess(_on_time(198) + waiting[:2]) == ()
    assert _assess(_on_time(197) + waiting) == (InvalidityCause.INSERTION_LOSS,)


def test_a_backlog_from_before_the_window_counts_in_the_numerator_only() -> None:
    """The numerator is every long wait at the close, whenever it was due; the
    denominator is what the window asked for."""
    backlog = [_trip(WINDOW.start_s - 100.0, None) for _ in range(5)]
    validity = assess_validity(
        run_end=CLEAN,
        trips=TripColumns.from_trips(_on_time(100) + backlog),
        window=WINDOW,
        snapshot_mismatch=False,
    )
    assert (validity.not_inserted_at_window_close, validity.due_in_window) == (5, 100)
    assert validity.causes == (InvalidityCause.INSERTION_LOSS,)


def test_insertion_loss_with_nothing_due() -> None:
    assert insertion_loss(0, 0) == 0.0
    assert insertion_loss(1, 0) == float("inf")
    assert _assess([_trip(WINDOW.start_s - 100.0, None)]) == (InvalidityCause.INSERTION_LOSS,)


def test_gridlock_and_snapshot_mismatch() -> None:
    gridlocked = dataclasses.replace(CLEAN, gridlock_detected=True)
    assert _assess(_on_time(200), gridlocked) == (InvalidityCause.GRIDLOCK,)
    assert _assess(_on_time(200), snapshot_mismatch=True) == (InvalidityCause.SNAPSHOT_MISMATCH,)


def test_every_cause_is_reported_not_just_the_first() -> None:
    causes = _assess(
        _on_time(100) + [_trip(WINDOW.end_s - 60.0, None) for _ in range(50)],
        dataclasses.replace(CLEAN, teleports=3, gridlock_detected=True),
        snapshot_mismatch=True,
    )
    assert causes == tuple(InvalidityCause)


def test_no_check_can_be_switched_off() -> None:
    """D-008, non-goal 3: no threshold or skip flag is a parameter."""
    parameters = inspect.signature(assess_validity).parameters
    assert set(parameters) == {"run_end", "trips", "window", "snapshot_mismatch"}
    for parameter in parameters.values():
        assert parameter.default is inspect.Parameter.empty, parameter.name


def test_invariant_14_holds_or_raises() -> None:
    check_trip_accounting(CLEAN, inserted_trips=107)
    with pytest.raises(TripAccountingError, match="invariant 14"):
        check_trip_accounting(CLEAN, inserted_trips=108)
