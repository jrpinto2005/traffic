"""Shared paths and raw-XML readers for the scenario tests.

The readers here parse net files with `xml.etree` directly, independently of
sumolib and of `traffic_lab.scenarios`, so a test can check the parser against
the file rather than against itself.
"""

from __future__ import annotations

import json
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import pytest
import sumolib

from traffic_lab.domain.network import Network, SignalTiming, TurnDirection
from traffic_lab.scenarios import IntersectionSpec, PhaseSpec, build
from traffic_lab.scenarios.generator import IDS_SUFFIX, NET_STEM
from traffic_lab.scenarios.parse import SumoIds

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = REPO_ROOT / "spikes" / "M0_reference"

#: The M0 probe: a four-way whose checked-in program has a permissive left
#: (`research/M0_reference_scenario.md` SS4). Built by T0.2, committed.
PROBE_NET = REPO_ROOT / "spikes" / "M0_reference" / "conflict_probe" / "probe.net.xml"

#: RESCO's `cologne1` (GPLv3): cloned into the main checkout, gitignored, symlinked
#: into worktrees, never copied into the repository (T1.3 Amendment A6).
COLOGNE1_NET = (
    REPO_ROOT
    / "spikes"
    / "M0_prior_art"
    / "RESCO"
    / "resco_benchmark"
    / "environments"
    / "cologne1"
    / "cologne1.net.xml"
)


@pytest.fixture(scope="session")
def cologne1_net() -> Path:
    if not COLOGNE1_NET.exists():
        pytest.skip(
            f"RESCO's cologne1 is not cloned at {COLOGNE1_NET.parent} (GPLv3, gitignored; "
            f"see spikes/M0_prior_art/.gitignore for the clone command)"
        )
    return COLOGNE1_NET


def request_rows(net_file: Path) -> dict[str, list[tuple[str, str]]]:
    """`{junction id: [(foes, response) by request index]}` for every junction with rows."""
    rows: dict[str, list[tuple[str, str]]] = {}
    for junction in ET.parse(net_file).getroot().iter("junction"):
        requests = junction.findall("request")
        if not requests:
            continue
        by_index = {
            int(r.get("index", "-1")): (r.get("foes", ""), r.get("response", "")) for r in requests
        }
        assert sorted(by_index) == list(range(len(requests))), junction.get("id")
        rows[junction.get("id", "")] = [by_index[i] for i in range(len(requests))]
    return rows


def foe_bit(bits: str, link: int) -> bool:
    """Bit `link` of a `foes`/`response` string, which runs right to left (D-023)."""
    return bits[len(bits) - 1 - link] == "1"


@pytest.fixture(scope="session")
def reference_net(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The M0 reference net, built into a temporary directory.

    Built here rather than in `spikes/M0_reference/` so this session never races
    `tests/backend/conftest.py`, which builds it in place.
    """
    out = tmp_path_factory.mktemp("reference") / "reference.net.xml"
    subprocess.run(
        [
            sumolib.checkBinary("netconvert"),
            "--node-files",
            str(REFERENCE_DIR / "reference.nod.xml"),
            "--edge-files",
            str(REFERENCE_DIR / "reference.edg.xml"),
            "--connection-files",
            str(REFERENCE_DIR / "reference.con.xml"),
            "--tllogic-files",
            str(REFERENCE_DIR / "reference.tll.xml"),
            "--output-file",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


@dataclass(frozen=True)
class RawNet:
    """What a net file contains, read with `xml.etree` alone."""

    lanes: list[str]
    junctions: dict[str, str]  # id -> type
    normal_connections: list[tuple[str, str]]  # (from lane, to lane)
    internal_connections: list[tuple[str, str]]
    link_index: dict[tuple[str, str], int]  # controlled normal connection -> linkIndex


def raw_net(net_file: Path) -> RawNet:
    root = ET.parse(net_file).getroot()
    lanes = [lane.get("id", "") for edge in root.iter("edge") for lane in edge.iter("lane")]
    junctions = {j.get("id", ""): j.get("type", "") for j in root.iter("junction")}
    normal: list[tuple[str, str]] = []
    internal: list[tuple[str, str]] = []
    link_index: dict[tuple[str, str], int] = {}
    for c in root.iter("connection"):
        lanes_of = (f"{c.get('from')}_{c.get('fromLane')}", f"{c.get('to')}_{c.get('toLane')}")
        if c.get("from", "").startswith(":"):
            internal.append(lanes_of)
            continue
        normal.append(lanes_of)
        if c.get("linkIndex") is not None:
            link_index[lanes_of] = int(c.get("linkIndex", "-1"))
    return RawNet(lanes, junctions, normal, internal, link_index)


def load_ids(path: Path) -> SumoIds:
    """Read the `<stem>.ids.json` mapping `build()` emits."""
    raw = json.loads(path.read_text())
    return SumoIds(
        lanes=tuple(raw["lanes"]),
        edges=tuple(raw["edges"]),
        junctions=tuple(raw["junctions"]),
        intersections=tuple(raw["intersections"]),
        connections=tuple((a, b) for a, b in raw["connections"]),
    )


TIMING = SignalTiming(min_green_s=10.0, max_green_s=60.0, yellow_s=3.0, all_red_s=2.0)
S, L, R = TurnDirection.THROUGH, TurnDirection.LEFT, TurnDirection.RIGHT

#: The default four-way with the textbook protected plan: each axis's through and
#: right turns, then its left turns.
FOUR_WAY = IntersectionSpec(
    phases=[
        PhaseSpec(green=[(0, S), (0, R), (2, S), (2, R)]),
        PhaseSpec(green=[(0, L), (2, L)]),
        PhaseSpec(green=[(1, S), (1, R), (3, S), (3, R)]),
        PhaseSpec(green=[(1, L), (3, L)]),
    ],
    timing=TIMING,
)

#: Three approaches at 0, 120 and 240 degrees: each has a right and a left turn and
#: no through movement. Each approach is served alone.
T_JUNCTION = IntersectionSpec(
    approaches=3,
    phases=[PhaseSpec(green=[(k, R), (k, L)]) for k in range(3)],
    timing=TIMING,
)


@dataclass(frozen=True)
class Built:
    net: Path
    network: Network
    ids: SumoIds
    spec: IntersectionSpec


def _build(spec: IntersectionSpec, out_dir: Path) -> Built:
    net, network = build(spec, out_dir)
    return Built(net, network, load_ids(out_dir / f"{NET_STEM}{IDS_SUFFIX}"), spec)


@pytest.fixture(scope="session")
def four_way(tmp_path_factory: pytest.TempPathFactory) -> Built:
    return _build(FOUR_WAY, tmp_path_factory.mktemp("four_way"))


@pytest.fixture(scope="session")
def t_junction(tmp_path_factory: pytest.TempPathFactory) -> Built:
    return _build(T_JUNCTION, tmp_path_factory.mktemp("t_junction"))


@pytest.fixture(scope="session", params=["four_way", "t_junction"])
def generated(request: pytest.FixtureRequest) -> Built:
    built: Built = request.getfixturevalue(request.param)
    return built


def assert_round_trip(network: Network, ids: SumoIds, net_file: Path) -> None:
    """Every SUMO lane and connection appears exactly once, by count and by ID.

    Connections are counted as Amendment A2 defines them: a canonical
    `LaneConnection` is a SUMO connection between two normal lanes; a SUMO
    connection *out of* an internal lane is represented by that internal lane,
    which must exist as a canonical lane with no successors.
    """
    raw = raw_net(net_file)

    # Lanes: all of them, internal included, in sorted order; once each.
    assert len(network.lanes) == len(raw.lanes) == len(set(raw.lanes))
    assert ids.lanes == tuple(sorted(raw.lanes))
    assert [int(lane.id) for lane in network.lanes] == list(range(len(raw.lanes)))
    for lane in network.lanes:
        assert ids.lanes[lane.id].rsplit("_", 1)[0] == ids.edges[lane.edge]

    # Connections between normal lanes: once each.
    assert len(network.connections) == len(raw.normal_connections)
    assert sorted(ids.connections) == sorted(raw.normal_connections)
    assert len(set(ids.connections)) == len(ids.connections)
    for connection in network.connections:
        assert (ids.lanes[connection.from_lane], ids.lanes[connection.to_lane]) == (
            ids.connections[connection.id]
        )

    # Connections out of internal lanes: represented by the internal lane.
    lanes = {ids.lanes[lane.id]: lane for lane in network.lanes}
    for from_lane, _ in raw.internal_connections:
        assert from_lane.startswith(":")
        assert lanes[from_lane].successors == ()

    # Junctions: every non-internal SUMO junction, sorted.
    assert ids.junctions == tuple(sorted(j for j, t in raw.junctions.items() if t != "internal"))

    # The display: position i is the connection SUMO numbers linkIndex i.
    (intersection,) = network.signalized_intersections
    assert len(intersection.controlled_connections) == len(raw.link_index)
    for position, connection_id in enumerate(intersection.controlled_connections):
        assert raw.link_index[ids.connections[connection_id]] == position
