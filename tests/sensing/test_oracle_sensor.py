"""`OracleSensor` (T1.9 A3): one exact detection per vehicle, every lane covered.

These are the unit-level checks of the contract, on hand-built `TrueState`s so
each field can be pinned. The oracle's exactness against the real simulator is
`tests/estimation/test_identity_exactness.py`.
"""

from __future__ import annotations

import inspect

import pytest

from traffic_lab.domain.network import (
    EdgeId,
    Lane,
    LaneId,
    Network,
    SensorId,
    VehicleId,
    VehicleType,
)
from traffic_lab.domain.observation import Observation
from traffic_lab.domain.state import LaneState, RunCounters, TrueState, VehicleState
from traffic_lab.sensing import OracleSensor, SensorModel

SENSOR = SensorId(7)
LANE_LENGTH_M = 100.0
NETWORK = Network(
    edges=(),
    lanes=tuple(
        Lane(
            id=LaneId(i),
            edge=EdgeId(0),
            index=0,
            length_m=LANE_LENGTH_M + i,
            width_m=3.2,
            speed_limit_mps=13.89,
            successors=(),
            adjacent_left=None,
            adjacent_right=None,
            allowed_types=frozenset({VehicleType.CAR}),
        )
        for i in range(4)
    ),
    connections=(),
    junctions=(),
    signalized_intersections=(),
)


def _vehicle(
    vehicle_id: int,
    lane: int,
    *,
    speed_mps: float = 8.0,
    halting_since_s: float | None = None,
    vehicle_type: VehicleType = VehicleType.CAR,
) -> VehicleState:
    return VehicleState(
        id=VehicleId(vehicle_id),
        type=vehicle_type,
        lane=LaneId(lane),
        position_on_lane_m=12.5 + vehicle_id,
        position_xy=(100.25 + vehicle_id, -3.5),
        speed_mps=speed_mps,
        time_loss_s=1.5,
        waiting_time_s=0.5,
        stop_count=2,
        is_halting=halting_since_s is not None,
        halting_since_s=halting_since_s,
    )


def _lane(lane: int) -> LaneState:
    return LaneState(
        lane=LaneId(lane), queue_count=0, queue_length_m=0.0, vehicle_count=0, mean_speed_mps=0.0
    )


def _state(
    vehicles: tuple[VehicleState, ...],
    *,
    lanes: tuple[int, ...] = (0, 1, 2, 3),
    time_s: float = 40.0,
) -> TrueState:
    return TrueState(
        time_s=time_s,
        vehicles=vehicles,
        lanes=tuple(_lane(lane) for lane in lanes),
        signals=(),
        counters=RunCounters(
            teleports=0,
            insertion_failures=0,
            gridlock_detected=False,
            arrived_at_sink=0,
            arrived_mid_link=0,
            still_in_network=len(vehicles),
        ),
    )


def test_the_oracle_is_a_sensor_model() -> None:
    sensor: SensorModel = OracleSensor(SENSOR, NETWORK)  # mypy checks the protocol is satisfied
    assert isinstance(sensor.observe(_state(()), 40.0), Observation)


def test_one_detection_per_vehicle_in_order() -> None:
    vehicles = (_vehicle(3, 0), _vehicle(1, 2), _vehicle(2, 2))
    observation = OracleSensor(SENSOR, NETWORK).observe(_state(vehicles), 40.0)
    assert [d.track_id for d in observation.detections] == [3, 1, 2]


def test_a_moving_vehicle_is_copied_exactly_with_zero_uncertainty() -> None:
    vehicle = _vehicle(5, 1, speed_mps=9.75, vehicle_type=VehicleType.MOTORCYCLE)
    (detection,) = OracleSensor(SENSOR, NETWORK).observe(_state((vehicle,)), 40.0).detections

    assert detection.sensor == SENSOR
    assert detection.observed_at_s == 40.0
    assert detection.position_xy == vehicle.position_xy
    assert detection.position_cov == (0.0, 0.0, 0.0)
    assert detection.speed_mps == 9.75
    assert detection.speed_std == 0.0
    assert detection.vehicle_class is VehicleType.MOTORCYCLE
    assert detection.class_confidence == 1.0
    assert detection.track_id == 5
    assert detection.lane == LaneId(1)
    assert detection.stationary_s == 0.0


@pytest.mark.parametrize(
    ("halting_since_s", "expected_stationary_s"),
    [(40.0, 0.0), (39.5, 0.5), (39.0, 1.0), (12.0, 28.0)],
)
def test_stationary_time_is_the_clock_the_truth_keeps(
    halting_since_s: float, expected_stationary_s: float
) -> None:
    vehicle = _vehicle(1, 0, speed_mps=0.0, halting_since_s=halting_since_s)
    (detection,) = OracleSensor(SENSOR, NETWORK).observe(_state((vehicle,)), 40.0).detections
    assert detection.stationary_s == expected_stationary_s


def test_observation_is_received_when_it_is_sampled() -> None:
    observation = OracleSensor(SENSOR, NETWORK).observe(
        _state((_vehicle(1, 0),), time_s=25.0), 25.0
    )
    assert observation.received_at_s == 25.0
    assert observation.detections[0].observed_at_s == 25.0


def test_every_lane_is_observed_including_empty_ones() -> None:
    # Absence of a detection on a covered lane is evidence of absence; the oracle
    # must therefore claim coverage of the lanes it saw nothing on as well.
    observation = OracleSensor(SENSOR, NETWORK).observe(
        _state((_vehicle(1, 2),), lanes=(0, 1, 2, 3, 9)), 40.0
    )
    assert observation.observed_lanes == frozenset(LaneId(i) for i in (0, 1, 2, 3, 9))


def test_an_empty_network_is_still_fully_covered() -> None:
    observation = OracleSensor(SENSOR, NETWORK).observe(_state(()), 40.0)
    assert observation.detections == ()
    assert observation.observed_lanes == frozenset(LaneId(i) for i in range(4))


@pytest.mark.parametrize("now_s", [39.0, 40.5, 0.0])
def test_zero_latency_means_now_must_be_the_state_time(now_s: float) -> None:
    with pytest.raises(ValueError, match="zero latency"):
        OracleSensor(SENSOR, NETWORK).observe(_state((_vehicle(1, 0),)), now_s)


def test_the_oracle_is_stateless() -> None:
    sensor = OracleSensor(SENSOR, NETWORK)
    state = _state((_vehicle(1, 0), _vehicle(2, 1, speed_mps=0.0, halting_since_s=30.0)))
    first = sensor.observe(state, 40.0)
    sensor.observe(_state((), time_s=50.0), 50.0)
    assert sensor.observe(state, 40.0) == first


def test_the_oracle_takes_a_sensor_id_and_nothing_else() -> None:
    # Non-goal 3: no noise, latency or dropout parameters -- "not even disabled
    # ones". Zero error is structural, so there is nothing to configure.
    parameters = list(inspect.signature(OracleSensor).parameters)
    assert parameters == ["sensor", "network"]


def test_distance_to_stop_is_the_lane_length_minus_the_position() -> None:
    # D-036. Lane i is 100 + i m long and `_vehicle` sits 12.5 + id m along it.
    vehicles = (_vehicle(1, 0), _vehicle(2, 3))
    detections = OracleSensor(SENSOR, NETWORK).observe(_state(vehicles), 40.0).detections
    assert [d.distance_to_stop_m for d in detections] == [100.0 - 13.5, 103.0 - 14.5]
