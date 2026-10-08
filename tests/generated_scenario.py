"""The generated intersection every SUMO-driving test runs on, and its demand.

One place for what the scenario, backend and estimation tests share (T1.14
Amendment A1): the default four-approach spec with the textbook protected plan,
`build()`'s output read back with its ID mapping, and a demand of one flow per
movement. The hand-built M0 reference scenario is no longer a test fixture -- it
cannot be represented validly under `D-023` (T1.3's completion record) -- and
`spikes/M0_reference/` is used only by `tests/scenarios/test_parse.py`, to
document its defects.

Test support only. Demand generation is T1.5's; nothing here is a scenario the
experiments run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from traffic_lab.domain.network import (
    IntersectionId,
    Movement,
    Network,
    SignalizedIntersection,
    SignalTiming,
    TurnDirection,
    movements_of,
)
from traffic_lab.scenarios import IntersectionSpec, PhaseSpec, build
from traffic_lab.scenarios.generator import IDS_SUFFIX, NET_STEM
from traffic_lab.scenarios.parse import SumoIds

TIMING = SignalTiming(min_green_s=10.0, max_green_s=60.0, yellow_s=3.0, all_red_s=2.0)
S, L, R = TurnDirection.THROUGH, TurnDirection.LEFT, TurnDirection.RIGHT

#: The default four-way with the textbook protected plan: each axis's through and
#: right turns, then its left turns.
FOUR_WAY = IntersectionSpec(
    phases=[
        PhaseSpec(green=[(0, S), (0, R), (2, S), (2, R)]),
        PhaseSpec(green=[(0, L), (2, L)]),
        PhaseSpec(green=[(1, S), (1, R), (3, S), (3, R)]),
        PhaseSpec(green=[(1, L), (3, L)]),
    ],
    timing=TIMING,
)

#: Seconds between vehicles on each movement's flow in the shared fixture:
#: 94.7 veh/h per movement, 1137 veh/h in all -- about 65 % of the static
#: program's capacity, so runs on it are valid under D-008's insertion-loss
#: threshold. Capacity measured, not assumed: with every movement oversupplied
#: (`OVERLOAD_PERIOD_S`) the static program discharged 144-150 veh/h per movement,
#: 1762 veh/h in all, over [600, 3600) s (seed 42, SUMO 1.27.1). At this period
#: the pending-insertion count is 0 on 97 % of steps after a 300 s warm-up and
#: never more than 4 for one step -- the instants all twelve flows emit at once.
DEMAND_PERIOD_S = 38.0

#: The period `tests/scenarios/test_runtime.py` first used: 6171 veh/h, about 3.5x
#: capacity. For tests that are about load, never for the shared fixture.
OVERLOAD_PERIOD_S = 7.0


@dataclass(frozen=True)
class Built:
    net: Path
    network: Network
    ids: SumoIds
    spec: IntersectionSpec

    @property
    def intersection(self) -> SignalizedIntersection:
        (intersection,) = self.network.signalized_intersections
        return intersection

    @property
    def intersection_id(self) -> IntersectionId:
        return self.intersection.id

    @property
    def movements(self) -> tuple[Movement, ...]:
        return movements_of(self.network, self.intersection.junction)

    @property
    def all_red(self) -> str:
        """The display with every controlled link red."""
        return "r" * len(self.intersection.controlled_connections)

    def static_phase_period_s(self) -> float:
        """Green start to the next green start in the static program."""
        timing = self.spec.timing
        return timing.min_green_s + timing.yellow_s + timing.all_red_s

    def static_cycle_s(self) -> float:
        return len(self.spec.phases) * self.static_phase_period_s()


def load_ids(path: Path) -> SumoIds:
    """Read the `<stem>.ids.json` mapping `build()` emits."""
    raw = json.loads(path.read_text())
    return SumoIds(
        lanes=tuple(raw["lanes"]),
        edges=tuple(raw["edges"]),
        junctions=tuple(raw["junctions"]),
        intersections=tuple(raw["intersections"]),
        connections=tuple((a, b) for a, b in raw["connections"]),
    )


def build_intersection(spec: IntersectionSpec, out_dir: Path) -> Built:
    net, network = build(spec, out_dir)
    return Built(net, network, load_ids(out_dir / f"{NET_STEM}{IDS_SUFFIX}"), spec)


def one_flow_per_movement(built: Built, path: Path, end_s: float, *, period_s: float) -> Path:
    """One flow per movement, so every movement has vehicles on it."""
    lines = ["<routes>"]
    for movement in built.movements:
        lines.append(
            f'    <flow id="m{int(movement.id)}" from="{built.ids.edges[movement.from_edge]}" '
            f'to="{built.ids.edges[movement.to_edge]}" begin="0" end="{end_s}" '
            f'period="{period_s}" departLane="best" departSpeed="max"/>'
        )
    lines.append("</routes>")
    path.write_text("\n".join(lines) + "\n")
    return path


def free_flow_population(built: Built, period_s: float) -> float:
    """Vehicles the network holds when nothing waits (Little's law): the arrival
    rate of `one_flow_per_movement` times the free-flow time across one approach
    in and one out. A liveness bound derived from the scenario: a run below it
    never filled the network even to its uncongested level."""
    arrival_rate_per_s = len(built.movements) / period_s
    crossing_s = 2 * built.spec.approach_length_m / built.spec.speed_limit_mps
    return arrival_rate_per_s * crossing_s
