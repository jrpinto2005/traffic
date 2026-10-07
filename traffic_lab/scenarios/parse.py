"""Parse a built SUMO network into canonical types (`05_DOMAIN_MODEL.md` SS2, SS7).

One parser for every net: T1.3's own output and nets it did not generate (the
M0 reference, RESCO's `cologne1`), so it cannot lean on the generator's naming.
Reads static file data through sumolib only; never a running simulation.

**Canonical IDs** (`05_DOMAIN_MODEL.md` SS7, T1.3 Amendment A2):

- `LaneId`: sorted SUMO lane IDs, internal (`:`) lanes included -- the order of
  `BackendIndex.lane_sumo_ids`.
- `EdgeId`: sorted SUMO edge IDs, internal edges included.
- `JunctionId`: sorted SUMO junction IDs. Internal junctions (`type="internal"`,
  waiting positions inside a junction) are not nodes of the network and sumolib
  does not load them; T1.3's generated nets have none (asserted in
  `tests/scenarios/test_build.py`).
- `IntersectionId`: sorted traffic-light IDs -- `BackendIndex.intersection_sumo_ids`.
- `LaneConnectionId`: connections between normal lanes, sorted by
  (from `LaneId`, to `LaneId`).
- `MovementId`: local to its junction, numbered from 0 in `movements_of()` order --
  the numbering `validate_network()` invariant 8 checks signal groups against.
- `SignalGroupId`: one signal group per movement, numbered as the movement.
- `PhaseId`: the authored order.

**Connections.** A canonical `LaneConnection` is a SUMO connection between two
normal lanes. SUMO's connections *out of* internal lanes (from the internal lane
to the outgoing lane, or between the two halves of a split internal lane) are
represented by the internal lane itself, which is a canonical `Lane` on an
internal `Edge` whose junctions are both the junction it crosses. Internal lanes
therefore have no `successors`.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import sumolib

from traffic_lab.domain.network import (
    ConflictMatrix,
    Edge,
    EdgeId,
    IntersectionId,
    Junction,
    JunctionId,
    Lane,
    LaneConnection,
    LaneConnectionId,
    LaneId,
    MovementId,
    Network,
    NetworkValidationError,
    Phase,
    PhaseId,
    SignalGroup,
    SignalGroupId,
    SignalizedIntersection,
    SignalTiming,
    TurnDirection,
    VehicleType,
    conflicting_pair,
    movements_of,
    validate_network,
)
from traffic_lab.scenarios.conflicts import (
    NetworkCorrespondenceError,
    junction_index,
    seed_conflict_matrix,
)

#: A connection's `dir` attribute -> canonical turn (T1.3 Amendment A4). Anything
#: else is not representable and raises.
TURN_OF_SUMO_DIR = {
    "s": TurnDirection.THROUGH,
    "l": TurnDirection.LEFT,
    "L": TurnDirection.LEFT,
    "r": TurnDirection.RIGHT,
    "R": TurnDirection.RIGHT,
    "t": TurnDirection.U_TURN,
}

#: The SUMO vehicle class each canonical type is. The inverse of
#: `traffic_lab.backend.projection.VEHICLE_CLASS_TO_TYPE`, which `scenarios/` may
#: not import (`06_ARCHITECTURE.md` SS10); a test asserts the two agree.
SUMO_CLASS_OF_TYPE = {VehicleType.CAR: "passenger", VehicleType.MOTORCYCLE: "motorcycle"}

#: One authored phase: the (incoming edge SUMO ID, turn) pairs it greens.
PhaseGreens = Collection[tuple[str, TurnDirection]]


@dataclass(frozen=True, slots=True)
class SumoIds:
    """The SUMO string ID of every canonical integer ID: position *i* holds ID *i*.

    `connections` holds each canonical connection as (from lane, to lane) SUMO IDs.
    Movements, signal groups and phases have no SUMO ID (SS7: SUMO has no
    first-class movement).
    """

    lanes: tuple[str, ...]
    edges: tuple[str, ...]
    junctions: tuple[str, ...]
    intersections: tuple[str, ...]
    connections: tuple[tuple[str, str], ...]

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), indent=1)


def parse_network(
    net_file: Path, *, phases: Sequence[PhaseGreens], timing: SignalTiming
) -> tuple[Network, SumoIds]:
    """Parse `net_file` into a validated canonical `Network` and its ID mapping.

    `phases` and `timing` are the authored signal plan of the net's one traffic
    light (D-023: authored, then validated). Phases name movements by incoming
    edge SUMO ID and turn, so a net T1.3 did not generate needs no approach
    numbering. Raises `NetworkValidationError` (invariant 7, naming the pair) for
    a phase containing a `CONFLICTING` pair, `ValueError` for a phase naming a
    movement that does not exist, and `NetworkCorrespondenceError` for a net the
    canonical types cannot represent one-to-one.
    """
    net = sumolib.net.readNet(str(net_file), withInternal=True)

    sumo_edges = sorted(net.getEdges(), key=lambda e: e.getID())
    for edge in sumo_edges:
        if edge.getFunction() not in ("", "internal"):
            raise NetworkCorrespondenceError(
                f"edge {edge.getID()} has function {edge.getFunction()!r}; pedestrian "
                f"infrastructure has no canonical type (D-029)"
            )
    sumo_nodes = sorted(net.getNodes(), key=lambda n: n.getID())
    traffic_lights = sorted(net.getTrafficLights(), key=lambda t: t.getID())
    if len(traffic_lights) != 1:
        raise NetworkCorrespondenceError(
            f"{net_file.name} has {len(traffic_lights)} traffic lights; M1 parses single "
            f"intersections (multiple intersections are M5)"
        )

    lane_id = {
        lane.getID(): LaneId(i)
        for i, lane in enumerate(
            sorted((lane for e in sumo_edges for lane in e.getLanes()), key=lambda la: la.getID())
        )
    }
    edge_id = {edge.getID(): EdgeId(i) for i, edge in enumerate(sumo_edges)}
    junction_id = {node.getID(): JunctionId(i) for i, node in enumerate(sumo_nodes)}

    sumo_connections = _normal_connections(sumo_edges, lane_id)
    connections = tuple(
        LaneConnection(
            id=LaneConnectionId(i),
            from_lane=lane_id[c.getFromLane().getID()],
            to_lane=lane_id[c.getToLane().getID()],
            via_junction=junction_id[c.getFrom().getToNode().getID()],
            turn=_turn(c),
        )
        for i, c in enumerate(sumo_connections)
    )

    lanes = _lanes(sumo_edges, lane_id, edge_id, connections)
    edges = _edges(sumo_edges, lane_id, edge_id, junction_id)
    provisional = Network(
        edges=edges,
        lanes=lanes,
        connections=connections,
        junctions=_junctions(sumo_nodes, sumo_edges, lane_id, connections),
        signalized_intersections=(),
    )
    _check_movement_keys(provisional, sumo_edges)
    junctions = tuple(
        dataclasses.replace(
            junction,
            conflicts=_conflicts(provisional, junction, node, sumo_connections),
        )
        for junction, node in zip(provisional.junctions, sumo_nodes, strict=True)
    )
    network = dataclasses.replace(provisional, junctions=junctions)

    tls = traffic_lights[0]
    controlled = _controlled_connections(tls, sumo_connections, connections)
    intersection = _signalize(network, controlled, phases, timing, sumo_edges, edge_id)
    network = dataclasses.replace(network, signalized_intersections=(intersection,))
    validate_network(network)

    ids = SumoIds(
        lanes=tuple(lane_id),
        edges=tuple(edge_id),
        junctions=tuple(junction_id),
        intersections=(tls.getID(),),
        connections=tuple(
            (c.getFromLane().getID(), c.getToLane().getID()) for c in sumo_connections
        ),
    )
    return network, ids


# --- Topology -----------------------------------------------------------------


def _normal_connections(sumo_edges: Sequence[Any], lane_id: dict[str, LaneId]) -> list[Any]:
    """SUMO's connections between normal lanes, in `LaneConnectionId` order."""
    found = [
        connection
        for edge in sumo_edges
        if edge.getFunction() == ""
        for lane in edge.getLanes()
        for connection in lane.getOutgoing()
    ]
    for connection in found:
        if connection.getTo().getFunction() != "":
            raise NetworkCorrespondenceError(
                f"connection {connection.getFromLane().getID()} -> "
                f"{connection.getToLane().getID()} ends on a non-normal edge"
            )
    found.sort(key=lambda c: (lane_id[c.getFromLane().getID()], lane_id[c.getToLane().getID()]))
    keys = [(c.getFromLane().getID(), c.getToLane().getID()) for c in found]
    if len(set(keys)) != len(keys):
        raise NetworkCorrespondenceError("two SUMO connections join the same pair of lanes")
    return found


def _turn(connection: Any) -> TurnDirection:
    direction = connection.getDirection()
    if direction not in TURN_OF_SUMO_DIR:
        raise NetworkCorrespondenceError(
            f"connection {connection.getFromLane().getID()} -> "
            f"{connection.getToLane().getID()} has dir={direction!r}, which has no "
            f"canonical TurnDirection (T1.3 Amendment A4)"
        )
    return TURN_OF_SUMO_DIR[direction]


def _lanes(
    sumo_edges: Sequence[Any],
    lane_id: dict[str, LaneId],
    edge_id: dict[str, EdgeId],
    connections: Sequence[LaneConnection],
) -> tuple[Lane, ...]:
    successors: dict[LaneId, list[LaneConnectionId]] = {}
    for connection in connections:
        successors.setdefault(connection.from_lane, []).append(connection.id)

    lanes: list[Lane] = []
    for edge in sumo_edges:
        edge_lanes = edge.getLanes()
        for index, lane in enumerate(edge_lanes):
            this = lane_id[lane.getID()]
            lanes.append(
                Lane(
                    id=this,
                    edge=edge_id[edge.getID()],
                    index=index,
                    length_m=float(lane.getLength()),
                    width_m=float(lane.getWidth()),
                    speed_limit_mps=float(lane.getSpeed()),
                    successors=tuple(successors.get(this, ())),
                    # Index 0 is rightmost; same edge only (SS8 invariant 3).
                    adjacent_left=(
                        lane_id[edge_lanes[index + 1].getID()]
                        if index + 1 < len(edge_lanes)
                        else None
                    ),
                    adjacent_right=lane_id[edge_lanes[index - 1].getID()] if index > 0 else None,
                    allowed_types=frozenset(
                        t for t, sumo_class in SUMO_CLASS_OF_TYPE.items() if lane.allows(sumo_class)
                    ),
                )
            )
    return tuple(sorted(lanes, key=lambda la: la.id))


def _edges(
    sumo_edges: Sequence[Any],
    lane_id: dict[str, LaneId],
    edge_id: dict[str, EdgeId],
    junction_id: dict[str, JunctionId],
) -> tuple[Edge, ...]:
    """Edges in `EdgeId` order. Internal edges run from and to the junction they cross.

    `opposite` pairs two normal edges when each is the only normal edge between
    the same two junctions in its direction: symmetric by construction (SS8
    invariant 5), and `None` wherever "the reverse edge of the same street" would
    be ambiguous.
    """
    by_direction: dict[tuple[str, str], list[str]] = {}
    for edge in sumo_edges:
        if edge.getFunction() == "":
            key = (edge.getFromNode().getID(), edge.getToNode().getID())
            by_direction.setdefault(key, []).append(edge.getID())

    def opposite(edge: Any) -> EdgeId | None:
        if edge.getFunction() != "":
            return None
        forward = by_direction[(edge.getFromNode().getID(), edge.getToNode().getID())]
        reverse = by_direction.get((edge.getToNode().getID(), edge.getFromNode().getID()), [])
        if len(forward) == 1 and len(reverse) == 1:
            return edge_id[reverse[0]]
        return None

    return tuple(
        Edge(
            id=edge_id[edge.getID()],
            lanes=tuple(lane_id[lane.getID()] for lane in edge.getLanes()),
            from_junction=junction_id[edge.getFromNode().getID()],
            to_junction=junction_id[edge.getToNode().getID()],
            length_m=float(edge.getLength()),
            opposite=opposite(edge),
        )
        for edge in sumo_edges
    )


def _junctions(
    sumo_nodes: Sequence[Any],
    sumo_edges: Sequence[Any],
    lane_id: dict[str, LaneId],
    connections: Sequence[LaneConnection],
) -> tuple[Junction, ...]:
    """Junctions with empty conflict matrices; `_conflicts` fills them in once
    `movements_of` can run over the provisional network."""
    incoming: dict[str, list[LaneId]] = {}
    outgoing: dict[str, list[LaneId]] = {}
    for edge in sumo_edges:
        if edge.getFunction() != "":
            continue
        lanes = [lane_id[lane.getID()] for lane in edge.getLanes()]
        incoming.setdefault(edge.getToNode().getID(), []).extend(lanes)
        outgoing.setdefault(edge.getFromNode().getID(), []).extend(lanes)

    junctions = []
    for i, node in enumerate(sumo_nodes):
        x, y = node.getCoord()
        junctions.append(
            Junction(
                id=JunctionId(i),
                incoming_lanes=tuple(sorted(incoming.get(node.getID(), []))),
                outgoing_lanes=tuple(sorted(outgoing.get(node.getID(), []))),
                connections=tuple(c.id for c in connections if c.via_junction == JunctionId(i)),
                conflicts=ConflictMatrix(movements=(), matrix=np.zeros((0, 0), dtype=np.int8)),
                position_xy=(float(x), float(y)),
            )
        )
    return tuple(junctions)


def _check_movement_keys(network: Network, sumo_edges: Sequence[Any]) -> None:
    """A movement is keyed by (approach edge, turn) (D-011, SS2.6) and has one
    `to_edge`. SUMO can give one approach two exits with the same canonical turn --
    netconvert marks them `r` and `R` (or `l` and `L`) at five or more approaches
    -- and the movement key cannot tell them apart."""
    edge_sumo_id = [e.getID() for e in sumo_edges]
    lanes = {lane.id: lane for lane in network.lanes}
    exits: dict[tuple[EdgeId, TurnDirection], set[EdgeId]] = {}
    for connection in network.connections:
        key = (lanes[connection.from_lane].edge, connection.turn)
        exits.setdefault(key, set()).add(lanes[connection.to_lane].edge)
    for (from_edge, turn), to_edges in exits.items():
        if len(to_edges) > 1:
            raise NetworkCorrespondenceError(
                f"approach {edge_sumo_id[from_edge]} has {len(to_edges)} {turn.value} exits "
                f"({', '.join(sorted(edge_sumo_id[e] for e in to_edges))}); a Movement is keyed "
                f"by (approach edge, turn) and has one to_edge (D-011)"
            )


def _conflicts(
    network: Network, junction: Junction, node: Any, sumo_connections: Sequence[Any]
) -> ConflictMatrix:
    movements = movements_of(network, junction.id)
    return seed_conflict_matrix(
        node,
        [
            (m.id, [junction_index(sumo_connections[int(c)]) for c in m.connections])
            for m in movements
        ],
    )


# --- Signals --------------------------------------------------------------------


def _controlled_connections(
    tls: Any, sumo_connections: Sequence[Any], connections: Sequence[LaneConnection]
) -> tuple[LaneConnectionId, ...]:
    """The light's connections by SUMO `linkIndex`, read from the built net (D-034).

    Mapped through each connection, never assumed equal to its junction index
    (T1.3 Amendment A1, trap 2).
    """
    by_lanes = {
        (c.getFromLane().getID(), c.getToLane().getID()): connections[i].id
        for i, c in enumerate(sumo_connections)
    }
    by_link: dict[int, LaneConnectionId] = {}
    for in_lane, out_lane, link in tls.getConnections():
        key = (in_lane.getID(), out_lane.getID())
        if link in by_link:
            raise NetworkCorrespondenceError(
                f"traffic light {tls.getID()} shows connections {key} and "
                f"{_lanes_of(by_link[link], sumo_connections)} at the same linkIndex {link}; "
                f"controlled_connections has one connection per index (T1.3 Amendment A3)"
            )
        by_link[int(link)] = by_lanes[key]
    if sorted(by_link) != list(range(len(by_link))):
        raise NetworkCorrespondenceError(
            f"traffic light {tls.getID()} uses link indices {sorted(by_link)}, not 0..n-1"
        )
    return tuple(by_link[i] for i in range(len(by_link)))


def _lanes_of(connection: LaneConnectionId, sumo_connections: Sequence[Any]) -> tuple[str, str]:
    c = sumo_connections[int(connection)]
    return (c.getFromLane().getID(), c.getToLane().getID())


def _signalize(
    network: Network,
    controlled: tuple[LaneConnectionId, ...],
    phases: Sequence[PhaseGreens],
    timing: SignalTiming,
    sumo_edges: Sequence[Any],
    edge_id: dict[str, EdgeId],
) -> SignalizedIntersection:
    by_id = {c.id: c for c in network.connections}
    junctions = {by_id[c].via_junction for c in controlled}
    if len(junctions) != 1:
        raise NetworkCorrespondenceError(
            f"the traffic light controls connections at {len(junctions)} junctions"
        )
    (junction,) = junctions
    assert junction is not None  # SUMO connections always cross a junction

    movements = movements_of(network, junction)
    movement_of = {(m.from_edge, m.turn): m.id for m in movements}
    edge_sumo_id = [e.getID() for e in sumo_edges]
    conflicts = next(j.conflicts for j in network.junctions if j.id == junction)

    authored: list[Phase] = []
    for k, greens in enumerate(phases):
        green_movements: list[MovementId] = []
        for edge, turn in greens:
            movement = movement_of.get((edge_id[edge], turn)) if edge in edge_id else None
            if movement is None:
                available = sorted(f"({edge_sumo_id[e]}, {t.value})" for e, t in movement_of)
                raise ValueError(
                    f"phase {k} greens ({edge}, {turn.value}), which is not a movement of the "
                    f"signalized junction; its movements are {', '.join(available)}"
                )
            green_movements.append(movement)
        pair = conflicting_pair(conflicts, green_movements)
        if pair is not None:
            a, b = (movements[int(m)] for m in pair)
            raise NetworkValidationError(
                7,
                f"phase {k} greens conflicting movements ({edge_sumo_id[a.from_edge]}, "
                f"{a.turn.value}) and ({edge_sumo_id[b.from_edge]}, {b.turn.value}) (D-023)",
            )
        authored.append(
            Phase(id=PhaseId(k), green_groups=frozenset(SignalGroupId(m) for m in green_movements))
        )

    return SignalizedIntersection(
        id=IntersectionId(0),
        junction=junction,
        signal_groups=tuple(
            SignalGroup(id=SignalGroupId(m.id), movements=(m.id,)) for m in movements
        ),
        phases=tuple(authored),
        timing=timing,
        controlled_connections=controlled,
    )
