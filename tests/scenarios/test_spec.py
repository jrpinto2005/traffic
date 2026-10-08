"""`IntersectionSpec` / `PhaseSpec` validation (T1.3 contract, Amendment A4)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from traffic_lab.domain.network import SignalTiming, TurnDirection
from traffic_lab.scenarios import IntersectionSpec, PhaseSpec

TIMING = SignalTiming(min_green_s=10.0, max_green_s=60.0, yellow_s=3.0, all_red_s=2.0)
PHASES = [PhaseSpec(green=[(0, TurnDirection.THROUGH)])]


def _spec(**overrides: Any) -> IntersectionSpec:
    fields: dict[str, Any] = {"phases": PHASES, "timing": TIMING}
    fields.update(overrides)
    return IntersectionSpec(**fields)


def test_contract_defaults() -> None:
    spec = _spec()
    assert spec.approaches == 4
    assert spec.lanes_per_approach == 2
    assert spec.approach_length_m == 200.0
    assert spec.speed_limit_mps == 13.89
    assert spec.turn_lanes is False


def test_timing_is_required() -> None:
    """A4: required, no default -- it affects results."""
    with pytest.raises(ValidationError, match="timing"):
        IntersectionSpec(phases=PHASES)  # type: ignore[call-arg]


def test_phases_are_required() -> None:
    with pytest.raises(ValidationError, match="phases"):
        IntersectionSpec(timing=TIMING)  # type: ignore[call-arg]


def test_fewer_than_three_approaches_is_rejected() -> None:
    with pytest.raises(ValidationError, match="approaches"):
        _spec(approaches=2)


def test_a_phase_naming_a_missing_approach_is_rejected() -> None:
    with pytest.raises(ValidationError, match=r"\(4, through\)"):
        _spec(phases=[PhaseSpec(green=[(4, TurnDirection.THROUGH)])])


def test_turn_lanes_is_rejected_at_m1() -> None:
    with pytest.raises(ValidationError, match="turn_lanes=True is not specified at M1"):
        _spec(turn_lanes=True)


def test_a_zero_yellow_is_rejected() -> None:
    timing = SignalTiming(min_green_s=10.0, max_green_s=60.0, yellow_s=0.0, all_red_s=2.0)
    with pytest.raises(ValidationError, match="yellow_s"):
        _spec(timing=timing)


def test_unknown_keys_are_rejected() -> None:
    with pytest.raises(ValidationError, match="extra"):
        _spec(approach_count=4)


def test_the_spec_loads_from_plain_data() -> None:
    """The form a YAML scenario arrives in (T1.11 nests IntersectionSpec in its config)."""
    spec = IntersectionSpec.model_validate(
        {
            "approaches": 3,
            "phases": [{"green": [[0, "left"], [1, "right"]]}],
            "timing": {"min_green_s": 8, "max_green_s": 0, "yellow_s": 3, "all_red_s": 0},
        }
    )
    assert spec.phases[0].green == [(0, TurnDirection.LEFT), (1, TurnDirection.RIGHT)]
    assert spec.timing == SignalTiming(min_green_s=8, max_green_s=0, yellow_s=3, all_red_s=0)
