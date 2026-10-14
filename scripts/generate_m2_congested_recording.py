"""Generate M2 Congested Run Recording (M2 Exit Criterion).

Runs a simulation under near-capacity demand with record_trace=True,
renders the 2D visual replay with research overlays, and exports
an animated GIF to research/M2_congested_run.gif.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from tests.experiments.support import in_fresh_process
from tests.generated_scenario import (
    FOUR_WAY,
    build_intersection,
    one_flow_per_movement,
)
from traffic_lab.experiments.config import RunConfig
from traffic_lab.experiments.runner import RunSpec, run_one
from traffic_lab.experiments.spec import make_max_pressure_controller
from traffic_lab.viz.renderer import RenderConfig, ReplayRenderer
from traffic_lab.viz.trace import TraceReader


def main() -> None:
    exp_dir = Path("research/m2_replay_experiment")
    if exp_dir.exists():
        shutil.rmtree(exp_dir)
    exp_dir.mkdir(parents=True, exist_ok=True)

    print("Building intersection scenario...")
    built = build_intersection(FOUR_WAY, exp_dir / "scenario")
    routes_file = one_flow_per_movement(
        built, exp_dir / "demand.rou.xml", end_s=80.0, period_s=28.0
    )

    out_run = exp_dir / "congested_run"
    config = RunConfig(
        name="m2_congested_run",
        master_seed=42,
        warmup_s=5.0,
        measurement_s=70.0,
        cooldown_s=5.0,
        record_trace=True,
        trace_compressed=True,
    )
    spec = RunSpec(
        run_id="m2_congested_run",
        net=built.net,
        routes=routes_file,
        network=built.network,
        controller_factory=make_max_pressure_controller,
        config=config,
        seed_index=0,
        output_dir=out_run,
        step_length_s=1.0,
        transport="libsumo",
    )

    print("Executing simulation with trace recording enabled...")
    in_fresh_process(run_one, spec)

    trace_file = out_run / "trace.jsonl.gz"
    assert trace_file.exists(), f"Trace file not found at {trace_file}"
    print(f"Recorded trace: {trace_file} ({trace_file.stat().st_size / 1024:.1f} KB)")

    gif_out = Path("research/M2_congested_run.gif")
    print(f"Rendering 2D replay with research overlays to {gif_out}...")
    with TraceReader(trace_file) as reader:
        renderer = ReplayRenderer(reader, config=RenderConfig(width_px=600, height_px=600))
        renderer.export_gif(gif_out, fps=8, step_stride=1)

    print(f"GIF exported: {gif_out} ({gif_out.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
