"""`run_many`: fresh processes, reproducibility, crash isolation and outputs (T1.11 A3).

Every run here is a real SUMO run in a `spawn` worker. The common-random-numbers
and reproducibility tests are the ticket's most important: every comparison
the project will make is paired on them (D-017).
"""

from __future__ import annotations

import dataclasses
import functools
import json
import pickle
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from tests.backend.conftest import DEMAND_END_S, Scenario
from tests.experiments.controllers import (
    CRASH_MESSAGE,
    CycleFrom,
    crashing,
    exits,
    hold_first,
    segfaults,
)
from tests.experiments.routes import out_of_order_routes
from tests.experiments.support import CONFIG, Instrumented, make_spec, watch
from tests.generated_scenario import OVERLOAD_PERIOD_S, one_flow_per_movement
from traffic_lab.backend import display_state
from traffic_lab.domain.state import SignalStage, TrueState
from traffic_lab.experiments.config import RunConfig
from traffic_lab.experiments.runner import (
    EXPERIMENT_FILE,
    FAILURES_FILE,
    MANIFEST_FILE,
    RESULT_FILE,
    TRIPINFO_FILE,
    WARNING_LOG_FILE,
    RunSpec,
    run_many,
)
from traffic_lab.experiments.seeds import derive_run_seeds

#: Result columns that measure the machine rather than the run.
MACHINE_COLUMNS = ("wall_clock_s", "peak_memory_mb")

PROGRESS_LINE = re.compile(
    r"^\[\d+/\d+\] (done|invalid|failed) \S+ \| done \d+ invalid \d+ failed \d+ \| "
    r"elapsed \d+\.\d s$"
)


def _row(path: Path) -> dict[str, Any]:
    row = pl.read_parquet(path).row(0, named=True)
    return {k: v for k, v in row.items() if k not in MACHINE_COLUMNS}


def _manifest(run_dir: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads((run_dir / MANIFEST_FILE).read_text())
    return manifest


def _trips(run_dir: Path) -> list[dict[str, str]]:
    """Tripinfo's records. The file's header comment carries a timestamp, so the
    records -- not the bytes -- are what a reproduction must match."""
    root = ET.parse(run_dir / TRIPINFO_FILE).getroot()
    return [dict(e.attrib) for e in root.iter("tripinfo")]


# --- Reproducibility ----------------------------------------------------------


def test_the_same_spec_twice_gives_identical_results(scenario: Scenario, tmp_path: Path) -> None:
    spec = make_spec(scenario, tmp_path / "run", hold_first)

    run_many([spec], tmp_path / "first", jobs=1)
    first_row, first_trips = _row(spec.output_dir / RESULT_FILE), _trips(spec.output_dir)
    first_manifest = _manifest(spec.output_dir)
    run_many([spec], tmp_path / "second", jobs=1)

    assert _row(spec.output_dir / RESULT_FILE) == first_row
    assert _trips(spec.output_dir) == first_trips
    second_manifest = _manifest(spec.output_dir)
    for key in (*MACHINE_COLUMNS, "code_version"):
        first_manifest.pop(key), second_manifest.pop(key)
    assert second_manifest == first_manifest

    # Non-vacuous: the run is stochastic, so another replication differs.
    other = dataclasses.replace(spec, seed_index=1, output_dir=tmp_path / "other")
    run_many([other], tmp_path / "third", jobs=1)
    assert _trips(other.output_dir) != first_trips
    assert first_row["all.completed"] > 0


def test_the_experiment_parquet_holds_every_finished_run_in_spec_order(
    scenario: Scenario, tmp_path: Path
) -> None:
    specs = [
        make_spec(scenario, tmp_path / f"seed{k}", hold_first, seed_index=k) for k in (2, 0, 1)
    ]
    path = run_many(specs, tmp_path / "experiment", jobs=3)
    assert path == tmp_path / "experiment" / EXPERIMENT_FILE
    experiment = pl.read_parquet(path)
    assert experiment["run_id"].to_list() == ["seed2", "seed0", "seed1"]
    for spec, row in zip(specs, experiment.iter_rows(named=True), strict=True):
        alone = pl.read_parquet(spec.output_dir / RESULT_FILE).row(0, named=True)
        assert {k: row[k] for k in alone} == alone
        for name in (RESULT_FILE, MANIFEST_FILE, TRIPINFO_FILE, WARNING_LOG_FILE):
            assert (spec.output_dir / name).exists()
        assert _manifest(spec.output_dir)["seeds"] == derive_run_seeds(
            CONFIG.master_seed, spec.seed_index
        )
    assert pl.read_parquet(tmp_path / "experiment" / FAILURES_FILE).is_empty()


# --- Common random numbers at the seed level ------------------------------------


#: When `CycleFrom` first asks for something `HoldFirst` does not.
DIVERGE_AT_S = 30.0


def _arrivals(states: tuple[TrueState, ...]) -> list[tuple[float, tuple[int, ...]]]:
    """Per state, the vehicles in it that were in no earlier state."""
    seen: set[int] = set()
    arrivals = []
    for state in states:
        new = tuple(sorted(int(v.id) for v in state.vehicles if int(v.id) not in seen))
        seen.update(new)
        arrivals.append((state.time_s, new))
    return arrivals


def _until(run: Instrumented, end_s: float) -> tuple[TrueState, ...]:
    return tuple(s for s in run.states if s.time_s <= end_s)


def test_arms_share_seeds_and_arrivals_until_their_controllers_differ(
    scenario: Scenario, tmp_path: Path
) -> None:
    holding = make_spec(scenario, tmp_path / "hold", hold_first)
    cycling = dataclasses.replace(
        holding,
        run_id="cycle",
        output_dir=tmp_path / "cycle",
        controller_factory=functools.partial(CycleFrom, start_s=DIVERGE_AT_S),
    )
    a, b = watch(holding), watch(cycling)

    assert _manifest(holding.output_dir)["seeds"] == _manifest(cycling.output_dir)["seeds"]

    # Identical until the first decision at which the arms ask for different phases:
    # the same vehicles enter at the same instants, and drive identically.
    assert _arrivals(_until(a, DIVERGE_AT_S)) == _arrivals(_until(b, DIVERGE_AT_S))
    assert _until(a, DIVERGE_AT_S) == _until(b, DIVERGE_AT_S)
    assert sum(len(new) for _, new in _arrivals(_until(a, DIVERGE_AT_S))) >= 10

    # ... and they really do act differently from there: the same displays until
    # the decision at the divergence point, then a change only one arm asked for.
    assert [x for x in a.applied if x[0] < DIVERGE_AT_S] == [
        x for x in b.applied if x[0] < DIVERGE_AT_S
    ]
    i = scenario.built.intersection_id
    first = scenario.built.intersection.phases[0].id
    leaving = display_state(scenario.network, i, SignalStage.YELLOW, first)
    assert (DIVERGE_AT_S, i, leaving) in b.applied
    assert all(x[0] != DIVERGE_AT_S for x in a.applied)
    assert a.applied != b.applied
    assert a.states != b.states

    # Non-vacuous: another replication under the same controller differs before
    # the divergence point, so the equality above is the seeds' doing.
    other = watch(dataclasses.replace(holding, seed_index=1, output_dir=tmp_path / "other"))
    assert _until(other, DIVERGE_AT_S) != _until(a, DIVERGE_AT_S)


# --- Failures, invalid runs, warnings --------------------------------------------


def test_a_crashing_controller_fails_exactly_its_own_run(
    scenario: Scenario, tmp_path: Path
) -> None:
    specs = [
        make_spec(scenario, tmp_path / "ok0", hold_first, seed_index=0),
        make_spec(scenario, tmp_path / "boom", crashing, seed_index=0),
        make_spec(scenario, tmp_path / "ok1", hold_first, seed_index=1),
    ]
    experiment = pl.read_parquet(run_many(specs, tmp_path / "experiment", jobs=3))

    assert experiment["run_id"].to_list() == ["ok0", "ok1"]
    failures = pl.read_parquet(tmp_path / "experiment" / FAILURES_FILE)
    assert failures.select("run_id", "exit_code", "signal").rows() == [("boom", 1, None)]
    (text,) = failures["exception"].to_list()
    assert "RuntimeError" in text and CRASH_MESSAGE in text
    assert "decide" in text  # the child's own traceback came back with it
    assert not (tmp_path / "boom" / RESULT_FILE).exists()
    assert not (tmp_path / "boom" / MANIFEST_FILE).exists()


@pytest.mark.parametrize("jobs", [1, 2, 5])
def test_a_process_that_exits_fails_only_its_own_run(
    scenario: Scenario, tmp_path: Path, jobs: int
) -> None:
    """`os._exit(1)` raises nothing and writes nothing: the exit code is all there
    is. Runs before it, beside it and after it in the batch are unaffected."""
    specs = [make_spec(scenario, tmp_path / f"ok{k}", hold_first, seed_index=k) for k in range(4)]
    specs.insert(1, make_spec(scenario, tmp_path / "dies", exits))
    experiment = pl.read_parquet(run_many(specs, tmp_path / "experiment", jobs=jobs))

    assert experiment["run_id"].to_list() == ["ok0", "ok1", "ok2", "ok3"]
    assert experiment["valid"].to_list() == [True] * 4
    failures = pl.read_parquet(tmp_path / "experiment" / FAILURES_FILE)
    assert failures.rows() == [("dies", 1, None, None)]


def test_a_segfaulting_process_fails_only_its_own_run(scenario: Scenario, tmp_path: Path) -> None:
    """SIGSEGV, as a segfault inside libsumo would end the process."""
    specs = [
        make_spec(scenario, tmp_path / "ok0", hold_first, seed_index=0),
        make_spec(scenario, tmp_path / "segv", segfaults),
        make_spec(scenario, tmp_path / "ok1", hold_first, seed_index=1),
    ]
    experiment = pl.read_parquet(run_many(specs, tmp_path / "experiment", jobs=3))

    assert experiment["run_id"].to_list() == ["ok0", "ok1"]
    failures = pl.read_parquet(tmp_path / "experiment" / FAILURES_FILE)
    assert failures.rows() == [("segv", None, "SIGSEGV", None)]


def test_an_overloaded_run_is_in_the_experiment_flagged_invalid(
    scenario: Scenario, tmp_path: Path
) -> None:
    overload = one_flow_per_movement(
        scenario.built, tmp_path / "overload.rou.xml", DEMAND_END_S, period_s=OVERLOAD_PERIOD_S
    )
    specs = [
        make_spec(scenario, tmp_path / "normal", hold_first),
        make_spec(scenario, tmp_path / "overload", hold_first, routes=overload),
    ]
    experiment = pl.read_parquet(run_many(specs, tmp_path / "experiment", jobs=2))

    rows = {row["run_id"]: row for row in experiment.iter_rows(named=True)}
    assert set(rows) == {"normal", "overload"}
    assert rows["normal"]["valid"] is True
    assert rows["overload"]["valid"] is False
    assert "insertion_loss" in rows["overload"]["invalid_causes"].split(",")
    assert rows["overload"]["insertion_loss"] > 0.01
    assert pl.read_parquet(tmp_path / "experiment" / FAILURES_FILE).is_empty()


def test_sumo_warnings_are_counted_and_the_console_carries_only_progress(
    scenario: Scenario, tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """A3: an out-of-order route file gives `sumo_warnings >= 1` and nothing on the
    console, whatever this process's locale -- each run's process sets its own
    (`traffic_lab.experiments.worker`)."""
    specs = [
        make_spec(
            scenario,
            tmp_path / "ooo",
            hold_first,
            routes=out_of_order_routes(scenario.built, tmp_path / "ooo.rou.xml"),
        ),
        make_spec(scenario, tmp_path / "clean", hold_first),
    ]
    capfd.readouterr()
    run_many(specs, tmp_path / "experiment", jobs=2)
    console = capfd.readouterr()

    assert console.out == ""
    lines = console.err.splitlines()
    assert len(lines) == len(specs)
    assert all(PROGRESS_LINE.match(line) for line in lines), lines
    assert _manifest(tmp_path / "ooo")["sumo_warnings"] >= 1
    assert _manifest(tmp_path / "clean")["sumo_warnings"] == 0


def test_progress_counts_every_outcome(
    scenario: Scenario, tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    overload = one_flow_per_movement(
        scenario.built, tmp_path / "overload.rou.xml", DEMAND_END_S, period_s=OVERLOAD_PERIOD_S
    )
    specs = [
        make_spec(scenario, tmp_path / "ok", hold_first),
        make_spec(scenario, tmp_path / "bad", hold_first, routes=overload),
        make_spec(scenario, tmp_path / "boom", crashing),
    ]
    capfd.readouterr()
    run_many(specs, tmp_path / "experiment", jobs=1)
    lines = [line for line in capfd.readouterr().err.splitlines() if line.startswith("[")]
    assert [line.split()[1:3] for line in lines] == [
        ["done", "ok"],
        ["invalid", "bad"],
        ["failed", "boom"],
    ]
    assert "done 1 invalid 1 failed 1" in lines[-1]
    assert lines[-1].startswith("[3/3]")


# --- Refusals ---------------------------------------------------------------------


def test_runs_may_not_share_an_id_or_a_directory(scenario: Scenario, tmp_path: Path) -> None:
    spec = make_spec(scenario, tmp_path / "a", hold_first)
    with pytest.raises(ValueError, match="run_id"):
        run_many([spec, dataclasses.replace(spec, output_dir=tmp_path / "b")], tmp_path, jobs=1)
    with pytest.raises(ValueError, match="output_dir"):
        run_many([spec, dataclasses.replace(spec, run_id="b")], tmp_path, jobs=1)
    with pytest.raises(ValueError, match="jobs"):
        run_many([spec], tmp_path, jobs=0)


def _config(**overrides: object) -> RunConfig:
    return RunConfig.model_validate({**CONFIG.model_dump(), **overrides})


@pytest.mark.parametrize(
    "overrides",
    [{"warmup_s": 60.5}, {"measurement_s": 299.5}, {"cooldown_s": 0.25}],
    ids=["window-start", "window-end", "run-end"],
)
def test_phase_boundaries_must_fall_on_the_step_grid(
    scenario: Scenario, tmp_path: Path, overrides: dict[str, float]
) -> None:
    with pytest.raises(ValueError, match="step grid"):
        make_spec(scenario, tmp_path, hold_first, config=_config(**overrides))
    make_spec(scenario, tmp_path, hold_first, config=_config(**overrides), step_length_s=0.25)


def test_neutral_snapshot_warmup_is_refused_until_t1_6(scenario: Scenario, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"T1\.6"):
        make_spec(scenario, tmp_path, hold_first, config=_config(warmup_design="neutral_snapshot"))


def test_a_spec_is_picklable(scenario: Scenario, tmp_path: Path) -> None:
    spec = make_spec(scenario, tmp_path, functools.partial(CycleFrom, start_s=5.0))
    clone: RunSpec = pickle.loads(pickle.dumps(spec))
    assert clone.run_id == spec.run_id
    assert clone.controller_factory(clone.network).decision_interval_s == 5.0
