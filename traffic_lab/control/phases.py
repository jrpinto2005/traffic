"""What each authored phase serves, in lanes and movements: the static view controllers share.

Webster, our actuated controller and Max-Pressure all need the same three facts
about a phase -- its movements, the lanes those movements leave from and the
lanes they enter -- and the authored order in which phases follow one another.
They are derived once, at construction, from the canonical `Network`; nothing
here reads dynamic state.

Movements are numbered by `movements_of(..., start_id=0)`, the numbering signal
groups refer to (`validate_network()` invariant 8, `green_link_indices()`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from traffic_lab.domain.network import (
    IntersectionId,
    LaneId,
    Movement,
    Network,
    PhaseId,
    SignalizedIntersection,
    movements_of,
)
from traffic_lab.domain.observation import EstimatedState
from traffic_lab.domain.state import SignalState


@dataclass(frozen=True, slots=True)
class PhaseService:
    """One authored phase's movements and the lanes they use.

    `incoming_lanes` and `outgoing_lanes` are sets: a lane two of the phase's
    movements share (a through-and-right lane) appears once.
    """

    phase: PhaseId
    movements: tuple[Movement, ...]
    incoming_lanes: frozenset[LaneId]
    outgoing_lanes: frozenset[LaneId]


def the_intersection(network: Network) -> SignalizedIntersection:
    """The network's one signalized intersection.

    A `Controller` returns one `PhaseRequest` per decision (`D-020`), so each
    controller here drives exactly one intersection -- M1's isolated
    intersection. A network with any other number raises `ValueError` rather
    than leaving all but one signal uncontrolled.
    """
    intersections = network.signalized_intersections
    if len(intersections) != 1:
        raise ValueError(
            f"a controller drives one signalized intersection; the network has {len(intersections)}"
        )
    return intersections[0]


def phase_service(
    network: Network, intersection: SignalizedIntersection
) -> tuple[PhaseService, ...]:
    """Each authored phase of `intersection`, in authored order, with what it serves."""
    movements = {m.id: m for m in movements_of(network, intersection.junction)}
    connections = {c.id: c for c in network.connections}
    groups = {g.id: g.movements for g in intersection.signal_groups}
    services = []
    for phase in intersection.phases:
        served = tuple(
            movements[movement_id]
            for group_id in sorted(phase.green_groups)
            for movement_id in groups[group_id]
        )
        links = [connections[c] for m in served for c in m.connections]
        services.append(
            PhaseService(
                phase=phase.id,
                movements=served,
                incoming_lanes=frozenset(c.from_lane for c in links),
                outgoing_lanes=frozenset(c.to_lane for c in links),
            )
        )
    return tuple(services)


def next_phase_map(intersection: SignalizedIntersection) -> Mapping[PhaseId, PhaseId]:
    """Each authored phase's successor in authored order, the last wrapping to the first.

    Authored order is the order the program was written in, the order a
    fixed-time plan runs and the order the constraint layer's max-green
    override follows (`ConstraintLayer._next_legal_phase`).
    """
    order = [phase.id for phase in intersection.phases]
    return {phase: order[(k + 1) % len(order)] for k, phase in enumerate(order)}


def own_signal(est: EstimatedState, intersection: IntersectionId) -> SignalState:
    """`intersection`'s signal state as the constraint layer reports it (`D-033`).

    During a transition `active_phase` is the phase being entered and
    `green_started_s` is `None`. Raises `ValueError` if `est` has none.
    """
    for signal in est.signals:
        if signal.intersection == intersection:
            return signal
    raise ValueError(f"EstimatedState carries no signal state for intersection {intersection}")
