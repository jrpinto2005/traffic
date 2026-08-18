# M0 SUMO Semantics — queue and demand

**Ticket:** `tickets/M0/T0.5_sumo_semantics.md` · **Status:** complete

---

## 1. Queue semantics (`D-025`)

### 1.1 `getLastStepHaltingNumber`

- SUMO defines a halting vehicle as one with speed below **0.1 m/s**.
- `traci.lane.getLastStepHaltingNumber(lane_id)` returns the number of such vehicles on the lane in the last step.
- It applies **no duration condition**.

### 1.2 Lane-area detectors

Lane-area detectors report the same halting criterion, but more:

- `last step halting vehicles number`
- `last step jam length in vehicles`
- `last step jam length in meters`
- occupancy

So they are not a different queue definition; they are a richer measurement surface over the same halt threshold.

### 1.3 The 1 s duration condition

The `D-025` queue definition is therefore **not** SUMO's native halting counter.
The ≥1 s continuous-halting condition must be computed by us.

### 1.4 Queue length in metres

SUMO exposes queue length in metres as **jam length** on lane-area detectors (`getJamLengthMeters`).

If we compute queue length ourselves from vehicle states, then vehicle length and gap assumptions matter; the native halting counter alone does not encode them.

**Decision status:** `D-025` confirmed as written, with the intentional note that our queue is a stricter version than SUMO's native halting count.

---

## 2. Demand semantics (`D-022`)

### 2.1 `jtrrouter`

`jtrrouter` builds routes from:

- a network
- turn-ratio definitions
- flow definitions

It also supports sink edges and a route-length guard:

- `--sinks` or sink entries in the turn file declare where vehicles may exit
- `--max-edges-factor` caps how long a generated route may become

### 2.2 Random flows

For repeated flows, `period="exp(X)"` means exponentially distributed gaps.
That is a Poisson process with expected value **X insertions per second**.

### 2.3 `departPos` and `arrivalPos`

Both work on vehicles:

- `departPos` can place a vehicle at an interior position when it enters
- `arrivalPos` can remove it at an interior position on its final edge

The spike experiment showed this directly:

- a boundary trip ended at `arrivalPos="189.60"`
- a mid-link trip ended at `arrivalPos="100.00"`
- an unfinished vehicle written with `--tripinfo-output.write-unfinished true` emitted `arrival="-1.00"`, `arrivalLane=""`, `arrivalPos="-1.00"`, `vaporized="end"`

That means the three-way accounting is separable in tripinfo output, provided unfinished trips are written.

**Decision status:** `D-022` confirmed as written.

---

## 3. Evidence notes

- The queue result is backed by SUMO's TraCI docs plus the lane-area detector docs.
- The demand result was checked against the SUMO routing docs and by direct run output on the reference scenario.
