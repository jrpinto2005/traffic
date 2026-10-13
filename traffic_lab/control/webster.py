"""Webster fixed-time: the plan computed for the demand being tested (D-013, T1.10 A2).

**Not an equal split.** `D-013` exists because a badly tuned fixed-time baseline
manufactures improvement for everything compared against it, so the cycle and
the splits are computed by Webster's method from the **configured** demand and
the saturation flow calibrated in SUMO (`D-037`) -- never from observed state.

**The method** (Webster, F. V. (1958). *Traffic Signal Settings*. Road Research
Technical Paper No. 39, HMSO, London):

* Flow of a movement, veh/h: its source's rate times its turn ratio. A source's
  rate is `rate_saturation_fraction x` its approach's saturation flow, which is
  the approach's lane count times the per-lane **through** saturation flow
  (`D-022`, `D-037`; the same rule as
  `traffic_lab.scenarios.demand.source_rate_veh_per_s`).
* Saturation flow of a movement, veh/h: the per-lane saturation flow **for its
  turn** at its lanes' speed limit, times the number of lanes serving it.
* Flow ratio of a movement: flow / saturation flow. A phase's critical flow ratio
  `y_i` is the largest ratio among its movements; `Y = sum y_i`.
* Lost time per phase is `yellow_s + all_red_s` -- the HCM default, in which a
  2 s start-up loss at the beginning of green and a 2 s yellow extension at its
  end (vehicles still crossing in the yellow) cancel, so the effective green
  equals the displayed green and each change costs exactly its clearance.
  `L` is the sum over phases.
* Optimum cycle `C0 = (1.5 L + 5) / (1 - Y)`, seconds; effective greens
  `g_i = (C0 - L) y_i / Y`.
* `Y >= 1` raises `WebsterUndefinedError`: the formula has no positive cycle there,
  the intersection cannot be signalised for that demand, and a sweep must not
  ask for it.

**Executing it.** Each green is rounded half-up to the step length and clamped
to `[min_green_s, max_green_s]` (`max_green_s == 0` disables the upper bound).
Every clamp is **reported** -- in `WebsterPlan.clamps` and as a log warning --
never silent: a clamped plan is no longer Webster's, and whoever reads a result
must be able to see by how much. `WebsterController` runs the plan through the
constraint layer at Δt = 1 s, requesting the next authored phase once the green
in progress has lasted its planned length; the layer inserts the clearances.

**What the method here does not cover, and refuses** (`ValueError`), rather than
guess at: a source on an edge that does not approach the intersection (its flow
would reach it through propagation A2 does not define), attrition declared on
an approach (A2's flow is the source rate times the turn ratio, with no
attrition term), and vehicle types other than cars (`D-037` calibrates cars only
at M1).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from traffic_lab.control.phases import next_phase_map, own_signal, phase_service, the_intersection
from traffic_lab.domain.action import PhaseRequest
from traffic_lab.domain.demand import DemandSpec
from traffic_lab.domain.network import (
    EdgeId,
    IntersectionId,
    MovementId,
    Network,
    PhaseId,
    SignalizedIntersection,
    TurnDirection,
    VehicleType,
    movements_of,
)
from traffic_lab.domain.observation import EstimatedState

logger = logging.getLogger(__name__)

#: Per-lane saturation flow, veh/h/lane, for a (speed limit in m/s, turn) -- the
#: calibration `D-037` stores. Production callers pass
#: `functools.partial(traffic_lab.scenarios.saturation.per_lane_saturation_flow_vph,
#: VehicleType.CAR)`; `control/` cannot import `scenarios/` (`06_ARCHITECTURE.md`
#: SS10), so the calibration arrives as this callable.
SaturationFlowLookup = Callable[[float, TurnDirection], float]

#: Webster's constants: `C0 = (WEBSTER_LOST_TIME_FACTOR L + WEBSTER_CONSTANT_S) / (1 - Y)`.
WEBSTER_LOST_TIME_FACTOR = 1.5
WEBSTER_CONSTANT_S = 5.0

#: Absorbs binary rounding when comparing simulated times; far below any step.
_TIME_EPS_S = 1e-9


class WebsterUndefinedError(ValueError):
    """`Y >= 1` (or `Y == 0`): Webster's cycle does not exist for this demand."""


@dataclass(frozen=True, slots=True)
class WebsterTiming:
    """Webster's formula alone: the optimum cycle and the effective greens, seconds."""

    cycle_s: float
    effective_greens_s: tuple[float, ...]


def webster_timing(
    critical_flow_ratios: Sequence[float], lost_times_s: Sequence[float]
) -> WebsterTiming:
    """`C0 = (1.5 L + 5) / (1 - Y)` and `g_i = (C0 - L) y_i / Y`, per phase, seconds.

    `critical_flow_ratios` are the phases' `y_i` and `lost_times_s` their lost
    times, in the same order. Raises `WebsterUndefinedError` if `Y >= 1` or
    `Y == 0` (no demand: the split `y_i / Y` is undefined), and `ValueError` for
    a negative ratio or lost time or mismatched lengths.
    """
    if len(critical_flow_ratios) != len(lost_times_s) or not critical_flow_ratios:
        raise ValueError(
            f"{len(critical_flow_ratios)} flow ratios for {len(lost_times_s)} lost times; "
            f"need one of each per phase"
        )
    if any(not y >= 0.0 for y in critical_flow_ratios) or any(not t >= 0.0 for t in lost_times_s):
        raise ValueError(
            f"flow ratios {list(critical_flow_ratios)} and lost times {list(lost_times_s)} "
            f"must be non-negative"
        )
    total_y = math.fsum(critical_flow_ratios)
    if total_y >= 1.0:
        raise WebsterUndefinedError(
            f"Y = {total_y:.4f} >= 1: the demand exceeds what any cycle can serve, and "
            f"Webster's cycle (1.5 L + 5) / (1 - Y) is undefined"
        )
    if total_y == 0.0:
        raise WebsterUndefinedError("Y = 0: no demand, so Webster's split y_i / Y is undefined")
    lost_s = math.fsum(lost_times_s)
    cycle_s = (WEBSTER_LOST_TIME_FACTOR * lost_s + WEBSTER_CONSTANT_S) / (1.0 - total_y)
    return WebsterTiming(
        cycle_s=cycle_s,
        effective_greens_s=tuple((cycle_s - lost_s) * y / total_y for y in critical_flow_ratios),
    )


@dataclass(frozen=True, slots=True)
class GreenClamp:
    """A planned green that the timing bounds moved: reported, never silent."""

    phase: PhaseId
    computed_s: float  # Webster's green, rounded to the step length
    applied_s: float  # what runs
    bound: Literal["min_green_s", "max_green_s"]


@dataclass(frozen=True, slots=True)
class WebsterPlan:
    """A Webster plan for one intersection, with every intermediate value kept.

    Per-phase tuples are in authored order (`phases`).
    """

    intersection: IntersectionId
    phases: tuple[PhaseId, ...]
    movement_flows_vph: dict[MovementId, float]
    movement_flow_ratios: dict[MovementId, float]
    flow_ratios: tuple[float, ...]  # y_i, the critical ratio of each phase
    total_flow_ratio: float  # Y
    lost_times_s: tuple[float, ...]  # yellow_s + all_red_s per phase
    optimum_cycle_s: float  # C0
    effective_greens_s: tuple[float, ...]  # Webster's g_i, unrounded
    greens_s: tuple[float, ...]  # rounded to the step and clamped: what runs
    clamps: tuple[GreenClamp, ...]

    @property
    def lost_time_s(self) -> float:
        """`L`, seconds per cycle."""
        return math.fsum(self.lost_times_s)

    @property
    def cycle_s(self) -> float:
        """The cycle that runs: executed greens plus clearances, seconds."""
        return math.fsum(self.greens_s) + self.lost_time_s


def movement_flows_vph(
    network: Network,
    intersection: SignalizedIntersection,
    demand: DemandSpec,
    saturation_flow_vph: SaturationFlowLookup,
) -> dict[MovementId, float]:
    """Configured flow of every movement of `intersection`, veh/h (module docstring).

    Raises `ValueError` for a demand A2's flow does not cover: a source off the
    intersection's approaches, attrition on an approach, a non-car share, or a
    source on an approach without turn ratios.
    """
    junction = intersection.junction
    movements = movements_of(network, junction)
    approaches = {m.from_edge for m in movements}
    for attrition in demand.attrition:
        if attrition.edge in approaches and attrition.rate > 0.0:
            raise ValueError(
                f"attrition {attrition.rate} on approach edge {int(attrition.edge)}: Webster's "
                f"movement flow (source rate x turn ratio, T1.10 A2) has no attrition term"
            )
    ratios = {
        spec.from_edge: spec.ratios for spec in demand.turn_ratios if spec.junction == junction
    }
    rate_vph: dict[EdgeId, float] = {}
    for k, source in enumerate(demand.sources):
        if source.edge not in approaches:
            raise ValueError(
                f"source {k} is on edge {int(source.edge)}, which does not approach "
                f"intersection {int(intersection.id)}; Webster's flow (T1.10 A2) covers sources "
                f"on its approaches only"
            )
        others = sorted(
            t.value for t, s in source.type_mix.items() if s > 0 and t != VehicleType.CAR
        )
        if others:
            raise ValueError(
                f"source {k} mixes in {', '.join(others)}: saturation flow is calibrated for "
                f"cars only at M1 (D-037)"
            )
        if source.edge not in ratios:
            raise ValueError(f"source {k}'s approach edge {int(source.edge)} has no turn ratios")
        approach_vph = _approach_saturation_flow_vph(network, source.edge, saturation_flow_vph)
        rate_vph[source.edge] = (
            rate_vph.get(source.edge, 0.0) + source.rate_saturation_fraction * approach_vph
        )
    return {
        m.id: rate_vph.get(m.from_edge, 0.0) * ratios.get(m.from_edge, {}).get(m.turn, 0.0)
        for m in movements
    }


def webster_plan(
    network: Network,
    demand: DemandSpec,
    saturation_flow_vph: SaturationFlowLookup,
    *,
    step_length_s: float,
) -> WebsterPlan:
    """Webster's plan for the network's one signalized intersection (module docstring)."""
    if not step_length_s > 0.0:
        raise ValueError(f"step_length_s must be positive, got {step_length_s}")
    intersection = the_intersection(network)
    timing = intersection.timing
    services = phase_service(network, intersection)
    flows = movement_flows_vph(network, intersection, demand, saturation_flow_vph)
    lanes = {lane.id: lane for lane in network.lanes}
    connections = {c.id: c for c in network.connections}

    movement_ratios: dict[MovementId, float] = {}
    for movement in movements_of(network, intersection.junction):
        serving = {connections[c].from_lane for c in movement.connections}
        speeds = {lanes[lane].speed_limit_mps for lane in serving}
        if len(speeds) != 1:
            raise ValueError(
                f"movement {int(movement.id)} leaves lanes with speed limits {sorted(speeds)}; "
                f"saturation flow is calibrated per speed limit (D-037)"
            )
        flow = flows[movement.id]
        if flow == 0.0:
            movement_ratios[movement.id] = 0.0
            continue
        (speed,) = speeds
        capacity_vph = saturation_flow_vph(speed, movement.turn) * len(serving)
        movement_ratios[movement.id] = flow / capacity_vph

    served = {m.id for service in services for m in service.movements}
    unserved = sorted(int(m) for m, f in flows.items() if f > 0.0 and m not in served)
    if unserved:
        raise ValueError(f"movements {unserved} carry demand but no authored phase serves them")

    flow_ratios = tuple(
        max((movement_ratios[m.id] for m in service.movements), default=0.0) for service in services
    )
    lost_times_s = tuple(timing.yellow_s + timing.all_red_s for _ in services)
    timing_result = webster_timing(flow_ratios, lost_times_s)

    greens: list[float] = []
    clamps: list[GreenClamp] = []
    for service, effective_s in zip(services, timing_result.effective_greens_s, strict=True):
        rounded_s = _round_half_up(effective_s, step_length_s)
        applied_s = rounded_s
        bound: Literal["min_green_s", "max_green_s"] | None = None
        if applied_s < timing.min_green_s:
            applied_s, bound = timing.min_green_s, "min_green_s"
        elif timing.max_green_s > 0.0 and applied_s > timing.max_green_s:
            applied_s, bound = timing.max_green_s, "max_green_s"
        if bound is not None:
            clamp = GreenClamp(service.phase, rounded_s, applied_s, bound)
            clamps.append(clamp)
            logger.warning(
                "Webster green of phase %d clamped from %.3f s to %s = %.3f s (T1.10 A2)",
                int(clamp.phase),
                clamp.computed_s,
                clamp.bound,
                clamp.applied_s,
            )
        greens.append(applied_s)

    return WebsterPlan(
        intersection=intersection.id,
        phases=tuple(service.phase for service in services),
        movement_flows_vph=flows,
        movement_flow_ratios=movement_ratios,
        flow_ratios=flow_ratios,
        total_flow_ratio=math.fsum(flow_ratios),
        lost_times_s=lost_times_s,
        optimum_cycle_s=timing_result.cycle_s,
        effective_greens_s=timing_result.effective_greens_s,
        greens_s=tuple(greens),
        clamps=tuple(clamps),
    )


class WebsterController:
    """Runs a `WebsterPlan` through the constraint layer (`Controller`, D-020).

    At every decision: during a transition, or before the green in progress has
    lasted its planned length, it requests the phase already in effect (HELD);
    from then on it requests the next authored phase. The plan's greens are at
    least `min_green_s`, so the request is granted at the decision where the
    planned length is reached -- exactly, when Δt divides the green -- and the
    constraint layer runs the yellow and all-red. Reads only its own signal
    state from `EstimatedState`: a schedule needs nothing else.
    """

    def __init__(
        self,
        network: Network,
        demand: DemandSpec,
        saturation_flow_vph: SaturationFlowLookup,
        *,
        step_length_s: float = 1.0,
        decision_interval_s: float = 1.0,
    ) -> None:
        self.decision_interval_s = decision_interval_s  # D-020; T1.10 A2: 1 s
        self.plan = webster_plan(network, demand, saturation_flow_vph, step_length_s=step_length_s)
        self._intersection = self.plan.intersection
        for phase, green_s in zip(self.plan.phases, self.plan.greens_s, strict=True):
            multiples = green_s / decision_interval_s
            if abs(multiples - round(multiples)) > 1e-6:
                # A green between two decisions would run to the next one: longer than
                # planned, silently. Refused instead (rounding to the step length, A2,
                # is exact only when the decision interval is the step length).
                raise ValueError(
                    f"phase {int(phase)}'s planned green {green_s} s is not a multiple of "
                    f"decision_interval_s = {decision_interval_s} s, so it cannot run exactly"
                )
        self._green_s = dict(zip(self.plan.phases, self.plan.greens_s, strict=True))
        self._next = next_phase_map(the_intersection(network))

    def decide(self, est: EstimatedState, now_s: float) -> PhaseRequest:
        own = own_signal(est, self._intersection)
        phase = own.active_phase
        if own.in_transition or own.green_started_s is None:
            return PhaseRequest(self._intersection, phase)
        if now_s - own.green_started_s + _TIME_EPS_S >= self._green_s[phase]:
            return PhaseRequest(self._intersection, self._next[phase])
        return PhaseRequest(self._intersection, phase)


def _approach_saturation_flow_vph(
    network: Network, edge: EdgeId, saturation_flow_vph: SaturationFlowLookup
) -> float:
    """Lane count x per-lane through saturation flow (D-037)."""
    the_edge = network.edges[edge]
    speeds = {network.lanes[lane].speed_limit_mps for lane in the_edge.lanes}
    if len(speeds) != 1:
        raise ValueError(
            f"edge {int(edge)} has lanes with speed limits {sorted(speeds)}; saturation flow "
            f"is calibrated per speed limit (D-037)"
        )
    (speed,) = speeds
    return len(the_edge.lanes) * saturation_flow_vph(speed, TurnDirection.THROUGH)


def _round_half_up(value_s: float, step_s: float) -> float:
    """`value_s` to the nearest multiple of `step_s`, halves up (not banker's rounding)."""
    return math.floor(value_s / step_s + 0.5) * step_s
