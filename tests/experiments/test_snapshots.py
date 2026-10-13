"""Tests for initial-state snapshot keying, production, caching, loading,
and design rules (T1.6, D-018, D-032)."""

from __future__ import annotations

import dataclasses
import functools
from pathlib import Path

import pytest

from tests.backend.conftest import Scenario, make_config
from tests.experiments.controllers import CycleFrom, hold_first
from tests.experiments.support import make_spec, watch
from traffic_lab.backend import SumoBackend
from traffic_lab.backend.config import SnapshotMismatchError
from traffic_lab.experiments.config import RunConfig
from traffic_lab.experiments.runner import MANIFEST_FILE, run_one
from traffic_lab.experiments.snapshots import WarmupDesign, load_into, produce, snapshot_key


def test_snapshot_key_formatting() -> None:
    key = snapshot_key("abcd1234hash", 1.0, 42, WarmupDesign.NEUTRAL_SNAPSHOT)
    assert key == "abcd1234hash_1.0_42_neutral_snapshot"

    key2 = snapshot_key("abcd1234hash", 0.8, 100, WarmupDesign.SELF)
    assert key2 == "abcd1234hash_0.8_100_self"


def test_snapshot_production_and_loading_yields_identical_truestate(
    scenario: Scenario, tmp_path: Path
) -> None:
    snapshot = tmp_path / "snapshot.xml"
    produce(
        scenario.net,
        scenario.routes,
        scenario.network,
        warmup_s=60.0,
        output_path=snapshot,
        step_length_s=1.0,
        seed=42,
    )
    assert snapshot.exists()
    assert snapshot.with_name(f"{snapshot.name}.manifest.json").exists()

    backend = SumoBackend()
    backend.start(scenario.net, scenario.routes, make_config(), network=scenario.network)
    try:
        load_into(backend, snapshot)
        loaded_state = backend.project()
        assert loaded_state.time_s == 60.0
    finally:
        backend.close()


def test_loading_snapshot_with_mismatched_network_fails(scenario: Scenario, tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.xml"
    produce(
        scenario.net,
        scenario.routes,
        scenario.network,
        warmup_s=30.0,
        output_path=snapshot,
    )

    sidecar = snapshot.with_name(f"{snapshot.name}.manifest.json")
    content = sidecar.read_text().replace('"network_sha256": "', '"network_sha256": "different_')
    sidecar.write_text(content)

    backend = SumoBackend()
    backend.start(scenario.net, scenario.routes, make_config(), network=scenario.network)
    try:
        with pytest.raises(SnapshotMismatchError, match="network sha256="):
            load_into(backend, snapshot)
    finally:
        backend.close()


def test_loading_snapshot_with_mismatched_sumo_version_fails(
    scenario: Scenario, tmp_path: Path
) -> None:
    snapshot = tmp_path / "snapshot.xml"
    produce(
        scenario.net,
        scenario.routes,
        scenario.network,
        warmup_s=30.0,
        output_path=snapshot,
    )

    sidecar = snapshot.with_name(f"{snapshot.name}.manifest.json")
    import json

    data = json.loads(sidecar.read_text())
    data["sumo_version"] = "v0_0_0_mismatch"
    sidecar.write_text(json.dumps(data))

    backend = SumoBackend()
    backend.start(scenario.net, scenario.routes, make_config(), network=scenario.network)
    try:
        with pytest.raises(SnapshotMismatchError, match="version-sensitive"):
            load_into(backend, snapshot)
    finally:
        backend.close()


def test_two_arms_under_neutral_snapshot_start_from_identical_state(
    scenario: Scenario, tmp_path: Path
) -> None:
    cfg = RunConfig.model_validate(
        {
            "name": "neutral_test",
            "master_seed": 42,
            "warmup_s": 60.0,
            "measurement_s": 300.0,
            "cooldown_s": 0.0,
            "warmup_design": "neutral_snapshot",
        }
    )
    spec_hold = make_spec(scenario, tmp_path / "hold", hold_first, config=cfg)
    spec_cycle = dataclasses.replace(
        spec_hold,
        run_id="cycle",
        output_dir=tmp_path / "cycle",
        controller_factory=functools.partial(CycleFrom, start_s=60.0),
    )

    run1 = watch(spec_hold)
    run2 = watch(spec_cycle)

    state1_at_load = next(s for s in run1.states if s.time_s == 61.0)
    state2_at_load = next(s for s in run2.states if s.time_s == 61.0)

    assert state1_at_load == state2_at_load


def test_warmup_design_appears_in_manifest(scenario: Scenario, tmp_path: Path) -> None:
    spec = make_spec(scenario, tmp_path / "run_self", hold_first)
    run_one(spec)

    import json

    manifest = json.loads((spec.output_dir / MANIFEST_FILE).read_text())
    assert manifest["warmup_design"] == "self"

    cfg_neutral = RunConfig.model_validate(
        {
            "name": "neutral_manifest_test",
            "master_seed": 42,
            "warmup_s": 30.0,
            "measurement_s": 60.0,
            "cooldown_s": 0.0,
            "warmup_design": "neutral_snapshot",
        }
    )
    spec_neutral = make_spec(scenario, tmp_path / "run_neutral", hold_first, config=cfg_neutral)
    run_one(spec_neutral)

    manifest_neutral = json.loads((spec_neutral.output_dir / MANIFEST_FILE).read_text())
    assert manifest_neutral["warmup_design"] == "neutral_snapshot"
