"""Unit tests for ActuatedController (D-013, D-036, T1.10 A3)."""

from __future__ import annotations

import dataclasses

import pytest

from tests.backend.conftest import Scenario
from tests.domain.factories import build_valid_network
from tests.generated_scenario import Built
from traffic_lab.control.actuated import ActuatedController
from traffic_lab.control.constraint_layer import ConstraintLayer, ConstraintLayerConfig
from traffic_lab.domain.action import RequestOutcome
from traffic_lab.domain.network import IntersectionId, PhaseId
from traffic_lab.domain.observation import EstimatedState, LaneEstimate
from traffic_lab.domain.state import SignalState


def _estimate(
    built: Built,
    zone_counts: dict[str, float],
    active: int,
    now_s: float,
    green_started_s: float | None,
    in_transition: bool = False,
) -> EstimatedState:
    lanes = tuple(
        LaneEstimate(
            lane=lane.id,
            queue_count=0.0,
            queue_count_std=0.0,
            last_observed_s=now_s,
            vehicle_count=zone_counts.get(built.ids.lanes[lane.id], 0.0),
            zone_count=zone_counts.get(built.ids.lanes[lane.id], 0.0),
        )
        for lane in built.network.lanes
    )
    return EstimatedState(
        time_s=now_s,
        lanes=lanes,
        signals=(
            SignalState(
                intersection=built.intersection_id,
                active_phase=PhaseId(active),
                phase_started_s=green_started_s if green_started_s is not None else now_s,
                green_started_s=green_started_s,
                in_transition=in_transition,
            ),
        ),
    )


def test_default_parameters() -> None:
    network = build_valid_network()
    controller = ActuatedController(network)
    assert controller.decision_interval_s == 1.0
    assert controller.gap_s == 3.0


def test_holds_phase_during_min_green_even_if_empty(scenario: Scenario) -> None:
    built = scenario.built
    controller = ActuatedController(scenario.network)
    # min_green_s is 10.0 s. Green started at 0.0 s. At now_s = 5.0 s, empty zones:
    est = _estimate(built, {}, active=0, now_s=5.0, green_started_s=0.0)
    req = controller.decide(est, 5.0)
    assert req.phase == PhaseId(0)


def test_extends_green_while_occupied_after_min_green(scenario: Scenario) -> None:
    built = scenario.built
    controller = ActuatedController(scenario.network)
    # Phase 0 incoming lane approach_0_in_0 occupied at t = 15.0 s (past min_green 10.0 s):
    est = _estimate(built, {"approach_0_in_0": 1.0}, active=0, now_s=15.0, green_started_s=0.0)
    req = controller.decide(est, 15.0)
    assert req.phase == PhaseId(0)


def test_gaps_out_immediately_at_min_green_if_empty_all_along(scenario: Scenario) -> None:
    built = scenario.built
    controller = ActuatedController(scenario.network)
    # Green started at 0.0 s. At 10.0 s (min green reached), no vehicle has ever arrived:
    est = _estimate(built, {}, active=0, now_s=10.0, green_started_s=0.0)
    req = controller.decide(est, 10.0)
    # Next phase after 0 is phase 1
    assert req.phase == PhaseId(1)


def test_gaps_out_after_gap_s_when_zone_empties(scenario: Scenario) -> None:
    built = scenario.built
    controller = ActuatedController(scenario.network, gap_s=3.0)
    # Vehicle in zone at t = 8.0 s (during min green)
    est_8 = _estimate(built, {"approach_0_in_0": 1.0}, active=0, now_s=8.0, green_started_s=0.0)
    controller.decide(est_8, 8.0)

    # Empty at t = 10.0 s (elapsed since vehicle = 2.0 s <= 3.0 s) -> extends
    est_10 = _estimate(built, {}, active=0, now_s=10.0, green_started_s=0.0)
    assert controller.decide(est_10, 10.0).phase == PhaseId(0)

    # Empty at t = 11.0 s (elapsed since vehicle = 3.0 s <= 3.0 s) -> extends
    est_11 = _estimate(built, {}, active=0, now_s=11.0, green_started_s=0.0)
    assert controller.decide(est_11, 11.0).phase == PhaseId(0)

    # Empty at t = 12.0 s (elapsed since vehicle = 4.0 s > 3.0 s) -> gaps out to phase 1
    est_12 = _estimate(built, {}, active=0, now_s=12.0, green_started_s=0.0)
    assert controller.decide(est_12, 12.0).phase == PhaseId(1)


def test_transition_holds_active_phase(scenario: Scenario) -> None:
    built = scenario.built
    controller = ActuatedController(scenario.network)
    est = _estimate(built, {}, active=1, now_s=15.0, green_started_s=None, in_transition=True)
    req = controller.decide(est, 15.0)
    assert req.phase == PhaseId(1)


def test_missing_lane_raises_value_error(scenario: Scenario) -> None:
    built = scenario.built
    controller = ActuatedController(scenario.network)
    full = _estimate(built, {}, active=0, now_s=5.0, green_started_s=0.0)
    used_lane = next(iter(controller._services[PhaseId(0)]))
    partial = EstimatedState(
        full.time_s,
        tuple(lane for lane in full.lanes if lane.lane != used_lane),
        full.signals,
    )
    with pytest.raises(ValueError, match="no estimate for lane"):
        controller.decide(partial, 5.0)


def test_refuses_multi_intersection_network(scenario: Scenario) -> None:
    network = scenario.network
    doubled = dataclasses.replace(
        network,
        signalized_intersections=(
            *network.signalized_intersections,
            dataclasses.replace(network.signalized_intersections[0], id=IntersectionId(1)),
        ),
    )
    with pytest.raises(ValueError, match="one signalized intersection"):
        ActuatedController(doubled)


def test_runs_through_constraint_layer_with_zero_rejected(scenario: Scenario) -> None:
    """T1.10 Acceptance Criteria: No controller ever produces a REJECTED outcome."""
    network = scenario.network
    built = scenario.built
    controller = ActuatedController(network)
    layer = ConstraintLayer(
        network, ConstraintLayerConfig(decision_interval_s=1.0, step_length_s=1.0)
    )

    now_s = 0.0
    for step in range(1, 120):
        now_s = float(step)
        layer.step(now_s)
        sig = layer.signal_state(built.intersection_id)
        # Vehicles present periodically on approach 0 and 1
        has_veh = (step % 25) < 8
        zone = {"approach_0_in_0": 1.0 if has_veh else 0.0}
        est = _estimate(
            built,
            zone,
            active=int(sig.active_phase),
            now_s=now_s,
            green_started_s=sig.green_started_s,
            in_transition=sig.in_transition,
        )
        req = controller.decide(est, now_s)
        result = layer.submit(req, now_s)
        assert result.outcome != RequestOutcome.REJECTED
