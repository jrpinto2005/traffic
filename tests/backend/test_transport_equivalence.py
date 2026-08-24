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

from pathlib import Path

from tests.backend.conftest import make_config
from traffic_lab.backend import SumoBackend
from traffic_lab.domain.state import TrueState

#: Long enough to cover several full signal cycles (60 s each in the reference
#: program), a saturated queue, and hundreds of arrivals, so the counters and the
#: halting bookkeeping are all exercised rather than just the empty-network case.
STEPS = 300


def _run(transport: str, net: Path, routes: Path, steps: int = STEPS) -> list[TrueState]:
    backend = SumoBackend()
    backend.start(net, routes, make_config(transport=transport))
    try:
        states = []
        for _ in range(steps):
            backend.step()
            states.append(backend.project())
        return states
    finally:
        backend.close()


def test_transports_produce_identical_true_state_sequences(
    reference_net: Path, reference_routes: Path
) -> None:
    over_traci = _run("traci", reference_net, reference_routes)
    over_libsumo = _run("libsumo", reference_net, reference_routes)

    assert len(over_traci) == len(over_libsumo) == STEPS
    for step, (traci_state, libsumo_state) in enumerate(zip(over_traci, over_libsumo, strict=True)):
        assert traci_state == libsumo_state, f"transports diverge at step {step}"


def test_the_sequence_is_not_trivially_empty(reference_net: Path, reference_routes: Path) -> None:
    """Guard against the equivalence test passing on two empty simulations.

    An equality assertion over two runs that both did nothing would pass and
    prove nothing, so the fixture's own liveness is asserted separately rather
    than assumed.
    """
    states = _run("traci", reference_net, reference_routes)
    assert max(len(state.vehicles) for state in states) > 20
    assert max(lane.queue_count for state in states for lane in state.lanes) > 0
    assert states[-1].counters.arrived_at_sink > 0
    assert len({state.signals[0].active_phase for state in states}) == 4
