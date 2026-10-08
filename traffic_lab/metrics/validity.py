"""The validity gate (D-008, `07_EXPERIMENT_METHODOLOGY.md` SS5) and trip accounting.

A run is **invalid** -- not merely noisy -- on any teleport, on insertion loss
above 1 %, on detected gridlock, or on a snapshot/network mismatch. Nothing here
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

from traffic_lab.domain.state import RunCounters

#: D-008, ratified 2026-10-07: above 1 % of the vehicles due in the measurement
#: window still waiting to enter when it closes, the run is invalid. A fraction.
INSERTION_LOSS_THRESHOLD = 0.01


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
    pending_at_window_close: int  # vehicles; SUMO's pending list when the window closed
    due_in_window: int  # vehicles; trips scheduled to depart within the window
    insertion_loss: float  # fraction; pending_at_window_close / due_in_window

    @property
    def valid(self) -> bool:
        return not self.causes


def insertion_loss(pending_at_window_close: int, due_in_window: int) -> float:
    """D-008's insertion loss, a fraction.

    With nothing due in the window the ratio is undefined; it is 0 when nothing
    is pending either, and infinite -- above any threshold -- when vehicles are
    still waiting to enter a window that asked for none, because applied demand
    then cannot match configured demand.
    """
    if due_in_window > 0:
        return pending_at_window_close / due_in_window
    return 0.0 if pending_at_window_close == 0 else float("inf")


def assess_validity(
    *,
    run_end: RunCounters,
    pending_at_window_close: int,
    due_in_window: int,
    snapshot_mismatch: bool,
) -> Validity:
    """Every D-008 check, every time.

    `run_end` are the counters at the last step of the run: teleports and
    gridlock are sticky, so a run that teleported or gridlocked at any point is
    invalid even if it recovered. `snapshot_mismatch` is a fact the caller
    reports: the backend refuses a mismatched snapshot at load (D-032), so a run
    that reaches this point with `True` is one a caller chose to record.
    """
    loss = insertion_loss(pending_at_window_close, due_in_window)
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
        pending_at_window_close=pending_at_window_close,
        due_in_window=due_in_window,
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
