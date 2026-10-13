"""Webster fixed-time (T1.10 A2): the formula, the plan for a configured demand, its execution.

The textbook check is a published worked example: *Fundamentals of
Transportation*, Wikibooks, "Traffic Signals", Example 3 ("Cycle Length
Calculation", Oak Street and Washington Avenue): two critical approaches with
v/s = 0.3 each and 15 s of lost time give an optimal cycle of 68.75 s. The
formula is Webster's (1958), *Traffic Signal Settings*, Road Research Technical
Paper No. 39.

The plan tests recompute the expected flow ratios by hand from
`configs/saturation_flow.json`, read here with `json` rather than through
`traffic_lab.scenarios.saturation`, so the plan is checked against the stored
calibration rather than against the code that reads it.
"""

from __future__ import annotations

import json
import logging
import math
import re

import pytest

from tests.backend.conftest import Scenario
from tests.control.support import (
    CAR_SATURATION,
    SPLIT,
    approach_sources,
    demand_on,
    drive,
    green_runs,
)
from traffic_lab.control.webster import (
    WebsterController,
    WebsterUndefinedError,
    webster_plan,
    webster_timing,
)
from traffic_lab.domain.demand import AttritionSpec, SourceSpec
from traffic_lab.domain.network import EdgeId, PhaseId, VehicleType
from traffic_lab.scenarios.demand import source_rate_veh_per_s
from traffic_lab.scenarios.saturation import SATURATION_FLOW_TABLE

#: Approaches 0 and 2 loaded twice as heavily as 1 and 3: unequal splits, unclamped mostly.
UNBALANCED = (0.3, 0.15, 0.3, 0.15)


def _stored_saturation_vph() -> dict[str, float]:
    raw = json.loads(SATURATION_FLOW_TABLE.read_text())["calibrations"]
    return {c["turn"]: c["mean_vph_per_lane"] for c in raw if c["speed_limit_mps"] == 13.89}


# --- The formula ----------------------------------------------------------------------


def test_cycle_matches_the_published_worked_example() -> None:
    """Wikibooks, Fundamentals of Transportation, Traffic Signals, Example 3:
    L = 15 s, two critical v/s of 0.3: C_opt = (1.5 x 15 + 5) / (1 - 0.6) = 68.75 s."""
    timing = webster_timing([0.3, 0.3], [7.5, 7.5])
    assert timing.cycle_s == pytest.approx(68.75, abs=1e-12)
    # Equal ratios share the effective green, C0 - L = 53.75 s, equally.
    assert timing.effective_greens_s == pytest.approx((26.875, 26.875), abs=1e-12)


def test_unequal_ratios_split_the_effective_green_in_proportion() -> None:
    """By hand: y = 0.18, 0.32, 0.22, 2 s lost per phase: L = 6, Y = 0.72,
    C0 = (9 + 5) / 0.28 = 50 s, and the 44 s of effective green go 11 : 19.56 : 13.44."""
    timing = webster_timing([0.18, 0.32, 0.22], [2.0, 2.0, 2.0])
    assert timing.cycle_s == pytest.approx(50.0, abs=1e-9)
    assert timing.effective_greens_s == pytest.approx((11.0, 44 * 0.32 / 0.72, 44 * 0.22 / 0.72))
    assert math.fsum(timing.effective_greens_s) == pytest.approx(50.0 - 6.0)


@pytest.mark.parametrize("ratios", [[0.5, 0.5], [0.6, 0.45], [0.0, 1.0]])
def test_y_of_one_or_more_raises(ratios: list[float]) -> None:
    with pytest.raises(WebsterUndefinedError, match="Y = "):
        webster_timing(ratios, [5.0] * len(ratios))


def test_y_just_below_one_is_still_defined() -> None:
    timing = webster_timing([0.5, 0.49], [5.0, 5.0])
    assert timing.cycle_s == pytest.approx((1.5 * 10 + 5) / 0.01)


def test_no_demand_raises() -> None:
    with pytest.raises(WebsterUndefinedError, match="Y = 0"):
        webster_timing([0.0, 0.0], [5.0, 5.0])


# --- The plan for a configured demand ---------------------------------------------------


def test_plan_flow_ratios_come_from_the_configured_demand_and_calibration(
    scenario: Scenario,
) -> None:
    built = scenario.built
    demand = demand_on(built.network, sources=approach_sources(built, UNBALANCED), split=SPLIT)
    plan = webster_plan(built.network, demand, CAR_SATURATION, step_length_s=1.0)

    sat = _stored_saturation_vph()
    s_t, s_l, s_r = sat["through"], sat["left"], sat["right"]

    def axis(level: float) -> tuple[float, float]:
        # Approach rate = level x 2 lanes x s_through. Through runs on both lanes, right
        # and left on one each (netconvert's default assignment on two lanes).
        rate = level * 2 * s_t
        through = SPLIT["through"] * rate / (2 * s_t)
        right = SPLIT["right"] * rate / s_r
        left = SPLIT["left"] * rate / s_l
        return max(through, right), left

    y0, y1 = axis(UNBALANCED[0])
    y2, y3 = axis(UNBALANCED[1])
    expected_y = (y0, y1, y2, y3)
    assert plan.flow_ratios == pytest.approx(expected_y, rel=1e-12)
    # The right turn, not the through, is critical on these approaches: its single
    # lane at 1366 veh/h is the scarcer capacity. Worth pinning -- a plan that read
    # the through ratio would under-serve every right turn.
    assert y0 > SPLIT["through"] * UNBALANCED[0]

    total_y = sum(expected_y)
    lost_s = 4 * (3.0 + 2.0)
    cycle_s = (1.5 * lost_s + 5) / (1 - total_y)
    assert plan.total_flow_ratio == pytest.approx(total_y, rel=1e-12)
    assert plan.lost_time_s == lost_s
    assert plan.optimum_cycle_s == pytest.approx(cycle_s, rel=1e-12)
    assert plan.effective_greens_s == pytest.approx(
        tuple((cycle_s - lost_s) * y / total_y for y in expected_y), rel=1e-12
    )
    # 19.53, 9.71, 9.76, 4.85 s -> rounded 20, 10, 10, 5 -> phase 3 clamped up to 10.
    assert plan.greens_s == (20.0, 10.0, 10.0, 10.0)
    assert [(int(c.phase), c.computed_s, c.applied_s, c.bound) for c in plan.clamps] == [
        (3, 5.0, 10.0, "min_green_s")
    ]
    assert plan.cycle_s == 50.0 + lost_s


def test_source_rate_agrees_with_the_demand_generator(scenario: Scenario) -> None:
    """Webster and `build_routes` must load the same intersection with the same rate."""
    built = scenario.built
    demand = demand_on(built.network, sources=approach_sources(built, UNBALANCED), split=SPLIT)
    plan = webster_plan(built.network, demand, CAR_SATURATION, step_length_s=1.0)
    movements = {m.id: m for m in built.movements}
    for source in demand.sources:
        generated_vph = 3600.0 * source_rate_veh_per_s(built.network, source)
        planned_vph = sum(
            flow
            for m, flow in plan.movement_flows_vph.items()
            if movements[m].from_edge == source.edge
        )
        assert planned_vph == pytest.approx(generated_vph, rel=1e-12)


def test_every_clamp_is_reported_and_logged(
    scenario: Scenario, caplog: pytest.LogCaptureFixture
) -> None:
    """Light demand: every green falls below the 10 s minimum. Heavy: the 60 s maximum."""
    built = scenario.built
    light = demand_on(built.network, sources=approach_sources(built, (0.05,) * 4), split=SPLIT)
    with caplog.at_level(logging.WARNING, logger="traffic_lab.control.webster"):
        plan = webster_plan(built.network, light, CAR_SATURATION, step_length_s=1.0)
    assert plan.greens_s == (10.0,) * 4
    assert [c.bound for c in plan.clamps] == ["min_green_s"] * 4
    assert all(c.computed_s < 10.0 for c in plan.clamps)
    logged = [r.getMessage() for r in caplog.records]
    assert len(logged) == 4
    assert all(re.search(r"clamped from .* to min_green_s = 10\.000 s", m) for m in logged)

    heavy = demand_on(
        built.network, sources=approach_sources(built, (0.6, 0.3, 0.6, 0.3)), split=SPLIT
    )
    plan = webster_plan(built.network, heavy, CAR_SATURATION, step_length_s=1.0)
    assert plan.total_flow_ratio < 1.0
    (clamp, *_) = plan.clamps
    assert (int(clamp.phase), clamp.bound, clamp.applied_s) == (0, "max_green_s", 60.0)
    assert clamp.computed_s > 60.0
    assert plan.greens_s[0] == 60.0


def test_overloaded_demand_raises(scenario: Scenario) -> None:
    built = scenario.built
    demand = demand_on(built.network, sources=approach_sources(built, (0.9,) * 4), split=SPLIT)
    with pytest.raises(WebsterUndefinedError, match=r"Y = .* >= 1"):
        webster_plan(built.network, demand, CAR_SATURATION, step_length_s=1.0)


def test_greens_round_half_up_to_the_step_length(scenario: Scenario) -> None:
    built = scenario.built
    demand = demand_on(built.network, sources=approach_sources(built, UNBALANCED), split=SPLIT)
    plan = webster_plan(built.network, demand, CAR_SATURATION, step_length_s=0.5)
    # 19.53 -> 19.5; 9.71 -> 9.5, 9.76 -> 10.0, then the 10 s minimum.
    assert plan.greens_s == (19.5, 10.0, 10.0, 10.0)
    assert {int(c.phase) for c in plan.clamps} == {1, 3}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("attrition", "no attrition term"),
        ("off_approach", "does not approach"),
        ("motorcycles", "cars only"),
    ],
)
def test_demand_outside_the_method_is_refused(
    scenario: Scenario, change: str, message: str
) -> None:
    built = scenario.built
    demand = demand_on(built.network, sources=approach_sources(built, UNBALANCED), split=SPLIT)
    approach = demand.sources[0].edge
    exit_edge = EdgeId(built.ids.edges.index("approach_0_out"))
    if change == "attrition":
        demand = type(demand)(
            demand.sources, demand.turn_ratios, (AttritionSpec(approach, 0.1),), demand.sink_edges
        )
    elif change == "off_approach":
        extra = SourceSpec(exit_edge, None, 0.1, {VehicleType.CAR: 1.0})
        demand = type(demand)(
            (*demand.sources, extra), demand.turn_ratios, demand.attrition, demand.sink_edges
        )
    else:
        mixed = SourceSpec(approach, None, 0.1, {VehicleType.CAR: 0.8, VehicleType.MOTORCYCLE: 0.2})
        demand = type(demand)(
            (mixed, *demand.sources[1:]), demand.turn_ratios, demand.attrition, demand.sink_edges
        )
    with pytest.raises(ValueError, match=message):
        webster_plan(built.network, demand, CAR_SATURATION, step_length_s=1.0)


def test_attrition_off_the_approaches_is_allowed(scenario: Scenario) -> None:
    """Attrition on an exit edge happens after the stop line; the flow is unchanged."""
    built = scenario.built
    demand = demand_on(built.network, sources=approach_sources(built, UNBALANCED), split=SPLIT)
    exit_edge = EdgeId(built.ids.edges.index("approach_0_out"))
    with_exit_attrition = type(demand)(
        demand.sources, demand.turn_ratios, (AttritionSpec(exit_edge, 0.3),), demand.sink_edges
    )
    plain = webster_plan(built.network, demand, CAR_SATURATION, step_length_s=1.0)
    other = webster_plan(built.network, with_exit_attrition, CAR_SATURATION, step_length_s=1.0)
    assert plain == other


# --- Execution: the scheduled sequence, exactly ------------------------------------------


def test_fixed_time_runs_exactly_its_schedule_over_many_cycles(scenario: Scenario) -> None:
    """Through the real constraint layer, step by step: every green the planned length, in
    authored order, and every clearance yellow + all-red, for 60 cycles."""
    built = scenario.built
    demand = demand_on(built.network, sources=approach_sources(built, UNBALANCED), split=SPLIT)
    controller = WebsterController(built.network, demand, CAR_SATURATION, step_length_s=1.0)
    plan = controller.plan
    cycles = 60
    ticks = drive(built.network, controller, end_s=cycles * plan.cycle_s + 1.0)
    runs = green_runs(ticks)
    assert len(runs) == cycles * len(plan.phases)
    expected_start_s = 0.0
    for k, (phase, start_s, length_s) in enumerate(runs):
        index = k % len(plan.phases)
        assert phase == int(plan.phases[index])
        assert start_s == expected_start_s
        assert length_s == plan.greens_s[index]
        expected_start_s = start_s + length_s + plan.lost_times_s[index]
    outcomes = {t.result.outcome.value for t in ticks if t.result is not None}
    assert outcomes == {"held", "granted"}


def test_a_green_the_decision_interval_cannot_reach_exactly_is_refused(
    scenario: Scenario,
) -> None:
    built = scenario.built
    demand = demand_on(built.network, sources=approach_sources(built, UNBALANCED), split=SPLIT)
    with pytest.raises(ValueError, match="not a multiple of decision_interval_s"):
        WebsterController(
            built.network, demand, CAR_SATURATION, step_length_s=0.5, decision_interval_s=1.0
        )


def test_the_controller_only_requests_authored_phases(scenario: Scenario) -> None:
    built = scenario.built
    demand = demand_on(built.network, sources=approach_sources(built, UNBALANCED), split=SPLIT)
    controller = WebsterController(built.network, demand, CAR_SATURATION, step_length_s=1.0)
    ticks = drive(built.network, controller, end_s=600.0)
    assert {t.signal.active_phase for t in ticks} == {PhaseId(k) for k in range(4)}
    assert all(t.result is None or t.result.outcome.value != "rejected" for t in ticks)
