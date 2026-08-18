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

### Distortion

Measured over the 1200 s run:

| Setting | Teleports | Departed | Mean `timeLoss` |
| --- | --- | --- | --- |
| `--time-to-teleport 300` | 24 | 224 | 1038.12 s |
| `--time-to-teleport -1` | 0 | 200 | 1168.16 s |

Teleporting reduced mean `timeLoss` by about **11.1%** in this stress case.

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

- `D-008` is confirmed and strengthened: teleporting must be disabled and counted, not merely tolerated.
- The footguns are reproducible, and the detection rule belongs in T1.8.
