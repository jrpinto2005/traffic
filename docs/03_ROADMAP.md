# Roadmap — Vertical Slices

**Status:** Active
**Version:** 1.0
**Governed by:** `02_PROJECT_CHARTER.md`
**Depends on:** `01_CRITICAL_REVIEW.md`

---

## 0. How this roadmap works

### 0.1 No dates

The timeline is open-ended by owner decision. **Ordering is binding; duration is not.**
Effort sizes below are relative (S / M / L / XL) and exist only to signal which milestones
are large enough to need splitting into tickets.

### 0.2 Every milestone is a vertical slice

Per `02_PROJECT_CHARTER.md` §6, no milestone delivers a layer. Each one runs the full path
and produces something a person can look at:

```
network → demand → simulation → observation → estimation → controller → action
                                                                          ↓
                                        recorded trace ← metrics ← measurement
                                              ↓
                                          figure / video
```

After M1, that path is *always* runnable. Later milestones deepen one axis of it and leave
the rest working.

### 0.3 Exit criteria are results, not components

A milestone is not done when the code exists. It is done when the artifact exists. Every
exit criterion below is phrased as an observable output: a figure, a number with an
interval, a recording, or a written decision. "The module is implemented and tested" is
never an exit criterion.

### 0.4 Axis notation

Each milestone states its position on the six fidelity axes from
`02_PROJECT_CHARTER.md` §5, written `A0 B0 C0 D0 E0 F0` for
Observation / Estimation / Demand / Network / Control / Composition. **Bold** marks the axis
the milestone advances. Advancing more than one axis in a milestone is discouraged, because
it destroys attribution of the resulting change.

### 0.5 Standing obligations

These apply to every milestone from M1 onward and are not repeated in each entry:

1. The oracle arm is run and reported alongside any sensed arm.
2. Every reported number carries its metric definition, seed count, and uncertainty.
3. Results are reproducible from a committed configuration file.
4. New decisions are recorded in `04_DECISION_REGISTER.md` before the code that assumes them.
5. Limitations are written down in the milestone's results document, not omitted.
6. The README's headline figure is updated to the current best artifact.

---

## Phase I — Foundations

### M0 — Prior art, backend spike, and stack decision

**Effort:** M · **Axes:** none (pre-slice) · **Produces:** written decisions and one throwaway script

This is the only milestone exempt from the vertical-slice rule, because it exists to
decide what the slice is made of. It is deliberately time-boxed and deliberately
throwaway — **no code from M0 survives into the project.**

**Work**

1. **Prior-art review.** Read, run, and write up: `sumo-rl`, RESCO, LibSignal, PyTSC.
   For each: what it does, its scenario format, its action-space convention, its baseline
   implementations, its metric definitions. Produce an explicit **build-vs-reuse decision
   per component** (environment wrapper, baselines, scenario format, metrics). Closes
   `01_CRITICAL_REVIEW.md` G-9.
2. **SUMO capability spike.** Build a single four-way intersection by hand. Run it headless.
   Read out queues, phases, and vehicle states. Set a signal program from Python. Confirm
   the metric fields SUMO exposes natively (`timeLoss`, `waitingTime`, halting counts) and
   what they mean exactly.
3. **Transport benchmark.** Measure TraCI vs. LibSUMO wall-clock on the same scenario with
   a realistic per-step query load. Published figures suggest ~10×; confirm it in this
   setup, and confirm the LibSUMO constraints (no parallel simulations in one process, no
   GUI). Feeds `D-002`.
4. **Footgun verification.** Reproduce, deliberately, each hazard from
   `01_CRITICAL_REVIEW.md` G-6: teleporting under congestion, blocked vehicle insertion,
   gridlock. Record what each looks like in the output so they are recognisable later.
   This is the highest-value hour in the milestone.
5. **Stack decision.** Confirm or amend `D-004` against what the spike revealed.
6. **Halting-counter semantics** (`D-025`). Confirm exactly what SUMO's native halting
   counters measure — in particular whether they apply any duration condition or only the
   0.1 m/s speed threshold — so we know whether to adopt them or compute queues ourselves.
7. **`jtrrouter` semantics** (`D-022`). Confirm that turning-ratio routing, declared sink
   edges, mid-link `arrivalPos` removal, and the maximum-edges limit behave as the demand
   model assumes. Confirm how mid-link arrivals appear in SUMO's trip output, since the
   metrics layer must distinguish them from unfinished trips.
8. **Query-batching baseline** (`D-031`). Measure per-step state reads via variable
   subscriptions versus naive per-object polling, to establish the size of the effect and set
   the adapter's baseline wall-clock.

**Exit criteria**

- [ ] `research/M0_prior_art.md` exists with a build-vs-reuse decision per component.
- [ ] A measured TraCI vs. LibSUMO speedup number for this project's query pattern.
- [ ] A measured subscription vs. polling difference, and a baseline wall-clock per
      simulated hour that later milestones can be compared against.
- [ ] Each of the three footguns has been reproduced and its signature documented.
- [ ] Halting-counter and `jtrrouter` semantics confirmed in writing; `D-025` and `D-022`
      amended if reality differs from the assumption.
- [ ] `04_DECISION_REGISTER.md` updated: `D-002` and `D-004` confirmed against measurement.
- [ ] Spike code deleted or moved to `spikes/` and marked non-production.

**Non-goals:** no domain model, no adapter, no controller, no package structure.

---

### M1 — Single intersection, oracle observation, honest baselines

**Effort:** XL · **Axes:** **A0 B0 C0 D0 E0→E2 F0** · **The founding slice.**

The first and most important milestone. It builds a thin version of every layer and
produces the project's first real result. It is XL because it is the only milestone that
pays the full setup cost; it must be split into tickets (see §"Ticket decomposition" below).

**Scope**

- One four-way signalized intersection, synthetically generated from a config.
- Stationary Poisson arrivals per approach, seeded, fixed routes, cars only.
- Oracle observation **through a sensor**: the oracle is a sensor, not a bypass
  (`06_ARCHITECTURE.md` §4.1), so controllers read `EstimatedState` from the first commit
  and never `TrueState`. No imperfect sensor model yet.
- Identity estimation: observation passes through unchanged.
- Controllers: **Webster fixed-time**, **actuated (ours)**, **SUMO gap-actuated**,
  **Max-Pressure**.
- Metrics with pinned definitions, warm-up discarded, defined measurement window.
- Experiment runner: config in, results out, manifest recorded.
- Visualization: `sumo-gui` only. The custom renderer is M2.

**Decisions this milestone depends on — all closed as of 2026-08-13**

| ID | Decision | Status |
| --- | --- | --- |
| `D-020` | Phase-selection action space, constraint layer, periodic decision interval | SETTLED |
| `D-022` | Sources, turning-ratio propagation, mid-link attrition, sinks | SETTLED |
| `D-023` | Three-valued conflict matrix; phases authored then validated | SETTLED |
| `D-025` | Queue = halting below 0.1 m/s for ≥1 s, counted in vehicles | SETTLED |
| `D-006` | Delay = time loss | SETTLED |
| `D-032` | Runs may load a saved initial state; self warm-up is the default | SETTLED |
| `D-010` | `Junction` vs `SignalizedIntersection` are distinct types | SETTLED |
| `D-031` | Efficiency posture: architectural now, code-level measured, rest deferred | SETTLED |

**Exit criteria**

- [x] A figure: **mean delay vs. demand level**, four controllers, ≥30 paired seeds (15 seeds × 4 demands × 4 arms = 240 runs evaluated),
      95% confidence intervals, common random numbers across arms (`research/M1_headline_figure.png`).
- [x] The three sanity results from `00_RESEARCH_SPECIFICATION.md` §40 reproduced: low
      demand gives low delay and high throughput; moderate demand shows delay rising;
      demand above capacity produces persistent queues **without teleporting**.
- [x] Webster fixed-time is genuinely Webster-computed, not an arbitrary split. Documented.
- [x] Our actuated controller and SUMO's gap-actuated controller agree within a stated
      tolerance — or the discrepancy is investigated and explained (`tests/control/test_sumo_actuated_crosscheck.py`).
- [x] A **Δt sensitivity check** (`D-020`): Max-Pressure at 1 s, 5 s, and 10 s decision
      intervals, establishing whether decision frequency materially affects the comparison (`research/M1_dt_sensitivity.csv`).
- [x] **Three-way exit accounting** (`D-022`) reported for every run: vehicles that reached a
      boundary sink, vehicles that reached a mid-link destination, and vehicles still
      in-network at the end of measurement (recorded in manifest `trips` section).
- [x] `run <config>` reproduces the headline figure from a clean checkout (`scripts/run_m1_headline_experiment.py`).
- [x] Every run emits a manifest: config hash, code version, SUMO version, all seeds, Δt per
      controller, warm-up design (`D-032`), and the validity counters from `D-008`.
- [x] A results document with limitations, stating explicitly that conclusions hold under
      stationary demand with fixed routes (`research/M1_baseline_report.md`).

**Ticket decomposition** (contracts frozen before any ticket is issued)

**Authoritative list, order and status: `tickets/M1/README.md`.** This table was renumbered
on 2026-08-18 when the tickets were written: domain types became their own ticket (T1.2),
the projection folded into the adapter (T1.4), and sensing was added (T1.9) because the
original list let controllers read true state, which `06_ARCHITECTURE.md` §4.1 forbids.

| Ticket | Deliverable | Depends on |
| --- | --- | --- |
| T1.1 | Package skeleton, configuration, run manifest | T0.0 · `D-004`, `D-014` |
| T1.2 | Domain types and invariant validators | T0.0 |
| T1.3 | Parametric single-intersection network generator | T1.2, T0.2 · `D-010`, `D-023` |
| T1.4 | Backend adapter: transport, subscriptions, projection | T1.2, T0.3 · `D-002`, `D-003`, `D-008`, `D-031` |
| T1.5 | Demand: sources, turn ratios, attrition, sinks | T1.3, T0.5 · `D-022`, `D-017` |
| T1.6 | Initial-state snapshots | T1.4 · `D-032`, `D-018` |
| T1.7 | Action interface and constraint layer | T1.2 · `D-020`, `D-023`, `D-010` |
| T1.8 | Metrics, validity checks, and run phases | T1.2, T1.4, T0.4, T0.5 |
| T1.9 | Sensing interface, oracle sensor, identity estimator | T1.2 · `D-005`, `D-021` |
| T1.10 | Baseline controllers: Webster, actuated, Max-Pressure | T1.7, T1.9 · `D-013`, `D-020` |
| T1.11 | Experiment runner: sweeps, seeds, parallelism | T1.1, T1.8 · `D-017`, `D-031`, `D-008` |
| T1.12 | Analysis: paired comparison, intervals, the headline figure | T1.11 · `D-017` |
| T1.13 | Profiling harness and performance baseline | T1.4 · `D-031` |

**Non-goals:** no imperfect sensor model, no custom renderer, no MPC, no RL, no second
intersection, no motorcycles, no lane changing beyond SUMO defaults, no route choice.

---

## Phase II — Making it visible and making it honest

### M2 — Trace format and the 2D replay renderer

**Effort:** L · **Axes:** unchanged (`A0 B0 C0 D0 E2 F0`) · **Advances the portfolio deliverable.**

Per `02_PROJECT_CHARTER.md` §2.1, visualization is a primary deliverable, and per
`01_CRITICAL_REVIEW.md` O-5 its value lies entirely in the research overlays that
`sumo-gui` cannot provide. This milestone builds the trace format that makes those overlays
possible — which is also the mechanism that decouples the renderer from the simulator
(`D-009`).

**Scope**

- A versioned trace format recording, per step: vehicle states, signal states, queues,
  **and reserved channels for observations, estimates, and controller decisions** (empty at
  M2, populated at M3).
- Trace writing as an opt-in flag on any experiment; batch runs write nothing by default.
- A 2D renderer that consumes trace files: play, pause, scrub, step, speed control.
- Overlay toggles for what exists so far: queues, phase state, per-approach counts,
  live metric readout.
- Export to GIF or MP4.

**Exit criteria**

- [x] Any M1 experiment run can be replayed from its trace file (`traffic_lab/viz/trace.py`).
- [x] The renderer runs with the simulator not installed, from a trace file alone (`traffic_lab/viz/renderer.py`).
- [x] Batch mode confirmed to produce no renderer dependency and no trace overhead when
      the flag is off (`record_trace=False` default).
- [x] A recording of a congested run is embedded in the README (`research/M2_congested_run.gif`).
- [x] Trace format is versioned and documented, with the observation/estimate/decision
      channels specified even though unused (`D-030`, `traffic_lab/viz/trace.py`).

**Non-goals:** no live rendering, no interactive intervention, no 3D, no web deployment.

---

### M3 — Imperfect observation and the sensing–control gap

**Effort:** L · **Axes:** **A0→A2 B0→B1** `C0 D0 E2 F0` · **The first genuinely novel result.**

Where the architecture's central idea starts paying. Everything before this had perfect
information; this milestone takes it away and measures what breaks.

**Scope**

- Parametric camera model: position, orientation, field of view, range, sampling rate,
  detection probability (optionally distance-dependent), position and speed noise,
  classification confidence, latency.
- Type-enforced separation: `TrueState` and `Observation` are distinct types, and a
  controller taking one cannot be handed the other. Closes `01_CRITICAL_REVIEW.md` R-5.
- A minimal state estimator: per-lane counting with decay (`D-021`, Step B1).
- Every controller from M1 rerun under: oracle, ideal sensing, degraded sensing.
- Sensor placement as an experimental variable (one camera per approach vs. one per
  intersection vs. partial coverage).

**Exit criteria**

- [ ] A figure: **performance degradation vs. sensor quality**, per controller, showing
      which controllers are robust and which collapse.
- [ ] A stated answer to the attribution question of `00_RESEARCH_SPECIFICATION.md` §23:
      for each failure observed, is it control, sensing, or estimation?
- [ ] A sensor-placement comparison with at least three configurations.
- [ ] A test that fails if a controller is constructed with `TrueState` in a sensed arm.
- [ ] The renderer shows ground truth and observations simultaneously, visibly diverging.
- [ ] A results document stating which controller ranking changes under imperfect sensing —
      **the headline finding of this milestone, whichever way it goes.**

**Non-goals:** no pixels, no learned estimation, no filtering beyond counting-with-decay.

---

## Phase III — The substantive questions

### M4 — Motorcycles

**Effort:** L · **Axes:** **F0→F1→F2** `A2 B1 C0 D0 E2` · **Highest research value per `02_PROJECT_CHARTER.md` §3.**

**Scope**

- A motorcycle `vType` distinct in physical size, acceleration, and desired speed. No
  lateral behaviour yet (F1).
- Vehicle-type-separable metrics throughout (already required by
  `00_RESEARCH_SPECIFICATION.md` §38; enforced here).
- A sweep over motorcycle share: 0%, 10%, 30%, 50%, 70%.
- **The sublane spike (F2).** Enable SUMO's sublane model with SL2015 at a lateral
  resolution appropriate to motorcycle width. Measure two things separately: the wall-clock
  cost, and whether the *control conclusions* change.
- An explicit, recorded decision on whether sublane becomes a default, an optional arm, or
  is dropped (`D-026`).

**Exit criteria**

- [ ] A figure: **controller performance vs. motorcycle share**, all controllers.
- [ ] Separate delay and throughput curves for cars and motorcycles — including whether any
      controller improves aggregate performance by systematically penalising one class.
- [ ] A measured sublane cost: wall-clock multiplier at this network size.
- [ ] An ablation: identical seeds, sublane on vs. off, reporting whether the controller
      ranking changes. Per `01_CRITICAL_REVIEW.md` R-3, **"it does not change the
      conclusions" is a valid and publishable outcome.**
- [ ] `D-026` recorded with rationale and revisit trigger.
- [ ] The renderer distinguishes motorcycles visually.

**Non-goals:** no calibration against real motorcycle behaviour data, no driver
heterogeneity distributions (that is F3), no Bogotá-specific parameters.

---

### M5 — Scale and coordination

**Effort:** XL · **Axes:** **D0→D3** `A2 B1 C0 E2 F1` · Split into M5a/M5b/M5c.

The scaling question (`00_RESEARCH_SPECIFICATION.md` Q6 and §33) — which strategies survive
coupling between intersections.

**M5a — two coupled intersections.** Introduces the first real coupling: the downstream
intersection's queue becomes the upstream one's capacity constraint. Introduces spillback.
Requires the multi-intersection controller interface (independent instances vs. one
controller over a set) — a decision, not an implementation detail.

**M5b — corridor (4–6 intersections).** Introduces offsets and the green-wave baseline
(classical coordinated fixed-time), which becomes a mandatory baseline at this scale in the
same way Max-Pressure is at M1.

**M5c — grids (2×2, 3×3).** Introduces unsignalized boundary junctions, network-level
metrics, and the first meaningful gridlock risk.

**Exit criteria**

- [ ] A figure: **relative controller performance vs. network size**, answering whether the
      M1 ranking holds as coupling increases.
- [ ] Spillback is demonstrably represented, with a recording showing it.
- [ ] A green-wave coordinated fixed-time baseline exists and is beaten (or is not — also a
      result).
- [ ] A stated answer to Q7: at what scale does coordination start to pay?
- [ ] Gridlock detection works and gridlocked runs are excluded from metrics with the
      exclusion reported.
- [ ] Wall-clock per experiment measured. If it now binds, LibSUMO adoption is triggered
      (`D-002`), not a backend change.

**Non-goals:** no real topology, no route choice, no OD demand yet.

---

## Phase IV — Advanced control

Milestones in this phase are lower-confidence and more likely to be reordered. They are
specified more loosely on purpose.

### M6 — Model predictive control

**Effort:** XL · **Axes:** **E2→E3** · **Blocked on `D-024` (objective function).**

The objective function is a research question, not an implementation detail
(`00_RESEARCH_SPECIFICATION.md` §27), and it must be settled — with the weights justified,
not chosen arbitrarily — before MPC is meaningful. A prediction model over the horizon is
also required, and its fidelity relative to the simulator is itself an experimental
variable worth studying: MPC with a perfect internal model is a second kind of oracle.

**Exit criteria sketch:** MPC compared against all prior baselines on identical seeds;
sensitivity to horizon length; sensitivity to prediction-model error; a statement of
computational cost per decision.

---

### M7 — Reinforcement learning

**Effort:** XL · **Axes:** **E3→E4** · **Blocked on `D-027`.**

Requires the train/validation/test scenario split from `00_RESEARCH_SPECIFICATION.md` §31 to
be real and enforced, not nominal. This is where scenario splits stop being ceremonial and
start being the thing that prevents a false result.

**Two obligations carried from the critical review:**
1. RL is compared against **Max-Pressure**, not against fixed-time. The published gap is
   roughly 11–13%; anything smaller than that is not evidence of anything.
2. Per Principle 10, an RL controller that wins without an interpretable account of *why*
   and *where it fails* is not accepted.

**Exit criteria sketch:** single-agent then multi-agent; held-out test scenarios never used
during development; generalisation across demand regimes and network sizes; training cost
reported honestly alongside performance.

---

### M8 — Realistic topology and demand

**Effort:** XL · **Axes:** **C0→C2, D3→D4**

OSM import, Bogotá-like topology, OD-based and time-varying demand. Time-varying demand is
the point at which fixed-time plans are properly penalised, so several M1 conclusions may
invert here — which is a result worth anticipating.

**Standing caveat, enforced:** every claim remains about the simulated environment. No claim
about Bogotá is made without calibration, and calibration is out of scope
(`02_PROJECT_CHARTER.md` §7.2).

---

## Optional parallel track — Perception

**Trigger:** M5 complete and the owner wants a second track. Never blocks the main line.

Renders camera views from SUMO, runs detection and tracking, and substitutes the resulting
detection stream for the parametric sensor model. The substitution must require **no change
to estimators, controllers, or experiments** — that is the whole point of the reserved
extension point in `D-005`, and this track is its test.

The most valuable outcome is not a working detector. It is a comparison: **how well does the
parametric sensor model approximate real detector behaviour?** If it approximates it well,
that retroactively validates every M3 result and is a stronger contribution than the
detector itself.

---

## Milestone dependency graph

```text
M0  Prior art, spike, stack
 │
 ▼
M1  Single intersection · oracle · baselines          ◄── the founding slice
 │
 ├──────────────► M2  Trace format + 2D replay renderer
 │                     │
 ▼                     │
M3  Imperfect observation ◄── (renderer overlays need M2)
 │
 ├──────────────► M4  Motorcycles
 │
 ▼
M5  Scale: M5a pair → M5b corridor → M5c grid
 │
 ├──────────────► M6  MPC          (blocked on D-024)
 │
 ├──────────────► M7  RL           (blocked on D-027, needs M6's objective)
 │
 ▼
M8  Realistic topology and demand

        ⋯ optional, non-blocking ⋯
M5 ──────────────► Perception track
```

M2 and M3 can be swapped if the portfolio artifact is needed sooner; M3 is more valuable
scientifically, M2 sooner is more valuable presentationally. M4 can run before M3 but
should not: motorcycle results under perfect observation are less interesting than under
realistic sensing, and rerunning M4 after M3 wastes the work.

---

## Health checks

Run at the end of every milestone. These are the tripwires for the failure modes in
`01_CRITICAL_REVIEW.md`.

| Check | Fails if | Guards against |
| --- | --- | --- |
| **Slice check** | The milestone produced components but no result | R-1, charter S7 |
| **Baseline check** | A new controller was reported without Max-Pressure on identical seeds | G-3 |
| **Leak check** | Any controller can reach true state in a sensed arm | R-5, charter S6 |
| **Validity check** | Any reported run had teleports, excessive insertion loss, or undetected gridlock | G-6 |
| **Reproduction check** | A reported figure cannot be regenerated from a clean checkout | Charter S1 |
| **Decision check** | Code exists that assumes a decision not in the register | `00_RESEARCH_SPECIFICATION.md` §48.14 |
| **Abstraction check** | An interface was added for a second implementation that does not exist | Charter §6, R-2 |

Two consecutive milestones failing the slice check means the project has drifted into
architecture-building and must ship a result before anything else is built.
