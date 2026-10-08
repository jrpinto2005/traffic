"""Demand variants on the generated intersection for the trip-level tests (T1.8).

The shared fixture (`tests/generated_scenario.py`) has one vehicle type and no
attrition. The tripinfo and metrics tests need what it lacks, each built on a
T1.3-generated intersection and never on the M0 reference:

* two `vType`s, `passenger` and `motorcycle` (`07_EXPERIMENT_METHODOLOGY.md` SS2.4);
* trips with a declared `arrivalPos` (D-022's mid-link attrition);
* insertions at standstill, one free to drive away and one held behind a
  stopped vehicle (07 SS2.1 as amended: stops is SUMO's `waitingCount`);
* an overload that leaves vehicles undeparted (D-008's insertion loss).

Every time and position below is chosen so the expected tripinfo values can be
stated in advance; where a test asserts one, the derivation is next to it.

Test support only; demand generation is T1.5's.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from tests.generated_scenario import Built
from traffic_lab.backend import BackendConfig, SumoBackend
from traffic_lab.domain.network import Movement, TurnDirection
from traffic_lab.domain.state import TrueState

#: Deterministic drivers (`sigma="0"`, no speed deviation), so free-flow trips
#: have exactly computable travel times and zero time loss.
CAR_TYPE = "car"
MOTO_TYPE = "moto"
VTYPES = (
    f'    <vType id="{CAR_TYPE}" vClass="passenger" accel="2.6" decel="4.5" sigma="0" '
    'length="5" minGap="2.5" maxSpeed="13.89" speedFactor="1" speedDev="0"/>\n'
    f'    <vType id="{MOTO_TYPE}" vClass="motorcycle" accel="3.0" decel="5" sigma="0" '
    'length="2.2" minGap="1.5" maxSpeed="13.89" speedFactor="1" speedDev="0"/>\n'
)

#: Where the mid-link trips in `semantics_routes` are removed, metres along the lane.
MID_LINK_ARRIVAL_POS_M = 100.0

#: The flood of `semantics_routes`: one vehicle a second on one lane of one
#: through movement, `FLOOD_BEGIN_S` to `FLOOD_END_S` -- far above what a lane
#: under a four-phase signal discharges, so its tail is still waiting to enter
#: when the run ends. Vehicle `flood.n` is scheduled at `FLOOD_BEGIN_S + n`.
FLOOD_BEGIN_S = 60
FLOOD_END_S = 400

#: How long the two blockers of `semantics_routes` stand on the outbound edge.
BLOCKER_STOP_S = 40


def through_movements(built: Built) -> list[Movement]:
    return [m for m in built.movements if m.turn is TurnDirection.THROUGH]


def semantics_routes(built: Built, path: Path) -> Path:
    """One vehicle per tripinfo case, plus a flood that cannot all get in.

    Single-edge trips run on an outbound edge, which no signal controls, so
    their free-flow values are exact:

    * `sink_free` (car) and `mid_free` (motorcycle, `arrivalPos`): free flow;
    * `stand_free`: inserted at 0 m/s on an empty lane, drives straight off;
    * `stand_held`: inserted at 0 m/s directly behind `blk0`, which -- with
      `blk1` beside it on the other lane -- stands for `BLOCKER_STOP_S`, so the
      probe is still halted at its first move step;
    * `late` departs ten seconds before any run of `semantics` ends: unfinished.
    """
    m_out, m_flood = through_movements(built)[1], through_movements(built)[0]
    out_edge = built.ids.edges[m_out.to_edge]
    flood_edges = f"{built.ids.edges[m_flood.from_edge]} {built.ids.edges[m_flood.to_edge]}"
    lines = [
        "<routes>",
        VTYPES.rstrip("\n"),
        f'    <route id="out" edges="{out_edge}"/>',
        f'    <route id="flood_route" edges="{flood_edges}"/>',
        # The blockers' stop is on the first lane positions after their own
        # departure, so they are standing still before `stand_held` arrives.
        f'    <vehicle id="blk0" type="{CAR_TYPE}" route="out" depart="0" departPos="60" '
        f'departSpeed="0" departLane="0"><stop lane="{out_edge}_0" endPos="62" '
        f'duration="{BLOCKER_STOP_S}"/></vehicle>',
        f'    <vehicle id="blk1" type="{CAR_TYPE}" route="out" depart="0" departPos="60" '
        f'departSpeed="0" departLane="1"><stop lane="{out_edge}_1" endPos="62" '
        f'duration="{BLOCKER_STOP_S}"/></vehicle>',
        # 62 m stop line minus a 5 m car minus 2.5 m minGap: front bumper at 54.5.
        f'    <vehicle id="stand_held" type="{CAR_TYPE}" route="out" depart="5" departPos="54" '
        f'departSpeed="0" departLane="0"/>',
        # SUMO drops, with only a warning (suppressed here), any route-file entry
        # whose departure precedes the one before it: keep these in time order.
        f'    <flow id="flood" type="{CAR_TYPE}" route="flood_route" begin="{FLOOD_BEGIN_S}" '
        f'end="{FLOOD_END_S}" period="1" departLane="0" departSpeed="max"/>',
        f'    <vehicle id="sink_free" type="{CAR_TYPE}" route="out" depart="100" '
        f'departSpeed="max" departLane="0"/>',
        f'    <vehicle id="mid_free" type="{MOTO_TYPE}" route="out" depart="110" '
        f'departSpeed="max" departLane="1" arrivalPos="{MID_LINK_ARRIVAL_POS_M}"/>',
        f'    <vehicle id="stand_free" type="{CAR_TYPE}" route="out" depart="130" '
        f'departSpeed="0" departLane="0"/>',
        f'    <vehicle id="late" type="{MOTO_TYPE}" route="out" depart="{SEMANTICS_END_S - 10}" '
        f'departSpeed="max"/>',
        "</routes>",
    ]
    path.write_text("\n".join(lines) + "\n")
    return path


#: How long `semantics_routes` is run for.
SEMANTICS_END_S = 600


def mixed_type_flows(built: Built, path: Path, end_s: float, *, period_s: float) -> Path:
    """`one_flow_per_movement`'s load, split between cars and motorcycles.

    Every movement carries a car flow and a motorcycle flow, each at twice
    `period_s` and offset by half of it, so the combined arrival rate per
    movement is the same as one flow at `period_s`. A movement's `arrivalPos`
    is declared on every third movement's motorcycles, so mid-link arrivals of
    one type exist alongside sink arrivals of both.
    """
    lines = ["<routes>", VTYPES.rstrip("\n")]
    cars, motos = [], []
    for k, movement in enumerate(built.movements):
        edges = (
            f'from="{built.ids.edges[movement.from_edge]}" to="{built.ids.edges[movement.to_edge]}"'
        )
        attrition = f' arrivalPos="{MID_LINK_ARRIVAL_POS_M}"' if k % 3 == 0 else ""
        cars.append(
            f'    <flow id="c{k}" type="{CAR_TYPE}" {edges} begin="0" end="{end_s}" '
            f'period="{2 * period_s}" departLane="best" departSpeed="max"/>'
        )
        motos.append(
            f'    <flow id="m{k}" type="{MOTO_TYPE}" {edges} begin="{period_s}" end="{end_s}" '
            f'period="{2 * period_s}" departLane="best" departSpeed="max"{attrition}/>'
        )
    # Every car flow before any motorcycle flow: SUMO silently drops an entry
    # that begins earlier than the one before it.
    lines += cars + motos
    lines.append("</routes>")
    path.write_text("\n".join(lines) + "\n")
    return path


@dataclass(frozen=True)
class Run:
    """One finished SUMO run: every projected state, and where its tripinfo is."""

    states: tuple[TrueState, ...]
    tripinfo: Path
    backend: SumoBackend  # closed; kept for its `index`

    @property
    def end_s(self) -> float:
        return self.states[-1].time_s


def run(built: Built, routes: Path, tripinfo: Path, steps: int, config: BackendConfig) -> Run:
    """Drive `steps` steps of `step()` + `project()`, then close SUMO."""
    backend = SumoBackend()
    backend.start(built.net, routes, config, network=built.network)
    states: list[TrueState] = []
    try:
        for _ in range(steps):
            backend.step()
            states.append(backend.project())
    finally:
        backend.close()
    return Run(tuple(states), tripinfo, backend)


def tripinfo_ids(path: Path) -> list[str]:
    """Vehicle IDs in file order -- `read_trips` keeps that order, so tests can
    name the records it returns."""
    return [element.attrib["id"] for element in ET.parse(path).getroot().iter("tripinfo")]
