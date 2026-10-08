"""`build_routes()`: a `DemandSpec` as one SUMO route file (D-022, T1.5 as amended 2026-10-07).

**Realisation** (D-022's mapping to SUMO):

- **Sources** are `<flow>`s with `period="exp(rate)"`: exponential headways, so
  Poisson arrivals at `rate` veh/s. A mid-link source sets `departPos`. A type
  mix is one flow per type at `rate x share` -- independent Poisson streams whose
  superposition is a Poisson stream at `rate`, each vehicle's type drawn with
  probability `share`.
- **Turning ratios** are `<edgeRelation from= to= probability=/>` (the modern
  turn-file format; `<fromEdge>`/`<toEdge>` is deprecated in SUMO 1.27.1) fed to
  `jtrrouter` with the declared `--sink-edges`. `jtrrouter` expands every flow
  into explicit `<vehicle>`s with fixed routes.
- **Attrition** post-processes those routes (Amendment A3): walking each route,
  on an edge with attrition rate `a` the vehicle is locally destined with
  probability `a`; its route is cut there and given an `arrivalPos` drawn
  uniformly on that edge -- beyond its departure position on the edge it enters
  on -- in whole centimetres, strictly short of the edge's end so tripinfo can
  never show it as a sink arrival.

**Rates** are a fraction of the receiving approach's saturation flow (D-022):

    rate_veh_per_s = rate_saturation_fraction x n_lanes x s_through / 3600

where `n_lanes` is the source edge's lane count and `s_through` the per-lane
through saturation flow calibrated in SUMO for cars at that edge's speed limit
(D-037, `saturation.per_lane_saturation_flow_vph`). Mixed traffic has no
calibrated saturation flow at M1, so a type mix with a non-car share is refused
(D-037's revisit trigger is M4's motorcycles).

**Seeding** (D-017). `seed` is the demand stream's. It is split by
`numpy.random.SeedSequence` into two independent children: one seeds
`jtrrouter` (arrival times, type draws through the per-type flows, turn choices)
and one the attrition sampler. SUMO reads `--seed` as a signed 32-bit integer,
which a derived stream seed overflows about half the time, so `jtrrouter`
receives its child's first 32-bit word shifted right by one. Same seed, same
bytes: the file is written here, not copied from `jtrrouter` (whose header
carries a timestamp).

**Order.** SUMO silently drops a route-file entry that departs earlier than the
one before it. Vehicles are written in `jtrrouter`'s order, which is by
departure, and the order is asserted before writing.

**Max-edges.** With sink edges declared, a route `jtrrouter` cuts at its
maximum-edges limit cannot be closed and `jtrrouter` fails with "could not be
closed" per route. Those are counted and logged on every build, zero included
(D-022's memoryless-routing artifact). Validation guarantees every reachable
non-sink edge has turning ratios, so no other route can fail to close.
"""

from __future__ import annotations

import logging
import math
import re
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from pathlib import Path
from xml.sax.saxutils import quoteattr

import numpy as np

from traffic_lab.domain.demand import DemandSpec, SourceSpec
from traffic_lab.domain.network import (
    Edge,
    EdgeId,
    JunctionId,
    Movement,
    Network,
    TurnDirection,
    VehicleType,
    movements_of,
)
from traffic_lab.scenarios.parse import SumoIds
from traffic_lab.scenarios.saturation import per_lane_saturation_flow_vph
from traffic_lab.scenarios.tools import SumoToolError, run_tool
from traffic_lab.scenarios.vehicles import depart_xml, vtype_id, vtype_xml

logger = logging.getLogger(__name__)

#: SS8 invariant 15: |sum of a junction approach's turn ratios - 1| at most this.
TURN_RATIO_TOLERANCE = 1e-6

#: |sum of a source's type shares - 1| at most this.
TYPE_MIX_TOLERANCE = 1e-6

#: Every flow runs from 0 to this, seconds: SUMO's own default flow duration (24 h),
#: written explicitly because SUMO warns when a flow has no end. `DemandSpec`
#: carries no horizon, so the files cover any run shorter than a day.
DEMAND_END_S = 86400.0

#: Files `build_routes()` writes to `out`.
ROUTES_FILE = "demand.rou.xml"
FLOWS_FILE = "demand.flows.xml"
TURNS_FILE = "demand.turns.xml"

_NOT_CLOSED = re.compile(r"^Error: The route starting at edge '.*' could not be closed\.$", re.M)


class DemandValidationError(ValueError):
    """A `DemandSpec` that cannot be built, naming the offending edge.

    `invariant` is the `05_DOMAIN_MODEL.md` SS8 invariant violated (15 or 16),
    or `None` for a spec that is malformed in some other way.
    """

    def __init__(self, invariant: int | None, message: str) -> None:
        prefix = f"invariant {invariant}: " if invariant is not None else ""
        super().__init__(prefix + message)
        self.invariant = invariant


class DemandOrderError(RuntimeError):
    """The routes are not in departure order, which SUMO would silently thin."""


class MaxEdgesLimitError(RuntimeError):
    """`jtrrouter` cut routes at its maximum-edges limit (D-022)."""


# --- Saturation flow ------------------------------------------------------------


def approach_saturation_flow_vph(network: Network, edge: EdgeId) -> float:
    """Saturation flow of `edge`, veh/h: its lane count x the per-lane through value (D-037)."""
    the_edge = network.edges[edge]
    speeds = {network.lanes[lane].speed_limit_mps for lane in the_edge.lanes}
    if len(speeds) != 1:
        raise DemandValidationError(
            None,
            f"edge {edge} has lanes with speed limits {sorted(speeds)}; D-037 calibrates "
            f"saturation flow per speed limit, so an approach needs one",
        )
    (speed,) = speeds
    through = per_lane_saturation_flow_vph(VehicleType.CAR, speed, TurnDirection.THROUGH)
    return len(the_edge.lanes) * through


def source_rate_veh_per_s(network: Network, source: SourceSpec) -> float:
    """The source's total Poisson rate, veh/s."""
    return (
        source.rate_saturation_fraction
        * approach_saturation_flow_vph(network, source.edge)
        / 3600.0
    )


# --- Validation (SS8 invariants 15-16) -------------------------------------------


def validate_demand(network: Network, ids: SumoIds, spec: DemandSpec) -> None:
    """Raise `DemandValidationError`, naming the edge, for a spec that cannot be built."""
    edges = network.edges

    def name(edge: EdgeId) -> str:
        return f"{ids.edges[edge]} (EdgeId {int(edge)})"

    def check_edge(edge: EdgeId, role: str) -> Edge:
        if not 0 <= int(edge) < len(edges):
            raise DemandValidationError(
                None, f"{role} names EdgeId {int(edge)}, not in the network"
            )
        if ids.edges[edge].startswith(":"):
            raise DemandValidationError(None, f"{role} names {name(edge)}, an internal edge")
        return edges[edge]

    for edge in spec.sink_edges:
        check_edge(edge, "sink_edges")

    attrition: dict[EdgeId, float] = {}
    for a in spec.attrition:
        check_edge(a.edge, "attrition")
        if a.edge in attrition:
            raise DemandValidationError(None, f"attrition declared twice on {name(a.edge)}")
        if not 0.0 <= a.rate < 1.0:
            raise DemandValidationError(
                16, f"attrition rate on {name(a.edge)} is {a.rate}, not in [0, 1)"
            )
        attrition[a.edge] = a.rate

    ratios = _validated_turn_ratios(network, spec, name, check_edge)

    for k, source in enumerate(spec.sources):
        source_edge = check_edge(source.edge, f"source {k}")
        if not (
            math.isfinite(source.rate_saturation_fraction) and source.rate_saturation_fraction > 0
        ):
            raise DemandValidationError(
                None,
                f"source {k} on {name(source.edge)} has rate_saturation_fraction "
                f"{source.rate_saturation_fraction}, must be > 0",
            )
        if source.position_m is not None and not 0.0 <= source.position_m < source_edge.length_m:
            raise DemandValidationError(
                None,
                f"source {k} on {name(source.edge)} at {source.position_m} m, outside the "
                f"edge's [0, {source_edge.length_m}) m",
            )
        shares = dict(source.type_mix)
        if any(not share >= 0.0 for share in shares.values()) or not math.isclose(
            sum(shares.values()), 1.0, rel_tol=0.0, abs_tol=TYPE_MIX_TOLERANCE
        ):
            raise DemandValidationError(
                None,
                f"source {k} on {name(source.edge)} has type mix {_mix(shares)}; shares must "
                f"be >= 0 and sum to 1",
            )
        uncalibrated = sorted(t.value for t, s in shares.items() if s > 0 and t != VehicleType.CAR)
        if uncalibrated:
            raise DemandValidationError(
                None,
                f"source {k} on {name(source.edge)} mixes in {', '.join(uncalibrated)}: an "
                f"approach's saturation flow is calibrated for cars only at M1 (D-037; "
                f"motorcycles are its M4 revisit trigger)",
            )

    # Every edge a route can reach must end it (a sink) or continue it (turn ratios):
    # anything else is a route jtrrouter cannot close, or one closed by its defaults.
    reached: set[EdgeId] = set()
    frontier = [s.edge for s in spec.sources]
    while frontier:
        edge = frontier.pop()
        if edge in reached:
            continue
        reached.add(edge)
        if edge in spec.sink_edges:
            continue
        key = (edges[edge].to_junction, edge)
        if key not in ratios:
            raise DemandValidationError(
                15,
                f"routes reach {name(edge)}, which is not a sink and has no turn ratios at "
                f"its downstream junction",
            )
        frontier.extend(m.to_edge for m, p in ratios[key] if p > 0.0)


def _validated_turn_ratios(
    network: Network,
    spec: DemandSpec,
    name: Callable[[EdgeId], str],
    check_edge: Callable[[EdgeId, str], Edge],
) -> dict[tuple[JunctionId, EdgeId], list[tuple[Movement, float]]]:
    """Invariant 15 for each `TurnRatioSpec`; returns (movement, probability) per approach."""
    out: dict[tuple[JunctionId, EdgeId], list[tuple[Movement, float]]] = {}
    for spec_ratio in spec.turn_ratios:
        edge = check_edge(spec_ratio.from_edge, "turn_ratios")
        where = f"{name(spec_ratio.from_edge)} at JunctionId {int(spec_ratio.junction)}"
        if edge.to_junction != spec_ratio.junction:
            raise DemandValidationError(
                15, f"turn ratios for {where}: the edge does not enter that junction"
            )
        key = (spec_ratio.junction, spec_ratio.from_edge)
        if key in out:
            raise DemandValidationError(15, f"turn ratios declared twice for {where}")
        ratios = dict(spec_ratio.ratios)
        total = sum(ratios.values())
        if any(not p >= 0.0 for p in ratios.values()) or not math.isclose(
            total, 1.0, rel_tol=0.0, abs_tol=TURN_RATIO_TOLERANCE
        ):
            raise DemandValidationError(
                15,
                f"turn ratios for {where} are {_mix(ratios)}, summing to {total}; they must "
                f"be >= 0 and sum to 1.0 within {TURN_RATIO_TOLERANCE}",
            )
        movements = {
            m.turn: m
            for m in movements_of(network, spec_ratio.junction)
            if m.from_edge == spec_ratio.from_edge
        }
        missing = sorted(t.value for t, p in ratios.items() if p > 0 and t not in movements)
        if missing:
            raise DemandValidationError(
                15,
                f"turn ratios for {where} send traffic {', '.join(missing)}, but the approach "
                f"has only {', '.join(sorted(t.value for t in movements))}",
            )
        # Every movement listed, unlisted ones at 0, so jtrrouter applies no defaults.
        out[key] = [(m, float(ratios.get(turn, 0.0))) for turn, m in movements.items()]
    return out


def _mix(shares: dict[TurnDirection, float] | dict[VehicleType, float]) -> str:
    return "{" + ", ".join(f"{k.value}: {v}" for k, v in shares.items()) + "}"


# --- Building ------------------------------------------------------------------


def build_routes(
    net_file: Path, network: Network, ids: SumoIds, spec: DemandSpec, seed: int, out: Path
) -> Path:
    """Emit SUMO route files into the directory `out`. Returns the path passed to Backend.start().

    `seed` is the `demand` stream's seed (D-017). Raises `DemandValidationError`
    (naming the edge) before writing anything for a spec violating SS8
    invariants 15-16 or otherwise unbuildable.
    """
    validate_demand(network, ids, spec)
    if seed < 0:
        raise ValueError(f"seed must be >= 0, got {seed}")
    jtrrouter_seq, attrition_seq = np.random.SeedSequence(seed).spawn(2)
    jtrrouter_seed = int(jtrrouter_seq.generate_state(1)[0]) >> 1  # SUMO's --seed is int32

    out.mkdir(parents=True, exist_ok=True)
    flows = out / FLOWS_FILE
    turns = out / TURNS_FILE
    flows.write_text(_flows_xml(network, ids, spec))
    turns.write_text(_turns_xml(network, ids, spec))

    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "jtrrouter.rou.xml"
        code, output = run_tool(
            "jtrrouter",
            [
                "--net-file",
                str(net_file),
                "--route-files",
                str(flows),
                "--turn-ratio-files",
                str(turns),
                "--sink-edges",
                ",".join(sorted(ids.edges[e] for e in spec.sink_edges)),
                "--seed",
                str(jtrrouter_seed),
                "--output-file",
                str(raw),
                "--no-step-log",
                "true",
            ],
            allow_failure=True,
        )
        vehicles = _parse_vehicles(raw) if raw.exists() else []
        hits = count_max_edges_hits(output)
        logger.info(
            "jtrrouter max-edges limit: %d of %d route generations hit it (D-022)",
            hits,
            len(vehicles),
        )
        if hits:
            raise MaxEdgesLimitError(
                f"{hits} routes hit jtrrouter's maximum-edges limit and could not be closed "
                f"at a sink (D-022: adjust the turn ratios)"
            )
        if code != 0:
            raise SumoToolError(f"jtrrouter failed ({code}):\n{output}")

    rng = np.random.default_rng(attrition_seq)
    rates = {a.edge: a.rate for a in spec.attrition if a.rate > 0.0}
    edge_of = {sumo_id: EdgeId(i) for i, sumo_id in enumerate(ids.edges)}
    length = {sumo_id: network.edges[e].length_m for sumo_id, e in edge_of.items()}
    for attributes, route in vehicles:
        for i, sumo_edge in enumerate(route):
            rate = rates.get(edge_of[sumo_edge])
            if rate is None or not rng.random() < rate:
                continue
            start_m = float(attributes.get("departPos", "0")) if i == 0 else 0.0
            del route[i + 1 :]
            attributes["arrivalPos"] = _arrival_pos(rng, start_m, length[sumo_edge])
            break

    check_departure_order(float(attributes["depart"]) for attributes, _ in vehicles)
    routes = out / ROUTES_FILE
    routes.write_text(_routes_xml(vehicles))
    return routes


def count_max_edges_hits(jtrrouter_output: str) -> int:
    """Routes `jtrrouter` reports it could not close: with sink edges declared and
    every reachable non-sink edge given turn ratios, those its max-edges limit cut."""
    return len(_NOT_CLOSED.findall(jtrrouter_output))


def check_departure_order(departures_s: Iterable[float]) -> None:
    """Raise `DemandOrderError` unless departures never decrease: SUMO drops, without an
    error, a route-file entry departing earlier than the one before it."""
    previous = -math.inf
    for k, depart in enumerate(departures_s):
        if depart < previous:
            raise DemandOrderError(
                f"vehicle {k} departs at {depart} s, before its predecessor at {previous} s; "
                f"SUMO would silently drop it"
            )
        previous = depart


def _arrival_pos(rng: np.random.Generator, start_m: float, length_m: float) -> str:
    """Uniform on the whole centimetres strictly between `start_m` and `length_m`."""
    low_cm = math.floor(start_m * 100.0) + 1
    high_cm = math.ceil(length_m * 100.0) - 1  # inclusive
    if high_cm < low_cm:
        raise DemandValidationError(
            None, f"no arrival position between {start_m} m and the edge end at {length_m} m"
        )
    cm = int(rng.integers(low_cm, high_cm + 1))
    return f"{cm // 100}.{cm % 100:02d}"


def _flows_xml(network: Network, ids: SumoIds, spec: DemandSpec) -> str:
    lines = ["<routes>"]
    lines += [f"    {vtype_xml(t)}" for t in VehicleType]
    for k, source in enumerate(spec.sources):
        rate = source_rate_veh_per_s(network, source)
        position = "" if source.position_m is None else f' departPos="{source.position_m!r}"'
        for vehicle_type in VehicleType:
            share = source.type_mix.get(vehicle_type, 0.0)
            if share <= 0.0:
                continue
            lines.append(
                f'    <flow id="source{k}_{vehicle_type.value}" type="{vtype_id(vehicle_type)}" '
                f'from={quoteattr(ids.edges[source.edge])} begin="0" '
                f'end="{DEMAND_END_S:.0f}" period="exp({rate * share!r})"{position}'
                f"{depart_xml()}/>"
            )
    lines.append("</routes>")
    return "\n".join(lines) + "\n"


def _turns_xml(network: Network, ids: SumoIds, spec: DemandSpec) -> str:
    lines = ["<edgeRelations>"]
    for spec_ratio in spec.turn_ratios:
        movements = {
            m.turn: m
            for m in movements_of(network, spec_ratio.junction)
            if m.from_edge == spec_ratio.from_edge
        }
        for turn, movement in movements.items():
            lines.append(
                f"    <edgeRelation from={quoteattr(ids.edges[movement.from_edge])} "
                f"to={quoteattr(ids.edges[movement.to_edge])} "
                f'probability="{float(spec_ratio.ratios.get(turn, 0.0))!r}"/>'
            )
    lines.append("</edgeRelations>")
    return "\n".join(lines) + "\n"


def _parse_vehicles(raw: Path) -> list[tuple[dict[str, str], list[str]]]:
    vehicles: list[tuple[dict[str, str], list[str]]] = []
    for element in ET.parse(raw).getroot().iter("vehicle"):
        route = element.find("route")
        if route is None:
            raise SumoToolError(f"jtrrouter wrote vehicle {element.get('id')} without a route")
        vehicles.append((dict(element.attrib), route.get("edges", "").split()))
    return vehicles


def _routes_xml(vehicles: list[tuple[dict[str, str], list[str]]]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!-- Generated by traffic_lab.scenarios.demand.build_routes (T1.5, D-022). -->",
        "<routes>",
    ]
    lines += [f"    {vtype_xml(t)}" for t in VehicleType]
    for attributes, route in vehicles:
        attrs = "".join(f" {k}={quoteattr(v)}" for k, v in attributes.items())
        lines.append(f"    <vehicle{attrs}>")
        lines.append(f'        <route edges="{" ".join(route)}"/>')
        lines.append("    </vehicle>")
    lines.append("</routes>")
    return "\n".join(lines) + "\n"
