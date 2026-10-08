"""`MetricAccumulator` end to end on real SUMO runs (T1.8 Amendment A5).

Each run drives the generated intersection, feeds every projected state to the
accumulator, then reads SUMO's tripinfo with `read_trips` and finalizes. The
expected values are recomputed in the tests from the tripinfo XML itself,
independently of `read_trips` and `TripColumns`.
"""

from __future__ import annotations

import dataclasses
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import polars as pl
import pytest

from tests.backend.conftest import Scenario, make_config
from tests.generated_scenario import DEMAND_PERIOD_S, OVERLOAD_PERIOD_S, one_flow_per_movement
from tests.trip_scenarios import Run, mixed_type_flows, run
from traffic_lab.backend.tripinfo import read_trips
from traffic_lab.domain.network import VehicleType
from traffic_lab.metrics import (
    AGGREGATE,
    InvalidityCause,
    MeasurementWindow,
    MetricAccumulator,
    MetricResult,
    TripAccountingError,
)
from traffic_lab.metrics.columns import TripColumns

#: Mixed-type run: 5 minutes of warm-up, 10 of measurement, 5 of cool-down.
WINDOW = MeasurementWindow(start_s=300.0, end_s=900.0)
END_S = 1200


def _finalize(
    result_run: Run, scenario: Scenario, window: MeasurementWindow, *, teleports: int = 0
) -> MetricResult:
    """Accumulate every state of `result_run`, then finalize on its tripinfo.

    `teleports` overwrites the last state's teleport counter, to induce one."""
    accumulator = MetricAccumulator(window, scenario.network)
    states = list(result_run.states)
    if teleports:
        last = states[-1]
        states[-1] = dataclasses.replace(
            last, counters=dataclasses.replace(last.counters, teleports=teleports)
        )
    for state in states:
        accumulator.accumulate(state)
    trips = read_trips(result_run.tripinfo, result_run.backend.index, end_s=result_run.end_s)
    return accumulator.finalize(trips, snapshot_mismatch=False)


@pytest.fixture(scope="module")
def mixed(scenario: Scenario, tmp_path_factory: pytest.TempPathFactory) -> Run:
    out = tmp_path_factory.mktemp("mixed")
    routes = mixed_type_flows(
        scenario.built, out / "mixed.rou.xml", END_S, period_s=DEMAND_PERIOD_S
    )
    tripinfo = out / "tripinfo.xml"
    return run(
        scenario.built,
        routes,
        tripinfo,
        END_S,
        make_config(transport="libsumo", tripinfo_path=tripinfo),
    )


@pytest.fixture(scope="module")
def mixed_result(mixed: Run, scenario: Scenario) -> MetricResult:
    return _finalize(mixed, scenario, WINDOW)


def _xml(path: Path) -> list[dict[str, str]]:
    return [dict(e.attrib) for e in ET.parse(path).getroot().iter("tripinfo")]


def _completed_in_window(path: Path, vtype: str | None = None) -> list[dict[str, str]]:
    return [
        e
        for e in _xml(path)
        if WINDOW.start_s <= float(e["arrival"]) < WINDOW.end_s
        and (vtype is None or e["vType"] == vtype)
    ]


def test_delay_and_its_parts_are_tripinfos_exactly(mixed: Run, mixed_result: MetricResult) -> None:
    """A5: delay = timeLoss + departDelay, both parts equal to tripinfo's."""
    completed = _completed_in_window(mixed.tripinfo)
    assert len(completed) == mixed_result.aggregate.completed > 100
    time_loss = [float(e["timeLoss"]) for e in completed]
    depart_delay = [float(e["departDelay"]) for e in completed]
    n = len(completed)
    assert mixed_result.aggregate.mean_time_loss_s == pytest.approx(sum(time_loss) / n, rel=1e-12)
    assert mixed_result.aggregate.mean_insertion_delay_s == pytest.approx(
        sum(depart_delay) / n, rel=1e-12
    )
    assert mixed_result.aggregate.mean_delay_s == pytest.approx(
        sum(t + d for t, d in zip(time_loss, depart_delay, strict=True)) / n, rel=1e-12
    )
    assert sum(depart_delay) > 0  # the second part is really exercised


def test_per_trip_delay_columns_equal_tripinfo(mixed: Run) -> None:
    trips = read_trips(mixed.tripinfo, mixed.backend.index, end_s=mixed.end_s)
    columns = TripColumns.from_trips(trips)
    xml = _xml(mixed.tripinfo)
    assert columns.time_loss_s.tolist() == [float(e["timeLoss"]) for e in xml]
    assert columns.insertion_delay_s.tolist() == [float(e["departDelay"]) for e in xml]
    assert columns.delay_s.tolist() == [float(e["timeLoss"]) + float(e["departDelay"]) for e in xml]


@pytest.mark.parametrize(
    ("vtype", "vehicle_type"), [("car", VehicleType.CAR), ("moto", VehicleType.MOTORCYCLE)]
)
def test_every_trip_metric_per_vehicle_type(
    mixed: Run,
    mixed_result: MetricResult,
    scenario: Scenario,
    vtype: str,
    vehicle_type: VehicleType,
) -> None:
    """A5 and 07 SS2.4: each type's metrics are its own trips' and nobody else's."""
    metrics = mixed_result.by_type[vehicle_type]
    completed = _completed_in_window(mixed.tripinfo, vtype)
    n = len(completed)
    assert metrics.completed == n > 50

    def mean(attr: str) -> float:
        return sum(float(e[attr]) for e in completed) / n

    assert metrics.mean_time_loss_s == pytest.approx(mean("timeLoss"), rel=1e-12)
    assert metrics.mean_insertion_delay_s == pytest.approx(mean("departDelay"), rel=1e-12)
    assert metrics.mean_travel_time_s == pytest.approx(mean("duration"), rel=1e-12)
    assert metrics.mean_waiting_time_s == pytest.approx(mean("waitingTime"), rel=1e-12)
    assert metrics.mean_stops == pytest.approx(mean("waitingCount"), rel=1e-12)
    assert metrics.throughput_veh_per_h == pytest.approx(n / (WINDOW.duration_s / 3600.0))

    # Approach delay: mean time loss by the edge of the departure lane.
    by_edge: dict[int, list[float]] = {}
    for e in completed:
        edge = scenario.built.ids.edges.index(e["departLane"].rsplit("_", 1)[0])
        by_edge.setdefault(edge, []).append(float(e["timeLoss"]))
    expected = {edge: sum(v) / len(v) for edge, v in by_edge.items()}
    assert {int(k): v for k, v in metrics.approach_delay_s.items()} == pytest.approx(
        expected, rel=1e-12
    )


def test_aggregate_is_the_sum_of_the_types(mixed_result: MetricResult) -> None:
    car = mixed_result.by_type[VehicleType.CAR]
    moto = mixed_result.by_type[VehicleType.MOTORCYCLE]
    total = mixed_result.aggregate
    for field in ("completed", "arrived_at_sink", "arrived_mid_link", "still_in_network"):
        assert getattr(total, field) == getattr(car, field) + getattr(moto, field), field
    assert total.total_time_loss_veh_h == pytest.approx(
        car.total_time_loss_veh_h + moto.total_time_loss_veh_h
    )
    assert total.throughput_veh_per_h == pytest.approx(
        car.throughput_veh_per_h + moto.throughput_veh_per_h
    )
    assert total.mean_delay_s == pytest.approx(
        (car.mean_delay_s * car.completed + moto.mean_delay_s * moto.completed)  # type: ignore[operator]
        / total.completed
    )
    # Only the motorcycles of every third movement leave mid-link.
    assert car.arrived_mid_link == 0 < moto.arrived_mid_link
    assert total.completion_rate == pytest.approx(
        total.completed / (total.completed + total.still_in_network)
    )


def test_three_way_accounting_at_window_close(mixed: Run, mixed_result: MetricResult) -> None:
    """D-022: completed in the window and still in the network at its end, from
    two sources -- tripinfo and the TrueState at `end_s` -- partition the trips
    that entered before the window closed and did not finish before it opened."""
    (closing,) = [s for s in mixed.states if s.time_s == WINDOW.end_s]
    assert mixed_result.aggregate.still_in_network == len(closing.vehicles)

    in_network_by_tripinfo = 0
    for e in _xml(mixed.tripinfo):
        depart, arrival = float(e["depart"]), float(e["arrival"])
        if 0 <= depart < WINDOW.end_s and (arrival < 0 or arrival >= WINDOW.end_s):
            in_network_by_tripinfo += 1
    assert in_network_by_tripinfo == len(closing.vehicles)

    total_loss_s = sum(float(e["timeLoss"]) for e in _completed_in_window(mixed.tripinfo)) + sum(
        v.time_loss_s for v in closing.vehicles
    )
    assert mixed_result.aggregate.total_time_loss_veh_h == pytest.approx(total_loss_s / 3600.0)


def test_the_sink_mid_link_split_is_tripinfos(mixed: Run, mixed_result: MetricResult) -> None:
    """Every finished motorcycle of a flow with `arrivalPos` left mid-link, every
    other finished trip at a sink; the backend's kinematic estimate is reported
    beside it, not used."""
    xml = _xml(mixed.tripinfo)
    expected_mid = sum(
        1
        for e in xml
        if float(e["arrival"]) >= 0
        and e["id"].startswith("m")
        and int(e["id"][1:].split(".")[0]) % 3 == 0
    )
    assert mixed_result.mid_link_arrivals_tripinfo == expected_mid > 0
    assert mixed_result.mid_link_arrivals_kinematic == mixed.states[-1].counters.arrived_mid_link


def test_a_valid_two_type_run(mixed_result: MetricResult) -> None:
    assert mixed_result.validity.valid, mixed_result.validity
    assert mixed_result.mser5_truncation_s is not None


def test_invariant_14_holds_on_the_real_run_and_a_fabricated_mismatch_raises(
    mixed: Run, scenario: Scenario
) -> None:
    trips = read_trips(mixed.tripinfo, mixed.backend.index, end_s=mixed.end_s)
    last = mixed.states[-1].counters
    inserted = sum(1 for t in trips if t.inserted)
    assert last.arrived_at_sink + last.arrived_mid_link + last.still_in_network == inserted

    accumulator = MetricAccumulator(WINDOW, scenario.network)
    for state in mixed.states:
        accumulator.accumulate(state)
    dropped_one_inserted = [t for t in trips if t.inserted][1:] + [
        t for t in trips if not t.inserted
    ]
    with pytest.raises(TripAccountingError, match="invariant 14"):
        accumulator.finalize(dropped_one_inserted, snapshot_mismatch=False)


def test_an_induced_teleport_is_flagged_and_the_run_still_written(
    mixed: Run, mixed_result: MetricResult, scenario: Scenario, tmp_path: Path
) -> None:
    """The backend forbids real teleports (D-008), so the counters are constructed."""
    result = _finalize(mixed, scenario, WINDOW, teleports=1)
    assert not result.validity.valid
    assert result.validity.causes == (InvalidityCause.TELEPORT,)
    # Every metric is still there, identical to the valid run's.
    assert result.aggregate == mixed_result.aggregate
    assert result.by_type == mixed_result.by_type

    path = tmp_path / "run.parquet"
    pl.DataFrame([result.to_row()]).write_parquet(path)
    back = pl.read_parquet(path).row(0, named=True)
    assert back["valid"] is False
    assert back["invalid_causes"] == "teleport"
    assert back["teleports"] == 1
    assert back[f"{AGGREGATE}.mean_delay_s"] == mixed_result.aggregate.mean_delay_s
    assert back["motorcycle.completed"] == mixed_result.by_type[VehicleType.MOTORCYCLE].completed


def test_an_overloaded_run_is_invalid_by_insertion_loss(scenario: Scenario, tmp_path: Path) -> None:
    routes = one_flow_per_movement(
        scenario.built, tmp_path / "overload.rou.xml", 3600.0, period_s=OVERLOAD_PERIOD_S
    )
    tripinfo = tmp_path / "tripinfo.xml"
    overload = run(
        scenario.built,
        routes,
        tripinfo,
        700,
        make_config(transport="libsumo", tripinfo_path=tripinfo),
    )
    result = _finalize(overload, scenario, MeasurementWindow(start_s=300.0, end_s=600.0))
    assert InvalidityCause.INSERTION_LOSS in result.validity.causes
    assert result.validity.insertion_loss > 0.01
    # 12 flows, one vehicle every 7 s each, scheduled in [300, 600).
    assert result.validity.due_in_window == sum(
        1 for k in range(0, 3600 // 7 + 1) if 300 <= 7 * k < 600
    ) * len(scenario.built.movements)
    # The numerator, recounted from the XML: flow `mK.n` is due at 7 n; waiting at
    # least 30 s at the close means due at or before 570, and still outside means
    # never inserted or inserted at or after 600.
    not_inserted = sum(
        1
        for e in _xml(tripinfo)
        if 7 * int(e["id"].split(".")[1]) <= 570
        and (float(e["depart"]) < 0 or float(e["depart"]) >= 600)
    )
    assert result.validity.not_inserted_at_window_close == not_inserted > 0


def test_a_burst_of_pending_vehicles_at_the_close_does_not_invalidate_the_shared_fixture(
    scenario: Scenario, tmp_path: Path
) -> None:
    """D-008 as refined 2026-10-07, prompted by the case this reproduces.

    The shared demand releases all twelve flows in the same second, so for one
    step SUMO's pending list holds four vehicles that are a second late. A
    window closing on that step had 4 of ~190 due vehicles "not inserted" under
    the pending-snapshot rule -- 2 %, invalid -- although demand is served
    (65 % of capacity). Counted as vehicles that have waited 30 s, it is 0.
    """
    tripinfo = tmp_path / "tripinfo.xml"
    shared = run(
        scenario.built,
        scenario.routes,
        tripinfo,
        1300,
        make_config(transport="libsumo", tripinfo_path=tripinfo),
    )
    burst = next(s for s in shared.states if s.time_s >= 900 and s.counters.insertion_failures == 4)
    window = MeasurementWindow(start_s=burst.time_s - 600.0, end_s=burst.time_s)
    result = _finalize(shared, scenario, window)

    pending_rule = burst.counters.insertion_failures / result.validity.due_in_window
    assert pending_rule > 0.01  # what the snapshot rule would have said
    assert result.validity.not_inserted_at_window_close == 0
    assert result.validity.valid, result.validity


def test_a_trickle_run_is_valid(scenario: Scenario, tmp_path: Path) -> None:
    routes = one_flow_per_movement(
        scenario.built, tmp_path / "trickle.rou.xml", 3600.0, period_s=120.0
    )
    tripinfo = tmp_path / "tripinfo.xml"
    trickle = run(
        scenario.built,
        routes,
        tripinfo,
        1000,
        make_config(transport="libsumo", tripinfo_path=tripinfo),
    )
    result = _finalize(trickle, scenario, MeasurementWindow(start_s=300.0, end_s=900.0))
    assert result.validity.valid, result.validity
    assert result.validity.insertion_loss == 0.0
    assert result.validity.due_in_window > 0
    assert math.isclose(result.aggregate.completion_rate or 0.0, 1.0, abs_tol=0.2)


def test_the_kinematic_split_disagreement_is_reported_on_the_shared_fixture(
    scenario: Scenario, tmp_path: Path
) -> None:
    """The shared demand declares no `arrivalPos`, so tripinfo reports no mid-link
    arrival; the backend's kinematic classifier is known to drift (T1.14 found 5
    of 1124 by 3600 s). The result carries both counts, and tripinfo's is the
    one the metrics use."""
    tripinfo = tmp_path / "tripinfo.xml"
    shared = run(
        scenario.built,
        scenario.routes,
        tripinfo,
        1200,
        make_config(transport="libsumo", tripinfo_path=tripinfo),
    )
    result = _finalize(shared, scenario, MeasurementWindow(start_s=300.0, end_s=1100.0))
    assert result.mid_link_arrivals_tripinfo == 0
    assert result.aggregate.arrived_mid_link == 0
    assert result.mid_link_arrivals_kinematic == shared.states[-1].counters.arrived_mid_link
    assert result.validity.valid, result.validity
