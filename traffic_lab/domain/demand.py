"""Demand specification: `05_DOMAIN_MODEL.md` SS6.1, the owner's open-boundary model (D-022).

Vehicles are **not conserved** inside the study area: they enter from Poisson
sources, propagate by turning ratios, and leave at a boundary sink or mid-link,
having reached a local destination (attrition). Configuration, not state: the
scenario layer turns a `DemandSpec` into SUMO route files
(`traffic_lab.scenarios.demand.build_routes`), which is also where invariants
15-16 of SS8 are enforced -- these frozen dataclasses cannot see the network
they refer to, so they cannot name an offending edge by its SUMO ID.

Rates are a **fraction of the receiving approach's saturation flow** (D-022),
saturation flow being calibrated in SUMO (D-037), so "demand level 0.15" means
the same loading on a two-lane and a three-lane approach.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from traffic_lab.domain.network import EdgeId, JunctionId, TurnDirection, VehicleType


@dataclass(frozen=True, slots=True)
class SourceSpec:
    edge: EdgeId
    position_m: float | None  # None = edge start (boundary); else a mid-link source
    rate_saturation_fraction: float  # of the receiving approach's saturation flow
    type_mix: Mapping[VehicleType, float]  # share of the source's vehicles per type


@dataclass(frozen=True, slots=True)
class TurnRatioSpec:
    junction: JunctionId
    from_edge: EdgeId
    ratios: Mapping[TurnDirection, float]  # sums to 1.0 (SS8 invariant 15)


@dataclass(frozen=True, slots=True)
class AttritionSpec:
    edge: EdgeId
    rate: float  # fraction of through-flow locally destined, in [0, 1) (SS8 invariant 16)


@dataclass(frozen=True, slots=True)
class DemandSpec:
    sources: tuple[SourceSpec, ...]
    turn_ratios: tuple[TurnRatioSpec, ...]
    attrition: tuple[AttritionSpec, ...]
    sink_edges: frozenset[EdgeId]
    seed_stream: str = "demand"
