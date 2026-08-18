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

**This is wrong, and was corrected on 2026-08-18.** The original text claimed detectors are
"not a different queue definition; a richer measurement surface over the same halt threshold."

Measured (`spikes/M0_verify/verify.py`, section B): on one lane over 600 s with the signal
running normally, `getLastStepHaltingNumber` and `getJamLengthVehicle` **disagreed on 230 of
600 steps**, with the jam length consistently higher. Jam length applies SUMO's own jam
criterion — a gap threshold plus a speed threshold — and therefore counts slow-moving vehicles
that the halting counter, at a strict 0.1 m/s, excludes.

They coincide only in a fully saturated queue, which is why the first pass concluded they were
the same: it was measured under an all-red signal, where every definition of "queued" agrees
trivially.

**Consequence.** Jam length is *not* a drop-in source for `D-025`'s queue. It remains a
candidate for the secondary queue-length-in-metres metric at M4, but as a distinct measure that
must be reported under its own name.

### 1.3 The 1 s duration condition

The `D-025` queue definition is therefore **not** SUMO's native halting counter.
The ≥1 s continuous-halting condition must be computed by us.

### 1.4 Queue length in metres

SUMO exposes `getJamLengthMeters` on lane-area detectors, but per §1.2 that is the *jam*
criterion, not the halting criterion. Using it as "queue length in metres" would silently pair a
metres metric to a different queue definition than the vehicles metric beside it.

If we compute queue length ourselves from vehicle states, vehicle length and gap assumptions
matter; the native halting counter alone does not encode them. Which of the two we adopt at M4
is an open question, not settled here.

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

For repeated flows, `period="exp(X)"` means exponentially distributed gaps, i.e. a Poisson
process at **rate X insertions per second** — X is a rate, not a period.

**Verified empirically** (`spikes/M0_verify/verify.py`, section A), which the ticket required
rather than assumed: `exp(0.2)` over 3600 s inserted 717 vehicles with a mean headway of
4.990 s, an implied rate of 0.200 veh/s, and a headway standard deviation of 5.007 s. Standard
deviation equal to the mean is the signature of the exponential distribution.

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

**Provenance, corrected 2026-08-18.** The first pass of this document answered most of §1 from
documentation. T0.5's ticket existed precisely because `D-025` and `D-022` had already *assumed*
these semantics and needed empirical confirmation, and documentation is what we already had.

| Claim | Evidence |
| --- | --- |
| §1.1 halting counter is speed-threshold only, no duration | SUMO docs; consistent with T0.1's independent reading of sumo-rl source |
| §1.2 jam length ≠ halting counter | **Measured** — 230/600 steps disagree |
| §1.3 the 1 s condition is ours to compute | Follows from §1.1 |
| §1.4 metres metric | **Open** — depends on §1.2, deferred to M4 |
| §2.2 `exp(X)` is a rate, arrivals are Poisson | **Measured** — 717 arrivals, rate 0.200/s, stdev = mean |
| §2.3 three-way trip accounting is separable | **Measured** — direct `tripinfo` output |
| §2.1 `jtrrouter` sinks and `--max-edges-factor` | Documentation only. **Still unverified**, and T1.5 depends on it. |

The one remaining documentation-only claim that a ticket depends on is `jtrrouter`'s behaviour.
T1.5 should treat it as unconfirmed and escalate if it does not hold.
