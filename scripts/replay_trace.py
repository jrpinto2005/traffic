"""Replay and export simulation traces to video or animated GIF (D-009, D-030, M2).

Usage:
    python scripts/replay_trace.py <trace_file> [--gif <output.gif>] [--fps 10] [--stride 1]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from traffic_lab.viz.renderer import RenderConfig, ReplayRenderer
from traffic_lab.viz.trace import TraceReader


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay and export simulation trace files.")
    parser.add_argument("trace", type=Path, help="Path to trace file (.jsonl or .jsonl.gz)")
    parser.add_argument("--gif", type=Path, default=None, help="Output animated GIF path")
    parser.add_argument("--fps", type=int, default=10, help="Frames per second (default: 10)")
    parser.add_argument("--stride", type=int, default=1, help="Step stride sampling (default: 1)")
    parser.add_argument(
        "--width", type=int, default=800, help="Image width in pixels (default: 800)"
    )
    parser.add_argument(
        "--height", type=int, default=800, help="Image height in pixels (default: 800)"
    )
    args = parser.parse_args()

    print(f"Loading trace: {args.trace}")
    with TraceReader(args.trace) as reader:
        config = RenderConfig(width_px=args.width, height_px=args.height)
        renderer = ReplayRenderer(reader, config=config)

        if args.gif:
            print(f"Exporting animated GIF to {args.gif} (fps={args.fps}, stride={args.stride})...")
            out = renderer.export_gif(args.gif, fps=args.fps, step_stride=args.stride)
            print(f"Export complete: {out} ({out.stat().st_size / 1024:.1f} KB)")
        else:
            frames = reader.read_all_frames()
            print(
                f"Trace contains {len(frames)} frames. "
                "Specify --gif <path.gif> to render animation."
            )


if __name__ == "__main__":
    main()
