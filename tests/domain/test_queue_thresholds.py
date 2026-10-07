"""D-025's two thresholds have one definition, in `traffic_lab.domain.state` (D-033).

They moved there from `traffic_lab.backend.config` so the backend, the sensors
and the estimators agree by construction. `traffic_lab.backend` keeps
re-exporting both names so nothing that imports them from there breaks.
"""

from __future__ import annotations

import traffic_lab.backend as backend
import traffic_lab.backend.config as backend_config
from traffic_lab.domain import state


def test_the_thresholds_have_the_d025_values() -> None:
    assert state.HALTING_SPEED_MPS == 0.1
    assert state.QUEUE_MIN_HALTING_S == 1.0


def test_the_backend_re_exports_the_domain_definitions() -> None:
    assert backend.HALTING_SPEED_MPS is state.HALTING_SPEED_MPS
    assert backend.QUEUE_MIN_HALTING_S is state.QUEUE_MIN_HALTING_S


def test_the_backend_config_module_no_longer_defines_them() -> None:
    # One definition: a second copy in `config.py` could drift from this one.
    assert not hasattr(backend_config, "HALTING_SPEED_MPS")
    assert not hasattr(backend_config, "QUEUE_MIN_HALTING_S")
