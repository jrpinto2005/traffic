"""The run manifest: what makes a result reproducible (06_ARCHITECTURE.md SS7).

"A result without a manifest is not a result." Every field is always populated,
including counters whose honest value is currently zero (D-008, D-022).
"""

from __future__ import annotations

import resource
import sys
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from traffic_lab.experiments.config import RunConfig, compute_config_hash
from traffic_lab.experiments.seeds import derive_seeds
from traffic_lab.experiments.version import get_code_version, get_sumo_version


class RunManifest(BaseModel):
    """Everything needed to know exactly what a run was and to reproduce it."""

    model_config = ConfigDict(frozen=True)

    config_hash: str
    """SHA-256 of the canonical serialised config (`compute_config_hash`). For a run
    executed by `traffic_lab.experiments.runner` it covers the whole resolved run
    record in `config` together with `seeds` (`runner.resolved_run`)."""

    config: dict[str, Any]
    """The fully resolved config, defaults included. For an executed run, everything
    needed to reproduce it from this file alone: see `runner.resolved_run`."""

    code_version: str
    """Git SHA of HEAD, suffixed '-dirty' if the working tree has uncommitted changes."""

    sumo_version: str
    """Installed `eclipse-sumo` distribution version."""

    seeds: dict[str, int]
    """Per-stream seed, per D-017. Keys are `traffic_lab.experiments.seeds.SEED_STREAMS`."""

    decision_interval_s: dict[str, float | None]
    """Per-controller decision interval, per D-020. Empty: no controller schema exists yet."""

    warmup_design: Literal["self", "neutral_snapshot"]
    """D-032: whether each arm warmed up under its own controller or a shared snapshot."""

    validity: dict[str, int | bool]
    """D-008 counters: `teleports` (int), `insertion_failures` (int),
    `gridlock_detected` (bool)."""

    trips: dict[str, int]
    """D-022 three-way trip accounting: `arrived_at_sink`, `arrived_mid_link`,
    `still_in_network`.

    `validity` and `trips` together use exactly the field names of
    `traffic_lab.domain.state.RunCounters` (`05_DOMAIN_MODEL.md` SS3.2), so the
    runner copies counters across by name rather than through a translation
    table in which a typo would drop a counter silently."""

    constraint_outcomes: dict[str, int | float] = Field(default_factory=dict)
    """D-020, T1.10 Scope 4: per-outcome counters from the constraint layer."""

    sumo_warnings: int
    """Warnings SUMO wrote to the run's `--error-log` (T1.11 Amendment A2). Reported,
    not an invalidity cause."""

    wall_clock_s: float
    """Wall-clock time this invocation took, in seconds."""

    peak_memory_mb: float
    """Peak resident set size of this process, in megabytes."""


def build_manifest(config: RunConfig, *, wall_clock_s: float, peak_memory_mb: float) -> RunManifest:
    """Build the manifest for a run.

    At T1.1 no simulation has happened: the CLI stub only loads and validates a
    config. `validity`, `trips` and `sumo_warnings` are therefore recorded at their honest
    pre-simulation value of zero/false, per D-008 and D-022's "recorded always,
    even when zero" rule, rather than omitted or faked — T1.11's runner is what
    overwrites them with real counts. `decision_interval_s` is empty because no
    controller config schema exists yet (T1.10 adds controllers).
    """
    return RunManifest(
        config_hash=compute_config_hash(config),
        config=config.model_dump(mode="json"),
        code_version=get_code_version(),
        sumo_version=get_sumo_version(),
        seeds=derive_seeds(config.master_seed),
        decision_interval_s={},
        warmup_design=config.warmup_design,
        validity={"teleports": 0, "insertion_failures": 0, "gridlock_detected": False},
        trips={"arrived_at_sink": 0, "arrived_mid_link": 0, "still_in_network": 0},
        constraint_outcomes={
            "granted": 0,
            "deferred": 0,
            "held": 0,
            "forced": 0,
            "rejected": 0,
            "max_green_overshoot_s": 0.0,
            "max_green_worst_overshoot_s": 0.0,
            "overrides_deferred_by_transition": 0,
        },
        sumo_warnings=0,
        wall_clock_s=wall_clock_s,
        peak_memory_mb=peak_memory_mb,
    )


def measure_peak_memory_mb() -> float:
    """Peak resident set size of this process so far, in MB.

    `ru_maxrss` units differ by platform: bytes on macOS/BSD, kibibytes on Linux.
    `sys.platform` is the only portable way to know which.
    """
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return peak / 1e6
    return peak / 1e3
