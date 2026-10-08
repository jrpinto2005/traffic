"""`BackendIndex.vehicle_types`: the vType ID -> `VehicleType` map (T1.8 ruling E3).

SUMO's tripinfo names a trip's vType *ID*, not its class, so the trip records
need the same resolution the projector applies to live vehicles. One map, built
once at `start()`, read by both.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.backend.conftest import Scenario, make_config
from traffic_lab.backend import SumoBackend, TransportName
from traffic_lab.domain.network import VehicleType

_ROUTES = """<routes>
    <vType id="car" vClass="passenger"/>
    <vType id="moto" vClass="motorcycle"/>
    <vType id="bike" vClass="bicycle"/>
</routes>
"""


@pytest.mark.parametrize("transport", ["traci", "libsumo"])
def test_the_index_resolves_declared_types_through_their_class(
    scenario: Scenario, tmp_path: Path, transport: TransportName
) -> None:
    routes = tmp_path / "types.rou.xml"
    routes.write_text(_ROUTES)
    backend = SumoBackend()
    backend.start(scenario.net, routes, make_config(transport=transport), network=scenario.network)
    try:
        types = backend.index.vehicle_types
    finally:
        backend.close()

    assert types["car"] is VehicleType.CAR
    assert types["moto"] is VehicleType.MOTORCYCLE
    # SUMO's implicit default type, which demand without a `type` attribute uses.
    assert types["DEFAULT_VEHTYPE"] is VehicleType.CAR
    # Outside the canonical ontology: absent, not coerced.
    assert "bike" not in types
    assert "DEFAULT_BIKETYPE" not in types


def test_the_map_cannot_be_modified_through_the_index(scenario: Scenario) -> None:
    backend = SumoBackend()
    backend.start(scenario.net, scenario.routes, make_config(), network=scenario.network)
    try:
        types = backend.index.vehicle_types
        with pytest.raises(TypeError):
            types["intruder"] = VehicleType.CAR  # type: ignore[index]
    finally:
        backend.close()
