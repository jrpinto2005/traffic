# Canonical Domain Model

**Status:** Active
**Version:** 1.0
**Governed by:** `02_PROJECT_CHARTER.md`
**Implements:** `D-003`, `D-010`, `D-011`, `D-012`, `D-020`, `D-022`, `D-023`, `D-025`
**Supersedes:** `00_RESEARCH_SPECIFICATION.md` §§7, 11–19

---

## 1. What this model is, and what it is not

Per `D-003`, the canonical domain model is a **read-only projection plus a command surface**
over SUMO. It is not a re-implementation of traffic dynamics, and the entities below are not
simulation objects — they are the vocabulary the project's own layers use to talk about what
SUMO is doing.

This resolves the central contradiction of the original specification
(`01_CRITICAL_REVIEW.md` C-1): `00_RESEARCH_SPECIFICATION.md` §§11–19 read as a specification
for building a microsimulator. They are reinterpreted here as a description of concepts we
reason about.

### 1.1 The inclusion test

> **An attribute enters this model only if you can name the controller, sensor, metric,
> estimator, or experiment that reads it.**

If you cannot, it stays in SUMO. This test is applied at code review and it is not
negotiable — it is the only thing preventing the abstraction tax described in
`01_CRITICAL_REVIEW.md` R-2, where a parallel model maintained against a single backend
becomes pure cost.

Applied throughout this document. Where a field that "obviously belongs" is absent, its
absence is deliberate and usually annotated.

### 1.2 Conventions

**Units are in field names.** `length_m`, `speed_mps`, `time_loss_s`, `flow_vph`. This is not
style: unit confusion between m/s and km/h, and between veh/h and veh/s, is the most common
source of silent numerical error in traffic work.

**IDs are integers, resolved once at load.** SUMO identifies everything by string. String-keyed
lookups inside the step loop are a known hot path (`D-031`), so every string ID is resolved to
a dense integer index when the network is loaded, and the mapping is kept for reporting and
for talking to the backend.

```python
LaneId  = NewType("LaneId", int)
EdgeId  = NewType("EdgeId", int)
JunctionId = NewType("JunctionId", int)
IntersectionId = NewType("IntersectionId", int)   # a signalized junction
MovementId = NewType("MovementId", int)
LaneConnectionId = NewType("LaneConnectionId", int)
SignalGroupId = NewType("SignalGroupId", int)
PhaseId = NewType("PhaseId", int)
VehicleId = NewType("VehicleId", int)
SensorId = NewType("SensorId", int)


class VehicleType(StrEnum):
    CAR = "car"
    MOTORCYCLE = "motorcycle"
```

`LaneConnectionId` and `SignalGroupId` were used by fields in §2 before being listed here;
added 2026-08-18 after T1.2 had to infer them.

`VehicleType` is `{CAR, MOTORCYCLE}` per `00_RESEARCH_SPECIFICATION.md` §17 and `D-013` —
motorcycles are first-class from the start, and the type-mix parameter exists from day one even
though M1 runs cars only, so that M4 needs no schema change. Its **dynamics** live in SUMO's
`vType` and are never interpreted by us (`D-003`); this enum only names the classes that metrics
must separate (`07_EXPERIMENT_METHODOLOGY.md` §2.4).

**Static structure is frozen; dynamic state is rebuilt each step.** Network types are
immutable after load. State types are constructed per step from one batched subscription
fetch (`06_ARCHITECTURE.md` §5.2).

---

## 2. Network structure

### 2.1 Edge

Per `D-012`, edges are **unidirectional**, following the SUMO and OpenStreetMap convention.
A two-way street is a pair of opposing edges. There is no bidirectional primitive, because
inventing one would create a translation problem at both the backend boundary and the future
OSM-import boundary for no benefit.

```python
@dataclass(frozen=True, slots=True)
class Edge:
    id: EdgeId
    lanes: tuple[LaneId, ...]        # ordered right-to-left in travel direction
    from_junction: JunctionId
    to_junction: JunctionId
    length_m: float
    opposite: EdgeId | None          # the reverse edge of the same street, if any
```

`00_RESEARCH_SPECIFICATION.md` §11 called this a "road segment". Renamed to `Edge` to match
SUMO and graph terminology, and because "segment" invites confusion with sub-parts of a link.

**Absent by the inclusion test:** geometry beyond length (the renderer reads geometry from the
network file directly, not from `TrueState`), capacity (derived from lanes and speed limit
where needed, not stored), and road class.

### 2.2 Lane

```python
@dataclass(frozen=True, slots=True)
class Lane:
    id: LaneId
    edge: EdgeId
    index: int                       # 0 = rightmost in travel direction
    length_m: float
    width_m: float                   # read only when the sublane model is enabled (D-026)
    speed_limit_mps: float
    successors: tuple[LaneConnectionId, ...]
    adjacent_left: LaneId | None
    adjacent_right: LaneId | None
    allowed_types: frozenset[VehicleType]
```

Per `D-011`, **two relations, not one graph**:

| Relation | Direction | Route-traversable | Represents |
| --- | --- | --- | --- |
| `successors` | Longitudinal | **Yes** | Continuation within an edge, and crossings through a junction |
| `adjacent_left` / `adjacent_right` | Lateral | **No** | Parallel same-direction lanes; the lane-change relation |

Merging them, as `00_RESEARCH_SPECIFICATION.md` §13 proposed, means every routing, distance,
and reachability computation must filter edges by type — and forgetting the filter produces
plausible, wrong answers. Keeping them separate makes the wrong computation impossible to
write rather than merely discouraged.

### 2.3 LaneConnection

The single edge type of the longitudinal graph.

```python
@dataclass(frozen=True, slots=True)
class LaneConnection:
    id: LaneConnectionId
    from_lane: LaneId
    to_lane: LaneId
    via_junction: JunctionId | None  # None = continuation within an edge
    turn: TurnDirection              # THROUGH | LEFT | RIGHT | U_TURN
```

**Absent:** `geometry`, `priority`, and `constraints` from
`00_RESEARCH_SPECIFICATION.md` §13. Right-of-way between conflicting connections is expressed
by the junction's conflict matrix (§2.5), which is one representation instead of two that
would drift apart. Geometry is the renderer's concern and it reads the network file.

### 2.4 Junction and SignalizedIntersection

Per `D-010`, one word split into two along the line between topology and control.

```python
@dataclass(frozen=True, slots=True)
class Junction:
    id: JunctionId
    incoming_lanes: tuple[LaneId, ...]
    outgoing_lanes: tuple[LaneId, ...]
    connections: tuple[LaneConnectionId, ...]
    conflicts: ConflictMatrix
    position_xy: tuple[float, float]


@dataclass(frozen=True, slots=True)
class SignalizedIntersection:
    id: IntersectionId
    junction: JunctionId
    signal_groups: tuple[SignalGroup, ...]     # invariant: len >= 2
    phases: tuple[Phase, ...]                  # validated against the conflict matrix
    timing: SignalTiming                       # min/max green, yellow, all-red
    controlled_connections: tuple[LaneConnectionId, ...]   # display order = SUMO link index (D-034)
```

`controlled_connections` lists the connections the signal displays, in the order of SUMO's
state string, so that a displayed red/yellow/green string can be read back as a canonical phase
(`D-034`). Added 2026-10-07.

A `SignalizedIntersection` **is a** `Junction` with signals — specialisation, not composition.
Signalizing promotes; de-signalizing demotes; nothing is created or destroyed. This is what
makes "what if we remove this signal?" a valid experiment rather than an entity deletion.

`|SignalGroups| >= 2` from `00_RESEARCH_SPECIFICATION.md` §8.1 is correct and applies **here
only**. Unsignalized junctions — every grid boundary node, every priority merge — are
first-class and nameable.

### 2.5 ConflictMatrix

The primitive from which phases are derived. Lives on `Junction`, not on
`SignalizedIntersection`, because a conflict between two movements is a fact of geometry
whether or not a signal is present.

```python
class Compatibility(IntEnum):
    COMPATIBLE  = 0    # may run simultaneously, no interaction
    PERMITTED   = 1    # may run simultaneously, one yields to the other
    CONFLICTING = 2    # may never run simultaneously

@dataclass(frozen=True, slots=True)
class ConflictMatrix:
    movements: tuple[MovementId, ...]
    matrix: npt.NDArray[np.int8]     # (n, n) of Compatibility; symmetric except PERMITTED
```

Three values rather than two, per `D-023`. A permitted left turn is legal *and* conflicting —
it crosses opposing through traffic and yields to it. Collapsing that into a binary either
forbids a movement real intersections allow, or permits one they do not. It also changes the
capacity model, because a permitted movement discharges at a reduced saturation flow.

`PERMITTED` is asymmetric: it records which movement yields.

Seeded from SUMO's computed junction conflicts, overridable per scenario. **Protected turns
only at M1**; the `PERMITTED` value exists in the schema from day one so no migration is
needed when scenarios require it, probably at M5.

### 2.6 Movement — a view, not an entity

Per `D-011`, `Movement` is **derived, never stored**: the subset of lane connections crossing
a junction, grouped by (approach edge, turn direction).

```python
@dataclass(frozen=True, slots=True)
class Movement:
    id: MovementId
    junction: JunctionId
    from_edge: EdgeId
    to_edge: EdgeId
    turn: TurnDirection
    connections: tuple[LaneConnectionId, ...]
    signal_group: SignalGroupId | None
```

`00_RESEARCH_SPECIFICATION.md` §§13 and 15 described `Movement` and `LaneConnection` as
separate entities. They are the same topology described twice, which means two places to keep
in sync with the backend and an inevitable divergence. Controllers and signal logic address
movements; the topology stores connections; the view is computed once at load.

### 2.7 SignalGroup and Phase

```python
@dataclass(frozen=True, slots=True)
class SignalGroup:
    id: SignalGroupId
    movements: tuple[MovementId, ...]

@dataclass(frozen=True, slots=True)
class Phase:
    id: PhaseId
    green_groups: frozenset[SignalGroupId]

@dataclass(frozen=True, slots=True)
class SignalTiming:
    min_green_s: float
    max_green_s: float               # 0.0 disables the max-green override
    yellow_s: float
    all_red_s: float
```

Per `D-023`, phases are **authored per scenario, then validated at load**. Every declared
phase is checked against the conflict matrix and any phase containing a `CONFLICTING` pair is
rejected with an error naming the pair.

Authoring rather than enumerating is deliberate: automatic enumeration from the matrix
produces a large set of legal-but-nonsensical phases that no engineer would deploy, and every
one of them would pollute the controller's action space.

**Transitions are not phases.** Yellow and all-red are properties of a change from one phase
to another, executed by the constraint layer (`D-020`). Modelling them as phases would place
them in the action space, and no controller should be able to *choose* "yellow" — it is a
consequence of switching, not a decision.

---

## 3. Dynamic state

### 3.1 TrueState

What actually happened. Per `06_ARCHITECTURE.md` §4, readable by exactly four consumers —
sensors, metrics, the trace writer, and the snapshot writer — and **never by a controller.**

```python
@dataclass(frozen=True, slots=True)
class VehicleState:
    id: VehicleId
    type: VehicleType
    lane: LaneId
    position_on_lane_m: float
    position_xy: tuple[float, float]   # sensors need world coordinates for FOV geometry
    speed_mps: float
    time_loss_s: float                 # accumulated; D-006
    waiting_time_s: float              # accumulated
    stop_count: int                    # accumulated
    is_halting: bool                   # speed < 0.1 m/s; D-025
    halting_since_s: float | None      # for the >= 1 s duration condition

@dataclass(frozen=True, slots=True)
class LaneState:
    lane: LaneId
    queue_count: int                   # D-025, primary
    queue_length_m: float              # secondary, reported from M4
    vehicle_count: int
    mean_speed_mps: float

@dataclass(frozen=True, slots=True)
class SignalState:
    intersection: IntersectionId
    active_phase: PhaseId
    phase_started_s: float          # when the phase became active — transition start
    green_started_s: float | None   # when its green began; None while in transition
    in_transition: bool

@dataclass(frozen=True, slots=True)
class TrueState:
    time_s: float
    vehicles: tuple[VehicleState, ...]
    lanes: tuple[LaneState, ...]
    signals: tuple[SignalState, ...]
    counters: RunCounters
```

`halting_since_s` exists because `D-025` requires **one second of continuous halting**, not an
instantaneous speed check — the distinction `00_RESEARCH_SPECIFICATION.md` §19 correctly
insisted on, made testable.

**Absent by the inclusion test:** acceleration (no consumer — SUMO integrates it, nothing
reads it), route (metrics need the origin and destination recorded at insertion and arrival,
not the full path carried every step), desired speed (a `vType` parameter, in the manifest),
and lateral position (added only when `D-026` enables the sublane model).

### 3.2 RunCounters

The validity and accounting counters, carried in state so they land in the manifest rather
than being reconstructed.

```python
@dataclass(frozen=True, slots=True)
class RunCounters:
    teleports: int                     # D-008; must remain 0
    insertion_failures: int            # D-008
    gridlock_detected: bool            # D-008
    arrived_at_sink: int               # D-022, served
    arrived_mid_link: int              # D-022, served (attrition)
    still_in_network: int              # D-022, unserved
```

The three-way trip accounting of `D-022` is a **first-class part of state**, not a
post-processing step, because collapsing served and unserved is the failure mode
`07_EXPERIMENT_METHODOLOGY.md` §4 exists to prevent.

---

## 4. Observation and estimate

### 4.1 Observation

Per `D-005`, the reserved extension point for a real perception pipeline imposes a hard design
constraint: **`Observation` is a stream of detections with uncertainty, and nothing in it
references how it was produced.** No field mentions field of view, range, or detection
probability. A pixel-derived detection stream must substitute for the parametric one with no
change to estimators, controllers, or experiments — and that is only true if the type does not
encode the parametric model.

```python
@dataclass(frozen=True, slots=True)
class Detection:
    sensor: SensorId
    observed_at_s: float               # when the sensor sampled
    position_xy: tuple[float, float]   # estimated
    position_cov: tuple[float, float, float]   # xx, yy, xy
    speed_mps: float                   # estimated
    speed_std: float
    vehicle_class: VehicleType
    class_confidence: float            # [0, 1]
    track_id: int | None               # None if the sensor does not track
    lane: LaneId | None                # the sensor's lane assignment; None if it cannot assign
    stationary_s: float | None         # time seen stationary, 0.0 while moving; None if untracked

@dataclass(frozen=True, slots=True)
class Observation:
    received_at_s: float               # observed_at_s + latency
    detections: tuple[Detection, ...]
    observed_lanes: frozenset[LaneId]  # coverage: which lanes this observation speaks about
```

`observed_lanes` is the honest way to represent partial coverage. Absence of a detection on a
covered lane is evidence of absence; on an uncovered lane it is no evidence at all. Without
this distinction an estimator cannot tell "empty" from "unobserved", and every partial-sensing
result would be wrong in the same direction.

`track_id` is nullable because tracking is a sensor capability, not a given. Whether the
controller has access to identity across frames is an experimental variable at M3.

`lane` and `stationary_s` were added 2026-10-07 (`D-033`). Without them an estimator cannot
place a detection on a lane — the domain has no lane geometry — nor apply `D-025`'s ≥ 1 s
halting condition from samples taken every Δt. Both are ordinary outputs of traffic video
analytics, so a pixel pipeline can fill them, and both are things a camera can get wrong.

### 4.2 EstimatedState

What the controller believes. The only state a controller ever sees.

```python
@dataclass(frozen=True, slots=True)
class LaneEstimate:
    lane: LaneId
    queue_count: float                 # non-integer: it is an estimate
    queue_count_std: float
    last_observed_s: float | None      # None = never observed
    vehicle_count: float

@dataclass(frozen=True, slots=True)
class EstimatedState:
    time_s: float
    lanes: tuple[LaneEstimate, ...]
    signals: tuple[SignalState, ...]   # the controller knows its own signals exactly
```

`queue_count` is a float with a standard deviation, deliberately. A controller written against
an integer queue count will silently pretend certainty it does not have, and the whole point of
M3 is to measure what happens when that certainty is false.

`last_observed_s` carries the staleness that `D-021`'s attrition problem produces: a
counting estimator cannot distinguish "the vehicle reached a local destination" from "the
downstream camera missed it", so it accumulates bias, and an estimate's age is the minimum
information needed to reason about that.

Signal state is exact because a real controller knows what it commanded.

---

## 5. Actions

Per `D-020`, phase selection through a constraint layer. Full contract in
`08_AGENT_HANDOFF_PROTOCOL.md` §9; the types are:

```python
@dataclass(frozen=True, slots=True)
class PhaseRequest:
    intersection: IntersectionId
    phase: PhaseId

class RequestOutcome(StrEnum):
    GRANTED = "granted"; DEFERRED = "deferred"; HELD = "held"
    FORCED = "forced";   REJECTED = "rejected"

@dataclass(frozen=True, slots=True)
class ActionResult:
    outcome: RequestOutcome
    active_phase: PhaseId
    reason: str
    seconds_until_actionable: float
```

Every controller acts through this, **including fixed-time**, which names the phase its
schedule dictates. That is what makes a schedule and a learned policy comparable: they differ
in how they choose, not in what they are allowed to choose.

---

## 6. Scenario specification

Configuration, not state. Consumed by the scenario layer, passed to the backend, and recorded
in the manifest.

### 6.1 Demand

Per `D-022`, the owner-specified open-boundary link–node flow model: vehicles are **not
conserved** inside the study area.

```python
@dataclass(frozen=True, slots=True)
class SourceSpec:
    edge: EdgeId
    position_m: float | None           # None = edge start (boundary); else a mid-link source
    rate_saturation_fraction: float    # of the receiving approach's saturation flow
    type_mix: Mapping[VehicleType, float]

@dataclass(frozen=True, slots=True)
class TurnRatioSpec:
    junction: JunctionId
    from_edge: EdgeId
    ratios: Mapping[TurnDirection, float]     # sums to 1.0

@dataclass(frozen=True, slots=True)
class AttritionSpec:
    edge: EdgeId
    rate: float                        # fraction of through-flow locally destined

@dataclass(frozen=True, slots=True)
class DemandSpec:
    sources: tuple[SourceSpec, ...]
    turn_ratios: tuple[TurnRatioSpec, ...]
    attrition: tuple[AttritionSpec, ...]
    sink_edges: frozenset[EdgeId]
    seed_stream: str = "demand"
```

Rates are a **fraction of saturation flow**, not absolute veh/h, so that "demand level 0.8"
means the same degree of loading across geometries and is comparable across experiments.

Attrition is **per-edge**. An arterial between two major intersections has low attrition; a
commercial street lined with parking has high attrition. A single global rate misrepresents
both.

Routes are resolved **at insertion** and then fixed. No re-routing, no congestion response —
a deliberate limitation, because route choice and signal control interact and would make a
change in network performance unattributable to the controller.

Realised in SUMO by `jtrrouter` (turn ratios and declared sink edges), `<flow>` with
exponential headways (Poisson arrivals), `departPos` (mid-link sources), and `arrivalPos`
(mid-link attrition). Verified in the M0 spike.

### 6.2 Sensors

```python
@dataclass(frozen=True, slots=True)
class CameraSpec:
    id: SensorId
    position_xy: tuple[float, float]
    orientation_rad: float
    fov_rad: float
    range_m: float
    sampling_rate_hz: float
    detection_probability: float       # may be distance-dependent at A-Step-3
    position_noise_std_m: float
    speed_noise_std_mps: float
    latency_s: float
    seed_stream: str = "sensor"
```

`OracleSpec` carries no parameters. Per `06_ARCHITECTURE.md` §4.1 the oracle is a sensor, not
a bypass — which is what makes a truth leak structurally impossible rather than merely
forbidden.

---

## 7. Canonical ↔ SUMO mapping

| Canonical | SUMO | Note |
| --- | --- | --- |
| `Edge` | `<edge>` | Both unidirectional. Direct correspondence. |
| `Lane` | `<lane>` | Index convention matches (0 = rightmost). |
| `LaneConnection` | `<connection>` | |
| `Junction` | `<junction>` / node | SUMO's `type` attribute distinguishes signalized from priority — the same split as `D-010`. |
| `SignalizedIntersection` | junction with `type="traffic_light"` + `<tlLogic>` | |
| `Phase` | `<phase>` in `<tlLogic>` | Ours holds green groups; SUMO's holds a per-connection state string. Translated both ways through `SignalizedIntersection.controlled_connections`; `TrueState` decodes the displayed string, because SUMO's phase index is always 0 once a controller drives the light (`D-034`). |
| `ConflictMatrix` | Computed junction `<request>` / response matrix | Seeded from SUMO, overridable. |
| `Movement` | No single equivalent | A view over connections; SUMO has no first-class movement. |
| `VehicleType` | `<vType>` | Dynamics parameters live in SUMO and are recorded in the manifest, never interpreted by us (`D-003`). |
| `DemandSpec` | `<flow>` + `jtrrouter` turn files | §6.1 |
| Snapshot | `--save-state` / `--load-state` | `D-032` |

**Integer IDs follow sorted SUMO IDs.** `LaneId(i)` is the *i*-th of all SUMO lane IDs in
sorted order, internal (`:`-prefixed) lanes included; `EdgeId`, `JunctionId` and
`IntersectionId` likewise over edges, junctions and traffic lights. This is the order the
backend already uses (`BackendIndex`), so the network generator and the backend agree without
exchanging a table. Added 2026-10-07.

---

## 8. Invariants

Checked at load for static structure, and by property-based tests for dynamic state.

**Who checks what** — added 2026-08-18 after T1.2 correctly refused to guess. The groups below
are enforced in different places, and `validate_network()` owns only the first two:

| Invariants | Enforced by | Ticket |
| --- | --- | --- |
| 1–8, and the `min_green`/`max_green` clauses of 9 | `validate_network()` at load | T1.2 ✅ |
| 9's `decision_interval_s <= min_green_s` clause | The constraint layer's config validation — `SignalTiming` (§2.7) has no such field; it belongs to the controller layer | T1.7 |
| 10–12 (dynamic state) | The backend adapter must **uphold** these when projecting SUMO state into `TrueState`; frozen dataclasses cannot self-validate cross-field properties | T1.4 |
| 13–14 (validity and trip accounting) | The metrics layer's validity gate | T1.8 |
| 15–16 (demand) | The demand generator, which is where §6's `TurnRatioSpec` and `AttritionSpec` are built | T1.5 |

**Network**
1. Every lane belongs to exactly one edge.
2. Every lane has exactly one travel direction, inherited from its edge.
3. `adjacent_left` / `adjacent_right` connect lanes of the **same** edge only.
4. Every `LaneConnection` with `via_junction` set has both endpoints in that junction's
   incoming and outgoing lane sets.
5. `Edge.opposite`, where set, is symmetric.

**Signals**
6. Every `SignalizedIntersection` has ≥ 2 signal groups.
7. Every declared phase contains no `CONFLICTING` movement pair. Violation is a load error
   naming the pair.
8. Every movement of a signalized junction belongs to exactly one signal group.
9. `min_green_s > 0`, `max_green_s > min_green_s` or `== 0`, `decision_interval_s <=
   min_green_s`.

**State**
10. Every vehicle is on exactly one lane.
11. `is_halting` ⟺ `speed_mps < 0.1`.
12. `queue_count` counts exactly the vehicles halting for ≥ 1 s.
13. `teleports == 0` for any valid run (`D-008`).
14. `arrived_at_sink + arrived_mid_link + still_in_network == ` total inserted.

**Demand**
15. Turn ratios sum to 1.0 per (junction, from_edge), within tolerance.
16. Attrition rates are in [0, 1).

---

## 9. Deliberately absent

| Absent | Where it lives instead |
| --- | --- |
| Car-following, acceleration, braking models | SUMO `vType`. `D-003`, `01_CRITICAL_REVIEW.md` C-1. |
| Lane-change mechanics | SUMO LC2013 / SL2015. The `adjacent` relation is topology only. |
| Vehicle acceleration in state | No consumer. Inclusion test. |
| Route in vehicle state | Origin and destination recorded at insertion and arrival. |
| Geometry beyond length and junction position | The renderer reads the network file. |
| `PedestrianCrossing` | Deferred, `D-029`. Its signal-timing consequence is captured by `min_green_s`. |
| Lateral position | Added when `D-026` enables the sublane model. |
| Capacity as a stored attribute | Derived where needed from lanes and speed limit. |
| Emissions, fuel | Available in SUMO; added when an experiment needs them. |
| A `RoadSegment` distinct from `Edge` | One concept, one name. |

---

## 10. Amendment

Adding a field requires passing the inclusion test in §1.1 and naming its consumer in the
amendment. Adding an entity requires a decision register entry. Removing either requires
confirming no consumer remains.
