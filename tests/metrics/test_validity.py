"""The validity gate (D-008) and invariants 13-14, on constructed counters.

The real-run halves of these -- an overloaded run invalid, a trickle valid,
invariant 14 exact on SUMO's own output -- are in `test_metric_accumulator.py`.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from traffic_lab.domain.state import RunCounters
from traffic_lab.metrics.validity import (
    INSERTION_LOSS_THRESHOLD,
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


def _assess(**overrides: object) -> tuple[InvalidityCause, ...]:
    fields: dict[str, object] = {
        "run_end": CLEAN,
        "pending_at_window_close": 0,
        "due_in_window": 200,
        "snapshot_mismatch": False,
    }
    fields.update(overrides)
    return assess_validity(**fields).causes  # type: ignore[arg-type]


def test_a_clean_run_is_valid() -> None:
    validity = assess_validity(
        run_end=CLEAN, pending_at_window_close=0, due_in_window=200, snapshot_mismatch=False
    )
    assert validity.valid and validity.causes == ()


def test_one_teleport_invalidates_invariant_13() -> None:
    assert _assess(run_end=dataclasses.replace(CLEAN, teleports=1)) == (InvalidityCause.TELEPORT,)


def test_insertion_loss_threshold_is_one_percent_exclusive() -> None:
    assert INSERTION_LOSS_THRESHOLD == 0.01
    assert _assess(pending_at_window_close=2, due_in_window=200) == ()  # exactly 1 %
    assert _assess(pending_at_window_close=3, due_in_window=200) == (
        InvalidityCause.INSERTION_LOSS,
    )


def test_insertion_loss_with_nothing_due() -> None:
    assert insertion_loss(0, 0) == 0.0
    assert insertion_loss(1, 0) == float("inf")
    assert _assess(pending_at_window_close=1, due_in_window=0) == (InvalidityCause.INSERTION_LOSS,)


def test_gridlock_and_snapshot_mismatch() -> None:
    assert _assess(run_end=dataclasses.replace(CLEAN, gridlock_detected=True)) == (
        InvalidityCause.GRIDLOCK,
    )
    assert _assess(snapshot_mismatch=True) == (InvalidityCause.SNAPSHOT_MISMATCH,)


def test_every_cause_is_reported_not_just_the_first() -> None:
    causes = _assess(
        run_end=dataclasses.replace(CLEAN, teleports=3, gridlock_detected=True),
        pending_at_window_close=50,
        snapshot_mismatch=True,
    )
    assert causes == tuple(InvalidityCause)


def test_no_check_can_be_switched_off() -> None:
    """D-008, non-goal 3: no threshold or skip flag is a parameter."""
    parameters = set(inspect.signature(assess_validity).parameters)
    assert parameters == {
        "run_end",
        "pending_at_window_close",
        "due_in_window",
        "snapshot_mismatch",
    }
    for parameter in inspect.signature(assess_validity).parameters.values():
        assert parameter.default is inspect.Parameter.empty, parameter.name


def test_invariant_14_holds_or_raises() -> None:
    check_trip_accounting(CLEAN, inserted_trips=107)
    with pytest.raises(TripAccountingError, match="invariant 14"):
        check_trip_accounting(CLEAN, inserted_trips=108)
