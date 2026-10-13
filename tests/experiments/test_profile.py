"""Tests for the profiling harness and CLI profile subcommand (T1.13)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from traffic_lab.experiments.cli import main
from traffic_lab.experiments.profile import profile_command

SMOKE_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "smoke.yaml"


def test_profile_command_runs_on_smoke_config_and_appends_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline_file = tmp_path / "baseline.jsonl"
    exit_code = profile_command(SMOKE_CONFIG, top_n=10, baseline_path=baseline_file)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "=== Performance Profile: smoke ===" in captured.out
    assert "Wall-clock / simulated hour:" in captured.out
    assert "Top 10 hot paths" in captured.out

    assert baseline_file.exists()
    lines = baseline_file.read_text().strip().splitlines()
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["config_name"] == "smoke"
    assert record["simulated_s"] == 420.0
    assert record["wall_clock_per_simulated_hour"] > 0
    assert record["peak_memory_mb"] > 0
    assert len(record["top_hotpaths"]) == 10


def test_profile_command_respects_top_n(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    baseline_file = tmp_path / "baseline.jsonl"
    exit_code = profile_command(SMOKE_CONFIG, top_n=5, baseline_path=baseline_file)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Top 5 hot paths" in captured.out

    lines = baseline_file.read_text().strip().splitlines()
    record = json.loads(lines[0])
    assert len(record["top_hotpaths"]) == 5


def test_profile_command_regression_warning_on_degraded_performance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline_file = tmp_path / "baseline.jsonl"
    artificially_fast_record = {
        "timestamp": "2026-01-01T00:00:00Z",
        "config_name": "smoke",
        "code_version": "test",
        "sumo_version": "1.27.1",
        "wall_clock_s": 0.001,
        "simulated_s": 420.0,
        "simulated_hours": 0.116667,
        "wall_clock_per_simulated_hour": 0.008,
        "peak_memory_mb": 50.0,
        "top_hotpaths": [],
    }
    baseline_file.write_text(json.dumps(artificially_fast_record) + "\n")

    exit_code = profile_command(SMOKE_CONFIG, top_n=5, baseline_path=baseline_file)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "WARNING: Performance degradation detected!" in captured.err


def test_cli_profile_subcommand(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline_file = tmp_path / "baseline.jsonl"
    monkeypatch.setattr("traffic_lab.experiments.profile.DEFAULT_BASELINE_PATH", baseline_file)

    with pytest.raises(SystemExit) as exc_info:
        main(["profile", str(SMOKE_CONFIG), "--top", "3"])

    assert exc_info.value.code == 0
    assert baseline_file.exists()
