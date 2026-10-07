"""Generated nets in a running SUMO (T1.3 Amendment A7).

These are the checks that would have caught the M0 reference program: what the
light actually shows, read back from SUMO, compared with what the canonical
phases say -- never with our own copy of the program.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import sumolib
import traci

from tests.scenarios.conftest import Built
from traffic_lab.backend import BackendConfig, SumoBackend, TransportName
from traffic_lab.domain.network import PhaseId, movements_of

SUMO = sumolib.checkBinary("sumo")


def _demand(built: Built, path: Path, end_s: float) -> Path:
    """One flow per movement, so every movement has vehicles on it. Test fixture
    only -- demand generation is T1.5."""
    network, ids = built.network, built.ids
    (intersection,) = network.signalized_intersections
    lines = ["<routes>"]
    for movement in movements_of(network, intersection.junction):
        lines.append(
            f'    <flow id="m{int(movement.id)}" from="{ids.edges[movement.from_edge]}" '
            f'to="{ids.edges[movement.to_edge]}" begin="0" end="{end_s}" period="7" '
            f'departLane="best" departSpeed="max"/>'
        )
    lines.append("</routes>")
    path.write_text("\n".join(lines) + "\n")
    return path


def _cycle_s(built: Built) -> float:
    timing = built.spec.timing
    return len(built.spec.phases) * (timing.min_green_s + timing.yellow_s + timing.all_red_s)


def test_sumo_loads_and_runs_the_net_with_no_warnings(generated: Built, tmp_path: Path) -> None:
    """A7: run WITHOUT `--no-warnings` -- the flag that hid the M0 reference's
    crossing greens. Two full cycles of the static program with vehicles on every
    movement: a program greening crossing movements would show up here as
    emergency braking or collisions.

    `LC_ALL=C` because SUMO otherwise warns that it could not set the C locale on
    this machine -- a warning about the process environment, not the network.
    """
    end_s = 2 * _cycle_s(generated) + 60.0
    routes = _demand(generated, tmp_path / "demand.rou.xml", end_s - 60.0)
    result = subprocess.run(
        [
            SUMO,
            "--net-file",
            str(generated.net),
            "--route-files",
            str(routes),
            "--end",
            str(end_s),
            "--time-to-teleport",
            "-1",
            "--no-step-log",
            "true",
            "--duration-log.statistics",
            "true",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "LC_ALL": "C"},
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Warning" not in output, output
    assert "Error" not in output, output
    inserted = int(output.split("Inserted: ")[1].split()[0])
    assert inserted > 50, output  # the run really carried traffic


@pytest.mark.parametrize("transport", ["traci", "libsumo"])
def test_backend_index_follows_the_generator_id_mapping(
    generated: Built, tmp_path: Path, transport: TransportName
) -> None:
    """A7: `BackendIndex` lists lanes and traffic lights in exactly the order of
    the generator's emitted mapping, so `TrueState` and `Network` name the same
    lanes (Amendment A2)."""
    routes = tmp_path / "empty.rou.xml"
    routes.write_text("<routes/>\n")
    backend = SumoBackend()
    backend.start(
        generated.net,
        routes,
        BackendConfig(transport=transport, seed=1, decision_interval_s=1.0, gridlock_steps=100),
    )
    try:
        assert backend.index.lane_sumo_ids == generated.ids.lanes
        assert backend.index.intersection_sumo_ids == generated.ids.intersections
    finally:
        backend.close()


Links = frozenset[tuple[str, str]]


def _shown(net: Path, tls_id: str, steps: int) -> list[tuple[Links, Links]]:
    """Per step, the (green, yellow) connections SUMO displays, as SUMO lane pairs:
    `getControlledLinks()` read against `getRedYellowGreenState()`. Nothing of
    ours is consulted."""
    traci.start([SUMO, "--net-file", str(net), "--no-step-log", "true", "--end", str(steps + 1)])
    try:
        links = traci.trafficlight.getControlledLinks(tls_id)
        shown: list[tuple[Links, Links]] = []
        for _ in range(steps):
            state = traci.trafficlight.getRedYellowGreenState(tls_id)
            green = frozenset(
                (i, o) for k, ch in enumerate(state) if ch in "Gg" for i, o, _ in links[k]
            )
            yellow = frozenset(
                (i, o) for k, ch in enumerate(state) if ch in "yY" for i, o, _ in links[k]
            )
            shown.append((green, yellow))
            traci.simulationStep()
        return shown
    finally:
        traci.close()


def _phase_connections(built: Built) -> list[Links]:
    """Each authored phase's connections, from its movements -- not from
    `controlled_connections` or `green_link_indices()`, which are under test."""
    network, ids = built.network, built.ids
    (intersection,) = network.signalized_intersections
    movements = {m.id: m for m in movements_of(network, intersection.junction)}
    groups = {g.id: g for g in intersection.signal_groups}
    return [
        frozenset(
            ids.connections[c]
            for g in phase.green_groups
            for m in groups[g].movements
            for c in movements[m].connections
        )
        for phase in intersection.phases
    ]


def _check_display(built: Built, net: Path) -> list[PhaseId]:
    """Run one cycle and return the phases shown, in order. Raises AssertionError
    if any green display is not exactly one authored phase's connections, or a
    yellow is not the yellow of the phase just shown."""
    expected = _phase_connections(built)
    shown_phases: list[PhaseId] = []
    for green, yellow in _shown(net, built.ids.intersections[0], int(_cycle_s(built))):
        if green:
            assert not yellow, "green and yellow shown together"
            assert green in expected, f"SUMO shows green {sorted(green)}: no authored phase"
            phase = PhaseId(expected.index(green))
            if not shown_phases or shown_phases[-1] != phase:
                shown_phases.append(phase)
        elif yellow:
            assert shown_phases and yellow == expected[shown_phases[-1]]
    return shown_phases


def test_sumo_shows_green_exactly_on_each_phase_movements(generated: Built) -> None:
    """A7: for each authored phase, the links SUMO actually shows green at runtime
    are exactly the connections of that phase's movements, every phase is shown,
    in the authored order."""
    shown = _check_display(generated, generated.net)
    assert shown == [PhaseId(k) for k in range(len(generated.spec.phases))]


def test_traci_reports_the_same_junctions_and_edges(generated: Built) -> None:
    """`JunctionId` and `EdgeId` follow sorted SUMO IDs as a running SUMO reports
    them: TraCI's junction list includes internal junctions, of which generated
    nets have none."""
    traci.start([SUMO, "--net-file", str(generated.net), "--no-step-log", "true", "--end", "1"])
    try:
        assert tuple(sorted(traci.junction.getIDList())) == generated.ids.junctions
        assert tuple(sorted(traci.edge.getIDList())) == generated.ids.edges
    finally:
        traci.close()
