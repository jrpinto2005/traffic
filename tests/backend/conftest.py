"""Shared fixtures for the backend tests.

Every test here drives a real SUMO. There is no mock simulator and there will
not be one: the whole point of `traffic_lab.backend` is that it is the seam
against SUMO, so a test against a fake would assert our beliefs about SUMO
rather than SUMO's behaviour -- which is exactly the failure mode
`research/M0_sumo_semantics.md` SS3 records ("the first pass answered most of
SS1 from documentation").

The scenario is a T1.3-generated intersection (T1.14 Amendment A1): the default
four-approach spec with the protected four-phase plan, its static program, and
one flow per movement (`tests/generated_scenario.py`). Every geometry-specific
value a test needs -- the traffic light, the length of a display, edge IDs,
timings -- is read from it rather than written down.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.generated_scenario import FOUR_WAY, Built, build_intersection, one_flow_per_movement
from traffic_lab.backend import BackendConfig
from traffic_lab.domain.network import Network

#: The demand runs this long; no test drives the scenario further.
DEMAND_END_S = 3600.0


@dataclass(frozen=True)
class Scenario:
    """A generated intersection with its demand: what `SumoBackend.start()` takes."""

    built: Built
    routes: Path

    @property
    def net(self) -> Path:
        return self.built.net

    @property
    def network(self) -> Network:
        return self.built.network


@pytest.fixture(scope="session")
def scenario(tmp_path_factory: pytest.TempPathFactory) -> Scenario:
    """The net path, the route path and the canonical `Network`, built once per session."""
    out = tmp_path_factory.mktemp("generated_scenario")
    built = build_intersection(FOUR_WAY, out)
    routes = one_flow_per_movement(built, out / "demand.rou.xml", DEMAND_END_S)
    return Scenario(built, routes)


def make_config(**overrides: object) -> BackendConfig:
    """A valid `BackendConfig`, so each test states only what it is about.

    `gridlock_steps` is large enough that the scenario never trips it
    accidentally; the gridlock tests set their own.
    """
    fields: dict[str, object] = {
        "seed": 42,
        "decision_interval_s": 5.0,
        "gridlock_steps": 300,
    }
    fields.update(overrides)
    return BackendConfig(**fields)  # type: ignore[arg-type]
