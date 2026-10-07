"""The backend adapter: the only package that talks to SUMO.

`00_RESEARCH_SPECIFICATION.md` §25 makes that a hard architectural boundary and
`06_ARCHITECTURE.md` §10 rule 2 enforces it as a test — `traci`, `libsumo` and
`sumolib` are importable from `traffic_lab.backend` and nowhere else.

What the rest of the project uses from here is deliberately small: a `Backend`
to drive, a `BackendConfig` to configure it, a `BackendIndex` to relate dense
canonical IDs back to SUMO's strings, and two errors. `Projector`, the
transports and the raw per-step records are internal — exposing them would put a
per-object query surface within reach of layers that must not have one (D-031).
"""

from __future__ import annotations

from traffic_lab.backend.adapter import (
    SNAPSHOT_SIDECAR_SUFFIX,
    Backend,
    BackendIndex,
    SumoBackend,
)
from traffic_lab.backend.config import (
    HALTING_SPEED_MPS,
    QUEUE_MIN_HALTING_S,
    BackendConfig,
    BackendStartupError,
    SnapshotMismatchError,
    TransportName,
)

__all__ = [
    "HALTING_SPEED_MPS",
    "QUEUE_MIN_HALTING_S",
    "SNAPSHOT_SIDECAR_SUFFIX",
    "Backend",
    "BackendConfig",
    "BackendIndex",
    "BackendStartupError",
    "SnapshotMismatchError",
    "SumoBackend",
    "TransportName",
]
