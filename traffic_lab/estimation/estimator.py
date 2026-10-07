"""The estimator seam: `Observation` in, `EstimatedState` out (D-033, D-021).

An `Estimator` turns what the sensor reported into what the controller believes.
It never sees `TrueState` -- the package imports none of it, and
`tests/control/test_control_import_boundary.py` keeps it that way -- so a result
about the estimator is a result about the estimator and not about a leak.

`signals` comes from the constraint layer, because a controller knows what it
commanded (`05_DOMAIN_MODEL.md` SS4.2). The estimator copies it into
`EstimatedState` unchanged, which means `EstimatedState` is built in exactly one
place (D-033).
"""

from __future__ import annotations

from typing import Protocol

from traffic_lab.domain.observation import EstimatedState, Observation
from traffic_lab.domain.state import SignalState


class Estimator(Protocol):
    def update(
        self, obs: Observation, signals: tuple[SignalState, ...], now_s: float
    ) -> EstimatedState:
        """Fold `obs` into a belief about the network at simulated time `now_s`."""
        ...
