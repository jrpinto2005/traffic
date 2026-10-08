"""Seeding a junction's conflict matrix from the built net file (D-023, corrected 2026-10-07).

**Source.** Static net-file data only: each junction's `<request index=N foes=...>`
rows. Never `traci.lane.getLinks()`, whose values are runtime state (D-023).

**Rule** (`04_DECISION_REGISTER.md` D-023, "Seeding rule corrected 2026-10-07").
Two links that are foes in **either** direction are `CONFLICTING`; links that are
foes in neither are `COMPATIBLE`. `PERMITTED` arises only where a scenario
declares a pair permitted; no M1 scenario can (D-023 point 4, T1.3 non-goal 5:
`IntersectionSpec` has no field for it), so the M1 matrix is binary, as intended.
`response` is therefore not read: it encodes priority -- who yields if both are
green -- not whether two links may be green together. A movement-level entry
aggregates its links' entries, most restrictive wins; the diagonal is
`COMPATIBLE`.

**Reading traps**, each verified on real nets:

1. *Bit order.* A `foes` string runs right to left: its last character is link 0.
   Only that reading makes `foes` symmetric (asserted in
   `tests/scenarios/test_conflicts.py`). sumolib's `Node.areFoes` reads it that
   way.
2. *Two numberings.* A row's `index` is the connection's **junction index**, which
   is not, in general, the traffic light's `linkIndex`. The two are related only
   through the connection, so every lookup here goes connection -> junction index.
   See `junction_index()` for how the index is derived and cross-checked.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from traffic_lab.domain.network import Compatibility, ConflictMatrix, MovementId


class NetworkCorrespondenceError(ValueError):
    """A SUMO network that canonical types cannot represent one-to-one.

    T1.3's `Escalate if` condition 2. Raised instead of guessing, so that a
    network the model cannot describe produces no `Network` rather than a
    plausible wrong one.
    """


def junction_index(connection: Any) -> int:
    """The `<request index>` of a sumolib connection at the junction it crosses.

    Primary derivation: sumolib's `Connection.getJunctionIndex()`, which counts
    connections in the order SUMO numbers them -- the junction's `incLanes`, and
    each lane's connections in file order.

    Cross-check, wherever the connection has an internal lane: SUMO names it
    `:<junction>_<e>_<l>`, where `<e>` is the junction index of the **first**
    connection on that internal edge and `<l>` the lane on it, so the junction
    index is `e + l`. Reading `<e>` alone (the middle number) gives two
    connections of one two-lane through movement the same index and leaves a
    `<request>` row with no connection -- `tests/scenarios/test_conflicts.py`
    shows it on the M0 probe and on `cologne1`. Disagreement between the two
    derivations raises rather than picking one.
    """
    index = int(connection.getJunctionIndex())
    node_id = connection.getFrom().getToNode().getID()
    if index < 0:
        raise NetworkCorrespondenceError(
            f"connection {_describe(connection)} is not among junction {node_id}'s links"
        )
    via = connection.getViaLaneID()
    if via:
        prefix = f":{node_id}_"
        edge_part, _, lane_part = via.removeprefix(prefix).rpartition("_")
        if not (via.startswith(prefix) and edge_part.isdigit() and lane_part.isdigit()):
            raise NetworkCorrespondenceError(
                f"connection {_describe(connection)} has internal lane {via!r}, not of the "
                f"form ':{node_id}_<index>_<lane>'"
            )
        if int(edge_part) + int(lane_part) != index:
            raise NetworkCorrespondenceError(
                f"connection {_describe(connection)}: sumolib gives junction index {index}, "
                f"its internal lane {via!r} gives {int(edge_part) + int(lane_part)}"
            )
    return index


def links_are_foes(node: Any, a: int, b: int) -> bool:
    """Whether junction links `a` and `b` conflict, in either direction (D-023).

    `Node.areFoes(i, j)` reads bit `j` of row `i`'s `foes` counting from the
    **right** (trap 1).
    """
    try:
        return bool(node.areFoes(a, b) or node.areFoes(b, a))
    except (KeyError, IndexError) as exc:
        raise NetworkCorrespondenceError(
            f"junction {node.getID()} has no complete <request> row for links {a} and {b}"
        ) from exc


def seed_conflict_matrix(
    node: Any, movements: Sequence[tuple[MovementId, Sequence[int]]]
) -> ConflictMatrix:
    """The movement-level conflict matrix of one junction.

    `movements` pairs each movement with the junction indices of its
    connections. Entry `[a, b]` is `CONFLICTING` if any link of `a` and any link
    of `b` are foes in either direction, else `COMPATIBLE`; the diagonal is
    `COMPATIBLE`. Symmetric by construction.
    """
    size = len(movements)
    matrix = np.full((size, size), Compatibility.COMPATIBLE, dtype=np.int8)
    for a, (_, links_a) in enumerate(movements):
        for b, (_, links_b) in enumerate(movements):
            if a != b and any(links_are_foes(node, i, j) for i in links_a for j in links_b):
                matrix[a, b] = Compatibility.CONFLICTING
    return ConflictMatrix(movements=tuple(m for m, _ in movements), matrix=matrix)


def _describe(connection: Any) -> str:
    return f"{connection.getFromLane().getID()} -> {connection.getToLane().getID()}"
