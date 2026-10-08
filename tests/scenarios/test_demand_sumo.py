"""Realised demand, verified against SUMO's tripinfo (T1.5 acceptance criteria 3-5).

Every scenario runs `build_routes()`' file through the `sumo` binary for 12 h of
demand plus a 15-minute drain under the generated four-way's static protected
plan, at level 0.1: the plan serves it with flat delay on two and three lanes.
(Level 0.15 does not: on two lanes it offers more than `tests/generated_scenario.py`'s
measured 1762 veh/h capacity, and with the earlier held-green saturation flow the
delay already grew from 191 s to 949 s over the run.)

Counting is done in tripinfo, never in the route file: every vehicle scheduled
before the cutoff must appear there (`analysed_trips`), so a vehicle SUMO
dropped fails the test instead of skewing a fraction. Tolerances are four
binomial (or Poisson) standard errors -- a false failure about once in 16,000 --
with at least ~3,000 trips behind each.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.generated_scenario import FOUR_WAY, Built, build_intersection
from tests.scenarios.demand_support import (
    SPLIT,
    RouteEntry,
    Trip,
    analysed_trips,
    approaches,
    edge,
    four_source_spec,
    lane_length_m,
    read_routes,
    read_trips,
    run_sumo,
)
from traffic_lab.domain.demand import DemandSpec
from traffic_lab.domain.network import TurnDirection
from traffic_lab.scenarios.demand import approach_saturation_flow_vph, build_routes

LEVEL = 0.1
CUTOFF_S = 12 * 3600.0
DRAIN_S = 900.0
#: Flow is counted from here to the cutoff, after the network has filled.
FLOW_WINDOW_S = (600.0, CUTOFF_S)
SEED = 11

APPROACH_ATTRITION = ("approach_0_in", 0.2)
EXIT_ATTRITION = ("approach_2_out", 0.3)
MID_LINK_SOURCE = ("approach_1_in", 50.0)


@dataclass(frozen=True)
class Run:
    built: Built
    spec: DemandSpec
    routes: dict[str, RouteEntry]
    trips: list[Trip]  # tripinfo of every vehicle scheduled before the cutoff


def _run(built: Built, spec: DemandSpec, tmp: Path) -> Run:
    routes_file = build_routes(
        built.net, built.network, built.ids, spec, SEED, tmp / "demand", end_s=CUTOFF_S
    )
    tripinfo = tmp / "tripinfo.xml"
    run_sumo(built.net, routes_file, tripinfo, CUTOFF_S + DRAIN_S)
    routes = read_routes(routes_file)
    trips = analysed_trips(routes, read_trips(tripinfo), CUTOFF_S)
    return Run(built, spec, {r.id: r for r in routes}, trips)


@pytest.fixture(scope="module")
def plain_two_lane(four_way: Built, tmp_path_factory: pytest.TempPathFactory) -> Run:
    return _run(four_way, four_source_spec(four_way, LEVEL), tmp_path_factory.mktemp("plain2"))


@pytest.fixture(scope="module")
def plain_three_lane(tmp_path_factory: pytest.TempPathFactory) -> Run:
    tmp = tmp_path_factory.mktemp("plain3")
    built = build_intersection(FOUR_WAY.model_copy(update={"lanes_per_approach": 3}), tmp / "net")
    return _run(built, four_source_spec(built, LEVEL), tmp)


@pytest.fixture(scope="module")
def with_attrition(four_way: Built, tmp_path_factory: pytest.TempPathFactory) -> Run:
    spec = four_source_spec(
        four_way,
        LEVEL,
        attrition=dict([APPROACH_ATTRITION, EXIT_ATTRITION]),
        positions=dict([MID_LINK_SOURCE]),
    )
    return _run(four_way, spec, tmp_path_factory.mktemp("attrition"))


def _within_binomial(successes: int, trials: int, p: float) -> bool:
    return abs(successes / trials - p) < 4.0 * math.sqrt(p * (1.0 - p) / trials)


# --- Turning ratios (criterion 4) -------------------------------------------------


@pytest.mark.parametrize("approach", range(4))
def test_the_realised_split_matches_the_turn_ratios(plain_two_lane: Run, approach: int) -> None:
    run = plain_two_lane
    built = run.built
    from_edge = approaches(built)[approach]
    exit_turn = {
        built.ids.edges[m.to_edge]: m.turn
        for m in built.movements
        if built.ids.edges[m.from_edge] == from_edge
    }
    mine = [t for t in run.trips if run.routes[t.id].edges[0] == from_edge]
    assert len(mine) > 3000
    realised = Counter(exit_turn[t.arrival_edge] for t in mine)  # KeyError = wrong exit
    assert set(realised) == set(SPLIT)
    for turn, p in SPLIT.items():
        assert _within_binomial(realised[turn], len(mine), p), (turn, realised, len(mine))


def test_the_configured_ratios_sum_to_one(plain_two_lane: Run) -> None:
    for ratio in plain_two_lane.spec.turn_ratios:
        assert math.isclose(sum(ratio.ratios.values()), 1.0)


# --- Attrition (criterion 3) --------------------------------------------------------


def _mid_link(run: Run, trip: Trip) -> bool:
    return trip.arrival_pos_m < lane_length_m(run.built.net, trip.arrival_edge) - 0.005


def test_approach_attrition_is_realised_at_its_rate(with_attrition: Run) -> None:
    """Vehicles leaving before the stop line: arrived mid-link on the approach they entered."""
    run = with_attrition
    sumo_edge, rate = APPROACH_ATTRITION
    entered = [t for t in run.trips if t.depart_edge == sumo_edge]
    assert len(entered) > 3000
    left_early = [t for t in entered if t.arrival_edge == sumo_edge and _mid_link(run, t)]
    assert _within_binomial(len(left_early), len(entered), rate), (len(left_early), len(entered))


def test_exit_attrition_is_realised_at_its_rate(with_attrition: Run) -> None:
    """Of the vehicles that reached the exit edge, the fraction arriving mid-link on it."""
    run = with_attrition
    sumo_edge, rate = EXIT_ATTRITION
    reached = [t for t in run.trips if t.arrival_edge == sumo_edge]
    assert len(reached) > 2500
    mid_link = [t for t in reached if _mid_link(run, t)]
    assert _within_binomial(len(mid_link), len(reached), rate), (len(mid_link), len(reached))


def test_edges_without_attrition_have_none(with_attrition: Run) -> None:
    run = with_attrition
    for trip in run.trips:
        if trip.arrival_edge not in (APPROACH_ATTRITION[0], EXIT_ATTRITION[0]):
            assert not _mid_link(run, trip), trip


def test_tripinfo_arrivals_are_where_the_route_file_put_them(with_attrition: Run) -> None:
    """Each locally destined vehicle arrives on its route's last edge at its declared
    `arrivalPos`; every other vehicle arrives at the end of a sink edge."""
    run = with_attrition
    sinks = {run.built.ids.edges[e] for e in run.spec.sink_edges}
    for trip in run.trips:
        route = run.routes[trip.id]
        assert trip.arrival_edge == route.edges[-1]
        if route.arrival_pos_m is None:
            assert trip.arrival_edge in sinks
            assert trip.arrival_pos_m == lane_length_m(run.built.net, trip.arrival_edge)
        else:
            assert trip.arrival_pos_m == route.arrival_pos_m


def test_mid_link_sources_enter_at_their_position(with_attrition: Run) -> None:
    run = with_attrition
    sumo_edge, position_m = MID_LINK_SOURCE
    entered = [t for t in run.trips if run.routes[t.id].edges[0] == sumo_edge]
    assert len(entered) > 3000
    assert all(t.depart_edge == sumo_edge for t in entered)
    assert all(run.routes[t.id].depart_pos_m == position_m for t in entered)


def test_every_vehicle_is_a_car(with_attrition: Run) -> None:
    assert {t.vtype for t in with_attrition.trips} == {"car"}


# --- Loading across geometries (criterion 5, as amended) -------------------------


def _flow_per_saturation(run: Run) -> tuple[float, int]:
    """(vehicles from all approaches arriving in the flow window per hour / summed
    approach saturation flow, the count behind it)."""
    start_s, end_s = FLOW_WINDOW_S
    count = sum(1 for t in run.trips if start_s <= t.arrival_s < end_s)
    saturation_vph = sum(
        approach_saturation_flow_vph(run.built.network, edge(run.built, e))
        for e in approaches(run.built)
    )
    return count / ((end_s - start_s) / 3600.0) / saturation_vph, count


def test_the_same_level_loads_two_and_three_lanes_alike(
    plain_two_lane: Run, plain_three_lane: Run
) -> None:
    """Amendment A4: the same demand level gives the same realised flow per unit of
    saturation flow on a two-lane and a three-lane approach, within Poisson tolerance."""
    two, n_two = _flow_per_saturation(plain_two_lane)
    three, n_three = _flow_per_saturation(plain_three_lane)
    assert n_three > 1.4 * n_two  # the three-lane approaches really carry 1.5x the vehicles
    for ratio, n in ((two, n_two), (three, n_three)):
        assert abs(ratio - LEVEL) < 4.0 * LEVEL / math.sqrt(n), (ratio, n)
    combined_se = math.hypot(LEVEL / math.sqrt(n_two), LEVEL / math.sqrt(n_three))
    assert abs(two - three) < 4.0 * combined_se, (two, three)


def test_per_approach_saturation_flow_scales_with_lanes(
    plain_two_lane: Run, plain_three_lane: Run
) -> None:
    two = approach_saturation_flow_vph(
        plain_two_lane.built.network, edge(plain_two_lane.built, "approach_0_in")
    )
    three = approach_saturation_flow_vph(
        plain_three_lane.built.network, edge(plain_three_lane.built, "approach_0_in")
    )
    assert math.isclose(three / two, 1.5)


def test_turn_directions_cover_the_split(plain_two_lane: Run) -> None:
    turns = {m.turn for m in plain_two_lane.built.movements}
    assert turns == {TurnDirection.THROUGH, TurnDirection.LEFT, TurnDirection.RIGHT}
