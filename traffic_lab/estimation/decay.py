"""Counting-with-decay state estimator (D-005, D-021, M3).

Implements the `Estimator` protocol: turns imperfect `Observation` streams into
an `EstimatedState` belief. Tracks per-lane vehicle and queue counts, updating
actively observed lanes and exponentially decaying unobserved/occluded lanes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from traffic_lab.domain.network import LaneId, Network
from traffic_lab.domain.observation import EstimatedState, LaneEstimate, Observation
from traffic_lab.domain.state import QUEUE_MIN_HALTING_S, SignalState


@dataclass(frozen=True, slots=True)
class DecayEstimatorConfig:
    """Configuration for counting-with-decay estimator."""

    half_life_s: float = 15.0  # Time for unobserved counts to halve
    zone_s: float = 2.0  # Stop-line detection zone duration
    default_queue_std: float = 1.0  # Base uncertainty when decaying


class CountingWithDecayEstimator:
    """State estimator maintaining per-lane tracking and exponential decay memory."""

    def __init__(self, network: Network, config: DecayEstimatorConfig | None = None) -> None:
        self.network = network
        self.config = config or DecayEstimatorConfig()
        self._decay_rate = math.log(2.0) / max(0.1, self.config.half_life_s)

        self._zone_length_m: dict[LaneId, float] = {
            lane.id: self.config.zone_s * lane.speed_limit_mps for lane in network.lanes
        }

        # Memory state per lane
        all_lanes = tuple(lane.id for lane in network.lanes)
        self._vehicle_counts: dict[LaneId, float] = {lane_id: 0.0 for lane_id in all_lanes}
        self._queue_counts: dict[LaneId, float] = {lane_id: 0.0 for lane_id in all_lanes}
        self._zone_counts: dict[LaneId, float] = {lane_id: 0.0 for lane_id in all_lanes}
        self._last_observed_s: dict[LaneId, float | None] = {lane_id: None for lane_id in all_lanes}

    def update(
        self, obs: Observation, signals: tuple[SignalState, ...], now_s: float
    ) -> EstimatedState:
        """Fold `obs` into a continuous network belief at simulated time `now_s`."""
        obs_lanes = obs.observed_lanes

        # Count detections directly on observed lanes
        fresh_veh: dict[LaneId, int] = dict.fromkeys(obs_lanes, 0)
        fresh_queue: dict[LaneId, int] = dict.fromkeys(obs_lanes, 0)
        fresh_zone: dict[LaneId, int] = dict.fromkeys(obs_lanes, 0)

        for det in obs.detections:
            lane = det.lane
            if lane is not None and lane in obs_lanes:
                fresh_veh[lane] += 1
                if (
                    det.distance_to_stop_m is not None
                    and 0.0 <= det.distance_to_stop_m <= self._zone_length_m.get(lane, 0.0)
                ):
                    fresh_zone[lane] += 1
                if det.stationary_s is not None and det.stationary_s >= QUEUE_MIN_HALTING_S:
                    fresh_queue[lane] += 1

        lane_estimates: list[LaneEstimate] = []
        for lane_id in sorted(self._vehicle_counts.keys()):
            last_obs: float | None
            if lane_id in obs_lanes:
                # Direct update from incoming observation
                veh_cnt = float(fresh_veh[lane_id])
                queue_cnt = float(fresh_queue[lane_id])
                zone_cnt = float(fresh_zone[lane_id])
                last_obs = obs.received_at_s
                queue_std = 0.0

                self._vehicle_counts[lane_id] = veh_cnt
                self._queue_counts[lane_id] = queue_cnt
                self._zone_counts[lane_id] = zone_cnt
                self._last_observed_s[lane_id] = last_obs
            else:
                # Unobserved lane: exponential decay from previous estimate
                last_obs = self._last_observed_s[lane_id]
                if last_obs is None:
                    veh_cnt = 0.0
                    queue_cnt = 0.0
                    zone_cnt = 0.0
                    queue_std = self.config.default_queue_std
                else:
                    dt = max(0.0, now_s - last_obs)
                    decay = math.exp(-self._decay_rate * dt)
                    veh_cnt = self._vehicle_counts[lane_id] * decay
                    queue_cnt = self._queue_counts[lane_id] * decay
                    zone_cnt = self._zone_counts[lane_id] * decay
                    queue_std = self.config.default_queue_std * (1.0 - decay)

            lane_estimates.append(
                LaneEstimate(
                    lane=lane_id,
                    queue_count=round(queue_cnt, 4),
                    queue_count_std=round(queue_std, 4),
                    last_observed_s=last_obs,
                    vehicle_count=round(veh_cnt, 4),
                    zone_count=round(zone_cnt, 4),
                )
            )

        return EstimatedState(
            time_s=now_s,
            lanes=tuple(lane_estimates),
            signals=signals,
        )
