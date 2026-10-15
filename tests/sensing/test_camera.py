"""Tests for CameraConfig, CameraSensor, and MultiCameraSensor (D-005, D-021, T3.1)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import cast

from tests.generated_scenario import FOUR_WAY, build_intersection
from traffic_lab.domain.network import LaneId, SensorId, VehicleId, VehicleType
from traffic_lab.domain.state import TrueState, VehicleState
from traffic_lab.sensing.camera import CameraConfig, CameraSensor, MultiCameraSensor
from traffic_lab.sensing.model import SensorModel


def _make_mock_state(time_s: float, vehicles: list[VehicleState]) -> TrueState:
    mock_obj = type(
        "MockTrueState",
        (),
        {
            "time_s": time_s,
            "vehicles": tuple(vehicles),
            "lanes": (),
            "signals": (),
            "counters": None,
        },
    )()
    return cast(TrueState, mock_obj)


def _make_vehicle(
    veh_id: int, x: float, y: float, speed: float = 10.0, lane: int = 16
) -> VehicleState:
    return VehicleState(
        id=VehicleId(veh_id),
        type=VehicleType("car"),
        lane=LaneId(lane),
        position_xy=(x, y),
        speed_mps=speed,
        position_on_lane_m=50.0,
        time_loss_s=0.0,
        waiting_time_s=0.0,
        stop_count=0,
        is_halting=False,
        halting_since_s=None,
    )


def test_camera_implements_sensor_model(tmp_path: Path) -> None:
    built = build_intersection(FOUR_WAY, tmp_path / "scen")
    config = CameraConfig(
        sensor_id=SensorId(1),
        position_xy=(200.0, 200.0),
        heading_rad=0.0,
        fov_rad=math.pi / 2.0,
        range_m=100.0,
    )
    cam = CameraSensor(config, built.network)
    assert isinstance(cam, SensorModel)


def test_camera_fov_and_range_filtering(tmp_path: Path) -> None:
    built = build_intersection(FOUR_WAY, tmp_path / "scen")
    # Camera at (200, 200) pointing East (heading=0.0) with 90-degree FOV (+/- 45 deg)
    config = CameraConfig(
        sensor_id=SensorId(1),
        position_xy=(200.0, 200.0),
        heading_rad=0.0,
        fov_rad=math.pi / 2.0,
        range_m=50.0,
        p_det_0=1.0,  # 100% detection inside FOV
        pos_noise_std=0.0,
        speed_noise_std=0.0,
    )
    cam = CameraSensor(config, built.network)

    v_inside = _make_vehicle(1, 230.0, 200.0)  # 30m East (inside FOV)
    v_too_far = _make_vehicle(2, 280.0, 200.0)  # 80m East (outside range 50m)
    v_behind = _make_vehicle(3, 170.0, 200.0)  # 30m West (behind camera)
    v_side = _make_vehicle(4, 200.0, 240.0)  # 40m North (outside 45-deg half-FOV)

    state = _make_mock_state(10.0, [v_inside, v_too_far, v_behind, v_side])
    obs = cam.observe(state, 10.0)

    detected_ids = [d.track_id for d in obs.detections]
    assert detected_ids == [1]
    assert obs.detections[0].position_xy == (230.0, 200.0)


def test_camera_distance_dependent_dropout(tmp_path: Path) -> None:
    built = build_intersection(FOUR_WAY, tmp_path / "scen")
    # Camera with 100m range and p_det_0=1.0
    config = CameraConfig(
        sensor_id=SensorId(1),
        position_xy=(200.0, 200.0),
        heading_rad=0.0,
        fov_rad=math.pi / 2.0,
        range_m=100.0,
        p_det_0=1.0,
        pos_noise_std=0.0,
        speed_noise_std=0.0,
        seed=123,
    )
    cam = CameraSensor(config, built.network)

    # Near vehicle (10m) vs far vehicle (90m)
    v_near = _make_vehicle(1, 210.0, 200.0)
    v_far = _make_vehicle(2, 290.0, 200.0)

    near_detected = 0
    far_detected = 0
    trials = 500

    for _ in range(trials):
        state = _make_mock_state(1.0, [v_near, v_far])
        obs = cam.observe(state, 1.0)
        ids = {d.track_id for d in obs.detections}
        if 1 in ids:
            near_detected += 1
        if 2 in ids:
            far_detected += 1

    # Theoretical: P(10m) = 1.0 * (1 - 10/200) = 0.95
    # Theoretical: P(90m) = 1.0 * (1 - 90/200) = 0.55
    near_rate = near_detected / trials
    far_rate = far_detected / trials

    assert abs(near_rate - 0.95) < 0.05
    assert abs(far_rate - 0.55) < 0.05
    assert near_rate > far_rate + 0.3


def test_camera_latency_and_noise(tmp_path: Path) -> None:
    built = build_intersection(FOUR_WAY, tmp_path / "scen")
    config = CameraConfig(
        sensor_id=SensorId(1),
        position_xy=(200.0, 200.0),
        heading_rad=0.0,
        fov_rad=2.0 * math.pi,  # Omni
        range_m=100.0,
        p_det_0=1.0,
        pos_noise_std=2.0,
        speed_noise_std=1.0,
        latency_s=1.5,
        seed=42,
    )
    cam = CameraSensor(config, built.network)
    v = _make_vehicle(1, 220.0, 200.0, speed=12.0)
    state = _make_mock_state(15.0, [v])

    obs = cam.observe(state, 15.0)
    assert obs.received_at_s == 16.5  # 15.0 + 1.5 latency
    assert len(obs.detections) == 1
    det = obs.detections[0]
    assert det.observed_at_s == 15.0
    # Noisy position is not exactly 220.0, 200.0 but within ~3 sigmas
    assert abs(det.position_xy[0] - 220.0) < 6.0
    assert abs(det.speed_mps - 12.0) < 3.0


def test_multi_camera_sensor_fusion_and_dedup(tmp_path: Path) -> None:
    built = build_intersection(FOUR_WAY, tmp_path / "scen")
    # Camera 1 pointing East, Camera 2 pointing North
    cam1 = CameraSensor(
        CameraConfig(
            sensor_id=SensorId(1),
            position_xy=(200.0, 200.0),
            heading_rad=0.0,
            fov_rad=math.pi / 2.0,
            range_m=50.0,
            p_det_0=1.0,
            pos_noise_std=0.0,
            speed_noise_std=0.0,
            monitored_lanes=frozenset([LaneId(16), LaneId(17)]),
        ),
        built.network,
    )
    cam2 = CameraSensor(
        CameraConfig(
            sensor_id=SensorId(2),
            position_xy=(200.0, 200.0),
            heading_rad=math.pi / 2.0,
            fov_rad=math.pi / 2.0,
            range_m=50.0,
            p_det_0=1.0,
            pos_noise_std=0.0,
            speed_noise_std=0.0,
            monitored_lanes=frozenset([LaneId(20), LaneId(21)]),
        ),
        built.network,
    )
    multi = MultiCameraSensor((cam1, cam2))
    assert isinstance(multi, SensorModel)
    assert multi._observed_lanes == frozenset([LaneId(16), LaneId(17), LaneId(20), LaneId(21)])

    # Vehicle in both cameras' FOV (e.g. at 45 degrees: 220, 220)
    v_shared = _make_vehicle(1, 220.0, 220.0)
    # Vehicle only in cam1 (East: 230, 200)
    v_cam1 = _make_vehicle(2, 230.0, 200.0)
    # Vehicle only in cam2 (North: 200, 230)
    v_cam2 = _make_vehicle(3, 200.0, 230.0)

    state = _make_mock_state(5.0, [v_shared, v_cam1, v_cam2])
    obs = multi.observe(state, 5.0)

    # v_shared should only be included once despite being seen by both cameras
    track_ids = [d.track_id for d in obs.detections if d.track_id is not None]
    assert sorted(track_ids) == [1, 2, 3]
