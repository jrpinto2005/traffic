# M0 Prior Art Review — sumo-rl, RESCO, LibSignal, PyTSC

**Ticket:** `tickets/M0/T0.1_prior_art.md` · **Archetype:** Spike
**Informs:** `D-013`, `D-020` · **Closes:** `01_CRITICAL_REVIEW.md` G-9
**Date:** 2026-08-18

---

## 0. Status of this review, and what was *not* done

**SUMO is not installed** (`T0.0` is still pending). The ticket's Method section requires
running `sumo-rl`'s single-intersection example and one RESCO scenario. That acceptance
criterion is **explicitly unchecked**:

- [ ] ~~Run `sumo-rl`'s single-intersection example~~ — **NOT DONE, blocked on T0.0.**
- [ ] ~~Run one RESCO scenario~~ — **NOT DONE, blocked on T0.0.**

Everything below comes from reading the source at the commits cloned into
`spikes/M0_prior_art/` on 2026-08-18, plus the RESCO NeurIPS 2021 paper and the PyTSC paper.
Vendored source is gitignored; clone commands are in `spikes/M0_prior_art/.gitignore`.

### What running would settle that reading cannot

These are the specific claims below that are inferred from code and should be **verified by
execution** once T0.0 lands. They are listed so a later ticket can close them mechanically:

1. **RESCO's effective green time under Max-Pressure.** Reading says a signal that switches
   at every 5 s decision point spends 3 s in yellow plus up to 2 s in all-red, leaving
   0–2 s of actual green. Verify by logging `getRedYellowGreenState` per second on
   `grid4x4` with `@MAXPRESSURE`.
2. **RESCO's `queued` stickiness.** Reading says a vehicle is flagged queued permanently
   once it drops below 0.1 m/s and stays flagged while within 200 m. Verify by comparing
   `Observation.total_queued` against `traci.lane.getLastStepHaltingNumber` summed over the
   same lanes; they should diverge upward.
3. **PyTSC's SUMO seeding.** Reading says `--seed` is never passed, so all "trials" on the
   SUMO backend are the same realisation. Verify by running the same scenario twice with
   different `seed:` values and diffing the tripinfo output.
4. **PyTSC's `max_depart_delay: 0`.** Reading says the key is never passed to SUMO, so
   SUMO's default applies rather than the aggressive discard the config implies. Verify by
   inspecting the launched command line.
5. **LibSignal's `yellow_phase_time` inference.** Reading says it is `min(phase.duration)`
   over the net file's first program, which will mis-identify yellow on any net with a
   short green. Verify on a net with a 4 s green.
6. **sumo-rl's `max_green`.** The docstring says the parameter is ignored; the code says it
   fires only when `enforce_max_green=True` *and* the controller requested to stay.
   Verify with a controller that always requests the current phase.

None of these change the recommendations in §7 — they change how confidently we can state
the divergences in §5.

---

## 1. sumo-rl (LucasAlegre/sumo-rl)

`spikes/M0_prior_art/sumo-rl` · ~1.4k LOC of environment code · MIT.

### Purpose
A Gymnasium / PettingZoo wrapper around SUMO for RL traffic signal control. It is an
**environment**, not a benchmark: it deliberately ships no controllers other than a tabular
Q-learning agent (`sumo_rl/agents/ql_agent.py`). RESCO v1.0 was built on top of it.

### Scenario format
Plain SUMO. A `.net.xml` and a `.rou.xml` are passed directly to `SumoEnvironment`; there is
no intermediate description. Bundled nets live in `sumo_rl/nets/` — `single-intersection`,
`2way-single-intersection`, `2x2grid`, `3x3grid`, `4x4grid`, `double`, plus a vendored copy of
the eight RESCO nets under `sumo_rl/nets/RESCO/`, re-exported by
`sumo_rl/environment/resco_envs.py` as ready-made env factories.

**Signal phases are read from the net file.** `TrafficSignal._build_phases` scans
`getAllProgramLogics(...)[0].phases`, keeps every phase with no `y` that is not all-`r`/`s` as
a green phase, synthesises a yellow transition for every ordered green pair, and **rewrites
the whole TLS program via `setProgramLogic`**. The class docstring states the limitation
plainly: *"Currently it is not supporting all-red phases."*

### Action space
`spaces.Discrete(num_green_phases)` — **phase selection**, one discrete action per green
phase, applied every `delta_time` seconds. This is the same *kind* of action space as
`D-020`.

Constraint handling lives in `TrafficSignal.set_next_phase` and is thin:

| Constraint | sumo-rl behaviour |
| --- | --- |
| Min green | `if green_phase == new_phase or time_since_last_phase_change < yellow_time + min_green:` → **silently holds the current phase**. Effective min green is `min_green + yellow_time` = 7 s at defaults, not 5 s. |
| Max green | Only when `enforce_max_green=True` (**default `False`**), and only on the branch where the controller asked to *stay*. Requesting a different phase never triggers max-green. Override target is `(green_phase + 1) % num_green_phases`, i.e. cyclic, not chosen. |
| Yellow | Synthesised per ordered green pair, `yellow_time` = 2 s default. |
| All-red | **Not supported.** |
| Conflict legality | Not checked — legality is whatever the net file's phases encode. |
| Outcome record | **None.** A deferred request is indistinguishable from a granted one. |

Decision interval `delta_time` defaults to **5 s**, asserted `> yellow_time`. The step loop
(`_run_steps`) advances SUMO one second at a time and calls `TrafficSignal.update()` each
second, so yellow timing is exact — the same two-tier structure `D-020` specifies.

### Baselines implemented
**None.** Grep for `webster|actuated|max.?pressure|sotl|maxwave` across the whole repository
returns nothing. `fixed_ts=True` makes the env follow the net file's static program, which for
a `netconvert`-generated net is an arbitrary equal split — precisely the badly-tuned baseline
`D-013` rejects.

`TrafficSignal.get_pressure()` exists but is a **reward function, not a controller**, and it
is intersection-level: `sum(vehicle_number over all out lanes) - sum(over all in lanes)`. It
uses total vehicle counts, not queues, and is not decomposed per phase, so it is not
usable as Max-Pressure.

### Metric definitions

| sumo-rl name | Computation | Unit |
| --- | --- | --- |
| `system_total_stopped` | `sum(speed < 0.1)` over all vehicles | vehicles |
| `system_total_waiting_time` | `sum(traci.vehicle.getWaitingTime(v))` | s |
| `system_mean_speed` | mean of `getSpeed` | m/s |
| `system_total_arrived` / `departed` / `teleported` | accumulated `getArrivedNumber` / `getDepartedNumber` / `getEndingTeleportNumber` | count |
| `system_total_backlogged` | `len(getPendingVehicles())` | count |
| `<ts>_stopped` | `sum(getLastStepHaltingNumber(lane))` over incoming lanes | vehicles |
| `<ts>_accumulated_waiting_time` | per-lane sum of `getAccumulatedWaitingTime`, with manual cross-lane bookkeeping | s |
| lane `density` / `queue` | vehicle count / halting count, divided by `lane_length / (2.5 + mean vehicle length)` | fraction |

**There is no delay metric at all.** `timeLoss` is never read; no tripinfo output is
requested. Metrics are sampled per `step()` and dumped to CSV; there is **no warm-up, no
measurement window, and no trip-level accounting**.

Defaults worth knowing: `time_to_teleport = -1` (teleporting off by default — good, and it
matches `D-008`), `max_depart_delay = -1` (no discard), `waiting_time_memory = 1000`,
`sumo_seed = "random"` (**seed is random unless set**).

### Notes for us
- `get_accumulated_waiting_time_per_lane` calls `traci.vehicle.getLaneID` and
  `getAccumulatedWaitingTime` **per vehicle per lane per step**. This is the
  `08_AGENT_HANDOFF_PROTOCOL.md` §7 per-object-polling anti-pattern, in the default reward
  path. It is the single clearest reason not to reuse this wrapper's hot loop.
- Docstring/code disagreement on `max_green` (docstring says 60 and "currently ignored",
  signature says 50 and it is conditionally honoured) is a live bug in a results-affecting
  parameter.

---

## 2. RESCO (Pi-Star-Lab/RESCO)

`spikes/M0_prior_art/RESCO` · GPL-3 · **the clone is v2.0**, the refactored codebase; the
NeurIPS 2021 paper describes v1.0. Where the two differ I say so.

### Purpose
A **benchmark**: a fixed set of scenarios, a fixed set of state/reward/action options, and a
standardised implementation of several RL algorithms plus three non-learning controllers, so
that published numbers are comparable. This is the closest project in spirit to what our
M1 is for.

### Scenario format
A SUMO `.net.xml` and `.rou.xml` **plus a hand-authored YAML block per intersection** in
`resco_benchmark/config/signal.yaml`. Per signal:

- `lane_sets`: a dict from one of twelve turn movements (`'S-W'`, `'S-S'`, `'S-E'`, `'W-N'`,
  `'W-W'`, `'W-S'`, `'N-E'`, `'N-N'`, `'N-W'`, `'E-S'`, `'E-E'`, `'E-N'` — from-compass to
  to-compass, no U-turns) to the list of incoming lane IDs serving it.
- `downstream`: `{'N': <signal id or null>, 'E': …, 'S': …, 'W': …}` — the neighbour graph,
  which is what makes downstream pressure computable.
- `fixed_timings`: the fixed-time plan, **in units of decision steps, not seconds**.
- `fixed_phase_order_idx`, optionally `fixed_offset`.

Per map, a `phase_pairs` list of eight `[movement, movement]` pairs defines the action space.

**This is the format's real cost.** Every new network requires hand-authoring the lane sets,
the neighbour graph and the phase pairs. `Signal._find_neighbors` raises
`Exception("Invalid signal config")` if they are inconsistent. Nothing derives them from the
net file.

Scenarios and their windows (`config.yaml`): `grid4x4` and `arterial4x4` 0–3600 s;
`cologne1/3/8` 25200–28800 s (07:00–08:00); `ingolstadt1/7/21` 57600–61200 s (16:00–17:00);
`saltlake2_*` a full year of recorded data, 0–86400 s per day. `flow` scales demand
multiplicatively (`1.0` = original).

### Action space
Phase selection over the green phases discovered in the net file
(`act_size = len(signal.green_phases)`), with the eight `phase_pairs` giving the semantic
mapping. `action_set` may be `Phase` (default), `FixedCyclePlan` (keep / lengthen / shorten
the current phase in a fixed cycle) or `FixedCycle` (binary keep / advance). The alternative
action sets are in `mdp_options/actions.py`; `PhaseLength` is a `pass  # TODO`.

Constraint handling (`traffic_signal.Signal`):

| Constraint | RESCO behaviour |
| --- | --- |
| Min green | **None.** The 5 s decision interval is the only floor. |
| Max green | **None.** |
| Yellow | `cfg.yellow_length = 3` s, synthesised by `create_yellows()` for every ordered pair. |
| All-red | `cfg.clearance_length = 2` s, applied **only when the outgoing phase contains a permissive `g`**. The comment says "use if SUMO gridlocks in high demand". |
| Conflict legality | Implicit in the net file's phases. |
| Outcome record | None. |

Because yellow and all-red are consumed *inside* the 5 s decision interval, a controller that
switches at every decision point can be left with **0–2 s of actual green per cycle**. See
§0 item 1 — this needs verifying by running, but it follows directly from `Signal.step()`.

### Baselines implemented
Three, in `agents/static/`:

- **FIXED** — cycles `fixed_timings` (per-signal, in decision steps) in a permuted phase
  order, with an offset that is `# TODO only implemented for 2 signal maps with A3 and B3`.
  For `grid4x4` and `arterial4x4` every signal is given the identical plan
  `[4, 2, 4, 2, 4, 2, 4, 2]` = 20/10/20/10/20/10/20/10 s. **This is an equal-split plan, not
  a Webster plan.** For Cologne/Ingolstadt the timings appear derived from the real programs.
- **MAXWAVE** — `argmax` over `phase_pairs` of `wave[left] + wave[right]`, where
  `wave = queued + approaching` per movement. This is greedy-queue, i.e. the paper's "Greedy".
- **MAXPRESSURE** — a two-line subclass of `MAXWAVE` that runs the same `argmax` over the
  `mplight` state with the leading `current_phase` element stripped. The `mplight` state is,
  per movement: `sum(inbound lane.queued) - sum(downstream lane.queued)`. So RESCO's
  Max-Pressure **is** per-movement, queue-based, downstream-subtracted pressure — the
  textbook form — but with no saturation-flow weighting and no min green.

No Webster. No actuated. No SUMO `type="actuated"` cross-check.

### Metric definitions
Two streams.

**From SUMO tripinfo XML** (`utils/logs.py::parse_xml_log`), configured as
`xml_metrics: ['timeLoss', 'duration', 'waitingTime']` and renamed for plots by
`pretty_names.yaml`:

| RESCO label | Source | Unit |
| --- | --- | --- |
| **"Average Delay" / "Delay (s)"** | tripinfo `timeLoss`, **plus tripinfo `departDelay`** (v2.0 only), summed over all trips and divided by the trip count | s/veh |
| "Average Travel Time" | tripinfo `duration` | s/veh |
| "Average Waiting Time" | tripinfo `waitingTime` | s/veh |

The trip set includes unfinished and undeparted vehicles, because the command line carries
`--tripinfo-output.write-unfinished True`, `--tripinfo-output.write-undeparted True` and
`--eager-insert`. Vehicles whose ID starts with `ghost` (lane-closure props) are excluded.

**From RESCO's own per-step CSV** (`csv_metrics: ['rewards','max_queues','queue_lengths','vehicles','phase_length']`):
`queue_lengths` = `Observation.total_queued`, `max_queues` = per-signal max over lanes.

**RESCO's queue is not SUMO's halting count and not ours.** In `Vehicle.observe`:

```python
if vehicle.speed < 0.1:
    self.queued = True      # never reset
if self.queued:
    self.wait += cfg.step_ratio
```

A vehicle becomes `queued` the first time it drops below 0.1 m/s and **stays queued for as
long as it remains within `cfg.max_distance = 200 m` of the junction**, moving or not. The
same flag gates `wait`, so RESCO's waiting time is *time since first stop*, not time below a
speed threshold. Both quantities are strictly larger than the SUMO-native equivalents.
This queue is the input to MAXPRESSURE and MAXWAVE, so under `D-025`'s framing RESCO's
Max-Pressure is **a different controller**, not just a differently-measured one.

**RESCO's per-vehicle `delay` is dimensionless.** `Signal._inter_step_observe` subscribes to
`VAR_TIMELOSS` and then overwrites it:

```python
vehicle[tc.VAR_TIMELOSS] = (vehicle[tc.VAR_SPEED] - vehicle[tc.VAR_ALLOWED_SPEED]) / vehicle[tc.VAR_ALLOWED_SPEED]
```

so `Vehicle.delay` accumulates a normalised speed deficit in `[-1, 0]` per observation step,
not seconds. Only the `oracle_delay` reward uses the real `getTimeLoss`. The paper's
footnote 3 confirms this is deliberate: signal-induced delay "can only be computed in
hindsight", so the *reward* uses a real-time approximation. The *reported* delay is tripinfo
`timeLoss`, which is a different quantity from the reward.

### Run protocol
- `episodes: 100`, `trials: 5` independent runs, no warm-up, no measurement window: metrics
  cover the entire `start_time`→`end_time` span, and for `grid4x4`/`arterial4x4` that means
  from an empty network.
- SUMO command line: `--time-to-teleport -1` (**matches `D-008`**), `--no-warnings`,
  `--no-step-log`, `--extrapolate-departpos True`, `--eager-insert`, and
  `--random True` — **always**. `config.yaml` says `seed: null # Unused right now, TODO make
  fully reproducible runs with seeding`. RESCO runs are therefore **not reproducible and not
  seed-paired**, which rules out the common-random-numbers design `D-017` requires.
- Validity: teleports are structurally impossible (good), but there is no insertion-failure
  threshold and no gridlock detector. `init_ender` optionally aborts if any pending vehicle
  has waited ≥ 1800 s.

---

## 3. LibSignal (DaRL-LibSignal/LibSignal)

`spikes/M0_prior_art/LibSignal`.

### Purpose
A **cross-simulator** framework: one agent implementation runs against SUMO, CityFlow or
CBEngine through a `world/` abstraction (`world_sumo.py`, `world_cityflow.py`,
`world_openengine.py`). Its selling point is sim-to-real / sim-to-sim transfer — the README
advertises "Conversion between SUMO and CityFlow is carefully calibrated" and links two
sim-to-real papers.

### Scenario format
**CityFlow-first.** The SUMO scenarios are shipped alongside a converted CityFlow JSON
roadnet: `configs/sim/sumo1x1_colight.cfg` names both
`combined_file: raw_data/cologne1/cologne1.sumocfg` and
`roadnetFile: raw_data/cologne1/cologne1_roadnet_red.json`. The JSON roadnet is what defines
intersections, phases and lane links; the SUMO net is the execution substrate. Configuration
is layered YAML (`configs/tsc/base.yml` + per-agent override) plus a JSON sim config.

### Action space
`gym.spaces.Discrete(len(inter_obj.phases))` — phase selection. Decision interval
`action_interval: 10` s (`base.yml`). Yellow is inserted by `world_sumo.create_yellows`.

**Yellow duration is inferred, not configured.** `world_sumo.py:63`:

```python
self.yellow_phase_time = min([i.duration for i in self.eng.trafficlight.getAllProgramLogics(self.id)[0].phases])
```

i.e. the shortest phase in the net file's first program is assumed to be the yellow. On a net
with a short green this silently mis-identifies the yellow. `base.yml` also carries
`yellow_length: 5`, which the SUMO world ignores. No all-red. No max green. Min green is
whatever each controller enforces for itself (`t_min`).

### Baselines implemented
`agent/fixedtime.py`, `agent/maxpressure.py`, `agent/sotl.py`, plus RL agents (DQN, FRAP,
CoLight, PressLight, MPLight, MADDPG, PPO, SAC, MAGD).

- **fixedtime** — `t_fixed: 30`, round-robin over phases. This is literally the
  "30 s NS / 30 s EW" plan that `D-013` names as a badly-tuned baseline.
- **maxpressure** — `t_min: 10` s min green, then
  `argmax_phase sum(lvc[start] - lvc[end] for start, end in phase_available_lanelinks[phase])`
  where `lvc = get_info("lane_count")`. **`lane_count` is the total number of vehicles on the
  lane within the sensing distance, not the queue.** So LibSignal's Max-Pressure is
  count-based, where RESCO's is queue-based. The two are different algorithms sharing a name.
- **sotl** — thresholds `min_green_vehicle`, `max_red_vehicle`, `t_min`, over
  `lane_waiting_count`.

No Webster. No actuated. No SUMO gap-actuated cross-check.

### Metric definitions
This is where LibSignal diverges hardest.

| LibSignal name | Computation (`world/world_sumo.py`) | Unit |
| --- | --- | --- |
| `lane_delay` (**"approximate delay", the default**) | `1 - lane_avg_speed / lane_speed_limit` | **dimensionless, [0,1]** |
| "real delay" (`get_real_delay`, opt-in via `delay_type`) | Per lane traversed: `max(0, observed_time_on_lane - lane_length/min(lane_max_speed, vehicle_max_speed))`, summed over the vehicle's lane sequence | s |
| `lane_waiting_count` | count of vehicles with `wait > 0`, where `wait` is seeded from `getWaitingTime` once and then incremented by `step_length` **every step regardless of current speed** | vehicles |
| `queue_length` | `lane_measures['queue_length'] + 1` for **every** vehicle on the lane, i.e. it equals the lane vehicle count. Carries the source comment `#TODO: CHEC ITS RIGHT CALCULATION?` | vehicles |
| `throughput` | `len(self.vehicles)` — vehicles **currently tracked**, not completed trips. `#TODO: check if only trach left cars` | count |
| `real_average_travel_time` | mean of a per-vehicle accumulated time counter | s |

Three of these are mislabelled relative to any standard definition: `lane_delay` is not a
delay, `queue_length` is not a queue, and `throughput` is not a throughput. The "real delay"
path is a hand-rolled reimplementation of time loss with a **per-lane clamp at zero**, which
makes it systematically larger than SUMO's `timeLoss` (SUMO nets losses and gains across the
whole trip; LibSignal cannot go negative on any lane).

Defaults: `steps: 3600`, `episodes: 200`, `seed: 0` (single seed), no warm-up, no measurement
window, teleporting left at the SUMO default (**not disabled**).

---

## 4. PyTSC (rbokade/pytsc)

`spikes/M0_prior_art/PyTSC` · paper: Bokade & Jin, *Sensors* 25(5):1302, 2025
(arXiv:2410.18202). Note: the paper does not carry the repo URL in its abstract page; the
URL `https://github.com/rbokade/pytsc` comes from the HTML full text. The org names guessed
from the paper title (`UMass-LIDS`, `tsc-benchmark`) do not exist.

### Purpose
A MARL-focused unified platform whose stated goal is fixing "slow simulation speeds and
convoluted, difficult-to-maintain codebases" in the existing platforms. Supports SUMO and
CityFlow.

### Architecture — worth studying independently of whether we reuse it
`pytsc/common/` holds abstract bases (`simulator`, `retriever`, `network_parser`,
`traffic_signal`, `metrics`, `observations`, `actions`, `reward`) and `pytsc/backends/sumo/`
and `pytsc/backends/cityflow/` hold one concrete implementation each. This is **exactly the
shape `D-002` describes** for our backend adapter, with the difference that PyTSC has two
real implementations and we would have one. It is the best available worked example of where
the seam should fall.

### Scenario format
Native simulator files (`.sumocfg` + `.net.xml`, or CityFlow JSON) plus a per-scenario
`config.yaml` layered over `pytsc/scenarios/default/config.yaml`. Network topology, phases
and lane links are **parsed from the net file** by `backends/sumo/network_parser.py` — no
hand-authored lane sets, unlike RESCO. Ships synthetic grid generators
(`generators/grid_generator.py`) and trip generators, plus scenarios `2x2_sumo_grid`,
`3x3_sumo_grid`, `cologne3`, and a family of `random_grid*` scenarios.

### Action space
Two, selected by `signal.action_space`:

- **`phase_switch` (the default)** — binary: `0` hold, `1` advance to the next phase in a
  round-robin cycle (`round_robin: True`). `D-020` considered and **rejected** exactly this
  as the canonical form, on the grounds that it cannot skip an empty phase.
- **`phase_selection`** — index of the phase to switch to. Available but not the default.
- `CentralizedActionSpace` composes either into a joint action of size `n_actions ** n_agents`.

Constraint handling is an **action mask**: `TLSFreePhaseSelectLogic.get_allowable_phase_switches(time_on_phase)`
returns a per-phase 0/1 vector enforcing `min_green_time: 5`, `max_green_time: 60` and the
green→yellow ordering. Defaults `yellow_time: 5`, `delta_time: 5`, with a hard assertion
`yellow_time == delta_time`. Masking is a cleaner mechanism than sumo-rl's silent hold, but
it still records no outcome: a controller cannot tell "I was overridden" from "I chose this".

### Baselines implemented
`pytsc/controllers/controllers.py`: `FixedTimeController(green_time=25)` round-robin,
`GreedyController`, `MaxPressureController`, `SOTLController(theta=3, mu=4, phi_min=5)`,
`RandomController`. No Webster, no actuated.

**PyTSC's Max-Pressure has two defects.** In `_compute_pressure_for_phase`:

```python
for inc_lane, out_lanes in phase_inc_out_lanes.items():
    inc_lane_vehicles = sum([p >= 0.0 for p in inc_pos_mat])
    out_lane_vehicles = 0
    for out_lane in out_lanes:
        out_pos_mat = ...
        out_lane_vehicles = sum([p >= 0.0 for p in out_pos_mat])   # assignment, not +=
    pressure += np.abs(inc_lane_vehicles - out_lane_vehicles)      # absolute value
```

1. `out_lane_vehicles` is **assigned** inside the loop, so only the last outbound lane counts.
2. `np.abs(...)` means a movement whose *downstream* is more congested than its inbound scores
   **high** pressure. That inverts the sign of the controlling term and defeats the entire
   point of pressure control.

It also counts all vehicles within visibility (`p >= 0.0`), not queued ones, so it is
count-based like LibSignal rather than queue-based like RESCO. **Do not port this
implementation.**

### Metric definitions

| PyTSC name | Computation (`backends/sumo/metrics.py`, `retriever.py`) | Unit |
| --- | --- | --- |
| `n_queued` | `LAST_STEP_VEHICLE_HALTING_NUMBER` per lane, summed | vehicles |
| **`mean_delay`** | `1 - norm_mean_speed`, where `norm_mean_speed` is the lane-mean of `mean_speed / lane_max_speed` | **dimensionless, [0,1]** |
| `average_travel_time` | per lane, `VAR_CURRENT_TRAVELTIME / n_vehicles`, then averaged **over lanes** | not a trip travel time |
| `average_wait_time` | per lane, `VAR_WAITING_TIME / n_queued`, averaged over lanes | s |
| `density` | lane-mean `LAST_STEP_OCCUPANCY` | fraction |
| `pressure` | sum of per-signal pressure | vehicles |
| `flickering_signal` | mean of per-signal `phase_changed` | fraction |

`average_travel_time` deserves a flag: `VAR_CURRENT_TRAVELTIME` is SUMO's *estimated lane
traversal time* (`length / mean_speed`), not a realised trip duration. Dividing it by the
lane's vehicle count and averaging over lanes produces a quantity with no clean
interpretation. It is not comparable to anything in `07_EXPERIMENT_METHODOLOGY.md` §2.

`n_queued` uses SUMO's native halting counter, which is the **closest of the four projects to
`D-025`** — same 0.1 m/s threshold, missing only the 1 s duration condition.

### Run protocol and validity
- `delta_time: 5`, `sim_length: 3600`, `episode_limit: 360` s in the default config
  (scenario configs override).
- `initial_wait_time: 0` — a warm-up parameter exists and is **off by default**.
- Validity counters are the best of the four: `n_teleported`, `n_colliding`,
  `n_emergency_brakes`, `n_loaded`, `n_departed`, `n_arrived`, all subscribed and reported
  per step. Nothing acts on them — a run is never marked invalid.
- `time_to_teleport: 10000` — longer than a 3600 s episode, so teleporting is disabled *by
  magnitude*, not by the `-1` flag. A longer episode would silently re-enable it.
- **`--seed` is never passed to SUMO.** `start_simulator()` builds the command line with
  `--start`, `--no-warnings`, `--time-to-teleport`, `--quit-on-end`, `--no-step-log`,
  `--duration-log.disable`, `--remote-port` — and nothing else. The config's `seed:` reaches
  only `random.seed()` in Python. `max_depart_delay: 0` and `waiting_time_memory: 10000` are
  likewise never passed to the SUMO backend; they are dead keys there.
- `obs_dropout_prob` (default 0.0) is the only sensing-degradation knob in any of the four
  projects. It is a single scalar Bernoulli drop on observation readings — not a sensor model.

### Efficiency
Lane, signal and simulation variables are read via **TraCI subscriptions**, which is what
`D-031` asks for. But `_compute_lane_position_matrix` then calls
`traci.vehicle.getLanePosition(v)` and `traci.vehicle.getSpeed(v)` **per vehicle, per lane,
per step**, which is the §7 anti-pattern in the default observation path — the same defect as
sumo-rl, in a codebase that otherwise gets the transport layer right.

---

## 5. Their conventions versus ours

Our conventions: `D-006` (delay = time loss), `D-008` (teleporting off, validity counters),
`D-013` (mandatory baselines), `D-017` (seeds, paired comparison), `D-018` (warm-up and
measurement window), `D-020` (phase selection, constraint layer, periodic Δt), `D-022` (trip
accounting), `D-025` (queue), `07_EXPERIMENT_METHODOLOGY.md` §2.

Legend: **=** same · **≈** same family, different details · **✗** divergent, numbers not
comparable · **—** absent.

### 5.1 Action space and control (`D-020`, `D-023`)

| Aspect | Ours (`D-020`) | sumo-rl | RESCO | LibSignal | PyTSC |
| --- | --- | --- | --- | --- | --- |
| Action form | Phase selection | Phase selection **=** | Phase selection **=** (+ cycle variants) | Phase selection **=** | **`phase_switch` binary, round-robin, by default ✗** (`phase_selection` available) |
| Phase set source | Authored + validated against a conflict matrix (`D-023`) | Net file, greens auto-detected **≈** | Net file greens + hand-authored `phase_pairs` YAML **≈** | CityFlow JSON roadnet **✗** | Net file, parsed **≈** |
| Decision interval Δt | Per-controller, global default; must be ≥ SUMO step and ≤ min green | 5 s, global **≈** | 5 s, global **≈** | 10 s, global **≈** | 5 s, global; asserted `== yellow_time` **≈** |
| Min green | Enforced by constraint layer, per phase | `min_green + yellow_time` = 7 s effective **≈** | **— none** ✗ | Per-controller `t_min` (10 s for MP) **≈** | 5 s via action mask **=** |
| Max green | Enforced, with a documented overshoot rule | Off by default; only fires on a "stay" request **✗** | **— none** ✗ | **—** ✗ | 60 s via action mask **=** |
| Yellow | Enforced every step by the constraint layer | 2 s, per-step update **=** | 3 s, per-step update **=** | Inferred as `min(phase durations)` **✗** | 5 s **=** |
| All-red | Enforced | **— not supported** ✗ | 2 s, only after permissive-left phases **≈** | **—** ✗ | Not separately modelled **≈** |
| Conflict legality | Three-valued conflict matrix, request may be REJECTED | Net file only | Net file only | Roadnet only | Net file only |
| Request outcome record | GRANTED / DEFERRED / HELD / FORCED / REJECTED, all recorded | **— silent hold** ✗ | **—** ✗ | **—** ✗ | Action mask, but no outcome record **≈** |
| Two-tier (safety every step, policy every Δt) | Required | Yes **=** | Yes **=** | Yes **=** | Yes **=** |

### 5.2 Metrics (`D-006`, `D-025`, §2)

| Metric | Ours | sumo-rl | RESCO | LibSignal | PyTSC |
| --- | --- | --- | --- | --- | --- |
| **Primary delay** | SUMO `timeLoss`, s/veh | **— none** ✗ | tripinfo `timeLoss` **+ `departDelay`** ✗ (near-match) | default `1 - v̄/v_max`, dimensionless **✗**; opt-in "real delay" = per-lane clamped time loss **✗** | `1 - v̄/v_max`, dimensionless **✗** |
| **Queue** | Halting < 0.1 m/s **for ≥ 1 s continuous**, count | `getLastStepHaltingNumber` — speed only, no duration **≈** | **Sticky**: queued once below 0.1 m/s, stays queued within 200 m **✗** | `queue_length` = lane vehicle count **✗**; `lane_waiting_count` = sticky wait flag **✗** | `getLastStepHaltingNumber` — speed only **≈** (closest) |
| Waiting time | Cumulative time below 0.1 m/s | `getAccumulatedWaitingTime` **≈** | Time since first stop **✗** | Seeded then incremented every step **✗** | `VAR_WAITING_TIME / n_queued` per lane, lane-averaged **✗** |
| Travel time | Depart→arrival, boundary sink **or** mid-link (`D-022`) | **—** | tripinfo `duration` **≈** | Per-vehicle accumulated counter **≈** | `VAR_CURRENT_TRAVELTIME / n_vehicles`, lane-averaged **✗** |
| Throughput | Completed trips/h over the measurement window | arrived count **≈** | derivable from tripinfo **≈** | vehicles currently in network **✗** | `n_arrived` per step **≈** |
| Per-vehicle-type split | Required from M1 (`§2.4`) | **—** ✗ | `VAR_TYPE` subscribed but unused in metrics **—** | **—** ✗ | **—** ✗ |
| Metric ↔ controller-input identity | Same definition (`D-025`) | n/a (no controller) | Same (sticky queue used for both) **=** in principle | Different: MP uses `lane_count`, reports `queue_length` **✗** | Different: MP uses visibility-window counts, reports `n_queued` **✗** |

### 5.3 Run protocol (`D-008`, `D-017`, `D-018`, `D-022`, `D-032`)

| Aspect | Ours | sumo-rl | RESCO | LibSignal | PyTSC |
| --- | --- | --- | --- | --- | --- |
| Teleporting | `-1`, **asserted at startup**, refuses to run otherwise | `-1` default **≈** (no assert) | `-1` always **≈** (no assert) | SUMO default, **on** ✗ | `10000` — off by magnitude, not by flag **✗** |
| Insertion loss | Counted; run marked invalid above threshold | `getPendingVehicles()` logged | `--eager-insert`, undeparted written to tripinfo **≈** | **—** ✗ | `n_loaded - n_departed` derivable, unused **≈** |
| Gridlock detection | Explicit, run marked gridlocked | **—** ✗ | `init_ender` heuristic on depart delay **≈** | **—** ✗ | **—** ✗ |
| Seeds | Fixed scheme, ≥30 paired seeds, **common random numbers across arms** | `"random"` by default ✗ | **`--random` always; seeding is a TODO** ✗ | `seed: 0`, single seed ✗ | **`--seed` never reaches SUMO** ✗ |
| Replications | ≥30 paired | n/a | 5 trials × 100 episodes **✗** | 1 **✗** | 10 test episodes **✗** |
| Warm-up | MSER-5 truncation, per scenario and demand level | **—** ✗ | **—** ✗ | **—** ✗ | `initial_wait_time`, default 0 **✗** |
| Measurement window | Explicit, with cool-down | Whole run **✗** | Whole run **✗** | Whole run **✗** | Whole run **✗** |
| Snapshots (`D-032`) | Warm up once, save, reuse | **—** | `saveState` / `--load-state`, saltlake only **≈** | **—** | **—** |
| Trip accounting (`D-022`) | Three ways: boundary sink, mid-link arrival, still in-network | **—** | unfinished + undeparted written to tripinfo **≈** | **—** ✗ | **—** ✗ |
| Reported uncertainty | 95% CI on paired differences | n/a | ±1 std over 5 seeds **≈** | **—** ✗ | over 10 test episodes **≈** |
| Result selection | Pre-registered window | n/a | **Best episode** over the run **✗** (see §6) | Final **≈** | Periodic test **≈** |

### 5.4 Baselines (`D-013`)

| `D-013` requires | sumo-rl | RESCO | LibSignal | PyTSC |
| --- | --- | --- | --- | --- |
| Webster fixed-time (computed, not arbitrary) | — | **— equal split `[4,2,4,2,4,2,4,2]` on the grids** | **— `t_fixed: 30` round-robin** | **— `green_time: 25` round-robin** |
| Actuated (ours) | — | — | — | — |
| SUMO gap-actuated cross-check | — | — | — | — |
| Max-Pressure | — | **Yes**, queue-based, per-movement, downstream-subtracted | Yes, but **count-based** | Yes, but **two defects, sign inverted** |
| Coordinated fixed-time (M5b) | — | `fixed_offset`, `# TODO only implemented for 2 signal maps` | — | — |
| Optional: SOTL | — | — | Yes | Yes |
| Optional: Max-Wave | — | Yes (`MAXWAVE`) | — | `GreedyController` |

**Not one of the four implements Webster, an actuated controller, or the SUMO gap-actuated
cross-check.** Every fixed-time baseline in every project is either an equal split or a
uniform round-robin — exactly the failure mode `D-013` was written to prevent. This is the
single most important result of the review: the part of `D-013` that is hardest to get right
is also the part that no prior-art project supplies.

### 5.5 The divergences that matter most, ranked

1. **Queue definition (`D-025`).** RESCO's sticky queue is not a queue in our sense, and
   because it feeds MAXPRESSURE, RESCO's "Max-Pressure" is a *different controller* from
   ours. LibSignal's `queue_length` is a vehicle count. Only PyTSC's is close, and it lacks
   the 1 s duration condition. **Our Max-Pressure results will not be numerically comparable
   to any published RESCO or LibSignal number**, only directionally comparable.
2. **Delay definition (`D-006`).** LibSignal and PyTSC both report a dimensionless
   `1 - v̄/v_max` under the name "delay". RESCO reports tripinfo `timeLoss` — the same family
   as ours — but adds `departDelay` and averages over undeparted vehicles too. A number
   labelled "delay" from LibSignal or PyTSC cannot be placed on the same axis as ours at all.
3. **No warm-up and no measurement window anywhere.** All four average over the whole
   episode, three of them starting from an empty network. Our `D-018` numbers will be
   systematically *higher* (no free-flow filling period diluting the mean) than a published
   whole-episode number on the same scenario.
4. **Seeding.** None of the four can do the paired, common-random-numbers comparison
   `D-017` requires. RESCO passes `--random` unconditionally; PyTSC never passes `--seed` at
   all. This means published gaps between two controllers carry unpaired noise that our
   design removes — their effect sizes and ours are not measured against the same variance.
5. **Missing min/max green in RESCO.** With no min green and a 5 s decision interval that
   yellow and all-red are consumed from, RESCO's controllers can operate at signal timings
   that would be illegal in the field. Any comparison against RESCO numbers imports that.
6. **PyTSC's default binary action space.** `D-020` rejected keep/switch precisely because it
   cannot skip an empty phase. PyTSC results run under the default config are measuring a
   more constrained controller than ours.

---

## 6. What RESCO's "~11% MPLight over Max-Pressure" actually measures

Source: Ault & Sharon, *Reinforcement Learning Benchmarks for Traffic Signal Control*,
NeurIPS 2021 Datasets & Benchmarks, **§4.1 "Validation", page 7**:

> "For validating the MPLight implementation, a traffic scenario was configured to be similar
> to the synthetic 4×4 symmetric network that was presented in the original MPLight
> publication [Chen et al. 2020]. The RESCO network is depicted in Figure 3 4×4 Grid […]
> Demand was set according to Config. 4 in Chen et al. […] Chen et al. 2020 reported a 13%
> improvement for MPLight over Max-pressure. The RESCO results show a similar trend with an
> **11% improvement**."

Unpacking that, exactly:

| Question | Answer |
| --- | --- |
| **Which network?** | RESCO's **`4x4 Grid` validation scenario** — a *synthetic* symmetric 16-signal grid built to mirror the network in the original MPLight paper (Chen et al., AAAI 2020). **Not** Cologne, **not** Ingolstadt, **not** any real city. |
| **Which demand?** | "Config. 4 in Chen et al." — a synthetic demand configuration lifted from the MPLight paper and reproduced in SUMO. Episode length 3600 s from an empty network. |
| **Which metric?** | "Delay (s)", the y-axis of Figure 4. In the codebase this is the per-trip mean of SUMO tripinfo `timeLoss` over all trips in the episode, including unfinished and undeparted vehicles (v2.0 additionally adds `departDelay`). |
| **How measured?** | 5 random seeds, 100 episodes, learning curves smoothed with a 5-episode sliding window. Max-Pressure does not learn, so it appears as a flat dashed reference line. |
| **Warm-up?** | None. Whole-episode average from an empty network. |
| **What is "Max-Pressure" here?** | RESCO's `MAXPRESSURE`: greedy `argmax` over the 8 `phase_pairs` of per-movement `(inbound sticky-queued − downstream sticky-queued)`, no min green, no saturation-flow weighting, sensing truncated at 200 m. |

**Three caveats that change how `D-013` should read this number.**

1. **The two underlying delay values are never printed.** Table 1 covers only Ingolstadt and
   Cologne (Single / Corridor / Region) and lists only IDQN, IPPO, MPLight and FMA2C — **it
   contains no Max-Pressure row and no 4×4 Grid column**. The 11% is stated as a percentage
   in prose and can only be eyeballed off Figure 4. It is not independently re-derivable from
   the paper.
2. **It is a validation number, not a benchmark result.** Its entire purpose in the paper is
   to show that RESCO's MPLight reimplementation behaves like the original (13% → 11%). The
   paper's actual conclusion about MPLight is the opposite in tone: §4.2 and §4.3 report that
   MPLight *diverges* on Ingolstadt Region, that "MPLight, in our experiments, works well in
   scenarios with similarly structured intersections. However, in scenarios with varying
   irregular intersections we observed divergence in learning", and §4.3 concludes that
   "synthetic scenarios […] relate poorly to more realistic scenarios from the perspective of
   gauging the performance of reinforcement learning algorithms."
3. **Table 1 reports the best-performing episode**, not final or mean performance —
   "the best performing episode (not necessarily the final performance) of each algorithm
   averaged over five random seeds". Selecting the maximum over ~100 noisy episodes is an
   optimistically biased estimator. It does not directly contaminate the 11% (which comes
   from Figure 4) but it does mean **no number in RESCO's Table 1 is comparable to a
   pre-registered measurement-window mean of ours.**

### What we would have to match to claim a comparable number

To place our own MPLight-vs-Max-Pressure figure next to RESCO's 11%, we would have to adopt,
simultaneously: their sticky 200 m-truncated queue definition (`D-025` violation), their
12-movement / 8-phase-pair action space, 5 s Δt with 3 s yellow and **no min green**
(`D-020` violation), no warm-up and a whole-episode window (`D-018` violation), delay as
mean tripinfo `timeLoss` over all trips including undeparted (`D-006`-adjacent but not
identical), unpaired seeds (`D-017` violation), and the Chen et al. Config-4 demand on their
synthetic 4×4 grid.

**Recommendation:** do not try. Four settled decisions would have to be violated to match one
prose percentage on a synthetic validation scenario. What we *can* legitimately do is state a
**directional** claim — "our learned controller improves on Max-Pressure by X% under our
definitions, which is the same order as the 11–13% reported in the literature under different
definitions" — with the divergences in §5 cited. `D-013`'s rationale sentence
("Published gaps of learned methods over Max-Pressure are on the order of 11–13%") is
accurate but should be read as *the synthetic-grid figure*, not a figure that survives on
realistic networks. **This is an escalation item — see §8.**

---

## 7. Build or reuse, per component

Framing: `02_PROJECT_CHARTER.md` §2.1 Consequence 3 makes reimplementation a legitimate
*learning* choice; `D-031` makes it an efficiency question. The tiebreaker used below is:
**reuse where the artifact is data or a well-tested external primitive; build where the
artifact encodes one of our settled decisions.** Every component that encodes `D-006`,
`D-020` or `D-025` must be ours, because adopting someone else's implementation of it silently
adopts their decision instead.

Per the ticket's Non-goal 1, none of this adopts anything. These are recommendations.

| Component | Recommendation | Reasoning |
| --- | --- | --- |
| **Environment wrapper** | **BUILD** | Every candidate embeds a decision we have already made differently: sumo-rl swallows deferred requests and cannot express all-red (`D-020`, `D-023`); RESCO has no min/max green and needs hand-authored per-signal YAML; LibSignal routes through a CityFlow roadnet; PyTSC defaults to a binary action space `D-020` explicitly rejected. All four also lack warm-up, measurement window and paired seeding. Retrofitting `D-008`/`D-017`/`D-018` into any of them is more work than writing our own thin adapter, and leaves us maintaining a fork. **Study PyTSC's `common/` + `backends/` split as the model for the `D-002` seam** — it is the best worked example available — but write the code. |
| **Baseline controllers** | **BUILD** — non-negotiable | `D-013` requires Webster, our actuated, SUMO gap-actuated and Max-Pressure. **Zero of the four projects implement the first three.** The fourth, Max-Pressure, exists in three of them and each is unusable for us: RESCO's is correct in form but defined over a sticky queue (`D-025` violation, and it changes the controller); LibSignal's is count-based, not queue-based; PyTSC's is outright buggy (absolute value on the pressure term, and `out_lane_vehicles` assigned rather than accumulated). Max-Pressure is ~30 lines. Write it against our `Queue` type. |
| **Scenario format** | **BUILD (generate), REUSE (validate against)** | Our scenarios are parametrically generated (`T1.2`, `T1.3`) from a config, which none of these do for our purposes — they ship fixed nets. Build the generator. **Reuse RESCO's `grid4x4`, `arterial4x4`, `cologne1` and `ingolstadt1` net + route files as read-only validation fixtures** once we reach multi-intersection work: they are calibrated, freely licensed (Cologne CC BY-NC-SA, Ingolstadt GPL-3) and widely cited, so "does our pipeline load a real network" becomes a testable question. Do **not** adopt RESCO's per-signal YAML — PyTSC shows the lane sets and neighbour graph can be parsed from the net file, and hand-authored topology is a decision recorded in a config file rather than in the register. |
| **Metrics** | **BUILD** | This is the highest-stakes "build" of the five. `07_EXPERIMENT_METHODOLOGY.md` §2.5 already requires one definition and one implementation. Two of the four report a dimensionless speed deficit as "delay"; one reports the lane vehicle count as "queue"; one reports vehicles-in-network as "throughput". None computes the per-vehicle-type split §2.4 requires from M1, and none does the three-way trip accounting `D-022` requires. There is nothing here to reuse. **Reuse SUMO's native outputs instead of anyone's wrapper**: `tripinfo` (`timeLoss`, `duration`, `waitingTime`, `departDelay`, plus `write-unfinished` / `write-undeparted`) and `getLastStepHaltingNumber` are the primitives, and `D-006` already says `timeLoss` is preferred *because* it is native and cannot drift from our own implementation. |
| **Analysis** | **BUILD (thin), REUSE the libraries** | None of the four does paired comparison, common random numbers, confidence intervals on differences, or MSER-5 warm-up truncation. RESCO's analysis (`utils/logs.py`, `utils/graph.py`) parses its own log format and plots ±1 std over 5 unpaired seeds; it is not reusable and would import the best-episode selection rule (§6). Build a thin layer over pandas/scipy/matplotlib per `D-004`. This is a small component and the statistics are the deliverable — see `08_AGENT_HANDOFF_PROTOCOL.md` §7, do not build a framework here. |

### 7.1 Does any of them already do substantially everything M1–M3 plan to do?

**No — but the answer is closer for M1 than is comfortable, and the reason it is "no" is
specific and worth stating.**

| Milestone | Closest project | Gap |
| --- | --- | --- |
| **M1** — single intersection, oracle observation, honest baselines | RESCO covers roughly 60% of the *plumbing*: SUMO wrapper, phase-selection action space, Max-Pressure, a benchmark scenario set, multi-seed runs, tripinfo-based delay. | It covers **none of the honest-baselines half**: no Webster, no actuated, no SUMO gap-actuated cross-check, no paired seeds, no warm-up, no measurement window, no Δt sensitivity check, no three-way exit accounting, no run manifest, and a queue definition that changes what Max-Pressure *is*. M1's exit criteria are almost exactly the list of things RESCO does not do. |
| **M2** — versioned trace format and 2D replay renderer with research overlays | None. | RESCO/LibSignal/PyTSC render via `sumo-gui` or CityFlow's replay viewer. There is no simulator-decoupled trace format and no research overlay anywhere. `D-009`'s record-then-replay design has no prior art in this set. |
| **M3** — parametric camera model, `TrueState`/`Observation` type separation, sensing–control gap | PyTSC's `obs_dropout_prob` and `visibility` window, and RESCO's `max_distance = 200 m` truncation. | These are *incidental* sensing limits, not sensor models: a scalar Bernoulli drop and a radius. None has FOV, orientation, distance-dependent detection probability, position/speed noise, classification confidence or latency. Critically, **none has a type-level separation between true state and observation** — every one of them hands the controller a numpy array derived directly from TraCI. `01_CRITICAL_REVIEW.md` R-5 / charter S6 have no prior art here at all. |

The honest summary: **the prior art solves the part of M1 that is easy to rewrite and skips
the part that is hard to get right.** Reimplementing the wrapper costs us a few days;
reimplementing the baselines and the methodology is the project. That is an argument for
building, not against.

---

## 8. Escalation to the architect

Per `08_AGENT_HANDOFF_PROTOCOL.md` §8. Three items, all decision-level.

### 8.1 `D-013`'s rationale sentence should be qualified

**Attempted:** confirming the "11–13% gap over Max-Pressure" figure that `D-013` cites as its
justification for making Max-Pressure mandatory.

**Finding:** the figure is real but narrower than the sentence implies. RESCO's 11% is a
**validation result on a synthetic symmetric 4×4 grid** with demand copied from the MPLight
paper, whose only purpose was to show that RESCO's reimplementation reproduces Chen et al.'s
13%. On RESCO's *realistic* scenarios the paper reports MPLight diverging and concludes that
synthetic scenarios "relate poorly to more realistic scenarios". The two underlying delay
values are never printed; Table 1 contains no Max-Pressure row.

**Options:** (a) leave `D-013` as-is — the decision (Max-Pressure is mandatory) is unaffected,
only its rationale sentence is loose; (b) amend the rationale to say "on synthetic grid
networks; on realistic irregular networks the published picture is mixed and learned methods
frequently lose"; (c) additionally add to `D-013` an explicit statement that we will not claim
comparability to published percentages.

**Recommendation (labelled as a recommendation):** (b) plus (c). The decision itself is well
made and if anything *better* supported by the realistic-scenario results — Max-Pressure is a
strong baseline there, which is exactly why it must be beaten. But a rationale that reads as
"RL beats Max-Pressure by 11–13%" will, three milestones out, become an expectation that a
null result has to argue against.

### 8.2 `D-025`'s spike question is answerable now, and the answer has a second half

**Attempted:** the spike `D-025` requires — "confirm what SUMO's native halting counters
actually measure, specifically whether they apply the duration condition or only the speed
threshold."

**Finding (partial, from prior-art source rather than from SUMO):** every project that uses
`getLastStepHaltingNumber` (sumo-rl, PyTSC) treats it as a pure speed threshold, and sumo-rl's
own source comment says so: *"In SUMO, a vehicle is considered halting if its speed is below
0.1 m/s"*. No project applies a duration condition. **This is consistent with `D-025`'s
1 s condition being ours alone, i.e. our queue counter cannot be `getLastStepHaltingNumber`
and must be computed by us.** I have not verified this against SUMO itself — that requires
T0.0 and belongs to T0.5.

**The second half is the part worth a decision.** `D-025` says the controller queue and the
metric queue are the same by default. Given that our queue will then differ from the queue in
every published Max-Pressure result, our Max-Pressure is a slightly different controller from
the published one. That is fine and defensible, but it should be **written down as an
intended divergence in `D-025`** rather than discovered at M5 when someone asks why our
Max-Pressure numbers do not line up.

**Recommendation:** add one line to `D-025` recording that the 1 s duration condition is a
deliberate divergence from all four surveyed projects, and that it changes Max-Pressure's
input, not only our reporting.

### 8.3 No prior art for `D-020`'s request-outcome record — confirming it is ours to design

**Attempted:** finding a reference implementation for the constraint layer's
GRANTED / DEFERRED / HELD / FORCED / REJECTED outcome record (the T1.6 contract).

**Finding:** none of the four records anything. sumo-rl silently holds; RESCO has no
constraints to violate; LibSignal defers inside each controller; PyTSC exposes an action
*mask*, which is the closest thing and is genuinely a good idea — it lets a controller avoid
making an illegal request rather than making one and being refused — but it still records no
outcome.

**This is not a blocker.** It is reported because `D-020`'s known-gap paragraph (what happens
when max green expires mid-transition) asks for confirmation at implementation, and prior art
offers no precedent either way: **no surveyed project models max green and a transition
simultaneously**, so there is nothing to copy. The provisional answer in `D-020` (the override
waits, and the overshoot is recorded) stands on its own reasoning.

**Recommendation:** consider adding the action **mask** to the T1.6 contract *alongside* the
outcome record, not instead of it. The mask is cheap, it is what an RL controller at M7 will
want, and it makes REJECTED rare rather than routine. Flagging it here rather than building
it, per §8 ("do not pick an option and proceed").

---

## 9. Specific things worth copying

Concrete, in rough order of value.

### 9.1 SUMO command-line flags (from RESCO)

RESCO's launch flags are the best in the set and several map directly onto `D-008` and
`D-022`:

| Flag | Why |
| --- | --- |
| `--time-to-teleport -1` | `D-008` requirement. RESCO passes it unconditionally; we additionally **assert** it. |
| `--tripinfo-output.write-unfinished True` | Gives us the "still in-network" leg of `D-022`'s three-way accounting for free, from a native output. |
| `--tripinfo-output.write-undeparted True` | Gives us insertion loss per vehicle rather than as a bare counter. |
| `--eager-insert` | RESCO's comment: "Undeparted not written correctly without this, slows down simulation though". Note the performance caveat for `D-031`. |
| `--no-step-log True`, `--duration-log.disable True` | (PyTSC also) removes per-step console I/O from the hot loop. |

### 9.2 Parameter values worth adopting as starting priors

Not as decisions — as the literature's centre of mass, so our defaults are defensible and our
Δt sensitivity check (`D-020`) has a reference point.

| Parameter | RESCO | LibSignal | PyTSC | sumo-rl | Note |
| --- | --- | --- | --- | --- | --- |
| Decision interval Δt | 5 s | 10 s | 5 s | 5 s | `D-020`'s 5 s suggestion for Max-Pressure is the consensus value. |
| Yellow | 3 s | inferred | 5 s | 2 s | 3 s is the most defensible; RESCO cites Ma & Wu. |
| All-red | 2 s (conditional) | — | — | — | Only RESCO models it at all. |
| Min green | — | 10 s | 5 s | 7 s effective | Wide spread; ours is a real decision, not a copy. |
| Max green | — | — | 60 s | 50 s (off) | |
| Sensing radius | 200 m | distance-limited | 75 m (10 bins × 7.5 m) | unlimited | Directly relevant to M3 sensor placement — 200 m is Chen et al.'s figure, 50 m is Ma & Wu's; the RESCO paper §2.2 notes this varies by publication and materially changes results. |
| Vehicle size + min gap | 5 + 2.5 m | — | 7.5 m | 2.5 m gap | The 7.5 m occupancy unit is a useful queue-length-in-metres primitive for `D-025`'s secondary unit at M4. |
| Episode length | 3600 s | 3600 s | 3600 s | 20000 s default | 3600 s is universal. |
| Replications | 5 trials | 1 | 10 test episodes | n/a | All far below `D-017`'s ≥30 paired. Worth noting in our results document as a methodological improvement over the field. |

### 9.3 Conventions and code patterns

1. **PyTSC's `common/` + `backends/` layout** — the cleanest available illustration of where
   the `D-002` backend seam falls: abstract `simulator`, `retriever`, `network_parser`,
   `traffic_signal`, `metrics` with one concrete package per backend. Study before writing
   `T1.4`.
2. **PyTSC's action mask** (`get_allowable_phase_switches`) — see §8.3.
3. **PyTSC's validity subscription set** — `n_teleported`, `n_colliding`,
   `n_emergency_brakes`, `n_loaded`, `n_departed`, `n_arrived` in a single
   `traci.simulation.subscribe` call. That is exactly `D-008`'s counter set, obtained at zero
   per-step cost. Copy the subscription list; add the acting-on-it that PyTSC omits.
4. **TraCI context subscriptions around a junction** (RESCO's
   `traci.junction.subscribeContext(signal_id, CMD_GET_VEHICLE_VARIABLE, radius, [...])`) —
   one call per junction per step returning every nearby vehicle's variables, instead of
   per-vehicle polling. This is the `D-031`-compliant pattern for M3's sensor model, where we
   will need per-vehicle position and speed within a radius. Note that RESCO then *undoes*
   the benefit by iterating in Python; the subscription itself is the good part.
5. **RESCO's 12-movement naming (`'N-E'`, `'S-S'`, …) and 8 phase pairs** — a compact,
   readable convention for naming turn movements and NEMA-style phases. Worth borrowing as
   *nomenclature* in `05_DOMAIN_MODEL.md`, independent of RESCO's hand-authored YAML.
6. **PyTSC's `flickering_coef`** — penalising phase changes is a standard term we will want
   when `D-024` (objective function) is decided; noting it exists.
7. **`obs_dropout_prob`** (PyTSC) — the only sensing-degradation knob in the prior art.
   A useful *floor* for M3: whatever our camera model does, it should reduce to this when all
   other parameters are ideal.

### 9.4 Test scenarios worth keeping as fixtures

Read-only, for validation, not as our primary scenarios:

| Scenario | Source | Use |
| --- | --- | --- |
| `cologne1` | RESCO (`nets/RESCO/cologne1`), CC BY-NC-SA | Single real intersection with a real signal program. Good M1 sanity check that our pipeline handles a non-synthetic net. |
| `ingolstadt1` | RESCO, GPL-3 | Same, second geometry. |
| `grid4x4` | RESCO | 16-signal synthetic grid; the M5 multi-intersection target and the network the 11% figure was measured on. |
| `arterial4x4` | RESCO | Two-lane arterials + one-lane avenues; the natural M5b green-wave test case. |
| `single-intersection` | sumo-rl | Minimal `.nod`/`.edg`/`.net`/`.rou`/`.sumocfg` set — the smallest complete SUMO example in the set, useful as a T0.2 reference while our own generator is being written. |

### 9.5 Anti-patterns confirmed by prior art

Worth recording because they are review-checklist items (§6, §7) that all four projects
demonstrate:

- **Per-vehicle TraCI polling inside the step loop** — sumo-rl's
  `get_accumulated_waiting_time_per_lane` and PyTSC's `_compute_lane_position_matrix`. Both
  sit in default observation/reward paths.
- **A results-affecting default that disagrees with its own documentation** — sumo-rl's
  `max_green` (docstring 60 and "ignored", code 50 and conditionally honoured).
- **A validity setting disabled by magnitude rather than by flag** — PyTSC's
  `time_to_teleport: 10000`, safe only while episodes are shorter than that.
- **Config keys that never reach the simulator** — PyTSC's `seed`, `max_depart_delay` and
  `waiting_time_memory` on the SUMO backend. A parameter that appears to be set and is not is
  worse than one that is absent.
- **A metric name that does not match its computation** — LibSignal's `queue_length`,
  `throughput` and `lane_delay`, each carrying a `TODO` comment questioning itself.

---

## 10. Summary

- **Build all five components.** Reuse SUMO's native outputs, RESCO's SUMO flags, RESCO's
  test networks as fixtures, and PyTSC's architecture as a reference. Adopt none of the four
  as a dependency.
- **The decisive reason is `D-013`.** Not one of the four implements Webster, an actuated
  controller, or the SUMO gap-actuated cross-check, and each Max-Pressure implementation is
  either defined over a queue we have rejected, defined over vehicle counts, or buggy.
- **Comparability to published numbers is limited by design, not by accident.** Queue
  definition, delay definition, warm-up, measurement window and seeding all differ, and each
  difference is a decision we made deliberately. Directional comparison is legitimate;
  numerical comparison is not. This should be stated in every results document.
- **No project does M2 or M3 at all.** The trace format, the renderer, and the
  `TrueState`/`Observation` separation have no prior art in this set.
- **Three escalation items** in §8, none blocking: qualify `D-013`'s rationale sentence,
  record `D-025`'s 1 s condition as an intended divergence that changes Max-Pressure's input,
  and consider adding an action mask alongside the T1.6 outcome record.
