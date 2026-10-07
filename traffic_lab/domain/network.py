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

import itertools
from collections.abc import Iterable
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


def conflicting_pair(
    conflicts: ConflictMatrix, movements: Iterable[MovementId]
) -> tuple[MovementId, MovementId] | None:
    """The first `CONFLICTING` pair among `movements`, or `None` if there is none.

    The one definition of "these movements may not be green together", shared by
    `validate_network()` (invariant 7, at load) and the constraint layer (at
    request time) so the two cannot disagree. Returns the pair rather than a bool
    because D-023 requires the error to name it.

    A pair conflicts if **either** direction of the matrix says `CONFLICTING`.
    Only `PERMITTED` is meant to be asymmetric (SS2.5), but nothing enforces
    that, and a matrix seeded from SUMO's `foes`/`response` need not be
    symmetric. `PERMITTED` is not a conflict: such a movement may run
    simultaneously and yields (D-023).
    """
    index = {m: i for i, m in enumerate(conflicts.movements)}
    matrix = conflicts.matrix
    for a, b in itertools.combinations(sorted(movements), 2):
        i, j = index[a], index[b]
        if Compatibility.CONFLICTING in (int(matrix[i, j]), int(matrix[j, i])):
            return (a, b)
    return None


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


def movements_of(
    network: Network,
    junction_id: JunctionId,
    *,
    start_id: MovementId = MovementId(0),
) -> tuple[Movement, ...]:
    """Compute the `Movement` view of one junction from its lane connections.

    Per D-011, a movement is the subset of lane connections crossing a junction,
    grouped by (approach edge, turn direction) -- never stored. `signal_group` is
    always `None` here: this function only sees topology (`network.lanes` and
    `network.connections`), not any scenario's authored `SignalGroup`s. A caller
    that also has those (T1.3's network generator, or `validate_network()`'s
    invariant-8 check) annotates them separately.

    `start_id` numbers the returned movements sequentially from this value. It
    is local to one junction; giving every junction in a network globally unique
    `MovementId`s (by offsetting `start_id` per junction) is the caller's job --
    T1.2 has no concept of a whole-network movement id space.
    """
    junctions_by_id = {j.id: j for j in network.junctions}
    junction = junctions_by_id[junction_id]
    lanes_by_id = {lane.id: lane for lane in network.lanes}
    connections_by_id = {conn.id: conn for conn in network.connections}

    order: list[tuple[EdgeId, TurnDirection]] = []
    grouped: dict[tuple[EdgeId, TurnDirection], list[LaneConnectionId]] = {}
    to_edge_of: dict[tuple[EdgeId, TurnDirection], EdgeId] = {}

    for conn_id in junction.connections:
        conn = connections_by_id[conn_id]
        from_lane = lanes_by_id[conn.from_lane]
        to_lane = lanes_by_id[conn.to_lane]
        key = (from_lane.edge, conn.turn)
        if key not in grouped:
            grouped[key] = []
            to_edge_of[key] = to_lane.edge
            order.append(key)
        grouped[key].append(conn_id)

    return tuple(
        Movement(
            id=MovementId(int(start_id) + offset),
            junction=junction_id,
            from_edge=key[0],
            to_edge=to_edge_of[key],
            turn=key[1],
            connections=tuple(grouped[key]),
            signal_group=None,
        )
        for offset, key in enumerate(order)
    )


# --- SS8 invariants ----------------------------------------------------------


class NetworkValidationError(ValueError):
    """Raised by `validate_network()` on a `05_DOMAIN_MODEL.md` SS8 violation.

    Carries the invariant number so tests and callers can assert on it
    precisely, and a message naming the offending entities -- per T1.2's
    contract, "a typed error naming the violated invariant and the offending
    entities".
    """

    def __init__(self, invariant: int, message: str) -> None:
        self.invariant = invariant
        super().__init__(f"invariant {invariant} violated: {message}")


def validate_network(network: Network) -> None:
    """Check `network` against invariants 1-9 of `05_DOMAIN_MODEL.md` SS8.

    Raises `NetworkValidationError` on the first violation found. Invariants
    10-14 (state) are not checked here: SS8 itself scopes them to property-based
    tests over dynamic state, not load-time network validation, and T1.2's own
    ticket Scope excludes them from `validate_network()`. Invariants 15-16
    (demand: turn-ratio and attrition bounds) are **not implemented** -- see the
    T1.2 completion report; they require `TurnRatioSpec` / `AttritionSpec`
    (SS6.1), which this ticket's "Sections in scope" list excludes, so
    implementing them here would silently take on scope the ticket did not
    grant.
    """
    edges_by_id = {e.id: e for e in network.edges}
    lanes_by_id = {lane.id: lane for lane in network.lanes}
    junctions_by_id = {j.id: j for j in network.junctions}

    _check_invariant_1(network, lanes_by_id)
    _check_invariant_2(network, edges_by_id)
    _check_invariant_3(network, lanes_by_id)
    _check_invariant_4(network, junctions_by_id)
    _check_invariant_5(network, edges_by_id)
    _check_invariant_6(network)
    _check_invariant_7(network, junctions_by_id)
    _check_invariant_8(network, junctions_by_id)
    _check_invariant_9(network)


def _check_invariant_1(network: Network, lanes_by_id: dict[LaneId, Lane]) -> None:
    """Every lane belongs to exactly one edge.

    Checked both ways: every lane an edge claims must exist and must claim that
    same edge back (no lane double-booked across two edges' `lanes` tuples).
    """
    seen: dict[LaneId, EdgeId] = {}
    for edge in network.edges:
        for lane_id in edge.lanes:
            lane = lanes_by_id.get(lane_id)
            if lane is None:
                raise NetworkValidationError(
                    1, f"edge {edge.id} lists lane {lane_id}, which does not exist"
                )
            if lane.edge != edge.id:
                raise NetworkValidationError(
                    1,
                    f"lane {lane_id} is listed under edge {edge.id} but its own "
                    f"`edge` field is {lane.edge}",
                )
            if lane_id in seen and seen[lane_id] != edge.id:
                raise NetworkValidationError(
                    1,
                    f"lane {lane_id} is listed under both edge {seen[lane_id]} and edge {edge.id}",
                )
            seen[lane_id] = edge.id


def _check_invariant_2(network: Network, edges_by_id: dict[EdgeId, Edge]) -> None:
    """Every lane has exactly one travel direction, inherited from its edge.

    Neither `Lane` nor `Edge` stores a direction field -- direction is implicit
    in `Edge` being unidirectional (D-012). The only way this can fail is a lane
    whose `edge` reference is dangling, so there is no edge to inherit a
    direction from.
    """
    for lane in network.lanes:
        if lane.edge not in edges_by_id:
            raise NetworkValidationError(
                2, f"lane {lane.id} references edge {lane.edge}, which does not exist"
            )


def _check_invariant_3(network: Network, lanes_by_id: dict[LaneId, Lane]) -> None:
    """`adjacent_left` / `adjacent_right` connect lanes of the same edge only."""
    for lane in network.lanes:
        for attr, neighbour_id in (
            ("adjacent_left", lane.adjacent_left),
            ("adjacent_right", lane.adjacent_right),
        ):
            if neighbour_id is None:
                continue
            neighbour = lanes_by_id.get(neighbour_id)
            if neighbour is None:
                raise NetworkValidationError(
                    3,
                    f"lane {lane.id}.{attr} references lane {neighbour_id}, which does not exist",
                )
            if neighbour.edge != lane.edge:
                raise NetworkValidationError(
                    3,
                    f"lane {lane.id} (edge {lane.edge}).{attr} is lane "
                    f"{neighbour_id} on a different edge ({neighbour.edge})",
                )


def _check_invariant_4(network: Network, junctions_by_id: dict[JunctionId, Junction]) -> None:
    """Every `LaneConnection` with `via_junction` set has both endpoints in that
    junction's incoming and outgoing lane sets."""
    for conn in network.connections:
        if conn.via_junction is None:
            continue
        junction = junctions_by_id.get(conn.via_junction)
        if junction is None:
            raise NetworkValidationError(
                4,
                f"connection {conn.id} references junction {conn.via_junction}, "
                "which does not exist",
            )
        if conn.from_lane not in junction.incoming_lanes:
            raise NetworkValidationError(
                4,
                f"connection {conn.id}'s from_lane {conn.from_lane} is not in "
                f"junction {junction.id}'s incoming_lanes",
            )
        if conn.to_lane not in junction.outgoing_lanes:
            raise NetworkValidationError(
                4,
                f"connection {conn.id}'s to_lane {conn.to_lane} is not in "
                f"junction {junction.id}'s outgoing_lanes",
            )


def _check_invariant_5(network: Network, edges_by_id: dict[EdgeId, Edge]) -> None:
    """`Edge.opposite`, where set, is symmetric."""
    for edge in network.edges:
        if edge.opposite is None:
            continue
        opposite = edges_by_id.get(edge.opposite)
        if opposite is None:
            raise NetworkValidationError(
                5,
                f"edge {edge.id}.opposite references edge {edge.opposite}, which does not exist",
            )
        if opposite.opposite != edge.id:
            raise NetworkValidationError(
                5,
                f"edge {edge.id}.opposite is {edge.opposite}, but edge "
                f"{edge.opposite}.opposite is {opposite.opposite}, not {edge.id}",
            )


def _check_invariant_6(network: Network) -> None:
    """Every `SignalizedIntersection` has >= 2 signal groups."""
    for si in network.signalized_intersections:
        if len(si.signal_groups) < 2:
            raise NetworkValidationError(
                6,
                f"intersection {si.id} has {len(si.signal_groups)} signal "
                "group(s), fewer than the required 2",
            )


def _check_invariant_7(network: Network, junctions_by_id: dict[JunctionId, Junction]) -> None:
    """Every declared phase contains no `CONFLICTING` movement pair."""
    for si in network.signalized_intersections:
        junction = junctions_by_id[si.junction]
        groups_by_id = {g.id: g for g in si.signal_groups}
        for phase in si.phases:
            movements_in_phase: set[MovementId] = set()
            for group_id in phase.green_groups:
                movements_in_phase.update(groups_by_id[group_id].movements)
            pair = conflicting_pair(junction.conflicts, movements_in_phase)
            if pair is not None:
                raise NetworkValidationError(
                    7,
                    f"phase {phase.id} of intersection {si.id} contains "
                    f"conflicting movement pair {pair}",
                )


def _check_invariant_8(network: Network, junctions_by_id: dict[JunctionId, Junction]) -> None:
    """Every movement of a signalized junction belongs to exactly one signal group."""
    for si in network.signalized_intersections:
        all_movements = {m.id for m in movements_of(network, si.junction)}
        membership: dict[MovementId, int] = dict.fromkeys(all_movements, 0)
        for group in si.signal_groups:
            for movement_id in group.movements:
                membership[movement_id] = membership.get(movement_id, 0) + 1
        for movement_id, count in membership.items():
            if count != 1:
                raise NetworkValidationError(
                    8,
                    f"movement {movement_id} of junction {si.junction} belongs "
                    f"to {count} signal group(s) of intersection {si.id}, not exactly 1",
                )


def _check_invariant_9(network: Network) -> None:
    """`min_green_s > 0`, `max_green_s > min_green_s` or `== 0`.

    `decision_interval_s <= min_green_s`, the invariant's third clause, is not
    checked here: `decision_interval_s` is not a field of `SignalTiming` (SS2.7)
    or anywhere else in the SS2-SS5 domain model T1.2 implements. It is the
    constraint layer's own config field (`08_AGENT_HANDOFF_PROTOCOL.md` SS9's
    worked T1.6 example), whose acceptance criteria already require T1.6 to
    reject `decision_interval_s > min_green_s` at load. See the T1.2 completion
    report.
    """
    for si in network.signalized_intersections:
        timing = si.timing
        if not timing.min_green_s > 0:
            raise NetworkValidationError(
                9,
                f"intersection {si.id}.timing.min_green_s = {timing.min_green_s}, must be > 0",
            )
        if not (timing.max_green_s == 0.0 or timing.max_green_s > timing.min_green_s):
            raise NetworkValidationError(
                9,
                f"intersection {si.id}.timing.max_green_s = {timing.max_green_s} "
                f"must be 0 or > min_green_s ({timing.min_green_s})",
            )
