"""`build()` on generated nets: files, round trip, validation, geometry (T1.3).

Runtime behaviour in SUMO -- warnings, `BackendIndex` order, what the light
actually shows -- is in `test_runtime.py`.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests.scenarios.conftest import (
    FOUR_WAY,
    TIMING,
    Built,
    L,
    R,
    S,
    assert_round_trip,
    foe_bit,
    raw_net,
    request_rows,
)
from traffic_lab.domain.network import (
    IntersectionId,
    NetworkValidationError,
    PhaseId,
    TurnDirection,
    green_link_indices,
    movements_of,
    validate_network,
)
from traffic_lab.scenarios import (
    IntersectionSpec,
    NetworkCorrespondenceError,
    PhaseSpec,
    build,
)
from traffic_lab.scenarios.generator import CENTER, IDS_SUFFIX, NET_STEM


def test_build_emits_the_input_files_the_net_and_the_id_mapping(four_way: Built) -> None:
    out_dir = four_way.net.parent
    assert four_way.net == out_dir / f"{NET_STEM}.net.xml"
    for suffix in (".nod.xml", ".edg.xml", ".con.xml", ".tll.xml", IDS_SUFFIX):
        assert (out_dir / f"{NET_STEM}{suffix}").is_file(), suffix


def test_every_sumo_lane_and_connection_appears_exactly_once(generated: Built) -> None:
    """AC: the canonical Network round-trips, by count and by ID. Connections are
    counted as Amendment A2 defines them -- see `assert_round_trip`."""
    assert_round_trip(generated.network, generated.ids, generated.net)


def test_validate_network_passes(generated: Built) -> None:
    validate_network(generated.network)


def test_the_t_junction_has_turns_and_no_through_movement(t_junction: Built) -> None:
    """AC: three approaches work, so nothing assumes four. At 120-degree spacing
    every approach turns right or left; nothing goes straight."""
    network, ids = t_junction.network, t_junction.ids
    (intersection,) = network.signalized_intersections
    movements = movements_of(network, intersection.junction)
    turns: dict[str, set[TurnDirection]] = {}
    for movement in movements:
        turns.setdefault(ids.edges[movement.from_edge], set()).add(movement.turn)
    assert turns == {f"approach_{k}_in": {R, L} for k in range(3)}
    assert len(intersection.phases) == 3


def test_a_phase_with_a_conflicting_pair_fails_naming_the_pair(tmp_path: Path) -> None:
    """AC, D-023: a hard error naming the pair, raised before anything is written."""
    spec = IntersectionSpec(
        phases=[PhaseSpec(green=[(0, S), (1, S)]), PhaseSpec(green=[(2, S)])], timing=TIMING
    )
    with pytest.raises(NetworkValidationError) as raised:
        build(spec, tmp_path)
    assert raised.value.invariant == 7
    assert "(approach_0_in, through) and (approach_1_in, through)" in str(raised.value)
    assert not list(tmp_path.iterdir())


def test_a_protected_left_against_the_opposing_through_is_rejected(tmp_path: Path) -> None:
    """The permissive left the M0 probe allows is CONFLICTING here: no M1
    scenario declares a permitted pair (D-023 point 4)."""
    spec = IntersectionSpec(phases=[PhaseSpec(green=[(0, L), (2, S)])], timing=TIMING)
    with pytest.raises(NetworkValidationError, match="approach_0_in, left"):
        build(spec, tmp_path)


def test_foes_are_symmetric_at_every_generated_junction(generated: Built) -> None:
    """A7: `foes` read right to left is symmetric."""
    rows = request_rows(generated.net)
    assert CENTER in rows
    for junction, junction_rows in rows.items():
        for i, (foes_i, _) in enumerate(junction_rows):
            for j, (foes_j, _) in enumerate(junction_rows):
                assert foe_bit(foes_i, j) == foe_bit(foes_j, i), (junction, i, j)


def test_generated_nets_have_no_internal_junctions(generated: Built) -> None:
    """So `JunctionId` covers every junction SUMO reports, internal ones included
    (`traci.junction.getIDList()` lists internal junctions; `test_runtime.py`)."""
    assert "internal" not in raw_net(generated.net).junctions.values()


def test_the_written_program_is_the_one_in_the_net(generated: Built) -> None:
    """Each authored phase's green state in the built net greens exactly
    `green_link_indices()`, followed by its yellow and the all-red."""
    root = ET.parse(generated.net).getroot()
    (tl_logic,) = root.iter("tlLogic")
    phases = [(float(p.get("duration", "0")), p.get("state", "")) for p in tl_logic.iter("phase")]
    assert len(phases) == 3 * len(generated.spec.phases)
    for k in range(len(generated.spec.phases)):
        (green_s, green), (yellow_s, yellow), (red_s, red) = phases[3 * k : 3 * k + 3]
        expected = green_link_indices(generated.network, IntersectionId(0), PhaseId(k))
        assert {i for i, ch in enumerate(green) if ch == "G"} == expected
        assert set(green) <= {"G", "r"}
        assert {i for i, ch in enumerate(yellow) if ch == "y"} == expected
        assert set(yellow) <= {"y", "r"}
        assert set(red) == {"r"}
        assert (green_s, yellow_s, red_s) == (TIMING.min_green_s, TIMING.yellow_s, TIMING.all_red_s)


def test_a_zero_all_red_is_omitted(tmp_path: Path) -> None:
    timing = type(TIMING)(min_green_s=10.0, max_green_s=60.0, yellow_s=3.0, all_red_s=0.0)
    net, _ = build(FOUR_WAY.model_copy(update={"timing": timing}), tmp_path)
    (tl_logic,) = ET.parse(net).getroot().iter("tlLogic")
    states = [p.get("state", "") for p in tl_logic.iter("phase")]
    assert len(states) == 2 * len(FOUR_WAY.phases)
    assert not any(set(state) == {"r"} for state in states)


def test_approach_k_sits_at_bearing_360k_over_n(generated: Built) -> None:
    root = ET.parse(generated.net).getroot()
    xy = {
        j.get("id"): (float(j.get("x", "0")), float(j.get("y", "0"))) for j in root.iter("junction")
    }
    cx, cy = xy[CENTER]
    n = generated.spec.approaches
    for k in range(n):
        x, y = xy[f"approach_{k}"]
        bearing = math.degrees(math.atan2(x - cx, y - cy)) % 360.0
        assert min(abs(bearing - 360.0 * k / n), 360.0 - abs(bearing - 360.0 * k / n)) < 0.01
        assert math.hypot(x - cx, y - cy) == pytest.approx(
            generated.spec.approach_length_m, abs=0.01
        )


def test_lanes_and_edges_follow_the_spec(generated: Built) -> None:
    network, ids, spec = generated.network, generated.ids, generated.spec
    edges = {ids.edges[e.id]: e for e in network.edges}
    lanes = {lane.id: lane for lane in network.lanes}
    for k in range(spec.approaches):
        inbound, outbound = edges[f"approach_{k}_in"], edges[f"approach_{k}_out"]
        assert inbound.opposite == outbound.id and outbound.opposite == inbound.id
        for edge in (inbound, outbound):
            assert len(edge.lanes) == spec.lanes_per_approach
            for lane_id in edge.lanes:
                lane = lanes[lane_id]
                assert lane.speed_limit_mps == spec.speed_limit_mps
                # Nominal node spacing; junction geometry consumes part of it.
                assert 0.0 < lane.length_m < spec.approach_length_m


def test_five_approaches_cannot_be_represented(tmp_path: Path) -> None:
    """Escalation, T1.3 condition 2: at five approaches netconvert gives one
    approach two right exits (`r` and `R`); a Movement keyed by (approach, turn)
    cannot hold both. Raised rather than merging two movements into one."""
    spec = IntersectionSpec(approaches=5, phases=[PhaseSpec(green=[(0, S)])], timing=TIMING)
    with pytest.raises(NetworkCorrespondenceError, match="approach_0_in has 2 right exits"):
        build(spec, tmp_path)
