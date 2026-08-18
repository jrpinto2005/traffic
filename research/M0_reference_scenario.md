# M0 Reference Scenario — hand-built four-way intersection

**Ticket:** `tickets/M0/T0.2_reference_scenario.md` · **Status:** complete as a source artifact

---

## 1. Network

The scenario lives in `spikes/M0_reference/` and is intentionally small:

- `reference.nod.xml` — four outer nodes plus the signalized junction `j1`
- `reference.edg.xml` — eight directed edges, 200 m approaches, 50 km/h
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

SUMO exposes connection-level metadata that is enough to seed the project's three-valued conflict matrix:

- `has priority`
- `is opened`
- `has approaching foe`
- current state
- direction
- length

In plain-connections terms, that is enough to distinguish:

- `compatible` movements
- `conflicting` movements
- `permitted` movements where one yields

This scenario does not use permitted turns; it uses protected-only movements. But the schema can already be seeded from SUMO's junction conflict data, and the three-valued matrix in `D-023` remains the right abstraction.

---

## 5. Notes

- The route file uses constant flows from all four approaches, with one flow per movement-lane pair.
- The script prints one line per step plus lane and vehicle state, which is enough for the later M0 spikes.
- The network is intentionally minimal; it is a reference, not the final generator output.
