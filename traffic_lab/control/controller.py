"""The controller seam: `EstimatedState` in, `PhaseRequest` out (D-020, T1.10's contract).

One of the three pre-approved seams (`08_AGENT_HANDOFF_PROTOCOL.md` SS7): every
controller -- fixed-time, actuated, Max-Pressure, and later MPC and RL -- is a
`Controller`, and every one of them acts through the constraint layer. A
`Protocol` with one method, no base class and no registry (D-031,
`06_ARCHITECTURE.md` SS11).

A controller receives `EstimatedState` only. There is no `TrueState` in scope,
and `tests/control/test_control_import_boundary.py` keeps it that way.

Defined here by T1.11, whose runner calls it (`06_ARCHITECTURE.md` SS6.2);
implemented by T1.10.
"""

from __future__ import annotations

from typing import Protocol

from traffic_lab.domain.action import PhaseRequest
from traffic_lab.domain.observation import EstimatedState


class Controller(Protocol):
    decision_interval_s: float  # D-020
    """Dt, simulated seconds: how often the runner asks for a decision."""

    def decide(self, est: EstimatedState, now_s: float) -> PhaseRequest:
        """The phase this controller wants at simulated time `now_s`, given `est`."""
        ...
