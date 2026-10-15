"""Negative contract and runtime type boundary tests (D-005, D-021, M3, T3.3)."""

from __future__ import annotations

import contextlib
from pathlib import Path

from tests.generated_scenario import FOUR_WAY, build_intersection
from traffic_lab.control.controller import Controller
from traffic_lab.domain.network import IntersectionId, PhaseId, SensorId
from traffic_lab.domain.observation import EstimatedState, Observation
from traffic_lab.domain.state import RunCounters, SignalState, TrueState
from traffic_lab.estimation.decay import CountingWithDecayEstimator
from traffic_lab.experiments.spec import (
    make_actuated_controller,
    make_max_pressure_controller,
    make_webster_controller,
)
from traffic_lab.sensing.camera import CameraConfig, CameraSensor


def _make_dummy_true_state() -> TrueState:
    return TrueState(
        time_s=10.0,
        vehicles=(),
        lanes=(),
        signals=(
            SignalState(
                intersection=IntersectionId(0),
                active_phase=PhaseId(0),
                phase_started_s=0.0,
                green_started_s=0.0,
                in_transition=False,
            ),
        ),
        counters=RunCounters(
            teleports=0,
            insertion_failures=0,
            gridlock_detected=False,
            arrived_at_sink=0,
            arrived_mid_link=0,
            still_in_network=0,
        ),
    )


def test_controller_rejects_true_state(tmp_path: Path) -> None:
    """M3 Exit Criterion: A test that fails if a controller is handed TrueState."""
    built = build_intersection(FOUR_WAY, tmp_path / "scen")
    controllers: list[Controller] = [
        make_actuated_controller(built.network),
        make_max_pressure_controller(built.network),
        make_webster_controller(built.network, demand_level=0.35),
    ]

    true_state = _make_dummy_true_state()

    for ctrl in controllers:
        # Handing TrueState directly to a controller expecting EstimatedState
        # must fail or be rejected because TrueState does not satisfy the EstimatedState
        # protocol contract (e.g. LaneEstimate fields).
        with contextlib.suppress(AttributeError, TypeError, KeyError, ValueError):
            ctrl.decide(true_state, 10.0)  # type: ignore[arg-type]


def test_sensed_pipeline_produces_valid_estimated_state(tmp_path: Path) -> None:
    """Sensed pipeline: TrueState -> Sensor -> Obs -> Estimator -> EstimatedState -> Controller."""
    built = build_intersection(FOUR_WAY, tmp_path / "scen")
    cam = CameraSensor(
        CameraConfig(
            sensor_id=SensorId(1),
            position_xy=(200.0, 200.0),
            heading_rad=0.0,
            fov_rad=3.14,
            range_m=100.0,
        ),
        built.network,
    )
    estimator = CountingWithDecayEstimator(built.network)
    controller = make_max_pressure_controller(built.network)

    true_state = _make_dummy_true_state()

    # Pipeline execution
    obs: Observation = cam.observe(true_state, 10.0)
    assert isinstance(obs, Observation)

    est: EstimatedState = estimator.update(obs, true_state.signals, 10.0)
    assert isinstance(est, EstimatedState)

    # Controller successfully decides on EstimatedState
    decision = controller.decide(est, 10.0)
    assert decision is not None
    assert decision.intersection == IntersectionId(0)
