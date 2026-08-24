"""Shared fixtures for the backend tests.

Every test here drives a real SUMO. There is no mock simulator and there will
not be one: the whole point of `traffic_lab.backend` is that it is the seam
against SUMO, so a test against a fake would assert our beliefs about SUMO
rather than SUMO's behaviour -- which is exactly the failure mode
`research/M0_sumo_semantics.md` SS3 records ("the first pass answered most of
SS1 from documentation").

The scenario is the M0 reference intersection (`research/M0_reference_scenario.md`):
four approaches, two lanes each, one static two-phase program, constant demand.
Its `reference.net.xml` is gitignored and built on demand by `netconvert`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sumolib import checkBinary

from traffic_lab.backend import BackendConfig

REFERENCE_DIR = Path(__file__).resolve().parents[2] / "spikes" / "M0_reference"
REFERENCE_NET = REFERENCE_DIR / "reference.net.xml"
REFERENCE_ROUTES = REFERENCE_DIR / "reference.rou.xml"


@pytest.fixture(scope="session")
def reference_net() -> Path:
    """Path to the built reference network, building it first if necessary."""
    if not REFERENCE_NET.exists():
        subprocess.run(
            [
                checkBinary("netconvert"),
                "--node-files",
                str(REFERENCE_DIR / "reference.nod.xml"),
                "--edge-files",
                str(REFERENCE_DIR / "reference.edg.xml"),
                "--connection-files",
                str(REFERENCE_DIR / "reference.con.xml"),
                "--tllogic-files",
                str(REFERENCE_DIR / "reference.tll.xml"),
                "--output-file",
                str(REFERENCE_NET),
            ],
            check=True,
            cwd=REFERENCE_DIR,
            capture_output=True,
        )
    return REFERENCE_NET


@pytest.fixture
def reference_routes() -> Path:
    return REFERENCE_ROUTES


def make_config(**overrides: object) -> BackendConfig:
    """A valid `BackendConfig`, so each test states only what it is about.

    `gridlock_steps` is large enough that the reference scenario never trips it
    accidentally; the gridlock tests set their own.
    """
    fields: dict[str, object] = {
        "seed": 42,
        "decision_interval_s": 5.0,
        "gridlock_steps": 300,
    }
    fields.update(overrides)
    return BackendConfig(**fields)  # type: ignore[arg-type]
