"""Backend configuration and the launch flags the adapter passes to SUMO.

Implements D-002 (transport is a configuration value, never a code change),
D-008 (`--time-to-teleport -1`, passed *and* asserted), D-020 (the step length
must divide the decision interval), and D-022 (native trip accounting via
`--tripinfo-output.write-unfinished` / `--write-undeparted`, which in turn
require `--eager-insert`).

The launch flags are RESCO's set, adopted via `research/M0_prior_art.md` §9.1.
Two prior-art anti-patterns from `08_AGENT_HANDOFF_PROTOCOL.md` §7 are avoided
here deliberately:

* **"a config key that never reaches the simulator"** — PyTSC's `seed` reaches
  only Python's `random`. Every field below is either passed to SUMO on the
  command line or used by a startup assertion, and `SumoBackend.start()` reads
  the values back out of the running simulator with `simulation.getOption()`.
* **"a validity setting disabled by magnitude rather than by flag"** — PyTSC's
  `time_to_teleport: 10000`. `time_to_teleport_s` is validated to be exactly
  `-1.0`; a large positive number is rejected, not tolerated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TransportName = Literal["traci", "libsumo"]

#: Speed below which SUMO — and therefore `VehicleState.is_halting` (D-025,
#: `05_DOMAIN_MODEL.md` §8 invariant 11) — considers a vehicle halting.
HALTING_SPEED_MPS = 0.1

#: Continuous halting duration a vehicle must reach before it counts towards
#: `LaneState.queue_count` (D-025, invariant 12). SUMO's native halting counter
#: applies no duration condition, so this part is ours — see
#: `research/M0_sumo_semantics.md` §1.3.
QUEUE_MIN_HALTING_S = 1.0


class BackendConfig(BaseModel):
    """Everything the adapter needs to launch and validate one SUMO simulation.

    `extra="forbid"` and `frozen=True` follow `traffic_lab.experiments.config`:
    a misspelled key fails at load rather than being silently ignored.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    transport: TransportName = Field(
        default="traci",
        description="D-002. TraCI for development and anything with a GUI; LibSUMO for "
        "batch and training workloads. LibSUMO holds one simulation per process.",
    )
    step_length_s: float = Field(
        default=1.0, gt=0.0, description="SUMO simulation step length, seconds."
    )
    seed: int = Field(
        ge=0,
        description="RNG seed passed to SUMO as `--seed`. Asserted to have arrived, because "
        "a seed that looks set and is not invalidates every claim of reproducibility.",
    )
    decision_interval_s: float = Field(
        gt=0.0,
        description="D-020's Δt. The backend does not act on it — it only asserts that "
        "`step_length_s` divides it, which is `06_ARCHITECTURE.md` §5.4's second startup "
        "assertion and cannot be checked without the value. Required rather than defaulted: "
        "Δt is per-controller (D-020) and a results-affecting default is not a Builder's "
        "to invent.",
    )
    gridlock_steps: int = Field(
        gt=0,
        description="D-008's N: the number of consecutive simulation steps during which no "
        "vehicle moves before the run is marked gridlocked. Required for the same reason as "
        "`decision_interval_s` — it decides whether a run is valid.",
    )
    time_to_teleport_s: float = Field(
        default=-1.0,
        description="D-008. Must be exactly -1 (teleporting disabled). Present as a field "
        "only so that the assertion has something to assert against and so the value lands "
        "in the run manifest; there is no legal second value.",
    )
    tripinfo_path: Path | None = Field(
        default=None,
        description="D-022. When set, SUMO writes tripinfo including unfinished and "
        "undeparted vehicles, which is the native per-vehicle form of the three-way trip "
        "accounting. When unset the three `--tripinfo-output*` flags are omitted rather "
        "than passed with nothing to write to.",
    )


class BackendStartupError(RuntimeError):
    """A `06_ARCHITECTURE.md` §5.4 startup assertion failed.

    Raised before or immediately after SUMO starts, never mid-run: a run that
    violates a methodology precondition must produce no results rather than
    wrong ones (D-008).
    """


class SnapshotMismatchError(BackendStartupError):
    """A snapshot was loaded against a different network or a different SUMO version.

    D-032: "loading a snapshot against a different network is a hard error rather
    than undefined behaviour."
    """


def launch_argv(sumo_binary: str, net: Path, routes: Path, config: BackendConfig) -> list[str]:
    """Build the SUMO command line for one run.

    Every flag here is justified in `research/M0_prior_art.md` §9.1 or by a
    decision. `--eager-insert` is unconditional and deliberately not
    configurable: it is what makes undeparted vehicles appear in tripinfo at
    all, and a validity mechanism that can be switched off by configuration is
    a `08_AGENT_HANDOFF_PROTOCOL.md` §7 anti-pattern. Its wall-clock cost is
    measured and reported in the T1.4 completion record, per D-031.
    """
    argv = [
        sumo_binary,
        "--net-file",
        str(net),
        "--route-files",
        str(routes),
        "--step-length",
        _format_float(config.step_length_s),
        "--seed",
        str(config.seed),
        # D-008. Asserted after start via `simulation.getOption`.
        "--time-to-teleport",
        _format_float(config.time_to_teleport_s),
        # D-022: undeparted vehicles are only written correctly with eager insertion.
        "--eager-insert",
        # Removes per-step console I/O from the hot loop (D-031).
        "--no-step-log",
        "true",
        "--duration-log.disable",
        "true",
        "--no-warnings",
        "true",
        # TraCI otherwise waits for a GUI-style start command.
        "--start",
        "--quit-on-end",
    ]
    if config.tripinfo_path is not None:
        argv += [
            "--tripinfo-output",
            str(config.tripinfo_path),
            # D-022's "still in-network" leg, per vehicle rather than as a bare counter.
            "--tripinfo-output.write-unfinished",
            "true",
            # D-022's insertion-loss leg, likewise per vehicle.
            "--tripinfo-output.write-undeparted",
            "true",
        ]
    return argv


def _format_float(value: float) -> str:
    """Render a float for SUMO's command line without an exponent or trailing noise.

    `str(-1.0)` is `'-1.0'`, which SUMO accepts, but `simulation.getOption` reads
    back `'-1'`; formatting here and normalising there keeps the startup
    assertion comparing like with like.
    """
    if value == int(value):
        return str(int(value))
    return repr(value)
