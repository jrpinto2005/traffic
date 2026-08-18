"""Actions: `05_DOMAIN_MODEL.md` SS5.

Implements D-020's canonical action interface: phase selection through a
constraint layer. Every controller acts through these types, including
fixed-time, which simply names the phase its schedule dictates -- that is what
makes a schedule and a learned policy comparable. The constraint layer itself
(`ConstraintLayer`, the state machine, the per-outcome counters) is T1.6's
contract, not this ticket's; only the shared request/outcome/result vocabulary
lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from traffic_lab.domain.network import IntersectionId, PhaseId


@dataclass(frozen=True, slots=True)
class PhaseRequest:
    intersection: IntersectionId
    phase: PhaseId


class RequestOutcome(StrEnum):
    GRANTED = "granted"
    DEFERRED = "deferred"
    HELD = "held"
    FORCED = "forced"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ActionResult:
    outcome: RequestOutcome
    active_phase: PhaseId
    reason: str
    seconds_until_actionable: float
