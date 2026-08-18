"""`traffic-lab run <config>` CLI stub invariants (T1.1 acceptance criteria).

Uses a self-contained fixture config rather than configs/smoke.yaml so these tests
do not depend on that file's existence; the smoke-config-specific acceptance check
lives in test_smoke_config.py alongside the fixture itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from traffic_lab.experiments.cli import run_command

VALID_CONFIG_YAML = (
    "name: fixture\nmaster_seed: 0\nwarmup_s: 60.0\n"
    "measurement_s: 300.0\ncooldown_s: 60.0\nwarmup_design: self\n"
)


def test_run_valid_config_prints_complete_manifest_and_exits_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = tmp_path / "fixture.yaml"
    config_path.write_text(VALID_CONFIG_YAML)

    exit_code = run_command(config_path)
    captured = capsys.readouterr()

    assert exit_code == 0
    manifest = json.loads(captured.out)
    expected_fields = {
        "config_hash",
        "config",
        "code_version",
        "sumo_version",
        "seeds",
        "decision_interval_s",
        "warmup_design",
        "validity",
        "trips",
        "wall_clock_s",
        "peak_memory_mb",
    }
    assert expected_fields <= manifest.keys()


def test_run_invalid_config_exits_1_and_names_the_field(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad_config = tmp_path / "bad.yaml"
    bad_config.write_text(
        "name: bad\nmaster_seed: 0\nwarmup_s: 60.0\nmeasurement_s: -5.0\ncooldown_s: 60.0\n"
    )
    exit_code = run_command(bad_config)
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "measurement_s" in captured.err


def test_run_missing_config_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_command(tmp_path / "missing.yaml")
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "missing.yaml" in captured.err
