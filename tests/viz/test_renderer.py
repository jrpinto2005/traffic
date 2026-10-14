"""Tests for ReplayRenderer, 2D replay engine, and GIF export (D-009, D-030, T2.3)."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

from traffic_lab.viz.renderer import RenderConfig, ReplayRenderer
from traffic_lab.viz.trace import (
    TRACE_FORMAT_VERSION,
    TraceHeader,
    TraceReader,
    TraceWriter,
)


def _create_synthetic_trace(trace_path: Path, num_steps: int = 5) -> None:
    header = TraceHeader(
        trace_version=TRACE_FORMAT_VERSION,
        run_id="synth_run",
        step_length_s=1.0,
        geometry={
            "junctions": [{"id": 0, "x": 0.0, "y": 0.0}],
            "lanes": [],
            "edges": [],
        },
        measurement_window={"start_s": 0.0, "end_s": float(num_steps)},
    )
    with TraceWriter(trace_path, header, compress=False) as writer:
        for s in range(1, num_steps + 1):
            writer.write_step(
                step=s,
                time_s=float(s),
                state=type(
                    "MockState",
                    (),
                    {
                        "vehicles": [
                            type(
                                "MockVehicle",
                                (),
                                {
                                    "id": 1,
                                    "type": "car",
                                    "lane": 0,
                                    "position_xy": (float(s * 5), 0.0),
                                    "speed_mps": 5.0,
                                    "position_on_lane_m": float(s * 5),
                                    "is_halting": False,
                                },
                            )()
                        ],
                        "signals": [
                            type(
                                "MockSignal",
                                (),
                                {
                                    "intersection": 0,
                                    "active_phase": 0,
                                    "green_started_s": 0.0,
                                    "in_transition": False,
                                },
                            )()
                        ],
                        "lanes": [],
                        "counters": type(
                            "MockCounters",
                            (),
                            {
                                "arrived_at_sink": 0,
                                "arrived_mid_link": 0,
                                "still_in_network": 1,
                                "teleports": 0,
                                "insertion_failures": 0,
                            },
                        )(),
                    },
                )(),
            )


def test_renderer_frame_rasterization(tmp_path: Path) -> None:
    trace_path = tmp_path / "test.jsonl"
    _create_synthetic_trace(trace_path, num_steps=3)

    reader = TraceReader(trace_path)
    renderer = ReplayRenderer(reader, RenderConfig(width_px=400, height_px=400, dpi=100))

    frames = reader.read_all_frames()
    assert len(frames) == 3

    img = renderer.render_frame(frames[0])
    assert isinstance(img, Image.Image)
    assert img.size == (400, 400)
    assert img.mode == "RGB"


def test_renderer_gif_export(tmp_path: Path) -> None:
    trace_path = tmp_path / "test_gif.jsonl"
    _create_synthetic_trace(trace_path, num_steps=6)

    reader = TraceReader(trace_path)
    renderer = ReplayRenderer(reader, RenderConfig(width_px=400, height_px=400, dpi=100))

    gif_out = tmp_path / "replay.gif"
    out = renderer.export_gif(gif_out, start_step=1, end_step=5, fps=5)
    assert out.exists()
    assert out.stat().st_size > 0

    with Image.open(gif_out) as loaded_gif:
        assert getattr(loaded_gif, "is_animated", False)
        assert getattr(loaded_gif, "n_frames", 1) == 5


def test_renderer_runs_without_sumo_imported() -> None:
    """Invariant check: Renderer has zero dependence on SUMO runtime."""
    # Ensure neither traci nor libsumo are imported in the renderer module
    renderer_modules = sys.modules["traffic_lab.viz.renderer"].__dict__
    assert "traci" not in renderer_modules
    assert "libsumo" not in renderer_modules
    assert "sumolib" not in renderer_modules
