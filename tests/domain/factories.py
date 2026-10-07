"""Shared fixture network for `domain` tests. Test-only, not a `traffic_lab` package.

Builds one small, valid, signalized 4-way junction: opposing north-south and
east-west through movements, each pair compatible with itself and conflicting
with the other pair -- the standard two-phase intersection. Every invariant
test in `test_validate_network.py` starts from `build_valid_network()` and
mutates a copy (via `dataclasses.replace`) to break exactly one invariant.
"""

from __future__ import annotations

import numpy as np

from traffic_lab.domain.network import (
    Compatibility,
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
    Phase,
    PhaseId,
    SignalGroup,
    SignalGroupId,
    SignalizedIntersection,
    SignalTiming,
    TurnDirection,
    VehicleType,
)

J_NORTH = JunctionId(1)
J_SOUTH = JunctionId(2)
J_EAST = JunctionId(3)
J_WEST = JunctionId(4)
J0 = JunctionId(0)

E_N_IN, E_S_IN, E_E_IN, E_W_IN = (EdgeId(i) for i in range(4))
E_N_OUT, E_S_OUT, E_E_OUT, E_W_OUT = (EdgeId(i) for i in range(4, 8))

L_N_IN, L_S_IN, L_E_IN, L_W_IN = (LaneId(i) for i in range(4))
L_N_OUT, L_S_OUT, L_E_OUT, L_W_OUT = (LaneId(i) for i in range(4, 8))

C_S_TO_N = LaneConnectionId(0)
C_N_TO_S = LaneConnectionId(1)
C_E_TO_W = LaneConnectionId(2)
C_W_TO_E = LaneConnectionId(3)

# The order `movements_of()` assigns ids in, given junction.connections below:
# (S-in, THROUGH) -> 0, (N-in, THROUGH) -> 1, (E-in, THROUGH) -> 2, (W-in, THROUGH) -> 3.
M_S, M_N, M_E, M_W = (MovementId(i) for i in range(4))

# Display order (SUMO link index) deliberately differs from LaneConnectionId order,
# so a test reading it cannot pass by accidentally assuming the two coincide:
# link 0 = N->S, 1 = E->W, 2 = S->N, 3 = W->E.
CONTROLLED_CONNECTIONS = (C_N_TO_S, C_E_TO_W, C_S_TO_N, C_W_TO_E)

SG_NS = SignalGroupId(0)
SG_EW = SignalGroupId(1)

PHASE_NS = PhaseId(0)
PHASE_EW = PhaseId(1)

INTERSECTION = IntersectionId(0)


def _lane(lane_id: LaneId, edge_id: EdgeId) -> Lane:
    return Lane(
        id=lane_id,
        edge=edge_id,
        index=0,
        length_m=50.0,
        width_m=3.5,
        speed_limit_mps=13.9,
        successors=(),
        adjacent_left=None,
        adjacent_right=None,
        allowed_types=frozenset({VehicleType.CAR}),
    )


def build_valid_network() -> Network:
    edges = (
        Edge(E_N_IN, (L_N_IN,), J_NORTH, J0, 100.0, E_S_OUT),
        Edge(E_S_IN, (L_S_IN,), J_SOUTH, J0, 100.0, E_N_OUT),
        Edge(E_E_IN, (L_E_IN,), J_EAST, J0, 100.0, E_W_OUT),
        Edge(E_W_IN, (L_W_IN,), J_WEST, J0, 100.0, E_E_OUT),
        Edge(E_N_OUT, (L_N_OUT,), J0, J_NORTH, 100.0, E_S_IN),
        Edge(E_S_OUT, (L_S_OUT,), J0, J_SOUTH, 100.0, E_N_IN),
        Edge(E_E_OUT, (L_E_OUT,), J0, J_EAST, 100.0, E_W_IN),
        Edge(E_W_OUT, (L_W_OUT,), J0, J_WEST, 100.0, E_E_IN),
    )

    lanes = tuple(
        _lane(lane_id, edge_id)
        for lane_id, edge_id in (
            (L_N_IN, E_N_IN),
            (L_S_IN, E_S_IN),
            (L_E_IN, E_E_IN),
            (L_W_IN, E_W_IN),
            (L_N_OUT, E_N_OUT),
            (L_S_OUT, E_S_OUT),
            (L_E_OUT, E_E_OUT),
            (L_W_OUT, E_W_OUT),
        )
    )

    connections = (
        LaneConnection(C_S_TO_N, L_S_IN, L_N_OUT, J0, TurnDirection.THROUGH),
        LaneConnection(C_N_TO_S, L_N_IN, L_S_OUT, J0, TurnDirection.THROUGH),
        LaneConnection(C_E_TO_W, L_E_IN, L_W_OUT, J0, TurnDirection.THROUGH),
        LaneConnection(C_W_TO_E, L_W_IN, L_E_OUT, J0, TurnDirection.THROUGH),
    )

    c = Compatibility
    matrix = np.array(
        [
            [c.COMPATIBLE, c.COMPATIBLE, c.CONFLICTING, c.CONFLICTING],
            [c.COMPATIBLE, c.COMPATIBLE, c.CONFLICTING, c.CONFLICTING],
            [c.CONFLICTING, c.CONFLICTING, c.COMPATIBLE, c.COMPATIBLE],
            [c.CONFLICTING, c.CONFLICTING, c.COMPATIBLE, c.COMPATIBLE],
        ],
        dtype=np.int8,
    )
    conflicts = ConflictMatrix(movements=(M_S, M_N, M_E, M_W), matrix=matrix)

    junction = Junction(
        id=J0,
        incoming_lanes=(L_S_IN, L_N_IN, L_E_IN, L_W_IN),
        outgoing_lanes=(L_N_OUT, L_S_OUT, L_W_OUT, L_E_OUT),
        connections=(C_S_TO_N, C_N_TO_S, C_E_TO_W, C_W_TO_E),
        conflicts=conflicts,
        position_xy=(0.0, 0.0),
    )

    sg_ns = SignalGroup(id=SG_NS, movements=(M_S, M_N))
    sg_ew = SignalGroup(id=SG_EW, movements=(M_E, M_W))

    phase_ns = Phase(id=PHASE_NS, green_groups=frozenset({SG_NS}))
    phase_ew = Phase(id=PHASE_EW, green_groups=frozenset({SG_EW}))

    timing = SignalTiming(min_green_s=5.0, max_green_s=60.0, yellow_s=3.0, all_red_s=2.0)

    intersection = SignalizedIntersection(
        id=INTERSECTION,
        junction=J0,
        signal_groups=(sg_ns, sg_ew),
        phases=(phase_ns, phase_ew),
        timing=timing,
        controlled_connections=CONTROLLED_CONNECTIONS,
    )

    boundary_junctions = tuple(
        Junction(
            id=j,
            incoming_lanes=(),
            outgoing_lanes=(),
            connections=(),
            conflicts=ConflictMatrix(movements=(), matrix=np.zeros((0, 0), dtype=np.int8)),
            position_xy=(0.0, 0.0),
        )
        for j in (J_NORTH, J_SOUTH, J_EAST, J_WEST)
    )

    return Network(
        edges=edges,
        lanes=lanes,
        connections=connections,
        junctions=(junction, *boundary_junctions),
        signalized_intersections=(intersection,),
    )
