"""A run's manifest reproduces the run on its own (`06_ARCHITECTURE.md` SS7, register v1.12).

It records the full resolved spec -- run ID, seed index, transport, step
length, Δt, the controller by qualified name and bound arguments, D-008's N,
the `RunConfig` -- the net and routes files by content hash, and the seeds;
`config_hash` covers all of it.
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.backend.conftest import DEMAND_END_S, Scenario
from tests.experiments.controllers import CycleFrom, hold_first
from tests.experiments.support import CONFIG, make_spec
from tests.generated_scenario import one_flow_per_movement
from traffic_lab.experiments.config import canonical_hash
from traffic_lab.experiments.runner import MANIFEST_FILE, RunSpec, controller_identity, run_many
from traffic_lab.experiments.seeds import derive_run_seeds


def _manifest(spec: RunSpec) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads((spec.output_dir / MANIFEST_FILE).read_text())
    return manifest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_manifest_records_the_resolved_run(scenario: Scenario, tmp_path: Path) -> None:
    spec = make_spec(
        scenario,
        tmp_path / "cycle",
        functools.partial(CycleFrom, start_s=30.0),
        seed_index=3,
    )
    run_many([spec], tmp_path / "experiment", jobs=1)
    manifest = _manifest(spec)

    assert manifest["config"] == {
        "run_id": "cycle",
        "seed_index": 3,
        "transport": "libsumo",
        "step_length_s": 1.0,
        "decision_interval_s": 5.0,
        "controller": {
            "factory": "tests.experiments.controllers.CycleFrom",
            "args": [],
            "keywords": {"start_s": 30.0},
        },
        "gridlock_steps": manifest["config"]["gridlock_steps"],
        "net_sha256": _sha256(scenario.net),
        "routes_sha256": _sha256(scenario.routes),
        "run_config": CONFIG.model_dump(mode="json"),
    }
    assert manifest["seeds"] == derive_run_seeds(CONFIG.master_seed, 3)
    assert manifest["config_hash"] == canonical_hash(
        {"config": manifest["config"], "seeds": manifest["seeds"]}
    )
    assert manifest["decision_interval_s"] == {"tests.experiments.controllers.CycleFrom": 5.0}


def test_the_hash_tells_apart_seed_indices_and_route_contents(
    scenario: Scenario, tmp_path: Path
) -> None:
    routes = tmp_path / "demand.rou.xml"
    shutil.copy(scenario.routes, routes)
    base = make_spec(scenario, tmp_path / "base", hold_first, run_id="r", routes=routes)
    other_seed = dataclasses.replace(base, seed_index=1, output_dir=tmp_path / "seed1")
    run_many([base, dataclasses.replace(other_seed, run_id="r1")], tmp_path / "e1", jobs=2)

    # Same spec, same routes path; only the file's content differs.
    one_flow_per_movement(scenario.built, routes, DEMAND_END_S, period_s=45.0)
    other_routes = dataclasses.replace(base, output_dir=tmp_path / "routes2")
    run_many([other_routes], tmp_path / "e2", jobs=1)

    a, b, c = (_manifest(base), _manifest(other_seed), _manifest(other_routes))
    assert len({a["config_hash"], b["config_hash"], c["config_hash"]}) == 3
    changed = {k for k in a["config"] if a["config"][k] != c["config"][k]}
    assert changed == {"routes_sha256"}
    assert a["seeds"] == c["seeds"]


def test_a_run_hashes_the_same_wherever_its_files_live(scenario: Scenario, tmp_path: Path) -> None:
    """Paths are not in the record: the same files elsewhere are the same run."""
    elsewhere = tmp_path / "copy"
    elsewhere.mkdir()
    net, routes = shutil.copy(scenario.net, elsewhere), shutil.copy(scenario.routes, elsewhere)
    here = make_spec(scenario, tmp_path / "here", hold_first, run_id="r")
    there = dataclasses.replace(here, net=Path(net), routes=Path(routes), output_dir=tmp_path / "x")
    run_many([here], tmp_path / "e1", jobs=1)
    run_many([there], tmp_path / "e2", jobs=1)
    assert _manifest(here)["config_hash"] == _manifest(there)["config_hash"]


def _local_factory() -> Any:
    def factory(network: Any) -> Any:
        return hold_first(network)

    return factory


@pytest.mark.parametrize(
    "factory",
    [
        lambda network: hold_first(network),
        _local_factory(),
        functools.partial(CycleFrom, start_s=object()),  # type: ignore[arg-type]
    ],
    ids=["lambda", "closure", "non-json-argument"],
)
def test_a_factory_the_manifest_cannot_name_is_refused(
    scenario: Scenario, tmp_path: Path, factory: Any
) -> None:
    with pytest.raises(ValueError, match="controller factory"):
        make_spec(scenario, tmp_path, factory)


def test_controller_identity_of_plain_and_partial_factories() -> None:
    assert controller_identity(hold_first) == {
        "factory": "tests.experiments.controllers.hold_first",
        "args": [],
        "keywords": {},
    }
    assert controller_identity(functools.partial(CycleFrom, start_s=5.0, decision_interval_s=1.0))[
        "keywords"
    ] == {"start_s": 5.0, "decision_interval_s": 1.0}
