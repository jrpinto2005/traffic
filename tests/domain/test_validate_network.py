"""One test per `05_DOMAIN_MODEL.md` SS8 invariant covered by `validate_network()`.

`validate_network()` implements invariants 1-9 only. Invariants 10-14 (state)
and 15-16 (demand) are deliberately absent -- see `network.py`'s
`validate_network()` docstring and the T1.2 completion report for why.

Each test starts from `factories.build_valid_network()` (which itself must
pass `validate_network()` cleanly -- asserted once, below) and breaks exactly
one invariant via `dataclasses.replace`.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.domain.factories import (
    E_S_IN,
    E_S_OUT,
    J0,
    L_N_IN,
    L_S_IN,
    M_E,
    M_N,
    M_S,
    M_W,
    SG_EW,
    build_valid_network,
)
from traffic_lab.domain.network import (
    Compatibility,
    ConflictMatrix,
    LaneId,
    NetworkValidationError,
    Phase,
    PhaseId,
    SignalGroup,
    SignalGroupId,
    SignalTiming,
    validate_network,
)


def test_the_fixture_network_is_itself_valid() -> None:
    validate_network(build_valid_network())  # must not raise


def test_invariant_1_lane_must_belong_to_exactly_one_edge() -> None:
    network = build_valid_network()
    # L_N_IN is edge E_N_IN's lane; also list it under E_S_IN.
    e_s_in = next(e for e in network.edges if e.id == E_S_IN)
    edges = tuple(
        dataclasses.replace(e, lanes=(*e.lanes, L_N_IN)) if e.id == E_S_IN else e
        for e in network.edges
    )
    assert e_s_in  # sanity: found it
    network = dataclasses.replace(network, edges=edges)
    with pytest.raises(NetworkValidationError) as excinfo:
        validate_network(network)
    assert excinfo.value.invariant == 1


def test_invariant_2_lane_edge_reference_must_exist() -> None:
    network = build_valid_network()
    # Point L_N_IN at a nonexistent edge, and unlist it from E_N_IN so
    # invariant 1's edge-driven traversal never visits it -- this test targets
    # invariant 2's dangling-reference check specifically, not invariant 1.
    edges = tuple(
        dataclasses.replace(e, lanes=tuple(x for x in e.lanes if x != L_N_IN))
        if L_N_IN in e.lanes
        else e
        for e in network.edges
    )
    lanes = tuple(
        dataclasses.replace(lane, edge=LaneId(9999)) if lane.id == L_N_IN else lane
        for lane in network.lanes
    )
    network = dataclasses.replace(network, edges=edges, lanes=lanes)
    with pytest.raises(NetworkValidationError) as excinfo:
        validate_network(network)
    assert excinfo.value.invariant == 2


def test_invariant_3_adjacent_lanes_must_share_an_edge() -> None:
    network = build_valid_network()
    # Point L_N_IN's adjacent_left at L_S_IN, which is on a different edge.
    lanes = tuple(
        dataclasses.replace(lane, adjacent_left=L_S_IN) if lane.id == L_N_IN else lane
        for lane in network.lanes
    )
    network = dataclasses.replace(network, lanes=lanes)
    with pytest.raises(NetworkValidationError) as excinfo:
        validate_network(network)
    assert excinfo.value.invariant == 3


def test_invariant_4_via_junction_connection_endpoints_must_be_in_the_junctions_lane_sets() -> None:
    network = build_valid_network()
    junctions = tuple(
        dataclasses.replace(j, incoming_lanes=tuple(x for x in j.incoming_lanes if x != L_S_IN))
        if j.id == J0
        else j
        for j in network.junctions
    )
    network = dataclasses.replace(network, junctions=junctions)
    with pytest.raises(NetworkValidationError) as excinfo:
        validate_network(network)
    assert excinfo.value.invariant == 4


def test_invariant_5_edge_opposite_must_be_symmetric() -> None:
    network = build_valid_network()
    # Break symmetry: E_N_IN.opposite is E_S_OUT; unset E_S_OUT.opposite.
    edges = tuple(
        dataclasses.replace(e, opposite=None) if e.id == E_S_OUT else e for e in network.edges
    )
    network = dataclasses.replace(network, edges=edges)
    with pytest.raises(NetworkValidationError) as excinfo:
        validate_network(network)
    assert excinfo.value.invariant == 5


def test_invariant_6_signalized_intersection_needs_at_least_two_signal_groups() -> None:
    network = build_valid_network()
    intersections = tuple(
        dataclasses.replace(si, signal_groups=(si.signal_groups[0],))
        for si in network.signalized_intersections
    )
    network = dataclasses.replace(network, signalized_intersections=intersections)
    with pytest.raises(NetworkValidationError) as excinfo:
        validate_network(network)
    assert excinfo.value.invariant == 6


def test_invariant_7_phase_with_a_conflicting_pair_is_rejected() -> None:
    network = build_valid_network()
    # A phase pairing the NS group with the EW group green_groups -- M_S/M_N vs
    # M_E/M_W are CONFLICTING in the fixture matrix.
    bad_phase = Phase(id=PhaseId(2), green_groups=frozenset({SignalGroupId(0), SG_EW}))
    intersections = tuple(
        dataclasses.replace(si, phases=(*si.phases, bad_phase))
        for si in network.signalized_intersections
    )
    network = dataclasses.replace(network, signalized_intersections=intersections)
    with pytest.raises(NetworkValidationError) as excinfo:
        validate_network(network)
    assert excinfo.value.invariant == 7


def test_invariant_8_every_movement_must_belong_to_exactly_one_signal_group() -> None:
    network = build_valid_network()
    # Drop M_W from every signal group: it now belongs to zero groups.
    intersections = tuple(
        dataclasses.replace(
            si,
            signal_groups=tuple(
                dataclasses.replace(g, movements=tuple(m for m in g.movements if m != M_W))
                for g in si.signal_groups
            ),
        )
        for si in network.signalized_intersections
    )
    network = dataclasses.replace(network, signalized_intersections=intersections)
    with pytest.raises(NetworkValidationError) as excinfo:
        validate_network(network)
    assert excinfo.value.invariant == 8


def test_invariant_8_a_movement_in_two_signal_groups_is_also_rejected() -> None:
    network = build_valid_network()
    # Add a third signal group duplicating M_S, referenced by no phase -- this
    # isolates invariant 8's membership-count check from invariant 7's
    # phase/conflict check, which a group used in a phase would also trip.
    extra_group = SignalGroup(id=SignalGroupId(2), movements=(M_S,))
    intersections = tuple(
        dataclasses.replace(si, signal_groups=(*si.signal_groups, extra_group))
        for si in network.signalized_intersections
    )
    network = dataclasses.replace(network, signalized_intersections=intersections)
    with pytest.raises(NetworkValidationError) as excinfo:
        validate_network(network)
    assert excinfo.value.invariant == 8


def test_invariant_9_min_green_must_be_positive() -> None:
    network = build_valid_network()
    intersections = tuple(
        dataclasses.replace(si, timing=dataclasses.replace(si.timing, min_green_s=0.0))
        for si in network.signalized_intersections
    )
    network = dataclasses.replace(network, signalized_intersections=intersections)
    with pytest.raises(NetworkValidationError) as excinfo:
        validate_network(network)
    assert excinfo.value.invariant == 9


def test_invariant_9_max_green_must_exceed_min_green_unless_zero() -> None:
    network = build_valid_network()
    intersections = tuple(
        dataclasses.replace(
            si, timing=dataclasses.replace(si.timing, min_green_s=10.0, max_green_s=5.0)
        )
        for si in network.signalized_intersections
    )
    network = dataclasses.replace(network, signalized_intersections=intersections)
    with pytest.raises(NetworkValidationError) as excinfo:
        validate_network(network)
    assert excinfo.value.invariant == 9


def test_invariant_9_zero_max_green_disables_the_override_and_is_accepted() -> None:
    network = build_valid_network()
    intersections = tuple(
        dataclasses.replace(si, timing=dataclasses.replace(si.timing, max_green_s=0.0))
        for si in network.signalized_intersections
    )
    network = dataclasses.replace(network, signalized_intersections=intersections)
    validate_network(network)  # must not raise


# --- Property-based test: invariant 7 for arbitrary conflict matrices ------

_MOVEMENT_IDS = (M_S, M_N, M_E, M_W)


@st.composite
def _random_symmetric_compatibility_matrix(draw: st.DrawFn) -> np.ndarray:
    """A random 4x4 matrix of `Compatibility` values, symmetric except that
    `PERMITTED` cells may differ from their mirror (D-023: `PERMITTED` is
    directionally asymmetric)."""
    n = len(_MOVEMENT_IDS)
    values = [[Compatibility.COMPATIBLE] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            forward = draw(st.sampled_from(list(Compatibility)))
            if forward is Compatibility.PERMITTED:
                backward = draw(st.sampled_from(list(Compatibility)))
            else:
                backward = forward
            values[i][j] = forward
            values[j][i] = backward
    return np.array(values, dtype=np.int8)


@given(
    matrix=_random_symmetric_compatibility_matrix(),
    conflicting_pair_index=st.integers(min_value=0, max_value=len(_MOVEMENT_IDS) - 1),
)
def test_property_a_phase_with_a_conflicting_pair_is_always_rejected(
    matrix: np.ndarray, conflicting_pair_index: int
) -> None:
    """For any conflict matrix, forcing one pair to CONFLICTING and putting both
    of that pair's movements in one phase must always be rejected."""
    i = conflicting_pair_index
    j = (i + 1) % len(_MOVEMENT_IDS)
    matrix[i, j] = Compatibility.CONFLICTING
    matrix[j, i] = Compatibility.CONFLICTING

    conflicts = ConflictMatrix(movements=_MOVEMENT_IDS, matrix=matrix)
    junction_id = J0

    # One signal group per movement so the conflicting pair can share a phase.
    groups = tuple(
        SignalGroup(id=SignalGroupId(k), movements=(m,)) for k, m in enumerate(_MOVEMENT_IDS)
    )
    phase = Phase(id=PhaseId(0), green_groups=frozenset({SignalGroupId(i), SignalGroupId(j)}))
    timing = SignalTiming(min_green_s=5.0, max_green_s=60.0, yellow_s=3.0, all_red_s=2.0)

    network = build_valid_network()
    junctions = tuple(
        dataclasses.replace(jn, conflicts=conflicts) if jn.id == junction_id else jn
        for jn in network.junctions
    )
    from traffic_lab.domain.network import IntersectionId, SignalizedIntersection

    intersection = SignalizedIntersection(
        id=IntersectionId(0),
        junction=junction_id,
        signal_groups=groups,
        phases=(phase,),
        timing=timing,
    )
    network = dataclasses.replace(
        network, junctions=junctions, signalized_intersections=(intersection,)
    )

    with pytest.raises(NetworkValidationError) as excinfo:
        validate_network(network)
    assert excinfo.value.invariant == 7
