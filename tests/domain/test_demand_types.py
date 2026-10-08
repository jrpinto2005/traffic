"""`05_DOMAIN_MODEL.md` SS6.1: the demand types exist with exactly the specified fields.

Invariants 15-16 are not checked here: they need the network to name the
offending edge, so the demand generator enforces them
(`tests/scenarios/test_demand_validation.py`).
"""

from __future__ import annotations

import dataclasses

import pytest

from traffic_lab.domain.demand import AttritionSpec, DemandSpec, SourceSpec, TurnRatioSpec
from traffic_lab.domain.network import EdgeId, JunctionId, TurnDirection, VehicleType


def test_fields_match_the_domain_model() -> None:
    assert [f.name for f in dataclasses.fields(SourceSpec)] == [
        "edge",
        "position_m",
        "rate_saturation_fraction",
        "type_mix",
    ]
    assert [f.name for f in dataclasses.fields(TurnRatioSpec)] == [
        "junction",
        "from_edge",
        "ratios",
    ]
    assert [f.name for f in dataclasses.fields(AttritionSpec)] == ["edge", "rate"]
    assert [f.name for f in dataclasses.fields(DemandSpec)] == [
        "sources",
        "turn_ratios",
        "attrition",
        "sink_edges",
        "seed_stream",
    ]


def test_demand_is_seeded_from_the_demand_stream_by_default() -> None:
    spec = DemandSpec(sources=(), turn_ratios=(), attrition=(), sink_edges=frozenset())
    assert spec.seed_stream == "demand"


def test_specs_are_frozen() -> None:
    source = SourceSpec(EdgeId(0), None, 0.1, {VehicleType.CAR: 1.0})
    ratio = TurnRatioSpec(JunctionId(0), EdgeId(0), {TurnDirection.THROUGH: 1.0})
    attrition = AttritionSpec(EdgeId(0), 0.1)
    for spec, field in ((source, "edge"), (ratio, "junction"), (attrition, "rate")):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(spec, field, 1)
