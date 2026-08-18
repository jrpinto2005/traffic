"""Network structure: the static, load-time vocabulary of `05_DOMAIN_MODEL.md` SS2.

Implements D-003 (domain model is a read-only projection, no traffic dynamics),
D-010 (`Junction` / `SignalizedIntersection` split by specialisation, conflict
matrix on the wider type), D-011 (two lane relations; `Movement` is a computed
view, never stored), D-012 (edges are unidirectional), D-023 (three-valued
conflict matrix; phases authored then validated against it).

All types are frozen and slotted -- static structure is immutable after load
(SS1.2). ID types are `NewType(..., int)`: SUMO's string IDs are resolved to
dense integers once, at load, so nothing in the step loop does a string-keyed
lookup (SS1.2, D-031).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import NewType

import numpy as np
import numpy.typing as npt

# --- IDs (SS1.2) -----------------------------------------------------------
# `LaneConnectionId` and `SignalGroupId` are used throughout SS2 (LaneConnection.id,
# SignalGroup.id) but omitted from SS1.2's enumeration. Added here following the
# same `NewType(..., int)` convention as the other eight -- not a new decision,
# just completing a list that every field reference already assumes exists.
LaneId = NewType("LaneId", int)
EdgeId = NewType("EdgeId", int)
JunctionId = NewType("JunctionId", int)
IntersectionId = NewType("IntersectionId", int)  # a signalized junction
MovementId = NewType("MovementId", int)
PhaseId = NewType("PhaseId", int)
VehicleId = NewType("VehicleId", int)
SensorId = NewType("SensorId", int)
LaneConnectionId = NewType("LaneConnectionId", int)
SignalGroupId = NewType("SignalGroupId", int)


class TurnDirection(StrEnum):
    """The four turn categories a `LaneConnection` may represent (SS2.3)."""

    THROUGH = "through"
    LEFT = "left"
    RIGHT = "right"
    U_TURN = "u_turn"


class VehicleType(StrEnum):
    """The vehicle ontology `05_DOMAIN_MODEL.md` uses but does not itself define
    in SS2-SS5 (it appears in `Lane.allowed_types`, `VehicleState.type`, and
    `Detection.vehicle_class`, all in T1.2 scope).

    `CAR` and `MOTORCYCLE` are the two values `00_RESEARCH_SPECIFICATION.md` SS17
    names, and `04_DECISION_REGISTER.md` D-013's M1 row ("Cars only -- but the
    type-mix parameter exists in the config from day one") and D-025's motorcycle
    discussion both assume exactly this pair as the eventual set. See the T1.2
    completion report for why this was implemented rather than escalated.
    """

    CAR = "car"
    MOTORCYCLE = "motorcycle"


# --- SS2.1 Edge, SS2.2 Lane, SS2.3 LaneConnection ---------------------------


@dataclass(frozen=True, slots=True)
class Edge:
    id: EdgeId
    lanes: tuple[LaneId, ...]  # ordered right-to-left in travel direction
    from_junction: JunctionId
    to_junction: JunctionId
    length_m: float
    opposite: EdgeId | None  # the reverse edge of the same street, if any


@dataclass(frozen=True, slots=True)
class Lane:
    id: LaneId
    edge: EdgeId
    index: int  # 0 = rightmost in travel direction
    length_m: float
    width_m: float  # read only when the sublane model is enabled (D-026)
    speed_limit_mps: float
    successors: tuple[LaneConnectionId, ...]
    adjacent_left: LaneId | None
    adjacent_right: LaneId | None
    allowed_types: frozenset[VehicleType]


@dataclass(frozen=True, slots=True)
class LaneConnection:
    id: LaneConnectionId
    from_lane: LaneId
    to_lane: LaneId
    via_junction: JunctionId | None  # None = continuation within an edge
    turn: TurnDirection


# --- SS2.5 ConflictMatrix ----------------------------------------------------


class Compatibility(IntEnum):
    COMPATIBLE = 0  # may run simultaneously, no interaction
    PERMITTED = 1  # may run simultaneously, one yields to the other
    CONFLICTING = 2  # may never run simultaneously


@dataclass(frozen=True, slots=True)
class ConflictMatrix:
    movements: tuple[MovementId, ...]
    # (n, n) of Compatibility values. `05_DOMAIN_MODEL.md` writes the field's
    # type as bare `np.ndarray`; parametrised here as `NDArray[np.int8]` because
    # mypy --strict (a T1.2 acceptance criterion) rejects an unparametrised
    # generic. Same field, same meaning, concrete dtype.
    matrix: npt.NDArray[np.int8]


def compatibility(matrix: ConflictMatrix, a: MovementId, b: MovementId) -> Compatibility:
    """Look up the three-valued compatibility of movement `a` against `b`.

    `PERMITTED` is asymmetric (D-023: it records which movement yields), so
    `compatibility(m, a, b)` and its mirror `(b, a)` may legitimately differ;
    the caller is responsible for querying the direction it needs.
    """
    index = {m: i for i, m in enumerate(matrix.movements)}
    return Compatibility(int(matrix.matrix[index[a], index[b]]))


# --- SS2.4 Junction and SignalizedIntersection ------------------------------


@dataclass(frozen=True, slots=True)
class Junction:
    id: JunctionId
    incoming_lanes: tuple[LaneId, ...]
    outgoing_lanes: tuple[LaneId, ...]
    connections: tuple[LaneConnectionId, ...]
    conflicts: ConflictMatrix
    position_xy: tuple[float, float]


# --- SS2.7 SignalGroup, Phase, SignalTiming (defined before
# SignalizedIntersection, which references all three) -----------------------


@dataclass(frozen=True, slots=True)
class SignalGroup:
    id: SignalGroupId
    movements: tuple[MovementId, ...]


@dataclass(frozen=True, slots=True)
class Phase:
    id: PhaseId
    green_groups: frozenset[SignalGroupId]


@dataclass(frozen=True, slots=True)
class SignalTiming:
    min_green_s: float
    max_green_s: float  # 0.0 disables the max-green override
    yellow_s: float
    all_red_s: float


@dataclass(frozen=True, slots=True)
class SignalizedIntersection:
    id: IntersectionId
    junction: JunctionId
    signal_groups: tuple[SignalGroup, ...]  # invariant: len >= 2
    phases: tuple[Phase, ...]  # validated against the conflict matrix
    timing: SignalTiming


# --- SS2.6 Movement -- a view, not an entity --------------------------------


@dataclass(frozen=True, slots=True)
class Movement:
    id: MovementId
    junction: JunctionId
    from_edge: EdgeId
    to_edge: EdgeId
    turn: TurnDirection
    connections: tuple[LaneConnectionId, ...]
    signal_group: SignalGroupId | None


# --- Network aggregate -------------------------------------------------------
# Not itself an entity from `05_DOMAIN_MODEL.md` SS2-SS5 -- it is the minimal
# aggregate `validate_network()` and `movements_of()` (added below in later
# commits) need to operate over: just tuples of the entities above, no fields
# of its own. Not binding on T1.3's network generator beyond providing these
# five tuples.


@dataclass(frozen=True, slots=True)
class Network:
    edges: tuple[Edge, ...]
    lanes: tuple[Lane, ...]
    connections: tuple[LaneConnection, ...]
    junctions: tuple[Junction, ...]
    signalized_intersections: tuple[SignalizedIntersection, ...]
