"""`green_link_indices()`: a phase's green links as SUMO link indices (D-034).

The fixture's `controlled_connections` order differs from `LaneConnectionId`
order (N->S, E->W, S->N, W->E), so the expected sets below are only produced by
reading positions from `controlled_connections`, never by assuming a
connection's id is its link index.
"""

from __future__ import annotations

import dataclasses

import pytest

from tests.domain.factories import INTERSECTION, PHASE_EW, PHASE_NS, build_valid_network
from traffic_lab.domain.network import IntersectionId, PhaseId, green_link_indices


def test_each_phase_greens_the_links_of_its_movements() -> None:
    network = build_valid_network()
    # NS phase: movements S and N -> connections S->N (link 2) and N->S (link 0).
    assert green_link_indices(network, INTERSECTION, PHASE_NS) == frozenset({0, 2})
    # EW phase: E->W (link 1) and W->E (link 3).
    assert green_link_indices(network, INTERSECTION, PHASE_EW) == frozenset({1, 3})


def test_the_result_follows_controlled_connections_order() -> None:
    network = build_valid_network()
    intersection = network.signalized_intersections[0]
    reversed_display = dataclasses.replace(
        intersection, controlled_connections=intersection.controlled_connections[::-1]
    )
    network = dataclasses.replace(network, signalized_intersections=(reversed_display,))
    assert green_link_indices(network, INTERSECTION, PHASE_NS) == frozenset({1, 3})
    assert green_link_indices(network, INTERSECTION, PHASE_EW) == frozenset({0, 2})


def test_a_connection_the_signal_does_not_display_is_an_error() -> None:
    network = build_valid_network()
    intersection = network.signalized_intersections[0]
    partial = dataclasses.replace(
        intersection, controlled_connections=intersection.controlled_connections[:2]
    )
    network = dataclasses.replace(network, signalized_intersections=(partial,))
    with pytest.raises(ValueError, match="not in controlled_connections"):
        green_link_indices(network, INTERSECTION, PHASE_NS)


def test_unknown_intersection_or_phase_raises() -> None:
    network = build_valid_network()
    with pytest.raises(KeyError):
        green_link_indices(network, IntersectionId(7), PHASE_NS)
    with pytest.raises(KeyError):
        green_link_indices(network, INTERSECTION, PhaseId(7))
