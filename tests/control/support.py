"""Demand, saturation flow and a constraint-layer loop for the controller tests. Test support only.

`demand_on` builds a `DemandSpec` from JSON values -- `[edge id, level]` pairs and
a turn split keyed by turn name -- so a controller factory bound to those values
can be recorded in a run manifest and rebuilt in a `spawn` worker
(`traffic_lab.experiments.runner.controller_identity`), and the route file can
be generated from the very same spec.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from tests.generated_scenario import Built
from traffic_lab.control.constraint_layer import ConstraintLayer, ConstraintLayerConfig
from traffic_lab.control.controller import Controller
from traffic_lab.control.webster import WebsterController
from traffic_lab.domain.action import ActionResult
from traffic_lab.domain.demand import DemandSpec, SourceSpec, TurnRatioSpec
from traffic_lab.domain.network import EdgeId, Network, TurnDirection, VehicleType, movements_of
from traffic_lab.domain.observation import EstimatedState
from traffic_lab.domain.state import SignalState
from traffic_lab.scenarios.saturation import per_lane_saturation_flow_vph

#: The calibrated per-lane saturation flow for cars (D-037), as `control/` takes it.
CAR_SATURATION = functools.partial(per_lane_saturation_flow_vph, VehicleType.CAR)

#: T1.5's test split: deliberately unequal, so a swapped turn would show.
SPLIT = {"through": 0.6, "right": 0.25, "left": 0.15}


def demand_on(
    network: Network, *, sources: Sequence[Sequence[float]], split: Mapping[str, float]
) -> DemandSpec:
    """A car source on each listed `[edge id, level]`, `split` on every approach of the
    network's one signalized junction, every edge leaving it a sink."""
    (intersection,) = network.signalized_intersections
    junction = intersection.junction
    ratios = {TurnDirection(turn): float(p) for turn, p in split.items()}
    approaches = sorted(e.id for e in network.edges if e.to_junction == junction)
    return DemandSpec(
        sources=tuple(
            SourceSpec(EdgeId(int(edge)), None, float(level), {VehicleType.CAR: 1.0})
            for edge, level in sources
        ),
        turn_ratios=tuple(TurnRatioSpec(junction, edge, dict(ratios)) for edge in approaches),
        attrition=(),
        sink_edges=frozenset(e.id for e in network.edges if e.from_junction == junction),
    )


def approach_sources(built: Built, levels: Sequence[float]) -> list[list[float]]:
    """`[edge id, level]` for approach k at `levels[k]`, as `demand_on` takes them."""
    return [
        [float(built.ids.edges.index(f"approach_{k}_in")), level] for k, level in enumerate(levels)
    ]


def make_webster_controller(network: Network) -> WebsterController:
    """Top-level factory for WebsterController on the generated network (T1.10)."""
    (intersection,) = network.signalized_intersections
    approaches = sorted({m.from_edge for m in movements_of(network, intersection.junction)})
    sources = [[float(edge), 0.2] for edge in approaches]
    demand = demand_on(network, sources=sources, split=SPLIT)
    return WebsterController(network, demand, CAR_SATURATION)


@dataclass(frozen=True)
class Tick:
    """One simulated step of `drive`: the layer's view after it, and any decision made."""

    time_s: float
    signal: SignalState
    result: ActionResult | None


def drive(
    network: Network,
    controller: Controller,
    end_s: float,
    *,
    step_length_s: float = 1.0,
) -> list[Tick]:
    """`06_ARCHITECTURE.md` SS6.2's control half with no simulator: `step()` every step,
    `decide()` and `submit()` every Δt from Δt on, the estimate carrying only the
    layer's own signal state -- all a schedule reads."""
    (intersection,) = network.signalized_intersections
    layer = ConstraintLayer(
        network,
        ConstraintLayerConfig(
            decision_interval_s=controller.decision_interval_s, step_length_s=step_length_s
        ),
    )
    ticks: list[Tick] = []
    decisions = 1
    steps = round(end_s / step_length_s)
    for k in range(1, steps + 1):
        now_s = k * step_length_s
        layer.step(now_s)
        result = None
        if now_s + 1e-9 >= decisions * controller.decision_interval_s:
            est = EstimatedState(
                time_s=now_s, lanes=(), signals=(layer.signal_state(intersection.id),)
            )
            result = layer.submit(controller.decide(est, now_s), now_s)
            decisions += 1
        ticks.append(Tick(now_s, layer.signal_state(intersection.id), result))
    return ticks


def green_runs(ticks: Sequence[Tick]) -> list[tuple[int, float, float]]:
    """Each completed green interval as (phase, start s, length s), in order."""
    runs: list[tuple[int, float, float]] = []
    current: tuple[int, float] | None = None
    for tick in ticks:
        green = None if tick.signal.in_transition else int(tick.signal.active_phase)
        if current is not None and green != current[0]:
            runs.append((current[0], current[1], tick.time_s - current[1]))
            current = None
        if green is not None and current is None:
            assert tick.signal.green_started_s is not None
            current = (green, tick.signal.green_started_s)
    return runs
