"""Tests for trace format, TraceWriter, and TraceReader (D-030, T2.1)."""

from __future__ import annotations

import functools
import json
from pathlib import Path

import pytest

from tests.experiments.support import in_fresh_process
from tests.generated_scenario import (
    DEMAND_PERIOD_S,
    FOUR_WAY,
    build_intersection,
    one_flow_per_movement,
)
from traffic_lab.domain.network import (
    ConflictMatrix,
    Edge,
    EdgeId,
    IntersectionId,
    Junction,
    JunctionId,
    Lane,
    LaneConnection,
    LaneConnectionId,
    LaneId,
    Network,
    Phase,
    PhaseId,
    SignalGroup,
    SignalGroupId,
    SignalizedIntersection,
    SignalTiming,
    TurnDirection,
    VehicleType,
)
from traffic_lab.domain.state import (
    LaneState,
    RunCounters,
    SignalState,
    TrueState,
    VehicleState,
)
from traffic_lab.experiments.config import RunConfig
from traffic_lab.experiments.runner import RunSpec, run_one
from traffic_lab.experiments.spec import make_webster_controller
from traffic_lab.viz.trace import (
    TRACE_FORMAT_VERSION,
    TraceHeader,
    TraceReader,
    TraceWriter,
    extract_network_geometry,
)


def _minimal_network() -> Network:
    """Build a tiny valid Network object for testing."""
    j1 = Junction(
        id=JunctionId(0),
        incoming_lanes=(LaneId(0),),
        outgoing_lanes=(LaneId(1),),
        connections=(LaneConnectionId(0),),
        conflicts=ConflictMatrix(
            movements=(), matrix=__import__("numpy").zeros((0, 0), dtype=__import__("numpy").int8)
        ),
        position_xy=(100.0, 200.0),
    )
    edge0 = Edge(
        id=EdgeId(0),
        lanes=(LaneId(0),),
        from_junction=JunctionId(1),
        to_junction=JunctionId(0),
        length_m=100.0,
        opposite=None,
    )
    edge1 = Edge(
        id=EdgeId(1),
        lanes=(LaneId(1),),
        from_junction=JunctionId(0),
        to_junction=JunctionId(2),
        length_m=100.0,
        opposite=None,
    )
    lane0 = Lane(
        id=LaneId(0),
        edge=EdgeId(0),
        index=0,
        length_m=100.0,
        width_m=3.2,
        speed_limit_mps=13.89,
        successors=(LaneConnectionId(0),),
        adjacent_left=None,
        adjacent_right=None,
        allowed_types=frozenset({VehicleType.CAR}),
    )
    lane1 = Lane(
        id=LaneId(1),
        edge=EdgeId(1),
        index=0,
        length_m=100.0,
        width_m=3.2,
        speed_limit_mps=13.89,
        successors=(),
        adjacent_left=None,
        adjacent_right=None,
        allowed_types=frozenset({VehicleType.CAR}),
    )
    conn = LaneConnection(
        id=LaneConnectionId(0),
        from_lane=LaneId(0),
        to_lane=LaneId(1),
        via_junction=JunctionId(0),
        turn=TurnDirection.THROUGH,
    )
    sig = SignalizedIntersection(
        id=IntersectionId(0),
        junction=JunctionId(0),
        signal_groups=(
            SignalGroup(id=SignalGroupId(0), movements=()),
            SignalGroup(id=SignalGroupId(1), movements=()),
        ),
        phases=(
            Phase(id=PhaseId(0), green_groups=frozenset({SignalGroupId(0)})),
            Phase(id=PhaseId(1), green_groups=frozenset({SignalGroupId(1)})),
        ),
        timing=SignalTiming(min_green_s=5.0, max_green_s=30.0, yellow_s=3.0, all_red_s=2.0),
        controlled_connections=(LaneConnectionId(0),),
    )
    return Network(
        edges=(edge0, edge1),
        lanes=(lane0, lane1),
        connections=(conn,),
        junctions=(j1,),
        signalized_intersections=(sig,),
    )


def _sample_state(time_s: float = 1.0) -> TrueState:
    v = VehicleState(
        id=__import__("traffic_lab.domain.network", fromlist=["VehicleId"]).VehicleId(101),
        type=VehicleType.CAR,
        lane=LaneId(0),
        position_on_lane_m=45.5,
        position_xy=(55.5, 200.0),
        speed_mps=11.2,
        time_loss_s=2.0,
        waiting_time_s=0.0,
        stop_count=0,
        is_halting=False,
        halting_since_s=None,
    )
    lstate = LaneState(
        lane=LaneId(0),
        queue_count=0,
        queue_length_m=0.0,
        vehicle_count=1,
        mean_speed_mps=11.2,
    )
    sig_state = SignalState(
        intersection=IntersectionId(0),
        active_phase=PhaseId(0),
        phase_started_s=0.0,
        green_started_s=0.0,
        in_transition=False,
    )
    counters = RunCounters(
        teleports=0,
        insertion_failures=0,
        gridlock_detected=False,
        arrived_at_sink=0,
        arrived_mid_link=0,
        still_in_network=1,
    )
    return TrueState(
        time_s=time_s,
        vehicles=(v,),
        lanes=(lstate,),
        signals=(sig_state,),
        counters=counters,
    )


def test_extract_network_geometry() -> None:
    net = _minimal_network()
    geo = extract_network_geometry(net)
    assert "junctions" in geo
    assert len(geo["junctions"]) == 1
    assert geo["junctions"][0]["id"] == 0
    assert geo["junctions"][0]["x"] == 100.0
    assert geo["junctions"][0]["y"] == 200.0

    assert "lanes" in geo
    assert len(geo["lanes"]) == 2
    assert geo["lanes"][0]["id"] == 0
    assert geo["lanes"][0]["speed_limit_mps"] == 13.89


def test_trace_writer_and_reader_roundtrip_raw(tmp_path: Path) -> None:
    net = _minimal_network()
    header = TraceHeader(
        trace_version=TRACE_FORMAT_VERSION,
        run_id="test_run_raw",
        step_length_s=1.0,
        geometry=extract_network_geometry(net),
        measurement_window={"start_s": 60.0, "end_s": 360.0},
    )
    trace_path = tmp_path / "trace.jsonl"

    with TraceWriter(trace_path, header, compress=False) as writer:
        for s in range(1, 4):
            writer.write_step(step=s, time_s=float(s), state=_sample_state(float(s)))

    assert trace_path.exists()
    reader = TraceReader(trace_path)
    assert reader.header.run_id == "test_run_raw"
    assert reader.header.trace_version == "1.0"
    assert reader.header.geometry["junctions"][0]["id"] == 0

    frames = reader.read_all_frames()
    assert len(frames) == 3
    assert frames[0].step == 1
    assert frames[0].time_s == 1.0
    assert len(frames[0].vehicles) == 1
    assert frames[0].vehicles[0]["id"] == 101
    assert frames[0].vehicles[0]["x"] == 55.5
    # Reserved channels present as None
    assert frames[0].observations is None
    assert frames[0].estimates is None
    assert frames[0].decisions is None


def test_trace_writer_and_reader_roundtrip_compressed(tmp_path: Path) -> None:
    net = _minimal_network()
    header = TraceHeader(
        trace_version=TRACE_FORMAT_VERSION,
        run_id="test_run_gz",
        step_length_s=1.0,
        geometry=extract_network_geometry(net),
        measurement_window={"start_s": 60.0, "end_s": 360.0},
    )
    trace_path = tmp_path / "trace.jsonl.gz"

    with TraceWriter(trace_path, header, compress=True) as writer:
        writer.write_step(step=1, time_s=1.0, state=_sample_state(1.0))

    assert trace_path.exists()
    with TraceReader(trace_path) as reader:
        assert reader.header.run_id == "test_run_gz"
        frames = reader.read_all_frames()
        assert len(frames) == 1
        assert frames[0].vehicles[0]["speed_mps"] == 11.2


def test_trace_reader_version_validation(tmp_path: Path) -> None:
    trace_path = tmp_path / "bad_trace.jsonl"
    trace_path.write_text(json.dumps({"trace_version": "99.0", "run_id": "bad"}) + "\n")

    with pytest.raises(ValueError, match=r"Unsupported trace version: 99\.0"):
        TraceReader(trace_path)


def test_simulation_run_with_trace_recording(tmp_path: Path) -> None:
    """Verify run_one records trace when record_trace=True, and omits when False."""
    built = build_intersection(FOUR_WAY, tmp_path / "scenario")
    routes_file = one_flow_per_movement(
        built, tmp_path / "demand.rou.xml", 25.0, period_s=DEMAND_PERIOD_S
    )

    # 1. Run without trace recording
    out_no_trace = tmp_path / "out_no_trace"
    config_no_trace = RunConfig(
        name="no_trace",
        master_seed=42,
        warmup_s=5.0,
        measurement_s=10.0,
        cooldown_s=5.0,
        record_trace=False,
    )
    spec_no_trace = RunSpec(
        run_id="no_trace",
        net=built.net,
        routes=routes_file,
        network=built.network,
        controller_factory=functools.partial(make_webster_controller, demand_level=0.15),
        config=config_no_trace,
        seed_index=0,
        output_dir=out_no_trace,
        step_length_s=1.0,
        transport="libsumo",
    )
    in_fresh_process(run_one, spec_no_trace)
    assert not (out_no_trace / "trace.jsonl.gz").exists()
    assert not (out_no_trace / "trace.jsonl").exists()

    manifest_no_trace = json.loads((out_no_trace / "manifest.json").read_text())
    assert manifest_no_trace.get("trace_file") is None

    # 2. Run with trace recording
    out_with_trace = tmp_path / "out_with_trace"
    config_with_trace = RunConfig(
        name="with_trace",
        master_seed=42,
        warmup_s=5.0,
        measurement_s=10.0,
        cooldown_s=5.0,
        record_trace=True,
        trace_compressed=True,
    )
    spec_with_trace = RunSpec(
        run_id="with_trace",
        net=built.net,
        routes=routes_file,
        network=built.network,
        controller_factory=functools.partial(make_webster_controller, demand_level=0.15),
        config=config_with_trace,
        seed_index=0,
        output_dir=out_with_trace,
        step_length_s=1.0,
        transport="libsumo",
    )
    in_fresh_process(run_one, spec_with_trace)
    trace_file = out_with_trace / "trace.jsonl.gz"
    assert trace_file.exists()
    assert trace_file.stat().st_size > 0

    manifest_with_trace = json.loads((out_with_trace / "manifest.json").read_text())
    assert manifest_with_trace["trace_file"] == "trace.jsonl.gz"

    # Verify trace reader can read the recorded simulation
    with TraceReader(trace_file) as reader:
        assert reader.header.run_id == "with_trace"
        assert len(reader.header.geometry["junctions"]) > 0
        frames = reader.read_all_frames()
        assert len(frames) == 20  # 5 + 10 + 5 steps
        assert frames[0].time_s == 1.0
        assert frames[-1].time_s == 20.0
