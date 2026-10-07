"""The identity estimator: an observation passed through, with no belief added.

The estimator of the oracle arm (`06_ARCHITECTURE.md` SS4.1). It counts what a
sensor reported and adds nothing: no smoothing, no decay, no prior. With the
`OracleSensor` its queue counts therefore equal the true ones exactly, which is
the property that makes the oracle arm a valid control for M3's degraded
sensors. Counting-with-decay is M3's, and D-021 is still open.

D-025's queue definition is applied here to the sensor's own `stationary_s`:
a detection is queued when it has been seen stationary for at least
`QUEUE_MIN_HALTING_S`. The estimator keeps no clock of its own, because one
rebuilt from samples taken every decision interval would miss up to that long of
the halting it is meant to time (D-033).

It accepts **complete** observations only -- every detection placed on a lane,
and on a lane the observation covers, with a stationary time. An estimator that
copes with partial observation has to say how, and that is M3's to decide.
"""

from __future__ import annotations

from traffic_lab.domain.network import LaneId
from traffic_lab.domain.observation import EstimatedState, LaneEstimate, Observation
from traffic_lab.domain.state import QUEUE_MIN_HALTING_S, SignalState


class IdentityEstimator:
    """Stateless: every `update` depends on its arguments alone."""

    def update(
        self, obs: Observation, signals: tuple[SignalState, ...], now_s: float
    ) -> EstimatedState:
        """Count `obs` per covered lane.

        `EstimatedState.time_s` is `now_s`: the instant the belief is for, which
        equals `obs.received_at_s` only when the sensor has zero latency.

        Raises `ValueError` for an incomplete observation: a detection with no
        `lane` or no `stationary_s`, or on a lane outside `obs.observed_lanes`.
        """
        vehicle_counts: dict[LaneId, int] = dict.fromkeys(obs.observed_lanes, 0)
        queue_counts: dict[LaneId, int] = dict.fromkeys(obs.observed_lanes, 0)
        for detection in obs.detections:
            lane = detection.lane
            stationary_s = detection.stationary_s
            if lane is None or stationary_s is None:
                raise ValueError(
                    f"IdentityEstimator accepts complete observations only; detection "
                    f"{detection.track_id!r} has lane={lane!r}, stationary_s={stationary_s!r}"
                )
            if lane not in obs.observed_lanes:
                raise ValueError(
                    f"detection {detection.track_id!r} is on lane {int(lane)}, which the "
                    f"observation does not cover"
                )
            vehicle_counts[lane] += 1
            if stationary_s >= QUEUE_MIN_HALTING_S:
                queue_counts[lane] += 1

        return EstimatedState(
            time_s=now_s,
            lanes=tuple(
                LaneEstimate(
                    lane=lane,
                    queue_count=float(queue_counts[lane]),
                    queue_count_std=0.0,
                    last_observed_s=obs.received_at_s,
                    vehicle_count=float(vehicle_counts[lane]),
                )
                for lane in sorted(obs.observed_lanes)
            ),
            signals=signals,
        )
