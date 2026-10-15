"""Parametric camera sensor model (D-005, D-017, D-021, M3).

Implements the `SensorModel` protocol: transforms ground-truth `TrueState` into
an imperfect `Observation` stream. Models optical field of view, distance-dependent
detection probability, Gaussian measurement noise, and latency.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from traffic_lab.domain.network import LaneId, Network, SensorId
from traffic_lab.domain.observation import Detection, Observation
from traffic_lab.domain.state import TrueState


@dataclass(frozen=True, slots=True)
class CameraConfig:
    """Configuration for a parametric traffic camera."""

    sensor_id: SensorId
    position_xy: tuple[float, float]
    heading_rad: float
    fov_rad: float
    range_m: float
    p_det_0: float = 0.95
    pos_noise_std: float = 0.5
    speed_noise_std: float = 0.3
    latency_s: float = 0.0
    seed: int = 42
    monitored_lanes: frozenset[LaneId] | None = None


class CameraSensor:
    """Parametric camera sensor implementing the `SensorModel` protocol."""

    def __init__(self, config: CameraConfig, network: Network) -> None:
        self.config = config
        self.network = network
        self._rng = random.Random(config.seed)
        self._lane_length_m: dict[LaneId, float] = {
            lane.id: lane.length_m for lane in network.lanes
        }

        # If monitored lanes not explicitly set, determine lanes within range
        if config.monitored_lanes is not None:
            self._monitored_lanes = config.monitored_lanes
        else:
            self._monitored_lanes = frozenset(lane.id for lane in network.lanes)

    @property
    def monitored_lanes(self) -> frozenset[LaneId]:
        return self._monitored_lanes

    def observe(self, state: TrueState, now_s: float) -> Observation:
        """Sample `state` into an imperfect `Observation` with noise and dropouts."""
        detections: list[Detection] = []
        cx, cy = self.config.position_xy
        heading = self.config.heading_rad
        half_fov = self.config.fov_rad / 2.0
        range_m = self.config.range_m
        p_det_0 = self.config.p_det_0
        pos_std = self.config.pos_noise_std
        speed_std = self.config.speed_noise_std

        for vehicle in state.vehicles:
            vx, vy = vehicle.position_xy
            dx = vx - cx
            dy = vy - cy
            dist = math.hypot(dx, dy)

            # 1. Range check
            if dist > range_m:
                continue

            # 2. Field of view check (if not omnidirectional)
            if self.config.fov_rad < 2.0 * math.pi - 1e-4:
                angle_to_veh = math.atan2(dy, dx)
                angle_diff = (angle_to_veh - heading + math.pi) % (2.0 * math.pi) - math.pi
                if abs(angle_diff) > half_fov:
                    continue

            # 3. Distance-dependent detection probability
            p_det = p_det_0 * max(0.0, 1.0 - dist / (2.0 * range_m))
            if self._rng.random() > p_det:
                continue  # Missed detection (false negative)

            # 4. Measurement noise
            noisy_x = vx + self._rng.gauss(0.0, pos_std)
            noisy_y = vy + self._rng.gauss(0.0, pos_std)
            noisy_speed = max(0.0, vehicle.speed_mps + self._rng.gauss(0.0, speed_std))

            # Continuous stationary time
            stationary_s = (
                0.0
                if vehicle.halting_since_s is None
                else max(0.0, state.time_s - vehicle.halting_since_s)
            )

            dist_to_stop = (
                max(0.0, self._lane_length_m[vehicle.lane] - vehicle.position_on_lane_m)
                if vehicle.lane in self._lane_length_m
                else None
            )

            det = Detection(
                sensor=self.config.sensor_id,
                observed_at_s=state.time_s,
                position_xy=(round(noisy_x, 3), round(noisy_y, 3)),
                position_cov=(round(pos_std**2, 4), round(pos_std**2, 4), 0.0),
                speed_mps=round(noisy_speed, 3),
                speed_std=round(speed_std, 3),
                vehicle_class=vehicle.type,
                class_confidence=round(max(0.5, min(1.0, 1.0 - 0.2 * (dist / range_m))), 3),
                track_id=int(vehicle.id),
                lane=vehicle.lane,
                stationary_s=round(stationary_s, 3),
                distance_to_stop_m=round(dist_to_stop, 3) if dist_to_stop is not None else None,
            )
            detections.append(det)

        received_at_s = round(state.time_s + self.config.latency_s, 3)
        return Observation(
            received_at_s=received_at_s,
            detections=tuple(detections),
            observed_lanes=self._monitored_lanes,
        )


class MultiCameraSensor:
    """Network camera system combining multiple cameras into one unified observation."""

    def __init__(self, cameras: tuple[CameraSensor, ...]) -> None:
        if not cameras:
            raise ValueError("MultiCameraSensor requires at least one camera")
        self.cameras = cameras
        all_lanes: set[LaneId] = set()
        for c in cameras:
            all_lanes.update(c.monitored_lanes)
        self._observed_lanes = frozenset(all_lanes)

    def observe(self, state: TrueState, now_s: float) -> Observation:
        """Observe state across all cameras, fusing detections and unioning lanes."""
        seen_tracks: set[int] = set()
        fused_detections: list[Detection] = []
        max_received_at = now_s

        for cam in self.cameras:
            obs = cam.observe(state, now_s)
            max_received_at = max(max_received_at, obs.received_at_s)
            for det in obs.detections:
                if det.track_id is not None and det.track_id in seen_tracks:
                    continue  # Deduplicate overlapping camera views
                if det.track_id is not None:
                    seen_tracks.add(det.track_id)
                fused_detections.append(det)

        return Observation(
            received_at_s=max_received_at,
            detections=tuple(fused_detections),
            observed_lanes=self._observed_lanes,
        )
