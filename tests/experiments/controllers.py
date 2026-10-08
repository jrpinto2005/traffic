"""Test controllers for the runner. Test support only; the real ones are T1.10's.

Each is a top-level class so a `spawn` worker can import it, and each satisfies
`traffic_lab.control.controller.Controller` -- mypy checks that through the
factories' return types. They read `EstimatedState` only, like any controller.
"""

from __future__ import annotations

from dataclasses import dataclass

from traffic_lab.control.controller import Controller
from traffic_lab.domain.action import PhaseRequest
from traffic_lab.domain.network import Network, PhaseId
from traffic_lab.domain.observation import EstimatedState
from traffic_lab.domain.state import SignalState


def _phases(network: Network) -> tuple[PhaseId, ...]:
    (intersection,) = network.signalized_intersections
    return tuple(phase.id for phase in intersection.phases)


class HoldFirst:
    """Always asks for the first authored phase; max green forces it on regardless."""

    def __init__(self, network: Network, *, decision_interval_s: float = 5.0) -> None:
        self.decision_interval_s = decision_interval_s
        (self._intersection,) = (i.id for i in network.signalized_intersections)
        self._phase = _phases(network)[0]

    def decide(self, est: EstimatedState, now_s: float) -> PhaseRequest:
        return PhaseRequest(self._intersection, self._phase)


class CycleFrom:
    """Holds whatever is active until `start_s`, then asks for the next phase in
    authored order at every decision -- read from its own signal state in `est`
    (D-033), so the constraint layer's view is what drives it."""

    def __init__(
        self, network: Network, *, start_s: float, decision_interval_s: float = 5.0
    ) -> None:
        self.decision_interval_s = decision_interval_s
        self._start_s = start_s
        self._phases = _phases(network)

    def decide(self, est: EstimatedState, now_s: float) -> PhaseRequest:
        (own,) = est.signals
        if now_s < self._start_s:
            return PhaseRequest(own.intersection, own.active_phase)
        position = self._phases.index(own.active_phase)
        return PhaseRequest(own.intersection, self._phases[(position + 1) % len(self._phases)])


@dataclass(frozen=True)
class Decision:
    """What one `decide()` call saw."""

    now_s: float
    est_time_s: float
    signals: tuple[SignalState, ...]
    lanes_seen: int


class Recording(CycleFrom):
    """`CycleFrom` that remembers every call, for the timing tests."""

    def __init__(
        self, network: Network, *, start_s: float = 10.0, decision_interval_s: float = 1.0
    ) -> None:
        super().__init__(network, start_s=start_s, decision_interval_s=decision_interval_s)
        self.decisions: list[Decision] = []

    def decide(self, est: EstimatedState, now_s: float) -> PhaseRequest:
        self.decisions.append(Decision(now_s, est.time_s, est.signals, len(est.lanes)))
        return super().decide(est, now_s)


class CrashingController(HoldFirst):
    """Raises at its first decision at or after `CRASH_AT_S`."""

    def decide(self, est: EstimatedState, now_s: float) -> PhaseRequest:
        if now_s >= CRASH_AT_S:
            raise RuntimeError(f"{CRASH_MESSAGE} at {now_s} s")
        return super().decide(est, now_s)


CRASH_AT_S = 120.0
CRASH_MESSAGE = "deliberate controller crash"


def hold_first(network: Network) -> Controller:
    return HoldFirst(network)


def crashing(network: Network) -> Controller:
    return CrashingController(network)
