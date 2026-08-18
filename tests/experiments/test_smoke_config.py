"""configs/smoke.yaml is T1.1's acceptance fixture (ticket: "used as the acceptance
fixture here and by T1.13").

Exercises the literal ticket acceptance criterion: `traffic-lab run configs/smoke.yaml`
prints a complete manifest and exits 0.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from traffic_lab.experiments.cli import run_command
from traffic_lab.experiments.config import load_config

SMOKE_CONFIG = Path("configs/smoke.yaml")


def test_smoke_config_loads_as_a_valid_run_config() -> None:
    config = load_config(SMOKE_CONFIG)
    assert config.name == "smoke"
    assert config.warmup_design == "self"


def test_cli_run_on_smoke_config_exits_0_and_prints_a_manifest(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = run_command(SMOKE_CONFIG)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"config_hash"' in captured.out
