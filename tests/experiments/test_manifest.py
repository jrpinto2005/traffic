"""RunManifest construction invariants (T1.1 contract; 06_ARCHITECTURE.md SS7)."""

from __future__ import annotations

import dataclasses

from traffic_lab.domain.state import RunCounters
from traffic_lab.experiments.config import RunConfig, compute_config_hash
from traffic_lab.experiments.manifest import build_manifest
from traffic_lab.experiments.seeds import SEED_STREAMS

CONFIG = RunConfig.model_validate(
    {
        "name": "smoke",
        "master_seed": 0,
        "warmup_s": 60.0,
        "measurement_s": 300.0,
        "cooldown_s": 60.0,
        "warmup_design": "self",
    }
)


def test_manifest_config_hash_matches_config() -> None:
    manifest = build_manifest(CONFIG, wall_clock_s=1.0, peak_memory_mb=10.0)
    assert manifest.config_hash == compute_config_hash(CONFIG)


def test_manifest_records_all_seed_streams() -> None:
    manifest = build_manifest(CONFIG, wall_clock_s=1.0, peak_memory_mb=10.0)
    assert set(manifest.seeds) == set(SEED_STREAMS)


def test_manifest_validity_and_trips_present_even_when_zero() -> None:
    """D-008 / D-022: counters are always recorded, even at zero — never omitted."""
    manifest = build_manifest(CONFIG, wall_clock_s=1.0, peak_memory_mb=10.0)
    assert manifest.validity == {
        "teleports": 0,
        "insertion_failures": 0,
        "gridlock_detected": False,
    }
    assert manifest.trips == {
        "arrived_at_sink": 0,
        "arrived_mid_link": 0,
        "still_in_network": 0,
    }


def test_manifest_counter_names_are_run_counters_field_names() -> None:
    """One vocabulary for the six D-008 / D-022 counters, not two.

    The runner fills `validity` and `trips` from `RunCounters`. If the names
    differ it needs a mapping, and a typo in that mapping drops a validity
    counter without failing anything.
    """
    manifest = build_manifest(CONFIG, wall_clock_s=1.0, peak_memory_mb=10.0)
    run_counter_names = {field.name for field in dataclasses.fields(RunCounters)}
    assert set(manifest.validity) | set(manifest.trips) == run_counter_names
    assert set(manifest.validity).isdisjoint(manifest.trips)


def test_manifest_warmup_design_follows_config() -> None:
    neutral = RunConfig.model_validate(
        {**CONFIG.model_dump(mode="json"), "warmup_design": "neutral_snapshot"}
    )
    manifest = build_manifest(neutral, wall_clock_s=1.0, peak_memory_mb=10.0)
    assert manifest.warmup_design == "neutral_snapshot"


def test_manifest_carries_measured_wall_clock_and_memory() -> None:
    manifest = build_manifest(CONFIG, wall_clock_s=3.5, peak_memory_mb=42.0)
    assert manifest.wall_clock_s == 3.5
    assert manifest.peak_memory_mb == 42.0


def test_manifest_is_json_serialisable() -> None:
    manifest = build_manifest(CONFIG, wall_clock_s=1.0, peak_memory_mb=10.0)
    dumped = manifest.model_dump(mode="json")
    assert dumped["config_hash"] == manifest.config_hash


def test_manifest_records_sumo_warnings_at_zero_before_simulation() -> None:
    """T1.11 A2: the field is always present; the stub has run no SUMO."""
    manifest = build_manifest(CONFIG, wall_clock_s=1.0, peak_memory_mb=10.0)
    assert manifest.sumo_warnings == 0


def test_manifest_records_constraint_outcomes() -> None:
    """T1.10 Scope 4: per-outcome counters from constraint layer are surfaced in the manifest."""
    manifest = build_manifest(CONFIG, wall_clock_s=1.0, peak_memory_mb=10.0)
    assert set(manifest.constraint_outcomes) >= {
        "granted",
        "deferred",
        "held",
        "forced",
        "rejected",
    }
