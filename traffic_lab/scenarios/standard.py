"""Standard scenario generation for profiling and benchmarks (T1.13)."""

from __future__ import annotations

import json
from pathlib import Path

from traffic_lab.domain.network import Network, SignalTiming, TurnDirection, movements_of
from traffic_lab.scenarios.generator import IDS_SUFFIX, NET_STEM, build
from traffic_lab.scenarios.parse import SumoIds
from traffic_lab.scenarios.spec import IntersectionSpec, PhaseSpec

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

#: Default period between vehicles on each movement's flow: 38.0 s (65 % capacity).
DEMAND_PERIOD_S = 38.0


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


def one_flow_per_movement(
    network: Network, ids: SumoIds, path: Path, end_s: float, *, period_s: float = DEMAND_PERIOD_S
) -> Path:
    """One flow per movement, so every movement has vehicles on it."""
    (intersection,) = network.signalized_intersections
    movements = movements_of(network, intersection.junction)
    lines = ["<routes>"]
    for movement in movements:
        lines.append(
            f'    <flow id="m{int(movement.id)}" from="{ids.edges[movement.from_edge]}" '
            f'to="{ids.edges[movement.to_edge]}" begin="0" end="{end_s}" '
            f'period="{period_s}" departLane="best" departSpeed="max"/>'
        )
    lines.append("</routes>")
    path.write_text("\n".join(lines) + "\n")
    return path


def build_standard_scenario(
    out_dir: Path, end_s: float, *, period_s: float = DEMAND_PERIOD_S
) -> tuple[Path, Path, Network]:
    """Build the standard four-way intersection network and routes for `end_s` simulated seconds.

    Returns (net_file, routes_file, network).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    net_file, network = build(FOUR_WAY, out_dir)
    ids = load_ids(out_dir / f"{NET_STEM}{IDS_SUFFIX}")
    routes_file = one_flow_per_movement(
        network, ids, out_dir / "demand.rou.xml", end_s, period_s=period_s
    )
    return net_file, routes_file, network
