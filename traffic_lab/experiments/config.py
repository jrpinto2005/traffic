"""Typed run configuration: YAML on disk, validated into a Pydantic model.

D-004: configuration is Pydantic v2 models with YAML on disk, validated at load so
that an invalid config fails before the simulator starts, naming the offending field.

At T1.1 the schema covers only what T1.1 itself can express: run identity, seeds
(D-017), and run phases (D-018, D-032). The scenario schema (T1.3) and the demand
schema (T1.5) do not exist yet and are deliberately not anticipated here — an
unpopulated field nothing reads is a D-031 anti-pattern.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class RunConfig(BaseModel):
    """The fully-specified configuration for one run.

    `extra="forbid"` so a misspelled or stray key fails at load rather than being
    silently ignored — see the D-031 anti-pattern list: "a config key that never
    reaches the simulator" is worse than an absent one.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # --- Run identity ---
    name: str = Field(min_length=1, description="Human-readable identifier for this run.")

    # --- Seeds (D-017) ---
    master_seed: int = Field(
        ge=0, description="Master seed. Per-stream seeds are derived from this alone."
    )

    # --- Run phases (D-018, D-032) ---
    warmup_s: float = Field(ge=0.0, description="Warm-up duration, simulated seconds. Discarded.")
    measurement_s: float = Field(
        gt=0.0, description="Measurement-window duration, simulated seconds. Metrics collected."
    )
    cooldown_s: float = Field(
        ge=0.0, description="Cool-down duration, simulated seconds. Lets in-flight trips finish."
    )
    warmup_design: Literal["self", "neutral_snapshot"] = Field(
        default="self",
        description="D-032: each arm warms up under its own controller ('self', the default "
        "for steady-state comparison) or all arms load one shared snapshot "
        "('neutral_snapshot', for transient-response experiments).",
    )

    # --- Tracing (D-030) ---
    record_trace: bool = Field(
        default=False,
        description="D-030: Whether to record step-by-step trace for 2D replay.",
    )
    trace_compressed: bool = Field(
        default=True,
        description="D-030: Whether trace file is gzip-compressed (.jsonl.gz).",
    )


def load_config(path: Path) -> RunConfig:
    """Load and validate a run config from a YAML file.

    Raises `pydantic.ValidationError` — naming the offending field — if the parsed
    document does not satisfy `RunConfig`. Raises `FileNotFoundError` if `path` does
    not exist. Both happen before anything simulator-related starts.
    """
    raw: Any = yaml.safe_load(path.read_text())
    if raw is None:
        raw = {}
    return RunConfig.model_validate(raw)


def compute_config_hash(config: RunConfig) -> str:
    """SHA-256 hex digest of the canonical JSON serialisation of a resolved config.

    "Canonical" means: JSON (not Python `repr`, which is not stable across Python
    versions for some types), object keys sorted, no incidental whitespace. This
    makes the hash depend only on the config's field values — not on YAML key order,
    dict insertion order, or object identity — so the same logical config produces
    the same hash on any machine and any run, satisfying D-017's manifest
    requirement and the T1.1 acceptance criterion.
    """
    return canonical_hash(config.model_dump(mode="json"))


def canonical_hash(payload: Any) -> str:
    """SHA-256 hex digest of `payload`'s canonical JSON: keys sorted, no whitespace.

    `payload` must already be JSON-compatible. `compute_config_hash` is this
    applied to a `RunConfig`; the experiment runner applies it to a run's whole
    resolved record (`traffic_lab.experiments.runner`).
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
