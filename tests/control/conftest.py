"""Fixtures for the controller tests that need the generated intersection.

The intersection is built once per session by `tests/backend/conftest.py` and
re-exported here, as `tests/metrics/conftest.py` does: pytest offers a fixture
only to the tests beneath the conftest that defines it.
"""

from __future__ import annotations

from tests.backend.conftest import scenario

__all__ = ["scenario"]
