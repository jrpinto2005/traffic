"""The constraint layer drives SUMO, and `TrueState` reads back what it shows (T1.14).

The acceptance test of D-034. A `ConstraintLayer` decides what the signal must
show; `display_state()` turns that into SUMO's string; `SumoBackend.apply()`
sends it; `project()` decodes what SUMO then displays. The loop is composed here
by hand, in `06_ARCHITECTURE.md` SS6.2's order -- step, project, `layer.step()`,
decide every Δt, then apply the display -- because T1.11's runner does not exist
yet, and neither package may read the other (Non-goal 3).

**Timing.** A display applied after the projection at `t` is the one SUMO shows
during the step to `t + Δ`, and so the one `project()` reads at `t + Δ`. The
layer's view to compare it with is therefore the one taken when the display was
applied: the layer at `t`, after its step and its decision.
"""

from __future__ import annotations

import pytest

from tests.backend.conftest import Scenario, make_config
from traffic_lab.backend import SumoBackend, display_state
from traffic_lab.control.constraint_layer import ConstraintLayer, ConstraintLayerConfig
from traffic_lab.domain.action import PhaseRequest, RequestOutcome
from traffic_lab.domain.network import PhaseId
from traffic_lab.domain.state import SignalStage, SignalState

#: The hand-written policy below: the first two phases are asked to end after
#: this much green; the last two are never asked, so max green forces them off.
_REQUESTED_GREEN_S = 15.0

#: Full cycles to run, each serving every authored phase once.
_CYCLES = 6


def _policy(
    layer: ConstraintLayer, scenario: Scenario, now_s: float, phases: list[PhaseId]
) -> PhaseRequest | None:
    """Ask for the next phase once the current one has had `_REQUESTED_GREEN_S` of
    green -- but only for the first half of the phases. The second half are held
    until the layer's max-green override forces them off."""
    i = scenario.built.intersection_id
    own = layer.signal_state(i)
    if own.in_transition or own.green_started_s is None:
        return None
    position = phases.index(own.active_phase)
    if position >= len(phases) // 2:
        return None
    if now_s - own.green_started_s < _REQUESTED_GREEN_S:
        return None
    return PhaseRequest(i, phases[(position + 1) % len(phases)])


@pytest.mark.parametrize("transport", ["traci", "libsumo"])
def test_truth_and_the_constraint_layer_agree_outside_transitions(
    scenario: Scenario, transport: str
) -> None:
    built, network = scenario.built, scenario.network
    i = built.intersection_id
    phases = [phase.id for phase in built.intersection.phases]
    timing = built.spec.timing
    decision_interval_s = 5.0
    forced_cycle_s = (len(phases) // 2) * (timing.max_green_s + timing.yellow_s + timing.all_red_s)
    requested_cycle_s = (len(phases) - len(phases) // 2) * (
        _REQUESTED_GREEN_S + decision_interval_s + timing.yellow_s + timing.all_red_s
    )
    steps = int(_CYCLES * (forced_cycle_s + requested_cycle_s))

    layer = ConstraintLayer(
        network,
        ConstraintLayerConfig(decision_interval_s=decision_interval_s, step_length_s=1.0),
        start_s=0.0,
    )
    backend = SumoBackend()
    backend.start(
        scenario.net,
        scenario.routes,
        make_config(transport=transport, decision_interval_s=decision_interval_s),
        network=network,
    )

    def apply_display() -> tuple[SignalState, PhaseId | None]:
        """Send what the layer says to show; return the layer's view and, during a
        transition, the phase being left."""
        stage, phase = layer.display(i)
        backend.apply(i, display_state(network, i, stage, phase))
        return layer.signal_state(i), phase if stage is SignalStage.YELLOW else None

    agreed = in_transition = 0
    green_sequence: list[PhaseId] = []
    leaving: PhaseId | None = None
    try:
        committed, yellow_of = apply_display()
        leaving = yellow_of if yellow_of is not None else leaving
        next_decision_s = decision_interval_s
        for _ in range(steps):
            backend.step()
            truth = backend.project()
            (shown,) = truth.signals

            if not committed.in_transition:
                assert shown == committed, f"t={truth.time_s}"
                agreed += 1
                if not green_sequence or green_sequence[-1] != shown.active_phase:
                    green_sequence.append(shown.active_phase)
            else:
                assert shown.in_transition, f"t={truth.time_s}"
                assert shown.green_started_s is None
                assert shown.active_phase == leaving, f"t={truth.time_s}"
                # D-034: the transition's start, in both views.
                assert shown.phase_started_s == committed.phase_started_s
                in_transition += 1

            layer.step(truth.time_s)
            if truth.time_s >= next_decision_s:
                request = _policy(layer, scenario, truth.time_s, phases)
                if request is not None:
                    result = layer.submit(request, truth.time_s)
                    assert result.outcome in (RequestOutcome.GRANTED, RequestOutcome.DEFERRED)
                next_decision_s += decision_interval_s
            committed, yellow_of = apply_display()
            leaving = yellow_of if yellow_of is not None else leaving
    finally:
        backend.close()

    # It really ran: both kinds of phase change, every phase in authored order,
    # at least five full cycles, and both views exercised.
    assert layer.counters.forced >= 5 * (len(phases) // 2)
    assert layer.counters.granted >= 5 * (len(phases) - len(phases) // 2)
    full_cycles = (len(green_sequence) - 1) // len(phases)
    assert full_cycles >= 5
    assert green_sequence == [phases[k % len(phases)] for k in range(len(green_sequence))]
    assert agreed + in_transition == steps
    # Every change shown took exactly yellow then all-red, read step by step.
    clearance_steps = int(timing.yellow_s + timing.all_red_s)
    changes = len(green_sequence) - 1
    assert changes * clearance_steps <= in_transition <= (changes + 1) * clearance_steps
    assert layer.counters.rejected == 0
