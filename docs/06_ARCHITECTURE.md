# Architecture

**Status:** Active
**Version:** 1.0
**Governed by:** `02_PROJECT_CHARTER.md`
**Implements:** `D-002`, `D-003`, `D-005`, `D-009`, `D-020`, `D-031`, `D-032`

---

## 1. Purpose and the one idea that matters

This document defines the layers, the boundaries between them, and the rules that make the
boundaries real rather than aspirational.

Most of it is ordinary. One idea is not, and it is the reason the architecture is shaped the
way it is:

> **Controllers never see true state. Not "should not" — cannot. `TrueState` is not in
> scope in any module a controller lives in.**

`02_PROJECT_CHARTER.md` S6 requires this, and `01_CRITICAL_REVIEW.md` R-5 identifies a leak
as the single failure that would silently invalidate every sensing result in the project.
Section 4 explains the mechanism that makes it structural instead of disciplinary, and it is
simpler than it sounds.

---

## 2. The layers

```text
              ┌─────────────────────────────────────────────────┐
              │              EXPERIMENT RUNNER                  │
              │   config → N independent runs → parquet         │
              └───────────────────┬─────────────────────────────┘
                                  │  one run = one process
                                  ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │                          SIMULATION RUN                          │
   │                                                                  │
   │   ┌────────────┐                                                 │
   │   │  SCENARIO  │  network + demand + snapshot → backend input    │
   │   └─────┬──────┘                                                 │
   │         ▼                                                        │
   │   ┌────────────────────────────────────────────┐                 │
   │   │            BACKEND ADAPTER                 │  ◄── SEAM 1     │
   │   │  transport: TraCI | LibSUMO                │                 │
   │   │  reads via subscriptions only              │                 │
   │   └─────┬──────────────────────────────┬───────┘                 │
   │         │ projects                     ▲ commands                │
   │         ▼                              │                         │
   │   ┌───────────┐                  ┌─────┴────────────┐            │
   │   │ TrueState │                  │ CONSTRAINT LAYER │            │
   │   └─────┬─────┘                  └─────▲────────────┘            │
   │         │                              │ PhaseRequest            │
   │         │  (only these four read it)   │                         │
   │         ├──────────┬─────────┬─────────┼──────────┐              │
   │         ▼          ▼         ▼         │          ▼              │
   │   ┌─────────┐  ┌───────┐ ┌───────┐     │    ┌──────────┐         │
   │   │ SENSORS │  │METRICS│ │ TRACE │     │    │ SNAPSHOT │         │
   │   └────┬────┘  └───────┘ └───────┘     │    └──────────┘         │
   │        │  ◄── SEAM 2                   │                         │
   │        ▼                               │                         │
   │  ┌─────────────┐                       │                         │
   │  │ Observation │                       │                         │
   │  └──────┬──────┘                       │                         │
   │         ▼                              │                         │
   │  ┌─────────────┐                       │                         │
   │  │  ESTIMATOR  │                       │                         │
   │  └──────┬──────┘                       │                         │
   │         ▼                              │                         │
   │  ┌──────────────┐                      │                         │
   │  │EstimatedState│                      │                         │
   │  └──────┬───────┘                      │                         │
   │         ▼                              │                         │
   │  ┌─────────────┐  ◄── SEAM 3           │                         │
   │  │ CONTROLLER  │──────────────────────►┘                         │
   │  └─────────────┘   every Δt                                      │
   └──────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │  results.parquet + trace  │
                    └─────────────┬─────────────┘
                                  ▼
                    ┌───────────────────────────┐
                    │   ANALYSIS  │  RENDERER   │   offline, separate processes
                    └───────────────────────────┘
```

This is `00_RESEARCH_SPECIFICATION.md` §24's loop with the boundaries made explicit and the
readers of `TrueState` enumerated.

### 2.1 Responsibilities

| Layer | Owns | Must not |
| --- | --- | --- |
| **Experiment runner** | Config expansion, seed derivation, process spawning, manifest, result collection | Know anything about traffic |
| **Scenario** | Network generation, demand generation, snapshot selection | Read simulation state |
| **Backend adapter** | The only code that talks to SUMO; projection into canonical types; command application | Interpret traffic semantics, compute metrics |
| **Constraint layer** | Signal timing, transition execution, safety enforcement | Choose a phase on policy grounds (only the max-green override) |
| **Sensors** | Turning `TrueState` into `Observation` | Be bypassed |
| **Estimator** | Turning `Observation` into `EstimatedState` | Read `TrueState` |
| **Controller** | Choosing a phase from `EstimatedState` | Touch the backend, know about SUMO, read `TrueState` |
| **Metrics** | Metric computation from `TrueState`, validity checks | Be recomputed anywhere else |
| **Trace** | Serialising a run for later replay | Be on by default |
| **Analysis / renderer** | Consuming outputs offline | Import the backend |

---

## 3. The three seams

Per `02_PROJECT_CHARTER.md` §6, indirection is justified only where a second implementation
is genuinely expected. Exactly three places qualify. **A fourth requires a decision register
entry.**

| Seam | Interface | Second implementation | Status |
| --- | --- | --- | --- |
| **1 — Backend transport** | `Backend` | LibSUMO alongside TraCI | Expected at M5/M7 (`D-002`) |
| **2 — Observation source** | `SensorModel` | Pixel-derived detections | Reserved (`D-005`) |
| **3 — Controller** | `Controller` | Every controller from Webster to RL | Exists immediately (`D-020`) |

Seam 3 is the only one with multiple implementations from day one. Seams 1 and 2 are
insurance, and both are cheap because the interface is small and the retrofit would be
expensive.

Note what is **not** a seam: the estimator (one implementation until M3, and then it is a
strategy behind a function, not a framework), metrics (one implementation, ever), the
scenario generator, and the trace writer.

---

## 4. How the truth/observation separation is enforced

### 4.1 The mechanism

The obvious design is to give controllers a choice of input type and rely on discipline. That
fails, because in an oracle experiment both objects are in scope and passing the wrong one is
a one-character mistake.

The design used instead removes the choice:

> **The oracle is a sensor, not a bypass.**

`OracleSensor` implements the same `SensorModel` interface as `CameraSensor`. It observes
every vehicle, with detection probability 1.0, zero noise, and zero latency. It returns an
`Observation` like any other sensor.

The consequence is that **a controller only ever receives `Observation` / `EstimatedState`,
in every experimental arm, including the oracle arm.** The `control/` package does not import
`TrueState` at all. There is no path to leak through, because there is no path.

```python
# sensing/oracle.py
class OracleSensor:
    """Perfect observation. The experimental control of D-023/§23, not a shortcut."""
    def observe(self, state: TrueState, now_s: float) -> Observation:
        return Observation(
            detections=[perfect_detection(v) for v in state.vehicles],
            coverage=Coverage.COMPLETE,
            latency_s=0.0,
        )
```

### 4.2 Who may read `TrueState`

Exactly four consumers, all of them outside the control path:

| Consumer | Why it is legitimate |
| --- | --- |
| **Sensor models** | Their entire job is `O_t = h(S_t) + ε_t` |
| **Metrics** | Evaluation must measure what actually happened, not what the controller believed. This is the point of having ground truth. |
| **Trace writer** | The renderer overlays truth against observation; that comparison is the reason the custom renderer exists (`01_CRITICAL_REVIEW.md` O-5) |
| **Snapshot writer** | Serialising state is the state (`D-032`) |

### 4.3 How it is checked

Three layers, cheapest first:

1. **Import check** — an automated test asserts that `traffic_lab.control` does not import
   `TrueState`, transitively. This is the check that actually catches things.
2. **Type checking** — `mypy --strict` on `control/`; the `Controller` protocol accepts
   `EstimatedState` only.
3. **Review** — item 1 of the review checklist in `08_AGENT_HANDOFF_PROTOCOL.md` §6.

---

## 5. The backend adapter

### 5.1 Transport abstraction

Per `D-002`, one interface, two transports, selected by configuration. TraCI and LibSUMO
share method signatures, so the abstraction is thin — but it must exist from the start,
because retrofitting it after controllers and experiments have hard-coded one is expensive.

Constraints that the abstraction must encode rather than leave to be discovered:

- **LibSUMO holds one simulation per process.** Parallel sweeps therefore parallelise across
  processes, not threads. This is why the runner's process model (§6) is shaped as it is —
  the constraint and the design agree rather than fight.
- **LibSUMO has no GUI.** Any GUI use forces TraCI. Since visualization is record-then-replay
  (`D-009`), this only affects debugging.

### 5.2 One batched projection per step, and no per-object access outside the adapter

Per `D-031` (amended 2026-08-18), this is an **architectural constraint, not an optimization**.
The adapter:

- fetches all state for a step in **one batched operation**,
- projects it into `TrueState`,
- and exposes **no** per-object query method to the rest of the system.

If a layer needs a quantity, it is added to the projection at construction, not fetched on
demand. Per-object access reaching sensors, metrics or controllers is a review defect
(`08_AGENT_HANDOFF_PROTOCOL.md` §6 item 9) — not because it is slow everywhere, but because
once other layers can ask for anything at any time, the property is unrecoverable.

**How the batching is done is transport-specific, and was measured rather than assumed.**

| Transport | Mechanism | Measured, per simulated hour |
| --- | --- | --- |
| TraCI | Variable and context subscriptions registered once at `start()` | 7.30 s vs 71.05 s polling — **~10× faster** |
| LibSUMO | Direct batched getters | 1.49 s vs 2.57 s subscribed — **~1.7× faster than subscribing** |

An earlier version of this section mandated subscriptions for both. That was wrong for LibSUMO,
which has no socket and therefore gains nothing from subscription bookkeeping while paying for
it — and LibSUMO is the transport intended for every heavy workload. The mechanism sits behind
the `D-002` seam; T1.4's byte-identical-`TrueState`-across-transports test is what keeps the two
implementations honest.

Context subscriptions remain the right tool for M3's radius-limited sensor queries. That is a
different question from per-step whole-state projection.

### 5.3 Projection, not re-implementation

Per `D-003`, the adapter projects into canonical types and stops. It does not model vehicle
dynamics; SUMO does. The inclusion test applies to every field: *name the controller, sensor,
metric, estimator, or experiment that reads it.* If you cannot, it does not enter `TrueState`.

### 5.4 Startup assertions

The adapter refuses to run unless the methodology preconditions hold (`D-008`):

- `--time-to-teleport -1` is set,
- the step length divides the configured decision interval (`D-020`),
- a loaded snapshot's network hash matches the current network (`D-032`),
- the SUMO version matches the one recorded in the manifest when a snapshot is loaded.

These are hard failures at startup. A run that violates them produces no results rather than
wrong ones.

---

## 6. Process and execution model

### 6.1 One run, one process

Per `D-031`, the runner is designed around **N independent runs**, not one run in a loop.
Each run is self-contained: its own config, its own derived seeds, its own process, its own
output file, no shared mutable state.

This is the largest single performance lever available (near-linear in cores), it is nearly
free if designed in from the start, and it composes with LibSUMO's one-simulation-per-process
constraint rather than working around it.

```text
runner (parent)
  ├── expand config → list of run specs (controller × demand × seed × ...)
  ├── derive seeds per run spec from the master seed
  ├── spawn worker processes, bounded by --jobs
  │     └── worker: build scenario → run → write results.parquet + manifest
  └── collect: concatenate parquet, validate, emit the experiment record
```

A worker that crashes fails its run and no other. A run marked invalid by a validity check
(`D-008`) is written with its invalidity flag rather than dropped silently — a missing run and
an invalid run are different facts, and the analysis layer must be able to tell them apart.

### 6.2 The step loop

Where the decision-interval throttle from `D-020` lives, and why the two tiers are separate:

```python
while sim.time < end_time:
    backend.step()                          # SUMO advances one step
    true_state = backend.project()          # one batched subscription fetch

    constraint_layer.step(sim.time)         # EVERY step: timers, yellow, all-red
    metrics.accumulate(true_state)          # EVERY step: cheap array appends
    if trace_enabled:
        trace.record(true_state)            # opt-in only (D-009)

    if sim.time >= next_decision_time:      # EVERY Δt: the expensive part
        obs = sensor.observe(true_state, sim.time)
        est = estimator.update(obs, sim.time)
        req = controller.decide(est, sim.time)
        result = constraint_layer.submit(req, sim.time)
        if trace_enabled:
            trace.record_decision(obs, est, req, result)
        next_decision_time += decision_interval
```

The separation is a safety property, not an efficiency one: if the constraint layer only ran
at decision points, a yellow interval could overrun by up to Δt. Throttling the policy is an
approximation; throttling the timers is a defect.

---

## 7. Configuration, manifests, and reproducibility

**Configuration** is Pydantic v2 models with YAML on disk (`D-004`). Validation happens at
load: an invalid config fails before the simulator starts, with an error naming the field.

**The manifest** is what makes `02_PROJECT_CHARTER.md` S1 true. Every run emits one:

| Field | Why |
| --- | --- |
| Config hash | Identifies the exact configuration |
| Full resolved config | So the run reproduces without the original file |
| Code version | Git SHA, or a dirty-tree marker |
| SUMO version | State files and behaviour are version-sensitive |
| All derived seeds, per stream | `D-017`; ablations are uninterpretable without this |
| Δt per controller | `D-020`; comparability caveat |
| Warm-up design | Self warm-up or neutral snapshot (`D-032`) |
| Validity counters | Teleports, insertion failures, gridlock (`D-008`) |
| Trip accounting | Boundary sinks, mid-link arrivals, still in-network (`D-022`) |
| Wall-clock and peak memory | Feeds the performance baseline (`D-031`) |

A result without a manifest is not a result.

---

## 8. Trace and rendering

Per `D-009`, record-then-replay. The simulation optionally writes a trace; the renderer is an
independent consumer with no dependency on the simulator and no ability to affect it.

The trace format (`D-030`, still open) must reserve channels for observations, estimated
state, and controller decisions from M2 onward, even though they are only populated at M3.
Adding them later would invalidate every earlier trace, and those overlays are the entire
justification for building a custom renderer rather than using `sumo-gui`.

Traces are **off by default**. Batch sweeps write none, which removes trace I/O from the hot
path by construction rather than by remembering to disable it.

---

## 9. Extension points

### 9.1 Perception (`D-005`)

Seam 2 is the reserved extension point. The obligation is specific: a detection stream
derived from pixels must substitute for the parametric sensor **with no change to estimators,
controllers, or experiments.**

The design requirement that makes this true: `Observation` is *a stream of detections with
uncertainty*, not a structure that assumes geometric generation. A detection carries a
position estimate, a velocity estimate, a class with confidence, and a covariance or
equivalent — all things a real detector produces. Nothing in it references field of view,
range, or any other parameter of how it was made.

If the perception track ever runs, its most valuable output is not a working detector. It is
the comparison: **how well did the parametric model approximate real detector behaviour?** A
good approximation retroactively validates every M3 result.

### 9.2 A second backend (`D-001`)

Seam 1 exists. No second implementation is planned, and per `01_CRITICAL_REVIEW.md` R-2 the
domain model is kept deliberately small so that the seam stays cheap. If portability ever
becomes a real goal, adopting LibSignal or PyTSC is likely cheaper than having maintained a
bespoke abstraction for years — and that remains true precisely because we did not build one.

---

## 10. Module map

Per `D-014`. Directories are created when code goes into them.

| Package | Contains | Depends on |
| --- | --- | --- |
| `domain/` | Canonical types: network, `TrueState`, `Observation`, `EstimatedState`, actions | nothing |
| `backend/` | Adapter, transports, projection, startup assertions | `domain` |
| `scenarios/` | Network generation, demand generation, snapshots | `domain` |
| `sensing/` | `SensorModel`, `CameraSensor`, `OracleSensor` | `domain` |
| `estimation/` | Estimators | `domain` |
| `control/` | Constraint layer, all controllers | `domain` **minus `TrueState`** |
| `metrics/` | Definitions, accumulators, validity checks | `domain` |
| `experiments/` | Runner, seed derivation, manifests | all of the above |
| `trace/` | Trace writer and reader | `domain` |

**Dependency rules, checked by test:**

1. `control/` does not import `TrueState` (§4.3).
2. Only `backend/` imports TraCI or LibSUMO. Enforcing
   `00_RESEARCH_SPECIFICATION.md` §25's hard boundary as a test rather than a convention.
3. `domain/` imports nothing from the project. It is the vocabulary; it cannot depend on
   users of the vocabulary.
4. The renderer and analysis tools do not import `backend/`.

---

## 11. What this architecture deliberately does not have

Recorded so nobody adds them, and so a reviewer has a list.

| Absent | Why |
| --- | --- |
| A plugin/registry system | Three controllers is not three plugins. `D-031` anti-patterns. |
| An event bus or observer framework | The step loop is a loop. It is readable as one. |
| A dependency-injection container | Constructor arguments. |
| An abstract base class hierarchy for controllers | A `Protocol` with one method. No inheritance. |
| A generic `Simulation` interface above the backend | That is what the backend adapter already is. Two layers of the same abstraction is one too many. |
| Live streaming from simulation to renderer | `D-009`. Record-then-replay. |
| Async or threading in the run path | One run is sequential; parallelism is across processes (§6.1). |
| A database server | Parquet files and DuckDB (`D-004`). |

---

## 12. Amendment

This document changes when a seam is added or removed, when a dependency rule changes, or
when a layer's responsibilities move. All three are decision-register events, not
implementation details.
