"""The SUMO `vType` of each canonical `VehicleType`, and how vehicles are inserted.

One definition shared by the route files `build_routes()` writes and the
saturation-flow calibration (D-037), so demand fractions are fractions of a
capacity measured with the very vehicles that will drive.

Dynamics live in SUMO's `vType` and are never interpreted here (D-003): a type is
its `vClass` and SUMO's defaults for that class, which is why calibration
results are keyed by the SUMO version *and* a hash of these attributes.
"""

from __future__ import annotations

import hashlib
import json
from xml.sax.saxutils import quoteattr

from traffic_lab.domain.network import VehicleType
from traffic_lab.scenarios.parse import SUMO_CLASS_OF_TYPE

#: How every generated vehicle enters the network: the lane SUMO judges best for
#: the route, at the highest safe speed. The shared test fixture's convention
#: (`tests/generated_scenario.py`), ratified for T1.5 (escalation E4).
DEPART_ATTRIBUTES: tuple[tuple[str, str], ...] = (("departLane", "best"), ("departSpeed", "max"))


def vtype_id(vehicle_type: VehicleType) -> str:
    """The `vType` ID: the canonical name, so tripinfo's `type` reads back directly."""
    return vehicle_type.value


def vtype_attributes(vehicle_type: VehicleType) -> dict[str, str]:
    """The `vType`'s parameters, ID excluded: its SUMO class and nothing else."""
    return {"vClass": SUMO_CLASS_OF_TYPE[vehicle_type]}


def vtype_hash(vehicle_type: VehicleType) -> str:
    """SHA-256 of the `vType` parameters, the calibration key (D-037)."""
    canonical = json.dumps(vtype_attributes(vehicle_type), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def vtype_xml(vehicle_type: VehicleType) -> str:
    attributes = "".join(f" {k}={quoteattr(v)}" for k, v in vtype_attributes(vehicle_type).items())
    return f"<vType id={quoteattr(vtype_id(vehicle_type))}{attributes}/>"


def depart_xml() -> str:
    """`DEPART_ATTRIBUTES` as XML attributes, with a leading space."""
    return "".join(f" {k}={quoteattr(v)}" for k, v in DEPART_ATTRIBUTES)
