"""The validity gate (D-008, `07_EXPERIMENT_METHODOLOGY.md` SS5) and trip accounting.

A run is **invalid** -- not merely noisy -- on any teleport, on insertion loss
above 1 %, on detected gridlock, or on a snapshot/network mismatch.

**Insertion loss** (D-008 as refined 2026-10-07, register v1.10): the trips
scheduled at least `INSERTION_WAIT_THRESHOLD_S` before the window closes and
still not inserted when it closes, over the trips scheduled in the window --
both counted exactly from tripinfo's scheduled and actual departures, never
from SUMO's pending list at the closing instant. A vehicle that has waited half
a minute to enter means a queue reached the boundary; one that waited a step
does not, and is charged through `departDelay` in the primary delay anyway. Nothing here
can be switched off: there is no parameter that skips a check and no threshold
that can be passed in (D-008: "a threshold that can be relaxed per experiment
is not a threshold"). An invalid run keeps all its metrics and carries its
causes; it is written, never dropped.

This module owns invariants 13 and 14 of `05_DOMAIN_MODEL.md` SS8:

13. `teleports == 0` for any valid run -- a teleport is an invalidity cause.
14. `arrived_at_sink + arrived_mid_link + still_in_network == total inserted` --
    checked at run end against the trips tripinfo reports as inserted. A
    mismatch is a defect in our accounting, not a property of the run, so it
    **raises** rather than flagging (T1.8 Amendment A3).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from traffic_lab.domain.state import RunCounters
from traffic_lab.metrics.columns import TripColumns
from traffic_lab.metrics.phases import MeasurementWindow

#: D-008, ratified 2026-10-07: above 1 % of the vehicles due in the measurement
#: window still waiting to enter when it closes, the run is invalid. A fraction.
INSERTION_LOSS_THRESHOLD = 0.01

#: D-008 as refined 2026-10-07: a trip counts towards insertion loss only once it
#: has waited at least this long, in seconds, to enter when the window closes.
#: Not configurable, like the threshold above.
INSERTION_WAIT_THRESHOLD_S = 30.0


class InvalidityCause(StrEnum):
    TELEPORT = "teleport"
    INSERTION_LOSS = "insertion_loss"
    GRIDLOCK = "gridlock"
    SNAPSHOT_MISMATCH = "snapshot_mismatch"


class TripAccountingError(RuntimeError):
    """Invariant 14 failed: our counters and SUMO's tripinfo disagree on how
    many vehicles entered the network. A defect to fix, never a run to flag."""


@dataclass(frozen=True, slots=True)
class Validity:
    causes: tuple[InvalidityCause, ...]  # in declaration order; empty means valid
    teleports: int
    gridlock_detected: bool
    snapshot_mismatch: bool
    not_inserted_at_window_close: int  # vehicles; waited >= 30 s, still outside at close
    due_in_window: int  # vehicles; trips scheduled to depart within the window
    insertion_loss: float  # fraction; not_inserted_at_window_close / due_in_window

    @property
    def valid(self) -> bool:
        return not self.causes


def not_inserted_at_window_close(columns: TripColumns, window: MeasurementWindow) -> int:
    """Trips scheduled at least `INSERTION_WAIT_THRESHOLD_S` before `window.end_s`
    and not inserted by then: never inserted, or inserted at or after it.

    A trip inserted in the step that starts at `d` is first in the network in the
    state stamped `d + 1`, so "inserted by the close" means `depart < end_s` --
    the same convention under which tripinfo's schedule explains SUMO's pending
    list exactly (`tests/backend/test_tripinfo.py`).
    """
    end_s = window.end_s
    depart = columns.depart_s
    with np.errstate(invalid="ignore"):  # NaN departures compare False
        outside = np.isnan(depart) | (depart >= end_s)
    waited_long = end_s - columns.scheduled_depart_s >= INSERTION_WAIT_THRESHOLD_S
    return int((outside & waited_long).sum())


def due_in_window(columns: TripColumns, window: MeasurementWindow) -> int:
    """Trips scheduled to depart within `[start_s, end_s)`."""
    scheduled = columns.scheduled_depart_s
    return int(((scheduled >= window.start_s) & (scheduled < window.end_s)).sum())


def insertion_loss(not_inserted: int, due: int) -> float:
    """D-008's insertion loss, a fraction.

    With nothing due in the window the ratio is undefined; it is 0 when nothing
    is waiting either, and infinite -- above any threshold -- when vehicles are
    still waiting to enter a window that asked for none, because applied demand
    then cannot match configured demand.
    """
    if due > 0:
        return not_inserted / due
    return 0.0 if not_inserted == 0 else float("inf")


def assess_validity(
    *,
    run_end: RunCounters,
    trips: TripColumns,
    window: MeasurementWindow,
    snapshot_mismatch: bool,
) -> Validity:
    """Every D-008 check, every time.

    `run_end` are the counters at the last step of the run: teleports and
    gridlock are sticky, so a run that teleported or gridlocked at any point is
    invalid even if it recovered. `trips` are the run's tripinfo records, from
    which insertion loss is counted. `snapshot_mismatch` is a fact the caller
    reports: the backend refuses a mismatched snapshot at load (D-032), so a run
    that reaches this point with `True` is one a caller chose to record.
    """
    not_inserted = not_inserted_at_window_close(trips, window)
    due = due_in_window(trips, window)
    loss = insertion_loss(not_inserted, due)
    causes: list[InvalidityCause] = []
    if run_end.teleports != 0:
        causes.append(InvalidityCause.TELEPORT)
    if loss > INSERTION_LOSS_THRESHOLD:
        causes.append(InvalidityCause.INSERTION_LOSS)
    if run_end.gridlock_detected:
        causes.append(InvalidityCause.GRIDLOCK)
    if snapshot_mismatch:
        causes.append(InvalidityCause.SNAPSHOT_MISMATCH)
    return Validity(
        causes=tuple(causes),
        teleports=run_end.teleports,
        gridlock_detected=run_end.gridlock_detected,
        snapshot_mismatch=snapshot_mismatch,
        not_inserted_at_window_close=not_inserted,
        due_in_window=due,
        insertion_loss=loss,
    )


def check_trip_accounting(run_end: RunCounters, inserted_trips: int) -> None:
    """Invariant 14 at run end: served plus unserved equals inserted, exactly.

    `inserted_trips` is the number of tripinfo records with a departure. Only
    the total is checked here; how it splits between sink and mid-link is
    tripinfo's to say (D-035), and the kinematic split's disagreement is
    reported, not enforced.
    """
    accounted = run_end.arrived_at_sink + run_end.arrived_mid_link + run_end.still_in_network
    if accounted != inserted_trips:
        raise TripAccountingError(
            f"invariant 14 failed: arrived_at_sink ({run_end.arrived_at_sink}) + "
            f"arrived_mid_link ({run_end.arrived_mid_link}) + still_in_network "
            f"({run_end.still_in_network}) = {accounted}, but tripinfo reports "
            f"{inserted_trips} inserted trips"
        )
