"""Profiling harness for traffic-lab runs (T1.13, D-031).

Runs a standard scenario under `cProfile` and emits a hot-path report:
cumulative time by function, wall-clock per simulated hour, and peak memory.
Outputs a human-readable summary and appends a machine-readable JSONL record
to `research/performance_baseline.jsonl`. Compares performance against prior
baselines and warns on material degradation.
"""

from __future__ import annotations

import cProfile
import io
import json
import pstats
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from traffic_lab.control.hold_first import hold_first
from traffic_lab.experiments.config import load_config
from traffic_lab.experiments.manifest import measure_peak_memory_mb
from traffic_lab.experiments.runner import RunSpec, run_one
from traffic_lab.experiments.version import get_code_version, get_sumo_version
from traffic_lab.scenarios.standard import build_standard_scenario

DEFAULT_BASELINE_PATH = Path("research/performance_baseline.jsonl")


def profile_command(config_path: Path, top_n: int = 20, baseline_path: Path | None = None) -> int:
    """Run profiling on `config_path` and append result to `baseline_path`. Returns exit code."""
    if baseline_path is None:
        baseline_path = DEFAULT_BASELINE_PATH

    try:
        config = load_config(config_path)
    except ValidationError as exc:
        print(f"Invalid config at {config_path}:\n{exc}", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 1

    end_s = config.warmup_s + config.measurement_s + config.cooldown_s
    simulated_hours = end_s / 3600.0

    previous_baseline = _get_latest_baseline(baseline_path, config.name)

    with tempfile.TemporaryDirectory() as tmp_dir:
        work_dir = Path(tmp_dir)
        net_file, routes_file, network = build_standard_scenario(work_dir / "scenario", end_s=end_s)
        spec = RunSpec(
            run_id=f"profile_{config.name}",
            net=net_file,
            routes=routes_file,
            network=network,
            controller_factory=hold_first,
            config=config,
            seed_index=0,
            step_length_s=1.0,
            output_dir=work_dir / "run_out",
        )

        profiler = cProfile.Profile()
        start_wall = time.monotonic()
        profiler.enable()
        try:
            run_one(spec)
        finally:
            profiler.disable()
        wall_clock_s = time.monotonic() - start_wall

    wall_clock_per_simulated_hour = wall_clock_s / simulated_hours if simulated_hours > 0 else 0.0
    peak_memory_mb = measure_peak_memory_mb()

    stats_stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stats_stream)
    stats.strip_dirs()
    stats.sort_stats(pstats.SortKey.CUMULATIVE)

    top_hotpaths = _extract_top_hotpaths(stats, top_n)

    code_version = get_code_version()
    sumo_version = get_sumo_version()

    print(f"=== Performance Profile: {config.name} ===")
    print(f"Code version: {code_version}")
    print(f"SUMO version: {sumo_version}")
    print(f"Wall-clock time: {wall_clock_s:.2f} s")
    print(f"Simulated time: {end_s:.1f} s ({simulated_hours:.4f} simulated hours)")
    print(f"Wall-clock / simulated hour: {wall_clock_per_simulated_hour:.2f} s")
    print(f"Peak memory: {peak_memory_mb:.1f} MB\n")
    print(f"Top {top_n} hot paths (by cumulative time):")

    stats.print_stats(top_n)
    print(stats_stream.getvalue())

    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "config_name": config.name,
        "code_version": code_version,
        "sumo_version": sumo_version,
        "wall_clock_s": round(wall_clock_s, 4),
        "simulated_s": end_s,
        "simulated_hours": round(simulated_hours, 6),
        "wall_clock_per_simulated_hour": round(wall_clock_per_simulated_hour, 4),
        "peak_memory_mb": round(peak_memory_mb, 2),
        "top_hotpaths": top_hotpaths,
    }

    _append_baseline_record(baseline_path, record)

    if previous_baseline is not None:
        prev_rate_obj = previous_baseline.get("wall_clock_per_simulated_hour")
        if isinstance(prev_rate_obj, (int, float)) and prev_rate_obj > 0:
            prev_rate = float(prev_rate_obj)
            if wall_clock_per_simulated_hour > prev_rate * 1.25:
                decline_pct = ((wall_clock_per_simulated_hour - prev_rate) / prev_rate) * 100.0
                print(
                    f"WARNING: Performance degradation detected! Current rate "
                    f"({wall_clock_per_simulated_hour:.2f} s/sim-h) is {decline_pct:.1f}% slower "
                    f"than previous baseline ({prev_rate:.2f} s/sim-h).",
                    file=sys.stderr,
                )

    return 0


def _extract_top_hotpaths(stats: pstats.Stats, top_n: int) -> list[dict[str, object]]:
    """Extract structured function call data for the top N functions."""
    hotpaths: list[dict[str, object]] = []
    fcn_list = getattr(stats, "fcn_list", [])
    raw_stats: dict[tuple[str, int, str], tuple[int, int, float, float, dict[Any, Any]]] = getattr(
        stats, "stats", {}
    )
    if not fcn_list:
        fcn_list = list(raw_stats.keys())
    for func in fcn_list[:top_n]:
        func_stats = raw_stats.get(func)
        if func_stats is None:
            continue
        _cc, nc, tt, ct, _callers = func_stats
        filename, line, funcname = func
        hotpaths.append(
            {
                "function": f"{filename}:{line}({funcname})",
                "ncalls": nc,
                "tottime_s": round(tt, 6),
                "cumtime_s": round(ct, 6),
                "percall_cum_s": round(ct / nc, 6) if nc > 0 else 0.0,
            }
        )
    return hotpaths


def _get_latest_baseline(path: Path, config_name: str) -> dict[str, object] | None:
    """Read `path` and return the latest recorded baseline dict for `config_name`."""
    if not path.exists():
        return None
    latest: dict[str, object] | None = None
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if data.get("config_name") == config_name:
                    latest = data
    except (json.JSONDecodeError, OSError):
        return None
    return latest


def _append_baseline_record(path: Path, record: dict[str, object]) -> None:
    """Append JSON record to `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
