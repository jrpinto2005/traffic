"""`RunPhase` and `MeasurementWindow` (D-018): three phases, a half-open window."""

from __future__ import annotations

import pytest

from traffic_lab.metrics import MeasurementWindow, RunPhase


def test_phase_values_are_the_contracts() -> None:
    assert [p.value for p in RunPhase] == ["warmup", "measurement", "cooldown"]


def test_the_window_is_half_open() -> None:
    window = MeasurementWindow(start_s=300.0, end_s=900.0)
    assert window.phase(0.0) is RunPhase.WARMUP
    assert window.phase(299.0) is RunPhase.WARMUP
    assert window.phase(300.0) is RunPhase.MEASUREMENT
    assert window.phase(899.0) is RunPhase.MEASUREMENT
    assert window.phase(900.0) is RunPhase.COOLDOWN
    assert window.contains(300.0) and not window.contains(900.0)
    assert window.duration_s == 600.0


@pytest.mark.parametrize(("start", "end"), [(10.0, 10.0), (20.0, 10.0), (-1.0, 10.0)])
def test_an_empty_or_negative_window_is_rejected(start: float, end: float) -> None:
    with pytest.raises(ValueError, match="start_s < end_s"):
        MeasurementWindow(start_s=start, end_s=end)
