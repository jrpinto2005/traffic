# M0 Footguns — teleporting, insertion loss, gridlock

**Ticket:** `tickets/M0/T0.4_footguns.md` · **Status:** complete

---

## Setup

The reference network from `spikes/M0_reference/` was overloaded with eight constant flows at
3600 veh/h each and the signal was held at all-red to make the failure modes observable.

Run window: 1200 s.

---

## 1. Teleporting

### How it was induced

Force the intersection to stay all-red while demand continues to arrive.
With `--time-to-teleport 300`, SUMO eventually relocates vehicles that have been stuck too long.

### Signature in output

- `simulation.getEndingTeleportNumber()` starts increasing after the timeout
- `tripinfo` shows a lower `timeLoss` than the no-teleport run
- unfinished vehicles still appear with `arrival="-1.00"` / `vaporized="end"`

### Distortion — corrected 2026-08-18

The original measurement here reported an 11.1% reduction in mean `timeLoss` under the all-red
stress case. **That number should not be cited.** It was computed over the 224 of 9600 configured
vehicles that managed to depart — a 2.3% completion rate, in a run this same document declares
invalid one section later by its own insertion-loss rule. It demonstrates that teleporting
exists; it does not measure what teleporting does to an experiment we would otherwise believe.

Re-measured at realistic overload with the **signal running normally**
(`spikes/M0_verify/verify.py`, section D), sweeping demand on an isolated intersection:

| Demand / approach | Teleports | Finished / loaded | Mean `timeLoss` on | off | Distortion |
| --- | --- | --- | --- | --- | --- |
| 1080 veh/h | 0 | 4187 / 4239 | 21.7 s | 21.7 s | 0.0% |
| 1440 veh/h | 0 | 5570 / 5679 | 26.0 s | 26.0 s | 0.0% |
| 1800 veh/h | 0 | 6671 / 7128 | 54.6 s | 54.6 s | 0.0% |
| 2160 veh/h | 0 | 6736 / 8627 | 60.0 s | 60.0 s | 0.0% |

**No teleports occur at any level**, including one where 22% of configured demand never enters.

The reason is structural: teleporting requires a vehicle to be stuck *inside* the network. On an
isolated intersection with ~190 m approaches, a queue that exceeds the approach spills out of
the network entirely, so the overload is absorbed as **insertion loss** before any vehicle can
be trapped long enough to teleport.

### What this changes

**Insertion loss, not teleporting, is the dominant validity threat at M1.** At 2160 veh/h the
applied demand was 78% of the configured demand, and mean `timeLoss` rose only from 21.7 s to
60.0 s — because the vehicles that would have suffered the worst delay never entered at all.
That is precisely the bias `D-008` exists to catch, and it happens silently with teleporting
already disabled.

Teleporting becomes the dominant threat at **M5**, where a corridor or grid can trap a vehicle
between two signals with nowhere to spill. The check stays mandatory from M1 — it is nearly
free — but M1 results will be threatened by the insertion counter, not the teleport counter.

### Detection rule

Treat any non-zero ending teleport count as invalid for analysis, and record the count per run.

---

## 2. Insertion loss

### How it was induced

Same all-red overload. The network cannot clear vehicles, so departures stall and a large share of the configured demand never enters the network during the observation window.

### Signature in output

- departed count far below configured demand
- many vehicles remain pending at end of run
- `tripinfo` only covers the vehicles that actually departed

### Distortion

Configured demand in 1200 s: **9600 vehicles**.

| Setting | Departed | Failed to insert |
| --- | --- | --- |
| `--time-to-teleport 300` | 224 | 9376 |
| `--time-to-teleport -1` | 200 | 9400 |

### Detection rule

Compare configured demand against actual departures. If `departed / configured` collapses toward zero, the run is not a valid demand realisation and must be flagged.

---

## 3. Gridlock

### How it was induced

Same all-red overload. The easiest reliable trigger is to hold the signal at all-red, not to wait for demand alone to discover the jam.

### Signature in output

- all incoming lanes stay fully halted
- pending vehicles keep accumulating
- teleports begin once the timeout expires unless disabled
- with teleporting disabled, the run stays blocked and `timeLoss` keeps growing

### Detection rule

Cheapest reliable rule:

1. monitor every incoming lane
2. if `getLastStepHaltingNumber(lane) == getLastStepVehicleNumber(lane)` for a sustained window and
3. pending vehicles keep rising while departures flatten,

declare gridlock. Teleport counts are a corroborating signal, not the primary detector.

---

## 4. Decision status

- `D-008` is confirmed, and its **priority is reordered**: on an isolated intersection the
  insertion-loss check is the one that will actually fire, and the teleport check is insurance
  that starts paying at M5. Both stay mandatory from M1.
- The all-red stress case is retained above as a demonstration that the failure modes are real,
  but its numbers are not evidence about any regime we intend to run.
- The detection rules belong in T1.8, and the insertion-loss threshold deserves a real value
  rather than a placeholder — 22% loss produced a plausible-looking result.
