"""Dynamic state: `05_DOMAIN_MODEL.md` SS3, `TrueState` and its parts.

Per `06_ARCHITECTURE.md` SS4, `TrueState` is readable by exactly four
consumers -- sensors, metrics, the trace writer, the snapshot writer -- and
never by a controller. That boundary is enforced elsewhere (an import test on
`traffic_lab.control`, per `06_ARCHITECTURE.md` SS4.3); this module only
defines the type.

Implements D-025 (queue definition: `is_halting` is a 0.1 m/s speed threshold;
`queue_count` additionally requires >= 1 s continuous halting, tracked via
`halting_since_s`) and D-022 (trip accounting is three-way and first-class, not
a post-processing step: `RunCounters.arrived_at_sink` / `arrived_mid_link` /
`still_in_network`).

Static structure (`network.py`) is frozen after load; state types here are
rebuilt each step from one batched subscription fetch (SS1.2, `06_ARCHITECTURE.md`
SS5.2) -- so, like `network.py`, everything is a frozen, slotted dataclass, but
these are reconstructed rather than loaded once.
"""

from __future__ import annotations

from dataclasses import dataclass

from traffic_lab.domain.network import IntersectionId, LaneId, PhaseId, VehicleId, VehicleType

# D-025's two thresholds live here, in the domain, so that the backend, the
# sensors and the estimators share one definition (D-033). `traffic_lab.backend`
# re-exports both names.

#: Speed below which SUMO -- and therefore `VehicleState.is_halting` (D-025,
#: `05_DOMAIN_MODEL.md` SS8 invariant 11) -- considers a vehicle halting.
HALTING_SPEED_MPS = 0.1

#: Continuous halting duration a vehicle must reach before it counts towards
#: `LaneState.queue_count` (D-025, invariant 12). SUMO's native halting counter
#: applies no duration condition, so this part is ours -- see
#: `research/M0_sumo_semantics.md` SS1.3.
QUEUE_MIN_HALTING_S = 1.0


@dataclass(frozen=True, slots=True)
class VehicleState:
    id: VehicleId
    type: VehicleType
    lane: LaneId
    position_on_lane_m: float
    position_xy: tuple[float, float]  # sensors need world coordinates for FOV geometry
    speed_mps: float
    time_loss_s: float  # accumulated; D-006
    waiting_time_s: float  # accumulated
    stop_count: int  # accumulated
    is_halting: bool  # speed < 0.1 m/s; D-025
    halting_since_s: float | None  # for the >= 1 s duration condition


@dataclass(frozen=True, slots=True)
class LaneState:
    lane: LaneId
    queue_count: int  # D-025, primary
    queue_length_m: float  # secondary, reported from M4
    vehicle_count: int
    mean_speed_mps: float


@dataclass(frozen=True, slots=True)
class SignalState:
    intersection: IntersectionId
    active_phase: PhaseId
    phase_started_s: float  # when the phase became active - transition start
    green_started_s: float | None  # when its green began; None while in transition
    in_transition: bool


@dataclass(frozen=True, slots=True)
class RunCounters:
    teleports: int  # D-008; must remain 0
    insertion_failures: int  # D-008
    gridlock_detected: bool  # D-008
    arrived_at_sink: int  # D-022, served
    arrived_mid_link: int  # D-022, served (attrition)
    still_in_network: int  # D-022, unserved


@dataclass(frozen=True, slots=True)
class TrueState:
    time_s: float
    vehicles: tuple[VehicleState, ...]
    lanes: tuple[LaneState, ...]
    signals: tuple[SignalState, ...]
    counters: RunCounters
