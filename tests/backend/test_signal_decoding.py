"""`TrueState` signals are decoded from what SUMO displays (D-034, T1.14).

SUMO's program phase index is useless once a controller drives a light: it
switches to the `online` program, whose index is always 0. The projection
therefore decodes the displayed red/yellow/green string into canonical phases
through `SignalizedIntersection.controlled_connections`. These tests check the
decode against sources that do not go through it: the static program as written
in the net file, and displays applied by hand.
"""

from __future__ import annotations

import dataclasses
import itertools
import xml.etree.ElementTree as ET

import pytest

from tests.backend.conftest import Scenario, make_config
from traffic_lab.backend import BackendStartupError, SumoBackend
from traffic_lab.backend.projection import Projector
from traffic_lab.domain.network import PhaseId, VehicleType, green_link_indices
from traffic_lab.domain.state import SignalState


def _static_program(scenario: Scenario) -> list[tuple[float, str]]:
    """(duration_s, state) of every phase of the net's static program, read from
    the net file with `xml.etree` -- not from the generator or the decoder."""
    (tl_logic,) = ET.parse(scenario.net).getroot().iter("tlLogic")
    return [(float(p.get("duration", "")), p.get("state", "")) for p in tl_logic.iter("phase")]


def _expected_under_the_static_program(scenario: Scenario, steps: int) -> list[SignalState]:
    """What the decode must report, step by step, derived from the program alone.

    The generator writes the k-th authored phase's green as the program's
    green-yellow-all-red group k (`generator._program_states`), so a program
    position's phase follows from the position. The state read after the step to
    `t` is the one shown during `[t - 1, t)`.
    """
    program = _static_program(scenario)
    per_phase = len(program) // len(scenario.built.intersection.phases)
    # (start_s, program position) over enough cycles.
    starts: list[tuple[float, int]] = []
    clock_s = 0.0
    for position in itertools.cycle(range(len(program))):
        if clock_s > steps + 1:
            break
        starts.append((clock_s, position))
        clock_s += program[position][0]

    expected: list[SignalState] = []
    for t in range(1, steps + 1):
        shown_from = t - 1.0
        index = max(i for i, (start_s, _) in enumerate(starts) if start_s <= shown_from)
        position = starts[index][1]
        group_start_index = index - position % per_phase
        group_start_s = starts[group_start_index][0]
        group = position // per_phase
        if position % per_phase == 0:  # green
            # Became active when the previous group's yellow began; the first
            # phase at the start time.
            previous_yellow = group_start_index - per_phase + 1
            phase_started_s = 0.0 if group_start_index == 0 else starts[previous_yellow][0]
            expected.append(
                SignalState(
                    intersection=scenario.built.intersection_id,
                    active_phase=PhaseId(group),
                    phase_started_s=phase_started_s,
                    green_started_s=group_start_s,
                    in_transition=False,
                )
            )
        else:  # yellow or all-red, leaving `group`
            expected.append(
                SignalState(
                    intersection=scenario.built.intersection_id,
                    active_phase=PhaseId(group),
                    phase_started_s=starts[group_start_index + 1][0],
                    green_started_s=None,
                    in_transition=True,
                )
            )
    return expected


@pytest.mark.parametrize("transport", ["traci", "libsumo"])
def test_under_the_static_program_the_decode_shows_the_programs_phases(
    scenario: Scenario, transport: str
) -> None:
    """Before any `apply()`, decoding reports the phases the program shows: the
    decode does not depend on who drives the light."""
    steps = int(2.5 * scenario.built.static_cycle_s())
    expected = _expected_under_the_static_program(scenario, steps)
    backend = SumoBackend()
    backend.start(
        scenario.net,
        scenario.routes,
        make_config(transport=transport),
        network=scenario.network,
    )
    try:
        for t in range(steps):
            backend.step()
            assert backend.project().signals[0] == expected[t], f"t={t + 1}"
    finally:
        backend.close()
    # Every authored phase, green and in transition, was compared.
    assert {s.active_phase for s in expected} == {p.id for p in scenario.built.intersection.phases}
    assert any(s.in_transition for s in expected)


def _display(scenario: Scenario, greens: frozenset[int], char: str) -> str:
    size = len(scenario.built.intersection.controlled_connections)
    return "".join(char if link in greens else "r" for link in range(size))


def _greens(scenario: Scenario, phase: int) -> frozenset[int]:
    return green_link_indices(scenario.network, scenario.built.intersection_id, PhaseId(phase))


def test_a_controller_driven_light_decodes_through_a_transition(scenario: Scenario) -> None:
    """Under `apply()` SUMO's phase index is always 0; the decode still follows
    green, yellow, all-red, green -- naming the phase being left until the next
    green shows, and dating each instant to the step the display was applied."""
    built = scenario.built
    phase_0, phase_2 = _greens(scenario, 0), _greens(scenario, 2)
    plan = (
        [_display(scenario, phase_0, "G")] * 5
        + [_display(scenario, phase_0, "y")] * 3
        + [built.all_red] * 2
        + [_display(scenario, phase_2, "G")] * 4
        # Green straight to green: both instants move together.
        + [_display(scenario, phase_0, "g")] * 2
    )
    backend = SumoBackend()
    backend.start(scenario.net, scenario.routes, make_config(), network=scenario.network)
    try:
        seen = []
        for display in plan:
            backend.apply(built.intersection_id, display)
            backend.step()
            seen.append(backend.project().signals[0])
    finally:
        backend.close()

    def state(phase: int, started: float, green: float | None) -> SignalState:
        return SignalState(built.intersection_id, PhaseId(phase), started, green, green is None)

    assert seen == (
        [state(0, 0.0, 0.0)] * 5
        + [state(0, 5.0, None)] * 5  # yellow then all-red, applied from t=5
        + [state(2, 5.0, 10.0)] * 4  # green applied at t=10
        + [state(0, 14.0, 14.0)] * 2  # `g` counts as green
    )


def test_two_phases_green_at_once_raises_rather_than_guessing(scenario: Scenario) -> None:
    built = scenario.built
    both = _display(scenario, _greens(scenario, 0) | _greens(scenario, 2), "G")
    backend = SumoBackend()
    backend.start(scenario.net, scenario.routes, make_config(), network=scenario.network)
    try:
        backend.step()
        backend.project()
        backend.apply(built.intersection_id, both)
        backend.step()
        with pytest.raises(BackendStartupError, match="no phase's green link set"):
            backend.project()
    finally:
        backend.close()


def test_a_first_display_with_no_green_raises(scenario: Scenario) -> None:
    """A transition is named by the phase being left; before any phase has been
    shown there is none to name, and the decode refuses to invent one."""
    backend = SumoBackend()
    backend.start(scenario.net, scenario.routes, make_config(), network=scenario.network)
    try:
        backend.apply(scenario.built.intersection_id, scenario.built.all_red)
        backend.step()
        with pytest.raises(BackendStartupError, match="no phase has been shown yet"):
            backend.project()
    finally:
        backend.close()


def _projector(green_links: dict[PhaseId, frozenset[int]]) -> Projector:
    return Projector(
        lane_sumo_ids=(),
        lane_lengths_m=(),
        intersection_sumo_ids=("tls",),
        phase_green_links=(green_links,),
        start_s=0.0,
        vehicle_types={"passenger": VehicleType.CAR},
        step_length_s=1.0,
        gridlock_steps=10,
        max_accel_mps2=2.6,
    )


def test_two_phases_with_the_same_green_links_are_refused_at_start() -> None:
    """D-034's revisit trigger: the display alone cannot tell them apart."""
    with pytest.raises(BackendStartupError, match="cannot tell them apart"):
        _projector({PhaseId(0): frozenset({0, 1}), PhaseId(1): frozenset({1, 0})})


def test_a_phase_with_no_green_link_is_refused_at_start() -> None:
    with pytest.raises(BackendStartupError, match="cannot be told from a transition"):
        _projector({PhaseId(0): frozenset({0}), PhaseId(1): frozenset()})


def test_a_network_that_does_not_describe_the_net_is_refused(scenario: Scenario) -> None:
    no_signals = dataclasses.replace(scenario.network, signalized_intersections=())
    with pytest.raises(BackendStartupError, match="does not describe this net"):
        SumoBackend().start(scenario.net, scenario.routes, make_config(), network=no_signals)
