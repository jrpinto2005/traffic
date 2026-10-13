"""M1 Delta-t Sensitivity Check (D-020, Roadmap M1 Exit Criterion).

Evaluates Max-Pressure at decision intervals of 1s, 5s, and 10s across
demand levels [0.15, 0.25, 0.35, 0.45] with 15 paired seeds using libsumo.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib"

import polars as pl

from tests.generated_scenario import FOUR_WAY
from traffic_lab.experiments.spec import ControllerSpec, ExperimentSpec, run


def main() -> None:
    exp_dir = Path("research/m1_dt_experiment")
    if exp_dir.exists():
        shutil.rmtree(exp_dir)
    exp_dir.mkdir(parents=True, exist_ok=True)

    controllers = [
        ControllerSpec(name="max_pressure_1s", type="max_pressure", decision_interval_s=1.0),
        ControllerSpec(name="max_pressure_5s", type="max_pressure", decision_interval_s=5.0),
        ControllerSpec(name="max_pressure_10s", type="max_pressure", decision_interval_s=10.0),
    ]

    demand_levels = [0.15, 0.25, 0.35, 0.45]
    n_seeds = 15
    master_seed = 42

    spec = ExperimentSpec(
        scenario=FOUR_WAY,
        demand_levels=demand_levels,
        controllers=controllers,
        n_seeds=n_seeds,
        master_seed=master_seed,
        warmup_s=60.0,
        measurement_s=300.0,
        cooldown_s=60.0,
        step_length_s=1.0,
        transport="libsumo",
        warmup_design="self",
        name="m1_dt_sensitivity",
    )

    total_runs = len(controllers) * len(demand_levels) * n_seeds
    print(f"Running Delta-t sensitivity sweep: {total_runs} runs on paired seeds...")
    parquet_path = run(spec, exp_dir)
    print(f"Sweep completed. Output: {parquet_path}")

    df = pl.read_parquet(parquet_path)
    print(f"Loaded results dataframe: {len(df)} rows.")

    metric = "all.mean_delay_s" if "all.mean_delay_s" in df.columns else "all.delay_s"
    summary = (
        df.group_by(["demand_level", "controller"])
        .agg(
            [
                pl.col(metric).mean().alias("mean_delay_s"),
                pl.col(metric).std().alias("std_delay_s"),
                pl.len().alias("n"),
            ]
        )
        .sort(["demand_level", "controller"])
    )
    print("Results summary:")
    print(summary)

    out_csv = Path("research/M1_dt_sensitivity.csv")
    summary.write_csv(out_csv)
    print(f"Wrote {out_csv}")


if __name__ == "__main__":
    main()
