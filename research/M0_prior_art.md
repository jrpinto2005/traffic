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
