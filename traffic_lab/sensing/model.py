"""The sensor seam: `06_ARCHITECTURE.md` SS3 seam 2, SS4.1, implementing D-005.

A `SensorModel` is one of exactly four consumers allowed to read `TrueState`
(SS4.2) -- its entire job is `O_t = h(S_t) + eps_t` -- and what it hands onward
is an `Observation`, a stream of detections that says nothing about how it was
made (`05_DOMAIN_MODEL.md` SS4.1). The parametric camera model of M3 and the
oracle both implement this one protocol, which is what makes the oracle "a
sensor, not a bypass": a controller reads `EstimatedState` in every experimental
arm, and there is no path for ground truth to take around the sensor.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from traffic_lab.domain.observation import Observation
from traffic_lab.domain.state import TrueState


@runtime_checkable
class SensorModel(Protocol):
    def observe(self, state: TrueState, now_s: float) -> Observation:
        """Sample `state`, taken at simulated time `now_s`, into an `Observation`."""
        ...
