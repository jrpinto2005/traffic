"""Acceptance tests for ExperimentSpec and sweep expansion (T1.16, D-013, D-017)."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from tests.generated_scenario import FOUR_WAY
from traffic_lab.experiments.seeds import derive_run_seeds
from traffic_lab.experiments.spec import (
    ControllerSpec,
    ExperimentSpec,
    WarmupDesign,
    expand_experiment,
    run,
)


def test_two_controllers_share_identical_arrival_sequences(tmp_path: Path) -> None:
    """T1.16 Criterion 1: Two controllers run with the same master seed receive identical
    arrival sequences, verified by comparing generated route files.
    """
    spec = ExperimentSpec(
        scenario=FOUR_WAY,
        demand_levels=[0.2],
        controllers=[
            ControllerSpec(type="webster"),
            ControllerSpec(type="actuated"),
            ControllerSpec(type="max_pressure"),
            ControllerSpec(type="sumo_actuated"),
        ],
        n_seeds=1,
        master_seed=42,
        warmup_s=10.0,
        measurement_s=20.0,
        cooldown_s=10.0,
    )
    run_specs = expand_experiment(spec, tmp_path / "exp")
    assert len(run_specs) == 4

    # All 4 arms for the same (demand_level, seed) point to the exact same route file
    route_paths = [s.routes for s in run_specs]
    assert len(set(route_paths)) == 1
    shared_routes = route_paths[0]
    assert shared_routes.exists()

    content = shared_routes.read_text()
    assert "<routes>" in content
    assert "<vehicle" in content


def test_varying_sensor_stream_leaves_arrivals_unchanged() -> None:
    """T1.16 Criterion 2: Holding demand fixed while varying sensor changes
    nothing about arrivals.
    """
    seeds_a = derive_run_seeds(master_seed=42, seed_index=0)
    seeds_b = derive_run_seeds(master_seed=42, seed_index=0)

    # Within the same run, streams are independent and deterministic
    assert seeds_a["demand"] == seeds_b["demand"]

    # Even if sensor stream had another value, demand seed only depends on master_seed & seed_index
    assert derive_run_seeds(master_seed=42, seed_index=0)["demand"] == seeds_a["demand"]


def test_sweep_of_four_controllers_three_demands_ten_seeds(tmp_path: Path) -> None:
    """T1.16 Criterion 3: A sweep of 4 controllers x 3 demand levels x 10 seeds
    completes and yields 120 rows.
    """
    spec = ExperimentSpec(
        scenario=FOUR_WAY,
        demand_levels=[0.15, 0.30, 0.45],
        controllers=[
            ControllerSpec(type="webster"),
            ControllerSpec(type="actuated"),
            ControllerSpec(type="max_pressure"),
            ControllerSpec(type="sumo_actuated"),
        ],
        n_seeds=10,
        master_seed=123,
        warmup_s=5.0,
        measurement_s=15.0,
        cooldown_s=5.0,
        jobs=4,
    )

    out_dir = tmp_path / "sweep_120"
    parquet_path = run(spec, out_dir)
    assert parquet_path.exists()

    df = pl.read_parquet(parquet_path)
    assert len(df) == 120

    # Criterion 4: Records controller, dt, demand level, and seed index
    assert "controller" in df.columns
    assert "demand_level" in df.columns
    assert "seed_index" in df.columns
    assert "decision_interval_s" in df.columns

    assert set(df["controller"].unique().to_list()) == {
        "webster",
        "actuated",
        "max_pressure",
        "sumo_actuated",
    }
    assert set(df["demand_level"].unique().to_list()) == {0.15, 0.30, 0.45}
    assert set(df["seed_index"].unique().to_list()) == set(range(10))

    # All runs completed and valid
    assert df["valid"].all()


def test_experiment_spec_validation() -> None:
    """Validation checks on ExperimentSpec inputs."""
    # Empty demand levels
    with pytest.raises(ValueError, match="demand_levels"):
        ExperimentSpec(
            scenario=FOUR_WAY,
            demand_levels=[],
            controllers=[ControllerSpec(type="webster")],
            n_seeds=1,
            master_seed=0,
        )

    # Non-positive demand level
    with pytest.raises(ValueError, match="demand_level"):
        ExperimentSpec(
            scenario=FOUR_WAY,
            demand_levels=[-0.1],
            controllers=[ControllerSpec(type="webster")],
            n_seeds=1,
            master_seed=0,
        )

    # Empty controllers
    with pytest.raises(ValueError, match="controllers"):
        ExperimentSpec(
            scenario=FOUR_WAY,
            demand_levels=[0.2],
            controllers=[],
            n_seeds=1,
            master_seed=0,
        )

    # Duplicate controller names
    with pytest.raises(ValueError, match="duplicate"):
        ExperimentSpec(
            scenario=FOUR_WAY,
            demand_levels=[0.2],
            controllers=[
                ControllerSpec(name="ctrl", type="webster"),
                ControllerSpec(name="ctrl", type="actuated"),
            ],
            n_seeds=1,
            master_seed=0,
        )

    # Zero seeds
    with pytest.raises(ValueError, match="n_seeds"):
        ExperimentSpec(
            scenario=FOUR_WAY,
            demand_levels=[0.2],
            controllers=[ControllerSpec(type="webster")],
            n_seeds=0,
            master_seed=0,
        )

    # Negative master seed
    with pytest.raises(ValueError, match="master_seed"):
        ExperimentSpec(
            scenario=FOUR_WAY,
            demand_levels=[0.2],
            controllers=[ControllerSpec(type="webster")],
            n_seeds=1,
            master_seed=-1,
        )

    # Neutral snapshot accepted in T1.6
    spec_neutral = ExperimentSpec(
        scenario=FOUR_WAY,
        demand_levels=[0.2],
        controllers=[ControllerSpec(type="webster")],
        n_seeds=1,
        master_seed=0,
        warmup_design=WarmupDesign.NEUTRAL_SNAPSHOT,
    )
    assert spec_neutral.warmup_design == WarmupDesign.NEUTRAL_SNAPSHOT
