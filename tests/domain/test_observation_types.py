"""Construction and immutability of the SS4 observation/estimate types (D-005)."""

from __future__ import annotations

from traffic_lab.domain.network import IntersectionId, LaneId, PhaseId, SensorId, VehicleType
from traffic_lab.domain.observation import Detection, EstimatedState, LaneEstimate, Observation
from traffic_lab.domain.state import SignalState


def test_detection_carries_no_field_naming_how_it_was_produced() -> None:
    # D-005: Observation/Detection must not encode field of view, range, or
    # detection probability -- checked here as "these fields do not exist".
    forbidden = {"fov_rad", "range_m", "detection_probability", "orientation_rad"}
    assert forbidden.isdisjoint(Detection.__dataclass_fields__)
    assert forbidden.isdisjoint(Observation.__dataclass_fields__)


def test_observation_lanes_distinguish_covered_from_uncovered() -> None:
    detection = Detection(
        sensor=SensorId(0),
        observed_at_s=1.0,
        position_xy=(0.0, 0.0),
        position_cov=(0.1, 0.1, 0.0),
        speed_mps=5.0,
        speed_std=0.5,
        vehicle_class=VehicleType.CAR,
        class_confidence=0.9,
        track_id=None,
    )
    observation = Observation(
        received_at_s=1.1,
        detections=(detection,),
        observed_lanes=frozenset({LaneId(0), LaneId(1)}),
    )
    assert LaneId(2) not in observation.observed_lanes  # unobserved: no evidence either way


def test_lane_estimate_queue_count_is_a_float_with_uncertainty() -> None:
    estimate = LaneEstimate(
        lane=LaneId(0),
        queue_count=2.5,
        queue_count_std=0.7,
        last_observed_s=10.0,
        vehicle_count=4.0,
    )
    assert isinstance(estimate.queue_count, float)
    assert estimate.last_observed_s == 10.0


def test_estimated_state_never_observed_lane_has_none_last_observed() -> None:
    estimate = LaneEstimate(
        lane=LaneId(0),
        queue_count=0.0,
        queue_count_std=0.0,
        last_observed_s=None,
        vehicle_count=0.0,
    )
    signal = SignalState(
        intersection=IntersectionId(0),
        active_phase=PhaseId(0),
        phase_started_s=0.0,
        in_transition=False,
    )
    state = EstimatedState(time_s=5.0, lanes=(estimate,), signals=(signal,))
    assert state.lanes[0].last_observed_s is None
