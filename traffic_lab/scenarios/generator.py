"""`build()`: a parametric single signalized intersection, as SUMO files and canonical types.

Implements T1.3 (as amended 2026-10-07): emits `.nod.xml`, `.edg.xml`,
`.con.xml` and `.tll.xml`, runs `netconvert`, and parses the result with
`parse_network()` -- the same parser used for nets T1.3 did not generate.

**Two passes** (Amendment A1, trap 3). netconvert does not honour a `linkIndex`
written in a `.con.xml`, and the static program's state strings are indexed by
`linkIndex`. So the net is built once from nodes and edges alone, its link
order read back, the program written against that order, and the net rebuilt
with the program. The second pass is then checked: the program in the final
net must show, for every authored phase, exactly the links
`green_link_indices()` computes from the final net. The M0 reference greened
crossing movements for seven weeks because nothing made this check.

**Geometry.** Approach *k* of *n* is a two-way street from a boundary node at
bearing 360*k/n degrees clockwise from north, `approach_length_m` from the
centre. Edge IDs are `approach_<k>_in` (towards the junction) and
`approach_<k>_out`; the junction and its traffic light are `center`. Which
lanes carry which turns is netconvert's default assignment for shared lanes
(`turn_lanes=False`), recorded explicitly in the emitted `.con.xml`; no U-turn
connections are generated (`--no-turnarounds`).

**Warnings fail the build.** Any warning from netconvert raises: the generator
is the only author of these files, so a warning about them is a generator
defect, not noise. The converse does not hold -- SUMO runs a program that
greens conflicting links without a single warning, because netconvert derives
right-of-way from the loaded program (`tests/scenarios/test_link_order.py`).
The program check above, not the absence of warnings, is the guard.
"""

from __future__ import annotations

import math
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Literal
from xml.sax.saxutils import quoteattr

import sumolib

from traffic_lab.domain.network import Network, PhaseId, SignalTiming, green_link_indices
from traffic_lab.scenarios.conflicts import NetworkCorrespondenceError
from traffic_lab.scenarios.parse import SumoIds, parse_network
from traffic_lab.scenarios.spec import IntersectionSpec

#: Stem of every emitted file: `intersection.nod.xml`, ..., `intersection.net.xml`.
NET_STEM = "intersection"

#: The signalized junction and its traffic light.
CENTER = "center"

#: The emitted SUMO ID <-> canonical ID mapping (05_DOMAIN_MODEL.md SS1.2), beside the net.
IDS_SUFFIX = ".ids.json"


class NetconvertError(RuntimeError):
    """netconvert failed or warned while building a generated network."""


def approach_node(k: int) -> str:
    return f"approach_{k}"


def approach_in_edge(k: int) -> str:
    return f"approach_{k}_in"


def approach_out_edge(k: int) -> str:
    return f"approach_{k}_out"


def build(
    spec: IntersectionSpec,
    out_dir: Path,
    *,
    program: Literal["static", "actuated"] = "static",
) -> tuple[Path, Network]:
    """Returns (path to the .net.xml, the canonical Network).

    Also writes `<stem>.ids.json` (`SumoIds`) beside the net: the SUMO ID of
    every canonical ID. Raises `NetworkValidationError` naming the pair if an
    authored phase contains a `CONFLICTING` movement pair -- before any file is
    written to `out_dir`.
    """
    phases = [[(approach_in_edge(k), turn) for k, turn in phase.green] for phase in spec.phases]
    nodes = out_dir / f"{NET_STEM}.nod.xml"
    edges = out_dir / f"{NET_STEM}.edg.xml"
    connections = out_dir / f"{NET_STEM}.con.xml"
    program_file = out_dir / f"{NET_STEM}.tll.xml"
    net = out_dir / f"{NET_STEM}.net.xml"

    with tempfile.TemporaryDirectory() as tmp:
        draft_dir = Path(tmp)
        _write_nodes(draft_dir / nodes.name, spec)
        _write_edges(draft_dir / edges.name, spec)
        draft_net = draft_dir / "draft.net.xml"
        _netconvert(draft_net, draft_dir / nodes.name, draft_dir / edges.name)
        # Validates the authored phases (D-023) before anything reaches out_dir:
        # `foes` is geometry and does not change when the program is added.
        draft, draft_ids = parse_network(draft_net, phases=phases, timing=spec.timing)

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_nodes(nodes, spec)
    _write_edges(edges, spec)
    _write_connections(connections, draft, draft_ids)
    _write_program(program_file, draft, draft_ids, spec.timing, program=program)
    _netconvert(net, nodes, edges, connections, program_file)

    network, ids = parse_network(net, phases=phases, timing=spec.timing)
    _check_program_matches_link_order(net, network, len(phases), spec.timing, program=program)
    (out_dir / f"{NET_STEM}{IDS_SUFFIX}").write_text(ids.to_json())
    return net, network


# --- Plain XML ---------------------------------------------------------------


def _write_nodes(path: Path, spec: IntersectionSpec) -> None:
    lines = [
        "<nodes>",
        f'    <node id="{CENTER}" x="0.00" y="0.00" type="traffic_light" tl="{CENTER}"/>',
    ]
    for k in range(spec.approaches):
        bearing = 2.0 * math.pi * k / spec.approaches  # clockwise from north
        x = spec.approach_length_m * math.sin(bearing)
        y = spec.approach_length_m * math.cos(bearing)
        lines.append(f'    <node id="{approach_node(k)}" x="{x:.2f}" y="{y:.2f}" type="dead_end"/>')
    lines.append("</nodes>")
    path.write_text("\n".join(lines) + "\n")


def _write_edges(path: Path, spec: IntersectionSpec) -> None:
    lines = ["<edges>"]
    for k in range(spec.approaches):
        for edge, origin, target in (
            (approach_in_edge(k), approach_node(k), CENTER),
            (approach_out_edge(k), CENTER, approach_node(k)),
        ):
            lines.append(
                f'    <edge id="{edge}" from="{origin}" to="{target}" '
                f'numLanes="{spec.lanes_per_approach}" speed="{_number(spec.speed_limit_mps)}"/>'
            )
    lines.append("</edges>")
    path.write_text("\n".join(lines) + "\n")


def _write_connections(path: Path, draft: Network, ids: SumoIds) -> None:
    lanes = {lane.id: lane for lane in draft.lanes}
    lines = [
        "<!-- The connections netconvert assigned from the node and edge files alone (its",
        "     default lane assignment for shared lanes, no turnarounds), recorded so the",
        "     connection set is explicit. No linkIndex: netconvert does not honour one",
        "     written here (T1.3 Amendment A1, trap 3). -->",
        "<connections>",
    ]
    for connection in draft.connections:
        source, target = lanes[connection.from_lane], lanes[connection.to_lane]
        lines.append(
            f"    <connection from={quoteattr(ids.edges[source.edge])} "
            f"to={quoteattr(ids.edges[target.edge])} "
            f'fromLane="{source.index}" toLane="{target.index}"/>'
        )
    lines.append("</connections>")
    path.write_text("\n".join(lines) + "\n")


def _program_states(
    network: Network, n_phases: int, timing: SignalTiming
) -> list[tuple[float, str]]:
    """(duration_s, state) for the static program, from `green_link_indices()`.

    Each authored phase in order: green for `min_green_s` ('G' on its green
    links), yellow for `yellow_s` ('y' on the same links), all-red for
    `all_red_s` (omitted when 0). Every other link 'r'. The same display T1.14's
    `display_state()` produces: no link stays green across a transition.
    """
    (intersection,) = network.signalized_intersections
    size = len(intersection.controlled_connections)
    states: list[tuple[float, str]] = []
    for k in range(n_phases):
        green = green_link_indices(network, intersection.id, PhaseId(k))
        states.append((timing.min_green_s, _state(size, green, "G")))
        states.append((timing.yellow_s, _state(size, green, "y")))
        if timing.all_red_s > 0.0:
            states.append((timing.all_red_s, "r" * size))
    return states


def _write_program(
    path: Path,
    draft: Network,
    ids: SumoIds,
    timing: SignalTiming,
    *,
    program: Literal["static", "actuated"] = "static",
) -> None:
    (tls_id,) = ids.intersections
    n_phases = len(draft.signalized_intersections[0].phases)
    lines = [
        "<!-- The authored phases in order: green min_green_s, yellow yellow_s, all-red",
        "     all_red_s (omitted when 0). In effect ONLY until the first Backend.apply();",
        "     from then on the controller drives the light. This is not a baseline",
        "     fixed-time plan and must not be reported as one.",
        "     States are indexed by the linkIndex read back from a first netconvert pass",
        "     (T1.3 Amendment A1, trap 3). -->",
        "<additional>",
        f'    <tlLogic id={quoteattr(tls_id)} type="{program}" programID="0" offset="0">',
    ]
    if program == "actuated":
        lines += [
            '        <param key="max-gap" value="3.0"/>',
            '        <param key="detector-gap" value="2.0"/>',
            '        <param key="passing-time" value="2.0"/>',
        ]
    for duration_s, state in _program_states(draft, n_phases, timing):
        if program == "actuated" and "G" in state:
            lines.append(
                f'        <phase duration="{_number(duration_s)}" '
                f'minDur="{_number(timing.min_green_s)}" '
                f'maxDur="{_number(timing.max_green_s)}" '
                f'state="{state}"/>'
            )
        else:
            lines.append(f'        <phase duration="{_number(duration_s)}" state="{state}"/>')
    lines += ["    </tlLogic>", "</additional>"]
    path.write_text("\n".join(lines) + "\n")


def _state(size: int, green: frozenset[int], char: str) -> str:
    return "".join(char if i in green else "r" for i in range(size))


def _number(value: float) -> str:
    """A float for a SUMO attribute: no exponent, no trailing `.0` noise."""
    return str(int(value)) if value == int(value) else repr(value)


# --- netconvert --------------------------------------------------------------


def _netconvert(
    output: Path,
    nodes: Path,
    edges: Path,
    connections: Path | None = None,
    program: Path | None = None,
) -> None:
    argv = [
        sumolib.checkBinary("netconvert"),
        "--node-files",
        str(nodes),
        "--edge-files",
        str(edges),
        "--no-turnarounds",
        "true",
        "--output-file",
        str(output),
    ]
    if connections is not None:
        argv += ["--connection-files", str(connections)]
    if program is not None:
        argv += ["--tllogic-files", str(program)]
    # SUMO's tools set the C locale at start-up and, where the environment prevents
    # it, warn "Could not set locale to 'C'" -- a warning about the process, not the
    # network. LC_ALL=C lets the call succeed, so every warning left is a real one.
    result = subprocess.run(
        argv, capture_output=True, text=True, env={**os.environ, "LC_ALL": "C"}, check=False
    )
    output_text = result.stdout + result.stderr
    if result.returncode != 0:
        raise NetconvertError(f"netconvert failed ({result.returncode}):\n{output_text}")
    warnings = [line for line in output_text.splitlines() if line.startswith("Warning")]
    if warnings:
        raise NetconvertError("netconvert warned:\n" + "\n".join(warnings))


# --- The check that would have caught the M0 reference ------------------------


def _check_program_matches_link_order(
    net: Path,
    network: Network,
    n_phases: int,
    timing: SignalTiming,
    *,
    program: Literal["static", "actuated"] = "static",
) -> None:
    """The final net's program must be the one `green_link_indices()` computes
    from the final net. Fails if netconvert renumbered links between passes, or
    if the program did not load as written."""
    tls = sumolib.net.readNet(str(net), withPrograms=True).getTrafficLights()[0]
    programs = tls.getPrograms()
    if len(programs) != 1:
        raise NetworkCorrespondenceError(
            f"{net.name} has {len(programs)} programs for {tls.getID()}, expected 1"
        )
    (loaded,) = programs.values()
    if loaded.getType() != program:
        raise NetworkCorrespondenceError(
            f"{net.name} program type is {loaded.getType()!r}, expected {program!r}"
        )
    actual = [(float(p.duration), p.state) for p in loaded.getPhases()]
    expected = _program_states(network, n_phases, timing)
    if actual != expected:
        raise NetworkCorrespondenceError(
            f"the program in {net.name} does not show the authored phases on the built "
            f"net's links:\n  expected {expected}\n  found    {actual}"
        )
    if program == "actuated":
        for p in loaded.getPhases():
            if "G" in p.state and (
                float(p.minDur) != timing.min_green_s or float(p.maxDur) != timing.max_green_s
            ):
                raise NetworkCorrespondenceError(
                    f"actuated phase {p.state} has minDur={p.minDur}, maxDur={p.maxDur}; "
                    f"expected {timing.min_green_s}, {timing.max_green_s}"
                )
