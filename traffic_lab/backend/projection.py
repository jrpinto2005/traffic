"""Projection of one `RawStep` into one `TrueState`.

Implements D-003 (projection, not re-implementation: nothing here models
traffic dynamics), D-008 (`RunCounters`, gridlock detection), D-022 (three-way
trip accounting as first-class state), and D-025 (the queue definition).

**This module upholds `05_DOMAIN_MODEL.md` §8 invariants 10-12**, which the
ownership table assigns to T1.4 because `traffic_lab.domain` uses frozen
dataclasses that cannot self-validate cross-field properties:

10. *Every vehicle is on exactly one lane.* `VehicleState.lane` is resolved
    through a lane index built at start from **every** SUMO lane, internal
    junction lanes included, so a vehicle mid-junction still names a lane that
    exists in `TrueState.lanes`. An unknown lane is an error, not a silent skip.
11. *`is_halting` ⟺ `speed_mps < 0.1`.* `is_halting` is computed from
    `speed_mps` here and read from nowhere else, so the two cannot disagree.
    SUMO's own halting counter is deliberately not used as a second source.
12. *`queue_count` counts exactly the vehicles halting for ≥ 1 s.* Also computed
    here, from the same per-vehicle halting records, rather than from
    `lane.getLastStepHaltingNumber()` — which applies no duration condition
    (`research/M0_sumo_semantics.md` §1.3) and would not satisfy the invariant.

Everything transport-specific is upstream in `transport.py`. Projection is
shared, which is what lets the byte-identical-across-transports acceptance test
isolate the part that actually differs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from traffic_lab.backend.config import BackendStartupError
from traffic_lab.backend.transport import RawStep, RawVehicle
from traffic_lab.domain.network import (
    IntersectionId,
    LaneId,
    PhaseId,
    VehicleId,
    VehicleType,
)
from traffic_lab.domain.state import (
    HALTING_SPEED_MPS,
    QUEUE_MIN_HALTING_S,
    LaneState,
    RunCounters,
    SignalState,
    TrueState,
    VehicleState,
)

#: SUMO vehicle classes this project's `VehicleType` ontology covers. D-013 makes
#: M1 cars only while keeping the type-mix parameter present from day one, and
#: `05_DOMAIN_MODEL.md` fixes the canonical set at exactly these two. Anything
#: else is a hard failure rather than a silent coercion to `CAR`.
VEHICLE_CLASS_TO_TYPE = {
    "passenger": VehicleType.CAR,
    "motorcycle": VehicleType.MOTORCYCLE,
}

#: Numerical slack, in metres, on the arrival test below. Small: the test's real
#: work is done by the kinematic bound, not by this.
_ARRIVAL_TOLERANCE_M = 0.1


@dataclass(slots=True)
class _VehicleRecord:
    """The per-vehicle bookkeeping SUMO does not keep for us.

    SUMO exposes neither a continuous-halting timer nor a stop count, so both are
    accumulated here across steps. `last_lane_id` / `last_lane_position_m` /
    `last_speed_mps` are the previous step's values, kept because a vehicle's
    arrival is only observable *after* it has gone: classifying it as a sink or
    mid-link arrival (D-022) needs where it was when last seen.
    """

    canonical_id: VehicleId
    vehicle_type: VehicleType
    halting_since_s: float | None
    stop_count: int
    last_lane_id: str
    last_lane_position_m: float
    last_speed_mps: float


@dataclass(slots=True)
class _SignalRecord:
    """One light's decoded state: its phase, when the phase became active and
    when its green began, and the display they were decoded from.

    SUMO reports none of these in canonical terms, so all are tracked across
    steps -- see `Projector._project_signals`.
    """

    active_phase: PhaseId
    phase_started_s: float
    green_started_s: float | None
    in_transition: bool
    ryg_state: str


@dataclass(slots=True)
class _CumulativeCounters:
    """Run-to-date totals behind `RunCounters`. Serialised into snapshot sidecars."""

    teleports: int = 0
    arrived_at_sink: int = 0
    arrived_mid_link: int = 0
    motionless_steps: int = 0
    gridlock_detected: bool = False


class Projector:
    """Turns successive `RawStep`s into successive `TrueState`s.

    Stateful, because three things `TrueState` requires are not in any single
    SUMO reading: the continuous-halting timers behind D-025's queue, the
    cumulative counters behind D-008, and the three-way split of D-022's trip
    accounting.
    """

    def __init__(
        self,
        *,
        lane_sumo_ids: tuple[str, ...],
        lane_lengths_m: tuple[float, ...],
        intersection_sumo_ids: tuple[str, ...],
        phase_green_links: tuple[Mapping[PhaseId, frozenset[int]], ...],
        start_s: float,
        vehicle_types: dict[str, VehicleType],
        step_length_s: float,
        gridlock_steps: int,
        max_accel_mps2: float,
    ) -> None:
        """`phase_green_links[i]` holds the green link indices of every phase of
        `IntersectionId(i)`, the light `intersection_sumo_ids[i]`
        (`green_link_indices()`, D-034). `start_s` is the simulation's start time,
        when the first phase shown became active."""
        self._lane_sumo_ids = lane_sumo_ids
        self._lane_lengths_m = lane_lengths_m
        # SUMO's string IDs are resolved to dense integers once, at start, so
        # nothing in the step loop does a string-keyed domain lookup
        # (`05_DOMAIN_MODEL.md` §1.2, D-031).
        self._lane_index = {sumo_id: LaneId(i) for i, sumo_id in enumerate(lane_sumo_ids)}
        self._intersection_sumo_ids = intersection_sumo_ids
        if len(phase_green_links) != len(intersection_sumo_ids):
            raise BackendStartupError(
                f"the network describes {len(phase_green_links)} signalized intersections, "
                f"SUMO runs {len(intersection_sumo_ids)} traffic lights "
                f"{list(intersection_sumo_ids)}"
            )
        self._phase_by_green = tuple(
            _phase_by_green(sumo_id, greens)
            for sumo_id, greens in zip(intersection_sumo_ids, phase_green_links, strict=True)
        )
        self._start_s = start_s
        self._vehicle_types = vehicle_types
        self._step_length_s = step_length_s
        self._gridlock_steps = gridlock_steps
        # Furthest any declared vehicle type can advance in one step from a
        # standstill-relative speed, used by the arrival test below.
        self._max_advance_bonus_m = 0.5 * max_accel_mps2 * step_length_s * step_length_s

        # Insertion-ordered, and `VehicleId`s are assigned in increasing order,
        # so iterating this dict yields vehicles in canonical-id order without a
        # per-step sort.
        self._active: dict[str, _VehicleRecord] = {}
        self._next_vehicle_id = 0
        self._counters = _CumulativeCounters()
        self._signals: dict[str, _SignalRecord] = {}

    # --- Projection ----------------------------------------------------------

    def project(self, raw: RawStep) -> TrueState:
        time_s = raw.time_s
        self._retire_departed_vehicles(raw)
        self._admit_new_vehicles(raw)

        vehicles = self._project_vehicles(raw, time_s)
        lanes = self._project_lanes(vehicles, time_s)
        signals = self._project_signals(raw, time_s)
        counters = self._project_counters(raw, vehicles)

        return TrueState(
            time_s=time_s,
            vehicles=vehicles,
            lanes=lanes,
            signals=signals,
            counters=counters,
        )

    def _retire_departed_vehicles(self, raw: RawStep) -> None:
        """Drop records for vehicles no longer present, classifying arrivals (D-022).

        `raw.vehicles` is authoritative for who is in the network; the arrived
        list only says *why* someone left. Reconciling against the population
        rather than against the arrival list means a vehicle that leaves by any
        other route still leaves our books, instead of accumulating as a ghost.
        """
        present = raw.vehicles
        arrived = set(raw.arrived_ids)
        for sumo_id in [sid for sid in self._active if sid not in present]:
            record = self._active.pop(sumo_id)
            if sumo_id in arrived:
                self._classify_arrival(record)
                arrived.discard(sumo_id)
        # Vehicles that departed and arrived without ever being observed in a
        # projected step: counted at the sink so that
        # `arrived_at_sink + arrived_mid_link` stays equal to SUMO's own arrived
        # total, which is what makes §8 invariant 14 checkable by T1.8.
        self._counters.arrived_at_sink += len(arrived)

    def _classify_arrival(self, record: _VehicleRecord) -> None:
        """Split one arrival into D-022's served-at-sink and served-mid-link legs.

        A vehicle that ran off the end of its final lane reached a boundary sink.
        One removed part-way along it was removed by an `arrivalPos` — D-022's
        mid-link attrition.

        An arrival is only observable *after* the vehicle has gone, so the test
        is on where it was when last seen: could it have covered the remaining
        distance in the one unobserved step? The bound is kinematic —
        `v·Δt + ½·a·Δt²` at the fastest acceleration any declared vehicle type
        can manage — because a constant-speed bound is *not* an upper bound and
        misclassifies accelerating vehicles as attrition. Measured on the M0
        reference scenario, which contains no attrition at all: the
        constant-speed form reported 8 spurious mid-link arrivals in 400 steps,
        the kinematic form reports none.

        The residual failure mode is an `arrivalPos` set within one step's
        travel of the lane end, which is a sink arrival in all but name.
        `--tripinfo-output.write-unfinished` gives T1.8 the authoritative
        per-vehicle `arrivalPos` to audit this against at run end.
        """
        lane = self._lane_index.get(record.last_lane_id)
        if lane is None:
            self._counters.arrived_at_sink += 1
            return
        remaining_m = self._lane_lengths_m[lane] - record.last_lane_position_m
        reach_m = (
            record.last_speed_mps * self._step_length_s
            + self._max_advance_bonus_m
            + _ARRIVAL_TOLERANCE_M
        )
        if remaining_m <= reach_m:
            self._counters.arrived_at_sink += 1
        else:
            self._counters.arrived_mid_link += 1

    def _admit_new_vehicles(self, raw: RawStep) -> None:
        """Assign canonical `VehicleId`s to vehicles seen for the first time.

        Sorted by SUMO ID so the assignment is a pure function of the simulation
        and not of dictionary iteration order, which is what makes the two
        transports' `TrueState` sequences comparable at all.
        """
        if len(raw.vehicles) == len(self._active):
            return
        for sumo_id in sorted(sid for sid in raw.vehicles if sid not in self._active):
            self._active[sumo_id] = _VehicleRecord(
                canonical_id=VehicleId(self._next_vehicle_id),
                vehicle_type=self._resolve_type(raw.vehicles[sumo_id].type_id),
                halting_since_s=None,
                stop_count=0,
                last_lane_id=raw.vehicles[sumo_id].lane_id,
                last_lane_position_m=raw.vehicles[sumo_id].lane_position_m,
                last_speed_mps=raw.vehicles[sumo_id].speed_mps,
            )
            self._next_vehicle_id += 1

    def _resolve_type(self, type_id: str) -> VehicleType:
        vehicle_type = self._vehicle_types.get(type_id)
        if vehicle_type is None:
            raise BackendStartupError(
                f"vehicle type {type_id!r} has a SUMO vehicle class outside the canonical "
                f"ontology {sorted(VEHICLE_CLASS_TO_TYPE)}; `VehicleType` "
                f"(`05_DOMAIN_MODEL.md` §2) has no value for it"
            )
        return vehicle_type

    def _project_vehicles(self, raw: RawStep, time_s: float) -> tuple[VehicleState, ...]:
        states: list[VehicleState] = []
        for sumo_id, record in self._active.items():
            raw_vehicle = raw.vehicles[sumo_id]
            # Invariant 11: the single source for `is_halting` is `speed_mps`.
            is_halting = raw_vehicle.speed_mps < HALTING_SPEED_MPS
            if is_halting:
                if record.halting_since_s is None:
                    record.halting_since_s = time_s
                    # SUMO exposes no stop count; a stop is an entry into the
                    # halting state, counted here.
                    record.stop_count += 1
            else:
                record.halting_since_s = None

            record.last_lane_id = raw_vehicle.lane_id
            record.last_lane_position_m = raw_vehicle.lane_position_m
            record.last_speed_mps = raw_vehicle.speed_mps

            states.append(
                VehicleState(
                    id=record.canonical_id,
                    type=record.vehicle_type,
                    lane=self._lane_of(raw_vehicle),
                    position_on_lane_m=raw_vehicle.lane_position_m,
                    position_xy=(raw_vehicle.position_x_m, raw_vehicle.position_y_m),
                    speed_mps=raw_vehicle.speed_mps,
                    time_loss_s=raw_vehicle.time_loss_s,
                    waiting_time_s=raw_vehicle.waiting_time_s,
                    stop_count=record.stop_count,
                    is_halting=is_halting,
                    halting_since_s=record.halting_since_s,
                )
            )
        return tuple(states)

    def _lane_of(self, raw_vehicle: RawVehicle) -> LaneId:
        """Invariant 10: every vehicle is on exactly one lane, and it is a known one."""
        lane = self._lane_index.get(raw_vehicle.lane_id)
        if lane is None:
            raise BackendStartupError(
                f"vehicle is on lane {raw_vehicle.lane_id!r}, which was not in the network's "
                f"lane list at start; `05_DOMAIN_MODEL.md` §8 invariant 10 cannot be upheld"
            )
        return lane

    def _project_lanes(
        self, vehicles: tuple[VehicleState, ...], time_s: float
    ) -> tuple[LaneState, ...]:
        """Aggregate per-lane state from the projected vehicles.

        Derived from `vehicles` rather than read from SUMO's lane getters, for
        two reasons. First, D-025's queue needs the ≥ 1 s duration condition,
        which `getLastStepHaltingNumber` does not apply. Second, deriving the
        lane totals from the same vehicle records that satisfy invariants 10 and
        11 makes the lane and vehicle views of a step consistent by construction
        instead of by coincidence.
        """
        lane_count = len(self._lane_sumo_ids)
        vehicle_counts = [0] * lane_count
        speed_sums = [0.0] * lane_count
        queue_counts = [0] * lane_count
        # Furthest-upstream queued vehicle per lane; `None` where nothing queues.
        queue_tail_m: list[float | None] = [None] * lane_count

        for vehicle in vehicles:
            lane = vehicle.lane
            vehicle_counts[lane] += 1
            speed_sums[lane] += vehicle.speed_mps
            # Invariant 12: exactly the vehicles halting for >= 1 s. Both
            # operands come from SUMO's own clock, so the comparison is exact
            # rather than tolerance-based, and identical under either transport.
            if (
                vehicle.halting_since_s is not None
                and time_s - vehicle.halting_since_s >= QUEUE_MIN_HALTING_S
            ):
                queue_counts[lane] += 1
                tail = queue_tail_m[lane]
                if tail is None or vehicle.position_on_lane_m < tail:
                    queue_tail_m[lane] = vehicle.position_on_lane_m

        lanes: list[LaneState] = []
        for i in range(lane_count):
            tail_m = queue_tail_m[i]
            lanes.append(
                LaneState(
                    lane=LaneId(i),
                    queue_count=queue_counts[i],
                    # Stop line back to the furthest-upstream queued vehicle's
                    # front bumper. Deliberately assumption-free: it adds no
                    # vehicle length and no minimum gap, because
                    # `research/M0_sumo_semantics.md` §1.4 leaves the metre-based
                    # queue measure open until M4 and those two assumptions are
                    # exactly what the open question is about. Same D-025
                    # membership rule as `queue_count`, so the two agree on
                    # which vehicles are in the queue.
                    queue_length_m=(0.0 if tail_m is None else self._lane_lengths_m[i] - tail_m),
                    vehicle_count=vehicle_counts[i],
                    mean_speed_mps=(
                        speed_sums[i] / vehicle_counts[i] if vehicle_counts[i] else 0.0
                    ),
                )
            )
        return tuple(lanes)

    def _project_signals(self, raw: RawStep, time_s: float) -> tuple[SignalState, ...]:
        """Decode each light's displayed string into a canonical `SignalState` (D-034).

        SUMO's program phase index is not used: once a controller drives a light,
        SUMO runs its `online` program, whose index is always 0. What the light
        shows is decoded instead:

        * a display whose green link set (`G` and `g` alike) equals exactly one
          phase's is that phase, green;
        * a display with no green link is a transition -- yellow or all-red --
          and `active_phase` stays the phase being left;
        * a non-empty green set matching no phase raises, rather than guessing.

        `phase_started_s` is when the transition into the phase began -- or the
        start time, for the first phase shown -- and `green_started_s` when its
        green began, `None` during a transition. The display read after a step
        to `t` is the one shown during that step, so a change first seen at `t`
        began at `t - step_length_s`: the instant SUMO's static program switched
        (measured on 1.27.1: a new program phase reads a spent duration of one
        step when first seen) and the instant a controller applied it (before
        the step).

        The tracked state travels in the snapshot sidecar, because a SUMO state
        file does not carry it (D-032).
        """
        signals: list[SignalState] = []
        for index, sumo_id in enumerate(self._intersection_sumo_ids):
            ryg_state = raw.signals[sumo_id].ryg_state
            record = self._signals.get(sumo_id)
            if record is None or ryg_state != record.ryg_state:
                record = self._decode_change(index, sumo_id, ryg_state, record, time_s)
            signals.append(
                SignalState(
                    intersection=IntersectionId(index),
                    active_phase=record.active_phase,
                    phase_started_s=record.phase_started_s,
                    green_started_s=record.green_started_s,
                    in_transition=record.in_transition,
                )
            )
        return tuple(signals)

    def _decode_change(
        self,
        index: int,
        sumo_id: str,
        ryg_state: str,
        record: _SignalRecord | None,
        time_s: float,
    ) -> _SignalRecord:
        """Update one light's record for a display it was not showing a step ago."""
        phase = self._green_phase(index, sumo_id, ryg_state, time_s)
        changed_s = time_s - self._step_length_s

        if record is None:
            if phase is None:
                raise BackendStartupError(
                    f"traffic light {sumo_id!r} shows no green at its first projected step "
                    f"(t={time_s}, {ryg_state!r}); a transition is named by the phase being "
                    f"left, and no phase has been shown yet (D-034)"
                )
            record = _SignalRecord(
                active_phase=phase,
                phase_started_s=self._start_s,
                green_started_s=self._start_s,
                in_transition=False,
                ryg_state=ryg_state,
            )
            self._signals[sumo_id] = record
            return record

        if phase is None:
            if not record.in_transition:
                # The transition into the next phase has started, so the next
                # phase became active then; the one being left stays named.
                record.phase_started_s = changed_s
                record.green_started_s = None
                record.in_transition = True
        elif record.in_transition:
            # Green began. `phase_started_s` stays where the transition put it.
            record.active_phase = phase
            record.green_started_s = changed_s
            record.in_transition = False
        elif phase != record.active_phase:
            # Green straight to green with no transition between them: both
            # instants coincide.
            record.active_phase = phase
            record.phase_started_s = changed_s
            record.green_started_s = changed_s
        record.ryg_state = ryg_state
        return record

    def _green_phase(
        self, index: int, sumo_id: str, ryg_state: str, time_s: float
    ) -> PhaseId | None:
        """The phase whose green link set the display shows; `None` if nothing is green."""
        phases = self._phase_by_green[index]
        green = frozenset(link for link, char in enumerate(ryg_state) if char in "Gg")
        if not green:
            return None
        phase = phases.get(green)
        if phase is None:
            known = {int(p): sorted(links) for links, p in phases.items()}
            raise BackendStartupError(
                f"traffic light {sumo_id!r} shows green on links {sorted(green)} at t={time_s} "
                f"({ryg_state!r}), which is no phase's green link set {known}; refusing to "
                f"guess (D-034)"
            )
        return phase

    def _project_counters(self, raw: RawStep, vehicles: tuple[VehicleState, ...]) -> RunCounters:
        counters = self._counters
        counters.teleports += raw.teleports_ending

        # D-008 item 3: gridlock is "no vehicle has moved for N steps". An empty
        # network is not gridlocked, it is empty.
        if vehicles and all(vehicle.is_halting for vehicle in vehicles):
            counters.motionless_steps += 1
        else:
            counters.motionless_steps = 0
        if counters.motionless_steps >= self._gridlock_steps:
            # Sticky: a run that gridlocked and then cleared still gridlocked.
            counters.gridlock_detected = True

        return RunCounters(
            teleports=counters.teleports,
            # Vehicles that are due but could not be inserted: the backlog now,
            # and at run end the insertion loss D-008 gates on (nothing is
            # discarded, since no `--max-depart-delay` is set).
            # `--tripinfo-output.write-undeparted` gives T1.8 the per-vehicle
            # record behind the number. Not `loaded - departed`: SUMO loads
            # explicit `<vehicle>` demand -- which is what `jtrrouter` emits for
            # T1.5 -- up to `--route-steps` ahead of its departure time, so that
            # difference counts vehicles that are not due yet, and it goes
            # negative when loading happened before the first projected step.
            insertion_failures=raw.pending,
            gridlock_detected=counters.gridlock_detected,
            arrived_at_sink=counters.arrived_at_sink,
            arrived_mid_link=counters.arrived_mid_link,
            # D-022's unserved leg. Together with the two served legs this makes
            # §8 invariant 14 an identity rather than an estimate.
            still_in_network=len(vehicles),
        )

    # --- Snapshot support (D-032; mechanism only, policy is T1.6) ------------

    def state_dict(self) -> dict[str, Any]:
        """Serialise the bookkeeping a SUMO state file does not carry.

        SUMO's `--save-state` restores the simulation, not our halting timers,
        stop counts or cumulative counters. Without these, a loaded snapshot
        would not reproduce the `TrueState` it was saved from, which is T1.6's
        first acceptance criterion.
        """
        return {
            "next_vehicle_id": self._next_vehicle_id,
            "counters": {
                "teleports": self._counters.teleports,
                "arrived_at_sink": self._counters.arrived_at_sink,
                "arrived_mid_link": self._counters.arrived_mid_link,
                "motionless_steps": self._counters.motionless_steps,
                "gridlock_detected": self._counters.gridlock_detected,
            },
            "signals": {
                sumo_id: [
                    int(record.active_phase),
                    record.phase_started_s,
                    record.green_started_s,
                    record.in_transition,
                    record.ryg_state,
                ]
                for sumo_id, record in self._signals.items()
            },
            "vehicles": {
                sumo_id: [
                    int(record.canonical_id),
                    str(record.vehicle_type),
                    record.halting_since_s,
                    record.stop_count,
                    record.last_lane_id,
                    record.last_lane_position_m,
                    record.last_speed_mps,
                ]
                for sumo_id, record in self._active.items()
            },
        }

    def load_state_dict(self, payload: dict[str, Any]) -> None:
        """Restore what `state_dict()` saved, replacing the current bookkeeping."""
        self._counters = _CumulativeCounters(**payload["counters"])
        self._next_vehicle_id = int(payload["next_vehicle_id"])
        self._active = {
            sumo_id: _VehicleRecord(
                canonical_id=VehicleId(int(fields[0])),
                vehicle_type=VehicleType(fields[1]),
                halting_since_s=None if fields[2] is None else float(fields[2]),
                stop_count=int(fields[3]),
                last_lane_id=str(fields[4]),
                last_lane_position_m=float(fields[5]),
                last_speed_mps=float(fields[6]),
            )
            for sumo_id, fields in payload["vehicles"].items()
        }
        self._signals = {
            sumo_id: _SignalRecord(
                active_phase=PhaseId(int(fields[0])),
                phase_started_s=float(fields[1]),
                green_started_s=None if fields[2] is None else float(fields[2]),
                in_transition=bool(fields[3]),
                ryg_state=str(fields[4]),
            )
            for sumo_id, fields in payload["signals"].items()
        }


def _phase_by_green(
    sumo_id: str, green_links: Mapping[PhaseId, frozenset[int]]
) -> dict[frozenset[int], PhaseId]:
    """Invert one intersection's phase -> green links table, for decoding.

    Two phases with the same green link set cannot be told apart from the
    display (D-034's revisit trigger), and a phase with none cannot be told from
    a transition; both are refused at start rather than decoded ambiguously.
    """
    by_green: dict[frozenset[int], PhaseId] = {}
    for phase, links in green_links.items():
        if not links:
            raise BackendStartupError(
                f"phase {int(phase)} of traffic light {sumo_id!r} greens no link, so its "
                f"display cannot be told from a transition (D-034)"
            )
        if links in by_green:
            raise BackendStartupError(
                f"phases {int(by_green[links])} and {int(phase)} of traffic light {sumo_id!r} "
                f"green the same links {sorted(links)}; the display cannot tell them apart "
                f"(D-034's revisit trigger)"
            )
        by_green[links] = phase
    return by_green
