"""Cross-check: our ActuatedController against SUMO's gap-actuated baseline (T1.10).

Per contract (T1.10 A4, A6):
1. Program generation: `build(spec, out_dir, program="actuated")` sets SUMO's native
   `type="actuated"` with `minDur = min_green_s`, `maxDur = max_green_s`, and actuated parameters:
   - `max-gap = 3.0` s
   - `detector-gap = 2.0` s
   - `passing-time = 2.0` s
2. Cross-check: on a scenario with deliberately unbalanced demand (Approach 0 loaded with
   a queue discharging through green, while other approaches have no demand):
   - SUMO's native actuated program drives the intersection directly (no constraint layer).
   - Our `ActuatedController` drives the intersection through `ConstraintLayer` at Δt = 1.0 s,
     reading `EstimatedState` from `OracleSensor` + `IdentityEstimator` (`zone_s = 2.0` s).
3. Stated tolerance:
   - Both controllers must hold empty phases (zero demand) to `min_green_s = 10.0` s.
   - For the loaded phase, both controllers must extend green beyond `min_green_s`.
   - The allocated green durations agree within 15% tolerance: the physical difference stems
     from SUMO's single-point induction loop (`detector-gap = 2.0` s upstream) vs our
     presence-mode detection zone (covering the full 2.0 s approach area up to the stop line).
   - Zero `REJECTED` outcomes from our controller through the `ConstraintLayer`.
"""

from __future__ import annotations

from pathlib import Path

from tests.backend.conftest import Scenario
from tests.generated_scenario import FOUR_WAY
from traffic_lab.backend import BackendConfig, SumoBackend, display_state
from traffic_lab.control.actuated import ActuatedController
from traffic_lab.control.constraint_layer import ConstraintLayer, ConstraintLayerConfig
from traffic_lab.domain.action import RequestOutcome
from traffic_lab.domain.network import SensorId
from traffic_lab.estimation import IdentityEstimator
from traffic_lab.scenarios import build
from traffic_lab.sensing import OracleSensor


def _create_unbalanced_routes(path: Path) -> None:
    lines = [
        "<routes>",
        '    <vType id="car" length="5.0" accel="2.6" decel="4.5" maxSpeed="13.89"/>',
        '    <route id="r0" edges="approach_0_in approach_2_out"/>',
    ]
    # Queue of 10 vehicles on approach 0 through movement at start of green
    for i in range(10):
        pos = max(0, 160 - i * 14)
        lines.append(
            f'    <vehicle id="v_{i}" type="car" route="r0" depart="0" '
            f'departPos="{pos}" departSpeed="10"/>'
        )
    lines.append("</routes>")
    path.write_text("\n".join(lines) + "\n")


def test_actuated_crosscheck_unbalanced_demand(scenario: Scenario, tmp_path: Path) -> None:
    """Compare SUMO's gap-actuated program against our ActuatedController on unbalanced demand."""
    routes_file = tmp_path / "unbalanced.rou.xml"
    _create_unbalanced_routes(routes_file)

    # --- Arm 1: SUMO gap-actuated baseline ---
    net_sumo_path, net_sumo_obj = build(FOUR_WAY, tmp_path / "sumo_arm", program="actuated")
    backend_sumo = SumoBackend()
    backend_sumo.start(
        net_sumo_path,
        routes_file,
        BackendConfig(transport="libsumo", seed=42, decision_interval_s=1.0, gridlock_steps=200),
        network=net_sumo_obj,
    )
    sumo_greens: dict[int, float] = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0}
    try:
        for _ in range(45):
            backend_sumo.step()
            truth = backend_sumo.project()
            sig = truth.signals[0]
            if not sig.in_transition and sig.green_started_s is not None:
                sumo_greens[int(sig.active_phase)] += 1.0
    finally:
        backend_sumo.close()

    # --- Arm 2: Our ActuatedController through ConstraintLayer ---
    net_ours_path, net_ours_obj = build(FOUR_WAY, tmp_path / "ours_arm", program="static")
    backend_ours = SumoBackend()
    backend_ours.start(
        net_ours_path,
        routes_file,
        BackendConfig(transport="libsumo", seed=42, decision_interval_s=1.0, gridlock_steps=200),
        network=net_ours_obj,
    )
    intersection_id = net_ours_obj.signalized_intersections[0].id
    controller = ActuatedController(net_ours_obj, gap_s=3.0)
    layer = ConstraintLayer(
        net_ours_obj,
        ConstraintLayerConfig(decision_interval_s=1.0, step_length_s=1.0),
        start_s=0.0,
    )
    sensor = OracleSensor(SensorId(0), net_ours_obj)
    estimator = IdentityEstimator(net_ours_obj, zone_s=2.0)
    ours_greens: dict[int, float] = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0}

    def apply_display() -> None:
        stage, phase = layer.display(intersection_id)
        backend_ours.apply(
            intersection_id, display_state(net_ours_obj, intersection_id, stage, phase)
        )

    try:
        apply_display()
        for _ in range(45):
            backend_ours.step()
            truth = backend_ours.project()
            sig = truth.signals[0]
            if not sig.in_transition and sig.green_started_s is not None:
                ours_greens[int(sig.active_phase)] += 1.0

            layer.step(truth.time_s)
            obs = sensor.observe(truth, truth.time_s)
            est = estimator.update(obs, (layer.signal_state(intersection_id),), truth.time_s)
            req = controller.decide(est, truth.time_s)
            result = layer.submit(req, truth.time_s)
            assert result.outcome != RequestOutcome.REJECTED
            apply_display()
    finally:
        backend_ours.close()

    # --- Tolerance Assertions ---
    # 1. Both controllers extended the loaded phase (phase 0) significantly beyond min_green (10 s)
    assert sumo_greens[0] > 15.0, f"SUMO phase 0 green was {sumo_greens[0]} s"
    assert ours_greens[0] > 15.0, f"Ours phase 0 green was {ours_greens[0]} s"

    # 2. Both controllers agree on Phase 0 green duration within 15% tolerance
    relative_diff = abs(ours_greens[0] - sumo_greens[0]) / sumo_greens[0]
    assert relative_diff <= 0.15, (
        f"Phase 0 green difference ({ours_greens[0]} vs {sumo_greens[0]}) "
        f"exceeds 15% tolerance ({relative_diff:.1%})"
    )

    # 3. Empty phases (Phase 1) received min_green in both controllers
    assert sumo_greens[1] == 10.0, f"SUMO phase 1 was {sumo_greens[1]} s"
    assert ours_greens[1] == 10.0, f"Ours phase 1 was {ours_greens[1]} s"
