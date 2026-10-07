"""Conflict-matrix seeding from `<request>` rows (D-023 corrected, T1.3 Amendment A1).

Run against two nets T1.3 did not generate: the M0 probe, whose program has a
permissive left, and RESCO's `cologne1`. Generated nets get the same checks in
`test_build.py`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import sumolib

from tests.scenarios.conftest import PROBE_NET, foe_bit, request_rows
from traffic_lab.domain.network import Compatibility, MovementId
from traffic_lab.scenarios.conflicts import (
    junction_index,
    links_are_foes,
    seed_conflict_matrix,
)


def _nets(cologne1_net: Path) -> list[Path]:
    return [PROBE_NET, cologne1_net]


def _connections(node: Any) -> Iterator[Any]:
    """The node's connections between normal lanes."""
    for edge in node.getIncoming():
        if edge.getFunction():
            continue
        for lane in edge.getLanes():
            yield from lane.getOutgoing()


def test_foes_are_symmetric_read_right_to_left(cologne1_net: Path) -> None:
    """A7 (for nets we did not generate): trap 1, the last character is link 0."""
    for net_file in _nets(cologne1_net):
        for junction, rows in request_rows(net_file).items():
            for i, (foes_i, _) in enumerate(rows):
                for j, (foes_j, _) in enumerate(rows):
                    assert foe_bit(foes_i, j) == foe_bit(foes_j, i), (net_file.name, junction, i, j)


def test_foes_are_not_symmetric_read_left_to_right(cologne1_net: Path) -> None:
    """The wrong reading is detectably wrong, so the symmetry test has teeth."""
    for net_file, junction in ((PROBE_NET, "C"), (cologne1_net, "cluster_357187_359543")):
        rows = request_rows(net_file)[junction]
        assert any(
            rows[i][0][j] != rows[j][0][i] for i in range(len(rows)) for j in range(len(rows))
        ), (net_file.name, junction)


def test_junction_index_is_a_bijection_onto_request_rows(cologne1_net: Path) -> None:
    for net_file in _nets(cologne1_net):
        net = sumolib.net.readNet(str(net_file), withInternal=True)
        rows = request_rows(net_file)
        for node in net.getNodes():
            indices = [junction_index(c) for c in _connections(node)]
            assert sorted(indices) == list(range(len(rows.get(node.getID(), [])))), node.getID()


def test_the_middle_number_of_the_internal_lane_alone_is_not_the_junction_index(
    cologne1_net: Path,
) -> None:
    """Amendment A1 trap 2 says the junction index is the middle number of
    `:<junction>_<index>_<lane>`. That holds only for lane 0: the second lane of a
    two-lane through movement shares its internal edge, so the middle number
    collides. The collisions are exactly the "4 of 16" (probe) and "4 of 20"
    (`cologne1`) links D-023 records as disagreeing with `linkIndex`; read as
    middle number plus lane, the junction index equals `linkIndex` on every link
    of both nets.
    """
    for net_file, junction, collisions in (
        (PROBE_NET, "C", 4),
        (cologne1_net, "cluster_357187_359543", 4),
    ):
        node = sumolib.net.readNet(str(net_file), withInternal=True).getNode(junction)
        connections = list(_connections(node))
        middle = Counter(int(c.getViaLaneID().rsplit("_", 2)[1]) for c in connections)
        assert sum(count - 1 for count in middle.values()) == collisions
        assert all(junction_index(c) == c.getTLLinkIndex() for c in connections)


def _by_movement(node: Any) -> dict[tuple[str, str], list[int]]:
    grouped: dict[tuple[str, str], list[int]] = {}
    for connection in _connections(node):
        key = (connection.getFrom().getID(), connection.getDirection())
        grouped.setdefault(key, []).append(junction_index(connection))
    return grouped


def test_hand_checked_link_relations_on_the_probe() -> None:
    """The probe's geometry, read by hand: N2C comes from the north, so its right
    turn goes west (C2W), merging with E2C's through movement."""
    node = sumolib.net.readNet(str(PROBE_NET), withInternal=True).getNode("C")
    links = _by_movement(node)

    def foes(a: tuple[str, str], b: tuple[str, str]) -> bool:
        return any(links_are_foes(node, i, j) for i in links[a] for j in links[b])

    assert foes(("N2C", "r"), ("E2C", "s"))  # merge into C2W
    assert not foes(("N2C", "r"), ("S2C", "r"))  # opposite corners
    assert not foes(("N2C", "s"), ("S2C", "s"))  # opposing throughs
    assert foes(("N2C", "s"), ("E2C", "s"))  # crossing throughs
    # The textbook permissive left (green 'g' in the probe's program) crosses the
    # opposing through: a foe, so CONFLICTING unless a scenario declares it permitted.
    assert foes(("N2C", "l"), ("S2C", "s"))


def test_the_seeded_matrix_is_binary_symmetric_and_compatible_on_the_diagonal(
    cologne1_net: Path,
) -> None:
    for net_file in _nets(cologne1_net):
        net = sumolib.net.readNet(str(net_file), withInternal=True)
        for node in net.getNodes():
            grouped = list(_by_movement(node).values())
            movements = [(MovementId(i), links) for i, links in enumerate(grouped)]
            conflicts = seed_conflict_matrix(node, movements)
            matrix = conflicts.matrix
            assert conflicts.movements == tuple(MovementId(i) for i in range(len(grouped)))
            assert (matrix == matrix.T).all()
            assert set(np.unique(matrix)) <= {Compatibility.COMPATIBLE, Compatibility.CONFLICTING}
            assert (np.diag(matrix) == Compatibility.COMPATIBLE).all()


def test_movement_entries_agree_with_the_raw_rows(cologne1_net: Path) -> None:
    """Independent of sumolib: recompute each entry from the raw strings."""
    for net_file in _nets(cologne1_net):
        net = sumolib.net.readNet(str(net_file), withInternal=True)
        rows = request_rows(net_file)
        for node in net.getNodes():
            grouped = list(_by_movement(node).values())
            matrix = seed_conflict_matrix(
                node, [(MovementId(i), links) for i, links in enumerate(grouped)]
            ).matrix
            for a, links_a in enumerate(grouped):
                for b, links_b in enumerate(grouped):
                    expected = a != b and any(
                        foe_bit(rows[node.getID()][i][0], j) or foe_bit(rows[node.getID()][j][0], i)
                        for i in links_a
                        for j in links_b
                    )
                    assert (matrix[a, b] == Compatibility.CONFLICTING) == expected


@pytest.mark.parametrize("bad_via", [":X_1_0", ":C_1", ":C_3_0"])
def test_an_internal_lane_that_disagrees_with_sumolib_is_rejected(bad_via: str) -> None:
    from traffic_lab.scenarios.conflicts import NetworkCorrespondenceError

    node = sumolib.net.readNet(str(PROBE_NET), withInternal=True).getNode("C")
    connection = next(c for c in _connections(node) if c.getViaLaneID() == ":C_1_1")
    connection._via = bad_via
    with pytest.raises(NetworkCorrespondenceError):
        junction_index(connection)
