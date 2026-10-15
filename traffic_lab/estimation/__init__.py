"""Estimators: `Observation` in, `EstimatedState` out (`06_ARCHITECTURE.md` SS4).

Depends on `domain` **minus `TrueState`** and nothing else in the project -- like
`control/`, it must never be able to read ground truth, and it does not import
`backend/` (checked by `tests/control/test_control_import_boundary.py`).
"""

from __future__ import annotations

from traffic_lab.estimation.decay import (
    CountingWithDecayEstimator,
    DecayEstimatorConfig,
)
from traffic_lab.estimation.estimator import Estimator
from traffic_lab.estimation.factories import (
    make_decay_estimator,
    make_identity_estimator,
)
from traffic_lab.estimation.identity import IdentityEstimator

__all__ = [
    "CountingWithDecayEstimator",
    "DecayEstimatorConfig",
    "Estimator",
    "IdentityEstimator",
    "make_decay_estimator",
    "make_identity_estimator",
]
