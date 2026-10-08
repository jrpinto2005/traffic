"""`IdentityEstimator` (T1.9 A4): per-lane counts passed through, complete input only.

Unit-level checks on hand-built observations. This module deliberately builds no
`TrueState`: an estimator test that needed ground truth would be testing the
boundary the package exists to keep. Exactness against the real simulator is
`test_identity_exactness.py`.
"""

from __future__ import annotations

import inspect

import pytest

from traffic_lab.domain.network import (
    EdgeId,
    IntersectionId,
    Lane,
    LaneId,
    Network,
    PhaseId,
    SensorId,
    VehicleType,
)
from traffic_lab.domain.observation import Detection, Observation
from traffic_lab.domain.state import QUEUE_MIN_HALTING_S, SignalState
from traffic_lab.estimation import Estimator, IdentityEstimator

NETWORK = Network(
    edges=(),
    lanes=tuple(
        Lane(
            id=LaneId(i),
            edge=EdgeId(0),
            index=0,
            length_m=200.0,
            width_m=3.2,
            speed_limit_mps=10.0,  # a 20 m zone at the default zone_s of 2 s
            successors=(),
            adjacent_left=None,
            adjacent_right=None,
            allowed_types=frozenset({VehicleType.CAR}),
        )
        for i in (0, 1, 2, 7, 9, 31)
    ),
    connections=(),
    junctions=(),
    signalized_intersections=(),
)

SIGNALS = (
    SignalState(
        intersection=IntersectionId(0),
        active_phase=PhaseId(1),
        phase_started_s=31.0,
        green_started_s=36.0,
        in_transition=False,
    ),
)


def _detection(
    track_id: int,
    lane: int | None,
    stationary_s: float | None,
    distance_to_stop_m: float | None = 50.0,
) -> Detection:
    return Detection(
        sensor=SensorId(0),
        observed_at_s=40.0,
        position_xy=(0.0, 0.0),
        position_cov=(0.0, 0.0, 0.0),
        speed_mps=0.0 if stationary_s else 8.0,
        speed_std=0.0,
        vehicle_class=VehicleType.CAR,
        class_confidence=1.0,
        track_id=track_id,
        lane=None if lane is None else LaneId(lane),
        stationary_s=stationary_s,
        distance_to_stop_m=distance_to_stop_m,
    )


def _observation(
    detections: tuple[Detection, ...],
    lanes: tuple[int, ...] = (0, 1, 2),
    received_at_s: float = 40.0,
) -> Observation:
    return Observation(
        received_at_s=received_at_s,
        detections=detections,
        observed_lanes=frozenset(LaneId(lane) for lane in lanes),
    )


def test_the_identity_estimator_is_an_estimator() -> None:
    estimator: Estimator = IdentityEstimator(NETWORK)  # mypy checks the protocol is satisfied
    assert estimator.update(_observation(()), SIGNALS, 40.0).lanes != ()


def test_counts_vehicles_and_queued_vehicles_per_lane() -> None:
    detections = (
        _detection(1, 0, 0.0),  # moving
        _detection(2, 0, 3.0),  # queued
        _detection(3, 0, 7.0),  # queued
        _detection(4, 2, 0.0),  # moving
        _detection(5, 2, 1.0),  # queued: exactly the threshold
    )
    estimate = IdentityEstimator(NETWORK).update(_observation(detections), SIGNALS, 40.0)

    by_lane = {e.lane: e for e in estimate.lanes}
    assert (by_lane[LaneId(0)].vehicle_count, by_lane[LaneId(0)].queue_count) == (3.0, 2.0)
    assert (by_lane[LaneId(1)].vehicle_count, by_lane[LaneId(1)].queue_count) == (0.0, 0.0)
    assert (by_lane[LaneId(2)].vehicle_count, by_lane[LaneId(2)].queue_count) == (2.0, 1.0)


@pytest.mark.parametrize(
    ("stationary_s", "queued"),
    [
        (0.0, False),  # moving, or halting for no time at all
        (0.5, False),
        (0.999, False),
        (QUEUE_MIN_HALTING_S, True),  # D-025: "at least 1 second"
        (1.001, True),
        (60.0, True),
    ],
)
def test_the_queue_threshold_is_d025s_one_second(stationary_s: float, queued: bool) -> None:
    estimate = IdentityEstimator(NETWORK).update(
        _observation((_detection(1, 0, stationary_s),)), SIGNALS, 40.0
    )
    assert estimate.lanes[0].queue_count == (1.0 if queued else 0.0)
    assert estimate.lanes[0].vehicle_count == 1.0


def test_one_estimate_per_observed_lane_sorted_by_lane_id() -> None:
    estimate = IdentityEstimator(NETWORK).update(
        _observation((), lanes=(9, 2, 31, 0, 7)), SIGNALS, 40.0
    )
    assert [e.lane for e in estimate.lanes] == [LaneId(i) for i in (0, 2, 7, 9, 31)]


def test_an_unobserved_lane_gets_no_estimate() -> None:
    # No evidence is not evidence of absence: a lane the observation does not
    # cover must not appear as an empty one.
    estimate = IdentityEstimator(NETWORK).update(_observation((), lanes=(0, 1)), SIGNALS, 40.0)
    assert LaneId(2) not in {e.lane for e in estimate.lanes}


def test_a_covered_empty_lane_is_an_estimate_of_zero_not_a_gap() -> None:
    estimate = IdentityEstimator(NETWORK).update(
        _observation((_detection(1, 0, 0.0),), lanes=(0, 1)), SIGNALS, 40.0
    )
    empty = estimate.lanes[1]
    assert empty.lane == LaneId(1)
    assert (empty.vehicle_count, empty.queue_count) == (0.0, 0.0)
    assert empty.last_observed_s == 40.0


def test_an_empty_observed_set_gives_no_lane_estimates() -> None:
    estimate = IdentityEstimator(NETWORK).update(_observation((), lanes=()), SIGNALS, 40.0)
    assert estimate.lanes == ()


def test_zero_uncertainty_and_the_observations_receipt_time() -> None:
    estimate = IdentityEstimator(NETWORK).update(
        _observation((_detection(1, 0, 4.0),), received_at_s=38.0), SIGNALS, 40.0
    )
    for lane in estimate.lanes:
        assert lane.queue_count_std == 0.0
        assert lane.last_observed_s == 38.0


def test_the_estimate_is_for_now_and_the_signals_are_copied_unchanged() -> None:
    estimate = IdentityEstimator(NETWORK).update(_observation(()), SIGNALS, 40.0)
    assert estimate.time_s == 40.0
    assert estimate.signals == SIGNALS


def test_counts_are_floats() -> None:
    # `LaneEstimate.queue_count` is a float because it is an estimate; a
    # controller written against an int would pretend to a certainty it lacks.
    estimate = IdentityEstimator(NETWORK).update(
        _observation((_detection(1, 0, 2.0),)), SIGNALS, 40.0
    )
    for lane in estimate.lanes:
        assert isinstance(lane.queue_count, float)
        assert isinstance(lane.vehicle_count, float)
        assert isinstance(lane.queue_count_std, float)


def test_the_estimator_is_stateless() -> None:
    estimator = IdentityEstimator(NETWORK)
    busy = _observation((_detection(1, 0, 5.0), _detection(2, 1, 0.0)))
    first = estimator.update(busy, SIGNALS, 40.0)
    estimator.update(_observation(()), SIGNALS, 45.0)
    assert estimator.update(busy, SIGNALS, 40.0) == first


@pytest.mark.parametrize(
    ("detection", "reason"),
    [
        (_detection(1, None, 0.0), "lane=None"),
        (_detection(1, 0, None), "stationary_s=None"),
        (_detection(1, None, None), "lane=None"),
        (_detection(1, 5, 0.0), "does not cover"),  # lane 5 is outside observed_lanes
    ],
)
def test_incomplete_observations_are_refused(detection: Detection, reason: str) -> None:
    # Estimators that cope with partial observation are M3's; guessing a lane or
    # a stationary time here would be a decision, not a pass-through.
    observation = _observation((_detection(0, 0, 0.0), detection))
    with pytest.raises(ValueError, match=reason):
        IdentityEstimator(NETWORK).update(observation, SIGNALS, 40.0)


def test_the_estimator_takes_only_the_network_and_the_zone_length() -> None:
    # D-036: no other configuration to carry, and none that could silently fail to apply.
    assert list(inspect.signature(IdentityEstimator).parameters) == ["network", "zone_s"]


def test_zone_count_includes_the_zone_length_and_excludes_beyond_it() -> None:
    # D-036: lane speed limit 10 m/s x zone_s 2 s = 20 m. Boundary is inclusive.
    detections = (
        _detection(1, 0, 0.0, distance_to_stop_m=0.0),  # at the stop line
        _detection(2, 0, 0.0, distance_to_stop_m=20.0),  # exactly the zone length
        _detection(3, 0, 0.0, distance_to_stop_m=20.0 + 1e-9),  # just beyond
        _detection(4, 0, 0.0, distance_to_stop_m=-0.5),  # past the line: not in the zone
        _detection(5, 1, 0.0, distance_to_stop_m=5.0),
    )
    estimate = IdentityEstimator(NETWORK).update(_observation(detections), SIGNALS, 40.0)
    zones = {int(e.lane): e.zone_count for e in estimate.lanes}
    assert zones == {0: 2.0, 1: 1.0, 2: 0.0}


def test_zone_length_scales_with_zone_s() -> None:
    detections = (_detection(1, 0, 0.0, distance_to_stop_m=25.0),)
    default = IdentityEstimator(NETWORK).update(_observation(detections), SIGNALS, 40.0)
    longer = IdentityEstimator(NETWORK, zone_s=3.0).update(_observation(detections), SIGNALS, 40.0)
    assert default.lanes[0].zone_count == 0.0
    assert longer.lanes[0].zone_count == 1.0


def test_a_detection_without_a_distance_is_incomplete() -> None:
    observation = _observation((_detection(1, 0, 0.0, distance_to_stop_m=None),))
    with pytest.raises(ValueError, match="distance_to_stop_m"):
        IdentityEstimator(NETWORK).update(observation, SIGNALS, 40.0)
