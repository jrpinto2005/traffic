# Critical Review of the Research Specification

**Reviews:** `00_RESEARCH_SPECIFICATION.md` v0.1
**Status:** Complete
**Version:** 1.0
**Author:** Research architect (orchestrating agent)

> **Language note.** All project documents are written in English to match the original
> specification and to keep terminology aligned with code identifiers, SUMO documentation,
> and the literature. Conversation with the project owner happens in Spanish.

---

## 0. How to read this document

This is an adversarial reading of the specification. Its purpose is to find every place
where the document is self-contradictory, silently under-decided, or committed to work
that will not pay for itself — **before** any of it is handed to implementation agents.

Findings are grouped and prefixed:

| Prefix | Meaning |
| --- | --- |
| `C-n` | **Contradiction.** The spec asserts two things that cannot both hold. |
| `G-n` | **Gap.** A decision the spec needs but does not make, and does not list as TBD. |
| `R-n` | **Risk.** Not wrong, but likely to cause failure if left unmanaged. |
| `O-n` | **Over-engineering.** Work the spec commits to that should be cut or deferred. |

Every finding carries a **Resolution** pointing at the decision record
(`04_DECISION_REGISTER.md`) or at the milestone (`03_ROADMAP.md`) that closes it. A finding
with no resolution is still open and must not be silently decided by an implementation agent.

The specification's methodological core is deliberately **not** criticised here, because it
is the strongest part of the document and should be preserved verbatim: the
truth/observation/estimate separation (§22), the oracle as an experimental control (§23),
mandatory ablation (§32), baselines-before-advanced-methods (§26, Principle 6), and
"complexity must be earned" (§2.1). These are the reasons the project is a research lab and
not a traffic-light toy. Everything below assumes they stay.

---

## 1. Contradictions

### C-1 — SUMO is the backend, but §§11–19 specify building a microsimulator

**Severity: Critical.** This is the single most consequential problem in the document.

**What the spec says.** §6.1 designates SUMO as the primary simulation backend and lists
mature microscopic dynamics as the reason. Then §§11–19 and §2.2 specify road segments,
lanes, lane connections, lane-change mechanics, vehicle position/speed/acceleration,
car-following, braking models, stochasticity, and queue formation as things *this project*
will define and evolve. §44 lists "initial car-following model", "initial acceleration
model", "initial braking model", and "initial stochasticity" as open decisions to be made.

**Why it cannot hold.** If SUMO runs the simulation, the project does not choose a
car-following model in the sense the spec implies — it *selects and configures* one from
SUMO's library (Krauss, IDM, EIDM, Wiedemann, ACC/CACC). The same applies to lane changing
(LC2013, SL2015), acceleration and deceleration bounds, driver imperfection (`sigma`), and
reaction time (`actionStepLength`). These are `vType` parameters, not modules to be built.
Conversely, if the project builds these models, SUMO is not the backend and the reasons
given in §6.1 for choosing it evaporate.

The confusion is understandable: the spec conflates two legitimate but different activities
— **modelling the domain** (what our system reasons about) and **implementing the physics**
(what makes vehicles move). SUMO owns the second. The project owns the first.

**Recommendation.** Keep SUMO. Redefine the canonical domain model as a **read-only
projection plus a command surface**, not a re-implementation:

- The domain model exists so that controllers, sensors, estimators, metrics, and
  experiments speak a vocabulary the project controls, and so that a second backend remains
  possible.
- It contains *only* the concepts the project's own layers consume. If no controller,
  sensor, metric, or experiment reads an attribute, that attribute does not belong in the
  domain model, no matter how real the corresponding physical quantity is.
- Vehicle dynamics parameters are **configuration data** that the project passes down to
  the backend and records for reproducibility. They are not project-owned behaviour.

**Consequence for "complexity must be earned."** The principle survives, but its axes
change. Vehicle-physics realism is no longer an axis we climb, because SUMO hands us the
top of that ladder on day one at no incremental cost. The axes where earned complexity
genuinely applies are:

1. **Observation realism** — sensor models, noise, latency, partial coverage.
2. **State estimation** — from naive counting to filtering to learned estimators.
3. **Demand realism** — constant → time-varying → OD-based → calibrated.
4. **Network scale and coupling** — isolated intersection → corridor → grid → city-like.
5. **Controller sophistication** — fixed-time → actuated → max-pressure → MPC → RL.
6. **Behavioural composition** — vehicle mix, and specifically motorcycle share and
   whether lateral (sublane) behaviour is enabled.

Axis 6 is the one exception where a SUMO capability carries real incremental cost, because
the sublane model is significantly more expensive to run (see R-3).

**Resolution:** `D-001`, `D-003`. Fidelity ladder rewritten in `02_PROJECT_CHARTER.md §5`.

---

### C-2 — The Level 0 fidelity target is not reachable in SUMO

**Severity: High.** Follows from C-1 but deserves its own entry because it directly
misdirects the first implementation milestone.

**What the spec says.** §2.2 Level 0 defines the "Minimal Traffic World" as having
"basic traffic dynamics" and "basic queues" but explicitly *no* car-following (that is
Level 1). Level 1 then adds car-following, acceleration/deceleration, desired speed, and
lane changing as separate increments.

**Why it cannot hold.** SUMO has no mode in which vehicles move without a car-following
model. Level 0 as written describes a queueing/cell-transmission abstraction, which is a
different class of simulator entirely. An implementation agent handed "build Level 0"
would either build a second, non-SUMO simulator, or quietly reinterpret the instruction —
and quiet reinterpretation by downstream agents is exactly what §48.14 forbids.

Furthermore, Level 1's items do not arrive incrementally. Turning on SUMO gives you all of
them simultaneously. There is no meaningful ablation "with vs. without car-following"
because the "without" arm does not exist.

**Recommendation.** Delete the Level 0/1/3 ladder and replace it with the six axes listed
in C-1, each with its own explicit, *actually incremental* steps. The first milestone
should target a fully-dynamic single intersection with perfect observation, not a
degenerate physics model.

**Resolution:** `02_PROJECT_CHARTER.md §5`; `M1` in `03_ROADMAP.md`.

---

### C-3 — The definition of "intersection" excludes intersections

**Severity: Medium.** Small in wording, large in consequence.

**What the spec says.** §8.1: "An intersection is a road-system unit containing at least
two coordinated signal groups," with the formal condition `|SignalGroups| >= 2`.

**Why it is wrong.** Under this definition, an unsignalized junction is not an
intersection. But unsignalized junctions are unavoidable: every boundary node of a grid
network is one, every point where a road terminates or merges is one, and every realistic
Bogotá-like topology is full of them. They also matter for control, because they are where
spillback originates and where a controlled intersection's downstream capacity is
determined. A representation that cannot name them cannot reason about them.

The definition also conflates a topological fact (roads meet here) with a control fact
(a signal controller acts here). Those change independently — a junction can be
signalized, de-signalized, or signalized in only some experimental arms.

**Recommendation.** Split the concept:

- **`Junction`** — topological. Any node where lanes from more than one edge connect.
  Carries geometry, connections, and a conflict/priority structure.
- **`SignalizedIntersection`** — a `Junction` that additionally has signal groups, phases,
  and exactly one controller attached. Constraint `|SignalGroups| >= 2` applies here.

A controller's scope is a set of `SignalizedIntersection`s. Metrics and network analysis
operate over all `Junction`s.

**Resolution:** `D-010`.

---

### C-4 — `Movement` and `LaneConnection` are the same entity described twice

**Severity: Low, but it will cause duplicated state and drift if left alone.**

**What the spec says.** §13 defines `LaneConnection` as an explicit edge in a directed lane
graph, with `connection_type` values explicitly including "transition through an
intersection". §15 then defines `Movement` as "a vehicle transition through an
intersection," connecting an origin lane/approach to a destination lane/approach at an
intersection.

**Why it is a problem.** A movement *is* a lane connection whose type is
"through-intersection", plus an association to a signal group. Modelling them as two
entities means two places to store the same topology, two places to keep consistent with
the backend network, and an inevitable divergence when one is updated and the other is not.

**Recommendation.** One entity, `LaneConnection`, as the sole edge type in the lane graph.
`Movement` becomes a *view*: the subset of lane connections that cross a junction, grouped
by (approach, turn direction) and optionally annotated with a signal group. Controllers and
signal logic address movements; the topology stores connections.

A related simplification: §13 also folds lane changes into the same graph. See G-14.

**Resolution:** `D-011`, and the domain model document (pending, `05_DOMAIN_MODEL.md`).

---

### C-5 — "Complexity must be earned" vs. the long-term capability target

**Severity: Low. Tension, not a defect — but it must be named or agents will feel it as one.**

§2.1 forbids adding complexity without demonstrated experimental value. §46 then describes
a target experiment presupposing a 3×3 grid, time-varying OD demand, 30% motorcycles, noisy
partial camera observation, MPC, a six-term weighted objective, 100 seeds, and four
controllers compared.

These are not contradictory, but a naive reader can take §46 as a requirements list and
§2.1 as a prohibition on getting there. The resolution is to state explicitly that §46 is a
**capability target** describing what the mature platform should be *able* to express — not
a set of features to be built up-front, and not a promise that every component will be
built at all.

**Resolution:** `02_PROJECT_CHARTER.md §3`.

---

## 2. Gaps

### G-1 — No definition of the deliverable, the audience, or success

**Severity: Critical (now closed).** The specification describes at length what to build and
how to reason, and never once says what "done" looks like, who the output is for, or how to
tell a good outcome from a bad one. Scope cannot be defined without this, because scope is
precisely the set of things that serve the deliverable.

**Resolved by owner decision:** the deliverable is **learning plus a portfolio artifact**,
on an open-ended timeline, with a possible later pivot to a prototype. This has sharp
consequences that are worked out in the charter — most importantly, it **promotes
visualization from a secondary concern to a primary deliverable**, which inverts the
priority the specification gives it in §34.

**Resolution:** `02_PROJECT_CHARTER.md §§1–4`.

---

### G-2 — Computer vision is present in the roles and the data section but absent from the body

**Severity: High (now closed).** §43 lists a "Computer Vision" agent role. §44 lists
"synthetic video generation" and "real video sources" as open data decisions. But §§20–22,
which actually specify sensing, describe a purely *geometric and probabilistic* camera —
field of view, range, detection probability, position noise. Those are two different
projects. Rendering camera imagery from SUMO and running detection and multi-object
tracking on it is comparable in size to the entire rest of the platform.

**Resolved by owner decision:** parametric sensor model in the core; a reserved extension
point for a later optional perception track. The extension point is a real architectural
obligation, not a comment: the observation interface must be defined such that a
pixel-derived detection stream can be substituted for the parametric one without any change
to estimators, controllers, or experiments.

**Resolution:** `D-005`; extension point specified in the architecture document (pending).

---

### G-3 — The controller ladder is missing its most important baseline

**Severity: High.**

§26 lists Fixed-Time → Actuated → Optimization → MPC → RL → Distributed. **Max-Pressure is
absent**, and its absence would undermine every comparison the project makes.

Max-Pressure is the reference point in this literature. It is decentralized, needs only
upstream and downstream queue counts, has proven throughput-stability guarantees, and
routinely matches or beats deep RL methods. The RESCO benchmark reports roughly an 11%
improvement of MPLight over Max-Pressure, and Chen et al. report ~13% — that is the actual
size of the gap that sophisticated learned methods have to clear. A project that shows RL
beating a naive 30s/30s fixed-time plan has demonstrated nothing, because so does
Max-Pressure, at a fraction of the complexity.

Two further baseline gaps:

- **Webster's method** for fixed-time. §26's example is "30s NS / 30s EW", an arbitrary
  plan. A *badly tuned* baseline manufactures improvement out of nothing. Fixed-time must
  mean a Webster-optimal cycle and green split computed for the demand being tested.
- **SUMO's own actuated control** (gap-based, `type="actuated"`), as a second,
  independently-implemented actuated reference. If our actuated controller differs greatly
  from SUMO's, one of them has a bug.

**Recommendation.** The mandatory baseline set, required before any advanced controller is
reported, is: Webster fixed-time, SUMO gap-actuated, our own actuated, and Max-Pressure.
Optionally SOTL and Max-Wave (both are in RESCO).

**Resolution:** `D-013`; delivered in `M1` of `03_ROADMAP.md`.

---

### G-4 — No statistical methodology

**Severity: High.** §31 asks for train/validation/test splits and §46 mentions 100 seeds,
but nothing specifies how results become claims. Missing entirely:

- **Warm-up handling.** The first minutes of any run start from an empty network and are
  unrepresentative. Metrics computed over them are biased low and the bias varies with
  demand, which systematically distorts controller comparison.
- **Measurement window and end-of-run truncation.** Vehicles still in the network when the
  run ends have no completed travel time. Dropping them biases results in favour of
  controllers that let vehicles queue (their slow vehicles never finish and never count).
  This is a well-known way to accidentally prove that a bad controller is good.
- **Paired comparison / common random numbers.** Comparing controllers on *different*
  random demand realisations wastes most of the statistical power available. The same seed
  must produce the same vehicle arrivals across controller arms.
- **Uncertainty reporting.** No mention of confidence intervals, effect sizes, or the
  number of replications needed to detect a difference of a given size.
- **Multiple comparisons.** Comparing 5 controllers across 4 demand regimes and 3 sensor
  conditions is 60 comparisons; some will look significant by chance.
- **Seed hygiene.** Which seed controls what (demand, driver imperfection, sensor noise,
  RL exploration) must be separable, or ablations become uninterpretable.

**Recommendation.** A dedicated methodology document defining all of the above once, so
that no experiment has to re-decide it. For a learning/portfolio project this is
disproportionately valuable: correct experimental methodology is the part of the work that
reads as senior, and it is cheap to specify up front and expensive to retrofit.

**Resolution:** `D-017`, `D-018`; full treatment in `07_EXPERIMENT_METHODOLOGY.md` (pending).

---

### G-5 — "Delay" and "queue" are used throughout without definition

**Severity: High.** §38 lists average delay, total delay, and approach delay as headline
metrics. "Delay" has at least three incompatible operational definitions in traffic
engineering:

| Definition | Meaning | Notes |
| --- | --- | --- |
| **Time loss** | Actual travel time minus travel time at the desired/free-flow speed | What SUMO reports as `timeLoss`; includes deceleration and acceleration losses |
| **Control delay** | Delay attributable to the signal, per HCM methodology | Requires a defined approach segment; comparable to published engineering results |
| **Stopped delay** | Time spent below a speed threshold | Simplest, least comparable |

They can differ by a factor of two on the same run. Reporting "delay improved 18%" without
saying which one is not a result.

§19 does acknowledge that queue definition is TBD, and correctly notes that instantaneous
zero speed should not imply queued. That instinct is right and needs to become a concrete,
testable rule.

**Recommendation.** Pin one primary definition (proposed: **time loss**, because SUMO
computes it natively, it needs no geometric assumptions, and it is well-defined on
networks), record the others as secondary, and require every reported figure to name its
metric. Queue definition gets a spike because the "distance to stop line" component
interacts with network geometry.

**Resolution:** `D-006`, `D-007`.

---

### G-6 — No policy for teleporting, gridlock, or unfinished vehicles

**Severity: High. This is the most likely way for the project to produce silently wrong results.**

SUMO teleports vehicles that have been stuck longer than `--time-to-teleport` (default 300s).
The vehicle vanishes and reappears downstream. Under congested conditions — which is
precisely the regime where adaptive control is supposed to prove itself — teleporting
silently removes the congestion the experiment is trying to measure, and it removes *more*
of it for worse controllers. A comparison run with defaults can therefore show no
difference between an excellent and a terrible controller, or invert their ranking.

Neither the specification nor any of its open-questions lists mentions this. An
implementation agent following the spec faithfully will hit it and will not know.

Related unspecified behaviours: what happens when the network gridlocks and no vehicle can
move; what happens to vehicles that never enter because insertion is blocked (SUMO discards
them after a while, silently reducing the demand actually applied); and how unfinished trips
are accounted.

**Recommendation.** Make these explicit, loud, and checked:

- Disable teleporting (`--time-to-teleport -1`) for all research runs.
- Count and report vehicles that failed to insert; abort the run if the number exceeds a
  threshold, because the applied demand no longer matches the configured demand.
- Detect gridlock explicitly and mark the run as gridlocked rather than reporting its
  metrics as if valid.
- Define the measurement window and the treatment of vehicles still in-network at its end.

**Resolution:** `D-008`, `D-018`.

---

### G-7 — The action space is never defined, and it is the most consequential controller decision

**Severity: High.** §44 lists "exact action space" as open, which is correct, but the
document does not convey how much rests on it. The action space determines what every
controller can express, what RL can learn, what MPC optimizes over, and whether results are
comparable to the literature at all. The main families are:

| Family | Action | Notes |
| --- | --- | --- |
| **Phase selection** | Choose the next phase from a fixed set at each decision point | Most common in RL literature; simple; can produce erratic switching without min-green constraints |
| **Binary keep/switch** | Extend the current phase or advance to the next in a fixed cyclic order | Very constrained, very stable, easy to compare, used by many strong baselines |
| **Phase duration** | Set the duration of the next phase | Closer to engineering practice; harder for RL |
| **Cycle / split / offset** | Set plan parameters, applied over a whole cycle | Coordination-friendly; slow-acting; the classical formulation |

They are not interchangeable, and a controller ladder that mixes them is not a ladder. Two
controllers with different action spaces cannot be compared cleanly, because part of the
difference is the freedom they were given, not the intelligence they applied.

**Recommendation.** Define a single canonical action interface with an explicit constraint
layer (min green, max green, yellow, all-red, no-skip rules), and require all controllers to
act through it. Where a controller family genuinely needs a different action space, that
becomes an explicit experimental variable, reported as such.

**Resolution:** Open. Requires a spike; scheduled in `M1`. Tracked as `D-020`.

---

### G-8 — State estimation is specified only as notation

**Severity: Medium-High.** §22 gives `Ŝ_t` and `P(S_t | O_{1:t})` and stops. This layer sits
between the sensor model and every controller, so it cannot be left as a symbol. Concretely
undecided: whether estimation is per-lane counting, a recursive filter (Kalman on queue
dynamics, or particle filter), a learned model, or nothing at all in the first version.

There is a defensible minimal answer — the first estimator can be an identity-ish
accumulator that maintains per-lane counts from detections and decays them — and it should
be written down as a deliberate choice rather than arrived at by accident.

Worth noting for the project owner: this layer is where the platform's most distinctive
work could eventually live. Most of the adaptive-signal-control literature either assumes
perfect observation or uses a fixed detector model; explicitly separating estimation and
studying how controller performance degrades through it is uncommon and interesting.

**Resolution:** Open. Minimal estimator defined in `M3`. Tracked as `D-021`.

---

### G-9 — No prior-art review, with a real risk of rebuilding existing tooling

**Severity: Medium-High.** The specification does not mention any existing work in this
exact space. Several mature projects overlap heavily with what is described:

- **`sumo-rl`** (Alegre) — SUMO environments for traffic signal control, Gymnasium and
  PettingZoo compatible, widely used. Covers a large fraction of the experiment-harness and
  RL-environment work the spec describes.
- **RESCO** (Pi-Star Lab) — a benchmark suite with standardized scenarios and implemented
  baselines including Fixed-Time, Max-Pressure, and Max-Wave, plus DRL methods. It is the
  closest thing to a canonical comparison set.
- **LibSignal** — a multi-simulator traffic-signal-control library spanning SUMO and
  CityFlow.
- **PyTSC** — a unified multi-agent RL platform for traffic signal control across
  simulators.

For a learning-oriented project, "someone already built this" is *not* an argument against
building it — reimplementing is how you learn, and the spec's methodological ambitions
(oracle conditions, sensor realism, motorcycle composition) go beyond what these provide.
But it is a strong argument for **reading them first**: their scenario formats, action-space
conventions, and baseline implementations are free design review, and matching their
conventions makes results comparable to published numbers instead of incomparable.

**Recommendation.** A time-boxed prior-art spike as the first milestone, producing a written
comparison and an explicit build-vs-reuse decision per component.

**Resolution:** `M0` in `03_ROADMAP.md`.

---

### G-10 — No technology stack, configuration system, or results storage decision

**Severity: Medium.** The spec never states the implementation language (Python is implied
by §6.1 and §25 but never stated), nor how experiments are configured, nor where results go.
§30 describes `Experiment` and `ExperimentResult` as concepts with no serialization format.

For a project whose central promise is "every result reproducible from a configuration"
(Principle 7), the configuration format and the results store are load-bearing
infrastructure, not incidental choices. They also need to be settled before implementation
agents start, because every agent will touch them.

**Resolution:** `D-004`.

---

### G-11 — Demand generation and routing are TBD but block everything

**Severity: Medium.** §§28–29 honestly mark these as unresolved and important. The point to
add is that they are not *deferrable* in the way other TBDs are: no experiment can run
without demand, and demand design determines what the experiment can show. In particular,
whether the demand is *stationary* (Poisson at a fixed rate) or *non-stationary*
(peak/off-peak) changes which controllers can win, because a fixed-time plan tuned for the
average is severely penalised by non-stationarity and barely penalised by stationarity.

Routing has a similar hidden consequence: if vehicles re-route around congestion, signal
control and route choice interact, and it becomes impossible to attribute a change in
network performance to the controller. That interaction is interesting later and
disqualifying early.

**Recommendation.** Fixed routes and seeded stochastic arrivals for the first milestones,
explicitly recorded as a limitation. Route choice becomes an experimental axis only after
the isolated-intersection results are solid.

**Resolution:** `D-022` (proposed, see register).

---

### G-12 — Visualization architecture leaves live-vs-replay undecided

**Severity: Medium.** §35 shows the simulation engine emitting a "state stream" consumed by
a logger and a renderer in parallel, which implies live rendering. §5 requires that batch
mode run without visualization. Live rendering couples the renderer's frame rate to the
simulator's step rate, needs a transport, and makes the renderer a dependency of the
simulation process.

A **record-then-replay** design removes all of that: the simulation always writes a state
trace; the renderer is an independent consumer of trace files. Interactive viewing becomes
replay, which is strictly better for research anyway because you can scrub, pause, and
re-watch the exact run that produced a surprising number. Live viewing during a run, if ever
wanted, is then a special case of tailing the trace.

The one thing lost is interactive intervention (a human changing signals mid-run), which
the spec does not ask for.

**Resolution:** `D-009`.

---

### G-13 — No conflict/compatibility model, which is what actually defines a valid phase

**Severity: Medium.** §10 defines a phase as "a compatible set of movements" and §44 lists
"conflict representation between movements" as open. But compatibility is the *primitive* —
phases are derived from it. Without an explicit conflict relation the system cannot validate
that a controller's requested phase is safe, cannot enumerate the legal phase set for an
arbitrary junction geometry, and cannot support the spec's own requirement (§8.1) that
geometry be data rather than hard-coded assumption.

Also unaddressed: protected vs. permitted turns (a left turn may be legal *and* conflicting,
yielding to opposing through traffic), which changes both the conflict matrix and the
capacity model.

**Resolution:** Open, tracked as `D-023`. Design in `05_DOMAIN_MODEL.md`.

---

### G-14 — Longitudinal connectivity and lateral adjacency are merged into one graph

**Severity: Low-Medium.** §13 proposes a single directed lane graph `G_L = (V_L, E_L)` whose
edges include continuation, lane change, and intersection transitions. These have different
algebra: continuation and intersection transitions are what a *route* traverses; lane change
is a lateral relation between parallel lanes that a route does not traverse and a shortest
path must not treat as a hop. Merging them means every routing, distance, or reachability
computation has to filter edges by type, and forgetting the filter produces plausible but
wrong answers.

**Recommendation.** Two relations: `successor` (longitudinal, route-traversable, includes
intersection crossings) and `adjacent` (lateral, same direction, not route-traversable).

**Resolution:** `D-011`.

---

### G-15 — Bidirectional road representation left open, with a standard answer available

**Severity: Low.** §11 marks bidirectional segment representation as TBD. There is a
well-established convention used by both SUMO and OpenStreetMap: edges are unidirectional;
a two-way street is a pair of opposing edges linked by an optional reference. Inventing a
bidirectional primitive would create a translation problem at the backend boundary and at
the OSM import boundary later, for no benefit.

**Resolution:** `D-012`.

---

## 3. Risks

### R-1 — Unbounded architecture: no deadline, no single research question

**Severity: Critical. This is the most likely cause of project failure.**

The owner has chosen an open-ended timeline and a broad platform with no single driving
research question. Both choices are legitimate for a learning and portfolio project. Their
*combination* removes every natural forcing function: there is no date that says "stop
building infrastructure" and no question that says "this component is not needed to answer
it." The characteristic failure is a beautiful, well-abstracted, thoroughly-tested codebase
that has never run an experiment, plus a folder of empty directories.

The compounding factor is that this specification is unusually good at describing
*architecture*, which makes architecture the path of least resistance.

**Mitigation, adopted:** the roadmap is structured as **vertical slices**. Every milestone
must traverse the full stack — network, demand, simulation, observation, controller,
metrics, and a viewable artifact — and every milestone's exit criterion is a *result*
(a figure, a number with a confidence interval, a recorded run you can watch), never a
component. Breadth is achieved by successively deepening a working system, never by
building layers that do not yet connect to anything.

A secondary mitigation: a hard rule that no abstraction may be introduced for a second
implementation that does not yet exist, with two named exceptions where the insurance is
cheap and the retrofit is expensive (the backend adapter boundary, and the observation
interface).

**Resolution:** `02_PROJECT_CHARTER.md §6`; entire structure of `03_ROADMAP.md`.

---

### R-2 — Abstraction tax on the canonical domain model

**Severity: High.** Principle 9 ("preserve optionality") and §6.2 ("SUMO is a backend, not
the canonical representation") are correct in spirit and dangerous if taken literally. A
domain model that mirrors everything SUMO can express, maintained against exactly one
backend, is pure cost: every network feature must be modelled twice, kept in sync, and
tested twice, to enable a migration that has a low probability of ever happening.

The observation from the prior-art review sharpens this: LibSignal and PyTSC already solve
multi-simulator portability, so if portability ever genuinely becomes the goal, adopting one
of them is likely cheaper than having maintained a bespoke abstraction for years.

**Mitigation.** Keep the boundary, shrink the model. The adapter interface stays (it is a
handful of methods and it is what makes controllers testable without a simulator at all).
The domain model contains only what project-owned layers consume. Anything SUMO already
models and no project layer reads stays in SUMO.

The practical test for whether an attribute belongs in the domain model: *name the
controller, sensor, metric, or experiment that reads it.* If you cannot, it does not go in.

**Resolution:** `D-003`.

---

### R-3 — The sublane model is a performance cliff, and motorcycles are the reason to jump off it

**Severity: Medium-High.** SUMO's sublane model divides each lane into lateral strips and
switches lane-changing to SL2015, enabling side-by-side occupancy — which is exactly what is
needed to represent motorcycle filtering and lane splitting, one of the project's stated
interests (§18) and the thing that makes Bogotá a substantive setting rather than a label.

The cost is real and rarely stated up front: the recommended lateral resolution is at most
the width of the narrowest vehicle, so representing motorcycles means a fine resolution,
which multiplies the per-step lateral computation. Combined with the fact that RL training
and multi-seed sweeps are already the project's heaviest workloads, enabling sublane
globally could make the experiment budget an order of magnitude worse.

**Mitigation.** Treat sublane as an explicit experimental arm with a measured cost, not a
default. Milestone M4 includes a benchmark of wall-clock and results-difference with sublane
on vs. off. If the results difference is small relative to the cost, the honest conclusion —
"motorcycle filtering does not change the control conclusions at this scale, and here is the
evidence" — is itself a legitimate finding, and precisely what §32's ablation principle asks
for.

**Resolution:** `M4` in `03_ROADMAP.md`.

---

### R-4 — Handoff to less capable agents will fail on under-specified tickets

**Severity: High.** The project's operating model is that a frontier model designs and
weaker agents implement. The specification's §43 approaches this as a *taxonomy* problem —
it lists fourteen candidate agent roles. Role taxonomy is not what makes delegation work.
What makes it work is:

1. **Frozen interfaces.** The signature and the data contract exist before the ticket does.
2. **Executable acceptance criteria.** Tests the agent can run to know it is finished,
   written before the implementation.
3. **Small, closed scope.** A ticket that requires a judgement call the agent is not
   equipped to make will get a judgement call anyway, silently.
4. **Explicit non-goals per ticket**, because a capable-sounding agent with spare capacity
   will helpfully add abstractions nobody asked for.
5. **A named place to escalate**, so that an under-specified ticket comes back rather than
   being guessed at — which is the direct operationalisation of §48.14.

Fourteen roles is also more coordination surface than a project with one human needs.

**Mitigation.** Reduce to a small set of agent archetypes, and invest instead in a strict
ticket template and a contract-first workflow.

**Resolution:** `D-015`; `08_AGENT_HANDOFF_PROTOCOL.md` (pending).

---

### R-5 — Methodology can be invalidated silently by implementation shortcuts

**Severity: High.** §48.14 forbids exactly this, but forbidding is not preventing. The
concrete mechanisms by which it happens in this specific project:

- Teleporting or vehicle-insertion loss quietly changing the applied demand (G-6).
- A controller receiving true state through a debug path while nominally running on
  observations — the exact failure the truth/observation split exists to prevent, and easy
  to introduce accidentally when both objects are in scope.
- Reusing a seed across arms in a way that correlates noise with the treatment.
- Metrics computed over a window that includes warm-up.
- An experiment whose recorded configuration no longer matches the code that ran it.

**Mitigation.** Make each one a machine-checkable invariant rather than a documented rule:
type-level separation between `TrueState` and `Observation` so a controller *cannot* accept
the wrong one; a run manifest capturing config hash, code version, SUMO version, and seeds;
assertion of the no-teleport setting at run start; and a validation suite that runs before
any result is reported.

**Resolution:** `07_EXPERIMENT_METHODOLOGY.md` (pending) and `D-008`, `D-017`, `D-018`.

---

## 4. Over-engineering to cut or defer

### O-1 — The SUMO vs. CityFlow backend benchmark (§6.3)

**Recommendation: defer, do not cancel.**

A correction to an earlier assessment of mine: CityFlow is not abandoned. It remains
substantially faster than SUMO (reported around 20×) and is actively used in the
large-scale RL literature, with CityFlowER as a recent extension. So the case against the
benchmark is not that the alternative is dead.

The case is that the benchmark answers a question the project does not yet have. §6.3 lists
eleven evaluation criteria — that is a multi-week engineering exercise, and it must happen
before any research output exists, on a project whose main risk (R-1) is never reaching
research output. The two backends also differ in *fidelity*, not just speed: CityFlow
abstracts away heterogeneity and detailed driver behaviour, which is precisely what the
project needs for motorcycles. It is not a drop-in faster SUMO.

**Trigger to revisit:** when a measured experiment budget (most likely RL training or a
large seed sweep) makes wall-clock the binding constraint. At that point the first remedy is
LibSUMO, not a different simulator.

**Resolution:** `D-001`.

---

### O-2 — Fourteen top-level directories for a project with no code (§42)

The proposed layout separates `simulation/`, `domain/`, `controllers/`, `optimization/`,
`observation/`, `perception/`, `experiments/`, `visualization/`, `evaluation/`, `research/`,
`data/`, `configs/`, `tests/`, `docs/`. Several of these will stay empty for months
(`perception/`, `optimization/` as distinct from `controllers/`), and empty directories
actively mislead implementation agents about where code belongs. `evaluation/` versus
`experiments/` versus `research/` is a boundary nobody will apply consistently.

The specification itself says the structure should emerge from the architecture — this entry
just makes that concrete.

**Recommendation.** Start with a single installable package and a small number of
subpackages, and split only when a module actually grows. Proposed layout in `D-014`.

---

### O-3 — Fourteen agent roles (§43)

See R-4. Recommend five archetypes distinguished by the *kind of contract* they work
under, not by subject matter.

---

### O-4 — Pedestrian modelling (§16)

The spec already says pedestrian modelling should be minimal. Stronger recommendation:
**defer it entirely.** Pedestrian phases meaningfully constrain signal timing (minimum
crossing times set hard floors on green duration) and SUMO's pedestrian model is a
substantial subsystem. Including it early adds constraint complexity to every controller
before any controller has been validated. Fixed minimum-green floors capture most of the
signal-timing consequence at near-zero cost, with the caveat recorded as a limitation.

---

### O-5 — A custom renderer before a trace format exists

§34 and §36 describe a fairly rich visualization with toggleable overlay layers. Two
observations: `sumo-gui` already exists and is free, and it covers the "watch traffic move"
need entirely. What it *cannot* do is the thing the project actually needs — overlay
observations against ground truth and show controller reasoning (§37).

So the custom renderer is justified, but its value is entirely in the research overlays, and
those depend on a recorded trace containing observations, estimates, and controller
decisions. Build the trace format first and use `sumo-gui` in the interim.

---

## 5. What was correct and should not be revisited

Recorded explicitly so that later agents do not "improve" these:

1. **Truth / observation / estimate separation (§22).** Non-negotiable, and worth enforcing
   in the type system rather than by convention.
2. **The oracle condition (§23).** The cleanest available way to attribute a failure to
   control, sensing, or estimation. Every experiment involving sensing must carry its oracle
   arm.
3. **Baselines before advanced methods (Principle 6).** Strengthened by G-3, not weakened.
4. **Ablation as the test of added complexity (§32).**
5. **Reproducibility from configuration (Principle 7).**
6. **Backend independence as a boundary (Principle 1)** — kept, though the *model* behind it
   is shrunk per R-2.
7. **"The simulator is a scientific instrument, not the final product" (§1).** This single
   sentence prevents most of the ways this project could go wrong.
8. **Refusing to assume advanced controllers will win (§26, closing line).** Rare and
   correct. The Max-Pressure literature is a standing demonstration of why.

---

## 6. Summary of open items requiring a decision

Items no implementation agent may decide on its own:

| ID | Item | Blocking |
| --- | --- | --- |
| `D-020` | Canonical action space and constraint layer | M1 |
| `D-021` | State estimation approach (minimal version) | M3 |
| `D-022` | Demand generation framework and routing policy | M1 |
| `D-023` | Conflict/compatibility model and phase schema | M1 |
| `D-024` | Objective function for optimization-based controllers | M6 |
| `D-025` | Queue definition (stop-line distance component) | M1 |
| `D-026` | Sublane on/off as default | M4 |
| `D-027` | RL formulation (state, action, reward, algorithm) | M7 |

See `04_DECISION_REGISTER.md` for the full register including settled items.

---

## Sources

- [sumo-rl — RL environments for traffic signal control with SUMO](https://github.com/LucasAlegre/sumo-rl)
- [RESCO — Reinforcement Learning Benchmarks for Traffic Signal Control](https://github.com/Pi-Star-Lab/RESCO)
- [RESCO paper (NeurIPS Datasets & Benchmarks 2021)](https://datasets-benchmarks-proceedings.neurips.cc/paper/2021/file/f0935e4cd5920aa6c7c996a5ee53a70f-Paper-round1.pdf)
- [LibSignal: An Open Library for Traffic Signal Control](https://arxiv.org/pdf/2211.10649)
- [PyTSC: A Unified Platform for Multi-Agent RL in Traffic Signal Control](https://pmc.ncbi.nlm.nih.gov/articles/PMC11902778/)
- [SUMO TraCI documentation](https://sumo.dlr.de/docs/TraCI/index.html)
- [SUMO Sublane Model documentation](https://sumo.dlr.de/docs/Simulation/SublaneModel.html)
- [CityFlow](https://cityflow-project.github.io/)
- [CityFlowER: An Efficient and Realistic Traffic Simulator with Embedded ML Models](https://arxiv.org/pdf/2402.06127)
- [Purpose in the Machine: Do Traffic Simulators Produce Distributionally Equivalent Outcomes for RL?](https://arxiv.org/pdf/2311.08429)
