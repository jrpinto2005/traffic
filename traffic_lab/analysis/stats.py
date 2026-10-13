"""Statistical analysis for paired comparisons, confidence intervals, and replication sizing.

Implements D-017, 07_EXPERIMENT_METHODOLOGY.md §7, and ticket T1.12.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
import polars as pl


@dataclass(frozen=True, slots=True)
class PairedResult:
    """Result of a paired comparison between two controller arms over common seeds."""

    metric: str
    arm_a: str
    arm_b: str
    mean_a: float
    mean_b: float
    mean_diff: float
    ci_lower: float
    ci_upper: float
    relative_effect: float
    relative_ci_lower: float
    relative_ci_upper: float
    n: int
    p_value: float


def _bca_interval(
    obs_stat: float,
    boot_stats: np.ndarray,
    jack_stats: np.ndarray,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Compute BCa (bias-corrected and accelerated) bootstrap confidence interval."""
    b = len(boot_stats)
    if b == 0:
        raise ValueError("boot_stats cannot be empty")

    # 1. Bias correction z0
    num_less = np.sum(boot_stats < obs_stat)
    prop_less = float(num_less) / float(b)
    # Clamp prop_less away from 0 and 1 for numerical stability
    prop_less = max(1.0 / (2.0 * b), min(1.0 - 1.0 / (2.0 * b), prop_less))
    z0 = NormalDist().inv_cdf(prop_less)

    # 2. Acceleration parameter a from jackknife estimates
    jack_mean = float(np.mean(jack_stats))
    diffs = jack_mean - jack_stats
    sum_cubes = float(np.sum(diffs**3))
    sum_sq = float(np.sum(diffs**2))
    a = 0.0 if sum_sq == 0.0 else sum_cubes / (6.0 * (sum_sq**1.5))

    # 3. Adjusted percentiles
    z_alpha_lower = NormalDist().inv_cdf(alpha / 2.0)
    z_alpha_upper = NormalDist().inv_cdf(1.0 - alpha / 2.0)

    denom_lower = 1.0 - a * (z0 + z_alpha_lower)
    denom_upper = 1.0 - a * (z0 + z_alpha_upper)

    d_low = denom_lower if denom_lower != 0 else 1e-9
    d_upp = denom_upper if denom_upper != 0 else 1e-9

    pct_lower = NormalDist().cdf(z0 + (z0 + z_alpha_lower) / d_low)
    pct_upper = NormalDist().cdf(z0 + (z0 + z_alpha_upper) / d_upp)

    pct_lower = max(0.0, min(1.0, pct_lower))
    pct_upper = max(0.0, min(1.0, pct_upper))

    q_lower = float(np.percentile(boot_stats, pct_lower * 100.0))
    q_upper = float(np.percentile(boot_stats, pct_upper * 100.0))

    return q_lower, q_upper


def paired_difference(
    df: pl.DataFrame,
    metric: str,
    arm_a: str,
    arm_b: str,
    *,
    arm_col: str = "controller",
    seed_col: str = "seed_index",
    n_resamples: int = 10_000,
    alpha: float = 0.05,
    master_seed: int = 42,
) -> PairedResult:
    """Compute paired difference statistics and BCa confidence interval across runs.

    Rule 1 (§6.3, D-017): The replication unit is the run, not the vehicle.
    One run contributes one number per metric. Input DataFrame MUST contain
    run-level summary metrics, with exactly one row per (arm, seed). Passing
    per-vehicle rows raises a ValueError.
    """
    # Enforce anti-aggregation guard: Check for per-vehicle columns
    forbidden_vehicle_cols = {"vehicle_id", "trip_id", "veh_id", "depart_time"}
    if any(col in df.columns for col in forbidden_vehicle_cols):
        raise ValueError(
            "DataFrame contains per-vehicle rows. "
            "The replication unit MUST be the run, not the vehicle (§6.3)."
        )

    if metric not in df.columns:
        raise ValueError(f"Metric column '{metric}' not found in DataFrame.")
    if arm_col not in df.columns:
        raise ValueError(f"Arm column '{arm_col}' not found in DataFrame.")
    if seed_col not in df.columns:
        raise ValueError(f"Seed column '{seed_col}' not found in DataFrame.")

    # Filter arms
    df_a = df.filter(pl.col(arm_col) == arm_a)
    df_b = df.filter(pl.col(arm_col) == arm_b)

    if df_a.height == 0:
        raise ValueError(f"No rows found for arm '{arm_a}' in column '{arm_col}'.")
    if df_b.height == 0:
        raise ValueError(f"No rows found for arm '{arm_b}' in column '{arm_col}'.")

    # Check for duplicate seeds per arm (non-run-level data)
    if df_a.select(seed_col).is_duplicated().any():
        raise ValueError(
            f"Multiple rows found for same seed in arm '{arm_a}'. "
            "Data must be aggregated to one summary number per run (§6.3)."
        )
    if df_b.select(seed_col).is_duplicated().any():
        raise ValueError(
            f"Multiple rows found for same seed in arm '{arm_b}'. "
            "Data must be aggregated to one summary number per run (§6.3)."
        )

    # Join on seed_col to obtain paired observations
    paired = df_a.select([seed_col, pl.col(metric).alias("val_a")]).join(
        df_b.select([seed_col, pl.col(metric).alias("val_b")]),
        on=seed_col,
        how="inner",
    )

    n = paired.height
    if n < 2:
        raise ValueError(f"Paired comparison requires at least 2 common seeds, found {n}.")

    a_vals = paired["val_a"].to_numpy().astype(np.float64)
    b_vals = paired["val_b"].to_numpy().astype(np.float64)
    diffs = a_vals - b_vals

    mean_a = float(np.mean(a_vals))
    mean_b = float(np.mean(b_vals))
    mean_diff = float(np.mean(diffs))

    # Relative effect: mean_diff / mean_b (or 0.0 if mean_b == 0.0)
    rel_effect = mean_diff / mean_b if mean_b != 0.0 else 0.0

    # Paired t-test p-value
    std_diff = float(np.std(diffs, ddof=1))
    if std_diff == 0.0:
        p_val = 1.0 if mean_diff == 0.0 else 0.0
    else:
        t_stat = mean_diff / (std_diff / math.sqrt(n))
        p_val = 2.0 * (1.0 - NormalDist().cdf(abs(t_stat)))
        p_val = max(0.0, min(1.0, p_val))

    # Resampling / Bootstrap (10,000 resamples)
    rng = np.random.default_rng(master_seed)
    indices = rng.integers(0, n, size=(n_resamples, n))

    boot_a = a_vals[indices]
    boot_b = b_vals[indices]
    boot_diffs = boot_a - boot_b

    boot_mean_diffs = np.mean(boot_diffs, axis=1)
    boot_mean_b = np.mean(boot_b, axis=1)

    # Avoid div by zero in bootstrap relative effect
    safe_boot_b = np.where(boot_mean_b == 0.0, 1e-9, boot_mean_b)
    boot_rel_effects = boot_mean_diffs / safe_boot_b

    # Jackknife estimates
    jack_indices = np.array([np.delete(np.arange(n), i) for i in range(n)])
    jack_a = a_vals[jack_indices]
    jack_b = b_vals[jack_indices]
    jack_diffs = jack_a - jack_b

    jack_mean_diffs = np.mean(jack_diffs, axis=1)
    jack_mean_b = np.mean(jack_b, axis=1)
    safe_jack_b = np.where(jack_mean_b == 0.0, 1e-9, jack_mean_b)
    jack_rel_effects = jack_mean_diffs / safe_jack_b

    # Compute BCa CIs
    ci_lower, ci_upper = _bca_interval(mean_diff, boot_mean_diffs, jack_mean_diffs, alpha=alpha)
    rel_ci_lower, rel_ci_upper = _bca_interval(
        rel_effect, boot_rel_effects, jack_rel_effects, alpha=alpha
    )

    return PairedResult(
        metric=metric,
        arm_a=arm_a,
        arm_b=arm_b,
        mean_a=mean_a,
        mean_b=mean_b,
        mean_diff=mean_diff,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        relative_effect=rel_effect,
        relative_ci_lower=rel_ci_lower,
        relative_ci_upper=rel_ci_upper,
        n=n,
        p_value=p_val,
    )


def required_replications(sigma_d: float, mde: float) -> int:
    """Compute required replications n ≈ 7.85 · (sigma_d / mde)² for 80% power at 5% level.

    07_EXPERIMENT_METHODOLOGY.md §7.4.
    """
    if mde <= 0.0:
        raise ValueError(f"MDE (minimum detectable effect) must be positive, got {mde}")
    if sigma_d < 0.0:
        raise ValueError(f"sigma_d must be non-negative, got {sigma_d}")

    n_approx = 7.85 * ((sigma_d / mde) ** 2)
    return math.ceil(n_approx)


def holm_bonferroni(pvalues: Sequence[float], alpha: float = 0.05) -> list[bool]:
    """Apply Holm-Bonferroni step-down procedure for family-wise error rate control.

    07_EXPERIMENT_METHODOLOGY.md §7.5.
    Returns list of booleans where True indicates rejection of null hypothesis
    (statistically significant) and False indicates failure to reject.
    """
    m = len(pvalues)
    if m == 0:
        return []

    # Pair each p-value with its original index
    indexed_pvals = sorted(enumerate(pvalues), key=lambda x: x[1])

    rejected = [False] * m
    for k, (original_idx, p_val) in enumerate(indexed_pvals):
        threshold = alpha / float(m - k)
        if p_val <= threshold:
            rejected[original_idx] = True
        else:
            # Stop step-down procedure: hypothesis k and all subsequent are not rejected
            break

    return rejected
