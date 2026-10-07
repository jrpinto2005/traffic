"""Fixtures for the estimation tests that drive a real SUMO.

The reference scenario's network is built on demand by `tests/backend/conftest.py`
(`reference.net.xml` is gitignored), so its fixtures are re-exported here rather
than rebuilt: pytest only offers a fixture to the tests beneath the conftest that
defines it.
"""

from __future__ import annotations

from tests.backend.conftest import reference_net, reference_routes

__all__ = ["reference_net", "reference_routes"]
