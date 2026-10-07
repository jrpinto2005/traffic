"""Shared paths and raw-XML readers for the scenario tests.

The readers here parse net files with `xml.etree` directly, independently of
sumolib and of `traffic_lab.scenarios`, so a test can check the parser against
the file rather than against itself.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

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
