"""The two transports must produce byte-identical `TrueState` sequences.

**This is T1.4's most important test.** `D-031` was amended on 2026-08-18 to make
the *mechanism* of batching transport-specific -- subscriptions under TraCI,
direct getters under LibSUMO -- on the strength of a measurement
(`research/M0_performance.md`). That amendment is only safe because the two
implementations can be proven to behave identically, and this is the proof. If
it fails, one of the transports is wrong and `08_AGENT_HANDOFF_PROTOCOL.md` SS8
requires finding out which rather than reconciling them.

"Byte-identical" is asserted as structural equality of frozen dataclasses over
`float` fields, which in Python is exact equality -- no tolerance. That is the
right strength: TraCI serialises doubles over its socket without loss and
LibSUMO returns the same doubles in-process, so any difference at all would mean
the two are reading different things, not that one rounded.
"""

from __future__ import annotations

from tests.backend.conftest import Scenario, make_config
from traffic_lab.backend import SumoBackend
from traffic_lab.domain.state import TrueState

#: Full cycles of the static program to run: enough for queues on every red and
#: about a hundred arrivals, so the counters and the halting bookkeeping are all
#: exercised rather than just the empty-network case.
CYCLES = 5


def _steps(scenario: Scenario) -> int:
    return int(CYCLES * scenario.built.static_cycle_s())


def _run(transport: str, scenario: Scenario, steps: int) -> list[TrueState]:
    backend = SumoBackend()
    backend.start(
        scenario.net, scenario.routes, make_config(transport=transport), network=scenario.network
    )
    try:
        states = []
        for _ in range(steps):
            backend.step()
            states.append(backend.project())
        return states
    finally:
        backend.close()


def test_transports_produce_identical_true_state_sequences(scenario: Scenario) -> None:
    steps = _steps(scenario)
    over_traci = _run("traci", scenario, steps)
    over_libsumo = _run("libsumo", scenario, steps)

    assert len(over_traci) == len(over_libsumo) == steps
    for step, (traci_state, libsumo_state) in enumerate(zip(over_traci, over_libsumo, strict=True)):
        assert traci_state == libsumo_state, f"transports diverge at step {step}"


def test_the_sequence_is_not_trivially_empty(scenario: Scenario) -> None:
    """Guard against the equivalence test passing on two empty simulations.

    An equality assertion over two runs that both did nothing would pass and
    prove nothing, so the fixture's own liveness is asserted separately rather
    than assumed.
    """
    states = _run("traci", scenario, _steps(scenario))
    # More vehicles at once than the network holds when nothing waits.
    assert max(len(state.vehicles) for state in states) > scenario.free_flow_population
    assert max(lane.queue_count for state in states for lane in state.lanes) > 0
    assert states[-1].counters.arrived_at_sink > 0
    # Every authored phase was shown, decoded as a canonical phase (D-034).
    assert {state.signals[0].active_phase for state in states} == {
        phase.id for phase in scenario.built.intersection.phases
    }
