"""`SignalState`'s two instants, after the 2026-08-24 amendment.

`phase_started_s` marks when a phase became active -- the start of the
transition into it -- and `green_started_s` marks when its green began, or is
`None` while the transition is still running. The amendment's stated reason for
adding the second field is that a consumer would otherwise have had to compute
`now - phase_started_s - yellow_s - all_red_s`, so that identity is what the
first test below checks, on a program whose timings are known exactly.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from tests.backend.conftest import make_config
from traffic_lab.backend import SumoBackend
from traffic_lab.domain.network import IntersectionId
from traffic_lab.domain.state import SignalState

#: `spikes/M0_reference/reference.tll.xml`: 27 s green, 3 s yellow, twice over.
#: No all-red -- the reference program predates it.
_GREEN_S = 27.0
_YELLOW_S = 3.0
_ALL_RED_S = 0.0

_ALL_RED_STATE = "r" * 8


def _signals(reference_net: Path, reference_routes: Path, steps: int) -> list[SignalState]:
    backend = SumoBackend()
    backend.start(reference_net, reference_routes, make_config())
    try:
        out = []
        for _ in range(steps):
            backend.step()
            out.append(backend.project().signals[0])
        return out
    finally:
        backend.close()


def test_green_started_is_none_exactly_while_in_transition(
    reference_net: Path, reference_routes: Path
) -> None:
    signals = _signals(reference_net, reference_routes, 200)
    for signal in signals:
        assert (signal.green_started_s is None) == signal.in_transition
    # Both states really occur, or the biconditional above is half vacuous.
    assert any(signal.in_transition for signal in signals)
    assert any(not signal.in_transition for signal in signals)


def test_elapsed_green_matches_the_formula_the_amendment_replaced(
    reference_net: Path, reference_routes: Path
) -> None:
    """`green_started_s` equals `phase_started_s + yellow_s + all_red_s`.

    On a program whose transition timings are known, the new field must agree
    with the arithmetic it exists to save consumers from writing. If it does
    not, one of the two instants is being tracked against the wrong boundary.
    """
    signals = _signals(reference_net, reference_routes, 200)
    checked = 0
    for index, signal in enumerate(signals):
        if signal.in_transition or index < int(_GREEN_S + _YELLOW_S):
            # Skip the first phase, whose transition happened before the run
            # began and so has no start to track.
            continue
        assert signal.green_started_s is not None
        assert signal.green_started_s == signal.phase_started_s + _YELLOW_S + _ALL_RED_S
        checked += 1
    assert checked > 50


def test_the_two_instants_advance_once_per_cycle(
    reference_net: Path, reference_routes: Path
) -> None:
    """A green run keeps one `green_started_s`, and it moves by the cycle length."""
    signals = _signals(reference_net, reference_routes, 240)
    greens = sorted(
        {signal.green_started_s for signal in signals if signal.green_started_s is not None}
    )
    assert len(greens) >= 3
    gaps = {round(b - a, 6) for a, b in itertools.pairwise(greens)}
    assert gaps == {_GREEN_S + _YELLOW_S + _ALL_RED_S}


def test_an_override_that_shows_no_green_is_a_transition(
    reference_net: Path, reference_routes: Path
) -> None:
    """`in_transition` is read from the state string, not from the program.

    A controller driving the signal directly (T1.7) bypasses SUMO's phase table
    entirely, so a projection that inferred transitions from the phase index
    would go wrong the moment a controller took over.
    """
    backend = SumoBackend()
    backend.start(reference_net, reference_routes, make_config())
    try:
        for _ in range(10):
            backend.step()
            running = backend.project().signals[0]
        assert not running.in_transition
        assert running.green_started_s is not None

        for _ in range(5):
            backend.apply(IntersectionId(0), _ALL_RED_STATE)
            backend.step()
            overridden = backend.project().signals[0]
    finally:
        backend.close()

    assert overridden.in_transition
    assert overridden.green_started_s is None
    assert overridden.phase_started_s > running.phase_started_s


@pytest.mark.parametrize("transport", ["traci", "libsumo"])
def test_signal_timing_survives_a_snapshot(
    transport: str, reference_net: Path, reference_routes: Path, tmp_path: Path
) -> None:
    """Neither instant is in SUMO's state file, so both ride in the sidecar.

    Without this, a run resumed from a snapshot would report a phase that began
    at the moment of resumption, silently resetting every green timer.
    """
    snapshot = tmp_path / "state.xml"
    backend = SumoBackend()
    backend.start(reference_net, reference_routes, make_config(transport=transport))
    try:
        for _ in range(100):
            backend.step()
            saved = backend.project().signals[0]
        backend.save_state(snapshot)
        backend.load_state(snapshot)
        loaded = backend.project().signals[0]
    finally:
        backend.close()

    assert not saved.in_transition, "the fixture must be mid-green for this to mean anything"
    assert loaded == saved
