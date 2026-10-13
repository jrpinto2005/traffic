"""Trace format, streaming writer, and reader (D-030, M2).

Decouples replay visualization from the SUMO microsimulator (D-009, D-030).
Records static geometry in a metadata header and per-step state frames
(vehicles, signals, queues, metrics) in compressed or raw JSON Lines.
Reserves channels for observations, estimated states, and controller decisions (M3+).
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import IO, Any

from traffic_lab.domain.network import Network
from traffic_lab.domain.state import TrueState

TRACE_FORMAT_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class TraceHeader:
    """Header line (line 0) of a trace file."""

    trace_version: str
    run_id: str
    step_length_s: float
    geometry: dict[str, Any]
    measurement_window: dict[str, float]


@dataclass(frozen=True, slots=True)
class VehicleFrameItem:
    """Per-vehicle dynamic state recorded in a step frame."""

    id: int
    type: str
    lane: int
    x: float
    y: float
    speed_mps: float
    pos_m: float
    is_halting: bool


@dataclass(frozen=True, slots=True)
class SignalFrameItem:
    """Per-intersection signal state recorded in a step frame."""

    intersection: int
    active_phase: int
    green_started_s: float | None
    in_transition: bool


@dataclass(frozen=True, slots=True)
class StepFrame:
    """One simulation step frame (lines 1..N) in a trace file."""

    step: int
    time_s: float
    vehicles: list[dict[str, Any]]
    signals: list[dict[str, Any]]
    queues: dict[str, dict[str, Any]]
    metrics: dict[str, Any]
    observations: dict[str, Any] | None = None
    estimates: dict[str, Any] | None = None
    decisions: dict[str, Any] | None = None


def extract_network_geometry(network: Network) -> dict[str, Any]:
    """Extract static junction, lane, and edge coordinates for 2D replay."""
    return {
        "junctions": [
            {
                "id": int(j.id),
                "x": round(float(j.position_xy[0]), 3),
                "y": round(float(j.position_xy[1]), 3),
            }
            for j in network.junctions
        ],
        "edges": [
            {
                "id": int(e.id),
                "from_junction": int(e.from_junction),
                "to_junction": int(e.to_junction),
                "length_m": round(float(e.length_m), 3),
            }
            for e in network.edges
        ],
        "lanes": [
            {
                "id": int(lane.id),
                "edge": int(lane.edge),
                "index": int(lane.index),
                "length_m": round(float(lane.length_m), 3),
                "width_m": round(float(lane.width_m), 3),
                "speed_limit_mps": round(float(lane.speed_limit_mps), 3),
                "successors": [int(s) for s in lane.successors],
            }
            for lane in network.lanes
        ],
    }


class TraceWriter:
    """Streaming writer for trace files (.jsonl or .jsonl.gz)."""

    def __init__(self, target_path: Path, header: TraceHeader, compress: bool = True) -> None:
        self.target_path = target_path
        self.compress = compress
        target_path.parent.mkdir(parents=True, exist_ok=True)

        self._fh: IO[str]
        if compress or str(target_path).endswith(".gz"):
            self._fh = gzip.open(target_path, "wt", encoding="utf-8")  # noqa: SIM115
        else:
            self._fh = open(target_path, "w", encoding="utf-8")  # noqa: SIM115

        # Write header line
        header_dict = asdict(header)
        self._fh.write(json.dumps(header_dict) + "\n")
        self._closed = False

    def write_step(
        self,
        step: int,
        time_s: float,
        state: TrueState,
        observations: dict[str, Any] | None = None,
        estimates: dict[str, Any] | None = None,
        decisions: dict[str, Any] | None = None,
    ) -> None:
        """Write dynamic step frame directly from TrueState."""
        if self._closed:
            raise RuntimeError("Cannot write to closed TraceWriter")

        vehicles = [
            {
                "id": int(v.id),
                "type": str(v.type),
                "lane": int(v.lane),
                "x": round(float(v.position_xy[0]), 3),
                "y": round(float(v.position_xy[1]), 3),
                "speed_mps": round(float(v.speed_mps), 3),
                "pos_m": round(float(v.position_on_lane_m), 3),
                "is_halting": bool(v.is_halting),
            }
            for v in state.vehicles
        ]

        signals = [
            {
                "intersection": int(s.intersection),
                "active_phase": int(s.active_phase),
                "green_started_s": s.green_started_s,
                "in_transition": bool(s.in_transition),
            }
            for s in state.signals
        ]

        queues = {
            str(int(lane.lane)): {
                "queue_count": int(lane.queue_count),
                "vehicle_count": int(lane.vehicle_count),
                "mean_speed_mps": round(float(lane.mean_speed_mps), 3),
            }
            for lane in state.lanes
        }

        metrics = {
            "arrived_at_sink": int(state.counters.arrived_at_sink),
            "arrived_mid_link": int(state.counters.arrived_mid_link),
            "still_in_network": int(state.counters.still_in_network),
            "teleports": int(state.counters.teleports),
            "insertion_failures": int(state.counters.insertion_failures),
        }

        frame = {
            "step": step,
            "time_s": round(float(time_s), 3),
            "vehicles": vehicles,
            "signals": signals,
            "queues": queues,
            "metrics": metrics,
            "observations": observations,
            "estimates": estimates,
            "decisions": decisions,
        }
        self._fh.write(json.dumps(frame) + "\n")

    def close(self) -> None:
        """Flush and close file handle."""
        if not self._closed:
            self._fh.flush()
            self._fh.close()
            self._closed = True

    def __enter__(self) -> TraceWriter:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class TraceReader:
    """Reader and parser for recorded trace files."""

    def __init__(self, trace_path: Path) -> None:
        if not trace_path.exists():
            raise FileNotFoundError(f"Trace file not found: {trace_path}")
        self.trace_path = trace_path

        self._fh: IO[str]
        if str(trace_path).endswith(".gz"):
            self._fh = gzip.open(trace_path, "rt", encoding="utf-8")  # noqa: SIM115
        else:
            self._fh = open(trace_path, encoding="utf-8")  # noqa: SIM115

        first_line = self._fh.readline()
        if not first_line:
            raise ValueError(f"Trace file is empty: {trace_path}")

        raw_header = json.loads(first_line)
        if "trace_version" not in raw_header:
            raise ValueError("Trace missing trace_version in header")
        if raw_header["trace_version"] != TRACE_FORMAT_VERSION:
            raise ValueError(
                f"Unsupported trace version: {raw_header['trace_version']} "
                f"(expected {TRACE_FORMAT_VERSION})"
            )

        self.header = TraceHeader(
            trace_version=raw_header["trace_version"],
            run_id=raw_header["run_id"],
            step_length_s=float(raw_header["step_length_s"]),
            geometry=raw_header["geometry"],
            measurement_window=raw_header["measurement_window"],
        )

    def iter_frames(self) -> Any:
        """Yield StepFrames from trace file."""
        for line in self._fh:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            yield StepFrame(
                step=raw["step"],
                time_s=raw["time_s"],
                vehicles=raw["vehicles"],
                signals=raw["signals"],
                queues=raw["queues"],
                metrics=raw["metrics"],
                observations=raw.get("observations"),
                estimates=raw.get("estimates"),
                decisions=raw.get("decisions"),
            )

    def read_all_frames(self) -> list[StepFrame]:
        """Read all frames into memory."""
        return list(self.iter_frames())

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> TraceReader:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
