"""MSER-5 (`07_EXPERIMENT_METHODOLOGY.md` SS3.2, T1.8 Amendment A4).

Synthetic series with a transient whose extent is known, an independent
brute-force oracle for the statistic, and the trip-level wrapper on records.
"""

from __future__ import annotations

import numpy as np
import pytest

from traffic_lab.domain.network import LaneId, VehicleType
from traffic_lab.domain.trip import TripExit, TripRecord
from traffic_lab.metrics.mser import (
    MSER_BATCH_SIZE,
    estimate_warmup,
    mser5,
    running_average,
)


def _brute_force_mser5(series: np.ndarray) -> int:
    """The textbook definition, one candidate at a time, as an independent oracle."""
    n = len(series) // MSER_BATCH_SIZE
    batches = [
        float(np.mean(series[i * MSER_BATCH_SIZE : (i + 1) * MSER_BATCH_SIZE])) for i in range(n)
    ]
    best_d, best = 0, float("inf")
    for d in range(n // 2 + 1):
        rest = batches[d:]
        mean = sum(rest) / len(rest)
        value = sum((y - mean) ** 2 for y in rest) / len(rest) ** 2
        if value < best:
            best_d, best = d, value
    return best_d * MSER_BATCH_SIZE


def test_a_step_transient_is_cut_exactly_where_it_ends() -> None:
    rng = np.random.default_rng(1)
    series = np.concatenate([np.full(100, 60.0), 20.0 + rng.normal(0.0, 2.0, 900)])
    assert mser5(series) == 100


@pytest.mark.parametrize("seed", range(10))
def test_a_decaying_transient_is_cut_near_its_end(seed: int) -> None:
    """Bias 40 * exp(-t / 50) over a steady 20 s with unit-variance noise. The
    bias falls below one noise standard deviation at t = 50 ln 40 = 184 and to
    0.1 at t = 300, so a sensible truncation removes most of [0, 184) and stops
    well short of the end."""
    rng = np.random.default_rng(seed)
    t = np.arange(2000)
    series = 20.0 + 40.0 * np.exp(-t / 50.0) + rng.normal(0.0, 1.0, len(t))
    cut = mser5(series)
    assert 120 <= cut <= 400, cut
    assert np.mean(series[cut:]) == pytest.approx(20.0, abs=0.15)


@pytest.mark.parametrize("seed", range(5))
def test_a_stationary_series_loses_little(seed: int) -> None:
    rng = np.random.default_rng(seed)
    assert mser5(rng.normal(20.0, 5.0, 2000)) <= 500


@pytest.mark.parametrize("seed", range(20))
def test_agrees_with_the_brute_force_definition(seed: int) -> None:
    rng = np.random.default_rng(seed)
    series = rng.exponential(30.0, int(rng.integers(10, 400)))
    series[: int(rng.integers(0, 50))] += 50.0
    assert mser5(series) == _brute_force_mser5(series)


def test_too_short_a_series_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 10"):
        mser5(np.arange(9.0))


def test_running_average() -> None:
    assert running_average([2.0, 4.0, 6.0, 0.0]).tolist() == [2.0, 3.0, 4.0, 3.0]


def _finished(arrival_s: float, time_loss_s: float, insertion_delay_s: float) -> TripRecord:
    return TripRecord(
        vehicle_type=VehicleType.CAR,
        scheduled_depart_s=arrival_s - 30.0 - insertion_delay_s,
        depart_s=arrival_s - 30.0,
        insertion_delay_s=insertion_delay_s,
        arrival_s=arrival_s,
        travel_time_s=30.0,
        time_loss_s=time_loss_s,
        waiting_time_s=0.0,
        stops=0,
        depart_lane=LaneId(0),
        arrival_lane=LaneId(1),
        exit=TripExit.SINK,
    )


def test_estimate_warmup_orders_by_arrival_and_reports_a_time() -> None:
    """Records out of arrival order, the first 50 arrivals carrying a large
    insertion delay: the series is per-trip *delay* (timeLoss + departDelay),
    so the transient is visible only if both parts are summed."""
    trips = [_finished(1000.0 + i, 5.0, 0.0) for i in range(949, 49, -1)]
    trips += [_finished(1000.0 + i, 5.0, 100.0) for i in range(50)]
    trips.append(
        TripRecord(  # an unfinished trip is not in the series
            vehicle_type=VehicleType.CAR,
            scheduled_depart_s=0.0,
            depart_s=0.0,
            insertion_delay_s=0.0,
            arrival_s=None,
            travel_time_s=None,
            time_loss_s=1e6,
            waiting_time_s=0.0,
            stops=0,
            depart_lane=LaneId(0),
            arrival_lane=None,
            exit=None,
        )
    )
    estimate = estimate_warmup(trips)
    assert len(estimate.delay_s) == 950
    assert np.all(np.diff(estimate.arrival_s) >= 0)
    assert estimate.truncated_trips == 50
    assert estimate.truncation_s == 1050.0
    assert estimate.running_average_s[-1] == pytest.approx(np.mean(estimate.delay_s))
