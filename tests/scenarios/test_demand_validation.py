"""SS8 invariants 15-16 and the rest of `validate_demand`: load-time errors naming the edge.

Each test breaks one thing in an otherwise buildable spec, and checks the error
names the SUMO edge, so a misconfigured experiment fails before SUMO starts.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from tests.generated_scenario import Built
from tests.scenarios.demand_support import CARS, SPLIT, L, R, S, center, edge, four_source_spec
from traffic_lab.domain.demand import AttritionSpec, DemandSpec, SourceSpec, TurnRatioSpec
from traffic_lab.domain.network import EdgeId, TurnDirection, VehicleType
from traffic_lab.scenarios.demand import (
    DemandOrderError,
    DemandValidationError,
    build_routes,
    check_departure_order,
    count_max_edges_hits,
    validate_demand,
)


def _replace_ratio(spec: DemandSpec, index: int, ratios: dict[TurnDirection, float]) -> DemandSpec:
    turn_ratios = list(spec.turn_ratios)
    turn_ratios[index] = dataclasses.replace(turn_ratios[index], ratios=ratios)
    return dataclasses.replace(spec, turn_ratios=tuple(turn_ratios))


def test_a_buildable_spec_validates(four_way: Built) -> None:
    validate_demand(four_way.network, four_way.ids, four_source_spec(four_way, 0.1))


@pytest.mark.parametrize(
    "ratios",
    [
        {S: 0.6, R: 0.25, L: 0.25},  # sums to 1.1
        {S: 0.6, R: 0.25},  # sums to 0.85
        {S: 1.2, R: -0.2},  # sums to 1, but a negative probability
    ],
)
def test_invariant_15_turn_ratios_sum_to_one(
    four_way: Built, ratios: dict[TurnDirection, float]
) -> None:
    spec = _replace_ratio(four_source_spec(four_way, 0.1), 0, ratios)
    with pytest.raises(DemandValidationError, match="approach_0_in") as error:
        validate_demand(four_way.network, four_way.ids, spec)
    assert error.value.invariant == 15


def test_invariant_15_tolerance_admits_rounding(four_way: Built) -> None:
    spec = _replace_ratio(
        four_source_spec(four_way, 0.1), 0, {S: 0.3333333, R: 0.3333333, L: 0.3333334}
    )
    validate_demand(four_way.network, four_way.ids, spec)


@pytest.mark.parametrize("rate", [1.0, 1.5, -0.1])
def test_invariant_16_attrition_rates_lie_in_zero_one(four_way: Built, rate: float) -> None:
    spec = four_source_spec(four_way, 0.1, attrition={"approach_2_out": rate})
    with pytest.raises(DemandValidationError, match="approach_2_out") as error:
        validate_demand(four_way.network, four_way.ids, spec)
    assert error.value.invariant == 16


def test_zero_attrition_is_allowed(four_way: Built) -> None:
    spec = four_source_spec(four_way, 0.1, attrition={"approach_2_out": 0.0})
    validate_demand(four_way.network, four_way.ids, spec)


def test_validation_fails_before_anything_is_written(four_way: Built, tmp_path: Path) -> None:
    spec = four_source_spec(four_way, 0.1, attrition={"approach_2_out": 1.0})
    with pytest.raises(DemandValidationError):
        build_routes(
            four_way.net, four_way.network, four_way.ids, spec, 1, tmp_path / "out", end_s=3600.0
        )
    assert not (tmp_path / "out").exists()


def test_a_turn_with_no_movement_is_rejected(four_way: Built) -> None:
    spec = _replace_ratio(four_source_spec(four_way, 0.1), 0, {S: 0.5, TurnDirection.U_TURN: 0.5})
    with pytest.raises(DemandValidationError, match="u_turn"):
        validate_demand(four_way.network, four_way.ids, spec)


def test_turn_ratios_at_the_wrong_junction_are_rejected(four_way: Built) -> None:
    approach = edge(four_way, "approach_0_in")
    wrong = next(j for j in four_way.network.junctions if j.id != center(four_way)).id
    spec = dataclasses.replace(
        four_source_spec(four_way, 0.1),
        turn_ratios=(TurnRatioSpec(wrong, approach, dict(SPLIT)),),
    )
    with pytest.raises(DemandValidationError, match="does not enter"):
        validate_demand(four_way.network, four_way.ids, spec)


def test_an_approach_without_turn_ratios_is_rejected(four_way: Built) -> None:
    """jtrrouter would otherwise route it by its built-in default ratios, silently."""
    spec = four_source_spec(four_way, 0.1)
    spec = dataclasses.replace(spec, turn_ratios=spec.turn_ratios[1:])
    with pytest.raises(DemandValidationError, match=r"approach_0_in.*no turn ratios"):
        validate_demand(four_way.network, four_way.ids, spec)


def test_an_exit_that_is_not_a_sink_is_rejected(four_way: Built) -> None:
    spec = four_source_spec(four_way, 0.1)
    spec = dataclasses.replace(
        spec, sink_edges=spec.sink_edges - {edge(four_way, "approach_2_out")}
    )
    with pytest.raises(DemandValidationError, match="approach_2_out"):
        validate_demand(four_way.network, four_way.ids, spec)


def test_an_unreached_exit_need_not_be_a_sink(four_way: Built) -> None:
    """Only edges routes can reach matter: no traffic turns into approach_2_out."""
    spec = four_source_spec(four_way, 0.1)
    no_entry = {
        "approach_0_in": {R: 0.5, L: 0.5},  # through goes to approach_2_out
        "approach_1_in": {S: 0.5, R: 0.5},  # left goes to approach_2_out
        "approach_3_in": {S: 0.5, L: 0.5},  # right goes to approach_2_out
    }
    turn_ratios = tuple(
        dataclasses.replace(t, ratios=no_entry.get(four_way.ids.edges[t.from_edge], t.ratios))
        for t in spec.turn_ratios
    )
    spec = dataclasses.replace(
        spec,
        turn_ratios=turn_ratios,
        sink_edges=spec.sink_edges - {edge(four_way, "approach_2_out")},
    )
    validate_demand(four_way.network, four_way.ids, spec)


@pytest.mark.parametrize("fraction", [0.0, -0.1, float("nan")])
def test_a_source_rate_must_be_positive(four_way: Built, fraction: float) -> None:
    spec = four_source_spec(four_way, 0.1)
    sources = (dataclasses.replace(spec.sources[0], rate_saturation_fraction=fraction),)
    with pytest.raises(DemandValidationError, match="approach_0_in"):
        validate_demand(four_way.network, four_way.ids, dataclasses.replace(spec, sources=sources))


@pytest.mark.parametrize("position_m", [-1.0, 189.6, 500.0])
def test_a_mid_link_source_lies_on_its_edge(four_way: Built, position_m: float) -> None:
    spec = four_source_spec(four_way, 0.1, positions={"approach_1_in": position_m})
    with pytest.raises(DemandValidationError, match="approach_1_in"):
        validate_demand(four_way.network, four_way.ids, spec)


@pytest.mark.parametrize(
    "mix",
    [{VehicleType.CAR: 0.9}, {VehicleType.CAR: 1.1, VehicleType.MOTORCYCLE: -0.1}, {}],
)
def test_a_type_mix_is_a_distribution(four_way: Built, mix: dict[VehicleType, float]) -> None:
    spec = four_source_spec(four_way, 0.1)
    sources = (dataclasses.replace(spec.sources[0], type_mix=mix),)
    with pytest.raises(DemandValidationError, match="type mix"):
        validate_demand(four_way.network, four_way.ids, dataclasses.replace(spec, sources=sources))


def test_motorcycles_are_refused_until_their_saturation_flow_is_calibrated(
    four_way: Built,
) -> None:
    """The type-mix parameter exists (D-022); a non-car share has no D-037 saturation flow."""
    spec = four_source_spec(four_way, 0.1)
    mix = {VehicleType.CAR: 0.8, VehicleType.MOTORCYCLE: 0.2}
    sources = (dataclasses.replace(spec.sources[0], type_mix=mix),)
    with pytest.raises(DemandValidationError, match="motorcycle"):
        validate_demand(four_way.network, four_way.ids, dataclasses.replace(spec, sources=sources))
    zero_share = {VehicleType.CAR: 1.0, VehicleType.MOTORCYCLE: 0.0}
    sources = (dataclasses.replace(spec.sources[0], type_mix=zero_share),)
    validate_demand(four_way.network, four_way.ids, dataclasses.replace(spec, sources=sources))


def test_unknown_and_internal_edges_are_rejected(four_way: Built) -> None:
    spec = four_source_spec(four_way, 0.1)
    internal = EdgeId(next(i for i, e in enumerate(four_way.ids.edges) if e.startswith(":")))
    for bad in (EdgeId(len(four_way.ids.edges)), internal):
        bad_spec = dataclasses.replace(
            spec, sources=(SourceSpec(bad, None, 0.1, CARS), *spec.sources[1:])
        )
        with pytest.raises(DemandValidationError, match="source 0"):
            validate_demand(four_way.network, four_way.ids, bad_spec)


def test_duplicate_declarations_are_rejected(four_way: Built) -> None:
    spec = four_source_spec(four_way, 0.1, attrition={"approach_2_out": 0.1})
    twice = dataclasses.replace(
        spec, attrition=(*spec.attrition, AttritionSpec(spec.attrition[0].edge, 0.2))
    )
    with pytest.raises(DemandValidationError, match="twice"):
        validate_demand(four_way.network, four_way.ids, twice)
    twice = dataclasses.replace(spec, turn_ratios=(*spec.turn_ratios, spec.turn_ratios[0]))
    with pytest.raises(DemandValidationError, match="twice"):
        validate_demand(four_way.network, four_way.ids, twice)


def test_departure_order_is_enforced() -> None:
    check_departure_order([0.0, 1.5, 1.5, 2.0])
    with pytest.raises(DemandOrderError, match="silently drop"):
        check_departure_order([0.0, 2.0, 1.9])


def test_max_edges_hits_are_counted_from_jtrrouter_output() -> None:
    """The message jtrrouter prints, measured with --max-edges-factor 0.05 on the generated
    four-way (every route cut after one edge), not taken from documentation."""
    output = (
        "Error: The route starting at edge 'approach_0_in' could not be closed.\n"
        "Error: The route starting at edge 'approach_1_in' could not be closed.\n"
        "Quitting (on error).\n"
    )
    assert count_max_edges_hits(output) == 2
    assert count_max_edges_hits("Success.\n") == 0
