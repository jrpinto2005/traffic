"""Tests for statistical analysis functions in traffic_lab.analysis.stats.

Validates BCa bootstrap CI, required replications formula, Holm-Bonferroni,
and anti-aggregation guard.
"""

from __future__ import annotations

import math

import numpy as np
import polars as pl
import pytest

from traffic_lab.analysis.stats import (
    _bca_interval,
    holm_bonferroni,
    paired_difference,
    required_replications,
)


def test_bca_interval_reference_dataset() -> None:
    """BCa bootstrap reproduces a known reference interval on a textbook dataset.

    Dataset: paired differences d = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].
    Mean = 5.5, std = 3.027.
    """
    obs_diffs = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    obs_mean = float(np.mean(obs_diffs))
    n = len(obs_diffs)

    rng = np.random.default_rng(12345)
    boot_indices = rng.integers(0, n, size=(10000, n))
    boot_means = np.mean(obs_diffs[boot_indices], axis=1)

    jack_indices = np.array([np.delete(np.arange(n), i) for i in range(n)])
    jack_means = np.mean(obs_diffs[jack_indices], axis=1)

    q_low, q_high = _bca_interval(obs_mean, boot_means, jack_means, alpha=0.05)

    # Expected approx 95% BCa CI bounds for 1..10
    assert 3.2 <= q_low <= 4.2
    assert 6.8 <= q_high <= 7.8


def test_required_replications_hand_computed() -> None:
    """required_replications matches hand-computed values.

    Formula: n ≈ 7.85 * (sigma_d / MDE)^2.
    For sigma_d = 10.0 and MDE = 2.0:
    7.85 * (10 / 2)^2 = 7.85 * 25 = 196.25 -> math.ceil = 197.
    """
    assert required_replications(sigma_d=10.0, mde=2.0) == 197
    assert required_replications(sigma_d=5.0, mde=5.0) == 8
    with pytest.raises(ValueError, match="must be positive"):
        required_replications(sigma_d=10.0, mde=0.0)


def test_holm_bonferroni_hand_worked() -> None:
    """Holm-Bonferroni matches a hand-worked example.

    p-values: [0.01, 0.04, 0.03]
    Sorted: p_(1) = 0.01, p_(2) = 0.03, p_(3) = 0.04 with m = 3, alpha = 0.05.
    1. k=0: threshold = 0.05 / (3-0) = 0.01667. p_(1)=0.01 <= 0.01667 -> Reject p=0.01.
    2. k=1: threshold = 0.05 / (3-1) = 0.025. p_(2)=0.03 > 0.025 -> Stop. p=0.03, 0.04 not rejected.
    Expected result for [0.01, 0.04, 0.03] -> [True, False, False].
    """
    pvals = [0.01, 0.04, 0.03]
    rejected = holm_bonferroni(pvals, alpha=0.05)
    assert rejected == [True, False, False]


def test_anti_aggregation_guard_vehicle_rows() -> None:
    """Assertion test enforcing that analysis NEVER aggregates per-vehicle rows into an interval.

    Rule 1 (§6.3, D-017): The replication unit is the run, not the vehicle.
    """
    vehicle_df = pl.DataFrame(
        {
            "vehicle_id": ["v1", "v2", "v3", "v4"],
            "seed_index": [0, 0, 1, 1],
            "controller": ["webster", "webster", "actuated", "actuated"],
            "delay_s": [10.0, 12.0, 8.0, 9.0],
        }
    )

    with pytest.raises(ValueError, match="DataFrame contains per-vehicle rows"):
        paired_difference(
            vehicle_df,
            metric="delay_s",
            arm_a="actuated",
            arm_b="webster",
        )


def test_anti_aggregation_duplicate_seeds() -> None:
    """paired_difference raises ValueError if duplicate seed rows exist for an arm."""
    dup_df = pl.DataFrame(
        {
            "seed_index": [0, 0, 1, 1],
            "controller": ["webster", "webster", "actuated", "actuated"],
            "delay_s": [10.0, 12.0, 8.0, 9.0],
        }
    )

    with pytest.raises(ValueError, match="Multiple rows found for same seed"):
        paired_difference(
            dup_df,
            metric="delay_s",
            arm_a="actuated",
            arm_b="webster",
        )


def test_paired_difference_run_level_data() -> None:
    """paired_difference correctly computes statistics over run-level summary data."""
    # 5 paired seeds, run-level summary per seed
    data = pl.DataFrame(
        {
            "seed_index": [0, 1, 2, 3, 4, 0, 1, 2, 3, 4],
            "controller": [
                "actuated",
                "actuated",
                "actuated",
                "actuated",
                "actuated",
                "webster",
                "webster",
                "webster",
                "webster",
                "webster",
            ],
            "delay_s": [20.0, 22.0, 21.0, 23.0, 24.0, 25.0, 27.0, 26.0, 28.0, 29.0],
        }
    )

    result = paired_difference(
        data,
        metric="delay_s",
        arm_a="actuated",
        arm_b="webster",
        n_resamples=500,
        master_seed=42,
    )

    assert result.n == 5
    assert math.isclose(result.mean_a, 22.0)
    assert math.isclose(result.mean_b, 27.0)
    assert math.isclose(result.mean_diff, -5.0)
    assert result.ci_lower <= result.mean_diff <= result.ci_upper
    assert result.relative_effect < 0.0
