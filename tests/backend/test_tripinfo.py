"""`read_trips` against real SUMO tripinfo (D-035, T1.8 Amendment A1-A2, rulings E1-E3).

Every expectation here was first measured, not read from documentation
(`research/M0_sumo_semantics.md` SS3): finished, unfinished, undeparted and
mid-link trips, insertions at standstill, and scheduled departures recovered
for both departed and undeparted vehicles against flows whose schedule is
known in advance. Both transports, because tripinfo is written by SUMO itself
and the two must not differ in what it says.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from tests.backend.conftest import Scenario, make_config
from tests.generated_scenario import OVERLOAD_PERIOD_S, Built, one_flow_per_movement
from tests.trip_scenarios import (
    BLOCKER_STOP_S,
    FLOOD_BEGIN_S,
    FLOOD_END_S,
    MID_LINK_ARRIVAL_POS_M,
    SEMANTICS_END_S,
    Run,
    run,
    semantics_routes,
    through_movements,
    tripinfo_ids,
)
from traffic_lab.backend import TransportName
from traffic_lab.backend.tripinfo import TripinfoError, read_trips
from traffic_lab.domain.network import VehicleType
from traffic_lab.domain.trip import TripExit, TripRecord


@pytest.fixture(scope="module", params=["traci", "libsumo"])
def semantics(
    request: pytest.FixtureRequest, scenario: Scenario, tmp_path_factory: pytest.TempPathFactory
) -> Run:
    transport: TransportName = request.param
    out = tmp_path_factory.mktemp(f"semantics_{transport}")
    routes = semantics_routes(scenario.built, out / "semantics.rou.xml")
    tripinfo = out / "tripinfo.xml"
    return run(
        scenario.built,
        routes,
        tripinfo,
        SEMANTICS_END_S,
        make_config(transport=transport, tripinfo_path=tripinfo),
    )


def _by_id(semantics: Run) -> dict[str, TripRecord]:
    trips = read_trips(semantics.tripinfo, semantics.backend.index, end_s=semantics.end_s)
    ids = tripinfo_ids(semantics.tripinfo)
    assert len(ids) == len(trips)
    return dict(zip(ids, trips, strict=True))


def _out_lanes(built: Built) -> tuple[int, int]:
    """The two lanes of the outbound edge the single-edge trips run on."""
    out_edge = through_movements(built)[1].to_edge
    (edge,) = (e for e in built.network.edges if e.id == out_edge)
    lane0, lane1 = edge.lanes
    return int(lane0), int(lane1)


def test_a_free_flow_sink_trip(semantics: Run, scenario: Scenario) -> None:
    trip = _by_id(semantics)["sink_free"]
    lane0, _ = _out_lanes(scenario.built)
    assert trip.vehicle_type is VehicleType.CAR
    assert trip.scheduled_depart_s == trip.depart_s == 100.0
    assert trip.insertion_delay_s == 0.0
    # 189.6 m lane, entering at 5.1 m (one car length plus 0.1), at 13.89 m/s:
    # 184.5 / 13.89 = 13.3 s, so it leaves during the 14th step.
    assert trip.arrival_s == 114.0
    assert trip.travel_time_s == 14.0
    assert trip.time_loss_s == 0.0
    assert (trip.waiting_time_s, trip.stops) == (0.0, 0)
    assert trip.depart_lane == trip.arrival_lane == lane0
    assert trip.exit is TripExit.SINK


def test_a_mid_link_trip_is_classified_from_its_arrival_position(
    semantics: Run, scenario: Scenario
) -> None:
    trip = _by_id(semantics)["mid_free"]
    _, lane1 = _out_lanes(scenario.built)
    assert trip.vehicle_type is VehicleType.MOTORCYCLE
    assert trip.exit is TripExit.MID_LINK
    assert trip.arrival_lane == lane1
    # 100 m - 2.3 m entry position = 97.7 m at 13.89 m/s: 7.03 s, the 8th step.
    assert trip.travel_time_s == 8.0
    assert trip.time_loss_s == 0.0
    assert semantics.backend.index.lane_lengths_m[lane1] > MID_LINK_ARRIVAL_POS_M


def test_an_insertion_at_standstill_that_drives_away_is_not_a_stop(semantics: Run) -> None:
    """07 SS2.1 as amended: `waitingCount` does not count the insertion step."""
    trip = _by_id(semantics)["stand_free"]
    assert trip.stops == 0
    assert trip.waiting_time_s == 0.0
    # Accelerating from rest is time lost, though never below 0.1 m/s after insertion.
    assert trip.time_loss_s > 0.0


def test_an_insertion_at_standstill_still_halted_a_step_later_is_one_stop(semantics: Run) -> None:
    """Ruling E1: pinned, not corrected. The vehicle never moves before it halts --
    it is held behind a stopped car from insertion until the stop ends -- and
    SUMO's `waitingCount` still counts one stop."""
    trip = _by_id(semantics)["stand_held"]
    assert trip.stops == 1
    # Inserted at t=5, released when the blockers' 40 s stop (begun at t=2) ends:
    # halted at every move step from t=6 to t=41, 36 in all. `waitingTime` leaves
    # the insertion step out; `timeLoss` includes it (37 s + the acceleration loss).
    assert BLOCKER_STOP_S == 40
    assert trip.waiting_time_s == 36.0
    assert trip.time_loss_s > 37.0
    assert trip.exit is TripExit.SINK


def test_an_unfinished_trip(semantics: Run) -> None:
    trip = _by_id(semantics)["late"]
    assert trip.depart_s == SEMANTICS_END_S - 10
    assert trip.depart_lane is not None
    assert trip.inserted and not trip.finished
    assert (trip.arrival_s, trip.travel_time_s, trip.arrival_lane, trip.exit) == (
        None,
        None,
        None,
        None,
    )


def test_scheduled_departure_of_departed_and_undeparted_trips(semantics: Run) -> None:
    """Ruling E2: `depart - departDelay` for departed trips, `end_s - departDelay`
    for undeparted ones, against the flood's known schedule `flood.n` at
    `FLOOD_BEGIN_S + n`."""
    flood = {k: t for k, t in _by_id(semantics).items() if k.startswith("flood.")}
    assert len(flood) == FLOOD_END_S - FLOOD_BEGIN_S
    for vehicle_id, trip in flood.items():
        assert trip.scheduled_depart_s == FLOOD_BEGIN_S + int(vehicle_id.split(".")[1])

    undeparted = [t for t in flood.values() if not t.inserted]
    delayed = [t for t in flood.values() if t.inserted and t.insertion_delay_s > 0]
    assert undeparted and delayed  # both branches really were exercised
    for trip in undeparted:
        assert trip.insertion_delay_s == semantics.end_s - trip.scheduled_depart_s
        assert (trip.depart_s, trip.depart_lane) == (None, None)
        assert (trip.time_loss_s, trip.waiting_time_s, trip.stops) == (0.0, 0.0, 0)


def test_pending_insertions_match_the_recovered_schedule_at_every_step(semantics: Run) -> None:
    """The scheduled departures explain SUMO's pending list exactly.

    A vehicle due at `s` is attempted in the step that starts at `s`; one inserted
    at `d` first appears in the state at `d + 1`. So at the state stamped `T`,
    the pending list holds exactly the trips scheduled before `T` that had not
    departed before `T`. This is what D-008's insertion loss divides by.
    """
    trips = read_trips(semantics.tripinfo, semantics.backend.index, end_s=semantics.end_s)
    for state in semantics.states:
        t = state.time_s
        due_not_in = sum(
            1
            for trip in trips
            if trip.scheduled_depart_s < t and (trip.depart_s is None or trip.depart_s >= t)
        )
        assert state.counters.insertion_failures == due_not_in, t


def test_every_record_is_one_of_the_three_states(semantics: Run) -> None:
    for trip in read_trips(semantics.tripinfo, semantics.backend.index, end_s=semantics.end_s):
        if not trip.inserted:
            assert trip.depart_lane is None and not trip.finished
        if trip.finished:
            assert trip.inserted
            assert trip.exit is not None and trip.arrival_lane is not None
            assert trip.travel_time_s == pytest.approx(trip.arrival_s - trip.depart_s)  # type: ignore[operator]
        else:
            assert (trip.travel_time_s, trip.arrival_lane, trip.exit) == (None, None, None)


def test_a_trip_of_a_type_outside_the_map_raises(semantics: Run) -> None:
    index = dataclasses.replace(semantics.backend.index, vehicle_types={})
    with pytest.raises(TripinfoError, match="vType"):
        read_trips(semantics.tripinfo, index, end_s=semantics.end_s)


def test_a_wrong_end_time_raises_instead_of_shifting_the_schedule(semantics: Run) -> None:
    with pytest.raises(TripinfoError, match="end_s"):
        read_trips(semantics.tripinfo, semantics.backend.index, end_s=semantics.end_s - 1)


def test_scheduled_departures_on_the_overloaded_fixture(scenario: Scenario, tmp_path: Path) -> None:
    """Ruling E2 again, at scale: the shared intersection with every movement
    oversupplied, flow `mK.n` scheduled at `n * OVERLOAD_PERIOD_S`."""
    routes = one_flow_per_movement(
        scenario.built, tmp_path / "overload.rou.xml", 3600.0, period_s=OVERLOAD_PERIOD_S
    )
    tripinfo = tmp_path / "tripinfo.xml"
    result = run(
        scenario.built,
        routes,
        tripinfo,
        900,
        make_config(transport="libsumo", tripinfo_path=tripinfo),
    )
    trips = read_trips(tripinfo, result.backend.index, end_s=result.end_s)
    ids = tripinfo_ids(tripinfo)
    for vehicle_id, trip in zip(ids, trips, strict=True):
        assert trip.scheduled_depart_s == int(vehicle_id.split(".")[1]) * OVERLOAD_PERIOD_S
        assert trip.vehicle_type is VehicleType.CAR  # DEFAULT_VEHTYPE
    states = {"finished": 0, "unfinished": 0, "undeparted": 0}
    for trip in trips:
        key = "finished" if trip.finished else "unfinished" if trip.inserted else "undeparted"
        states[key] += 1
    assert min(states.values()) > 50, states
    # Every arrival on this demand runs off the end of its lane.
    assert all(t.exit is TripExit.SINK for t in trips if t.finished)
