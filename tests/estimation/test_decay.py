"""Tests for CountingWithDecayEstimator and DecayEstimatorConfig (D-005, D-021, T3.2)."""

from __future__ import annotations

import math
from pathlib import Path

from tests.generated_scenario import FOUR_WAY, build_intersection
from traffic_lab.domain.network import IntersectionId, LaneId, PhaseId, SensorId, VehicleType
from traffic_lab.domain.observation import Detection, Observation
from traffic_lab.domain.state import SignalState
from traffic_lab.estimation.decay import (
    CountingWithDecayEstimator,
    DecayEstimatorConfig,
)
from traffic_lab.estimation.estimator import Estimator


def _make_detection(lane: int, is_queued: bool = False, is_zone: bool = False) -> Detection:
    return Detection(
        sensor=SensorId(1),
        observed_at_s=10.0,
        position_xy=(200.0, 250.0),
        position_cov=(0.0, 0.0, 0.0),
        speed_mps=0.0 if is_queued else 10.0,
        speed_std=0.0,
        vehicle_class=VehicleType("car"),
        class_confidence=1.0,
        track_id=1,
        lane=LaneId(lane),
        stationary_s=5.0 if is_queued else 0.0,
        distance_to_stop_m=10.0 if is_zone else 80.0,
    )


def test_decay_estimator_implements_protocol(tmp_path: Path) -> None:
    built = build_intersection(FOUR_WAY, tmp_path / "scen")
    est = CountingWithDecayEstimator(built.network)
    assert isinstance(est, Estimator)


def test_decay_estimator_partial_coverage_tolerance(tmp_path: Path) -> None:
    built = build_intersection(FOUR_WAY, tmp_path / "scen")
    est = CountingWithDecayEstimator(built.network)

    # Observation covers only lane 16
    det = _make_detection(lane=16, is_queued=True, is_zone=True)
    obs = Observation(
        received_at_s=10.0,
        detections=(det,),
        observed_lanes=frozenset([LaneId(16)]),
    )
    sig = SignalState(
        intersection=IntersectionId(0),
        active_phase=PhaseId(0),
        phase_started_s=0.0,
        green_started_s=0.0,
        in_transition=False,
    )

    state = est.update(obs, (sig,), now_s=10.0)
    assert state.time_s == 10.0
    assert len(state.lanes) == len(built.network.lanes)

    lane_map = {le.lane: le for le in state.lanes}
    # Lane 16 was observed: count=1, queue=1, zone=1
    assert lane_map[LaneId(16)].vehicle_count == 1.0
    assert lane_map[LaneId(16)].queue_count == 1.0
    assert lane_map[LaneId(16)].zone_count == 1.0
    assert lane_map[LaneId(16)].queue_count_std == 0.0

    # Unobserved lanes (e.g. lane 17) default to 0.0 without crashing
    assert lane_map[LaneId(17)].vehicle_count == 0.0
    assert lane_map[LaneId(17)].queue_count == 0.0


def test_decay_estimator_exponential_decay_dynamics(tmp_path: Path) -> None:
    built = build_intersection(FOUR_WAY, tmp_path / "scen")
    cfg = DecayEstimatorConfig(half_life_s=10.0, default_queue_std=2.0)
    est = CountingWithDecayEstimator(built.network, cfg)

    # Step 1 (t=0s): Observe 8 queued vehicles on lane 16
    dets = tuple(_make_detection(lane=16, is_queued=True) for _ in range(8))
    obs_t0 = Observation(
        received_at_s=0.0,
        detections=dets,
        observed_lanes=frozenset([LaneId(16)]),
    )
    sig = SignalState(
        intersection=IntersectionId(0),
        active_phase=PhaseId(0),
        phase_started_s=0.0,
        green_started_s=0.0,
        in_transition=False,
    )
    state_t0 = est.update(obs_t0, (sig,), now_s=0.0)
    assert {le.lane: le for le in state_t0.lanes}[LaneId(16)].queue_count == 8.0

    # Step 2 (t=10s, 1 half-life elapsed without observation):
    # Camera loses connection: empty observed_lanes
    obs_empty = Observation(
        received_at_s=10.0,
        detections=(),
        observed_lanes=frozenset(),
    )
    state_t10 = est.update(obs_empty, (sig,), now_s=10.0)
    l16_t10 = {le.lane: le for le in state_t10.lanes}[LaneId(16)]
    # Half-life = 10s: count should halve from 8.0 to 4.0
    assert math.isclose(l16_t10.queue_count, 4.0, rel_tol=1e-3)
    assert math.isclose(l16_t10.vehicle_count, 4.0, rel_tol=1e-3)
    # Uncertainty increased
    assert l16_t10.queue_count_std > 0.5

    # Step 3 (t=20s, 2 half-lives elapsed): count halves again to 2.0
    state_t20 = est.update(obs_empty, (sig,), now_s=20.0)
    l16_t20 = {le.lane: le for le in state_t20.lanes}[LaneId(16)]
    assert math.isclose(l16_t20.queue_count, 2.0, rel_tol=1e-3)

    # Step 4 (t=100s, 10 half-lives): count converges to near 0.0
    state_t100 = est.update(obs_empty, (sig,), now_s=100.0)
    l16_t100 = {le.lane: le for le in state_t100.lanes}[LaneId(16)]
    assert math.isclose(l16_t100.queue_count, 0.0, abs_tol=0.01)
    assert l16_t100.queue_count >= 0.0
    # Uncertainty near default_queue_std (2.0)
    assert math.isclose(l16_t100.queue_count_std, 2.0, rel_tol=1e-2)
