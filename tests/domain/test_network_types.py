"""Construction and immutability of the SS2 network types (D-010, D-011, D-012)."""

from __future__ import annotations

import dataclasses

import pytest

from tests.domain.factories import J0, L_N_IN, L_S_IN, build_valid_network
from traffic_lab.domain.network import Compatibility, TurnDirection, compatibility


def test_network_builds_with_expected_shape() -> None:
    network = build_valid_network()
    assert len(network.edges) == 8
    assert len(network.lanes) == 8
    assert len(network.connections) == 4
    assert len(network.junctions) == 5
    assert len(network.signalized_intersections) == 1


def test_edge_and_lane_types_are_frozen() -> None:
    network = build_valid_network()
    edge = network.edges[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        edge.length_m = 200.0  # type: ignore[misc]


def test_lane_connection_turn_direction_round_trips() -> None:
    network = build_valid_network()
    conn = next(c for c in network.connections if c.from_lane == L_S_IN)
    assert conn.turn is TurnDirection.THROUGH
    assert conn.via_junction == J0


def test_junction_carries_a_conflict_matrix() -> None:
    network = build_valid_network()
    junction = next(j for j in network.junctions if j.id == J0)
    assert len(junction.conflicts.movements) == 4


def test_signalized_intersection_has_at_least_two_signal_groups() -> None:
    network = build_valid_network()
    intersection = network.signalized_intersections[0]
    assert len(intersection.signal_groups) >= 2


def test_conflict_matrix_lookup_is_symmetric_for_compatible_and_conflicting() -> None:
    network = build_valid_network()
    junction = next(j for j in network.junctions if j.id == J0)
    m_s, m_n, m_e, _m_w = junction.conflicts.movements
    assert compatibility(junction.conflicts, m_s, m_n) is Compatibility.COMPATIBLE
    assert compatibility(junction.conflicts, m_n, m_s) is Compatibility.COMPATIBLE
    assert compatibility(junction.conflicts, m_s, m_e) is Compatibility.CONFLICTING
    assert compatibility(junction.conflicts, m_e, m_s) is Compatibility.CONFLICTING


def test_lane_id_newtype_is_a_plain_int_at_runtime() -> None:
    # NewType erases at runtime (SS1.2): LaneId values are plain ints, so they
    # compare and hash like ints and cost nothing beyond a normal int lookup.
    assert int(L_N_IN) == 0
    assert isinstance(L_N_IN, int)
