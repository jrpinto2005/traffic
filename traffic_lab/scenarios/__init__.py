"""Scenario generation: SUMO input files and the canonical structures they describe.

`06_ARCHITECTURE.md` SS10: depends on `domain` only. `sumolib` -- offline file
tooling, never a running simulation -- is allowed here (rule 2, clarified
2026-10-07); `traci` and `libsumo` are not.
"""

from __future__ import annotations

from traffic_lab.scenarios.conflicts import NetworkCorrespondenceError
from traffic_lab.scenarios.parse import SumoIds, parse_network
from traffic_lab.scenarios.spec import IntersectionSpec, PhaseSpec

__all__ = [
    "IntersectionSpec",
    "NetworkCorrespondenceError",
    "PhaseSpec",
    "SumoIds",
    "parse_network",
]
