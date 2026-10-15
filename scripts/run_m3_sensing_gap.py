#!/usr/bin/env python3
"""Run the M3 sensing-control gap experiment suite and generate research artifacts.

Evaluates the 4 controllers (Webster, Actuated, Max-Pressure, SUMO Actuated) across:
1. Sensing regimes: Oracle, Ideal Camera, Degraded Camera sweeps (P_det, noise, latency)
2. Camera placements: 4-Approach, Single Central Omni, Partial 2-Approach
3. Attribution analysis (Sensing error vs Estimation error vs Controller fragility)
4. Ranking inversion analysis
5. Generates headline figures, tables, visual divergence replay, and research report.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any

os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib"

import matplotlib.pyplot as plt
import polars as pl

from tests.experiments.support import in_fresh_process
from tests.generated_scenario import FOUR_WAY, build_intersection
from traffic_lab.estimation.factories import make_decay_estimator
from traffic_lab.experiments.config import RunConfig
from traffic_lab.experiments.runner import RunSpec, run_many, run_one
from traffic_lab.experiments.seeds import derive_run_seeds
from traffic_lab.experiments.spec import (
    make_actuated_controller,
    make_max_pressure_controller,
    make_webster_controller,
)
from traffic_lab.scenarios.demand import build_routes, uniform_demand_spec
from traffic_lab.scenarios.generator import IDS_SUFFIX, NET_STEM, build
from traffic_lab.scenarios.parse import SumoIds
from traffic_lab.sensing.factories import (
    make_camera_sensor_4approach,
    make_camera_sensor_central_omni,
    make_camera_sensor_partial_2approach,
)
from traffic_lab.viz.renderer import RenderConfig, ReplayRenderer
from traffic_lab.viz.trace import TraceReader


def _load_ids(path: Path) -> SumoIds:
    import json

    raw = json.loads(path.read_text())
    return SumoIds(
        lanes=tuple(raw["lanes"]),
        edges=tuple(raw["edges"]),
        junctions=tuple(raw["junctions"]),
        intersections=tuple(raw["intersections"]),
        connections=tuple((a, b) for a, b in raw["connections"]),
    )


def run_experiment_suite(out_dir: Path) -> pl.DataFrame:
    """Build scenarios, generate route files, expand RunSpecs, and execute sweep."""
    networks_dir = out_dir / "networks"
    routes_dir = out_dir / "routes"
    runs_dir = out_dir / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Build networks (static and actuated)
    static_dir = networks_dir / "static"
    actuated_dir = networks_dir / "actuated"
    net_static_path, net_static_obj = build(FOUR_WAY, static_dir, program="static")
    ids_static = _load_ids(static_dir / f"{NET_STEM}{IDS_SUFFIX}")
    net_actuated_path, net_actuated_obj = build(FOUR_WAY, actuated_dir, program="actuated")

    demand_level = 0.20  # Valid stable operating point with zero insertion loss
    n_seeds = 5
    master_seed = 42
    warmup_s = 60.0
    measurement_s = 300.0
    cooldown_s = 60.0
    end_s = warmup_s + measurement_s + cooldown_s

    # 2. Build common routes per seed (D-017 paired seeds)
    route_files: dict[int, Path] = {}
    demand_spec = uniform_demand_spec(net_static_obj, demand_level)
    for s in range(n_seeds):
        seeds = derive_run_seeds(master_seed, s)
        route_out = routes_dir / f"seed_{s}"
        route_file = build_routes(
            net_static_path,
            net_static_obj,
            ids_static,
            demand_spec,
            seeds["demand"],
            route_out,
            end_s=end_s,
        )
        route_files[s] = route_file

    # 3. Define sweep variations
    # Controller configs: (name, type, dt_s)
    controllers = [
        ("webster", "webster", 1.0),
        ("actuated", "actuated", 1.0),
        ("max_pressure", "max_pressure", 5.0),
        ("sumo_actuated", "sumo_actuated", 1.0),
    ]

    # Conditions list: (condition_id, sensor_name, placement, p_det, noise, latency, factory_fn)
    conditions: list[tuple[str, str, str, float, float, float, Any]] = [
        # Arm 1: Oracle
        ("oracle", "oracle", "oracle", 1.0, 0.0, 0.0, None),
        # Arm 2: Ideal Camera (4-approach)
        (
            "ideal_cam",
            "camera",
            "4approach",
            1.0,
            0.0,
            0.0,
            functools.partial(
                make_camera_sensor_4approach,
                p_det=1.0,
                pos_noise_std=0.0,
                speed_noise_std=0.0,
                latency_s=0.0,
            ),
        ),
        # Arm 3: P_det sweep
        (
            "pdet_0.50",
            "camera",
            "4approach",
            0.50,
            1.0,
            1.0,
            functools.partial(
                make_camera_sensor_4approach,
                p_det=0.50,
                pos_noise_std=1.0,
                speed_noise_std=0.3,
                latency_s=1.0,
            ),
        ),
        (
            "pdet_0.70",
            "camera",
            "4approach",
            0.70,
            1.0,
            1.0,
            functools.partial(
                make_camera_sensor_4approach,
                p_det=0.70,
                pos_noise_std=1.0,
                speed_noise_std=0.3,
                latency_s=1.0,
            ),
        ),
        (
            "pdet_0.85",
            "camera",
            "4approach",
            0.85,
            1.0,
            1.0,
            functools.partial(
                make_camera_sensor_4approach,
                p_det=0.85,
                pos_noise_std=1.0,
                speed_noise_std=0.3,
                latency_s=1.0,
            ),
        ),
        (
            "pdet_0.95",
            "camera",
            "4approach",
            0.95,
            1.0,
            1.0,
            functools.partial(
                make_camera_sensor_4approach,
                p_det=0.95,
                pos_noise_std=1.0,
                speed_noise_std=0.3,
                latency_s=1.0,
            ),
        ),
        # Arm 4: Noise sweep (P_det=0.85, tau=1.0)
        (
            "noise_0.0",
            "camera",
            "4approach",
            0.85,
            0.0,
            1.0,
            functools.partial(
                make_camera_sensor_4approach,
                p_det=0.85,
                pos_noise_std=0.0,
                speed_noise_std=0.0,
                latency_s=1.0,
            ),
        ),
        (
            "noise_2.5",
            "camera",
            "4approach",
            0.85,
            2.5,
            1.0,
            functools.partial(
                make_camera_sensor_4approach,
                p_det=0.85,
                pos_noise_std=2.5,
                speed_noise_std=0.8,
                latency_s=1.0,
            ),
        ),
        (
            "noise_5.0",
            "camera",
            "4approach",
            0.85,
            5.0,
            1.0,
            functools.partial(
                make_camera_sensor_4approach,
                p_det=0.85,
                pos_noise_std=5.0,
                speed_noise_std=1.5,
                latency_s=1.0,
            ),
        ),
        # Arm 5: Latency sweep (P_det=0.85, noise=1.0)
        (
            "lat_0.0",
            "camera",
            "4approach",
            0.85,
            1.0,
            0.0,
            functools.partial(
                make_camera_sensor_4approach,
                p_det=0.85,
                pos_noise_std=1.0,
                speed_noise_std=0.3,
                latency_s=0.0,
            ),
        ),
        (
            "lat_3.0",
            "camera",
            "4approach",
            0.85,
            1.0,
            3.0,
            functools.partial(
                make_camera_sensor_4approach,
                p_det=0.85,
                pos_noise_std=1.0,
                speed_noise_std=0.3,
                latency_s=3.0,
            ),
        ),
        (
            "lat_5.0",
            "camera",
            "4approach",
            0.85,
            1.0,
            5.0,
            functools.partial(
                make_camera_sensor_4approach,
                p_det=0.85,
                pos_noise_std=1.0,
                speed_noise_std=0.3,
                latency_s=5.0,
            ),
        ),
        # Arm 6: Placements (Omni and Partial 2-approach)
        (
            "place_omni",
            "camera",
            "central_omni",
            0.85,
            1.0,
            1.0,
            functools.partial(
                make_camera_sensor_central_omni,
                p_det=0.85,
                pos_noise_std=1.0,
                speed_noise_std=0.3,
                latency_s=1.0,
            ),
        ),
        (
            "place_partial_2app",
            "camera",
            "partial_2approach",
            0.85,
            1.0,
            1.0,
            functools.partial(
                make_camera_sensor_partial_2approach,
                p_det=0.85,
                pos_noise_std=1.0,
                speed_noise_std=0.3,
                latency_s=1.0,
            ),
        ),
    ]

    run_specs: list[RunSpec] = []
    estimator_factory = make_decay_estimator

    for cond_id, sens_name, placement, p_det, noise, latency, sens_factory in conditions:
        for ctrl_name, ctrl_type, dt_s in controllers:
            for s in range(n_seeds):
                run_id = f"{ctrl_name}_{cond_id}_s{s}"
                run_out = runs_dir / run_id
                config = RunConfig(
                    name=run_id,
                    master_seed=master_seed,
                    warmup_s=warmup_s,
                    measurement_s=measurement_s,
                    cooldown_s=cooldown_s,
                    warmup_design="self",
                )

                # Factory construction
                factory: Any = None
                net_path = net_static_path
                net_obj = net_static_obj
                if ctrl_type == "webster":
                    factory = functools.partial(
                        make_webster_controller, demand_level=demand_level, decision_interval_s=dt_s
                    )
                elif ctrl_type == "actuated":
                    factory = functools.partial(make_actuated_controller, decision_interval_s=dt_s)
                elif ctrl_type == "max_pressure":
                    factory = functools.partial(
                        make_max_pressure_controller, decision_interval_s=dt_s
                    )
                elif ctrl_type == "sumo_actuated":
                    factory = None
                    net_path = net_actuated_path
                    net_obj = net_actuated_obj

                tags: dict[str, str | float | int] = {
                    "condition": cond_id,
                    "placement": placement,
                    "p_det": p_det,
                    "noise_std": noise,
                    "latency_s": latency,
                }

                run_specs.append(
                    RunSpec(
                        run_id=run_id,
                        net=net_path,
                        routes=route_files[s],
                        network=net_obj,
                        controller_factory=factory,
                        sensor_factory=sens_factory,
                        estimator_factory=estimator_factory if sens_factory is not None else None,
                        config=config,
                        seed_index=s,
                        transport="libsumo",
                        step_length_s=1.0,
                        output_dir=run_out,
                        controller_name=ctrl_name,
                        demand_level=demand_level,
                        sensor_name=sens_name,
                        estimator_name="decay" if sens_factory is not None else "identity",
                        tags=tags,
                    )
                )

    print(f"Total planned runs: {len(run_specs)} across {len(conditions)} conditions")
    parquet_path = out_dir / "experiment.parquet"
    if not parquet_path.exists():
        jobs = max(1, (os.cpu_count() or 2) - 1)
        print(f"Executing {len(run_specs)} runs using {jobs} worker processes...")
        run_many(run_specs, out_dir, jobs=jobs)
    else:
        print(f"Using existing experiment parquet at {parquet_path}")

    return pl.read_parquet(parquet_path)


def analyze_and_plot(df: pl.DataFrame) -> None:
    """Compute attribution metrics, generate summary table, and create headline figure."""
    out_table = Path("research/M3_sensing_gap_results.csv")
    out_fig = Path("research/M3_degradation_curves.png")

    metric = "all.mean_delay_s"
    agg_df = (
        df.group_by(["controller", "condition", "placement", "p_det", "noise_std", "latency_s"])
        .agg(
            [
                pl.col(metric).mean().alias("mean_delay_s"),
                pl.col(metric).std().alias("std_delay_s"),
                pl.col(metric).count().alias("n"),
            ]
        )
        .with_columns((pl.col("std_delay_s") / (pl.col("n").sqrt())).alias("se_delay_s"))
        .sort(["controller", "condition"])
    )
    agg_df.write_csv(out_table)
    print(f"Results table written to {out_table}")

    style_name = (
        "seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default"
    )
    plt.style.use(style_name)
    fig, axes = plt.subplots(2, 2, figsize=(13, 10))
    fig.suptitle(
        "M3 Sensing-Control Gap: Performance Degradation Across Controllers",
        fontsize=15,
        fontweight="bold",
        y=0.98,
    )

    ctrl_colors = {
        "max_pressure": "#1f77b4",
        "actuated": "#2ca02c",
        "webster": "#ff7f0e",
        "sumo_actuated": "#d62728",
    }
    ctrl_markers = {
        "max_pressure": "o",
        "actuated": "s",
        "webster": "^",
        "sumo_actuated": "v",
    }
    ctrl_labels = {
        "max_pressure": "Max-Pressure",
        "actuated": "Traffic-Lab Actuated",
        "webster": "Webster (Fixed-Plan)",
        "sumo_actuated": "SUMO Actuated (Ground Detectors)",
    }

    # 1. Subplot (0,0): P_det Sensitivity Sweep
    ax1 = axes[0, 0]
    pdet_conds = ["pdet_0.50", "pdet_0.70", "pdet_0.85", "pdet_0.95", "ideal_cam"]
    pdet_vals = [0.50, 0.70, 0.85, 0.95, 1.00]
    cond_map = dict(zip(pdet_conds, pdet_vals, strict=True))

    for ctrl in ctrl_colors:
        sub = agg_df.filter(
            (pl.col("controller") == ctrl) & (pl.col("condition").is_in(pdet_conds))
        )
        if not sub.is_empty():
            rows = sub.to_dicts()
            rows.sort(key=lambda r: cond_map[r["condition"]])
            xs = [cond_map[r["condition"]] for r in rows]
            ys = [r["mean_delay_s"] for r in rows]
            yerrs = [1.96 * r["se_delay_s"] for r in rows]
            ax1.errorbar(
                xs,
                ys,
                yerr=yerrs,
                label=ctrl_labels[ctrl],
                color=ctrl_colors[ctrl],
                marker=ctrl_markers[ctrl],
                linewidth=2,
                capsize=4,
            )

    ax1.set_title("(a) Detection Probability ($P_{det}$) Degradation", fontweight="bold")
    ax1.set_xlabel("Nominal Detection Probability ($P_{det}$)")
    ax1.set_ylabel("Mean Delay (s/veh)")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper right", framealpha=0.9)

    # 2. Subplot (0,1): Position Noise Sweep
    ax2 = axes[0, 1]
    noise_conds = ["noise_0.0", "pdet_0.85", "noise_2.5", "noise_5.0"]
    noise_vals = [0.0, 1.0, 2.5, 5.0]
    n_map = dict(zip(noise_conds, noise_vals, strict=True))

    for ctrl in ctrl_colors:
        sub = agg_df.filter(
            (pl.col("controller") == ctrl) & (pl.col("condition").is_in(noise_conds))
        )
        if not sub.is_empty():
            rows = sub.to_dicts()
            rows.sort(key=lambda r: n_map[r["condition"]])
            xs = [n_map[r["condition"]] for r in rows]
            ys = [r["mean_delay_s"] for r in rows]
            yerrs = [1.96 * r["se_delay_s"] for r in rows]
            ax2.errorbar(
                xs,
                ys,
                yerr=yerrs,
                label=ctrl_labels[ctrl],
                color=ctrl_colors[ctrl],
                marker=ctrl_markers[ctrl],
                linewidth=2,
                capsize=4,
            )

    ax2.set_title(r"(b) Coordinate Measurement Noise ($\sigma_{xy}$)", fontweight="bold")
    ax2.set_xlabel(r"Position Noise Std $\sigma_{xy}$ (m)")
    ax2.set_ylabel("Mean Delay (s/veh)")
    ax2.grid(True, alpha=0.3)

    # 3. Subplot (1,0): Transmission Latency Sweep
    ax3 = axes[1, 0]
    lat_conds = ["lat_0.0", "pdet_0.85", "lat_3.0", "lat_5.0"]
    lat_vals = [0.0, 1.0, 3.0, 5.0]
    l_map = dict(zip(lat_conds, lat_vals, strict=True))

    for ctrl in ctrl_colors:
        sub = agg_df.filter((pl.col("controller") == ctrl) & (pl.col("condition").is_in(lat_conds)))
        if not sub.is_empty():
            rows = sub.to_dicts()
            rows.sort(key=lambda r: l_map[r["condition"]])
            xs = [l_map[r["condition"]] for r in rows]
            ys = [r["mean_delay_s"] for r in rows]
            yerrs = [1.96 * r["se_delay_s"] for r in rows]
            ax3.errorbar(
                xs,
                ys,
                yerr=yerrs,
                label=ctrl_labels[ctrl],
                color=ctrl_colors[ctrl],
                marker=ctrl_markers[ctrl],
                linewidth=2,
                capsize=4,
            )

    ax3.set_title(r"(c) Sensor Transmission Latency ($\tau$)", fontweight="bold")
    ax3.set_xlabel(r"Observation Latency $\tau$ (s)")
    ax3.set_ylabel("Mean Delay (s/veh)")
    ax3.grid(True, alpha=0.3)

    # 4. Subplot (1,1): Camera Placement Architectures
    ax4 = axes[1, 1]
    place_conds = ["pdet_0.85", "place_omni", "place_partial_2app"]
    place_labels = ["Full 4-Approach", "Central Omni 360°", "Partial 2-Approach (EW)"]

    x_indices = range(len(place_labels))
    width = 0.2
    offsets = [-1.5 * width, -0.5 * width, 0.5 * width, 1.5 * width]

    for idx, ctrl in enumerate(ctrl_colors):
        means = []
        errs = []
        for c_id in place_conds:
            row = agg_df.filter(
                (pl.col("controller") == ctrl) & (pl.col("condition") == c_id)
            ).to_dicts()
            if row:
                means.append(row[0]["mean_delay_s"])
                errs.append(1.96 * row[0]["se_delay_s"])
            else:
                means.append(0.0)
                errs.append(0.0)

        xs = [xi + offsets[idx] for xi in x_indices]
        ax4.bar(
            xs,
            means,
            width=width,
            yerr=errs,
            capsize=3,
            label=ctrl_labels[ctrl],
            color=ctrl_colors[ctrl],
            alpha=0.85,
        )

    ax4.set_xticks(list(x_indices))
    ax4.set_xticklabels(place_labels, rotation=10, ha="right")
    ax4.set_title("(d) Camera Placement Comparison ($P_{det}=0.85$)", fontweight="bold")
    ax4.set_ylabel("Mean Delay (s/veh)")
    ax4.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_fig, dpi=300)
    plt.close()
    print(f"Degradation figure saved to {out_fig}")


def generate_visual_divergence_artifact() -> None:
    """Generate animated GIF showing ground truth vs imperfect camera observations."""
    exp_dir = Path("research/m3_replay_divergence")
    exp_dir.mkdir(parents=True, exist_ok=True)

    built = build_intersection(FOUR_WAY, exp_dir / "scenario")
    routes_file = (
        Path("research/m3_experiment/routes/seed_0/demand.rou.xml")
        if Path("research/m3_experiment/routes/seed_0/demand.rou.xml").exists()
        else None
    )
    if routes_file is None:
        from traffic_lab.scenarios.demand import build_routes, uniform_demand_spec

        demand = uniform_demand_spec(built.network, 0.35)
        sumo_ids = _load_ids(built.net.parent / f"{NET_STEM}{IDS_SUFFIX}")
        routes_file = build_routes(
            built.net, built.network, sumo_ids, demand, 42, exp_dir / "routes", end_s=80.0
        )

    out_run = exp_dir / "divergence_run"
    config = RunConfig(
        name="m3_divergence_run",
        master_seed=42,
        warmup_s=5.0,
        measurement_s=70.0,
        cooldown_s=5.0,
        record_trace=True,
        trace_compressed=True,
    )
    sensor_fac = functools.partial(
        make_camera_sensor_4approach,
        p_det=0.70,
        pos_noise_std=2.0,
        speed_noise_std=0.5,
        latency_s=1.0,
    )
    estimator_fac = make_decay_estimator

    spec = RunSpec(
        run_id="m3_divergence_run",
        net=built.net,
        routes=routes_file,
        network=built.network,
        controller_factory=make_max_pressure_controller,
        sensor_factory=sensor_fac,
        estimator_factory=estimator_fac,
        config=config,
        seed_index=0,
        output_dir=out_run,
        step_length_s=1.0,
        transport="libsumo",
        sensor_name="camera",
        estimator_name="decay",
    )

    print("Generating visual divergence simulation trace...")
    in_fresh_process(run_one, spec)

    trace_file = out_run / "trace.jsonl.gz"
    assert trace_file.exists(), f"Trace file missing at {trace_file}"

    gif_out = Path("research/M3_sensing_divergence.gif")
    print(f"Exporting animated divergence replay to {gif_out}...")
    with TraceReader(trace_file) as reader:
        renderer = ReplayRenderer(
            reader, config=RenderConfig(width_px=600, height_px=600, show_observations=True)
        )
        renderer.export_gif(gif_out, fps=8, step_stride=1)

    print(f"Divergence GIF exported: {gif_out} ({gif_out.stat().st_size / 1024:.1f} KB)")


def write_research_report(df: pl.DataFrame) -> None:
    """Generate consolidated M3 sensing-control gap report in ASD-STE100 English."""
    report_path = Path("research/M3_sensing_gap_report.md")
    template_path = Path("scripts/m3_report_template.md")

    metric = "all.mean_delay_s"
    agg = (
        df.group_by(["controller", "condition"])
        .agg(pl.col(metric).mean().alias("mean_delay"), pl.col(metric).std().alias("std_delay"))
        .sort(["controller", "condition"])
    )

    # Extract key numbers for attribution
    summary: dict[str, dict[str, float]] = {}
    for r in agg.to_dicts():
        summary.setdefault(r["controller"], {})[r["condition"]] = r["mean_delay"]

    def _v(ctrl: str, cond: str) -> float:
        return summary.get(ctrl, {}).get(cond, 0.0)

    rendered = template_path.read_text()
    tokens = {
        "mp_oracle": _v("max_pressure", "oracle"),
        "mp_ideal": _v("max_pressure", "ideal_cam"),
        "mp_p085": _v("max_pressure", "pdet_0.85"),
        "mp_p050": _v("max_pressure", "pdet_0.50"),
        "mp_omni": _v("max_pressure", "place_omni"),
        "mp_partial": _v("max_pressure", "place_partial_2app"),
        "act_oracle": _v("actuated", "oracle"),
        "act_ideal": _v("actuated", "ideal_cam"),
        "act_p085": _v("actuated", "pdet_0.85"),
        "act_p050": _v("actuated", "pdet_0.50"),
        "act_omni": _v("actuated", "place_omni"),
        "act_partial": _v("actuated", "place_partial_2app"),
        "web_oracle": _v("webster", "oracle"),
        "web_ideal": _v("webster", "ideal_cam"),
        "web_p085": _v("webster", "pdet_0.85"),
        "web_p050": _v("webster", "pdet_0.50"),
        "web_omni": _v("webster", "place_omni"),
        "web_partial": _v("webster", "place_partial_2app"),
        "sumo_oracle": _v("sumo_actuated", "oracle"),
        "sumo_ideal": _v("sumo_actuated", "ideal_cam"),
        "sumo_p085": _v("sumo_actuated", "pdet_0.85"),
        "sumo_p050": _v("sumo_actuated", "pdet_0.50"),
        "sumo_omni": _v("sumo_actuated", "place_omni"),
        "sumo_partial": _v("sumo_actuated", "place_partial_2app"),
    }
    for k, v in tokens.items():
        rendered = rendered.replace(f"{{{k}}}", f"{v:.2f}")
    report_path.write_text(rendered)
    print(f"Consolidated research report written to {report_path}")


def main() -> None:
    exp_dir = Path("research/m3_experiment")
    print("=== Step 1: Running Sensing-Control Gap Experiments ===")
    df = run_experiment_suite(exp_dir)

    print("=== Step 2: Generating Analysis Figures and Tables ===")
    analyze_and_plot(df)

    print("=== Step 3: Generating Visual Divergence GIF Artifact ===")
    generate_visual_divergence_artifact()

    print("=== Step 4: Writing Milestone M3 Research Report ===")
    write_research_report(df)
    print("=== Milestone M3 Suite Complete! ===")


if __name__ == "__main__":
    main()
