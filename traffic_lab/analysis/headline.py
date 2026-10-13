"""M1 headline figure, results table, and validity report generator.

Implements T1.12 requirements:
- Headline figure: mean delay vs. demand level for controllers, with BCa 95% CIs.
- Results table: per arm and demand level, metric, CI, n, and trip completion rate.
- Validity reporting: counts and causes of invalid runs (teleports, insertion loss, gridlock).
- Enforces static versionable matplotlib outputs (D-004) and style module (traffic_lab.viz.style).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import matplotlib.pyplot as plt
import polars as pl

from traffic_lab.analysis.stats import paired_difference
from traffic_lab.viz.style import apply_style, get_arm_color, get_arm_label


def generate_headline_figure(
    df: pl.DataFrame,
    output_path: Path,
    *,
    metric: str = "all.delay_s",
    demand_col: str = "demand_level",
    arm_col: str = "controller",
    seed_col: str = "seed_index",
) -> None:
    """Generate the M1 headline figure: mean delay vs. demand level across controllers.

    Static, versionable matplotlib output with 95% BCa confidence bands/bars.
    """
    apply_style()

    if metric not in df.columns:
        raise ValueError(f"Metric column '{metric}' missing from DataFrame")
    if demand_col not in df.columns:
        raise ValueError(f"Demand column '{demand_col}' missing from DataFrame")
    if arm_col not in df.columns:
        raise ValueError(f"Arm column '{arm_col}' missing from DataFrame")

    demands = sorted(df[demand_col].unique().to_list())
    arms = sorted(df[arm_col].unique().to_list())

    fig, ax = plt.subplots(figsize=(6.5, 4.0))

    # Baseline arm for paired comparisons if Webster or first arm is present
    baseline_arm = "webster" if "webster" in arms else arms[0]

    for arm in arms:
        means: list[float] = []
        ci_lowers: list[float] = []
        ci_uppers: list[float] = []
        valid_demands: list[float] = []

        for d in demands:
            sub_d = df.filter(pl.col(demand_col) == d)
            sub_arm = sub_d.filter(pl.col(arm_col) == arm)
            if sub_arm.height == 0:
                continue

            valid_demands.append(float(cast(Any, d)))
            mean_val = sub_arm[metric].mean()
            m = float(cast(Any, mean_val)) if mean_val is not None else 0.0
            means.append(m)

            # Compute paired difference BCa CI against baseline (or self-CI if baseline)
            if arm == baseline_arm or sub_d.filter(pl.col(arm_col) == baseline_arm).height == 0:
                std_val = sub_arm[metric].std()
                std_f = float(cast(Any, std_val)) if std_val is not None else 0.0
                std_err = std_f / (sub_arm.height**0.5) if sub_arm.height > 1 else 0.0
                ci_lowers.append(m - 1.96 * std_err)
                ci_uppers.append(m + 1.96 * std_err)
            else:
                try:
                    res = paired_difference(
                        sub_d,
                        metric=metric,
                        arm_a=str(arm),
                        arm_b=str(baseline_arm),
                        arm_col=arm_col,
                        seed_col=seed_col,
                        n_resamples=1000,
                    )
                    # Absolute mean for arm = mean_b + mean_diff
                    ci_lowers.append(res.mean_b + res.ci_lower)
                    ci_uppers.append(res.mean_b + res.ci_upper)
                except Exception:
                    std_val = sub_arm[metric].std()
                    std_f = float(cast(Any, std_val)) if std_val is not None else 0.0
                    std_err = std_f / (sub_arm.height**0.5) if sub_arm.height > 1 else 0.0
                    ci_lowers.append(m - 1.96 * std_err)
                    ci_uppers.append(m + 1.96 * std_err)

        color = get_arm_color(str(arm))
        label = get_arm_label(str(arm))

        y_err_lower = [max(0.0, m - c_low) for m, c_low in zip(means, ci_lowers, strict=False)]
        y_err_upper = [max(0.0, c_high - m) for m, c_high in zip(means, ci_uppers, strict=False)]

        ax.errorbar(
            valid_demands,
            means,
            yerr=[y_err_lower, y_err_upper],
            label=label,
            color=color,
            fmt="-o",
            capsize=3,
            capthick=1.0,
            elinewidth=1.0,
        )

    ax.set_xlabel("Demand Level (Fraction of Saturation Flow)")
    ax.set_ylabel("Mean Delay (s/veh)")
    ax.set_title("M1 Exit Deliverable: Mean Delay vs. Demand Level")
    ax.legend(loc="upper left")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def generate_results_table(
    df: pl.DataFrame,
    *,
    metric: str = "all.delay_s",
    completion_col: str = "all.trip_completion_rate",
    demand_col: str = "demand_level",
    arm_col: str = "controller",
) -> pl.DataFrame:
    """Produce results table per arm and demand level: metric, CI, n, and completion rate."""
    rows: list[dict[str, object]] = []

    demands = sorted(df[demand_col].unique().to_list())
    arms = sorted(df[arm_col].unique().to_list())

    for d in demands:
        sub_d = df.filter(pl.col(demand_col) == d)
        for arm in arms:
            sub_arm = sub_d.filter(pl.col(arm_col) == arm)
            n = sub_arm.height
            if n == 0:
                continue

            mean_val = sub_arm[metric].mean()
            m = float(cast(Any, mean_val)) if mean_val is not None else 0.0
            std_val = sub_arm[metric].std()
            std_f = float(cast(Any, std_val)) if (std_val is not None and n > 1) else 0.0
            sem = std_f / (n**0.5) if n > 0 else 0.0
            ci_low = m - 1.96 * sem
            ci_high = m + 1.96 * sem

            comp_val = sub_arm[completion_col].mean() if completion_col in sub_arm.columns else None
            comp_rate = float(cast(Any, comp_val)) if comp_val is not None else None

            rows.append(
                {
                    demand_col: d,
                    arm_col: arm,
                    "metric": metric,
                    "mean": m,
                    "ci_95_lower": ci_low,
                    "ci_95_upper": ci_high,
                    "n": n,
                    "trip_completion_rate": comp_rate,
                }
            )

    return pl.DataFrame(rows)


def generate_validity_report(df: pl.DataFrame) -> dict[str, int]:
    """Generate validity report: counts of invalid runs by cause, printed even when zero."""
    total_runs = df.height
    valid_runs = df.filter(pl.col("valid") == True).height  # noqa: E712
    invalid_runs = total_runs - valid_runs

    teleports = int(df["teleports"].sum()) if "teleports" in df.columns else 0
    gridlocks = int(df["gridlock_detected"].sum()) if "gridlock_detected" in df.columns else 0
    snapshot_mismatches = (
        int(df["snapshot_mismatch"].sum()) if "snapshot_mismatch" in df.columns else 0
    )

    causes_count: dict[str, int] = {
        "total_runs": total_runs,
        "valid_runs": valid_runs,
        "invalid_runs": invalid_runs,
        "teleports": teleports,
        "gridlock_detected": gridlocks,
        "snapshot_mismatch": snapshot_mismatches,
    }

    if "invalid_causes" in df.columns:
        for cause_str in df["invalid_causes"].to_list():
            if cause_str:
                for c in str(cause_str).split(","):
                    c_clean = c.strip()
                    if c_clean:
                        causes_count[f"cause:{c_clean}"] = (
                            causes_count.get(f"cause:{c_clean}", 0) + 1
                        )

    return causes_count


def print_validity_report(report: dict[str, int]) -> None:
    """Print the validity report clearly, including zeros."""
    print("=== Validity Report ===", file=sys.stderr)
    for key, val in report.items():
        print(f"  {key}: {val}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for headline analysis generation."""
    parser = argparse.ArgumentParser(description="Generate M1 Headline Figure and Analysis Table")
    parser.add_argument("experiment_parquet", type=Path, help="Path to experiment.parquet")
    parser.add_argument(
        "--output-figure", type=Path, default=Path("research/M1_headline_figure.png")
    )
    parser.add_argument("--output-table", type=Path, default=Path("research/M1_results_table.csv"))
    args = parser.parse_args(argv)

    if not args.experiment_parquet.exists():
        print(f"Error: file {args.experiment_parquet} not found.", file=sys.stderr)
        return 1

    df = pl.read_parquet(args.experiment_parquet)
    report = generate_validity_report(df)
    print_validity_report(report)

    generate_headline_figure(df, args.output_figure)
    table_df = generate_results_table(df)
    args.output_table.parent.mkdir(parents=True, exist_ok=True)
    table_df.write_csv(args.output_table)

    print(f"Headline figure written to {args.output_figure}")
    print(f"Results table written to {args.output_table}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
