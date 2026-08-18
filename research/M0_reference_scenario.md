# M0 Reference Scenario — hand-built four-way intersection

**Ticket:** `tickets/M0/T0.2_reference_scenario.md` · **Status:** complete as a source artifact

---

## 1. Network

The scenario lives in `spikes/M0_reference/` and is intentionally small:

- `reference.nod.xml` — four outer nodes plus the signalized junction `j1`
- `reference.edg.xml` — eight directed edges, 50 km/h, nodes placed 200 m from the junction.
  **The resulting lanes are 189.6 m, not 200 m** — junction geometry consumes the remainder.
  Anything computing saturation flow, queue capacity or free-flow travel time must read the
  built lane length from the network, never the nominal node spacing.
- `reference.con.xml` — eight controlled connections, two per approach
- `reference.tll.xml` — one static program with two green phases (NS and EW) plus explicit yellow transitions
- `reference.rou.xml` — constant demand from all four approaches
- `reference.sumocfg` — headless run configuration
- `run_reference.py` — builds the net with `netconvert`, then runs SUMO via TraCI and prints per-step state

The design is intentionally protected-only at M1: the second lane on each approach is used for the turning movement on that approach, but no permissive turn is modelled.

---

## 2. State fields and units

These are the fields the spike script prints, and the exact SUMO/TraCI meaning of each.

| Field | Source | Meaning | Unit |
| --- | --- | --- | --- |
| `timeLoss` | `traci.vehicle.getTimeLoss` | Accumulated travel-time loss of the vehicle relative to free flow | s |
| `waitingTime` | `traci.vehicle.getWaitingTime` | Accumulated waiting time for the vehicle | s |
| `speed` | `traci.vehicle.getSpeed` | Vehicle speed in the last simulation step | m/s |
| `position` | `traci.vehicle.getPosition` | Front-bumper center position in world coordinates | m, m |
| `type` | `traci.vehicle.getTypeID` | SUMO vehicle type identifier | type id |
| `lane` | `traci.vehicle.getLaneID` | Lane the vehicle occupied in the last step | lane id |
| `lastStepHaltingNumber` | `traci.lane.getLastStepHaltingNumber` | Vehicles on the lane with speed below 0.1 m/s in the last step | count |
| `lastStepOccupancy` | `traci.lane.getLastStepOccupancy` | Total vehicle length on the lane divided by lane length | fraction |
| `laneWaitingTime` | `traci.lane.getWaitingTime` | Waiting time accumulated over vehicles on the lane | s |
| TLS state | `traci.trafficlight.getRedYellowGreenState` | Per-link signal state string | symbol string |

For the queue semantics used elsewhere in the project, the important point is that SUMO's halting counter is speed-threshold only; the 1 s duration condition in `D-025` is ours.

---

## 3. Signal program control

There are three relevant TraCI entry points:

- `traci.trafficlight.setProgram(tls_id, program_id)` — switch to another defined program
- `traci.trafficlight.setPhase(tls_id, phase_index)` / `setPhaseDuration(...)` — move within the current program
- `traci.trafficlight.setRedYellowGreenState(tls_id, state)` — immediate manual override of the current signal state

For the reference spike, the static program in `reference.tll.xml` is enough. Mid-run override is still useful as a smoke test because it proves the intersection can be controlled from Python without rebuilding the network.

---

## 4. Conflict representation and D-023

**The mechanism given in the first pass was wrong, and the claim was never tested. Corrected
2026-08-18.**

The original text proposed seeding the matrix from `traci.lane.getLinks()` metadata —
`has priority`, `is opened`, `has approaching foe`. Two of those are **runtime** values that
depend on the current signal state and the vehicles currently present. Seeding a *static*
conflict matrix from dynamic link state is a category error. The claim was also asserted
without a test, on a scenario that deliberately contains no permitted turns — the one case
that the three-valued distinction exists for.

### What actually works

Verified on a probe network with a netconvert-inferred permissive left
(`spikes/M0_verify/verify.py`, section C). The conflict data is **static, in the net file**:

```xml
<junction id="c" type="traffic_light">
  <request index="3" response="1000011010000000" foes="1110011011100000"/>
```

- **`foes`** — bitstring over link indices: which links physically conflict with this one.
  Pure geometry, independent of signals.
- **`response`** — of those foes, the ones this link must **yield** to.

That yields the three-valued relation directly:

| `foes[i]` | `response[i]` | Relation |
| --- | --- | --- |
| 0 | — | `COMPATIBLE` |
| 1 | 1 | `PERMITTED` — this link yields to *i* |
| 1 | 0 | `CONFLICTING` — may not be green together |

Protected versus permissive is carried separately, in the **case** of the phase state string:

```
GGGgrrrrGGGgrrrr    G = protected green, g = permissive green (yields)
```

The fourth link in each group is the permissive left.

### Consequence for T1.3

`D-023` is confirmed as the right abstraction, but T1.3 must read `<request>` `foes` and
`response` from the built network plus the `G`/`g` case from the TLS program. It must **not**
use `getLinks()` runtime state. This scenario still contains no permitted turn, so T1.3's
validation needs a network that does — the probe in `spikes/M0_verify/` is one.

---

## 5. Notes

- The route file uses constant flows from all four approaches, with one flow per movement-lane pair.
- The script prints one line per step plus lane and vehicle state, which is enough for the later M0 spikes.
- The network is intentionally minimal; it is a reference, not the final generator output.
