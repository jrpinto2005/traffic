"""The run core: one run end to end, and many runs in a process pool (T1.11, D-031).

`run_one` executes `06_ARCHITECTURE.md` SS6.2's step loop literally. Every
simulation step: `backend.step()`, `project()`, `constraint_layer.step()`,
`accumulate()`. Every Dt: the oracle sensor, the identity estimator -- handed
the constraint layer's signal states (D-033) -- the controller, and `submit()`.
Then the display, applied only when it changes: `display_state()` costs about
15 % of a LibSUMO step at one call per step (T1.14), and SUMO holds whatever
was applied last. At the end SUMO is closed, its tripinfo read (D-035) and the
metrics finalized (T1.8); the run writes its result row, its manifest, its
tripinfo and its SUMO warning log.

`run_many` runs specs in a `ProcessPoolExecutor` with the `spawn` context and
`max_tasks_per_child=1`: **a fresh process per run.** LibSUMO holds one
simulation per process, and T1.4 showed a replay depends on the process's RNG
history, so a reused worker would make results depend on scheduling. A run that
raises produces no result row; it is recorded in `failures.parquet` with its
exception text, and nothing is retried. A run that is merely *invalid* (D-008)
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

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from traffic_lab.backend import BackendConfig, SumoBackend, TransportName, display_state
from traffic_lab.backend.config import count_sumo_warnings
from traffic_lab.backend.tripinfo import read_trips
from traffic_lab.control.constraint_layer import ConstraintLayer, ConstraintLayerConfig
from traffic_lab.control.controller import Controller
from traffic_lab.domain.network import IntersectionId, Network, PhaseId, SensorId
from traffic_lab.domain.state import SignalStage, TrueState
from traffic_lab.estimation import Estimator, IdentityEstimator
from traffic_lab.experiments.config import RunConfig, compute_config_hash
from traffic_lab.experiments.manifest import RunManifest, measure_peak_memory_mb
from traffic_lab.experiments.seeds import derive_run_seeds
from traffic_lab.experiments.version import get_code_version, get_sumo_version
from traffic_lab.metrics import MeasurementWindow, MetricAccumulator
from traffic_lab.sensing import OracleSensor, SensorModel

#: What every run writes into its `output_dir` (T1.11 Amendment A2).
RESULT_FILE = "result.parquet"
MANIFEST_FILE = "manifest.json"
TRIPINFO_FILE = "tripinfo.xml"
WARNING_LOG_FILE = "sumo-warnings.log"

#: The oracle arm's one sensor. An identifier, not a parameter.
ORACLE_SENSOR = SensorId(0)

#: Slack when comparing simulated times. SUMO's clock is in integer
#: milliseconds, so a time either lands on a boundary or misses it by a step.
_TIME_EPS_S = 1e-6


@dataclass(frozen=True, slots=True, kw_only=True)
class RunSpec:
    """One run, fully resolved and picklable: everything `run_one` needs.

    `controller_factory` must be importable by a fresh process -- a top-level
    function or class, or a `functools.partial` of one -- because `run_many`
    hands the spec to a `spawn` worker.

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
        config_hash=compute_config_hash(spec.config),
        config=spec.config.model_dump(mode="json"),
        code_version=get_code_version(),
        sumo_version=get_sumo_version(),
        seeds=seeds,
        decision_interval_s={type(controller).__name__: decision_interval_s},
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
