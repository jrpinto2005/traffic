"""`display_state()`: the constraint layer's stage and phase as SUMO's state string.

Checked against the network's own connections rather than against
`green_link_indices()` alone: a position is green exactly when its connection
belongs to a movement of the phase, found through the phase's signal groups.
"""

from __future__ import annotations

import pytest

from tests.backend.conftest import Scenario
from traffic_lab.backend import display_state
from traffic_lab.domain.network import IntersectionId, PhaseId
from traffic_lab.domain.state import SignalStage


def _phase_positions(scenario: Scenario, phase: PhaseId) -> set[int]:
    """Display positions of the phase's connections, via groups and movements."""
    intersection = scenario.built.intersection
    groups = {g.id: g for g in intersection.signal_groups}
    movements = {m.id: m for m in scenario.built.movements}
    (spec_phase,) = (p for p in intersection.phases if p.id == phase)
    connections = {
        c
        for g in spec_phase.green_groups
        for m in groups[g].movements
        for c in movements[m].connections
    }
    return {i for i, c in enumerate(intersection.controlled_connections) if c in connections}


def test_green_shows_G_on_exactly_the_phase_connections(scenario: Scenario) -> None:
    built = scenario.built
    for phase in built.intersection.phases:
        shown = display_state(scenario.network, built.intersection_id, SignalStage.GREEN, phase.id)
        assert len(shown) == len(built.intersection.controlled_connections)
        assert {i for i, ch in enumerate(shown) if ch == "G"} == _phase_positions(
            scenario, phase.id
        )
        assert set(shown) == {"G", "r"}, "only G and r: no permissive g at M1"


def test_yellow_shows_y_on_exactly_the_links_green_in_the_phase_being_left(
    scenario: Scenario,
) -> None:
    built = scenario.built
    for phase in built.intersection.phases:
        green = display_state(scenario.network, built.intersection_id, SignalStage.GREEN, phase.id)
        yellow = display_state(
            scenario.network, built.intersection_id, SignalStage.YELLOW, phase.id
        )
        assert yellow == green.replace("G", "y"), "no link stays green through a transition"


def test_all_red_is_every_link_red(scenario: Scenario) -> None:
    built = scenario.built
    shown = display_state(scenario.network, built.intersection_id, SignalStage.ALL_RED, None)
    assert shown == built.all_red


def test_a_stage_and_phase_that_do_not_go_together_raise(scenario: Scenario) -> None:
    i = scenario.built.intersection_id
    with pytest.raises(ValueError, match="ALL_RED shows no phase"):
        display_state(scenario.network, i, SignalStage.ALL_RED, PhaseId(0))
    for stage in (SignalStage.GREEN, SignalStage.YELLOW):
        with pytest.raises(ValueError, match="needs a phase"):
            display_state(scenario.network, i, stage, None)


def test_an_unknown_intersection_or_phase_raises(scenario: Scenario) -> None:
    with pytest.raises(KeyError):
        display_state(scenario.network, IntersectionId(7), SignalStage.ALL_RED, None)
    with pytest.raises(KeyError):
        display_state(
            scenario.network, scenario.built.intersection_id, SignalStage.GREEN, PhaseId(99)
        )
