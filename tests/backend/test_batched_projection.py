"""One batched projection per step, and no per-object query method exposed.

`D-031` as amended, and `06_ARCHITECTURE.md` SS5.2: this is an **architectural
constraint, not an optimization**. It exists so that per-object access cannot
leak into sensors, metrics and controllers, "where it would be both slow and
impossible to remove later".

The constraint has two halves and they are tested separately, because the
amendment separates them:

* **Invariant, both transports:** one `fetch()` per `project()`, and no
  per-object getter on the public surface.
* **Mechanism, TraCI only:** the number of state-reading calls per step is
  constant regardless of how many vehicles are in the network. LibSUMO
  deliberately does *not* satisfy this -- direct per-vehicle getters measured
  ~1.7x faster than subscriptions there because there is no socket to amortise
  (`research/M0_performance.md`) -- which is exactly why the amendment made the
  mechanism transport-specific and kept only the invariant binding.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from tests.backend.conftest import make_config
from traffic_lab.backend import SumoBackend
from traffic_lab.backend import transport as transport_module

#: Calls that read simulation state. `vehicle.subscribe` is deliberately absent:
#: it registers interest in a vehicle that departed this step, it returns no
#: state to the projection, and it is bounded by the departure rate rather than
#: by the population.
_STATE_READING_CALLS = frozenset(
    {
        "simulation.getSubscriptionResults",
        "vehicle.getAllSubscriptionResults",
        "trafficlight.getAllSubscriptionResults",
    }
)


class _CountingNamespace:
    def __init__(self, real: Any, counts: Counter[str], prefix: str) -> None:
        self._real = real
        self._counts = counts
        self._prefix = prefix

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._real, name)

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self._counts[f"{self._prefix}.{name}"] += 1
            return attribute(*args, **kwargs)

        return wrapper


class _CountingApi:
    """Wraps the real `traci` module and counts every call made through it."""

    def __init__(self, real: Any) -> None:
        self._real = real
        self.counts: Counter[str] = Counter()

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._real, name)
        if not callable(attribute):
            # A TraCI domain (`traci.vehicle`, `traci.lane`, ...) is an object,
            # not a callable; its methods are what we want to count.
            return _CountingNamespace(attribute, self.counts, name)

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self.counts[name] += 1
            return attribute(*args, **kwargs)

        return wrapper


@pytest.fixture
def counting_traci(monkeypatch: pytest.MonkeyPatch) -> _CountingApi:
    api = _CountingApi(transport_module.traci)
    monkeypatch.setattr(transport_module, "traci", api)
    return api


def test_traci_state_reads_per_step_do_not_scale_with_vehicle_count(
    reference_net: Path, reference_routes: Path, counting_traci: _CountingApi
) -> None:
    backend = SumoBackend()
    backend.start(reference_net, reference_routes, make_config(transport="traci"))
    try:
        backend.step()
        sparse = backend.project()
        counting_traci.counts.clear()
        backend.step()
        backend.project()
        sparse_calls = Counter(counting_traci.counts)

        for _ in range(600):
            backend.step()
            dense = backend.project()
        counting_traci.counts.clear()
        backend.step()
        backend.project()
        dense_calls = Counter(counting_traci.counts)
    finally:
        backend.close()

    # The premise: the two samples really are at different densities, or the
    # assertion below would be vacuous.
    assert len(dense.vehicles) > 5 * len(sparse.vehicles)

    reads_sparse = {k: v for k, v in sparse_calls.items() if k in _STATE_READING_CALLS}
    reads_dense = {k: v for k, v in dense_calls.items() if k in _STATE_READING_CALLS}
    assert reads_sparse == reads_dense == dict.fromkeys(_STATE_READING_CALLS, 1)

    # Nothing else is called at all except advancing the simulation once and
    # subscribing vehicles that departed this step, which is bounded by the
    # departure rate rather than by the population.
    allowed = _STATE_READING_CALLS | {"simulationStep", "vehicle.subscribe"}
    assert set(sparse_calls) <= allowed
    assert set(dense_calls) <= allowed
    assert sparse_calls["simulationStep"] == dense_calls["simulationStep"] == 1
    assert dense_calls["vehicle.subscribe"] < len(dense.vehicles) / 5


@pytest.mark.parametrize("transport", ["traci", "libsumo"])
def test_project_performs_exactly_one_batched_fetch(
    transport: str,
    reference_net: Path,
    reference_routes: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whatever the mechanism, `project()` reads the whole step exactly once."""
    fetches = Counter[str]()
    for name in ("TraciTransport", "LibsumoTransport"):
        cls = getattr(transport_module, name)
        original = cls.fetch

        def counted(self: Any, _original: Any = original) -> Any:
            fetches["fetch"] += 1
            return _original(self)

        monkeypatch.setattr(cls, "fetch", counted)

    backend = SumoBackend()
    backend.start(reference_net, reference_routes, make_config(transport=transport))
    try:
        for _ in range(20):
            backend.step()
        assert fetches["fetch"] == 0, "stepping must not fetch state"
        for expected in range(1, 6):
            backend.project()
            assert fetches["fetch"] == expected
    finally:
        backend.close()


def test_no_per_object_query_method_is_exposed() -> None:
    """The public surface is fixed, and nothing on it takes an object id.

    A regression guard with teeth: adding `vehicle(id)` or `queue_on(lane)`
    "just for debugging" fails here, which is the point. `D-031` is explicit
    that once other layers can ask for anything at any time, the property is
    unrecoverable.
    """
    public = {name for name in vars(SumoBackend) if not name.startswith("_")}
    assert public == {
        "start",
        "step",
        "project",
        "apply",
        "index",
        "save_state",
        "load_state",
        "close",
    }
