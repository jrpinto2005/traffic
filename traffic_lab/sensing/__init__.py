"""Sensor models: `TrueState` in, `Observation` out (`06_ARCHITECTURE.md` SS4).

Depends on `domain` and nothing else in the project; in particular it does not
import `backend/` -- a sensor reads the `TrueState` it is handed and never asks
the simulator anything (checked by `tests/control/test_control_import_boundary.py`).
"""

from __future__ import annotations

from traffic_lab.sensing.model import SensorModel
from traffic_lab.sensing.oracle import OracleSensor

__all__ = ["OracleSensor", "SensorModel"]
