"""Metrics, validity checks and run phases: one definition, one implementation.

`07_EXPERIMENT_METHODOLOGY.md` SS2.5: a metric recomputed anywhere else is a
review defect. Per `06_ARCHITECTURE.md` SS10 this package depends on
`traffic_lab.domain` only -- it reads `TrueState` every step and `TripRecord`s
at run end, and never the backend that produced them.
"""

from __future__ import annotations

from traffic_lab.metrics.accumulator import AGGREGATE, MetricAccumulator, MetricResult
from traffic_lab.metrics.mser import WarmupEstimate, estimate_warmup, mser5, running_average
from traffic_lab.metrics.phases import MeasurementWindow, RunPhase
from traffic_lab.metrics.trips import TripMetrics
from traffic_lab.metrics.validity import (
    INSERTION_LOSS_THRESHOLD,
    InvalidityCause,
    TripAccountingError,
    Validity,
)

__all__ = [
    "AGGREGATE",
    "INSERTION_LOSS_THRESHOLD",
    "InvalidityCause",
    "MeasurementWindow",
    "MetricAccumulator",
    "MetricResult",
    "RunPhase",
    "TripAccountingError",
    "TripMetrics",
    "Validity",
    "WarmupEstimate",
    "estimate_warmup",
    "mser5",
    "running_average",
]
