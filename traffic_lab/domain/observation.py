"""Observation and estimate: `05_DOMAIN_MODEL.md` SS4.

Implements D-005's reserved extension point for a real perception pipeline:
`Observation` is a stream of detections with uncertainty, and nothing in it
references how it was produced -- no field mentions field of view, range, or
detection probability. `Detection.lane` and `Detection.stationary_s` (D-033) are
ordinary outputs of traffic video analytics -- lane-level presence and dwell
time -- so a pixel pipeline fills them from its own map-matching and tracker,
and a camera model may get either wrong.

`EstimatedState` is the only state a controller ever sees; per
`06_ARCHITECTURE.md` SS4.1, the oracle is a sensor, not a bypass, so even a
"perfect" arm's controller reads this module's types, never `TrueState`.
"""

from __future__ import annotations

from dataclasses import dataclass

from traffic_lab.domain.network import LaneId, SensorId, VehicleType
from traffic_lab.domain.state import SignalState


@dataclass(frozen=True, slots=True)
class Detection:
    sensor: SensorId
    observed_at_s: float  # when the sensor sampled
    position_xy: tuple[float, float]  # estimated
    position_cov: tuple[float, float, float]  # xx, yy, xy
    speed_mps: float  # estimated
    speed_std: float
    vehicle_class: VehicleType
    class_confidence: float  # [0, 1]
    track_id: int | None  # None if the sensor does not track
    lane: LaneId | None  # the sensor's lane assignment; None if it cannot assign (D-033)
    stationary_s: float | None  # time seen stationary, 0.0 while moving; None if untracked (D-033)
    distance_to_stop_m: float | None  # front to the end of its lane; None if unknown (D-036)


@dataclass(frozen=True, slots=True)
class Observation:
    received_at_s: float  # observed_at_s + latency
    detections: tuple[Detection, ...]
    observed_lanes: frozenset[LaneId]  # coverage: which lanes this observation speaks about


@dataclass(frozen=True, slots=True)
class LaneEstimate:
    lane: LaneId
    queue_count: float  # non-integer: it is an estimate
    queue_count_std: float
    last_observed_s: float | None  # None = never observed
    vehicle_count: float
    zone_count: float  # vehicles within the lane's stop-line detection zone (D-036)


@dataclass(frozen=True, slots=True)
class EstimatedState:
    time_s: float
    lanes: tuple[LaneEstimate, ...]
    signals: tuple[SignalState, ...]  # the controller knows its own signals exactly
