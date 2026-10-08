"""Shared helpers for the demand tests: specs on a built intersection, route files, tripinfo.

Route files and tripinfo are read with `xml.etree` directly, independently of
`traffic_lab.scenarios.demand`, so a test checks the generator against the
files and against SUMO rather than against itself.
"""

from __future__ import annotations

import os
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import sumolib

from tests.generated_scenario import Built
from traffic_lab.domain.demand import AttritionSpec, DemandSpec, SourceSpec, TurnRatioSpec
from traffic_lab.domain.network import EdgeId, JunctionId, TurnDirection, VehicleType

S, L, R = TurnDirection.THROUGH, TurnDirection.LEFT, TurnDirection.RIGHT
CARS = {VehicleType.CAR: 1.0}

#: Turn split used throughout: deliberately unequal, so a swap would show.
SPLIT = {S: 0.6, R: 0.25, L: 0.15}


def edge(built: Built, sumo_id: str) -> EdgeId:
    return EdgeId(built.ids.edges.index(sumo_id))


def center(built: Built) -> JunctionId:
    return built.intersection.junction


def approaches(built: Built) -> list[str]:
    return [f"approach_{k}_in" for k in range(built.spec.approaches)]


def exits(built: Built) -> list[str]:
    return [f"approach_{k}_out" for k in range(built.spec.approaches)]


def four_source_spec(
    built: Built,
    level: float,
    *,
    split: Mapping[TurnDirection, float] = SPLIT,
    attrition: Mapping[str, float] | None = None,
    positions: Mapping[str, float] | None = None,
) -> DemandSpec:
    """A source on every approach at `level`, the same split everywhere, every exit a sink."""
    positions = positions or {}
    return DemandSpec(
        sources=tuple(
            SourceSpec(edge(built, e), positions.get(e), level, CARS) for e in approaches(built)
        ),
        turn_ratios=tuple(
            TurnRatioSpec(center(built), edge(built, e), dict(split)) for e in approaches(built)
        ),
        attrition=tuple(
            AttritionSpec(edge(built, e), rate) for e, rate in (attrition or {}).items()
        ),
        sink_edges=frozenset(edge(built, e) for e in exits(built)),
    )


@dataclass(frozen=True)
class RouteEntry:
    id: str
    type: str
    depart_s: float
    edges: tuple[str, ...]
    depart_pos_m: float | None
    arrival_pos_m: float | None


def read_routes(path: Path) -> list[RouteEntry]:
    entries = []
    for v in ET.parse(path).getroot().iter("vehicle"):
        route = v.find("route")
        assert route is not None
        entries.append(
            RouteEntry(
                id=v.get("id", ""),
                type=v.get("type", ""),
                depart_s=float(v.get("depart", "nan")),
                edges=tuple(route.get("edges", "").split()),
                depart_pos_m=float(v.get("departPos", "nan")) if "departPos" in v.attrib else None,
                arrival_pos_m=(
                    float(v.get("arrivalPos", "nan")) if "arrivalPos" in v.attrib else None
                ),
            )
        )
    return entries


@dataclass(frozen=True)
class Trip:
    id: str
    vtype: str
    arrival_s: float
    arrival_edge: str
    arrival_pos_m: float
    depart_edge: str


def run_sumo(net: Path, routes: Path, tripinfo: Path, end_s: float, *, seed: int = 1) -> None:
    """Run the `sumo` binary to `end_s`, writing tripinfo for arrived vehicles only."""
    subprocess.run(
        [
            sumolib.checkBinary("sumo"),
            "--net-file",
            str(net),
            "--route-files",
            str(routes),
            "--seed",
            str(seed),
            "--end",
            str(end_s),
            "--time-to-teleport",
            "-1",
            "--eager-insert",
            "--tripinfo-output",
            str(tripinfo),
            "--no-step-log",
            "true",
            "--duration-log.disable",
            "true",
            "--xml-validation",
            "never",
        ],
        check=True,
        capture_output=True,
        env={**os.environ, "LC_ALL": "C"},
    )


def read_trips(tripinfo: Path) -> dict[str, Trip]:
    trips = {}
    for t in ET.parse(tripinfo).getroot().iter("tripinfo"):
        trips[t.get("id", "")] = Trip(
            id=t.get("id", ""),
            vtype=t.get("vType", ""),
            arrival_s=float(t.get("arrival", "nan")),
            arrival_edge=t.get("arrivalLane", "").rsplit("_", 1)[0],
            arrival_pos_m=float(t.get("arrivalPos", "nan")),
            depart_edge=t.get("departLane", "").rsplit("_", 1)[0],
        )
    return trips


def lane_length_m(net: Path, sumo_edge: str) -> float:
    for e in ET.parse(net).getroot().iter("edge"):
        if e.get("id") == sumo_edge:
            return float(e.findall("lane")[0].get("length", "nan"))
    raise KeyError(sumo_edge)


def analysed_trips(routes: list[RouteEntry], trips: dict[str, Trip], cutoff_s: float) -> list[Trip]:
    """The tripinfo records of every vehicle scheduled to depart before `cutoff_s`.

    Asserts each one is there: counting in tripinfo, not the route file, and
    requiring the two to agree, makes a vehicle SUMO dropped fail the test
    instead of skewing a fraction. The run must end long enough after
    `cutoff_s` for every such vehicle to finish.
    """
    scheduled = [r.id for r in routes if r.depart_s < cutoff_s]
    missing = [i for i in scheduled if i not in trips]
    assert not missing, f"{len(missing)} of {len(scheduled)} scheduled vehicles never arrived"
    assert set(trips) <= {r.id for r in routes}, "tripinfo has vehicles not in the route file"
    return [trips[i] for i in scheduled]
