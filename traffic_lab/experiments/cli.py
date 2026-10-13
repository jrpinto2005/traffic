"""The `traffic-lab` command-line entry point.

At T1.1 this is a stub: `traffic-lab run <config>` loads and validates a config,
builds a run manifest, prints it, and exits. It does not simulate — T1.11 adds the
experiment runner.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from pydantic import ValidationError

from traffic_lab.experiments.config import load_config
from traffic_lab.experiments.manifest import build_manifest, measure_peak_memory_mb


def run_command(config_path: Path) -> int:
    """Load, validate, and print the manifest for `config_path`. Returns an exit code."""
    start = time.monotonic()
    try:
        config = load_config(config_path)
    except ValidationError as exc:
        print(f"Invalid config at {config_path}:\n{exc}", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 1

    wall_clock_s = time.monotonic() - start
    manifest = build_manifest(
        config, wall_clock_s=wall_clock_s, peak_memory_mb=measure_peak_memory_mb()
    )
    print(json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="traffic-lab")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="Load a config, validate it, print its manifest, and exit."
    )
    run_parser.add_argument("config", type=Path, help="Path to a run config YAML file.")

    args = parser.parse_args(argv)
    if args.command == "run":
        sys.exit(run_command(args.config))


if __name__ == "__main__":
    main()
