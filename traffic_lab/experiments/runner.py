"""The run core: one run end to end, and many runs, each in its own process (T1.11, D-031).

`run_one` executes `06_ARCHITECTURE.md` SS6.2's step loop literally. Every
simulation step: `backend.step()`, `project()`, `constraint_layer.step()`,
`accumulate()`. Every Dt: the oracle sensor, the identity estimator -- handed
the constraint layer's signal states (D-033) -- the controller, and `submit()`.
Then the display, applied only when it changes: `display_state()` costs about
15 % of a LibSUMO step at one call per step (T1.14), and SUMO holds whatever
was applied last. At the end SUMO is closed, its tripinfo read (D-035) and the
metrics finalized (T1.8); the run writes its result row, its manifest, its
tripinfo and its SUMO warning log.

`run_many` starts one `spawn` process per run, at most `jobs` at once: **a
fresh process per run.** LibSUMO holds one simulation per process, and T1.4
showed a replay depends on the process's RNG history, so a reused worker would
make results depend on scheduling. A run whose process raises, exits non-zero
or dies by a signal produces no result row; it is recorded in
`failures.parquet` with its exit code, signal and traceback, nothing is
retried, and no other run is affected. A run that is merely *invalid* (D-008)
is a result like any other and is written with its flags.

Timing conventions, stated once because off-by-one errors here are silent:

* SUMO begins at 0 s. The display is applied once before the first step, so
  SUMO leaves its static program for the constraint layer's from the start.
* The state after the k-th step is stamped `k * step_length_s`. The loop runs
  while the last state is before the run's end, so its last state is stamped
  exactly at the end -- warm-up plus measurement plus cool-down.
* Decisions fall at `k * Dt` for k = 1, 2, ...: the first at Dt, never at 0
  (there is no state at 0) and never at the first step unless Dt is the step
  length -- the convention of T1.14's display-loop test. `k * Dt` rather than
  repeated addition, so a fractional step length cannot drift a decision off
  its step.
* A display applied after the state at `t` is what SUMO shows during the step
  to the next state, so `TrueState` reads it one step later (T1.14).
"""

from __future__ import annotations

import functools
import hashlib
import json
import multiprocessing
import pickle
import signal
import sys
import time
import traceback
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from multiprocessing.connection import wait
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import Any, cast

import polars as pl

from traffic_lab.backend import BackendConfig, SumoBackend, TransportName, display_state
from traffic_lab.backend.config import count_sumo_warnings
from traffic_lab.backend.tripinfo import read_trips
from traffic_lab.control.constraint_layer import ConstraintLayer, ConstraintLayerConfig
from traffic_lab.control.controller import Controller
from traffic_lab.domain.network import IntersectionId, Network, PhaseId, SensorId
from traffic_lab.domain.state import SignalStage, TrueState
from traffic_lab.estimation import Estimator, IdentityEstimator
from traffic_lab.experiments.config import RunConfig, canonical_hash
from traffic_lab.experiments.manifest import RunManifest, measure_peak_memory_mb
from traffic_lab.experiments.seeds import derive_run_seeds
from traffic_lab.experiments.version import get_code_version, get_sumo_version
from traffic_lab.experiments.worker import run_in_child
from traffic_lab.metrics import MeasurementWindow, MetricAccumulator
from traffic_lab.sensing import OracleSensor, SensorModel

#: What every run writes into its `output_dir` (T1.11 Amendment A2).
RESULT_FILE = "result.parquet"
MANIFEST_FILE = "manifest.json"
TRIPINFO_FILE = "tripinfo.xml"
WARNING_LOG_FILE = "sumo-warnings.log"

#: Written by a run's process when the run raises (`worker.run_in_child`).
TRACEBACK_FILE = "exception.txt"

#: What `run_many` writes into the experiment directory.
EXPERIMENT_FILE = "experiment.parquet"
FAILURES_FILE = "failures.parquet"

#: The oracle arm's one sensor. An identifier, not a parameter.
ORACLE_SENSOR = SensorId(0)

#: Slack when comparing simulated times. SUMO's clock is in integer
#: milliseconds, so a time either lands on a boundary or misses it by a step.
_TIME_EPS_S = 1e-6


@dataclass(frozen=True, slots=True, kw_only=True)
class RunSpec:
    """One run, fully resolved and picklable: everything `run_one` needs.

    `controller_factory` must be importable by a fresh process -- a top-level
    function or class, or a `functools.partial` of one whose bound arguments are
    JSON values -- because `run_many` hands the spec to a `spawn` worker and the
    manifest records the factory by name and arguments (`controller_identity`).

    `gridlock_steps` is D-008's N, which `BackendConfig` requires and the T1.11
    contract's field list does not carry. It is required here, with no
    default, rather than invented: see the T1.11 completion report.
    """

    run_id: str
    net: Path
    routes: Path
    network: Network
    controller_factory: Callable[[Network], Controller]
    config: RunConfig
    seed_index: int
    transport: TransportName = "libsumo"
    step_length_s: float
    output_dir: Path
    gridlock_steps: int

    def __post_init__(self) -> None:
        controller_identity(self.controller_factory)  # raises if it cannot be recorded
        if not self.run_id:
            raise ValueError("run_id must be non-empty")
        if self.seed_index < 0:
            raise ValueError(f"seed_index must be non-negative, got {self.seed_index}")
        if self.step_length_s <= 0.0:
            raise ValueError(f"step_length_s must be positive, got {self.step_length_s}")
        if self.config.warmup_design != "self":
            # D-032's neutral snapshot needs T1.6. A run that recorded
            # "neutral_snapshot" in its manifest after warming up under its own
            # controller would be a false record, so it is refused.
            raise ValueError(
                f"warmup_design={self.config.warmup_design!r} is not supported until T1.6; "
                f"only 'self' warm-up can be run"
            )
        # The accumulator needs a state exactly at the window's end, and the
        # loop must stop exactly at the run's end: both are step-grid times.
        for name, boundary_s in (
            ("warm-up end", self.window.start_s),
            ("measurement end", self.window.end_s),
            ("run end", self.end_s),
        ):
            steps = boundary_s / self.step_length_s
            if abs(steps - round(steps)) > _TIME_EPS_S:
                raise ValueError(
                    f"the {name} at {boundary_s} s is not on the {self.step_length_s} s step grid"
                )

    @property
    def window(self) -> MeasurementWindow:
        """The measurement phase (D-018): it starts when warm-up ends."""
        start_s = self.config.warmup_s
        return MeasurementWindow(start_s=start_s, end_s=start_s + self.config.measurement_s)

    @property
    def end_s(self) -> float:
        """The run's last simulated instant: the window's end plus the cool-down."""
        return self.window.end_s + self.config.cooldown_s


def run_one(spec: RunSpec) -> Path:
    """Execute one run end to end; return the path of its `result.parquet`.

    Raises whatever the run raises -- a crashing controller, a failed startup
    assertion, a trip-accounting defect (invariant 14) -- after closing SUMO.
    An invalid run does not raise: it is written with its flags (D-008).
    """
    started = time.monotonic()
    out = spec.output_dir
    out.mkdir(parents=True, exist_ok=True)
    # A crash must not leave an earlier run's result behind looking like this one's.
    for stale in (RESULT_FILE, MANIFEST_FILE):
        (out / stale).unlink(missing_ok=True)
    tripinfo, warning_log = out / TRIPINFO_FILE, out / WARNING_LOG_FILE

    seeds = derive_run_seeds(spec.config.master_seed, spec.seed_index)
    controller = spec.controller_factory(spec.network)
    decision_interval_s = controller.decision_interval_s
    resolved = resolved_run(spec, decision_interval_s)
    layer = ConstraintLayer(
        spec.network,
        ConstraintLayerConfig(
            decision_interval_s=decision_interval_s, step_length_s=spec.step_length_s
        ),
        start_s=0.0,
    )
    accumulator = MetricAccumulator(spec.window, spec.network)
    backend = SumoBackend()
    backend.start(
        spec.net,
        spec.routes,
        BackendConfig(
            transport=spec.transport,
            step_length_s=spec.step_length_s,
            seed=seeds["driver"],
            decision_interval_s=decision_interval_s,
            gridlock_steps=spec.gridlock_steps,
            tripinfo_path=tripinfo,
            error_log_path=warning_log,
        ),
        network=spec.network,
    )
    try:
        last = _step_loop(
            spec,
            backend,
            layer,
            OracleSensor(ORACLE_SENSOR, spec.network),
            IdentityEstimator(spec.network),
            controller,
            accumulator,
        )
    finally:
        # SUMO writes tripinfo on close; nothing below may read it before.
        backend.close()

    trips = read_trips(tripinfo, backend.index, end_s=last.time_s)
    result = accumulator.finalize(trips, snapshot_mismatch=False)
    sumo_warnings = count_sumo_warnings(warning_log)
    wall_clock_s = time.monotonic() - started
    peak_memory_mb = measure_peak_memory_mb()

    row = {
        "run_id": spec.run_id,
        **result.to_row(),
        "wall_clock_s": wall_clock_s,
        "peak_memory_mb": peak_memory_mb,
    }
    _write_row(row, out / RESULT_FILE)

    counters = last.counters
    manifest = RunManifest(
        config_hash=canonical_hash({"config": resolved, "seeds": seeds}),
        config=resolved,
        code_version=get_code_version(),
        sumo_version=get_sumo_version(),
        seeds=seeds,
        decision_interval_s={resolved["controller"]["factory"]: decision_interval_s},
        warmup_design=spec.config.warmup_design,
        validity={
            "teleports": counters.teleports,
            "insertion_failures": counters.insertion_failures,
            "gridlock_detected": counters.gridlock_detected,
        },
        trips={
            "arrived_at_sink": counters.arrived_at_sink,
            "arrived_mid_link": counters.arrived_mid_link,
            "still_in_network": counters.still_in_network,
        },
        sumo_warnings=sumo_warnings,
        wall_clock_s=wall_clock_s,
        peak_memory_mb=peak_memory_mb,
    )
    (out / MANIFEST_FILE).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return out / RESULT_FILE


def resolved_run(spec: RunSpec, decision_interval_s: float) -> dict[str, Any]:
    """Everything that decides what a run does, as JSON values: the manifest's `config`.

    Enough to reproduce the run from the manifest alone: the spec's own fields,
    the controller by qualified name and bound arguments, its Δt, D-008's N, the
    T1.1 `RunConfig`, and the net and routes files by SHA-256 of their content.
    File paths are left out on purpose: they differ between machines, and the
    same run must hash the same everywhere (T1.1). `output_dir` is where the
    run is written, not what it is.
    """
    return {
        "run_id": spec.run_id,
        "seed_index": spec.seed_index,
        "transport": spec.transport,
        "step_length_s": spec.step_length_s,
        "decision_interval_s": decision_interval_s,
        "controller": controller_identity(spec.controller_factory),
        "gridlock_steps": spec.gridlock_steps,
        "net_sha256": _file_sha256(spec.net),
        "routes_sha256": _file_sha256(spec.routes),
        "run_config": spec.config.model_dump(mode="json"),
    }


def controller_identity(factory: Callable[[Network], Controller]) -> dict[str, Any]:
    """A controller factory as JSON: `{"factory": "module.qualname", "args": [...],
    "keywords": {...}}`, the arguments being those a `functools.partial` binds.

    Raises `ValueError` for a factory a fresh process could not import by name
    (a lambda, a closure) or whose bound arguments are not JSON values: either
    would make the manifest unable to say which controller ran.
    """
    target: Any = factory
    args: tuple[Any, ...] = ()
    keywords: dict[str, Any] = {}
    if isinstance(factory, functools.partial):
        target, args, keywords = factory.func, factory.args, dict(factory.keywords)
    module = getattr(target, "__module__", None)
    qualname = getattr(target, "__qualname__", None)
    if not module or not qualname or "<" in qualname:
        raise ValueError(
            f"controller factory {factory!r} is not importable by name; use a top-level "
            f"function or class, or a functools.partial of one"
        )
    identity = {"factory": f"{module}.{qualname}", "args": list(args), "keywords": keywords}
    try:
        return dict(json.loads(json.dumps(identity, sort_keys=True)))
    except TypeError as exc:
        raise ValueError(
            f"controller factory {factory!r} binds arguments that are not JSON values, so "
            f"the manifest could not record them"
        ) from exc


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _step_loop(
    spec: RunSpec,
    backend: SumoBackend,
    layer: ConstraintLayer,
    sensor: SensorModel,
    estimator: Estimator,
    controller: Controller,
    accumulator: MetricAccumulator,
) -> TrueState:
    """`06_ARCHITECTURE.md` SS6.2, literally; returns the run's last state."""
    network = spec.network
    intersections = tuple(i.id for i in network.signalized_intersections)
    decision_interval_s = controller.decision_interval_s
    shown: dict[IntersectionId, tuple[SignalStage, PhaseId | None]] = {}

    _apply_display_changes(backend, layer, network, intersections, shown)
    decisions = 1
    next_decision_s = decisions * decision_interval_s
    state: TrueState | None = None
    end_s = spec.end_s
    while state is None or state.time_s < end_s - _TIME_EPS_S:
        backend.step()  # SUMO advances one step
        state = backend.project()  # one batched fetch
        now_s = state.time_s

        layer.step(now_s)  # EVERY step: timers, yellow, all-red
        accumulator.accumulate(state)  # EVERY step: cheap appends

        if now_s + _TIME_EPS_S >= next_decision_s:  # EVERY Dt
            obs = sensor.observe(state, now_s)
            own = tuple(layer.signal_state(i) for i in intersections)  # D-033
            est = estimator.update(obs, own, now_s)
            request = controller.decide(est, now_s)
            layer.submit(request, now_s)
            decisions += 1
            next_decision_s = decisions * decision_interval_s

        _apply_display_changes(backend, layer, network, intersections, shown)
    return state


def _apply_display_changes(
    backend: SumoBackend,
    layer: ConstraintLayer,
    network: Network,
    intersections: tuple[IntersectionId, ...],
    shown: dict[IntersectionId, tuple[SignalStage, PhaseId | None]],
) -> None:
    """Send each intersection's display to SUMO if it differs from the last one sent.

    `layer.display()` is a tuple lookup; `display_state()` and `apply()` run
    only on a change -- a stage boundary or a granted or forced phase change.
    """
    for intersection in intersections:
        display = layer.display(intersection)
        if shown.get(intersection) != display:
            stage, phase = display
            backend.apply(intersection, display_state(network, intersection, stage, phase))
            shown[intersection] = display


def _write_row(row: Mapping[str, object], path: Path) -> None:
    """One run's row as Parquet.

    A metric that is `None` has no type of its own in a one-row frame; every
    optional field of T1.8's row is a float (a mean over no trips, an undefined
    completion rate, an MSER-5 truncation that could not be computed), so a
    null column is stored as Float64 and concatenates with the runs that have it.
    """
    frame = pl.from_dicts([row])
    frame = frame.with_columns(
        pl.col(name).cast(pl.Float64) for name, dtype in frame.schema.items() if dtype == pl.Null
    )
    frame.write_parquet(path)


@dataclass(frozen=True, slots=True)
class _Failure:
    """Why a run produced no result: how its process ended, and what it said."""

    exit_code: int | None  # the child's exit status; None if it never ran or a signal ended it
    signal: str | None  # the signal that ended it, e.g. "SIGSEGV"
    exception: str | None  # the traceback the child wrote, or why it could not run


def run_many(specs: Sequence[RunSpec], out: Path, *, jobs: int) -> Path:
    """Run every spec, each in its own fresh process, at most `jobs` alive at once.

    One `spawn` `multiprocessing.Process` per run, never reused, so each run's
    results depend on its spec alone. The parent waits on the processes and
    reads each exit code: a run fails if its process exits non-zero, is killed
    by a signal, or exits 0 without a result -- and **only that run fails**.
    Runs in flight or pending are unaffected, which a process pool cannot
    promise: when one of its workers dies it fails every pending task with it
    (measured: `os._exit` in one run of five failed all four that had not
    finished).

    Returns the path of `out/experiment.parquet`: one row per run that finished,
    valid or not, in the order of `specs`. Failed runs are in
    `out/failures.parquet` -- `run_id`, `exit_code`, `signal`, and `exception`,
    the traceback when the child wrote one -- always written, empty when nothing
    failed. Nothing is retried. One progress line per finished run goes to stderr.
    """
    if jobs < 1:
        raise ValueError(f"jobs must be at least 1, got {jobs}")
    _require_distinct(specs)
    out.mkdir(parents=True, exist_ok=True)

    context = multiprocessing.get_context("spawn")
    progress = _Progress(total=len(specs))
    pending = deque(specs)
    running: dict[int, tuple[BaseProcess, RunSpec]] = {}  # by process sentinel
    results: dict[str, Path] = {}
    failures: dict[str, _Failure] = {}

    def finish(spec: RunSpec, failure: _Failure | None) -> None:
        if failure is not None:
            failures[spec.run_id] = failure
            progress.report(spec.run_id, "failed")
            return
        path = spec.output_dir / RESULT_FILE
        results[spec.run_id] = path
        valid = bool(pl.read_parquet(path, columns=["valid"]).item())
        progress.report(spec.run_id, "done" if valid else "invalid")

    try:
        while pending or running:
            while pending and len(running) < jobs:
                spec = pending.popleft()
                spec.output_dir.mkdir(parents=True, exist_ok=True)
                traceback_path = spec.output_dir / TRACEBACK_FILE
                traceback_path.unlink(missing_ok=True)
                try:
                    payload = pickle.dumps(spec)
                except Exception:
                    finish(spec, _Failure(None, None, traceback.format_exc()))
                    continue
                process: BaseProcess = context.Process(
                    target=run_in_child,
                    args=(payload, str(traceback_path)),
                    name=f"run {spec.run_id}",
                )
                process.start()
                running[process.sentinel] = (process, spec)
            for sentinel in wait(list(running)):
                process, spec = running.pop(cast(int, sentinel))
                process.join()
                finish(spec, _failure_of(process, spec))
    finally:
        # Only reached with processes alive if the parent itself was interrupted.
        for process, _ in running.values():
            process.terminate()
            process.join()

    frames = [pl.read_parquet(results[s.run_id]) for s in specs if s.run_id in results]
    experiment = (
        pl.concat(frames, how="diagonal_relaxed")
        if frames
        else pl.DataFrame(schema={"run_id": pl.String})
    )
    experiment.write_parquet(out / EXPERIMENT_FILE)
    ordered = [s.run_id for s in specs if s.run_id in failures]
    pl.DataFrame(
        {
            "run_id": ordered,
            "exit_code": [failures[r].exit_code for r in ordered],
            "signal": [failures[r].signal for r in ordered],
            "exception": [failures[r].exception for r in ordered],
        },
        schema={
            "run_id": pl.String,
            "exit_code": pl.Int64,
            "signal": pl.String,
            "exception": pl.String,
        },
    ).write_parquet(out / FAILURES_FILE)
    return out / EXPERIMENT_FILE


def _failure_of(process: BaseProcess, spec: RunSpec) -> _Failure | None:
    """`None` if the run produced its result; otherwise how it failed."""
    code = process.exitcode
    traceback_path = spec.output_dir / TRACEBACK_FILE
    written = traceback_path.read_text() if traceback_path.exists() else None
    if code is not None and code < 0:  # multiprocessing's convention: -N is signal N
        return _Failure(None, signal.Signals(-code).name, written)
    if code != 0:
        return _Failure(code, None, written)
    if not (spec.output_dir / RESULT_FILE).exists():
        return _Failure(0, None, "the run's process exited 0 without writing its result")
    return None


def _require_distinct(specs: Sequence[RunSpec]) -> None:
    """Two runs sharing an ID or an output directory would share mutable state."""
    for what, values in (
        ("run_id", [s.run_id for s in specs]),
        ("output_dir", [s.output_dir.resolve() for s in specs]),
    ):
        seen: set[object] = set()
        for value in values:
            if value in seen:
                raise ValueError(f"two runs share {what} {value}")
            seen.add(value)


class _Progress:
    """One stderr line per finished run: counts so far and elapsed wall-clock."""

    def __init__(self, total: int) -> None:
        self._total = total
        self._started = time.monotonic()
        self._counts = {"done": 0, "invalid": 0, "failed": 0}

    def report(self, run_id: str, outcome: str) -> None:
        self._counts[outcome] += 1
        finished = sum(self._counts.values())
        counts = self._counts
        print(
            f"[{finished}/{self._total}] {outcome} {run_id} | "
            f"done {counts['done']} invalid {counts['invalid']} failed {counts['failed']} | "
            f"elapsed {time.monotonic() - self._started:.1f} s",
            file=sys.stderr,
            flush=True,
        )
