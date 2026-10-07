# Project Charter — Traffic Control Research Lab

**Status:** Active. This document governs scope.
**Version:** 1.0
**Supersedes:** `00_RESEARCH_SPECIFICATION.md` §§1–4, §2.2 (fidelity ladder), §42, §43
**Depends on:** `01_CRITICAL_REVIEW.md`

> The charter answers three questions the original specification never asked: **what is
> being delivered, to whom, and how do we know it worked.** Everything downstream —
> roadmap, architecture, agent tickets — derives its priorities from here. When a decision
> elsewhere conflicts with this document, this document wins, or this document changes.

---

## 1. What this project is

A **research platform for adaptive traffic signal control**, built to study how signal
control strategies behave under progressively more realistic traffic, sensing, and network
conditions — with motorcycle-heavy traffic as a first-class concern rather than an
afterthought.

The platform is composed of a simulation backend (SUMO) wrapped in a project-owned
interface, a synthetic sensing layer that deliberately withholds information from
controllers, a state estimation layer, a family of controllers spanning classical to
learned, an experiment harness that makes every result reproducible from a configuration
file, and a 2D visualization that shows not just traffic but what the controller believed
and why it acted.

The governing sentence from the original specification stands unchanged:

> **The simulator is a scientific instrument, not the final product.**

---

## 2. What is being delivered, and to whom

**Primary purpose: learning, and a portfolio artifact.** A possible later pivot toward a
prototype is acknowledged but is explicitly *not* a current design constraint.

This is not a soft goal, and it is not the same as "a fun side project." It has hard
consequences for scope, and they are not the ones the original specification assumed.

### 2.1 Consequences of the deliverable being learning plus portfolio

**Consequence 1 — Visualization is promoted to a primary deliverable.**
The original specification treats the 2D interface as secondary (§34: "deliberately
simple", §37: "primarily a research/debugging capability rather than a presentation
feature"). For a portfolio artifact this inverts. A person evaluating the work will spend
thirty seconds on it before deciding whether to spend thirty minutes. Nothing communicates a
traffic control platform in thirty seconds except watching it run. The visualization is how
the rest of the work becomes legible.

This does not mean building it first or making it elaborate. It means it is a milestone
with an owner and an exit criterion, not a stretch goal.

**Consequence 2 — Methodological rigor is a feature, not overhead.**
For a learning goal, the experimental methodology *is* much of the thing being learned.
For a portfolio, correct methodology is the strongest available signal of seniority —
confidence intervals, paired comparisons, honest baselines, and stated limitations
distinguish research from a demo more sharply than any algorithm does. The methodology
described in `01_CRITICAL_REVIEW.md` G-4 is therefore in scope at full strength, not
trimmed.

**Consequence 3 — Reimplementing existing tools is legitimate, but only knowingly.**
`sumo-rl`, RESCO, and LibSignal already cover parts of this ground. Building your own is a
valid learning choice. Building your own *without having read theirs* is not — it forfeits
free design review and produces results that cannot be compared to published numbers.
Hence the prior-art spike in M0.

**Consequence 4 — Negative and null results are deliverables.**
"We enabled the sublane model, measured the cost, and it did not change the control
conclusions" is a portfolio-worthy result and a genuine research finding. The project does
not need every advanced method to win. It needs every claim to be defensible.

**Consequence 5 — Calibration against real Bogotá data is not required.**
Nothing in a learning/portfolio deliverable requires that the simulation be a validated
model of a real city. Realism is pursued where it makes the *research questions*
meaningful, not to certify the simulator. This removes an entire class of work (data
acquisition, calibration, validation against field measurements) that would otherwise
dominate the schedule. It also imposes an obligation: every claim must be stated as being
about the simulated environment, never about Bogotá.

### 2.2 The concrete artifacts

At any point after M1, the repository should contain:

1. A **README** that shows results — figures, a recorded run, the headline numbers — above
   the fold, before any installation instructions.
2. A **reproducible experiment suite**: `run <config>` reproduces any reported figure.
3. A **written results document** per milestone, including limitations.
4. A **recorded run** (GIF or short video) demonstrating the current capability.
5. The **decision register**, kept current. A visible record of deliberate choices and
   their rationale is itself part of what the artifact demonstrates.

---

## 3. Research posture

The owner has chosen a **broad platform without a single driving research question**. This
charter accepts that choice and constrains it as follows.

The platform is built to be *capable of* answering the questions preserved in
`00_RESEARCH_SPECIFICATION.md` §45. It does not commit to answering all of them. Each
milestone answers a small, concrete question end-to-end, and breadth accumulates from
those answers rather than from unused capability.

Three of the preserved questions are worth flagging by expected value:

| Question | Assessment |
| --- | --- |
| **Q1 — adaptive vs. fixed-time** | Already answered in the literature. Necessary as a sanity check and a first milestone; produces no novelty. Do it, report it, move on. |
| **Q4 — robustness to imperfect observation** | High value. The truth/observation/estimate architecture is already built for it, and most published work assumes away the problem. |
| **Q5 — motorcycles** | Highest value. Genuinely under-studied, and the one place where the Bogotá framing does real work rather than decorating the abstract. |

If the project ever wants to sharpen into a single question, Q5 crossed with Q4 —
*how does motorcycle composition change what a controller needs to observe?* — is the
recommendation on file. **No commitment is required now.** The roadmap reaches both
naturally.

**§46 of the original specification is a capability target, not a requirements list.** It
describes what a mature platform should be able to express. It is not a promise that every
component named in it will be built.

---

## 4. Success criteria

Stated as observable conditions, not aspirations. The project is succeeding if, at any point
in time, all of the following are true:

| # | Criterion |
| --- | --- |
| **S1** | A stranger can clone the repository, follow the README, and reproduce a reported figure. |
| **S2** | Every reported number has a named metric definition, a seed count, and an uncertainty estimate. |
| **S3** | Every advanced controller has been compared against Webster fixed-time, actuated, and Max-Pressure on identical demand realisations. |
| **S4** | The current state of the system can be watched running, and the recording shows controller reasoning, not just moving rectangles. |
| **S5** | Every non-obvious design decision has an entry in the decision register with a rationale and a revisit trigger. |
| **S6** | No controller has ever received information that its sensor configuration does not provide, and this is enforced by types rather than by discipline. |
| **S7** | The most recent milestone completed a full vertical slice — it produced a result, not a component. |

**The project is failing** — regardless of code quality — if S7 has been false for two
consecutive work periods. That is the tripwire for R-1 (unbounded architecture) from the
critical review.

---

## 5. Fidelity axes (replaces the Level 0–4 ladder)

The original specification's fidelity ladder (§2.2) assumed the project implements vehicle
physics. It does not; SUMO does. See `01_CRITICAL_REVIEW.md` C-1 and C-2.

Complexity is instead earned along six independent axes. Each axis has genuinely
incremental steps, and each step must be justified by the criteria in
`00_RESEARCH_SPECIFICATION.md` §2.1 before it is taken.

| Axis | Step 0 | Step 1 | Step 2 | Step 3 |
| --- | --- | --- | --- | --- |
| **A. Observation** | Oracle (perfect state) | Ideal detectors, full coverage | Partial coverage, detection probability, position/speed noise | Latency, dropouts, sensor failure |
| **B. Estimation** | Identity (observation used directly) | Per-lane counting with decay | Recursive filter over queue dynamics | Learned estimator |
| **C. Demand** | Stationary Poisson, per-approach | Time-varying profiles (peak/off-peak) | OD matrices with fixed routes | Demand shocks; route choice |
| **D. Network** | 1 signalized intersection | 2 coupled intersections | Corridor | Grid (2×2, 3×3) → arbitrary → Bogotá-like |
| **E. Control** | Webster fixed-time | Actuated | Max-Pressure | MPC → RL → coordinated/distributed |
| **F. Composition** | Cars only | Cars + motorcycles, distinct vType, no lateral behaviour | Sublane enabled, filtering | Driver heterogeneity distributions |

**Rules governing the axes:**

1. Axes advance **independently**. A milestone typically advances one axis and holds the
   rest, so that the change in results is attributable.
2. The **oracle arm (A-Step-0) is never retired.** Every experiment involving imperfect
   sensing carries its oracle counterpart, per §23.
3. A step is taken only when a *specific* experiment needs it. "It would be more realistic"
   is not a reason.
4. Axis F Step 2 (sublane) carries a known performance cost and requires an explicit
   cost/benefit measurement before adoption as a default. See `01_CRITICAL_REVIEW.md` R-3.
5. Advancing an axis obliges an **ablation**: the milestone reports results with the new
   step and with the previous one, on identical seeds.

---

## 6. The vertical-slice rule

**This is the project's most important operating constraint**, and it exists specifically to
counter the failure mode identified in `01_CRITICAL_REVIEW.md` R-1.

> Every milestone must produce a working end-to-end system that yields a result. No
> milestone may deliver only a layer, a module, an abstraction, or a set of interfaces.

Concretely, a milestone is complete only when a single command runs the full path —
network → demand → simulation → observation → estimation → controller → action → metrics →
recorded trace — and produces an artifact a person can look at.

**Corollaries:**

- **No speculative abstraction.** An interface may not be introduced to support a second
  implementation that does not yet exist. Two exceptions, both because the insurance is
  cheap and the retrofit is expensive:
  1. the **backend adapter boundary** (`D-001`, `D-002`), and
  2. the **observation interface**, which must admit a pixel-derived detection stream
     without changes to downstream layers (`D-005`).
  Any third exception requires a decision register entry.
- **No empty directories.** A package is created when code goes into it.
- **Working beats complete.** A crude version of every layer beats a polished version of
  one layer, every time.
- **Refactoring is allowed, deferred design is not.** Building the simple thing and
  reshaping it later is the intended workflow. Building the general thing first is not.

---

## 7. Scope

### 7.1 In scope

**Simulation and domain**
- SUMO as the sole simulation backend, wrapped by a project-owned adapter.
- Adapter transport abstraction supporting both TraCI and LibSUMO (`D-002`).
- A canonical domain model as a **read-only projection plus command surface** — deliberately
  smaller than SUMO's own model (`D-003`, and R-2 of the critical review).
- Synthetic network generation: isolated intersection, coupled pair, corridor, grids.
- Seeded, reproducible demand generation.

**Sensing, estimation, control**
- Parametric sensor models: field of view, range, detection probability, position and speed
  noise, sampling rate, latency.
- The truth / observation / estimate separation, enforced in the type system.
- The oracle condition as a permanent experimental arm.
- Controllers: Webster fixed-time, actuated (ours and SUMO's), Max-Pressure, MPC, RL,
  coordinated/network-level.
- A single canonical action interface with an explicit constraint layer.

**Experimentation**
- Configuration-driven experiments with full run manifests.
- Batch execution across seeds and parameter sweeps.
- Pinned metric definitions, warm-up handling, paired comparison, uncertainty reporting.
- Scenario splits for training, validation, and test where learned methods are involved.
- Ablation as a first-class experiment type.

**Visualization**
- Record-then-replay architecture: simulations write traces, the renderer consumes them
  (`D-009`).
- 2D renderer with research overlays: ground truth, sensor observations, estimated state,
  queues, phases, and controller decisions.

**Documentation**
- Decision register, methodology document, per-milestone results documents with limitations.

### 7.2 Explicitly out of scope

Recorded so that no agent adds them and no reviewer expects them.

| Out of scope | Reason |
| --- | --- |
| **Building a microsimulator** | SUMO does this. See C-1. |
| **Implementing car-following, lane-changing, or acceleration models** | Configuration of SUMO models, not project code. |
| **Computer vision on pixels** | Deferred to an optional track. Extension point reserved. See `D-005`. |
| **Real-time deployment or hardware integration** | Not a prototype project at this stage. |
| **Production traffic management system features** | No operator UI, no alarms, no SCADA, no fault tolerance. |
| **Calibration against real Bogotá measurements** | Not required by the deliverable. See §2.1 Consequence 5. |
| **Pedestrian modelling beyond minimum-green floors** | Deferred. See O-4. |
| **Public transport, incidents, road works** | Deferred. Urban-realism items with no current experiment needing them. |
| **Emissions and fuel consumption metrics** | Available in SUMO; add only if an experiment asks. |
| **Multi-backend support** | One backend. Boundary kept, second implementation not built. See R-2. |
| **A backend benchmark against CityFlow** | Deferred with an explicit revisit trigger. See O-1, `D-001`. |
| **Route choice / dynamic re-routing** | Deferred; it confounds attribution of control effects. See G-11. |

### 7.3 Deferred with revisit triggers

Not out of scope forever — waiting on a condition.

| Item | Revisit when |
| --- | --- |
| Computer vision track | The core platform reaches M5 and the owner wants a second track. |
| Backend benchmark / CityFlow | Wall-clock is a *measured* binding constraint and LibSUMO has already been adopted. |
| Sublane / motorcycle filtering as default | M4 measures its cost and its effect on conclusions. |
| Pedestrian phases | An experiment requires pedestrian delay as an objective term. |
| Real Bogotá topology | M5 grid results are solid and OSM import is the natural next step. |
| Route choice | Isolated and corridor control results are established. |
| Emissions metrics | An objective function includes an environmental term. |

---

## 8. Quality bar, calibrated by area

Not everything deserves the same rigor. Applying uniform standards to a learning project
wastes effort on the parts nobody will examine and under-invests in the parts that carry
the whole claim.

| Area | Bar | Rationale |
| --- | --- | --- |
| **Experimental methodology** | **Highest.** No shortcuts. | It is what the deliverable is made of. Retrofitting is expensive; a flawed methodology invalidates results retroactively. |
| **Truth/observation separation** | **Highest.** Type-enforced. | A single leak silently invalidates every sensing result. See R-5. |
| **Reproducibility** | **Highest.** Manifest on every run. | Success criterion S1; cheap when built in, near-impossible to add later. |
| **Domain model / adapter** | **High.** Well-tested, deliberately small. | Everything depends on it. But small: R-2. |
| **Controllers** | **High** for baselines, **medium** for experimental ones. | A buggy baseline manufactures fake improvement. An experimental controller that underperforms is a result. |
| **Visualization** | **Medium-high polish, low correctness-criticality.** | Primary deliverable for the portfolio (§2.1), but a rendering bug does not corrupt a result. |
| **Simulation realism** | **Medium, and explicitly bounded.** | Realism serves the questions. Stated as a limitation, not chased. |
| **Performance** | **Low until measured.** | Principle 8. LibSUMO is the first remedy, and only when wall-clock actually binds. |
| **Production concerns** | **None.** No auth, no deployment, no scaling, no SLAs. | Out of scope. |

---

## 9. Operating model

The project owner acts as principal investigator and reviewer. A frontier model acts as
research architect and orchestrator, producing designs, contracts, and tickets. Less capable
agents implement against frozen contracts.

The three rules that make this work, derived from R-4:

1. **Contract before ticket.** Interfaces, data schemas, and acceptance tests exist before
   an implementation ticket is written.
2. **Escalate, do not guess.** A ticket that requires an undocumented judgement call must be
   returned, not resolved by the implementing agent. This is the operational form of
   `00_RESEARCH_SPECIFICATION.md` §48.14.
3. **Explicit non-goals per ticket.** Every ticket states what it must *not* do, because
   an agent with spare capacity will otherwise add abstractions nobody asked for.

Agent archetypes and the ticket template are specified in `08_AGENT_HANDOFF_PROTOCOL.md`.

---

## 10. Document map

| Document | Role | Status |
| --- | --- | --- |
| `00_RESEARCH_SPECIFICATION.md` | Original vision and research philosophy. Historical, partially superseded. | v0.1, frozen |
| `01_CRITICAL_REVIEW.md` | Adversarial reading of the specification. | v1.0, complete |
| `02_PROJECT_CHARTER.md` | **This document.** Deliverable, scope, success criteria. Governs. | v1.0, active |
| `03_ROADMAP.md` | Vertical-slice milestones and exit criteria. | v1.0, active |
| `04_DECISION_REGISTER.md` | Every decision: settled, proposed, open, deferred. | v1.0, living |
| `05_DOMAIN_MODEL.md` | Canonical entities, schemas, SUMO mapping. | v1.0, active |
| `06_ARCHITECTURE.md` | Layers, boundaries, adapter design, extension points. | v1.0, active |
| `07_EXPERIMENT_METHODOLOGY.md` | Metrics, seeds, statistics, validity checks. | v1.0, active |
| `08_AGENT_HANDOFF_PROTOCOL.md` | Agent archetypes, ticket template, definition of done. | v1.0, active |
| ~~`09_GLOSSARY.md`~~ | **Not planned.** The canonical ↔ SUMO mapping lives in `05_DOMAIN_MODEL.md` §7; a separate glossary would be a second place to drift. | dropped |

---

## 11. Amendment

This charter changes when the deliverable changes, when a success criterion proves
unmeasurable, or when a scope decision is reversed. Amendments are recorded as decision
register entries and the version here is incremented. The charter is not amended by
implication — a milestone that quietly exceeds scope is a defect, not an amendment.
