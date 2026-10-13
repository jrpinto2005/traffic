# Decision Register

**Status:** Living document. Updated before the code that assumes a decision, never after.
**Version:** 1.12 — see §6 for the change log
**Governed by:** `02_PROJECT_CHARTER.md`

---

## 0. How to use this register

This is the single source of truth for what has been decided. It exists to enforce
`00_RESEARCH_SPECIFICATION.md` §48.14 — that no implementation shortcut silently
invalidates the research methodology — by making the set of made decisions explicit and
checkable.

### 0.1 Status values

| Status | Meaning | Who may act |
| --- | --- | --- |
| **SETTLED** | Decided. Implementation may rely on it. | Anyone |
| **PROPOSED** | The architect's recommendation, awaiting owner ratification. | Nobody may build on it yet |
| **OPEN** | Genuinely undecided. Requires a spike, research, or an owner call. | Nobody. Escalate. |
| **DEFERRED** | Deliberately not now. Has a named revisit trigger. | Nobody |
| **SUPERSEDED** | Replaced by a later decision. Kept for the record. | Nobody |

### 0.2 The rule for implementation agents

> If your ticket requires a decision that is **OPEN**, **PROPOSED**, or absent from this
> register, **stop and escalate.** Do not choose. A guessed decision that happens to be
> reasonable is still a methodology defect, because it is undocumented and therefore
> un-revisitable.

### 0.3 Revisit triggers

Every non-trivial decision names the condition under which it should be reconsidered.
A decision without a trigger is either genuinely permanent or under-thought. Triggers are
checked at every milestone health check (`03_ROADMAP.md` §Health checks).

---

## 1. Index

| ID | Topic | Status | Blocks |
| --- | --- | --- | --- |
| [D-001](#d-001) | SUMO as sole backend; benchmark deferred | SETTLED | M0 |
| [D-002](#d-002) | Transport abstraction: TraCI then LibSUMO | SETTLED | M1 |
| [D-003](#d-003) | Domain model is a projection, not a re-implementation | SETTLED | M1 |
| [D-004](#d-004) | Technology stack | SETTLED | M1 |
| [D-005](#d-005) | Computer vision out of core; extension point reserved | SETTLED | M3 |
| [D-006](#d-006) | Primary delay = time loss + insertion delay (amended 2026-10-07) | SETTLED | M1 |
| [D-007](#d-007) | Queue definition — see D-025 | SUPERSEDED | — |
| [D-008](#d-008) | Teleporting disabled; gridlock and insertion loss detected | SETTLED | M1 |
| [D-009](#d-009) | Visualization is record-then-replay | SETTLED | M2 |
| [D-010](#d-010) | `Junction` vs `SignalizedIntersection` | SETTLED | M1 |
| [D-011](#d-011) | Two lane relations: `successor` and `adjacent` | SETTLED | M1 |
| [D-012](#d-012) | Unidirectional edges; no bidirectional primitive | SETTLED | M1 |
| [D-013](#d-013) | Mandatory baseline set | SETTLED | M1 |
| [D-014](#d-014) | Repository layout | SETTLED | M1 |
| [D-015](#d-015) | Five agent archetypes | SETTLED | M1 |
| [D-016](#d-016) | Documentation language: English | SETTLED | — |
| [D-017](#d-017) | Seed discipline, Monte Carlo replication, paired comparison | SETTLED | M1 |
| [D-018](#d-018) | Warm-up, measurement window, unfinished trips | SETTLED | M1 |
| [D-019](#d-019) | Deliverable is learning + portfolio | SETTLED | — |
| [D-020](#d-020) | Action space, constraint layer, periodic decision interval | SETTLED | M1 |
| [D-021](#d-021) | State estimation approach | OPEN | M3 |
| [D-022](#d-022) | Demand, routing, sources, sinks, mid-link attrition | SETTLED | M1 |
| [D-023](#d-023) | Conflict model and phase schema | SETTLED | M1 |
| [D-024](#d-024) | Objective function | OPEN | M6 |
| [D-025](#d-025) | Queue definition | SETTLED | M1 |
| [D-026](#d-026) | Sublane model as default | DEFERRED | M4 |
| [D-027](#d-027) | RL formulation | DEFERRED | M7 |
| [D-028](#d-028) | Multi-intersection controller scope | DEFERRED | M5a |
| [D-029](#d-029) | Pedestrian modelling | DEFERRED | — |
| [D-030](#d-030) | Trace format | OPEN | M2 |
| [D-031](#d-031) | Efficiency and reuse posture | SETTLED | M1 |
| [D-032](#d-032) | Initial-state snapshots | SETTLED | M1 |
| [D-033](#d-033) | Detections carry lane and stationary time; estimator receives signals | SETTLED | M1 |
| [D-034](#d-034) | `TrueState` signals decoded from SUMO's display | SETTLED | M1 |
| [D-035](#d-035) | Trip-level metrics come from SUMO's tripinfo | SETTLED | M1 |
| [D-036](#d-036) | Stop-line detection zone for gap-based actuation | SETTLED | M1 |
| [D-037](#d-037) | Saturation flow is calibrated in SUMO | SETTLED | M1 |
| [D-038](#d-038) | Inter-agent communication standard: ASD-STE100 and Two-Tier Reporting | SETTLED | M1 |
| [D-039](#d-039) | Modern agent architecture: Google Jules cloud execution & AGENTS.md interface | SETTLED | M1 |

**M1 is fully unblocked.** Every decision it depends on is SETTLED. The three remaining open
decisions — `D-021` (state estimation), `D-024` (objective function), `D-030` (trace format) —
block M3, M6, and M2 respectively, and none of them block the founding slice.

---

## 2. Settled and proposed decisions

<a id="d-001"></a>
### D-001 — SUMO is the sole simulation backend; the CityFlow benchmark is deferred

**Status:** SETTLED — ratified by owner 2026-08-13 · **Source:** `01_CRITICAL_REVIEW.md` O-1, R-2

**Decision.** SUMO is the only simulation backend. The multi-backend benchmark described in
`00_RESEARCH_SPECIFICATION.md` §6.3 is not performed now.

**Rationale.** The eleven-criterion benchmark in §6.3 is a multi-week engineering exercise
that must complete before any research output exists, on a project whose principal risk is
never reaching research output. It answers a question the project does not yet have.

Note a correction to an earlier assessment: CityFlow is *not* abandoned — it is roughly 20×
faster than SUMO and actively used in the large-scale RL literature. The argument for
deferral is not that the alternative is dead. It is that (a) there is no measured bottleneck
yet, (b) CityFlow abstracts away vehicle heterogeneity and detailed driver behaviour, which
is exactly what the motorcycle work needs, so it is not a drop-in faster SUMO, and (c) if
portability ever becomes the real goal, adopting LibSignal or PyTSC is likely cheaper than
having maintained a bespoke abstraction for years.

**Revisit trigger.** Wall-clock becomes a *measured* binding constraint on the experiment
budget — most plausibly during M7 RL training or a large M5 seed sweep. At that point the
first remedy is LibSUMO (`D-002`), then parallelism across processes, and only then a
different simulator.

---

<a id="d-002"></a>
### D-002 — The adapter abstracts its transport: TraCI first, LibSUMO when needed

**Status:** SETTLED — ratified by owner 2026-08-13 · **Source:** `01_CRITICAL_REVIEW.md` O-1; M0 spike

**Decision.** The backend adapter exposes one interface with two interchangeable transports.
Development and interactive work use TraCI. Batch and training workloads switch to LibSUMO
when wall-clock warrants it. The switch must be a configuration value, not a code change.

**Rationale.** LibSUMO embeds SUMO in the client process instead of talking over a socket,
and reported speedups are around 10× with identical method signatures. Because the
signatures match, the abstraction is nearly free — but only if it exists from the start.
Retrofitting it after controllers and experiments have hard-coded one transport is
expensive.

The constraints must be encoded in the abstraction, not discovered later: LibSUMO does not
support multiple concurrent simulations in one process, and does not support the GUI. So
parallel sweeps under LibSUMO require process-level parallelism, and any GUI use forces
TraCI.

**Revisit trigger.** M0 measures the actual speedup for this project's query pattern. If it
is under ~2×, the abstraction is still kept (it costs almost nothing) but LibSUMO adoption
drops in priority.

---

<a id="d-003"></a>
### D-003 — The canonical domain model is a read-only projection plus a command surface

**Status:** SETTLED — ratified by owner 2026-08-13 · **Source:** `01_CRITICAL_REVIEW.md` C-1, R-2

**Decision.** The project-owned domain model does **not** re-implement traffic dynamics. It
consists of:

1. **A projection** — canonical, backend-independent types describing the network topology
   and the true state at each step, populated from the backend.
2. **A command surface** — the actions the project can apply to the backend, principally
   signal control.
3. **Configuration types** — including vehicle-dynamics parameters, which are passed
   *through* to the backend and recorded for reproducibility, never interpreted by us.

**The inclusion test.** An attribute enters the domain model only if you can name the
controller, sensor, metric, estimator, or experiment that reads it. If you cannot, it stays
in SUMO. This test is applied at code review and is not negotiable — it is the only thing
preventing the abstraction tax described in R-2.

**Rationale.** Resolves the specification's central contradiction (C-1). Preserves
Principle 1 (backend independence) and Principle 9 (optionality) as a *boundary*, while
refusing the cost of a parallel model maintained against a single backend.

**Consequences.** `00_RESEARCH_SPECIFICATION.md` §§11–19 are reinterpreted as descriptions
of *concepts the project reasons about*, not modules the project builds. Its §44 items
"initial car-following model", "initial acceleration model", "initial braking model", and
"initial stochasticity" become SUMO `vType` configuration choices, recorded in the run
manifest.

**Revisit trigger.** A second backend is actually adopted, or a research question requires
modelling a phenomenon SUMO cannot express.

---

<a id="d-004"></a>
### D-004 — Technology stack

**Status:** SETTLED — ratified by owner 2026-08-13 · **Source:** `01_CRITICAL_REVIEW.md` G-10 · **Confirm in M0**

| Concern | Choice | Rationale |
| --- | --- | --- |
| Language | Python 3.12+ | SUMO's ecosystem, TraCI, LibSUMO, and the entire TSC literature |
| **Simulator install** | **`eclipse-sumo` from PyPI, pinned in `uv.lock`** | **Amended 2026-08-18 (T0.0).** Not a system package. Pins the SUMO version in the lockfile, so reproducing an experiment reproduces its simulator — `D-008` and Principle 7. Also guarantees the binary architecture matches the interpreter, which a Homebrew install on this machine would not have. |
| Dependency/env management | `uv` | Fast, lockfile-based, reproducible; single tool for envs and deps |
| Configuration | Pydantic v2 models, YAML on disk | Validation at load; typed configs; schema is self-documenting |
| Experiment results | Parquet via **polars' native writer**, queried with DuckDB | No server; columnar; handles large sweeps. **pyarrow is excluded — see below.** |
| Numerics | NumPy; Polars for results analysis | Polars over pandas for sweep-scale aggregation |
| Plotting | Matplotlib + a project style module | See the note below; alternatives were considered and rejected |
| Testing | pytest, with property-based tests for invariants | Invariant checking is load-bearing here |
| Lint/format | Ruff | Single tool |
| Type checking | mypy or pyright, strict on the domain package | The truth/observation separation depends on types being real |
| Renderer | Decide at M2 | Depends on the trace format; premature now |

**Note on the renderer.** Deliberately left open. The trace format (`D-030`) determines what
the renderer must consume, and choosing a rendering technology before knowing that is
backwards.

**Note on pyarrow — do not re-add it** (amended 2026-08-18 after T0.0).

`libsumo` bundles libarrow 24.0.0. Installing pyarrow alongside it produces a real ABI
collision, not a theoretical one: both register the `file` filesystem scheme, and
`pyarrow.parquet.write_table` then fails with
`ArrowKeyError: Attempted to register factory for scheme 'file'`.

This would have hit T1.11's experiment runner, which runs a simulation through libsumo and
writes Parquet **in the same process**, on every run of every sweep. It would have appeared
at M1 as an unexplained post-simulation crash pointing at a filesystem registry rather than
at a version conflict.

Polars writes and reads Parquet natively and DuckDB queries it natively; neither needs
pyarrow. Verified with pyarrow removed. Because pyarrow is the reflexive companion to
"Parquet", **this exclusion is recorded here so nobody re-adds it as an obvious dependency.**
Full evidence in `research/M0_environment.md`.

**Note on plotting** (owner asked whether something better than Matplotlib exists).
Matplotlib stays, and the reason is not inertia:

| Considered | Verdict |
| --- | --- |
| **Matplotlib** | **Chosen.** The only option that produces deterministic, versionable, publication-quality static output with full control over error bars, confidence bands, and small-multiple layouts — which is most of what this project plots. |
| Plotly / Bokeh | Rejected. Their advantage is interactivity in a browser. Our interactive need is *watching a simulation*, which the M2 renderer handles far better than a chart library would. Adds a dependency for a capability we get elsewhere. |
| Seaborn | Not rejected, just not needed yet. It is a thin layer over Matplotlib, so adding it later costs nothing. Worth it if statistical-plot boilerplate becomes annoying. |
| Plotnine (grammar of graphics) | Rejected for now. Genuinely more elegant for faceted comparisons, but it is a second mental model for the same output and the figures here are few and highly customised. |

The real quality lever is not the library. It is a **single project style module** —
`viz/style.py` — that fixes fonts, colours, figure sizes, and the house convention for
showing uncertainty, so that every figure in the repository looks like it came from the same
lab. Per `02_PROJECT_CHARTER.md` §2.1, figure quality is a portfolio deliverable, and
consistency across figures reads as rigour far more than any individual chart does.

**Revisit trigger.** A figure type appears that Matplotlib genuinely cannot express well; or
M2's renderer choice makes a shared dependency attractive.

---

<a id="d-005"></a>
### D-005 — Computer vision is outside the core; an extension point is reserved

**Status:** SETTLED (owner decision) · **Source:** `01_CRITICAL_REVIEW.md` G-2

**Decision.** The core platform models sensing **parametrically** — field of view, range,
detection probability, position and speed noise, latency — with parameters calibrated where
possible against published detector benchmarks. A real perception pipeline (rendering,
detection, tracking) is an **optional later track** that never blocks the main line.

**The reserved extension point is a real obligation, not a note.** The observation interface
must be defined such that a detection stream derived from pixels can be substituted for the
parametric one with **no change** to estimators, controllers, or experiments. Concretely:
the observation type is a stream of detections with uncertainty, not a structure that
assumes it was generated geometrically.

**Rationale.** Rendering camera views from SUMO and running detection and multi-object
tracking is comparable in size to the entire rest of the platform, and adds little to the
research questions the parametric model already lets us ask. Owner selected "optional later
track."

**Revisit trigger.** M5 complete and the owner wants a second track. See
`03_ROADMAP.md` §Optional parallel track.

---

<a id="d-006"></a>
### D-006 — Primary delay metric is time loss

**Status:** SETTLED — ratified by owner 2026-08-13 · **Source:** `01_CRITICAL_REVIEW.md` G-5

**Decision.** The primary reported delay metric is **time loss**: realised travel time minus
the travel time that would have been achieved at the desired speed over the same route.
SUMO computes this natively as `timeLoss`.

Secondary metrics, reported where relevant but never as the headline: stopped delay (time
below a speed threshold) and, at intersection level, an approximation of HCM control delay.

**Every reported delay figure must name its definition.** A number labelled only "delay" is
a defect.

**Rationale.** Time loss requires no geometric assumptions, is well-defined on networks and
across routes, is computed natively (so it cannot drift from our own implementation), and
captures acceleration and deceleration losses that stopped delay misses. The three
definitions can differ by a factor of two on the same run, so pinning one is not a
formality.

**Revisit trigger.** Comparison against a published result that reports control delay
specifically.

**Amended 2026-10-07, ratified by owner — the primary delay is `timeLoss + departDelay`.**
SUMO's `timeLoss` starts at insertion, so the time a vehicle waits to enter the network is in
no metric at all. Measured on the M0 reference net at 1500 veh/h per approach: mean
`departDelay` 274.1 s against mean `timeLoss` 64.3 s over 1327 completed trips. A controller
whose queues spill back to the boundary would therefore look *better*, and the ranking of two
controllers would depend on the approach length — an arbitrary modelling boundary (200 m).
Both terms come from SUMO's tripinfo (`D-035`), so the metric is still native and exact. The
two components are always reported separately as well, so the amendment never hides which
one moved. Unsaturated runs are unaffected in practice (`departDelay` ≈ 0).

---

<a id="d-007"></a>
### D-007 — *(superseded by D-025)*

**Status:** SUPERSEDED. Queue definition consolidated into `D-025`, now SETTLED.

---

<a id="d-008"></a>
### D-008 — Teleporting disabled; gridlock and insertion loss detected and reported

**Status:** SETTLED — ratified by owner 2026-08-13 · **Source:** `01_CRITICAL_REVIEW.md` G-6, R-5
**This is the highest-value decision in the register per unit of effort.**

**Decision.** Every research run:

1. Sets `--time-to-teleport -1`, disabling teleporting. The adapter **asserts** this at
   startup and refuses to run otherwise.
2. Counts vehicles that failed to insert. If the count exceeds a configured threshold, the
   run is **marked invalid** — the applied demand no longer matches the configured demand,
   so the experiment is measuring something other than what it claims.
3. Detects gridlock explicitly (no vehicle has moved for N steps) and marks the run
   gridlocked rather than reporting its metrics as valid.
4. Records all three counters in the run manifest, always, even when zero.

**Priority reordered 2026-08-18 after T0.4 was re-measured.** All three checks stay mandatory
from M1, but they do not carry equal weight at equal times:

- **Insertion loss is the threat that will actually fire at M1.** Swept on an isolated
  intersection with the signal running normally, demand at 2160 veh/h per approach produced
  **zero teleports** while 22% of configured demand never entered — and mean time loss rose only
  from 21.7 s to 60.0 s, because the vehicles that would have suffered worst never departed.
  A plausible-looking result over 78% of the intended demand is exactly the silent invalidation
  this decision exists to prevent.
- **Teleporting starts mattering at M5.** It requires a vehicle stuck *inside* the network; on an
  isolated intersection with ~190 m approaches, an over-capacity queue spills out of the network
  before anything can be trapped. A corridor or grid removes that escape.

The insertion-loss threshold therefore needs a justified value rather than a placeholder, and
T1.8 should treat it as the primary gate.

**Threshold set 2026-10-07, ratified by owner: 1 %.** Insertion loss is the number of vehicles
due during the measurement window that are still not inserted when it closes (SUMO's pending
list), divided by the number due in the window; above 1 % the run is invalid. Justification:
an order of magnitude below the 22 % T0.4 measured, and below the ≈ 3 % run-to-run spread of
realised Poisson demand at M1 volumes, so a run under the threshold cannot differ from its
configured demand by more than demand noise already does. Not configurable (non-goal 3 of
T1.8): a threshold that can be relaxed per experiment is not a threshold.

**Numerator refined 2026-10-07, ratified by owner — count only long waits.** T1.8's builder
showed the pending-list snapshot is fragile: when several flows release in the same second a
few vehicles wait one step to insert, and with ~190 vehicles due in a 600 s window two of them
at the closing instant already exceed 1 %. Insertion loss is now the number of vehicles
**scheduled at least 30 s before the window closes and still not inserted when it closes**,
divided by the number scheduled in the window, computed exactly from tripinfo's scheduled and
actual departures. A vehicle that has waited half a minute to enter means a queue reached the
boundary; one that waited a step does not. Delayed-then-inserted vehicles are already charged
through `departDelay` in the primary delay (`D-006`).

**Gridlock's N set 2026-10-08, ratified by owner — derived from the signal timing.** A run is
gridlocked when no vehicle has moved for **1.5 × the longest cycle the constraint layer can
produce**: the sum over phases of `max_green_s + yellow_s + all_red_s`, times 1.5, in steps.
A legitimate all-halted interval — one vehicle waiting at red while the signal serves empty
phases — can last almost a full cycle, so any fixed value is either a false positive on some
timing or slow to fire on another. Research runs must therefore set `max_green_s > 0`; a run
without it is refused. Not configurable.

**Rationale.** SUMO teleports stuck vehicles by default after 300s. Under congestion — the
regime where adaptive control is supposed to prove itself — this silently deletes the
congestion being measured, and deletes *more* of it for worse controllers. A default-settings
comparison can therefore show no difference between an excellent and a terrible controller,
or invert their ranking, with no visible error. Blocked insertions have the same character:
SUMO eventually discards them, quietly reducing applied demand.

None of these appear anywhere in the original specification, including its open-questions
list. They are the most likely mechanism by which this project produces confidently wrong
results.

**Revisit trigger.** None. This is permanent.

---

<a id="d-009"></a>
### D-009 — Visualization is record-then-replay

**Status:** SETTLED — ratified by owner 2026-08-13 · **Source:** `01_CRITICAL_REVIEW.md` G-12, O-5

**Decision.** Simulations optionally write a **trace file**. The renderer is an independent
consumer of trace files and has no dependency on, or coupling to, the simulator. There is no
live rendering path.

**Rationale.** Decouples renderer frame rate from simulator step rate; removes the need for
a streaming transport; keeps batch mode renderer-free by construction rather than by
discipline; and is strictly better for research, because you can scrub, pause, and re-watch
the exact run that produced a surprising number. Also makes the renderer independently
testable and independently shippable — it runs without SUMO installed.

**What is given up:** interactive intervention during a run (a human changing signals
mid-simulation). The specification does not ask for it.

**Revisit trigger.** A demonstrable need for human-in-the-loop intervention.

---

<a id="d-010"></a>
### D-010 — `Junction` and `SignalizedIntersection` are distinct concepts

**Status:** SETTLED — expanded on owner request, ratified 2026-08-14
**Source:** `01_CRITICAL_REVIEW.md` C-3

#### The problem in one sentence

`00_RESEARCH_SPECIFICATION.md` §8.1 says *"an intersection is a road-system unit containing
at least two coordinated signal groups"*, which means that under our own definition, **a
street corner with no traffic light is not an intersection** — so the system has no name for
it, no type for it, and no way to reason about it.

#### Why that is not a wording quibble

Unsignalized junctions are not an edge case we might encounter later. They are structurally
unavoidable and they carry real behaviour:

**1. Every network we build has them, starting at M5c.** A 3×3 grid of signalized
intersections has 9 controlled nodes and **12 boundary nodes** where traffic enters and
leaves. Those boundary nodes are junctions. If the type system cannot represent them, the
network generator cannot build the grid.

**2. They determine the capacity of the signalized ones.** A signal can only discharge a
queue as fast as the downstream link accepts vehicles. If the downstream link ends in an
unsignalized merge that is itself saturated, the green time is wasted. That is the
mechanism of spillback, and spillback is the headline phenomenon of M5. A model that cannot
represent the uncontrolled node cannot represent the thing that causes the congestion.

**3. Whether a node is signalized is an experimental variable.** A legitimate experiment is
"what happens if we de-signalize this intersection and make it a roundabout or a
priority junction?" Under §8.1's definition, that intersection would cease to exist when you
turn its signals off. An entity should not be deleted from the model by changing an
experimental parameter.

**4. Metrics need to cover the whole network, control needs to cover part of it.** Total
network delay includes delay accumulated at uncontrolled nodes. If "intersection" and
"controlled intersection" are the same word, every metric aggregation has to silently decide
which one it means, and different parts of the code will decide differently.

#### The fix

Split one word into two, along the line between *topology* (where roads meet) and *control*
(where we act):

| | `Junction` | `SignalizedIntersection` |
| --- | --- | --- |
| **What it is** | A node where lanes from more than one edge connect | A `Junction` that also has signals |
| **Answers** | "How is the network shaped?" | "Where can the controller act?" |
| **Carries** | Geometry, incoming/outgoing lanes, lane connections, conflict matrix, right-of-way rules | Everything a `Junction` has, **plus** signal groups, phases, and exactly one attached controller |
| **Constraint** | None; may have any number of approaches | `\|SignalGroups\| >= 2` (this is where §8.1's rule belongs) |
| **Consumed by** | Network generation, routing, metrics, spillback analysis | Controllers, the action interface, signal-timing metrics |
| **Example** | Grid boundary node, priority merge, roundabout, four-way stop | The nine controlled nodes of a 3×3 grid |

The relationship is **specialisation, not composition**: every `SignalizedIntersection`
*is a* `Junction`. Signalizing a junction promotes it; de-signalizing demotes it. Nothing is
created or destroyed.

#### Consequences in code

- A controller's scope is a set of `SignalizedIntersection`s. It is a type error to hand a
  controller a plain `Junction`.
- Routing, network metrics, and spillback analysis iterate over all `Junction`s.
- The conflict matrix (`D-023`) lives on `Junction`, not on `SignalizedIntersection` —
  because conflicts between movements are a fact of geometry that exists whether or not a
  signal is present. Phases, which are *derived* from the conflict matrix, live on
  `SignalizedIntersection`.
- This maps cleanly onto SUMO, which makes the same distinction: every node is a junction
  with a `type` attribute (`priority`, `right_before_left`, `traffic_light`, …), and only
  the `traffic_light` ones carry a program.

#### What the original definition got right, and is preserved

§8.1's refusal to assume a four-way geometry is correct and stays: `Junction` has no fixed
number of approaches, and geometry is data. The `|SignalGroups| >= 2` condition is also
correct — it just belongs on the narrower type.

**Revisit trigger.** None expected.

---

<a id="d-011"></a>
### D-011 — Two lane relations, and `Movement` is a view

**Status:** SETTLED — ratified by owner 2026-08-13 · **Source:** `01_CRITICAL_REVIEW.md` C-4, G-14

**Decision.** The lane graph has exactly two relations:

- **`successor`** — longitudinal and route-traversable. Includes continuation within an
  edge and crossings through a junction.
- **`adjacent`** — lateral, between parallel same-direction lanes. **Not** route-traversable.
  Lane changing operates over this relation.

`LaneConnection` is the single edge entity for `successor`. **`Movement` is a view, not a
stored entity**: the subset of lane connections crossing a junction, grouped by (approach,
turn direction), optionally annotated with a signal group.

**Rationale.** Merging lateral adjacency into the routing graph means every routing,
distance, and reachability computation must filter by edge type, and forgetting the filter
produces plausible-but-wrong answers. Storing `Movement` separately from `LaneConnection`
duplicates topology in two places that will drift.

**Revisit trigger.** None expected.

---

<a id="d-012"></a>
### D-012 — Edges are unidirectional; two-way streets are edge pairs

**Status:** SETTLED — ratified by owner 2026-08-13 · **Source:** `01_CRITICAL_REVIEW.md` G-15

**Decision.** Follow the SUMO and OpenStreetMap convention. A road edge has exactly one
direction. A two-way street is a pair of opposing edges, optionally linked by a reference.
No bidirectional primitive is introduced.

**Rationale.** Inventing a bidirectional primitive creates translation problems at both the
backend boundary and the future OSM-import boundary, for no benefit. Closes
`00_RESEARCH_SPECIFICATION.md` §11's TBD with the standard answer.

**Revisit trigger.** None expected.

---

<a id="d-013"></a>
### D-013 — Mandatory baseline set

**Status:** SETTLED — ratified by owner 2026-08-13 · **Source:** `01_CRITICAL_REVIEW.md` G-3

**Decision.** No advanced controller result may be reported until it has been compared, on
**identical seeds and identical demand realisations**, against all of:

1. **Webster fixed-time** — cycle length and green splits computed by Webster's method for
   the demand being tested. **Not** an arbitrary equal split.
2. **Actuated (ours)** — gap-based extension with min/max green.
3. **SUMO gap-actuated** — SUMO's own `type="actuated"` program, as an independent
   cross-check on our implementation.
4. **Max-Pressure.**

From M5b onward, **coordinated fixed-time (green wave)** joins the mandatory set for
corridor and grid networks.

Optional but recommended, both available in RESCO: SOTL and Max-Wave.

**Rationale.** Max-Pressure is the reference point in this literature: decentralized, needs
only upstream and downstream queue counts, has proven stability guarantees, and routinely
matches or beats deep RL. A project showing RL beating a naive 30s/30s plan has demonstrated
nothing.

**Qualification added 2026-08-18 after T0.1.** An earlier version of this rationale cited
"published gaps of 11–13%" without context. That figure is specifically RESCO's *synthetic
symmetric 4×4 grid validation* (NeurIPS D&B 2021 §4.1), computed over 5 unpaired seeds with
no warm-up and reported as the best episode of roughly a hundred — an optimistically biased
estimator, and not re-derivable from the paper since the underlying values are never printed.
The same paper's actual conclusion is that MPLight **diverges** on realistic irregular
networks and that synthetic scenarios "relate poorly" to real ones.

The decision is unchanged and arguably better supported. But the number is not a target: left
unqualified it becomes an expectation that a legitimate null result would have to argue
against three milestones from now. **Claim directional agreement with the literature, never
numerical agreement.**

Webster matters for the opposite reason: a *badly tuned* baseline manufactures improvement
out of nothing, and "30s NS / 30s EW" from `00_RESEARCH_SPECIFICATION.md` §26 is a badly
tuned baseline.

SUMO's actuated program is included because if our actuated controller diverges greatly from
SUMO's, one of them has a bug, and without the cross-check we will not know which.

**Revisit trigger.** A new baseline becomes standard in the literature.

---

<a id="d-014"></a>
### D-014 — Repository layout

**Status:** SETTLED — ratified by owner 2026-08-13 · **Source:** `01_CRITICAL_REVIEW.md` O-2

**Decision.** Start with one installable package and a small subpackage set. Split only when
a module actually grows. **No directory is created before code goes into it.**

```text
traffic_lab/              # the installable package
  domain/                 # canonical types: network, state, action, observation
  backend/                # SUMO adapter; transport abstraction (TraCI / LibSUMO)
  scenarios/              # network + demand generation
  sensing/                # sensor models and observation generation
  estimation/             # state estimators
  control/                # controllers (baselines and advanced)
  metrics/                # metric definitions, validity checks
  experiments/            # runner, sweeps, manifests
  trace/                  # trace writing and reading
configs/                  # YAML experiment configurations
results/                  # parquet outputs (gitignored)
research/                 # spike reports, per-milestone results documents
tests/
docs/                     # the numbered documents in this repository
```

**What was cut from `00_RESEARCH_SPECIFICATION.md` §42 and why:** `perception/` (deferred
per `D-005`), `optimization/` (merged into `control/` — MPC is a controller), `evaluation/`
vs `experiments/` vs `research/` (a three-way boundary nobody applies consistently; now
`metrics/` for definitions, `experiments/` for execution, `research/` for prose),
`visualization/` (a separate package at M2, decided then), `data/` (created when there is
data).

**Owner instruction attached to this ratification:** *"the code must be really flexible and
must reuse as much code as possible, let's also emphasize efficiency. This is a complex
project that needs to prioritize efficiency and scalability."* That instruction is about
engineering posture rather than directory layout, and taken literally it conflicts with
`02_PROJECT_CHARTER.md` §6 and Principle 8. It is therefore treated as its own decision and
reframed in **`D-031`**, which is PROPOSED and needs the owner's reaction.

**Revisit trigger.** A subpackage exceeds a size where its internal structure is unclear.

---

<a id="d-015"></a>
### D-015 — Five agent archetypes

**Status:** SETTLED — ratified by owner 2026-08-13 · **Source:** `01_CRITICAL_REVIEW.md` R-4

**Decision.** Replace the fourteen subject-matter roles of `00_RESEARCH_SPECIFICATION.md`
§43 with five archetypes distinguished by **the kind of contract they work under**:

| Archetype | Works from | Delivers | Autonomy |
| --- | --- | --- | --- |
| **Spike** | A question and a time box | A written finding; throwaway code | High — exploration is the point |
| **Builder** | A frozen interface + acceptance tests | An implementation passing those tests | Low — no design decisions |
| **Experimenter** | A config and a hypothesis | Results, figures, a written interpretation | Medium — may choose analysis, not methodology |
| **Reviewer** | A diff and the register | Findings, especially decision violations | N/A |
| **Scribe** | A completed milestone | Updated documents, results write-up | Low |

**Rationale.** Role taxonomy is not what makes delegation to weaker agents work. What makes
it work is frozen interfaces, executable acceptance criteria, small closed scope, explicit
per-ticket non-goals, and a named escalation path. Fourteen roles is more coordination
surface than a single-owner project needs.

The **Builder** archetype has deliberately low autonomy, and that is the crux: a Builder
that encounters an undocumented judgement call must escalate rather than decide. See
`08_AGENT_HANDOFF_PROTOCOL.md`.

**Revisit trigger.** Team size grows beyond one human.

---

<a id="d-016"></a>
### D-016 — Documentation is written in English

**Status:** SETTLED

**Decision.** All project documents, code identifiers, comments, and commit messages are in
English. Conversation with the project owner is in Spanish.

**Rationale.** Consistency with `00_RESEARCH_SPECIFICATION.md`, alignment with SUMO
documentation and the literature, no translation layer between docs and identifiers, and
portability of the portfolio artifact.

**Revisit trigger.** The owner prefers otherwise — this is a preference, not a technical
constraint, and reversing it early is cheap.

---

<a id="d-017"></a>
### D-017 — Seed discipline, Monte Carlo replication, and paired comparison

**Status:** SETTLED — ratified by owner 2026-08-13 · **Source:** `01_CRITICAL_REVIEW.md` G-4, R-5

**Decision.**

1. **Independent seed streams per source of randomness**: demand generation, driver
   imperfection, sensor noise, estimator (if stochastic), controller (RL exploration).
   Derived from one master seed by a documented scheme so that any single source can be
   held fixed while others vary. Without this, ablations are uninterpretable.
2. **Common random numbers across controller arms.** The same master seed must produce the
   *same vehicle arrivals* regardless of which controller is running. Comparisons are
   paired.
3. **Paired statistics.** Report the per-seed difference between arms and its confidence
   interval, not the difference of independent means. Paired comparison recovers most of
   the statistical power that independent sampling throws away.
4. **Seeds recorded in the manifest**, all of them, always.

**Rationale.** Controller comparison on different demand realisations wastes most of the
available power and can easily produce a "difference" that is entirely arrival noise.

**On Monte Carlo** (owner: *"we can use Monte Carlo and different seeds for evaluations"*).
Agreed, and this is exactly what the multi-seed design is — each seed is one Monte Carlo
replication of the stochastic system, and the metric of interest is estimated from the
sample across replications. Two refinements make it Monte Carlo done well rather than Monte
Carlo done naively:

1. **Common random numbers is a variance-reduction technique**, and it is the reason a
   paired design beats an unpaired one. Comparing arms on *independent* replications means
   the arrival noise appears in both samples and has to be averaged away; comparing them on
   *the same* replications means the noise cancels in the per-seed difference. The same
   conclusion typically needs several times fewer runs.
2. **Replication count is derived, not chosen.** Rather than picking a round number like
   100, the count comes from a target **minimum detectable effect**: decide the smallest
   difference worth claiming (a defensible default is 5% relative delay), estimate the
   per-seed standard deviation from a small pilot batch, and compute the replications needed
   to detect it. This is reported alongside results, so a null finding can be read as
   "no effect larger than X" rather than as an absence of evidence.

Both are cheap and both are the kind of thing that distinguishes a research result from a
plausible-looking chart.

**Revisit trigger.** RL training makes exact arrival reproduction across arms impractical —
in which case the deviation is documented per-experiment, not silently adopted.

---

<a id="d-018"></a>
### D-018 — Warm-up, measurement window, and unfinished trips

**Status:** SETTLED — ratified by owner 2026-08-13 · **Source:** `01_CRITICAL_REVIEW.md` G-4, G-6

**Decision.** Every run has three explicit phases, all recorded in the manifest:

| Phase | Purpose | Metrics |
| --- | --- | --- |
| **Warm-up** | Fill the network from empty to a representative state | Discarded entirely |
| **Measurement** | The window results are computed over | Collected |
| **Cool-down** | Let in-flight vehicles complete | Not collected; exists so trips finish |

Rules:

- Warm-up duration is a config parameter, justified per scenario (a sensible default is
  several times the free-flow traversal time of the longest route), and **must be validated**
  by showing that the metric of interest has stabilised.
- **Unfinished trips are the dangerous case.** Vehicles still in-network at the end of
  measurement have no completed travel time. Dropping them silently favours controllers that
  let vehicles queue, because their slowest vehicles never finish and never count. The
  policy: run a cool-down so most trips complete; count and report vehicles that still did
  not; and report a trip-completion rate alongside every travel-time metric so the reader
  can see whether the sample is biased.
- Demand may not change during the measurement window unless the experiment's subject *is*
  non-stationary demand, in which case the window covers whole cycles of the pattern.

**Rationale.** The first minutes of a run start from an empty network and are biased low,
and the bias varies with demand — which systematically distorts comparison across demand
levels. The unfinished-trip issue is a well-known way to accidentally prove a bad controller
is good.

**Revisit trigger.** None. Permanent methodology.

---

<a id="d-019"></a>
### D-019 — The deliverable is learning plus a portfolio artifact

**Status:** SETTLED (owner decision) · **Source:** `02_PROJECT_CHARTER.md` §2

**Decision.** Primary purpose is learning and a portfolio artifact, on an open-ended
timeline, with a possible later pivot to a prototype that is explicitly not a current design
constraint. Research posture is a broad platform without a single driving question.

**Principal consequences** (worked out in the charter): visualization is promoted to a
primary deliverable; methodological rigor stays at full strength; reimplementing existing
tools is legitimate but only after reading them; negative results are deliverables;
calibration against real Bogotá data is out of scope.

**Principal risk accepted:** open-ended timeline plus no single question removes every
natural forcing function. Mitigated by the vertical-slice rule
(`02_PROJECT_CHARTER.md` §6) and the slice health check (`03_ROADMAP.md`).

**Revisit trigger.** The owner decides to pursue a prototype, or wants to sharpen to a
single research question. The standing recommendation on file is Q5 × Q4 — how motorcycle
composition changes what a controller needs to observe.

---

## 3. Decisions closed for M1

These four were the founding slice's blockers. All are now settled.

<a id="d-020"></a>
### D-020 — Action space, constraint layer, and periodic decision interval

**Status:** SETTLED — ratified by owner 2026-08-13 · **Source:** `01_CRITICAL_REVIEW.md` G-7

**Why it matters more than it looks.** The action space determines what every controller can
express, what RL can learn, what MPC optimizes over, and whether results are comparable to
published work. Two controllers with different action spaces cannot be compared cleanly,
because part of the measured difference is the freedom they were given rather than the
intelligence they applied.

#### Decision 1 — Phase selection with a constraint layer

A **single canonical action interface built on phase selection**: at each decision point a
controller names the phase it wants next. Every controller acts through it, **including
fixed-time**, which simply names the phase its schedule dictates. This is what makes a
schedule and a learned policy genuinely comparable — they differ in how they choose, not in
what they are allowed to choose.

Considered and rejected as the canonical form: binary keep/switch (too constrained; cannot
skip an empty phase, which is half the value of adaptive control), phase duration (awkward
for RL), and cycle/split/offset (too slow-acting for M1, though it returns as the natural
formulation for coordination at M5b).

The **constraint layer** is the more important half. It sits between every controller and
the backend, and enforces:

- minimum green and maximum green per phase,
- yellow and all-red transition timing,
- phase-transition legality (per `D-023`'s conflict matrix),
- eventually, pedestrian minimum-green floors (`D-029`).

A controller *requests*; the constraint layer *grants, defers, or overrides*, and records
which. That record matters: "the RL policy requested an illegal switch 400 times" is
diagnostic information, not something to swallow silently.

#### Decision 2 — Decision interval is periodic, not per-step

**Owner instruction:** the controller decision interval is periodic; recomputing every
simulation step is too expensive.

Adopted, with a **two-tier structure** that is what makes it safe:

| Tier | Runs | Cost | Responsibility |
| --- | --- | --- | --- |
| **Constraint layer** | Every simulation step | Negligible — it is timers and table lookups | Countdown of min/max green, execution of yellow and all-red, safety enforcement |
| **Policy** | Every Δt (the decision interval) | Whatever the controller costs | Choosing the next phase |

Separating them means the expensive part is throttled while safety and timing stay exact.
If the policy ran only every 5 s *and* the constraint layer with it, a yellow interval could
overrun by up to 5 s, which is a safety-model defect, not an approximation.

**Δt is a per-controller configuration value with a global default**, because the right
value genuinely differs by controller family:

| Controller | Suggested Δt | Reason |
| --- | --- | --- |
| Fixed-time (Webster) | Irrelevant — schedule-driven | Acts at phase boundaries only |
| Actuated | **1 s** | Gap-out detection is the mechanism; a coarse interval blunts it into a different algorithm |
| Max-Pressure | 5 s | Pressure changes slowly; frequent switching is counterproductive |
| MPC | 5–10 s | Each decision solves an optimization; this is where cost binds |
| RL | 5 s | Also affects sample efficiency and episode length |

**Constraints on Δt:** it must be an integer multiple of the SUMO step length, and it must
be at least as fine as the minimum green, or the controller cannot express the shortest
legal phase.

#### The comparability caveat, and how it is handled

Controllers running at different Δt are **not perfectly comparable** — part of any measured
difference is decision frequency rather than decision quality. This is unavoidable (forcing
actuated to 5 s would misrepresent actuated), so it is managed rather than hidden:

1. Δt is recorded in the run manifest and **reported next to every result**.
2. M1 includes a **Δt sensitivity check**: run Max-Pressure at 1 s, 5 s, and 10 s. If
   performance is flat across that range, the caveat is empirically small and can be noted
   and set aside. If it is steep, Δt becomes a controlled experimental variable and all
   controllers are additionally compared at a common Δt.

#### Addition: legal-action mask (adopted 2026-08-18 after T0.1)

The constraint layer additionally exposes **which phases could be granted now**:

```python
def allowed_phases(self, intersection_id: IntersectionId) -> frozenset[PhaseId]
```

Adopted from PyTSC's `get_allowable_phase_switches`, which T0.1 identified as the one genuinely
good idea in the surveyed prior art that nobody else has. It lets a controller **avoid making
an illegal request** rather than being refused after the fact.

Three reasons to add it now rather than at M7, despite `02_PROJECT_CHARTER.md` §6's rule
against building for absent consumers:

1. It is not a new abstraction or seam — it generalises `actionable()`, which the interface
   already has, from "can I act" to "which actions are legal".
2. Action masking is standard practice in RL over discrete constrained action spaces and
   substantially improves learning. Adding it at M7 would change the `Controller` protocol
   after five milestones of controllers exist.
3. **It leaks nothing.** A controller already knows its own signal state exactly
   (`05_DOMAIN_MODEL.md` §4.2), and the mask is derivable from that plus the static conflict
   matrix. No true state is involved.

The per-outcome counters stay regardless: a masked controller that still requests an illegal
phase is a bug worth seeing.

#### Known gap, surfaced while writing the T1.6 contract

**Undecided: what happens when max green expires while a phase transition is in progress.**
Does the override wait for the yellow/all-red sequence to complete, or does it preempt it?
Preempting would violate invariant 3 of the T1.6 contract (every change is followed by a full
yellow and all-red) and is almost certainly unsafe; waiting means max green can be exceeded by
up to `yellow_s + all_red_s`, which must then be documented rather than treated as a bug.

**Closed 2026-08-18 by T1.7 — and the gap's premise did not hold.**

`max_green_s` bounds the **green interval** (§8 invariant 2: "green never longer than
`max_green_s`"). A green interval is by definition not running during a transition, so max-green
expiry **cannot occur mid-transition** and the question has no reachable case. T1.7 implemented
the waiting branch anyway and instrumented it — `ConstraintCounters.overrides_deferred_by_transition`
increments if it ever fires, stays 0 under an adversarial 200 s run with `max_green_s = 4 s`
against a 5 s clearance, and the property test asserts the same across every generated timing.
Counting beats asserting unreachability.

This rests on one reading, named here so it can be overruled: invariants 1 and 2 measure the
**green interval only**. The alternative — measuring from when the phase became active,
transition included — makes the gap reachable but makes invariants 1 and 2 **jointly
unsatisfiable** whenever `max_green_s < yellow_s + all_red_s`, since the green would need
negative length. That is why it is a finding rather than a choice.

**The overshoot this entry originally described was the wrong quantity.** "Up to
`yellow_s + all_red_s`" is a property of **service**, not of green: a phase forced off at max
green still holds the intersection through its clearance, so the *next* green starts
`max_green_s + yellow_s + all_red_s` later. That belongs in the results document as a property
of the system. The overshoot `max_green_s` itself suffers is much smaller — up to one step
length, when `max_green_s` does not fall on the step grid — and is recorded as
`max_green_overshoot_s` (cumulative) and `max_green_worst_overshoot_s` (worst single event),
because a total alone cannot distinguish one bad event from many negligible ones.

**Revisit trigger.** The Δt sensitivity check shows steep dependence; or a controller family
at M6/M7 needs an action space this interface cannot express.

---

<a id="d-022"></a>
### D-022 — Demand model: sources, propagation, mid-link attrition, sinks

**Status:** SETTLED — owner-specified model, formalised by the architect 2026-08-13;
arrivals, turn ratios and routing explicitly confirmed by owner 2026-08-18 with no changes
**Source:** `01_CRITICAL_REVIEW.md` G-11; owner's model, 2026-08-13

**Why it matters.** Demand design determines what an experiment can show. Whether demand is
stationary or time-varying decides which controllers can win: a fixed-time plan tuned to the
average is severely penalised by non-stationarity and barely penalised by stationarity. A
project that only tests stationary demand systematically overrates fixed-time.

Routing has a subtler consequence: if vehicles re-route around congestion, signal control and
route choice interact, and a change in network performance can no longer be attributed to the
controller.

#### The model

The owner specified an **open-boundary link–node flow model**. Vehicles are not conserved
inside the study area: they enter from outside it, propagate through it, and leave it —
sometimes at a boundary, sometimes in the middle of a link. Four mechanisms:

| # | Mechanism | Meaning | Owner's phrasing |
| --- | --- | --- | --- |
| **1** | **Initial state** | The run begins from a populated network, not an empty one | *"Empezamos el modelo con una 'imagen' del tráfico actual"* |
| **2** | **Exogenous sources** | Poisson arrivals from points outside the modelled network — boundaries, and also side streets, driveways and parking exits that we choose not to model | *"pueden entrar carros con distribución de Poisson de puntos no modelados"* |
| **3** | **Endogenous propagation** | Traffic arriving at an intersection is mostly traffic that left the previous one, following a route toward a destination | *"a semáforos o intersecciones llegan los carros que antes estaban en la otra intersección"* |
| **4** | **Attrition and sinks** | Vehicles leave either at an explicit exit point, or **mid-link**, having reached a destination between two signals | *"tasa de abandono… llegó a su destino entre semáforos o cámaras"* + *"puntos de salida de tráfico"* |

This is a good model and it is more realistic than the one originally recommended. Mechanism
4 in particular is something most traffic-signal-control studies omit: they conserve vehicles
between boundaries, which overstates downstream demand on every arterial. Local destinations
are a real and large fraction of urban traffic.

#### Formalisation

**Sources.** Two kinds, both Poisson with configurable rate, both seeded from the demand
stream (`D-017`):

- **Boundary sources** on edges entering the study area.
- **Mid-link sources** at a specified position on an interior edge, representing unmodelled
  side streets and driveways.

Rates are expressed as a **fraction of the receiving approach's saturation flow**, not as
absolute vehicles per hour, so that "demand level 0.8" means the same degree of loading
across different geometries and is comparable across experiments.

**Propagation and routing.** Routes are assigned by **turning ratios**, not by an OD matrix:
at each junction, a vehicle's next edge is drawn from a configured probability distribution
over the permitted movements. This matches mechanism 3 directly and is far simpler to
configure for synthetic networks than an OD matrix would be.

Routes are resolved **at insertion** and are then **fixed**. No re-routing, no congestion
response. This is a deliberate limitation (see the caveat below), not an oversight.

**Attrition.** Each interior edge carries an **attrition rate** — the fraction of its
through-flow whose destination is on that edge rather than downstream. Applied at route
construction: a vehicle drawn as "locally destined" gets a route terminating at a sampled
position on that edge, and is removed on arrival.

Attrition is **per-edge, not global.** An arterial link between two major intersections has
low attrition; a commercial street lined with parking has high attrition. A single global
rate would misrepresent both.

**Sinks.** Boundary edges leaving the study area are explicit exit points. A vehicle
reaching one has completed its trip.

#### Mapping to SUMO

Each mechanism maps to an existing SUMO facility, so none of this requires custom vehicle
handling:

| Mechanism | SUMO facility |
| --- | --- |
| Poisson arrivals | `<flow>` with exponentially distributed headways (`period="exp(rate)"`) |
| Mid-link sources | `<flow>` with `departPos` set to an interior position |
| Turning-ratio routing | `jtrrouter`, which builds routes from turn probabilities and supports declared sink edges — this is precisely the tool for this model |
| Mid-link attrition | `arrivalPos` on the vehicle's final edge |
| Sinks | Boundary edges declared as sinks to `jtrrouter` |
| Initial state | `--save-state` / `--load-state` (see `D-032`) |

**Verified 2026-08-18 (T0.5, second pass).** Turn ratios are honoured — configured
0.60 / 0.25 / 0.15 from one approach realised as 0.606 / 0.252 / 0.142 over 4000 generated
routes — and declared sink edges terminate every route (0 of 4000 ended off-sink).

**Correction binding on T1.5:** the `<fromEdge>` / `<toEdge>` turn-file format is **deprecated**
in SUMO 1.27.1, which emits a warning pointing at `<edgeRelation from=... to=... probability=.../>`.
Tutorials and older examples still show the legacy form.

**Still unverified:** `--max-edges-factor`. Every route on a single intersection is two edges, so
the memoryless-routing artifact described below cannot appear until a multi-junction network
exists at M5.

**Original spike instruction, now discharged:** that `jtrrouter`'s sink handling and turn-ratio semantics behave
as assumed, and that `arrivalPos` removal is counted the way we expect in SUMO's trip output.

#### Three consequences that must be handled, not discovered later

**1. Attrition changes what "throughput" means, and metrics must not conflate three
different exits.** With this model a vehicle can leave the simulation in three ways, and
they mean opposite things:

| Exit | Meaning | Counts as |
| --- | --- | --- |
| Reached a boundary sink | Completed its trip through the network | **Served demand** |
| Reached a mid-link destination | Completed its trip; arrived locally | **Served demand** |
| Still in-network at end of measurement | Did not complete | **Unserved** — see `D-018` |

Collapsing the first two with the third, in either direction, produces a false throughput
figure. The metrics layer counts all three separately and always reports them, per `D-018`'s
trip-completion-rate requirement.

**2. Turning-ratio routing is memoryless, and that has an artifact.** Because the next
movement is drawn independently at each junction, a vehicle can in principle circulate —
turn right four times and return where it started. On a 3×3 grid with realistic turn ratios
this is rare but nonzero. `jtrrouter` bounds it with a maximum-edges limit. The count of
route generations that hit the limit is logged; if it is material, turn ratios are adjusted
or a no-immediate-U-turn rule is added. This is exactly the kind of artifact that quietly
inflates travel-time metrics if nobody looks for it.

**3. Attrition creates a genuinely interesting problem for state estimation at M3.** The
owner's own phrasing — *"llegó a su destino entre semáforos o cámaras"* — names it: a vehicle
that leaves between two cameras is indistinguishable, from the sensors' point of view, from a
vehicle the downstream camera simply failed to detect. A counting-based estimator (`D-021`)
therefore cannot tell attrition from missed detection, and will drift.

That is not a defect in the demand model. It is a realistic, structural source of estimation
error that this model produces for free, and it makes M3's central question sharper: an
estimator must either be given the attrition rate as prior knowledge, or infer it, or
accumulate bias. Worth carrying forward explicitly into `D-021`.

#### Scope by milestone

| Milestone | Demand |
| --- | --- |
| **M1** | Stationary Poisson sources, fixed turn ratios, per-edge attrition, boundary sinks. Cars only — but the type-mix parameter exists in the config from day one so M4 needs no schema change. |
| **M4** | Type mix activated (cars + motorcycles); attrition rates may differ by type. |
| **M5** | Multiple sources and sinks; attrition becomes load-bearing as corridors lengthen. |
| **M8** | Time-varying profiles and OD matrices. |

**Standing caveat.** M1's conclusions hold under **stationary demand with fixed routes**, and
are provisional by construction. Non-stationary demand (M8) is where fixed-time plans are
properly penalised, so several M1 conclusions may invert there. The results document must say
so rather than leaving the reader to discover it.

**Revisit trigger.** Route choice becomes an experimental subject (deferred per
`02_PROJECT_CHARTER.md` §7.3); or M8 requires OD matrices, at which point turning ratios and
OD coexist as alternative demand backends behind the same config interface.

---

<a id="d-023"></a>
### D-023 — Conflict model and phase schema

**Status:** SETTLED — ratified by owner 2026-08-13 · **Source:** `01_CRITICAL_REVIEW.md` G-13

**Why it matters.** `00_RESEARCH_SPECIFICATION.md` §10 defines a phase as a compatible set of
movements, but **compatibility is the primitive** — phases are derived from it. Without an
explicit conflict relation, the system cannot validate that a requested phase is safe, cannot
enumerate the legal phase set for an arbitrary geometry, and cannot honour §8.1's requirement
that geometry be data rather than hard-coded assumption.

**Decision.**

1. **The conflict matrix is the primitive.** For each `Junction` (per `D-010` it lives on the
   topological type, because conflicts are a fact of geometry whether or not a signal is
   present), a **three-valued matrix** over movement pairs:

   | Value | Meaning |
   | --- | --- |
   | `compatible` | Both movements may run simultaneously with no interaction |
   | `conflicting` | Both movements may never run simultaneously |
   | `permitted` | Both may run simultaneously, but one yields to the other (e.g. a permitted left across opposing through traffic) |

   Two values would have been simpler, but a permitted left is legal *and* conflicting, and
   collapsing that distinction either forbids a movement real intersections allow or permits
   one they do not. It also changes the capacity model, since a permitted movement discharges
   at a reduced saturation flow.

   The matrix is derived from geometry where possible — SUMO computes junction conflicts and
   can seed it — and is overridable per scenario.

2. **Phases are authored, then validated.** Phases are declared per scenario rather than
   enumerated automatically from the matrix, because automatic enumeration produces a large
   set of legal-but-nonsensical phases that no engineer would deploy and that would pollute
   every controller's action space. **At load time, every declared phase is checked against
   the conflict matrix and any phase containing a `conflicting` pair is rejected** with an
   error naming the pair. Authoring gives control; validation prevents mistakes.

3. **Transitions are attributes of a phase change, not phases.** Yellow and all-red durations
   are properties of the transition from phase A to phase B, executed by the constraint layer
   (`D-020`). They are deliberately **not** first-class phases: modelling them as phases would
   put them in the action space, and no controller should ever be able to *choose* "yellow" —
   it is a consequence of switching, not a decision.

4. **Protected-only turns at M1.** The `permitted` value exists in the schema from the start
   so that no migration is needed, but M1 scenarios use protected turns only. Permitted turns
   are introduced when a scenario needs them, most likely at M5.

**Seeding mechanism, verified 2026-08-18 (T0.2, corrected).** The matrix is seeded from
**static net-file data**, not from runtime link state. Each junction carries
`<request index=N response=... foes=...>` rows: `foes` is a bitstring of which link indices
physically conflict with this one, and `response` is which of those foes this link must yield
to. That is exactly the three-valued relation:

| `foes[i]` | `response[i]` | Relation |
| --- | --- | --- |
| 0 | — | `COMPATIBLE` |
| 1 | 1 | `PERMITTED` — this link yields to *i* |
| 1 | 0 | `CONFLICTING` — may not be green together |

Protected versus permissive is carried separately, by the **case** of the phase state character:
`G` is protected green, `g` is permissive green that yields (e.g. `GGGgrrrrGGGgrrrr`).

T0.2's first pass proposed seeding from `traci.lane.getLinks()` metadata — `is opened`,
`has approaching foe` — which are **runtime** values dependent on current signal state and
current traffic. Seeding a static matrix from those is a category error. The claim was also
asserted without a test, on a scenario deliberately containing no permitted turns, which is the
one case the three-valued distinction exists for.

**Binding on T1.3:** read `<request>` `foes`/`response` from the built network plus the `G`/`g`
case from the TLS program. Do **not** use `getLinks()` runtime state. Validate against a network
that contains a permissive turn — `spikes/M0_verify/` builds one.

**Seeding rule corrected 2026-10-07 — supersedes the table above.** The table reads each
`<request>` row on its own and maps `foes=1, response=0` to `CONFLICTING`. Measured on the M0
probe, the reference net and RESCO's `cologne1`: **every** foe pair has at least one side that
yields (response bits `01`, `10` or `11`, never `00`). Read per row, every foe pair is therefore
`CONFLICTING` in one direction and `PERMITTED` can never survive the both-directions check of
invariant 7; read per pair, two crossing through movements look exactly like a permissive left
against opposing through. `response` encodes **priority** — who yields if both are green — not
whether two links may be green together. That is a signal-design choice, which SUMO keeps in the
program (the `g` case), not in `<request>`.

| `foes`, either direction | Scenario override | Entry `[a, b]` | Entry `[b, a]` |
| --- | --- | --- | --- |
| no | — | `COMPATIBLE` | `COMPATIBLE` |
| yes | none | `CONFLICTING` | `CONFLICTING` |
| yes | declared permitted | `PERMITTED` if `a` yields to `b` per `response`, else `COMPATIBLE` | the mirror |

At M1 no scenario declares a permitted pair (point 4), so the matrix is binary in practice, as
intended. Three reading traps, each verified: bit strings run **right to left** (the last
character is link 0 — only that reading makes `foes` symmetric); a junction's `<request index>`
and a traffic light's `linkIndex` are **different numberings** — they coincide on every net
checked (the probe, the reference net, `cologne1`), but nothing guarantees it (a custom
`linkIndex`, one light over joined junctions), so derive each from its own source and map
through the connection; and netconvert **does not honour** `linkIndex` written in a
`.con.xml`, which left the M0 reference program greening crossing movements together for seven
weeks (`research/M0_reference_scenario.md`, correction). Movement-level entries aggregate their
links' entries, most restrictive wins.

**Revisit trigger.** A junction geometry appears that the three-valued matrix cannot express;
or automatic phase enumeration becomes necessary for large imported networks at M8.

---

<a id="d-025"></a>
### D-025 — Queue definition *(supersedes D-007)*

**Status:** SETTLED — ratified by owner 2026-08-13 · **Source:** `01_CRITICAL_REVIEW.md` G-5

**Why it matters.** Max-Pressure is defined in terms of queue counts, so the queue definition
is not merely a metric — it is an *input to a controller*. Change the definition and you have
changed the controller. It is also a headline metric, and it is what a sensor must estimate.

`00_RESEARCH_SPECIFICATION.md` §19 correctly notes that instantaneous zero speed should not
imply queued. That instinct now needs to become a testable rule.

**Decision.** A vehicle is **queued** on a lane if it is *halting* — speed below
**0.1 m/s** — and has been continuously halting for at least **1 second**.

| Aspect | Decision | Reason |
| --- | --- | --- |
| **Speed threshold** | 0.1 m/s | Matches SUMO's own halting definition, so our counters and SUMO's native ones agree and can cross-check each other |
| **Minimum duration** | 1 s continuous | Excludes vehicles that are merely decelerating through zero, which is the failure `00_RESEARCH_SPECIFICATION.md` §19 correctly warned about |
| **Primary unit** | **Count** (vehicles) | Max-Pressure is defined over counts; counts are also what a camera can most reliably estimate, which keeps the controller's input and the sensor's output in the same unit |
| **Secondary unit** | Length (metres), reported from M4 | Count and length diverge sharply under mixed vehicle types — five motorcycles occupy far less road than five cars — so this becomes a *motorcycle-relevant* metric, not bookkeeping |
| **Distance to stop line** | **No condition at M1** | Deferred to M5, where spillback makes "which intersection does this queue belong to" a real question rather than a hypothetical one |
| **Controller queue vs. metric queue** | **Same definition** | They may diverge later, but only deliberately and documented. Identical by default means a controller optimizing queues is optimizing the thing we report |

**Divergence from all surveyed prior art, recorded deliberately (T0.1, 2026-08-18).**
No project surveyed applies a duration condition: RESCO sets a `queued` flag on first stop and
**never resets it** while the vehicle is within 200 m, LibSignal's `queue_length` is literally
the lane vehicle count, and PyTSC uses SUMO's speed-threshold-only halting count. Our 1 s
condition is therefore an intentional departure, and its consequence is larger than reporting:
because Max-Pressure is defined over queue counts, **a different queue definition is a
different controller.** RESCO's Max-Pressure and ours are not the same algorithm. Any
comparison against their published numbers must say so.

**Spike result, 2026-08-18 (T0.5, re-verified).** SUMO's `getLastStepHaltingNumber` applies a
0.1 m/s speed threshold with **no duration condition**, so `D-025`'s 1 s condition must be
computed by us — confirmed, decision unchanged.

**But lane-area jam length is a different measure, not a richer view of the same one.** Measured
over 600 s with the signal running, `getJamLengthVehicle` disagreed with the halting counter on
230 of 600 steps, always higher, because SUMO's jam criterion admits slow-moving vehicles that a
strict 0.1 m/s threshold excludes. They coincide only in a saturated queue. **`getJamLengthMeters`
is therefore not a drop-in source for the secondary metres metric**, and which source M4 adopts is
left open rather than assumed.

**Spike required before implementation.** Confirm what SUMO's native halting counters
(`getLastStepHaltingNumber` and the equivalent lane-area detector output) actually measure —
specifically whether they apply the duration condition or only the speed threshold — before
deciding to adopt them or compute our own. Folded into M0.

**Revisit trigger.** M5 spillback requires stop-line attribution; or M4 shows that
count-based queues misrepresent motorcycle-heavy approaches badly enough to change the
primary unit.

---

## 4. Open and deferred decisions, later milestones

<a id="d-021"></a>
### D-021 — State estimation approach · **OPEN · blocks M3**

Undecided: whether the first estimator is per-lane counting with decay, a recursive filter
over queue dynamics (Kalman or particle), or a learned model.

**Recommendation:** counting with decay at M3 (axis B, Step 1), deliberately chosen and
documented as minimal rather than arrived at by default. Filtering at Step 2 only if M3
shows that estimation error, rather than observation error, is what limits control.

**Worth flagging:** this layer is where the platform's most distinctive work could live. Most
of the literature either assumes perfect observation or fixes a detector model; explicitly
separating estimation and measuring how control degrades through it is uncommon.

**Carried forward from `D-022`.** The owner's demand model creates a structural estimation
problem for free, and it should shape this decision. Because vehicles can leave mid-link
(attrition), a counting estimator sees a vehicle enter a link upstream and never arrive
downstream — and **cannot distinguish "it reached a local destination" from "the downstream
camera missed it."** Both look identical in the observation stream. A naive counting
estimator therefore accumulates bias at a rate set by the attrition rate.

Three responses are possible, and choosing among them *is* this decision: give the estimator
the attrition rate as prior knowledge, have it infer the rate online, or accept the bias and
measure it. The third is a legitimate M3 baseline. This is a realistic problem that real
camera-based systems have, and it is more interesting than the noise model.

---

<a id="d-024"></a>
### D-024 — Objective function · **OPEN · blocks M6**

> **Located here, not in §3**, because it blocks M6 (MPC) rather than M1. Nothing before M6
> needs it: fixed-time follows a schedule, actuated follows a gap rule, and Max-Pressure has
> its objective built into its definition. MPC is the first controller that must be *told*
> what to optimize.

**What the issue actually is.** `00_RESEARCH_SPECIFICATION.md` §27 proposes

```
J = w₁·Delay + w₂·Queue + w₃·TravelTime + w₄·Stops + w₅·ThroughputLoss + w₆·Fairness
```

and correctly calls objective design a research question. The problem is that this expression
looks like a specification and is actually six unanswered questions wearing a formula. Three
of them are substantive:

**1. The weights are the policy, and there is no neutral choice.** Setting `w₁=w₂=1` is not
"unbiased" — it is a specific and arbitrary trade-off between delay and queue length, and it
determines the controller's behaviour more than the optimization algorithm does. Any weight
vector encodes a value judgement about whose time matters. It has to be justified by an
argument (a stated priority, a normalisation to comparable units, or a sensitivity analysis
showing the conclusions are robust across a range), never by picking round numbers.

**2. Several terms are not independent, so the sum double-counts.** Delay, travel time, and
throughput loss are three views of largely the same physical quantity. Adding them with
separate weights means an implicit and unexamined re-weighting of that quantity. Either the
terms are made orthogonal, or the redundancy is acknowledged and the redundant terms dropped.

**3. The optimization objective should probably not equal the evaluation metric.** If MPC
minimises exactly the number we report, it will exploit whatever that metric fails to
capture — the standard result of optimizing a proxy. Keeping them distinct is what allows
the reported figure to remain an honest measurement rather than the controller's own
scoreboard.

**Also undecided:** whether fairness across approaches is included at all (it conflicts with
aggregate efficiency — the efficient policy often starves a minor approach), and whether the
objective is defined per-intersection or network-wide, which is really a coordination
question and interacts with `D-028`.

**Must be closed before M6, by argument rather than by choosing numbers.** Expect this to be
its own small research exercise, most likely including a sensitivity sweep over weights.

---

<a id="d-026"></a>
### D-026 — Sublane model as default · **DEFERRED to M4**

SUMO's sublane model with SL2015 enables side-by-side occupancy and therefore motorcycle
filtering and lane splitting, which is the substantive content of the project's motorcycle
interest. The recommended lateral resolution is at most the width of the narrowest vehicle,
so motorcycles force a fine resolution, which multiplies per-step lateral computation.

**Decided at M4 by measurement:** wall-clock cost, and whether control conclusions change.
Three outcomes are all acceptable — default on, optional experimental arm, or dropped — and
"it does not change the conclusions, here is the evidence" is a legitimate finding under
`00_RESEARCH_SPECIFICATION.md` §32.

---

<a id="d-027"></a>
### D-027 — RL formulation · **DEFERRED to M7**

State representation, action space (constrained by `D-020`), reward (related to but not
necessarily identical to `D-024`), algorithm family, centralized vs. decentralized, training
protocol, and the train/validation/test scenario split.

**Two constraints fixed in advance:** RL is compared against Max-Pressure, not fixed-time
(`D-013`); and per Principle 10, an RL controller that wins without an interpretable account
of why and where it fails is not accepted.

---

<a id="d-028"></a>
### D-028 — Multi-intersection controller scope · **DEFERRED to M5a**

Whether a controller instance owns one intersection (with coordination as communication
between instances) or one controller owns a set. This shapes the RL formulation, so it
should be settled before M7 even though it first arises at M5a.

---

<a id="d-029"></a>
### D-029 — Pedestrian modelling · **DEFERRED, no trigger date**

Deferred entirely per `01_CRITICAL_REVIEW.md` O-4. Pedestrian phases impose hard floors on
green duration, and that consequence is captured at near-zero cost by minimum-green
constraints in the `D-020` constraint layer. Recorded as a stated limitation.

**Revisit trigger:** an experiment requires pedestrian delay as an objective term.

---

<a id="d-030"></a>
### D-030 — Trace format · **OPEN · blocks M2**

Must specify: what is recorded per step, at what rate, in what container (JSONL, Parquet,
or a binary format), how large a typical run's trace is, and how it is versioned.

**Fixed requirement regardless of format:** channels for observations, estimated state, and
controller decisions are specified at M2 even though they are only populated at M3. Adding
them later would invalidate every earlier trace, and the research overlays are the entire
justification for building a custom renderer (`01_CRITICAL_REVIEW.md` O-5).

---

## 5. Decisions arising from ratification

<a id="d-031"></a>
### D-031 — Efficiency and reuse posture

**Status:** SETTLED — reframed by the architect, clarified and ratified by owner 2026-08-14
**Source:** Owner instruction attached to `D-014`, 2026-08-13; owner clarification 2026-08-14

**The instruction.** *"The code must be really flexible and must reuse as much code as
possible, let's also emphasize efficiency. This is a complex project that needs to prioritize
efficiency and scalability."*

**The owner's clarification (2026-08-14).** *"When I say prioritize efficiency I mean code
efficiency — looking for patterns that can make the code faster, and understanding which
blocks of code may be making it slow."*

This narrows the instruction substantially and removes most of the conflict identified below.
The second half of the clarification — *understanding which blocks are making it slow* — is
**profiling**, which is precisely what Principle 8 asks for rather than what it forbids.
Principle 8 does not prohibit caring about speed; it prohibits optimizing before knowing
where the time goes. The clarified instruction is therefore adopted, and turned into a
standing measured practice in the third subsection below rather than left as an attitude.

**Why it cannot be adopted as written.** Taken literally, each of the three clauses conflicts
with something already ratified:

| Clause | Conflicts with | How it fails in practice |
| --- | --- | --- |
| *"really flexible"* | `02_PROJECT_CHARTER.md` §6 — no speculative abstraction | Flexibility is bought with indirection. Indirection added before a second use case exists is pure cost, and it is the specific mechanism by which a research codebase becomes a framework that is harder to change than the code it replaced. |
| *"reuse as much code as possible"* | Same | Maximising reuse produces generalised base classes with one subclass, parameters nobody varies, and coupling between things that only *looked* similar. Reuse is a consequence of good decomposition, not a target to maximise. |
| *"prioritize efficiency"* | `00_RESEARCH_SPECIFICATION.md` Principle 8 — no optimization before bottlenecks are identified | Optimizing before measuring reliably targets the wrong thing and makes the code harder to change while doing it. **Largely resolved by the owner's clarification** — see above; what was meant was profiling, not speculative optimization. |

**But the underlying concern is real and correct.** This project will run large sweeps —
controllers × demand levels × seeds × network sizes — and later RL training. Throughput
genuinely matters. The instruction is right that it cannot be an afterthought.

**The resolution** is to split efficiency into three kinds, treated differently:

#### Architectural efficiency — decide now, because retrofitting is expensive

| Decision | Lever | Status |
| --- | --- | --- |
| **Transport abstraction for LibSUMO** | ~10× on the simulation call path | `D-002`, settled |
| **Process-level parallelism as the runner's native shape** | Near-linear in cores. The single largest lever. | New, below |
| **One batched projection per step; no per-object access exposed to other layers** | ~10× on TraCI. Neutral-to-negative on LibSUMO — see the amendment. | Amended 2026-08-18 |
| **Periodic decision interval** | Proportional to Δt on controller cost | `D-020`, settled |
| **Columnar results storage; no per-step Python object churn in the hot loop** | Large at sweep scale | `D-004`, settled |
| **Traces opt-in, off by default** | Removes I/O from batch runs entirely | `D-009`, settled |
| **Snapshot initialisation instead of re-running warm-up** | Removes warm-up from every run after the first | `D-032`, below |

Two of these are new and are hereby decided:

**Parallelism.** The experiment runner is designed around *N independent runs*, not around
one run with the ability to loop. Every run is a self-contained unit: its own config, its own
seeds, its own process, its own output file, no shared mutable state. This is the largest
available speedup, it is nearly free if designed in from the start and awkward to retrofit,
and it composes with LibSUMO's constraint that one process holds one simulation rather than
fighting it.

*Illustrative budget arithmetic, to show why this is the lever that matters:* a full M5 sweep
of 5 controllers × 6 demand levels × 50 seeds × 6 network sizes is ~9,000 runs. At a
plausible ~36 s each, that is ~90 hours serially, ~11 hours across 8 cores, ~2 hours with
LibSUMO on top. No amount of micro-optimization in the metrics code reaches that.

**Query batching — amended 2026-08-18 after T0.3, which measured the opposite of what this
rule assumed for the transport we will actually use at scale.**

The original rule mandated variable subscriptions as the adapter's only state-reading
mechanism, reasoning that "the dominant cost in TraCI is round-trips". That reasoning is sound
and the measurement confirms it — **for TraCI**. It does not transfer:

| Transport | Subscriptions vs per-object polling | Measured |
| --- | --- | --- |
| TraCI | **~10× faster** | 7.30 s vs 71.05 s per simulated hour |
| LibSUMO | **~1.7× slower** | 2.57 s vs 1.49 s per simulated hour |

Reproduced independently by the architect; both passes agree on the ordering. The mechanism is
obvious in hindsight: LibSUMO is an in-process binding with no socket, so subscription
bookkeeping is pure overhead. And LibSUMO is the transport intended for **every heavy
workload** — the M5 sweeps and M7 training — so the rule as written would have imposed a ~70%
tax exactly where throughput matters most.

**The amended rule separates the invariant from the mechanism.**

*Architectural, binding, unchanged in force:* the adapter performs **one batched projection per
simulation step** and exposes **no per-object query method** to any other layer. This is what
keeps per-object access from leaking into sensors, metrics and controllers, where it would be
both slow and impossible to remove later. It remains a review defect to violate it
(`08_AGENT_HANDOFF_PROTOCOL.md` §6 item 9).

*Mechanism, transport-specific, chosen by measurement:* **how** the adapter batches is an
implementation detail behind the `D-002` seam. Subscriptions under TraCI; direct batched
getters under LibSUMO. T1.4 implements both and its acceptance criterion — byte-identical
`TrueState` across transports — already guarantees they cannot diverge in behaviour.

*Unaffected:* context subscriptions around a junction remain the right tool for M3's
radius-limited sensor queries. That is a different question from per-step whole-state
projection, and T0.3 measured only the latter.

**Note on how this was caught.** T0.3 found the contradiction and resolved it in its own
write-up rather than escalating. The finding survived only because the write-up was audited.
`08_AGENT_HANDOFF_PROTOCOL.md` §8 exists for exactly this case.

#### Code-level efficiency — a standing measured practice

This is what the owner's clarification asked for, and it is adopted as **infrastructure
rather than attitude.** The distinction matters: "write fast code" is advice that every
developer already agrees with and that changes nothing. What changes something is having a
committed tool that says where the time actually went.

Four obligations, starting at M1:

1. **A profiling harness lives in the repository.** A single command runs a standard
   scenario under a profiler and emits a hot-path report. It is committed code that anyone
   can run, not something reconstructed each time someone gets curious.
2. **Every milestone's results document includes a hot-path report** — where the time went,
   and what changed since the previous milestone.
3. **A performance baseline with a regression guard.** M0 establishes wall-clock per
   simulated hour. Each milestone records its own. A milestone that makes it materially
   worse must either explain why (a genuinely more expensive controller is a fine reason) or
   fix it. Silent 3× slowdowns accumulated across five milestones are how a project becomes
   untrainable without anyone deciding it should.
4. **An optimization without a before/after number is not accepted.** This is the rule that
   keeps the practice honest. Unmeasured optimization reliably produces code that is harder
   to read and no faster, and it is indistinguishable from measured optimization in a diff.

**Where the time actually goes in a SUMO-based traffic-signal-control project.** Listed so
the practice starts informed rather than blind — but every one of these is still confirmed by
the profiler before anything is changed:

| Hot path | Typical remedy |
| --- | --- |
| Backend round-trips per step | Variable and context subscriptions — already an architectural constraint above, and usually the dominant cost by a wide margin |
| Per-vehicle Python object allocation inside the step loop | Reuse buffers; slotted dataclasses; avoid constructing a dict per vehicle per step |
| Metric computation done per-vehicle in Python | Accumulate into arrays during the run; compute with NumPy at window close |
| Result or trace I/O inside the step loop | Buffer and flush; traces off by default (`D-009`) |
| Repeated lookups by string ID | Resolve IDs to integer indices once at network load |
| Controller policy cost | Decision-interval throttling (`D-020`) |

**What remains deferred.** Anything the profiler has not named. Principle 8 stands: the
practice above is how a bottleneck gets *identified*, and identification is the precondition
for optimizing, not a substitute for it.

#### On "flexible" and "reuse", reframed

**Flexibility is bought only at named seams.** The charter already names them: the backend
adapter (`D-002`), the observation interface (`D-005`), and the controller/action interface
(`D-020`). These three are where a second implementation is genuinely expected, so
indirection there is insurance. Everywhere else the charter's rule holds — no interface for a
second implementation that does not exist, and a third seam requires a register entry.

**Reuse is measured in concepts, not lines.** The goal is a *small orthogonal core*: exactly
one action interface, one metric-definition module, one config system, one experiment runner,
one trace format. Reuse follows from there being one of each thing rather than from shared
base classes. A codebase where every controller implements the same small interface is
maximally reusable and has no inheritance in it at all.

**Anti-patterns that are review defects in this project:**

- A base class with one subclass.
- A plugin or registry system before there are three implementations to register.
- A configuration option that no config file sets.
- A `Manager`, `Handler`, `Engine`, or `Factory` layer that only forwards calls.
- Caching added before a profile showed the recomputation mattered.
- A generic utility written for a single caller.

**Revisit trigger.** The M0 baseline or an M5 sweep shows wall-clock binding despite the
architectural levers above — at which point profiling identifies the target and Principle 8's
precondition is satisfied.

---

<a id="d-032"></a>
### D-032 — Runs may begin from a saved initial state

**Status:** SETTLED — owner-specified (`D-022` mechanism 1), formalised by the architect
**Source:** Owner's demand model, 2026-08-13

**Decision.** A run begins either from an empty network or from a **saved simulation state
snapshot** — the owner's *"imagen del tráfico actual"*. SUMO supports this natively through
`--save-state` and `--load-state`.

**How this unifies with `D-018`'s warm-up.** They are not competing mechanisms; they are the
production and consumption sides of the same thing:

> Warm-up from empty is **how a snapshot is produced**. A snapshot is **how warm-up is
> avoided** on every subsequent run.

So the workflow is: warm up once per (network, demand level, seed), save the state, and have
every later run load it. This removes warm-up wall-clock from the overwhelming majority of
runs in a sweep — a real efficiency lever, hence its appearance in `D-031`.

**The subtlety that must not be missed: whose controller warms up?** A snapshot produced
while controller X was running is a state that X induced, and starting every arm from it is
not neutral. There are two defensible designs and they answer *different questions*:

| Design | Procedure | Question it answers | Use for |
| --- | --- | --- | --- |
| **Self warm-up** *(default)* | Each arm warms up under its own controller, then measures | "What steady state does each controller induce, and how does it perform there?" | Steady-state comparison — the standard M1–M5 experiment |
| **Neutral snapshot** | All arms load one snapshot generated under Webster fixed-time | "Given this identical starting state, which controller recovers best?" | Transient response, demand shocks, incident recovery |

**Rule.** Whichever design an experiment uses, it is the **same across all arms** of that
experiment and is **recorded in the run manifest**. Mixing them within one comparison
invalidates it. Self warm-up is the default because equilibrium performance is what M1–M5
ask about; neutral snapshots become the natural design for shock experiments.

**Forward link to M6.** MPC needs to initialise its internal prediction model from an
*estimated* current state at every decision point. That is the same facility as this one,
pointed at an estimate rather than a saved file. Building snapshot loading now means M6
inherits it rather than inventing it.

**Caveat.** SUMO state files are sensitive to the SUMO version and to network changes. The
run manifest already records the SUMO version (`D-008`); snapshots additionally record a hash
of the network they were generated on, and loading a snapshot against a different network is
a hard error rather than undefined behaviour.

**Revisit trigger.** None expected.

---

<a id="d-033"></a>
### D-033 — Detections carry lane and stationary time; the estimator receives signal state

**Status:** SETTLED — ratified by owner 2026-10-07 · **Source:** pre-issue review of T1.9

**Problem.** As specified, T1.9 could not meet its own acceptance criterion — an identity
estimator whose queue counts equal the true ones exactly. Three gaps:

1. `Detection` carries a world position but no lane, and the domain model has no lane geometry
   on which to place a position.
2. `Observation` carries no signal state, yet `EstimatedState.signals` must be filled.
3. The sensor runs every Δt, not every step (`06_ARCHITECTURE.md` §6.2). An estimator that
   times halting from its own samples misses up to Δt of it, `D-025`'s ≥ 1 s condition then
   disagrees with truth, and the oracle arm stops being an oracle.

**Decision.**

- `Detection` gains `lane: LaneId | None` — the sensor's lane assignment — and
  `stationary_s: float | None` — how long the sensor has seen the vehicle stationary, `0.0`
  while it moves. `None` means the sensor cannot provide it. Both are standard outputs of
  traffic video analytics (lane-level presence, dwell time), and neither encodes the
  parametric sensor model, so `D-005`'s constraint holds: a pixel pipeline fills them from its
  own map-matching and tracker.
- `Estimator.update(obs, signals, now_s)`. Signal state is passed in from the constraint
  layer, because a controller knows what it commanded (`05_DOMAIN_MODEL.md` §4.2), and the
  estimator copies it into `EstimatedState`, which is therefore built in one place.
- `D-025`'s two thresholds (0.1 m/s, 1 s) move to `traffic_lab.domain.state`, so the backend,
  the sensors and the estimators share one definition.

**Consequence for M3.** Lane assignment and stationary time become things a camera can get
wrong, which is where they belong: in the sensor model, measured against the oracle arm.

**Rejected.** Lane geometry in the domain plus every-step sensing — more realistic
map-matching, but it changes the step loop's cost structure for fidelity M1 does not need.
Accepting an inexact oracle — forfeits sensor/estimator/control attribution, which is what the
project is for.

**Revisit trigger.** M3's camera model needs to report lane uncertainty as a distribution
rather than a single lane.

---

<a id="d-034"></a>
### D-034 — `TrueState` signals are decoded from what SUMO displays

**Status:** SETTLED — ratified by owner 2026-10-07 · **Source:** T1.4 audit

**Problem.** T1.4 projects `SignalState.active_phase` from SUMO's program phase index. Once a
controller drives a light through `setRedYellowGreenState` — every M1 controller does, through
the constraint layer — SUMO switches it to its `online` program, whose phase index is always 0
(verified on 1.27.1), while `spent_duration` keeps counting from the switch. `TrueState.signals`
is therefore meaningless in every controlled run.

**Decision.** The backend decodes the displayed red/yellow/green string into canonical terms.

- `SignalizedIntersection` gains `controlled_connections: tuple[LaneConnectionId, ...]`: the
  connections its signal displays, in SUMO link-index order. Produced by the network generator
  (T1.3).
- A phase's green links follow from its movements. A display whose green link set equals a
  phase's is that phase, green; any other display (yellow, all-red) is a transition.
- **`TrueState` reports what the lights show; the constraint layer reports what has been
  committed.** Outside transitions the two `SignalState`s are identical. During a transition
  `TrueState` names the phase being left (`in_transition=True`, `green_started_s=None`) and the
  constraint layer names the phase being entered. A phase's `phase_started_s` is the start of
  the transition that led into it, in both views.

Implemented by T1.14 on top of T1.3's link order.

**Rejected.** Overwriting `TrueState.signals` with the constraint layer's view — simpler, but a
defect in `apply()` would then be invisible to metrics, which exist to measure what happened.

**Revisit trigger.** A scenario in which two phases display the same green link set, which the
display alone cannot tell apart.

---

<a id="d-035"></a>
### D-035 — Trip-level metrics come from SUMO's tripinfo

**Status:** SETTLED — ratified by owner 2026-10-07 · **Source:** pre-issue review of T1.8

**Problem.** `TrueState` carries only vehicles still in the network, and a trip's final values
are fixed at arrival — the step it disappears. Measured on 531 completed trips: the last
`timeLoss` visible in `TrueState` falls short of SUMO's final value by up to 0.117 s (median
0.048 s, exact in none), and travel time reconstructed from first and last sighting is short by
exactly 1.000 s in every case. T1.8's criterion "matches SUMO's `timeLoss`" was unattainable.

**Decision.** At run end the backend parses SUMO's tripinfo — already written with unfinished
and undeparted vehicles for `D-022` — into canonical per-trip records. Trip-level metrics
(time loss, insertion delay, travel time, waiting time, stops, approach delay, throughput,
completion) are computed from them, filtered to the measurement window by departure and
arrival time. Step-level metrics (queue, max queue, total time loss of vehicles still
in-network) stay on `TrueState`. Tripinfo's `arrivalPos` also makes `D-022`'s sink versus
mid-link split exact at run end, which the step projection can only bound kinematically.

**Rejected.** Reconstructing from `TrueState`: no new parts, but a known bias in the primary
metric, and the reconstruction would itself be a second implementation of SUMO's definition.

**Revisit trigger.** A metric that needs trip data during the run rather than at its end (an
online controller objective, M6–M7).

---

<a id="d-036"></a>
### D-036 — A stop-line detection zone, so a controller can see gaps

**Status:** SETTLED — ratified by owner 2026-10-07 · **Source:** pre-issue review of T1.10

**Problem.** `D-013` requires our actuated controller to be gap-based, but `EstimatedState`
carries per lane only queue and vehicle counts — nothing about when vehicles arrive or how far
from the stop line they are. Without it there are no gaps to measure, and the cross-check
against SUMO's actuated controller would compare two different algorithms.

**Decision.**
- `Detection` gains `distance_to_stop_m: float | None` — how far the vehicle's front is from
  the end of its lane — a standard camera output; `None` if the sensor cannot tell.
- `LaneEstimate` gains `zone_count: float` — vehicles within the lane's detection zone, the last
  `zone_s × speed_limit_mps` metres before the stop line. `zone_s` is an estimator parameter,
  **2.0 s by default** to match SUMO's default actuated detector placement, so the cross-check
  compares like with like (T1.10 verifies that default against SUMO).
- Our actuated controller gaps out when the served lanes' zones have been empty for longer than
  its gap time — presence-mode actuation as deployed in the field.

**Rejected.** Queue-based extension (a different algorithm, which empties the cross-check of
meaning); dropping our actuated controller (loses an M1 exit criterion).

**Revisit trigger.** M3's camera model needs detection-zone coverage that differs from lane
coverage.

---

<a id="d-037"></a>
### D-037 — Saturation flow is calibrated in SUMO, not taken from the HCM

**Status:** SETTLED — ratified by owner 2026-10-07 · **Source:** pre-issue review of T1.5

**Problem.** `D-022` expresses demand as a fraction of saturation flow, and `D-013`'s Webster
computes cycles and splits from it, but nothing fixed the value. Measured on a T1.3-generated
intersection under continuous green with a saturated queue (default passenger `vType`,
13.89 m/s): through 1652, protected left 1624, right 1392 veh/h per lane. The HCM's base
1900 pc/h/ln with standard turn factors (≈ 1805 left, ≈ 1615 right) overstates SUMO's capacity
by 13–16 %, and Webster tuned to capacity that does not exist is the badly tuned baseline
`D-013` exists to prevent.

**Decision.** Saturation flow per lane is **measured in SUMO** for each (vehicle type, speed
limit, turn direction), by a pinned calibration procedure: one movement alone, held green, a
saturated queue, discharge counted over a steady window, several seeds. Results are versioned
with the SUMO version and the `vType` parameters, stored in the repository, and recorded in
every run manifest. Demand fractions (`D-022`) and Webster (`D-013`) read the same values. An
approach's saturation flow is its lane count times the per-lane through value.

**Rejected.** HCM base values: citable, but they mistune Webster in a direction that flatters
every controller compared against it.

**Revisit trigger.** A SUMO upgrade, a new `vType`, or M4's motorcycles (whose saturation flow
is itself a research question).

**Correction, 2026-10-08 — the architect's measurement was of the wrong quantity.** The numbers
above came from holding one movement green with an oversupplied source. T1.5's builder showed
that measures **insertion capacity at the boundary**, not saturation flow: only 0.3–0.7 % of the
counted through vehicles ever halted, because the backlog sat in SUMO's insertion buffer, not at
the stop line. A standing queue discharging after red ran at headways of 1.93–1.97 s from the
fifth vehicle on — about **1830–1866 veh/h/lane through**; turns were similar under both methods
(left ≈ 1666, right ≈ 1390), since the junction limits them either way. So the HCM's 1900
overstates SUMO's **through** saturation flow by only ~2–4 %, not 13–16 %; it still overstates
left (~8 %) and right (~14 %). **The decision stands** — calibrate in SUMO, because the turn
error alone would mistune Webster — and the procedure is now standing-queue discharge (red
pre-load, then green, headways from the fifth queued vehicle, induction loop at the stop line,
five seeds). The stored values are T1.5's, not the figures in the problem statement above.

---

<a id="d-038"></a>
### D-038 — Inter-agent communication standard: ASD-STE100 and Two-Tier Reporting

**Status:** SETTLED — ratified by owner 2026-10-13 · **Source:** Owner instruction

**Problem.** Autonomous agents communicating in natural English consume excessive context tokens
and introduce subtle ambiguities. Words like "should" or "consider" invite speculative abstractions
or silent judgements that violate methodological constraints. Furthermore, technical documentation
in English creates unnecessary cognitive burden when reporting progress directly to the human project owner.

**Decision.**
1. **Tier 1 (Agent-to-Agent):** All agent communication (tickets, acceptance criteria, completion
   reports, PR summaries, commit messages) must strictly follow **ASD-STE100 (Simplified Technical
   English)**. Core rules: maximum 20 words for instructions, 25 for descriptions; controlled vocabulary
   with single meanings; active voice and imperative mood; zero ambiguous modal verbs ("should", "may",
   "could" prohibited; "must" and "can" permitted); maximum 3 nouns in clusters.
2. **Tier 2 (Agent-to-User):** Final handoffs and status summaries delivered to the human owner must
   be provided in **Spanish**, formatted for high readability (clear, non-convoluted everyday prose),
   without omitting critical technical details, test proofs, or modified files.
3. Automated validation is enforced via `scripts/validate_ste100.py`.

**Rejected.** Free-form natural language prompts between agents (high token cost, high variance);
English-only user reports (increases cognitive load for owner); simplified reports that omit technical details.

**Revisit trigger.** The owner requests a different language policy.

---

<a id="d-039"></a>
### D-039 — Modern agent architecture: Google Jules cloud execution & AGENTS.md interface

**Status:** SETTLED — ratified by owner 2026-10-13 · **Source:** Owner instruction

**Problem.** The original delegation workflow ran all subagents in local git worktrees on the host Mac,
competing for CPU, memory, and filesystem locks. Additionally, subagent configurations were tightly
coupled to Anthropic Claude tooling (`.claude/agents/`), failing to leverage Google Pro capabilities
(Gemini Pro / Google Jules).

**Decision.**
1. Adopt **Google Jules** as the cloud-native autonomous worker for tickets requiring multi-file
   implementations (Builders) or exploratory investigations (Spikes). Jules executes in Google Cloud
   sandboxes with zero local machine overhead and delivers clean GitHub Pull Requests.
2. Maintain root **`AGENTS.md`** as the open, universal contract read natively by Jules, Cursor,
   and Gemini CLI, enshrining repository invariants, strict typing rules, and ASD-STE100 standards.
3. Reserve local worktree / subagent execution for fast, interactive changes (1–3 files) or offline work.

**Rejected.** Exclusive reliance on local workstation execution; proprietary vendor locks preventing
the use of Google Pro / Jules.

**Revisit trigger.** Jules integration model changes upstream in Google Labs.

---

## 6. Change log

| Version | Change |
| --- | --- |
| 1.13 | **Multi-agent modernization & ASD-STE100 standardization, 2026-10-13.** Owner ratified `D-038` (inter-agent communication in ASD-STE100; user-facing reports in clear, exhaustive Spanish) and `D-039` (Google Jules cloud-native execution with `AGENTS.md` open contract). |
| 1.12 | **T1.11 audit, 2026-10-08.** `D-008`'s gridlock N set by the owner: 1.5 × the longest possible cycle (Σ max green + yellow + all-red), derived per scenario, since a single queued vehicle can legitimately wait almost a cycle while every vehicle is halted. |
| 1.11 | **`D-037` corrected, 2026-10-08.** The architect's calibration procedure measured boundary insertion capacity (1652 through), not stop-line saturation flow (≈ 1830–1866 through, standing-queue discharge), found by T1.5's builder. The decision to calibrate in SUMO stands — the HCM still overstates turns by 8–14 % — and the procedure is now standing-queue discharge. |
| 1.10 | **T1.8 audit, 2026-10-07.** `D-008`'s insertion-loss numerator refined, ratified by the owner: vehicles scheduled ≥ 30 s before the window closes and still not inserted, from tripinfo, instead of the pending snapshot at the closing instant, which invalidated healthy short windows on synchronised releases. |
| 1.9 | **Pre-issue review of T1.5, 2026-10-07.** `D-037`, ratified by the owner: saturation flow is calibrated in SUMO (measured 1652 / 1624 / 1392 veh/h/lane through / left / right), because the HCM's 1900 overstates SUMO's capacity by 13–16 % and would mistune Webster. |
| 1.8 | **Pre-issue review of T1.10, 2026-10-07.** `D-036`, ratified by the owner: `D-013`'s gap-based actuated controller had no gap information in `EstimatedState`, so detections gain `distance_to_stop_m` and lane estimates a stop-line `zone_count` (zone length 2.0 s at the speed limit, matching SUMO's default detector placement). Webster found to depend on T1.5's saturation flow; T1.10 sequenced after T1.5. |
| 1.7 | **Pre-issue review of T1.8, 2026-10-07.** Three owner decisions. `D-035`: trip-level metrics come from SUMO's tripinfo, because `TrueState` cannot see a trip's final values (time loss short by up to 0.12 s, travel time by exactly 1 s, measured). `D-006` amended: primary delay is `timeLoss + departDelay`, because time spent waiting to enter appears in no metric (274 s against 64 s of time loss under oversaturation) and would reward spillback. `D-008`: insertion-loss threshold set at 1 % of vehicles due in the measurement window. |
| 1.6 | **Pre-issue review of T1.3 and T1.9, 2026-10-07.** `D-023`'s seeding rule **corrected** by the architect on measurement: every SUMO foe pair has a yielding side, so `response` encodes priority, not permissibility; foes now seed `CONFLICTING` and `PERMITTED` comes only from a scenario override. Two decisions ratified by the owner. `D-033`: T1.9 as specified could not produce an exact oracle — detections had no lane, observations no signals, and Δt sampling loses `D-025`'s 1 s halting condition — so detections gain `lane` and `stationary_s`, and the estimator receives signal state from the constraint layer. `D-034`: once a controller drives a light, SUMO reports phase index 0 for good (`online` program), so `TrueState` signals are decoded from the displayed state string through a link order T1.3 produces; truth shows what the lights display, the constraint layer what was committed. |
| 1.5 | **M0 audit and corrections, 2026-08-18.** An audit of the first-pass M0 write-ups found four defects, each re-verified before correcting. `D-031`'s subscription mandate **amended**: measured ~10× faster on TraCI but ~1.7× *slower* on LibSUMO, the transport intended for all heavy workloads; the invariant (one batched projection per step, no per-object access exposed) is kept, the mechanism becomes transport-specific. T0.3 had argued this away in its own write-up instead of escalating. `D-008` **priority reordered**: insertion loss, not teleporting, is the M1 threat — a demand sweep produced zero teleports while 22% of demand failed to insert. `D-025`: lane-area jam length is a **different measure** from the halting counter (disagreed on 230/600 steps), so the metres metric is reopened. `D-023`: the conflict matrix is seeded from static `<request>` `foes`/`response` plus the `G`/`g` case, **not** from runtime `getLinks()` state as first documented. |
| 1.4 | **M0 findings applied, 2026-08-18.** `D-004` amended twice from T0.0: SUMO installs as the `eclipse-sumo` PyPI distribution pinned in `uv.lock` rather than a system package, and **pyarrow is excluded** after a reproduced ABI collision with libsumo that would have broken T1.11's runner on every run. From T0.1: `D-013`'s "11–13%" claim qualified (it is a synthetic-grid, best-of-100, unpaired-seed figure, and the same paper concludes MPLight diverges on realistic networks); `D-025` records the 1 s halting condition as a deliberate divergence from all surveyed prior art, with the consequence that RESCO's Max-Pressure and ours are not the same algorithm; `D-020` gains a legal-action mask adopted from PyTSC. |
| 1.3 | **D-022 confirmed, 2026-08-18.** Owner confirmed the arrivals model, turn-ratio routing, and routing policy as formalised; no changes required. This unblocked `05_DOMAIN_MODEL.md`. Documents `05`, `06`, `07`, `08` written. `09_GLOSSARY.md` dropped — the canonical ↔ SUMO mapping lives in `05_DOMAIN_MODEL.md` §7, and a separate glossary would be a second place to drift. |
| 1.2 | **Second ratification pass, 2026-08-14.** `D-010` ratified after expansion. `D-031` ratified after the owner clarified that "efficiency" meant code efficiency and profiling; the entry was restructured from two categories to three, adding **code-level efficiency as a standing measured practice** (profiling harness, per-milestone hot-path report, performance regression guard, and the rule that an optimization without a before/after number is not accepted). **M1 is now fully unblocked.** |
| 1.1 | **Owner ratification pass, 2026-08-13.** `D-001`–`D-004`, `D-006`, `D-008`, `D-009`, `D-011`–`D-015`, `D-017`, `D-018` ratified and moved to SETTLED. All four M1 blockers closed: `D-020` (phase selection + constraint layer + periodic decision interval, per owner instruction), `D-022` (owner-specified source/propagation/attrition/sink model, formalised), `D-023` (three-valued conflict matrix, authored-then-validated phases), `D-025` (halting queue definition). `D-010` expanded on owner request and held at PROPOSED. Two new entries: `D-031` (efficiency and reuse posture — architect's reframing of an owner instruction, PROPOSED) and `D-032` (initial-state snapshots, derived from the owner's demand model). `D-004` extended with a plotting-library comparison; `D-017` extended with Monte Carlo replication guidance; `D-021` extended with the attrition/estimation-bias problem arising from `D-022`; `D-024` expanded to state the issue concretely. |
| 1.0 | Initial register. `D-005`, `D-016`, `D-019` settled from owner decisions; `D-001`–`D-018` proposed by the architect pending ratification; `D-020`–`D-030` open or deferred. |
