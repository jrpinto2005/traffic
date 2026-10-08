"""The route file `build_routes` writes, read back with `xml.etree`: determinism,
format, order, scheduled arrivals, and attrition as written.

The Kolmogorov-Smirnov test runs on the **scheduled** departures (Amendment A4)
of each source: about 11,800 per source at level 0.15 over the 24 h horizon, so
the >= 10,000 floor is asserted, and the same statistic is shown to reject a
rate 10 % off, so the test cannot pass for want of power.
"""

from __future__ import annotations

import logging
import math
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pytest

from tests.generated_scenario import Built
from tests.scenarios.demand_support import (
    S,
    approaches,
    edge,
    exits,
    four_source_spec,
    read_routes,
)
from traffic_lab.domain.network import VehicleType
from traffic_lab.scenarios.demand import (
    FLOWS_FILE,
    TURNS_FILE,
    build_routes,
    source_rate_veh_per_s,
)
from traffic_lab.scenarios.saturation import per_lane_saturation_flow_vph

#: A derived demand-stream seed above 2**31 - 1, which SUMO's --seed cannot parse
#: directly: `derive_seeds(0)["demand"]`.
LARGE_SEED = 3757552657

#: Kolmogorov's asymptotic critical value at alpha = 0.01: reject if sqrt(n) D > 1.628.
KS_CRITICAL_001 = 1.628


def _build(
    built: Built,
    tmp: Path,
    seed: int,
    *,
    attrition: Mapping[str, float] | None = None,
    positions: Mapping[str, float] | None = None,
) -> Path:
    spec = four_source_spec(built, 0.15, attrition=attrition, positions=positions)
    return build_routes(built.net, built.network, built.ids, spec, seed, tmp)


@pytest.fixture(scope="module")
def routes(four_way: Built, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(
        four_way,
        tmp_path_factory.mktemp("routes"),
        LARGE_SEED,
        attrition={"approach_0_in": 0.2, "approach_2_out": 0.3},
        positions={"approach_1_in": 50.0},
    )


def test_the_same_seed_gives_byte_identical_files(four_way: Built, tmp_path: Path) -> None:
    a = _build(four_way, tmp_path / "a", 7, attrition={"approach_2_out": 0.3})
    b = _build(four_way, tmp_path / "b", 7, attrition={"approach_2_out": 0.3})
    assert a.read_bytes() == b.read_bytes()


def test_different_seeds_give_different_files(four_way: Built, tmp_path: Path) -> None:
    a = _build(four_way, tmp_path / "a", 7)
    b = _build(four_way, tmp_path / "b", 8)
    assert a.read_bytes() != b.read_bytes()


def test_the_seed_reaches_the_attrition_sampler(four_way: Built, tmp_path: Path) -> None:
    """Holding everything else equal, attrition draws follow the seed: the jtrrouter part
    is identical without attrition, so the difference here is the sampler's."""
    a = read_routes(_build(four_way, tmp_path / "a", 7, attrition={"approach_2_out": 0.5}))
    b = read_routes(_build(four_way, tmp_path / "b", 8, attrition={"approach_2_out": 0.5}))
    assert [r.arrival_pos_m for r in a] != [r.arrival_pos_m for r in b]


def test_a_seed_beyond_sumos_int32_is_accepted(routes: Path) -> None:
    assert len(read_routes(routes)) > 0


def test_turns_use_the_modern_edge_relation_format(routes: Path) -> None:
    turns = ET.parse(routes.parent / TURNS_FILE).getroot()
    assert turns.tag == "edgeRelations"
    assert not list(turns.iter("fromEdge")) and not list(turns.iter("toEdge"))
    relations = list(turns.iter("edgeRelation"))
    assert len(relations) == 12  # four approaches x three movements
    assert {r.get("from") for r in relations} == {
        "approach_0_in",
        "approach_1_in",
        "approach_2_in",
        "approach_3_in",
    }


def test_one_vtype_per_vehicle_type_with_its_vclass(routes: Path) -> None:
    vtypes = {v.get("id"): v.get("vClass") for v in ET.parse(routes).getroot().iter("vType")}
    assert vtypes == {"car": "passenger", "motorcycle": "motorcycle"}
    assert {r.type for r in read_routes(routes)} == {VehicleType.CAR.value}


def test_vehicles_are_written_in_departure_order(routes: Path) -> None:
    departs = [r.depart_s for r in read_routes(routes)]
    assert departs == sorted(departs)
    assert len({r.id for r in read_routes(routes)}) == len(departs)


def test_every_route_ends_at_a_sink_or_mid_link(four_way: Built, routes: Path) -> None:
    for r in read_routes(routes):
        if r.arrival_pos_m is None:
            assert len(r.edges) == 2 and r.edges[-1] in exits(four_way)
        else:
            assert r.edges[-1] in ("approach_0_in", "approach_2_out")


def test_mid_link_sources_depart_at_their_position(routes: Path) -> None:
    for r in read_routes(routes):
        assert r.depart_pos_m == (50.0 if r.edges[0] == "approach_1_in" else None)


def test_arrival_positions_lie_strictly_inside_the_edge(four_way: Built, routes: Path) -> None:
    seen = 0
    for r in read_routes(routes):
        if r.arrival_pos_m is None:
            continue
        length = four_way.network.edges[edge(four_way, r.edges[-1])].length_m
        start = (r.depart_pos_m or 0.0) if len(r.edges) == 1 else 0.0
        assert start < r.arrival_pos_m < length
        seen += 1
    assert seen > 1000


def test_scheduled_attrition_matches_the_configured_rates(routes: Path) -> None:
    """In the file; the realised fractions are checked against SUMO's tripinfo in
    `test_demand_sumo.py`."""
    entries = read_routes(routes)
    on_approach = [r for r in entries if r.edges[0] == "approach_0_in"]
    cut = sum(1 for r in on_approach if len(r.edges) == 1)
    _assert_binomial(cut, len(on_approach), 0.2)
    into_exit = [r for r in entries if r.edges[-1] == "approach_2_out"]
    cut = sum(1 for r in into_exit if r.arrival_pos_m is not None)
    _assert_binomial(cut, len(into_exit), 0.3)


def test_the_max_edges_counter_is_logged_when_zero(
    four_way: Built, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="traffic_lab.scenarios.demand"):
        _build(four_way, tmp_path, 7)
    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("jtrrouter max-edges limit: 0 of ") for m in messages), messages


def test_the_flow_rate_is_the_level_times_the_approach_saturation_flow(
    four_way: Built, routes: Path
) -> None:
    flows = ET.parse(routes.parent / FLOWS_FILE).getroot().findall("flow")
    assert len(flows) == 4
    per_lane = per_lane_saturation_flow_vph(VehicleType.CAR, 13.89, S)
    expected = 0.15 * 2 * per_lane / 3600.0
    for flow in flows:
        assert flow.get("period") == f"exp({expected!r})"
    spec = four_source_spec(four_way, 0.15)
    assert source_rate_veh_per_s(four_way.network, spec.sources[0]) == expected


@pytest.mark.parametrize("source", range(4))
def test_scheduled_headways_are_exponential_at_the_configured_rate(
    four_way: Built, routes: Path, source: int
) -> None:
    rate = source_rate_veh_per_s(four_way.network, four_source_spec(four_way, 0.15).sources[source])
    departs = np.array(
        [r.depart_s for r in read_routes(routes) if r.id.startswith(f"source{source}_")]
    )
    headways = np.diff(np.concatenate([[0.0], departs]))
    n = len(headways)
    assert n >= 10_000
    assert math.sqrt(n) * _ks_exponential(headways, rate) < KS_CRITICAL_001
    # Power: the same sample is rejected against a rate 10 % off, either way.
    for wrong in (0.9 * rate, 1.1 * rate):
        assert math.sqrt(n) * _ks_exponential(headways, wrong) > KS_CRITICAL_001
    # The mean headway, within four standard errors of 1 / rate.
    assert abs(headways.mean() - 1.0 / rate) < 4.0 / rate / math.sqrt(n)
    # And the source is the one on its approach.
    assert {r.edges[0] for r in read_routes(routes) if r.id.startswith(f"source{source}_")} == {
        approaches(four_way)[source]
    }


def _ks_exponential(sample: np.ndarray, rate: float) -> float:
    """The two-sided Kolmogorov-Smirnov statistic of `sample` against Exp(rate)."""
    x = np.sort(sample)
    n = len(x)
    cdf = 1.0 - np.exp(-rate * x)
    above = np.arange(1, n + 1) / n - cdf
    below = cdf - np.arange(0, n) / n
    return float(max(above.max(), below.max()))


def _assert_binomial(successes: int, trials: int, p: float) -> None:
    """|observed - p| within four binomial standard errors (two-sided p ~ 6e-5)."""
    assert trials >= 500
    assert abs(successes / trials - p) < 4.0 * math.sqrt(p * (1.0 - p) / trials), (
        successes,
        trials,
        p,
    )
