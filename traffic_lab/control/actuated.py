"""Actuated signal control: gap-based extension on detection zones (D-013, D-036, T1.10 A3).

At each decision step (Δt = 1 s, matching D-020):
- Before `min_green_s`: hold the active green phase.
- Afterwards: extend green while any lane served by the active phase has `zone_count > 0`.
- Once those detection zones have been empty for longer than `gap_s` (default 3.0 s,
  matching SUMO's `max-gap` default): request the next authored phase.
- Max green enforcement is the constraint layer's responsibility (A3).

A phase transition follows authored phase order (`next_phase_map()`); empty phases
are not skipped, matching SUMO 1.27.1's default actuated traffic light logic.
"""

from __future__ import annotations

from traffic_lab.control.phases import next_phase_map, own_signal, phase_service, the_intersection
from traffic_lab.domain.action import PhaseRequest
from traffic_lab.domain.network import LaneId, Network, PhaseId
from traffic_lab.domain.observation import EstimatedState

_TIME_EPS_S = 1e-9


class ActuatedController:
    """`Controller` (D-020) implementing gap-based presence actuation (D-036)."""

    def __init__(
        self,
        network: Network,
        *,
        decision_interval_s: float = 1.0,
        gap_s: float = 3.0,
    ) -> None:
        self.decision_interval_s = decision_interval_s  # D-020 / T1.10 A3: 1 s
        self.gap_s = gap_s  # Verified against SUMO 1.27.1 max-gap default
        intersection = the_intersection(network)
        self._intersection = intersection.id
        self._timing = intersection.timing
        self._services: dict[PhaseId, frozenset[LaneId]] = {
            s.phase: s.incoming_lanes for s in phase_service(network, intersection)
        }
        self._next = next_phase_map(intersection)
        self._active_phase: PhaseId | None = None
        self._last_occupied_s: float | None = None

    def decide(self, est: EstimatedState, now_s: float) -> PhaseRequest:
        own = own_signal(est, self._intersection)
        phase = own.active_phase

        if own.in_transition or own.green_started_s is None:
            self._active_phase = phase
            self._last_occupied_s = None
            return PhaseRequest(self._intersection, phase)

        if self._active_phase != phase:
            self._active_phase = phase
            self._last_occupied_s = None

        incoming = self._services[phase]
        zone_counts = {lane.lane: lane.zone_count for lane in est.lanes}
        try:
            occupied = any(zone_counts[lane] > 0.0 for lane in incoming)
        except KeyError as missing:
            raise ValueError(
                f"EstimatedState has no estimate for lane {missing.args[0]}, which a phase of "
                f"intersection {int(self._intersection)} uses"
            ) from None

        if occupied:
            self._last_occupied_s = now_s

        elapsed_green = now_s - own.green_started_s
        if elapsed_green + _TIME_EPS_S < self._timing.min_green_s:
            return PhaseRequest(self._intersection, phase)

        if occupied:
            return PhaseRequest(self._intersection, phase)

        empty_since_s = (
            self._last_occupied_s if self._last_occupied_s is not None else own.green_started_s
        )
        if (now_s - empty_since_s) > self.gap_s + _TIME_EPS_S:
            return PhaseRequest(self._intersection, self._next[phase])

        return PhaseRequest(self._intersection, phase)
