"""`RunCounters` (D-008, D-022) and the snapshot mechanism (D-032).

The counters are checked **against SUMO's own tripinfo output** rather than
against our expectations of it. That is the whole reason
`--tripinfo-output.write-unfinished` and `--write-undeparted` are passed: they
turn D-022's three-way accounting from something we compute into something SUMO
reports, "which removes a class of our own arithmetic errors". A test that only
compared our counters to themselves would remove nothing.

Snapshots are tested for the mechanism only. Which snapshot a run starts from,
and when one is produced, is T1.6's policy question.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests.backend.conftest import make_config
from traffic_lab.backend import SumoBackend
from traffic_lab.domain.network import IntersectionId
from traffic_lab.domain.state import TrueState

#: Four approaches at 3600 veh/h into a single-lane-per-movement intersection.
#: Far above capacity, which is how `research/M0_footguns.md` induces both
#: insertion loss and gridlock.
_OVERLOAD_ROUTES = """<routes>
    <vType id="passenger" vClass="passenger" accel="2.6" decel="4.5" sigma="0.5"
           length="5.0" minGap="2.5" maxSpeed="13.89"/>
    <route id="n_s" edges="n_in s_out"/>
    <route id="s_n" edges="s_in n_out"/>
    <route id="e_w" edges="e_in w_out"/>
    <route id="w_e" edges="w_in e_out"/>
    <flow id="f0" type="passenger" route="n_s" begin="0" end="3600" vehsPerHour="3600"
          departLane="0" departSpeed="max"/>
    <flow id="f1" type="passenger" route="s_n" begin="0" end="3600" vehsPerHour="3600"
          departLane="0" departSpeed="max"/>
    <flow id="f2" type="passenger" route="e_w" begin="0" end="3600" vehsPerHour="3600"
          departLane="0" departSpeed="max"/>
    <flow id="f3" type="passenger" route="w_e" begin="0" end="3600" vehsPerHour="3600"
          departLane="0" departSpeed="max"/>
</routes>
"""

#: Every link red. The reference network has eight controlled connections.
_ALL_RED = "r" * 8


def _tripinfo_legs(path: Path) -> tuple[int, int, int]:
    """(finished, unfinished, undeparted) as SUMO itself reported them."""
    entries = ET.parse(path).getroot().findall("tripinfo")
    undeparted = [e for e in entries if float(e.get("depart", "-1")) < 0]
    departed = [e for e in entries if float(e.get("depart", "-1")) >= 0]
    finished = [e for e in departed if float(e.get("arrival", "-1")) >= 0]
    return len(finished), len(departed) - len(finished), len(undeparted)


def test_trip_accounting_matches_sumos_own_tripinfo(
    reference_net: Path, reference_routes: Path, tmp_path: Path
) -> None:
    """D-022's three legs, each against the native output that defines it.

    This is also `05_DOMAIN_MODEL.md` SS8 invariant 14 -- served plus unserved
    equals inserted -- demonstrated to hold, although enforcing it is T1.8's.
    """
    tripinfo = tmp_path / "tripinfo.xml"
    backend = SumoBackend()
    backend.start(reference_net, reference_routes, make_config(tripinfo_path=tripinfo))
    try:
        for _ in range(600):
            backend.step()
            state = backend.project()
    finally:
        backend.close()

    finished, unfinished, undeparted = _tripinfo_legs(tripinfo)
    counters = state.counters
    assert counters.arrived_at_sink + counters.arrived_mid_link == finished
    assert counters.still_in_network == unfinished
    assert counters.insertion_failures == undeparted
    assert finished > 0 and unfinished > 0


def test_no_mid_link_arrivals_where_the_scenario_has_no_attrition(
    reference_net: Path, reference_routes: Path
) -> None:
    """The reference scenario sets no `arrivalPos`, so every arrival is a sink one.

    A sharp test of the sink/mid-link split, and the one that caught the
    constant-speed bound: it reported 8 spurious mid-link arrivals here because
    a vehicle accelerating in its final unobserved step covers more than v*dt.
    """
    backend = SumoBackend()
    backend.start(reference_net, reference_routes, make_config())
    try:
        for _ in range(600):
            backend.step()
            state = backend.project()
    finally:
        backend.close()
    assert state.counters.arrived_at_sink > 300
    assert state.counters.arrived_mid_link == 0


def test_teleports_stay_zero_and_insertion_loss_is_what_fires(
    reference_net: Path, tmp_path: Path
) -> None:
    """D-008 as re-prioritised on 2026-08-18, reproduced.

    `research/M0_footguns.md`: on an isolated intersection an over-capacity queue
    spills out of the network before a vehicle can be trapped long enough to
    teleport, so the overload is absorbed as insertion loss. The teleport counter
    staying zero is therefore the expected result, not a broken counter -- and
    the insertion counter reading 1500 against SUMO's own 1500 undeparted
    vehicles is what shows the counters are live.
    """
    routes = tmp_path / "overload.rou.xml"
    routes.write_text(_OVERLOAD_ROUTES)
    tripinfo = tmp_path / "tripinfo.xml"

    backend = SumoBackend()
    backend.start(reference_net, routes, make_config(tripinfo_path=tripinfo))
    try:
        for _ in range(400):
            backend.apply(IntersectionId(0), _ALL_RED)
            backend.step()
            state = backend.project()
    finally:
        backend.close()

    _finished, _unfinished, undeparted = _tripinfo_legs(tripinfo)
    assert state.counters.teleports == 0
    assert state.counters.insertion_failures == undeparted > 1000


def test_gridlock_is_detected_after_the_configured_number_of_still_steps(
    reference_net: Path, tmp_path: Path
) -> None:
    """D-008 item 3: "no vehicle has moved for N steps", N configurable."""
    routes = tmp_path / "overload.rou.xml"
    routes.write_text(_OVERLOAD_ROUTES)

    backend = SumoBackend()
    backend.start(reference_net, routes, make_config(gridlock_steps=30))
    try:
        detected_at = None
        for step in range(400):
            backend.apply(IntersectionId(0), _ALL_RED)
            backend.step()
            state = backend.project()
            if state.counters.gridlock_detected and detected_at is None:
                detected_at = step
    finally:
        backend.close()

    assert detected_at is not None, "an all-red overload must gridlock"
    # It cannot fire before N steps have passed, and the network needs a few
    # steps to fill and stop first.
    assert detected_at >= 30
    assert state.counters.gridlock_detected, "gridlock is sticky once detected"


def test_an_empty_network_is_not_gridlocked(
    reference_net: Path, reference_routes: Path, tmp_path: Path
) -> None:
    """An empty network is empty, not jammed.

    Without this, `gridlock_steps` would fire on every run that starts from an
    empty network and has a warm-up longer than N -- marking every run invalid.
    """
    routes = tmp_path / "empty.rou.xml"
    routes.write_text('<routes>\n    <vType id="passenger" vClass="passenger"/>\n</routes>\n')

    backend = SumoBackend()
    backend.start(reference_net, routes, make_config(gridlock_steps=5))
    try:
        for _ in range(50):
            backend.step()
            state = backend.project()
    finally:
        backend.close()
    assert state.vehicles == ()
    assert not state.counters.gridlock_detected


#: SUMO writes simulation state at two decimal places and offers no option to
#: change it -- `--precision` was measured to have no effect on the state file
#: (12 and 16 both still produced two decimals). Every float in a loaded state
#: is therefore its saved value rounded to 0.01.
_STATE_FILE_PRECISION_M = 0.01


def _run_to(backend: SumoBackend, steps: int) -> TrueState:
    for _ in range(steps):
        backend.step()
        state = backend.project()
    return state


@pytest.mark.parametrize("transport", ["traci", "libsumo"])
def test_a_loaded_snapshot_reproduces_the_state_it_was_saved_from(
    transport: str, reference_net: Path, reference_routes: Path, tmp_path: Path
) -> None:
    """D-032's mechanism, to the precision SUMO's state file actually carries.

    Everything the adapter itself keeps -- canonical IDs, lane assignment,
    halting timers, stop counts, the signal phase, all of `RunCounters` -- round
    trips **exactly**, because it travels in our own sidecar. Everything SUMO
    keeps round trips to 0.01, because that is the precision its state file is
    written at. See `_STATE_FILE_PRECISION_M`.
    """
    snapshot = tmp_path / "state.xml"
    backend = SumoBackend()
    backend.start(reference_net, reference_routes, make_config(transport=transport))
    try:
        saved = _run_to(backend, 120)
        backend.save_state(snapshot)
        backend.load_state(snapshot)
        loaded = backend.project()
    finally:
        backend.close()

    assert loaded.time_s == saved.time_s
    assert loaded.counters == saved.counters
    assert loaded.signals == saved.signals
    assert [lane.queue_count for lane in loaded.lanes] == [lane.queue_count for lane in saved.lanes]

    by_id = {vehicle.id: vehicle for vehicle in saved.vehicles}
    assert {vehicle.id for vehicle in loaded.vehicles} == set(by_id)
    assert len(by_id) > 20
    for vehicle in loaded.vehicles:
        before = by_id[vehicle.id]
        assert vehicle.lane == before.lane
        assert vehicle.type == before.type
        assert vehicle.stop_count == before.stop_count
        assert vehicle.halting_since_s == before.halting_since_s
        assert abs(vehicle.position_on_lane_m - before.position_on_lane_m) <= (
            _STATE_FILE_PRECISION_M
        )
        assert abs(vehicle.speed_mps - before.speed_mps) <= _STATE_FILE_PRECISION_M
        assert abs(vehicle.time_loss_s - before.time_loss_s) <= _STATE_FILE_PRECISION_M


def _replay(transport: str, net: Path, routes: Path, snapshot: Path, steps: int) -> list[TrueState]:
    """Start fresh, load the snapshot immediately, and run.

    This is the shape T1.6 will use, and the shape that is deterministic. See
    `test_a_replay_depends_on_the_processs_rng_history_too` for why it matters
    that the load happens before anything else consumes randomness.
    """
    backend = SumoBackend()
    backend.start(net, routes, make_config(transport=transport))
    try:
        backend.load_state(snapshot)
        states = []
        for _ in range(steps):
            backend.step()
            states.append(backend.project())
        return states
    finally:
        backend.close()


def _produce(net: Path, routes: Path, snapshot: Path) -> None:
    backend = SumoBackend()
    backend.start(net, routes, make_config())
    try:
        _run_to(backend, 120)
        backend.save_state(snapshot)
    finally:
        backend.close()


@pytest.mark.parametrize("transport", ["traci", "libsumo"])
def test_replaying_a_snapshot_is_deterministic(
    transport: str, reference_net: Path, reference_routes: Path, tmp_path: Path
) -> None:
    """The property D-032 actually needs: one snapshot, one evolution.

    It is *not* the same evolution as the un-snapshotted continuation -- the
    0.01 rounding above perturbs the initial condition and the car-following
    model amplifies it within a step or two. What D-032 needs is that every arm
    loading one snapshot gets the same starting point and the same evolution
    from it, which is what makes a neutral-snapshot comparison controlled.
    """
    snapshot = tmp_path / "state.xml"
    _produce(reference_net, reference_routes, snapshot)

    first = _replay(transport, reference_net, reference_routes, snapshot, 40)
    second = _replay(transport, reference_net, reference_routes, snapshot, 40)

    assert first == second
    assert len(first[-1].vehicles) > 20


def test_a_replay_depends_on_the_processs_rng_history_too(
    reference_net: Path, reference_routes: Path, tmp_path: Path
) -> None:
    """`loadState` restores the vehicles but **not** SUMO's RNG.

    Loading the same snapshot twice into the *same* running simulator gives two
    different futures, because the first replay consumed randomness that the
    second then continues from. Recorded as a test rather than a comment because
    it constrains how T1.6 may use snapshots: a snapshot must be loaded into a
    freshly started simulator, before anything else has drawn from the RNG, or
    the arms of a neutral-snapshot comparison are not comparable after all.
    """
    snapshot = tmp_path / "state.xml"
    _produce(reference_net, reference_routes, snapshot)

    backend = SumoBackend()
    backend.start(reference_net, reference_routes, make_config())
    try:
        backend.load_state(snapshot)
        first = [_run_to(backend, 1) for _ in range(40)]
        backend.load_state(snapshot)
        second = [_run_to(backend, 1) for _ in range(40)]
    finally:
        backend.close()

    assert first[0].time_s == second[0].time_s, "both replays restart at the same time"
    assert first != second, (
        "if this ever passes, SUMO began restoring its RNG and the constraint "
        "documented here can be relaxed"
    )


def test_save_and_load_do_not_differ_between_transports(
    reference_net: Path, reference_routes: Path, tmp_path: Path
) -> None:
    """T1.4's third escalation condition, checked rather than assumed.

    "Escalate if `save_state` / `load_state` differ between transports." They do
    differ in *mechanism* -- SUMO drops TraCI subscriptions across a load, so the
    TraCI transport re-registers them and LibSUMO has nothing to re-register --
    and this asserts that the difference stops there.
    """
    snapshot = tmp_path / "state.xml"
    _produce(reference_net, reference_routes, snapshot)

    over_traci = _replay("traci", reference_net, reference_routes, snapshot, 20)
    over_libsumo = _replay("libsumo", reference_net, reference_routes, snapshot, 20)

    assert over_traci == over_libsumo
    assert len(over_traci[-1].vehicles) > 20
