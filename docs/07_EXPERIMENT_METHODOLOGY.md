# Experiment Methodology

**Status:** Active. Binding on every experiment.
**Version:** 1.0
**Governed by:** `02_PROJECT_CHARTER.md`
**Implements:** `D-006`, `D-008`, `D-017`, `D-018`, `D-022`, `D-025`, `D-032`

---

## 1. Why this document is binding

Per `02_PROJECT_CHARTER.md` §8, methodology carries the **highest** quality bar in the
project — higher than the domain model, higher than the controllers. Two reasons:

1. It is what the deliverable is made of. A learning-and-portfolio project is judged on
   whether its results mean anything, and correct methodology is the strongest available
   signal of that.
2. It is the only layer where a mistake is **retroactive**. A controller bug produces a bad
   controller. A methodology bug produces a folder of results that were never valid, and you
   usually find out long after the runs are gone.

Nothing here is decided per-experiment. Every experiment inherits all of it. An experiment
that needs to deviate records the deviation and its justification in its results document —
it does not quietly adopt a different rule.

---

## 2. Metric definitions

Every metric here is pinned. **Every reported number names its metric and its unit.** A
figure axis labelled "delay" without qualification is a defect, because delay has at least
three incompatible definitions that can differ by a factor of two on the same run.

### 2.1 Vehicle-level

| Metric | Unit | Definition |
| --- | --- | --- |
| **Delay** *(primary metric)* | s | **Time loss plus insertion delay** (`D-006`, amended 2026-10-07). Time loss: realised travel time minus the time the same route would take at the vehicle's desired speed — SUMO's `timeLoss`, including acceleration and deceleration losses. Insertion delay: time spent waiting to enter the network — SUMO's `departDelay`. Both from tripinfo (`D-035`); always also reported separately. |
| **Travel time** | s | Departure to arrival, where arrival is a boundary sink **or** a mid-link destination (`D-022`). |
| **Waiting time** | s | Cumulative time with speed below 0.1 m/s — SUMO's tripinfo `waitingTime`, which leaves out the insertion step (time loss includes it; measured 2026-10-07). |
| **Stops** | count | Number of times the vehicle halts (0.1 m/s threshold) — SUMO's tripinfo `waitingCount`. **Amended 2026-10-07:** an insertion at standstill counts as a stop when the vehicle is still halted at its first move step; neither tripinfo nor `TrueState` can separate that case, so the earlier "excluding the initial insertion" was unmeasurable. Rare below capacity (0 of 384 insertions at 65 %); 24 of 758 under heavy overload were near-standstill. |

**Secondary, reported where relevant, never as the headline:** stopped delay (waiting time),
and an HCM-style control delay approximation at intersection level.

### 2.2 Lane and intersection level

| Metric | Unit | Definition |
| --- | --- | --- |
| **Queue** *(primary)* | vehicles | Count of vehicles halting below 0.1 m/s continuously for ≥ 1 s. `D-025`. |
| **Queue length** | m | Distance from the stop line to the last queued vehicle. Secondary; reported from M4 where the car/motorcycle divergence becomes interesting. |
| **Max queue** | vehicles | Maximum of the above over the measurement window. |
| **Approach delay** | s | Mean time loss of vehicles whose route used that approach. |
| **Signal utilisation** | fraction | Green time during which the served movements discharged at ≥ 80% of saturation flow. Diagnostic; distinguishes "green given" from "green used". |

### 2.3 Network level

| Metric | Unit | Definition |
| --- | --- | --- |
| **Throughput** | veh/h | Completed trips per hour of measurement window. Completion means boundary sink **or** mid-link arrival (`D-022`). |
| **Mean delay** | s/veh | Mean primary delay over vehicles that completed within the window; its two components reported beside it. |
| **Total time loss** | veh·h | Sum over all vehicles including those still in-network, using their accumulated loss so far. Reported alongside the mean because the mean alone hides unserved demand. |
| **Trip completion rate** | fraction | Completed / (completed + still in-network). §4. |

**Where each metric comes from (`D-035`).** Vehicle-level metrics and every network metric
built from completed trips come from SUMO's tripinfo, parsed by the backend at run end and
filtered to the measurement window. Lane-level metrics and total time loss of vehicles still
in-network accumulate from `TrueState` every step. **Signal utilisation** needs decoded signal
state (T1.14) and saturation flow (T1.5); it is not part of T1.8.

### 2.4 Separability by vehicle type

Every vehicle-level and network-level metric is computed **per vehicle type as well as in
aggregate**, from M1, before motorcycles exist. Retrofitting separability after the
aggregation code is written is far more annoying than building it in.

This is not bookkeeping. At M4 the question *"does this controller improve the aggregate by
systematically penalising motorcycles?"* is answerable only if the split was recorded all
along, and it is exactly the kind of finding the project exists to produce.

### 2.5 One definition, one implementation

Metrics live in `metrics/` and are imported. A metric recomputed locally in a controller, an
analysis script, or a notebook is a review defect
(`08_AGENT_HANDOFF_PROTOCOL.md` §6 item 5). Two implementations of "queue" that agree today
will disagree after the next change to either.

---

## 3. Run structure

### 3.1 Three phases

Per `D-018`, every run has three phases, all recorded in the manifest.

| Phase | Metrics | Purpose |
| --- | --- | --- |
| **Warm-up** | Discarded | Fill the network from empty to a representative state |
| **Measurement** | Collected | The window results are computed over |
| **Cool-down** | Not collected | Let in-flight vehicles complete, so travel-time samples exist |

### 3.2 Determining the warm-up length

Not guessed. Two steps:

1. **Automatic:** MSER-5 applied to the primary metric's time series — the standard
   truncation heuristic, which picks the truncation point minimising the standard error of
   the remaining mean.
2. **Visual confirmation:** a running-average plot for at least one run per demand level,
   included in the milestone's results document the first time a scenario is used.

A sensible starting prior, before measurement, is several times the free-flow traversal time
of the longest route. It is a starting point for the search, not the answer.

**Warm-up length is per scenario and per demand level**, not global. Congested scenarios take
much longer to reach a representative state, and using one global value systematically
under-warms exactly the runs where warm-up matters most.

### 3.3 Snapshots

Per `D-032`, warm-up from empty is *how a snapshot is produced*; a snapshot is *how warm-up is
avoided* on every later run. Warm up once per (network, demand level, seed), save, reuse.

**Self warm-up is the default** — each arm warms up under its own controller, which answers
"what steady state does each controller induce". **Neutral snapshots** — all arms load one
state generated under Webster fixed-time — answer "given this state, who recovers best" and
are the right design for shock and incident experiments.

Whichever an experiment uses, it is the same across all arms and it is in the manifest.
Mixing them within one comparison invalidates it.

---

## 4. Trip accounting

Per `D-022`, a vehicle leaves the simulation in three ways, and they mean different things:

| Exit | Meaning | Counts as |
| --- | --- | --- |
| Boundary sink | Completed its trip through the network | Served |
| Mid-link destination (attrition) | Completed its trip; arrived locally | Served |
| Still in-network at end of measurement | Did not complete | **Unserved** |

All three are counted and reported for every run. **The trip completion rate accompanies
every travel-time metric**, because travel-time means are computed over completed trips only,
and a controller that lets vehicles queue indefinitely has its slowest vehicles excluded from
its own average. Without the completion rate next to it, that looks like good performance.

This is the failure mode `01_CRITICAL_REVIEW.md` G-4 identifies as a well-known way to
accidentally prove a bad controller is good.

---

## 5. The validity gate

Per `D-008`, a run is **invalid** — not merely noisy — if any of the following occurred:

| Condition | Why it invalidates |
| --- | --- |
| Any teleport | Teleporting deletes the congestion being measured, and deletes more of it for worse controllers |
| Insertion loss above 1 % (`D-008`) | The applied demand no longer matches the configured demand, so the experiment measures something other than what it claims |
| Gridlock detected | Metrics past that point are meaningless |
| Snapshot/network hash mismatch | The run did not start from the state it claims |

Invalid runs are **written with their invalidity flag, not dropped**. A missing run and an
invalid run are different facts and the analysis must distinguish them. Silently dropping
invalid runs biases a comparison toward whichever controller gridlocks less — which is
usually the answer you were trying to measure.

**Any invalid run in a reported comparison must be disclosed**, with its count and cause, in
the results document.

---

## 6. Randomness

### 6.1 Independent seed streams

Per `D-017`, each source of randomness gets its own stream, all derived from one master seed
by a documented scheme:

| Stream | Controls |
| --- | --- |
| `demand` | Arrival times, turn choices, attrition draws, vehicle type assignment |
| `driver` | SUMO driver imperfection (`sigma`), desired-speed deviation |
| `sensor` | Detection dropouts, position and speed noise |
| `estimator` | Any stochastic estimation |
| `policy` | RL exploration, or any stochastic controller |

Independence is what makes ablations interpretable: holding `demand` fixed while varying
`sensor` isolates the sensing effect. A single global seed makes that impossible.

### 6.2 Common random numbers

**The same master seed produces the same vehicle arrivals regardless of which controller
runs.** Comparisons are paired: arm A and arm B see identical demand realisations.

This is variance reduction, not bookkeeping. Comparing arms on independent realisations means
the arrival noise appears in both samples and must be averaged away; comparing them on the
same realisations means it cancels in the per-seed difference. The same conclusion typically
needs several times fewer runs.

### 6.3 The replication unit is the run, not the vehicle

**This is the easiest way to produce a confidently wrong confidence interval in this project.**

A single run yields thousands of per-vehicle delay samples. They are not independent —
vehicles in the same run share the same arrivals, the same signals, the same queues. Treating
them as independent samples inflates the effective sample size by three orders of magnitude
and produces intervals so tight that every difference looks significant.

The unit of analysis is **the run**. One run contributes **one number** per metric (its
within-run mean, or whatever summary the metric defines). Statistics are computed across
runs. Within-run distributions may be reported descriptively, never as the basis of an
interval or a test.

---

## 7. Statistics

### 7.1 Paired differences

For each seed *i*, compute the per-seed difference `d_i = m(A, i) − m(B, i)`. Report the mean
of `d`, its confidence interval, and the relative effect. Never the difference of two
independently-computed means.

### 7.2 Confidence intervals

**Bootstrap, BCa, 10,000 resamples**, over the paired differences.

Delay and queue distributions are skewed and heavy-tailed, and their run-level means are only
approximately normal at the sample sizes used here. With n ≥ 30 a paired t-interval is
usually adequate, but the bootstrap costs nothing on 30–100 numbers and does not require the
assumption. Use it.

### 7.3 Effect sizes

Report **relative** effect with its interval, e.g. *"time loss reduced 14.2% (95% CI:
9.1–19.0%)"*. Absolute seconds are not comparable across demand levels or network sizes, and
the whole point is to compare across them.

### 7.4 Replication count

Derived, not chosen. Picking 100 because it is round is how you end up over-running cheap
comparisons and under-running expensive ones.

1. Declare the **minimum detectable effect** δ — the smallest difference worth claiming. A
   defensible default is 5% relative.
2. Run a **pilot batch** of ~10 paired seeds. Estimate `σ_d`, the standard deviation of the
   paired difference.
3. For 80% power at the 5% level:

   ```
   n ≈ 7.85 · (σ_d / δ)²
   ```

4. Report both n and δ. This is what makes a null result readable as *"no effect larger than
   δ"* rather than as an absence of evidence.

### 7.5 Multiple comparisons

Declare the **family** — the set of comparisons that together constitute one claim — before
running. Apply **Holm–Bonferroni** within the family.

Five controllers across four demand regimes and three sensor conditions is 60 comparisons;
roughly three will look significant at the 5% level by chance alone. Reporting the three
without correction is the standard way to manufacture a finding.

### 7.6 No silent caps

If an analysis bounds coverage — top-N scenarios, a subsampled sweep, dropped arms — the
omission is stated. Silent truncation reads as "we covered everything" when it did not.

---

## 8. Experiment types

| Type | Question | Requirements |
| --- | --- | --- |
| **Comparison** | Does controller A beat controller B? | Paired seeds, full mandatory baseline set (`D-013`), oracle arm if sensing is involved |
| **Ablation** | Does this added complexity earn its cost? | Identical seeds with and without; report the difference **and** the wall-clock cost. `00_RESEARCH_SPECIFICATION.md` §32 |
| **Sensitivity** | How does performance depend on parameter p? | Sweep p, hold all else fixed, same seeds at every level |
| **Sweep** | How does the ranking change across regimes? | Full grid; declare the comparison family before running |
| **Validation** | Does the simulation behave plausibly? | Qualitative expectations stated in advance. `00_RESEARCH_SPECIFICATION.md` §40 |

### 8.1 The oracle arm is mandatory

Per `00_RESEARCH_SPECIFICATION.md` §23, any experiment involving imperfect sensing carries its
oracle counterpart. Without it, a controller that underperforms cannot be attributed: is it
the control policy, the sensor model, or the estimator? The oracle arm is what turns "it
failed" into a diagnosis.

Architecturally this is free — the oracle is a sensor, not a code path
(`06_ARCHITECTURE.md` §4.1).

### 8.2 The mandatory baseline set

Per `D-013`, no advanced controller is reported without Webster fixed-time, our actuated,
SUMO gap-actuated, and Max-Pressure on identical seeds. Coordinated fixed-time (green wave)
joins the set from M5b.

Webster matters as much as Max-Pressure and for the opposite reason: a badly tuned baseline
manufactures improvement out of nothing.

---

## 9. Scenario splits

Per `00_RESEARCH_SPECIFICATION.md` §31, and applicable **only where something is tuned or
learned**:

| Split | Used for |
| --- | --- |
| **Training** | Developing and tuning |
| **Validation** | Selecting among variants |
| **Test** | Held out; touched once, at final evaluation |

Scenarios differ by demand level and profile, motorcycle ratio, network geometry, sensor
configuration, and seed range. **Seed ranges must not overlap across splits.**

For fixed-time and actuated, splits are ceremonial — nothing is fit. They become real at M6
(MPC weight and horizon tuning) and load-bearing at M7 (RL). At M7 a test scenario touched
during development is contaminated and must be replaced, not reused.

---

## 10. Results document template

Every milestone produces one. Sections are not optional.

```markdown
# M<n> Results — <title>

## Question
The specific question this milestone answers. One sentence.

## Setup
Network, demand, sensing, controllers, Δt per controller, warm-up design,
seed count, and the minimum detectable effect.

## Validity
Invalid runs by cause. Trip completion rates. Insertion-failure counts.
Report even when all zero — "we checked and it was clean" is information.

## Results
Figures with confidence intervals. Effect sizes with intervals, not point
estimates. The comparison family and the correction applied.

## Interpretation
What this means. What it does not mean.

## Limitations
The regime the conclusions hold in, and the ones they do not. At minimum:
stationary demand, fixed routes, no calibration against real data.

## Reproduction
The exact command and config that regenerates every figure.
```

**Null and negative results are reported with the same prominence as positive ones.** Per
`02_PROJECT_CHARTER.md` §2.1, "we measured it and it did not matter, here is the evidence" is
a deliverable.

---

## 11. Checklist: how this project would produce a wrong result

Ordered by likelihood. Run through it before reporting anything.

| # | Failure | Guard |
| --- | --- | --- |
| 1 | Vehicles treated as independent samples | §6.3 — the replication unit is the run |
| 2 | Teleporting left enabled | `D-008` startup assertion |
| 3 | Unfinished trips excluded, favouring controllers that queue | §4 — trip completion rate reported alongside |
| 4 | Metrics computed over warm-up | §3.1 — three phases, MSER-5 truncation |
| 5 | Arms compared on different demand realisations | §6.2 — common random numbers |
| 6 | Fixed-time baseline arbitrarily tuned | `D-013` — Webster-computed |
| 7 | "Delay" reported without saying which definition | §2 — every number names its metric |
| 8 | Significance claimed across 60 uncorrected comparisons | §7.5 — declared family, Holm–Bonferroni |
| 9 | Invalid runs silently dropped | §5 — flagged and disclosed |
| 10 | Controller received information its sensors do not provide | `06_ARCHITECTURE.md` §4 — structurally impossible |
| 11 | Snapshot generated under one controller reused by all | `D-032` — same design across arms, in the manifest |
| 12 | Config drifted from the code that ran it | §7 of `06_ARCHITECTURE.md` — manifest with config hash and code version |

---

## 12. Amendment

Changes to this document invalidate comparability with earlier results. An amendment
therefore states explicitly whether prior results remain comparable, and if not, which ones
must be re-run. Recorded in `04_DECISION_REGISTER.md`.
