"""A simple baseline controller that holds the first authored phase (T1.13 support)."""

from __future__ import annotations

from traffic_lab.control.controller import Controller
from traffic_lab.domain.action import PhaseRequest
from traffic_lab.domain.network import Network
from traffic_lab.domain.observation import EstimatedState


class HoldFirst:
    """Always asks for the first authored phase; max green forces it on regardless."""

    def __init__(self, network: Network, *, decision_interval_s: float = 5.0) -> None:
        self.decision_interval_s = decision_interval_s
        (intersection,) = network.signalized_intersections
        self._intersection = intersection.id
        self._phase = intersection.phases[0].id

    def decide(self, est: EstimatedState, now_s: float) -> PhaseRequest:
        return PhaseRequest(self._intersection, self._phase)


def hold_first(network: Network) -> Controller:
    """Controller factory returning `HoldFirst` for `network`."""
    return HoldFirst(network)
