"""`parse_network()` on nets T1.3 did not generate.

The M0 reference (four-way, turnarounds at its boundary nodes, a program
corrected on 2026-10-07) and RESCO's `cologne1` (a real intersection: `#` in
edge IDs, internal junctions, `s` and `g` states, priority junctions with their
own conflicts). Parse only, no simulation -- the AC's guard against a parser
that encodes assumptions true only of the generator's output.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests.scenarios.conftest import (
    REFERENCE_DIR,
    assert_round_trip,
    foe_bit,
    raw_net,
    request_rows,
)
from traffic_lab.backend.projection import VEHICLE_CLASS_TO_TYPE
from traffic_lab.domain.network import (
    Compatibility,
    EdgeId,
    IntersectionId,
    NetworkValidationError,
    PhaseId,
    SignalTiming,
    TurnDirection,
    green_link_indices,
    movements_of,
    validate_network,
)
from traffic_lab.scenarios.parse import SUMO_CLASS_OF_TYPE, parse_network

TIMING = SignalTiming(min_green_s=10.0, max_green_s=60.0, yellow_s=3.0, all_red_s=2.0)

S, L, R, U = (
    TurnDirection.THROUGH,
    TurnDirection.LEFT,
    TurnDirection.RIGHT,
    TurnDirection.U_TURN,
)

#: Phases the reference net can carry. Its `reference.con.xml` sends each
#: approach's right turn from the *left* lane (lane 1) while the through movement
#: uses the right lane (lane 0), so the two cross inside the junction and are foes
#: -- through and right of one approach cannot share a phase.
REFERENCE_PHASES = [
    [("n_in", S), ("s_in", S)],
    [("n_in", R), ("s_in", R)],
    [("e_in", S), ("w_in", S)],
    [("e_in", R), ("w_in", R)],
]

#: cologne1's four approaches, each served alone: no two of an approach's own
#: movements are foes, so this authored plan validates.
COLOGNE1_APPROACHES = ("-32038056#3", "23429231#1", "28198821#3", "27115123#3")
COLOGNE1_SPLIT = [[(edge, turn) for turn in (R, S, L, U)] for edge in COLOGNE1_APPROACHES]


def _states(tll: Path) -> list[str]:
    return [p.get("state", "") for p in ET.parse(tll).getroot().iter("phase")]


def test_the_reference_net_round_trips(reference_net: Path) -> None:
    network, ids = parse_network(reference_net, phases=REFERENCE_PHASES, timing=TIMING)
    assert_round_trip(network, ids, reference_net)
    validate_network(network)
    assert ids.intersections == ("j1",)


def test_the_corrected_reference_program_still_greens_a_foe_pair(reference_net: Path) -> None:
    """The program corrected on 2026-10-07 (`GGrrGGrr` / `rrGGrrGG`) greens each
    approach's through (lane 0) and right turn (lane 1) together. Those links are
    foes in the built net, so under D-023's corrected rule the corrected program's
    phases are themselves a load error. Reported for escalation, not worked around.
    """
    rows = request_rows(reference_net)["j1"]
    assert foe_bit(rows[0][0], 1) and foe_bit(rows[1][0], 0)  # n_in through x n_in right

    as_programmed = [[("n_in", S), ("n_in", R), ("s_in", S), ("s_in", R)]]
    with pytest.raises(NetworkValidationError, match=r"\(n_in, through\) and \(n_in, right\)"):
        parse_network(reference_net, phases=as_programmed, timing=TIMING)


def test_canonical_green_links_match_the_reference_program_link_order(
    reference_net: Path,
) -> None:
    """The corrected program's `G` positions are exactly the green links of its
    movements: the through phase and right-turn phase of each axis together."""
    network, _ = parse_network(reference_net, phases=REFERENCE_PHASES, timing=TIMING)
    states = _states(REFERENCE_DIR / "reference.tll.xml")
    for program_phase, canonical in ((0, (0, 1)), (2, (2, 3))):
        expected = frozenset(i for i, ch in enumerate(states[program_phase]) if ch == "G")
        green = frozenset().union(
            *(green_link_indices(network, IntersectionId(0), PhaseId(p)) for p in canonical)
        )
        assert green == expected


def test_the_original_reference_program_is_rejected(reference_net: Path) -> None:
    """Before 2026-10-07 the reference greened links 0-3: north and east, whose
    through movements cross. As an authored phase it is a load error naming the pair."""
    north_and_east = [("n_in", S), ("e_in", S)]
    with pytest.raises(NetworkValidationError, match=r"\(e_in, through\) and \(n_in, through\)"):
        parse_network(reference_net, phases=[north_and_east], timing=TIMING)


def test_cologne1_round_trips(cologne1_net: Path) -> None:
    network, ids = parse_network(cologne1_net, phases=COLOGNE1_SPLIT, timing=TIMING)
    assert_round_trip(network, ids, cologne1_net)
    validate_network(network)
    assert ids.intersections == ("cluster_357187_359543",)
    (intersection,) = network.signalized_intersections
    assert len(intersection.controlled_connections) == 20
    # Real data the generator never produces: internal junctions (excluded, see
    # parse.py) and a priority junction with conflicts of its own.
    assert any(j.startswith(":") for j in raw_net(cologne1_net).junctions)
    priority = network.junctions[ids.junctions.index("364075")]
    assert (priority.conflicts.matrix == Compatibility.CONFLICTING).any()


def test_cologne1_permissive_left_conflicts_with_the_opposing_through(cologne1_net: Path) -> None:
    """cologne1's program shows its lefts as `g` alongside the opposing through.
    Under the corrected D-023 rule, with no permitted pair declared, that pair is
    CONFLICTING -- so its own program would not validate as authored phases."""
    network, ids = parse_network(cologne1_net, phases=COLOGNE1_SPLIT, timing=TIMING)
    (intersection,) = network.signalized_intersections
    junction = network.junctions[intersection.junction]
    edge = {e: EdgeId(i) for i, e in enumerate(ids.edges)}
    movement = {(m.from_edge, m.turn): m.id for m in movements_of(network, junction.id)}
    left = movement[(edge["-32038056#3"], L)]
    # 28198821#3's through movement runs into 32038056#0, the reverse of -32038056#3.
    opposing_through = movement[(edge["28198821#3"], S)]
    index = {m: i for i, m in enumerate(junction.conflicts.movements)}
    assert junction.conflicts.matrix[index[left], index[opposing_through]] == (
        Compatibility.CONFLICTING
    )


def test_a_phase_naming_a_missing_movement_is_rejected(reference_net: Path) -> None:
    with pytest.raises(ValueError, match=r"\(n_in, left\), which is not a movement"):
        parse_network(reference_net, phases=[[("n_in", L)]], timing=TIMING)


def test_the_vehicle_class_mapping_agrees_with_the_backend() -> None:
    """`scenarios/` may not import the backend, so the mapping is written twice."""
    assert {v: k for k, v in VEHICLE_CLASS_TO_TYPE.items()} == SUMO_CLASS_OF_TYPE
