"""Max-Pressure, lane-level form (D-013, T1.10 A5).

At each decision, for each authored phase: `U` is the set of incoming lanes of
its movements and `D` the set of their outgoing lanes, each lane once, and

    pressure = sum over U of queue_count - sum over D of queue_count.

The controller requests the phase of maximum pressure. On a tie it keeps the
phase in effect if that phase is among the maxima; otherwise it takes the
lowest phase ID among them. Nothing else: no weights, no saturation-flow or
turn-ratio terms, no switching penalty, no minimum-pressure threshold
(Non-goal 4) -- minimum and maximum green are the constraint layer's.

**Source.** Varaiya, P. (2013). "Max pressure control of a network of signalized
intersections." *Transportation Research Part C* 36, 177-195 -- the algorithm
and its stability result, stated over link queues with turn-ratio and
saturation-flow weights. The unweighted lane-level form used here, incoming
minus outgoing queue over a phase's lanes, is the one the traffic-signal-control
learning literature adopted as its baseline: Wei, H., Chen, C., Zheng, G., Wu,
K., Gayah, V., Xu, K., Li, Z. (2019). "PressLight: Learning Max Pressure Control
to Coordinate Traffic Signals in Arterial Network." *KDD '19*, 1290-1298 (the
pressure of a movement: incoming minus outgoing lane vehicles), and RESCO's
`MAXPRESSURE` (Ault, J., Sharon, G. (2021), NeurIPS Datasets and Benchmarks;
`research/M0_prior_art.md`). Two differences from those, both by contract: `U`
and `D` are **sets**, so a lane carrying two of a phase's movements counts once
(T1.10 A5); and the queue is `D-025`'s (halting at least 1 s), so this is not
RESCO's controller, whose queue flag is never reset (`D-025`, T0.1).

`queue_count` comes from `EstimatedState` (`D-025` via the estimator), outgoing
lanes included -- Escalate-if 2 is answered: they are in the estimate. A lane
the estimate does not carry raises rather than counting as empty.
"""

from __future__ import annotations

from traffic_lab.control.phases import own_signal, phase_service, the_intersection
from traffic_lab.domain.action import PhaseRequest
from traffic_lab.domain.network import LaneId, Network, PhaseId
from traffic_lab.domain.observation import EstimatedState


class MaxPressureController:
    """`Controller` (D-020) choosing the maximum-pressure phase every Δt (default 5 s)."""

    def __init__(self, network: Network, *, decision_interval_s: float = 5.0) -> None:
        self.decision_interval_s = decision_interval_s  # D-020's suggested value
        intersection = the_intersection(network)
        self._intersection = intersection.id
        self._lanes: tuple[tuple[PhaseId, frozenset[LaneId], frozenset[LaneId]], ...] = tuple(
            (s.phase, s.incoming_lanes, s.outgoing_lanes)
            for s in phase_service(network, intersection)
        )

    def pressures(self, est: EstimatedState) -> dict[PhaseId, float]:
        """Each authored phase's pressure under `est`, vehicles."""
        queue = {lane.lane: lane.queue_count for lane in est.lanes}
        try:
            return {
                phase: sum(queue[lane] for lane in incoming) - sum(queue[lane] for lane in outgoing)
                for phase, incoming, outgoing in self._lanes
            }
        except KeyError as missing:
            raise ValueError(
                f"EstimatedState has no estimate for lane {missing.args[0]}, which a phase of "
                f"intersection {int(self._intersection)} uses"
            ) from None

    def decide(self, est: EstimatedState, now_s: float) -> PhaseRequest:
        pressures = self.pressures(est)
        best = max(pressures.values())
        current = own_signal(est, self._intersection).active_phase
        if pressures[current] == best:
            return PhaseRequest(self._intersection, current)
        return PhaseRequest(
            self._intersection, min(p for p, value in pressures.items() if value == best)
        )
