"""Two numberings: junction index and traffic-light `linkIndex` (Amendment A1, trap 2).

On every net T1.3 generates -- and on the probe and `cologne1` -- the two
coincide, so a parser that assumed they were equal would pass every other test.
Here the four-way is rebuilt with its `linkIndex` reversed through the
`.tll.xml`'s `<connection>` elements (which, unlike a `.con.xml`, netconvert
honours), leaving the junction's `<request>` numbering untouched.

The second half replays the M0 reference's mistake -- a program whose states
assume a link order the built net does not have -- and shows that both the
runtime display check and `build()`'s own check reject it.
"""

from __future__ import annotations

import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest
import sumolib

from tests.generated_scenario import OVERLOAD_PERIOD_S, Built, load_ids, one_flow_per_movement
from tests.scenarios.conftest import raw_net
from tests.scenarios.test_runtime import SUMO, _check_display, _cycle_s, _shown
from traffic_lab.domain.network import (
    IntersectionId,
    LaneConnectionId,
    PhaseId,
    TurnDirection,
    conflicting_pair,
    green_link_indices,
    movements_of,
)
from traffic_lab.scenarios import NetworkCorrespondenceError, parse_network
from traffic_lab.scenarios.generator import (
    NET_STEM,
    _check_program_matches_link_order,
)
from traffic_lab.scenarios.parse import SumoIds


def _phases(built: Built) -> list[list[tuple[str, TurnDirection]]]:
    return [[(f"approach_{k}_in", turn) for k, turn in p.green] for p in built.spec.phases]


def _rebuild_reversed(built: Built, out: Path, *, permute_states: bool) -> Path:
    """The four-way with `linkIndex` reversed. With `permute_states`, the program
    is re-indexed consistently; without, it keeps the original states -- written
    against a link order the net no longer has."""
    src = built.net.parent
    root = ET.parse(src / f"{NET_STEM}.tll.xml").getroot()
    (tl_logic,) = root.iter("tlLogic")
    size = len(built.network.signalized_intersections[0].controlled_connections)
    if permute_states:
        for phase in tl_logic.iter("phase"):
            phase.set("state", phase.get("state", "")[::-1])
    links = raw_net(built.net).link_index
    for (from_lane, to_lane), link in links.items():
        from_edge, from_index = from_lane.rsplit("_", 1)
        to_edge, to_index = to_lane.rsplit("_", 1)
        ET.SubElement(
            root,
            "connection",
            {
                "from": from_edge,
                "to": to_edge,
                "fromLane": from_index,
                "toLane": to_index,
                "tl": "center",
                "linkIndex": str(size - 1 - link),
            },
        )
    program = out / "reversed.tll.xml"
    ET.ElementTree(root).write(program)
    net = out / "reversed.net.xml"
    result = subprocess.run(
        [
            sumolib.checkBinary("netconvert"),
            "--node-files",
            str(src / f"{NET_STEM}.nod.xml"),
            "--edge-files",
            str(src / f"{NET_STEM}.edg.xml"),
            "--connection-files",
            str(src / f"{NET_STEM}.con.xml"),
            "--tllogic-files",
            str(program),
            "--no-turnarounds",
            "true",
            "--output-file",
            str(net),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "LC_ALL": "C"},
        check=True,
    )
    assert "Warning" not in result.stdout + result.stderr
    return net


@pytest.fixture(scope="module")
def reversed_net(four_way: Built, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _rebuild_reversed(four_way, tmp_path_factory.mktemp("reversed"), permute_states=True)


def test_the_rebuilt_net_really_has_two_numberings(four_way: Built, reversed_net: Path) -> None:
    net = sumolib.net.readNet(str(reversed_net), withInternal=True)
    connections = [
        c
        for e in net.getEdges()
        if not e.getFunction()
        for lane in e.getLanes()
        for c in lane.getOutgoing()
    ]
    assert sum(c.getJunctionIndex() != c.getTLLinkIndex() for c in connections) == len(connections)


def test_controlled_connections_follow_link_index(four_way: Built, reversed_net: Path) -> None:
    network, ids = parse_network(
        reversed_net, phases=_phases(four_way), timing=four_way.spec.timing
    )
    assert ids == load_ids(four_way.net.parent / f"{NET_STEM}.ids.json")
    original = four_way.network.signalized_intersections[0].controlled_connections
    (intersection,) = network.signalized_intersections
    assert intersection.controlled_connections == original[::-1]
    size = len(original)
    for k in range(len(four_way.spec.phases)):
        before = green_link_indices(four_way.network, IntersectionId(0), PhaseId(k))
        after = green_link_indices(network, IntersectionId(0), PhaseId(k))
        assert after == frozenset(size - 1 - i for i in before)


def test_the_conflict_matrix_follows_the_junction_index(
    four_way: Built, reversed_net: Path
) -> None:
    """`foes` is indexed by junction index, which did not move: the matrix must not
    move either, although every `linkIndex` did."""
    network, _ = parse_network(reversed_net, phases=_phases(four_way), timing=four_way.spec.timing)
    for before, after in zip(four_way.network.junctions, network.junctions, strict=True):
        assert before.conflicts.movements == after.conflicts.movements
        assert np.array_equal(before.conflicts.matrix, after.conflicts.matrix)


def test_sumo_shows_each_phase_on_the_reversed_net(four_way: Built, reversed_net: Path) -> None:
    network, ids = parse_network(
        reversed_net, phases=_phases(four_way), timing=four_way.spec.timing
    )
    rebuilt = Built(reversed_net, network, ids, four_way.spec)
    assert _check_display(rebuilt, reversed_net) == [PhaseId(k) for k in range(4)]


# --- The M0 reference's mistake, replayed --------------------------------------


@pytest.fixture(scope="module")
def misindexed_net(four_way: Built, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _rebuild_reversed(four_way, tmp_path_factory.mktemp("misindexed"), permute_states=False)


def _parsed(built: Built, net: Path) -> tuple[Built, SumoIds]:
    network, ids = parse_network(net, phases=_phases(built), timing=built.spec.timing)
    return Built(net, network, ids, built.spec), ids


def test_the_display_check_rejects_a_misindexed_program(
    four_way: Built, misindexed_net: Path
) -> None:
    rebuilt, _ = _parsed(four_way, misindexed_net)
    with pytest.raises(AssertionError, match="no authored phase"):
        _check_display(rebuilt, misindexed_net)


def test_builds_own_check_rejects_a_misindexed_program(
    four_way: Built, misindexed_net: Path
) -> None:
    rebuilt, _ = _parsed(four_way, misindexed_net)
    with pytest.raises(NetworkCorrespondenceError, match="does not show the authored phases"):
        _check_program_matches_link_order(
            misindexed_net, rebuilt.network, len(four_way.spec.phases), four_way.spec.timing
        )


def test_sumo_runs_a_misindexed_program_without_a_single_warning(
    four_way: Built, misindexed_net: Path, tmp_path: Path
) -> None:
    """Why the display check exists. The mis-indexed program greens a CONFLICTING
    pair -- yet SUMO runs it, with traffic on every movement, without one warning:
    netconvert derives `response` from the loaded program, so the links greened
    together by mistake simply yield to each other. (Verified separately on
    1.27.1 with perpendicular through movements greened together: no runtime
    warning either.) The absence of warnings is therefore no evidence that a
    program shows the intended phases; `_check_display` is.
    """
    rebuilt, ids = _parsed(four_way, misindexed_net)
    (intersection,) = rebuilt.network.signalized_intersections
    junction = rebuilt.network.junctions[intersection.junction]
    movement_of = {
        c: m.id for m in movements_of(rebuilt.network, junction.id) for c in m.connections
    }
    connection_of = {lanes: LaneConnectionId(i) for i, lanes in enumerate(ids.connections)}
    first_green, _ = _shown(misindexed_net, "center", 1)[0]
    shown_movements = {movement_of[connection_of[lanes]] for lanes in first_green}
    assert conflicting_pair(junction.conflicts, shown_movements) is not None

    end_s = 2 * _cycle_s(four_way) + 60.0
    routes = one_flow_per_movement(
        four_way, tmp_path / "demand.rou.xml", end_s - 60.0, period_s=OVERLOAD_PERIOD_S
    )
    result = subprocess.run(
        [
            SUMO,
            "--net-file",
            str(misindexed_net),
            "--route-files",
            str(routes),
            "--end",
            str(end_s),
            "--time-to-teleport",
            "-1",
            "--no-step-log",
            "true",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "LC_ALL": "C"},
        check=False,
    )
    assert result.returncode == 0
    assert "Warning" not in result.stdout + result.stderr
