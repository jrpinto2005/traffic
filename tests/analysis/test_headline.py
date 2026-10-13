"""Tests for headline figure, results table, and validity report generation.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from traffic_lab.analysis.headline import (
    generate_headline_figure,
    generate_results_table,
    generate_validity_report,
)


def test_generate_validity_report() -> None:
    """Test validity report aggregation over run summary flags."""
    df = pl.DataFrame(
        {
            "run_id": ["r1", "r2", "r3"],
            "valid": [True, False, False],
            "teleports": [0, 1, 0],
            "gridlock_detected": [0, 0, 1],
            "snapshot_mismatch": [0, 0, 0],
            "invalid_causes": ["", "teleport", "gridlock"],
        }
    )

    report = generate_validity_report(df)
    assert report["total_runs"] == 3
    assert report["valid_runs"] == 1
    assert report["invalid_runs"] == 2
    assert report["teleports"] == 1
    assert report["gridlock_detected"] == 1
    assert report["snapshot_mismatch"] == 0


def test_generate_results_table() -> None:
    """Test results table formatting across arms and demand levels."""
    df = pl.DataFrame(
        {
            "demand_level": [0.5, 0.5, 0.8, 0.8],
            "controller": ["webster", "actuated", "webster", "actuated"],
            "all.delay_s": [30.0, 25.0, 50.0, 40.0],
            "all.trip_completion_rate": [1.0, 1.0, 0.95, 0.98],
        }
    )

    table = generate_results_table(df)
    assert table.height == 4
    assert "demand_level" in table.columns
    assert "controller" in table.columns
    assert "mean" in table.columns
    assert "trip_completion_rate" in table.columns


def test_generate_headline_figure(tmp_path: Path) -> None:
    """Test figure generation to an output PNG file."""
    df = pl.DataFrame(
        {
            "seed_index": [0, 1, 0, 1, 0, 1, 0, 1],
            "demand_level": [0.5, 0.5, 0.5, 0.5, 0.8, 0.8, 0.8, 0.8],
            "controller": [
                "webster",
                "webster",
                "actuated",
                "actuated",
                "webster",
                "webster",
                "actuated",
                "actuated",
            ],
            "all.delay_s": [30.0, 32.0, 25.0, 27.0, 50.0, 52.0, 40.0, 42.0],
        }
    )

    fig_path = tmp_path / "test_headline.png"
    generate_headline_figure(df, fig_path)

    assert fig_path.exists()
    assert fig_path.stat().st_size > 0
