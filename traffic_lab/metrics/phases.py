"""The three phases of a run (D-018, `07_EXPERIMENT_METHODOLOGY.md` SS3.1).

| Phase | Metrics |
| --- | --- |
| warm-up | discarded |
| measurement | collected |
| cool-down | not collected; exists so in-flight trips can finish |

A run's phases are fixed by its measurement window: everything before it is
warm-up, everything from its end on is cool-down. The window is half-open,
`[start_s, end_s)`, the convention T1.8 Amendment A2 pins for "completed in
the window".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RunPhase(StrEnum):
    WARMUP = "warmup"
    MEASUREMENT = "measurement"
    COOLDOWN = "cooldown"


@dataclass(frozen=True, slots=True)
class MeasurementWindow:
    """The measurement phase, `[start_s, end_s)` in simulated seconds."""

    start_s: float
    end_s: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.start_s < self.end_s:
            raise ValueError(
                f"a measurement window needs 0 <= start_s < end_s, got "
                f"[{self.start_s}, {self.end_s})"
            )

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s

    def phase(self, time_s: float) -> RunPhase:
        if time_s < self.start_s:
            return RunPhase.WARMUP
        if time_s < self.end_s:
            return RunPhase.MEASUREMENT
        return RunPhase.COOLDOWN

    def contains(self, time_s: float) -> bool:
        return self.start_s <= time_s < self.end_s
