"""Parametric camera sensor factories for standard network configurations (M3).

Provides top-level sensor factory functions suitable for multiprocessing worker instantiation.
"""

from __future__ import annotations

import math

from traffic_lab.domain.network import EdgeId, LaneId, Network, SensorId
from traffic_lab.sensing.camera import CameraConfig, CameraSensor, MultiCameraSensor
from traffic_lab.sensing.model import SensorModel
from traffic_lab.sensing.oracle import OracleSensor


def get_incoming_approach_lanes(network: Network) -> list[tuple[EdgeId, tuple[LaneId, ...]]]:
    """Return ordered incoming approach edges and their lane IDs."""
    if not network.signalized_intersections:
        return []
    center_junction = network.signalized_intersections[0].junction
    incoming: list[tuple[EdgeId, tuple[LaneId, ...]]] = []
    for edge in network.edges:
        if edge.to_junction == center_junction and edge.from_junction != center_junction:
            incoming.append((edge.id, edge.lanes))
    return incoming


def make_oracle_sensor(network: Network, seed: int) -> SensorModel:
    """Create exact oracle sensor."""
    _ = seed
    return OracleSensor(SensorId(0), network)


def make_camera_sensor_4approach(
    network: Network,
    seed: int,
    *,
    p_det: float = 0.95,
    pos_noise_std: float = 0.5,
    speed_noise_std: float = 0.3,
    latency_s: float = 0.0,
    range_m: float = 100.0,
) -> SensorModel:
    """Config 1: 4 cameras mounted at the stop lines of each approach pointing upstream."""
    if not network.signalized_intersections:
        return OracleSensor(SensorId(0), network)
    center_id = network.signalized_intersections[0].junction
    junctions = {j.id: j for j in network.junctions}
    cx, cy = junctions[center_id].position_xy

    incoming = get_incoming_approach_lanes(network)
    cam_specs = [
        ((cx, cy + 15.0), math.pi / 2.0),
        ((cx + 15.0, cy), 0.0),
        ((cx, cy - 15.0), -math.pi / 2.0),
        ((cx - 15.0, cy), math.pi),
    ]
    cameras: list[CameraSensor] = []
    for idx, ((pos_xy, heading), (_edge_id, lanes)) in enumerate(
        zip(cam_specs, incoming, strict=False)
    ):
        cfg = CameraConfig(
            sensor_id=SensorId(idx + 1),
            position_xy=pos_xy,
            heading_rad=heading,
            fov_rad=math.radians(70.0),
            range_m=range_m,
            p_det_0=p_det,
            pos_noise_std=pos_noise_std,
            speed_noise_std=speed_noise_std,
            latency_s=latency_s,
            seed=seed + idx * 100,
            monitored_lanes=frozenset(lanes),
        )
        cameras.append(CameraSensor(cfg, network))

    return MultiCameraSensor(tuple(cameras))


def make_camera_sensor_central_omni(
    network: Network,
    seed: int,
    *,
    p_det: float = 0.95,
    pos_noise_std: float = 0.5,
    speed_noise_std: float = 0.3,
    latency_s: float = 0.0,
    range_m: float = 80.0,
) -> SensorModel:
    """Config 2: Single 360-degree omnidirectional camera at intersection center."""
    if not network.signalized_intersections:
        return OracleSensor(SensorId(0), network)
    center_id = network.signalized_intersections[0].junction
    junctions = {j.id: j for j in network.junctions}
    cx, cy = junctions[center_id].position_xy

    incoming = get_incoming_approach_lanes(network)
    all_incoming_lanes: set[LaneId] = set()
    for _edge, lanes in incoming:
        all_incoming_lanes.update(lanes)

    cfg = CameraConfig(
        sensor_id=SensorId(10),
        position_xy=(cx, cy),
        heading_rad=0.0,
        fov_rad=2.0 * math.pi,
        range_m=range_m,
        p_det_0=p_det,
        pos_noise_std=pos_noise_std,
        speed_noise_std=speed_noise_std,
        latency_s=latency_s,
        seed=seed,
        monitored_lanes=frozenset(all_incoming_lanes),
    )
    return CameraSensor(cfg, network)


def make_camera_sensor_partial_2approach(
    network: Network,
    seed: int,
    *,
    p_det: float = 0.95,
    pos_noise_std: float = 0.5,
    speed_noise_std: float = 0.3,
    latency_s: float = 0.0,
    range_m: float = 100.0,
) -> SensorModel:
    """Config 3: Partial 2-approach coverage (East-West approaches only)."""
    if not network.signalized_intersections:
        return OracleSensor(SensorId(0), network)
    center_id = network.signalized_intersections[0].junction
    junctions = {j.id: j for j in network.junctions}
    cx, cy = junctions[center_id].position_xy

    incoming = get_incoming_approach_lanes(network)
    cameras: list[CameraSensor] = []
    if len(incoming) >= 4:
        east_lanes = incoming[1][1]
        west_lanes = incoming[3][1]

        east_cfg = CameraConfig(
            sensor_id=SensorId(1),
            position_xy=(cx + 15.0, cy),
            heading_rad=0.0,
            fov_rad=math.radians(70.0),
            range_m=range_m,
            p_det_0=p_det,
            pos_noise_std=pos_noise_std,
            speed_noise_std=speed_noise_std,
            latency_s=latency_s,
            seed=seed,
            monitored_lanes=frozenset(east_lanes),
        )
        cameras.append(CameraSensor(east_cfg, network))

        west_cfg = CameraConfig(
            sensor_id=SensorId(2),
            position_xy=(cx - 15.0, cy),
            heading_rad=math.pi,
            fov_rad=math.radians(70.0),
            range_m=range_m,
            p_det_0=p_det,
            pos_noise_std=pos_noise_std,
            speed_noise_std=speed_noise_std,
            latency_s=latency_s,
            seed=seed + 100,
            monitored_lanes=frozenset(west_lanes),
        )
        cameras.append(CameraSensor(west_cfg, network))

    return MultiCameraSensor(tuple(cameras))
