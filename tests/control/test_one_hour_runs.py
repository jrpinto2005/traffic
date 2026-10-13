"""One-hour runs through the experiment runner (T1.10 Acceptance Criteria A6).

Per T1.10 A6:
"Every controller runs at least one full hour on the shared generated intersection
through `traffic_lab.experiments.runner` with zero REJECTED outcomes."
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.control.support import make_webster_controller
from tests.generated_scenario import (
    DEMAND_PERIOD_S,
    FOUR_WAY,
    build_intersection,
    one_flow_per_movement,
)
from traffic_lab.control.actuated import ActuatedController
from traffic_lab.control.controller import Controller
from traffic_lab.control.max_pressure import MaxPressureController
from traffic_lab.domain.network import Network
from traffic_lab.experiments.config import RunConfig
from traffic_lab.experiments.runner import MANIFEST_FILE, RESULT_FILE, RunSpec, run_one

_ONE_HOUR_CONFIG = RunConfig(
    name="one_hour_acceptance",
    master_seed=42,
    warmup_s=300.0,
    measurement_s=3000.0,
    cooldown_s=300.0,
    warmup_design="self",
)


@pytest.mark.parametrize(
    ("name", "factory"),
    [
        ("webster", make_webster_controller),
        ("actuated", ActuatedController),
        ("max_pressure", MaxPressureController),
    ],
)
def test_controller_runs_one_full_hour_with_zero_rejected(
    name: str, factory: Callable[[Network], Controller], tmp_path: Path
) -> None:
    built = build_intersection(FOUR_WAY, tmp_path / "scenario")
    routes_file = one_flow_per_movement(
        built, tmp_path / "demand.rou.xml", 3600.0, period_s=DEMAND_PERIOD_S
    )

    out_dir = tmp_path / f"run_{name}"
    spec = RunSpec(
        run_id=f"one_hour_{name}",
        net=built.net,
        routes=routes_file,
        network=built.network,
        controller_factory=factory,
        config=_ONE_HOUR_CONFIG,
        seed_index=0,
        transport="libsumo",
        step_length_s=1.0,
        output_dir=out_dir,
    )

    result_parquet = run_one(spec)
    assert result_parquet.is_file(), f"{RESULT_FILE} was not written"

    manifest_json = out_dir / MANIFEST_FILE
    assert manifest_json.is_file(), f"{MANIFEST_FILE} was not written"
    manifest: dict[str, Any] = json.loads(manifest_json.read_text())

    # T1.10 Scope 4 and Acceptance Criteria: zero REJECTED outcomes
    outcomes = manifest["constraint_outcomes"]
    assert outcomes["rejected"] == 0, f"Controller {name} produced rejected outcomes: {outcomes}"
    assert outcomes["granted"] + outcomes["held"] + outcomes["forced"] > 0
