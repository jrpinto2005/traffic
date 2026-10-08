"""MSER-5 warm-up truncation and the running average (`07_EXPERIMENT_METHODOLOGY.md` SS3.2).

**MSER-5** (White, 1997; Franklin & White, 2008): batch the series into
non-overlapping means of 5 observations, `Y_1 .. Y_n` (a trailing incomplete
batch is dropped), and for each candidate number of deleted batches `d` compute

    MSER(d) = sum_{j > d} (Y_j - mean(Y_{d+1..n}))^2 / (n - d)^2

-- the squared standard error of the remaining mean, up to a constant. The
truncation is the `d` minimising it, returned as `5 d` observations.

The search covers `d <= n // 2`, the standard restriction: as `n - d` shrinks the
statistic is computed from a handful of batches and tends to a spurious minimum
at the very end of the series, so a truncation is only accepted from the first
half (Franklin & White; Hoad, Robinson & Davies, 2010). Ties go to the smallest
`d`.

Applied, per T1.8 Amendment A4, to the primary metric's series: per-trip delay
(`TripColumns.delay_s`) in order of arrival, with the truncation reported as a
simulated time. The running average is for the visual confirmation SS3.2
requires; it is a series to plot, not a metric.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from traffic_lab.domain.trip import TripRecord
from traffic_lab.metrics.columns import TripColumns

#: MSER-*5*: the batch size is the name of the method, not a tuning parameter.
MSER_BATCH_SIZE = 5

#: Fewer batches than this leave nothing to choose between.
_MIN_BATCHES = 2


def mser5(series: npt.ArrayLike) -> int:
    """How many leading observations of `series` to delete. Raises `ValueError`
    on a series too short to batch into at least two batches of five."""
    values = np.asarray(series, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError(f"MSER-5 takes a 1-D series, got shape {values.shape}")
    n = len(values) // MSER_BATCH_SIZE
    if n < _MIN_BATCHES:
        raise ValueError(
            f"MSER-5 needs at least {_MIN_BATCHES * MSER_BATCH_SIZE} observations, got "
            f"{len(values)}"
        )
    batches = values[: n * MSER_BATCH_SIZE].reshape(n, MSER_BATCH_SIZE).mean(axis=1)

    # Suffix sums give every candidate's statistic in one pass: for the batches
    # after d, sum of squares about their mean = S2 - S1^2 / k with k = n - d.
    suffix_sum = np.cumsum(batches[::-1])[::-1]
    suffix_sum_sq = np.cumsum(batches[::-1] ** 2)[::-1]
    remaining = np.arange(n, 0, -1, dtype=np.float64)
    sum_sq_dev = np.maximum(suffix_sum_sq - suffix_sum**2 / remaining, 0.0)
    statistic = sum_sq_dev / remaining**2

    candidates = n // 2 + 1  # d = 0 .. n // 2
    best = int(np.argmin(statistic[:candidates]))
    return best * MSER_BATCH_SIZE


def running_average(series: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Element i is the mean of the first i + 1 observations."""
    values = np.asarray(series, dtype=np.float64)
    return np.cumsum(values) / np.arange(1, len(values) + 1)


@dataclass(frozen=True, slots=True)
class WarmupEstimate:
    """MSER-5 applied to one run's per-trip delay, in order of arrival."""

    truncation_s: float  # arrival time of the first trip MSER-5 keeps
    truncated_trips: int  # leading trips MSER-5 deletes
    arrival_s: npt.NDArray[np.float64]  # the series' time axis
    delay_s: npt.NDArray[np.float64]  # the series: timeLoss + departDelay per trip
    running_average_s: npt.NDArray[np.float64]  # for the SS3.2 visual check


def estimate_warmup(trips: Sequence[TripRecord]) -> WarmupEstimate:
    """MSER-5 over every finished trip of a run, in order of arrival.

    Trips arriving in the same step keep their tripinfo order (a stable sort).
    The whole run is used, not the measurement window: this is how the window's
    start is chosen.
    """
    return warmup_from_columns(TripColumns.from_trips(trips))


def warmup_from_columns(columns: TripColumns) -> WarmupEstimate:
    """`estimate_warmup` on trips already in columns."""
    finished = columns.finished
    arrival_s = columns.arrival_s[finished]
    delay_s = columns.delay_s[finished]
    order = np.argsort(arrival_s, kind="stable")
    arrival_s, delay_s = arrival_s[order], delay_s[order]

    truncated = mser5(delay_s)
    return WarmupEstimate(
        truncation_s=float(arrival_s[truncated]),
        truncated_trips=truncated,
        arrival_s=arrival_s,
        delay_s=delay_s,
        running_average_s=running_average(delay_s),
    )
