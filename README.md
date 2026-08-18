# Traffic Control Research Lab

A research platform for **adaptive traffic signal control**, built to study how control
strategies behave as traffic, sensing, and network conditions get progressively more
realistic — with motorcycle-heavy traffic as a first-class concern rather than an afterthought.

> **The simulator is a scientific instrument, not the final product.**

---

## Status: pre-implementation

There is no code yet. This repository currently contains the research specification, the
architecture, and the ticket set for the first two milestones.

| | |
| --- | --- |
| **Now** | M0 — prior-art review, SUMO capability spikes, performance baseline |
| **Next** | M1 — single intersection, oracle observation, honest baselines |
| **Decisions settled** | 29 of 32 · [`04_DECISION_REGISTER.md`](04_DECISION_REGISTER.md) |
| **Open decisions** | D-021 (estimation, blocks M3) · D-024 (objective, blocks M6) · D-030 (trace format, blocks M2) |

### ▸ Headline result

*Reserved for M1's exit artifact: mean delay vs. demand for four controllers, ≥30 paired
seeds, 95% confidence intervals. This space stays empty until there is a real result to put
in it — a placeholder chart would be worse than an honest gap.*

---

## What this is

Six components, deliberately separated so that a failure can be attributed to one of them:

1. **Simulation** — SUMO as the backend, behind a project-owned adapter. We do not build a
   microsimulator; SUMO already is one.
2. **Sensing** — synthetic cameras that deliberately withhold information from controllers.
3. **Estimation** — what the control system *believes* is happening, distinct from what is.
4. **Control** — from Webster fixed-time and Max-Pressure through MPC to reinforcement
   learning.
5. **Experimentation** — every result reproducible from a configuration file and a seed.
6. **Visualization** — 2D replay that shows not just traffic, but what the controller
   believed and why it acted.

### The idea the architecture is built around

**Controllers never see true state.** Not "should not" — *cannot*. The oracle condition is
implemented as a *sensor* that returns perfect observations, not as a bypass, so a controller
receives estimated state in every experimental arm and `TrueState` is never in scope in the
control package at all. There is no path to leak through because there is no path.

That is what makes it possible to ask the questions this project exists for: when a controller
underperforms, is it the control policy, the sensor, or the estimator?

---

## Reading order

The documents build on each other. Read them in this order; each says what it supersedes.

| # | Document | What it answers |
| --- | --- | --- |
| 00 | [Research Specification](00_RESEARCH_SPECIFICATION.md) | The original vision. Partially superseded — read its header first. |
| 01 | [Critical Review](01_CRITICAL_REVIEW.md) | What in that vision was contradictory, missing, or over-scoped. |
| 02 | [Project Charter](02_PROJECT_CHARTER.md) | **Governs scope.** Deliverable, in/out, success criteria. |
| 03 | [Roadmap](03_ROADMAP.md) | Milestones, each a vertical slice exiting on a result. |
| 04 | [Decision Register](04_DECISION_REGISTER.md) | Every decision: settled, open, deferred, with revisit triggers. |
| 05 | [Domain Model](05_DOMAIN_MODEL.md) | The canonical vocabulary and its mapping to SUMO. |
| 06 | [Architecture](06_ARCHITECTURE.md) | Layers, the three seams, the observation boundary. |
| 07 | [Experiment Methodology](07_EXPERIMENT_METHODOLOGY.md) | Metrics, seeds, statistics, validity. **Binding on every experiment.** |
| 08 | [Agent Handoff Protocol](08_AGENT_HANDOFF_PROTOCOL.md) | How work is delegated without silently losing methodology. |

**In a hurry?** Read 02 for what this is, then 04's index for what has been decided.

---

## Repository layout

```text
00–08_*.md          the documents above
tickets/M0/         spike tickets — prior art, SUMO semantics, performance, footguns
tickets/M1/         builder tickets — the founding vertical slice
research/           spike findings and per-milestone results documents
spikes/             throwaway code from spikes; never imported by traffic_lab
traffic_lab/        the package (does not exist yet — created by T1.1)
configs/            experiment configurations
```

---

## Getting started

Not yet runnable. Once ticket [T0.0](tickets/M0/T0.0_environment.md) lands:

```bash
brew tap dlr-ts/sumo && brew install sumo
curl -LsSf https://astral.sh/uv/install.sh | sh
export SUMO_HOME="$(brew --prefix sumo)/share/sumo"
python -c "import traci, libsumo, sumolib; print('ok')"
uv sync
```

`libsumo` is not optional — [D-002](04_DECISION_REGISTER.md#d-002) depends on it for roughly
a 10× speedup on the simulation call path, which is what makes large seed sweeps and RL
training affordable.

---

## Principles that are not negotiable

Everything else is a decision with a revisit trigger. These are the constraints the project
would stop being research without:

1. **Truth, observation, and estimate are separate**, and the separation is structural rather
   than disciplinary.
2. **The oracle arm always runs** alongside any sensed arm, so failures can be attributed.
3. **Baselines before advanced methods.** No controller is reported without Webster
   fixed-time, actuated, and Max-Pressure on identical seeds. A badly tuned baseline
   manufactures improvement out of nothing.
4. **Complexity must be earned** — by an experiment that needs it, not by realism being
   available.
5. **Every result is reproducible** from a configuration, a seed, and a recorded manifest.
6. **Null results are deliverables.** "We measured it and it did not matter, here is the
   evidence" is a finding.

---

## Scope boundaries worth knowing up front

This project does **not** build a microsimulator, does not process camera pixels (a reserved
extension point, not a current goal), and does not calibrate against real Bogotá measurements.
Every claim it makes is about the simulated environment. See
[charter §7.2](02_PROJECT_CHARTER.md) for the full list and the reasoning.
