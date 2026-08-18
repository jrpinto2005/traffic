"""Config validation for the constraint layer, T1.7's clause of invariant 9.

`05_DOMAIN_MODEL.md` SS8 invariant 9 has three clauses. T1.2's
`validate_network()` owns the first two (`min_green_s > 0`, `max_green_s >
min_green_s` or `== 0`); this module's subject owns the third,
`decision_interval_s <= min_green_s`, because `decision_interval_s` is
controller-layer configuration and is not a field of `SignalTiming`.

The acceptance criterion is specifically that the rejection happens **at load,
with a clear error, not at runtime** -- so every test here provokes the failure
by building the config or the layer, never by stepping or submitting.
"""

from __future__ import annotations

import dataclasses

import pytest
from pydantic import ValidationError

from tests.domain.factories import build_valid_network
from traffic_lab.control.constraint_layer import (
    ConstraintConfigError,
    ConstraintLayerConfig,
    validate_decision_interval,
)
from traffic_lab.domain.network import SignalTiming

# The fixture network's single intersection has min_green_s = 5.0.
FIXTURE_MIN_GREEN_S = 5.0


def test_a_valid_config_is_accepted() -> None:
    config = ConstraintLayerConfig(decision_interval_s=5.0, step_length_s=1.0)
    assert config.decision_interval_s == 5.0
    validate_decision_interval(config, build_valid_network())


def test_invariant_9_decision_interval_above_min_green_is_rejected_at_load() -> None:
    config = ConstraintLayerConfig(decision_interval_s=10.0, step_length_s=1.0)
    with pytest.raises(ConstraintConfigError) as excinfo:
        validate_decision_interval(config, build_valid_network())
    assert excinfo.value.invariant == 9
    message = str(excinfo.value)
    assert "10.0" in message
    assert str(FIXTURE_MIN_GREEN_S) in message


def test_invariant_9_decision_interval_equal_to_min_green_is_accepted() -> None:
    """The clause is `<=`, not `<`: Dt may be exactly the minimum green."""
    config = ConstraintLayerConfig(decision_interval_s=FIXTURE_MIN_GREEN_S, step_length_s=1.0)
    validate_decision_interval(config, build_valid_network())


def test_invariant_9_is_checked_against_every_intersection() -> None:
    """Dt is one value applied to all intersections, so the tightest one binds."""
    network = build_valid_network()
    tight = dataclasses.replace(
        network.signalized_intersections[0],
        timing=SignalTiming(min_green_s=2.0, max_green_s=60.0, yellow_s=3.0, all_red_s=2.0),
    )
    network = dataclasses.replace(network, signalized_intersections=(tight,))

    config = ConstraintLayerConfig(decision_interval_s=4.0, step_length_s=1.0)
    with pytest.raises(ConstraintConfigError) as excinfo:
        validate_decision_interval(config, network)
    assert excinfo.value.invariant == 9


def test_decision_interval_must_be_a_multiple_of_the_step_length() -> None:
    """D-020's other stated constraint on Dt."""
    with pytest.raises(ValidationError) as excinfo:
        ConstraintLayerConfig(decision_interval_s=2.5, step_length_s=1.0)
    assert "step_length_s" in str(excinfo.value)


def test_a_fractional_step_length_that_divides_exactly_is_accepted() -> None:
    """`0.3 % 0.1` is `0.0999...` in binary floating point; the check must not
    reject a config that is exactly right."""
    ConstraintLayerConfig(decision_interval_s=0.3, step_length_s=0.1)


def test_non_positive_intervals_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ConstraintLayerConfig(decision_interval_s=0.0, step_length_s=1.0)
    with pytest.raises(ValidationError):
        ConstraintLayerConfig(decision_interval_s=1.0, step_length_s=0.0)


def test_an_unknown_config_key_is_rejected() -> None:
    """`extra="forbid"`: a config key that never reaches the simulator is worse
    than an absent one (D-031 anti-pattern list)."""
    with pytest.raises(ValidationError):
        ConstraintLayerConfig(
            decision_interval_s=5.0,
            step_length_s=1.0,
            min_green_s=5.0,  # type: ignore[call-arg]
        )
