"""Config loading and validation invariants (T1.1 contract)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from traffic_lab.experiments.config import RunConfig, compute_config_hash, load_config

VALID = {
    "name": "smoke",
    "master_seed": 0,
    "warmup_s": 60.0,
    "measurement_s": 300.0,
    "cooldown_s": 60.0,
    "warmup_design": "self",
}


def _write(tmp_path: Path, text: str, name: str = "config.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def test_warmup_design_defaults_to_self() -> None:
    values = dict(VALID)
    del values["warmup_design"]
    assert RunConfig.model_validate(values).warmup_design == "self"


@pytest.mark.parametrize(
    "override,bad_value",
    [
        ("measurement_s", -5.0),  # must be > 0
        ("measurement_s", 0.0),  # must be > 0, boundary excluded
        ("warmup_s", -1.0),  # must be >= 0
        ("cooldown_s", -1.0),  # must be >= 0
        ("master_seed", -1),  # must be >= 0
        ("name", ""),  # must be non-empty
        ("warmup_design", "bogus"),  # not in the Literal
    ],
)
def test_invalid_field_is_rejected_and_named(override: str, bad_value: object) -> None:
    """An invalid config fails at load, naming the offending field (ticket acceptance)."""
    values = {**VALID, override: bad_value}
    with pytest.raises(ValidationError) as excinfo:
        RunConfig.model_validate(values)
    assert override in str(excinfo.value)


def test_unknown_field_is_rejected() -> None:
    """A stray/misspelled key fails rather than being silently ignored (D-031 anti-pattern)."""
    values = {**VALID, "scenario": "not_yet_built"}
    with pytest.raises(ValidationError, match="scenario"):
        RunConfig.model_validate(values)


def test_load_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "does_not_exist.yaml")


def test_load_config_invalid_yaml_fails_before_use(tmp_path: Path) -> None:
    path = _write(tmp_path, "name: bad\nmeasurement_s: -5.0\nmaster_seed: 0\n")
    with pytest.raises(ValidationError):
        load_config(path)


def test_config_hash_is_deterministic() -> None:
    config = RunConfig.model_validate(VALID)
    assert compute_config_hash(config) == compute_config_hash(config)


def test_config_hash_is_stable_across_instances(tmp_path: Path) -> None:
    """Same logical config, loaded independently twice, hashes identically.

    This is the executable form of the ticket's "same config produces the same
    config_hash across runs and machines" criterion: the hash must depend only
    on field values, not on object identity, dict insertion order, or when it
    was computed.
    """
    path = _write(
        tmp_path,
        "name: smoke\nmaster_seed: 0\nwarmup_s: 60.0\n"
        "measurement_s: 300.0\ncooldown_s: 60.0\nwarmup_design: self\n",
    )
    first = compute_config_hash(load_config(path))
    second = compute_config_hash(load_config(path))
    assert first == second
    # Pinned so a future accidental change to the hashing scheme is caught here,
    # not discovered as a silent reproducibility break.
    assert first == "4f430f72546ff094a4fc6f7810f9fce81dfdbc71c1c729e2ef8fbf50a33c010c"


def test_config_hash_changes_with_a_field() -> None:
    base = RunConfig.model_validate(VALID)
    changed = RunConfig.model_validate({**VALID, "master_seed": 1})
    assert compute_config_hash(base) != compute_config_hash(changed)


def test_config_hash_independent_of_key_order(tmp_path: Path) -> None:
    ordered = _write(
        tmp_path,
        "name: smoke\nmaster_seed: 0\nwarmup_s: 60.0\n"
        "measurement_s: 300.0\ncooldown_s: 60.0\nwarmup_design: self\n",
    )
    reordered = _write(
        tmp_path,
        "warmup_design: self\ncooldown_s: 60.0\nmeasurement_s: 300.0\n"
        "warmup_s: 60.0\nmaster_seed: 0\nname: smoke\n",
        name="reordered.yaml",
    )
    assert compute_config_hash(load_config(ordered)) == compute_config_hash(load_config(reordered))
