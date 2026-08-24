"""`SumoBackend` — the only code in the project that drives SUMO.

Implements D-002 (one interface, two transports, selected by configuration),
D-003 (projection plus a command surface, nothing more), D-008 (the startup
assertions and the validity counters), D-031 as amended (one batched projection
per step; **no per-object query method exposed**), and D-032's snapshot
mechanism.

**The architectural constraint, stated once.** `project()` is the only way any
other layer reads simulation state, and it returns the whole step. There is no
`vehicle(id)`, no `lane(id)`, no `queue_on(lane)`. This is not an optimization —
`06_ARCHITECTURE.md` §5.2 is explicit that it exists so per-object access cannot
leak into sensors, metrics and controllers, "where it would be both slow and
impossible to remove later". Adding such a method is a review defect even if it
is faster in the case that motivates it.

**Startup assertions** (`06_ARCHITECTURE.md` §5.4) are hard failures before the
first step, because "a run that violates them produces no results rather than
wrong ones". Each is checked against the *running simulator* via
`simulation.getOption` wherever SUMO exposes it, not against our own config
object — a config value that never reached the simulator is precisely the
prior-art defect `08_AGENT_HANDOFF_PROTOCOL.md` §7 lists (PyTSC's `seed`).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sumolib import checkBinary

from traffic_lab.backend.config import (
    BackendConfig,
    BackendStartupError,
    SnapshotMismatchError,
    launch_argv,
)
from traffic_lab.backend.projection import VEHICLE_CLASS_TO_TYPE, Projector
from traffic_lab.backend.transport import LibsumoTransport, TraciTransport, Transport
from traffic_lab.domain.network import IntersectionId, VehicleType
from traffic_lab.domain.state import TrueState

#: Suffix of the sidecar written beside every snapshot. SUMO's own state file
#: carries neither the network it was produced on nor the version that wrote it,
#: and D-032 requires both to be checked on load.
SNAPSHOT_SIDECAR_SUFFIX = ".manifest.json"

#: Tolerance when checking that the step length divides the decision interval.
#: Both are floats from a config file, so exact modulo arithmetic is not safe.
_DIVISIBILITY_TOLERANCE = 1e-9


@dataclass(frozen=True, slots=True)
class BackendIndex:
    """The static SUMO-ID ↔ canonical-ID correspondence, fixed at `start()`.

    Canonical IDs are dense integers (`05_DOMAIN_MODEL.md` §1.2) and are
    therefore meaningless without this. Metrics need to know which `LaneId` is
    which approach; the manifest needs to record the correspondence so a result
    can be read back later.

    This is **not** a per-object query surface: it is static structure resolved
    once at start, it contains no simulation state, and it does not change while
    the run proceeds.
    """

    lane_sumo_ids: tuple[str, ...]
    lane_lengths_m: tuple[float, ...]
    intersection_sumo_ids: tuple[str, ...]


class Backend(Protocol):
    """The `D-002` seam, as `tickets/M1/T1.4_backend_adapter.md` specifies it."""

    def start(self, net: Path, routes: Path, cfg: BackendConfig) -> None: ...

    def step(self) -> None: ...

    def project(self) -> TrueState: ...

    def apply(self, intersection: IntersectionId, phase_state: str) -> None: ...

    def save_state(self, path: Path) -> None: ...

    def load_state(self, path: Path) -> None: ...

    def close(self) -> None: ...


class SumoBackend:
    """One SUMO simulation, behind one interface, over either transport."""

    def __init__(self) -> None:
        self._transport: Transport | None = None
        self._projector: Projector | None = None
        self._config: BackendConfig | None = None
        self._index: BackendIndex | None = None
        self._net_hash: str | None = None
        self._sumo_version: str | None = None
        self._intersection_index: dict[IntersectionId, str] = {}

    # --- Lifecycle -----------------------------------------------------------

    def start(self, net: Path, routes: Path, cfg: BackendConfig) -> None:
        self._assert_teleporting_disabled(cfg)
        self._assert_step_length_divides_decision_interval(cfg)

        transport: Transport = TraciTransport() if cfg.transport == "traci" else LibsumoTransport()
        transport.start(launch_argv(checkBinary("sumo"), net, routes, cfg))

        self._transport = transport
        self._config = cfg
        self._net_hash = _file_sha256(net)

        # From here on SUMO is running, so a failed assertion must take the
        # simulator down with it. Leaving a process behind on a rejected startup
        # would make the next run fail for an unrelated-looking reason -- and the
        # whole point of these assertions is that a bad run stops cleanly.
        try:
            self._sumo_version = transport.version()
            self._assert_simulator_agrees(cfg, transport)

            lane_sumo_ids = transport.lane_ids()
            intersection_sumo_ids = transport.traffic_light_ids()
            index = BackendIndex(
                lane_sumo_ids=lane_sumo_ids,
                lane_lengths_m=tuple(transport.lane_length_m(lane) for lane in lane_sumo_ids),
                intersection_sumo_ids=intersection_sumo_ids,
            )
            self._index = index
            self._intersection_index = {
                IntersectionId(i): sumo_id for i, sumo_id in enumerate(intersection_sumo_ids)
            }

            transport.register(intersection_sumo_ids)
            self._projector = Projector(
                lane_sumo_ids=index.lane_sumo_ids,
                lane_lengths_m=index.lane_lengths_m,
                intersection_sumo_ids=intersection_sumo_ids,
                vehicle_types=_vehicle_type_map(transport),
                step_length_s=cfg.step_length_s,
                gridlock_steps=cfg.gridlock_steps,
                max_accel_mps2=_max_accel_mps2(transport),
            )
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    # --- The step loop -------------------------------------------------------

    def step(self) -> None:
        self._require_started().step()

    def project(self) -> TrueState:
        """One batched fetch, one `TrueState`. The only state-reading method (D-031)."""
        transport = self._require_started()
        return self._require_projector().project(transport.fetch())

    # --- The command surface (D-003) -----------------------------------------

    def apply(self, intersection: IntersectionId, phase_state: str) -> None:
        """Drive one intersection's signal directly, as a red/yellow/green string.

        `05_DOMAIN_MODEL.md` §7: "Ours holds green groups; SUMO's holds a
        per-connection state string. The adapter translates." The translation
        itself needs the authored phase table, which is T1.3's output and T1.7's
        to apply; the backend's half is this call.
        """
        transport = self._require_started()
        sumo_id = self._intersection_index.get(intersection)
        if sumo_id is None:
            raise BackendStartupError(
                f"no traffic light for IntersectionId({int(intersection)}); "
                f"known: {sorted(int(i) for i in self._intersection_index)}"
            )
        transport.apply_ryg_state(sumo_id, phase_state)

    # --- Static structure ----------------------------------------------------

    @property
    def index(self) -> BackendIndex:
        """The canonical-ID correspondence fixed at `start()`."""
        if self._index is None:
            raise BackendStartupError("backend has not been started")
        return self._index

    # --- Snapshots (D-032; mechanism only, policy is T1.6) -------------------

    def save_state(self, path: Path) -> None:
        """Save SUMO's state plus the bookkeeping SUMO does not carry.

        The sidecar records the network hash and the SUMO version because D-032
        makes loading against either mismatch a hard error, and it records the
        projector's halting timers, stop counts and cumulative counters because
        otherwise a loaded snapshot could not reproduce the `TrueState` it was
        saved from.
        """
        transport = self._require_started()
        transport.save_state(path)
        _sidecar_path(path).write_text(
            json.dumps(
                {
                    "network_sha256": self._net_hash,
                    "sumo_version": self._sumo_version,
                    "projector": self._require_projector().state_dict(),
                },
                sort_keys=True,
            )
        )

    def load_state(self, path: Path) -> None:
        transport = self._require_started()
        projector = self._require_projector()

        sidecar = _sidecar_path(path)
        if not sidecar.exists():
            raise SnapshotMismatchError(
                f"snapshot {path} has no {SNAPSHOT_SIDECAR_SUFFIX} sidecar, so neither its "
                f"network nor its SUMO version can be checked (D-032)"
            )
        payload = json.loads(sidecar.read_text())

        if payload["network_sha256"] != self._net_hash:
            raise SnapshotMismatchError(
                f"snapshot {path} was produced on network sha256="
                f"{payload['network_sha256']}, this run's network is sha256={self._net_hash}; "
                f"D-032 makes this a hard error rather than undefined behaviour"
            )
        if payload["sumo_version"] != self._sumo_version:
            raise SnapshotMismatchError(
                f"snapshot {path} was produced by {payload['sumo_version']}, this run uses "
                f"{self._sumo_version}; SUMO state files are version-sensitive (D-032)"
            )

        transport.load_state(path)
        projector.load_state_dict(payload["projector"])

    # --- Startup assertions (`06_ARCHITECTURE.md` §5.4) ----------------------

    @staticmethod
    def _assert_teleporting_disabled(cfg: BackendConfig) -> None:
        """D-008: teleporting is disabled by flag, never by magnitude."""
        if cfg.time_to_teleport_s != -1.0:
            raise BackendStartupError(
                f"time_to_teleport_s is {cfg.time_to_teleport_s}, must be exactly -1.0. "
                f"D-008 disables teleporting by flag; a large positive value disables it only "
                f"until an episode outlasts it, which is how a run silently deletes the "
                f"congestion it is measuring"
            )

    @staticmethod
    def _assert_step_length_divides_decision_interval(cfg: BackendConfig) -> None:
        """D-020: Δt must be an integer multiple of the SUMO step length."""
        quotient = cfg.decision_interval_s / cfg.step_length_s
        if abs(quotient - round(quotient)) > _DIVISIBILITY_TOLERANCE:
            raise BackendStartupError(
                f"step_length_s={cfg.step_length_s} does not divide "
                f"decision_interval_s={cfg.decision_interval_s} (quotient {quotient}). "
                f"D-020 requires Δt to be an integer multiple of the step length, or the "
                f"controller cannot act at the interval it declares"
            )

    @staticmethod
    def _assert_simulator_agrees(cfg: BackendConfig, transport: Transport) -> None:
        """Read the settings back out of the running simulator.

        `08_AGENT_HANDOFF_PROTOCOL.md` §7: "a config key that never reaches the
        simulator ... invites the reader to believe an experiment was controlled
        when it was not." Checking our own config object would prove nothing;
        these read SUMO's view.
        """
        expected = {
            "time-to-teleport": cfg.time_to_teleport_s,
            "step-length": cfg.step_length_s,
            "seed": float(cfg.seed),
        }
        for option, wanted in expected.items():
            actual = transport.option(option)
            if float(actual) != wanted:
                raise BackendStartupError(
                    f"SUMO reports --{option}={actual!r} but the config asked for {wanted!r}; "
                    f"the setting did not reach the simulator"
                )

    # --- Internals -----------------------------------------------------------

    def _require_started(self) -> Transport:
        if self._transport is None:
            raise BackendStartupError("backend has not been started")
        return self._transport

    def _require_projector(self) -> Projector:
        if self._projector is None:
            raise BackendStartupError("backend has not been started")
        return self._projector


def _vehicle_type_map(transport: Transport) -> dict[str, VehicleType]:
    """Resolve every declared SUMO vType to a canonical `VehicleType`, once at start.

    Types outside the canonical ontology (SUMO ships defaults for bicycles,
    pedestrians, rail and containers) are left out of the map rather than
    rejected here — a scenario that merely *declares* them is fine. The failure
    is raised by `Projector` only if a vehicle of such a type actually appears,
    which is the point at which `TrueState` could not be built honestly.
    """
    resolved: dict[str, VehicleType] = {}
    for type_id in transport.vehicle_type_ids():
        vehicle_type = VEHICLE_CLASS_TO_TYPE.get(transport.vehicle_class(type_id))
        if vehicle_type is not None:
            resolved[type_id] = vehicle_type
    return resolved


def _max_accel_mps2(transport: Transport) -> float:
    """The fastest acceleration any declared vType can manage, read once at start.

    A single scalar rather than a per-type lookup: the projector uses it only as
    an upper bound when deciding whether a departing vehicle reached a sink, and
    the maximum over all declared types is a valid bound for every one of them
    while keeping a per-vehicle `vehicletype` call out of the step loop (D-031).
    """
    type_ids = transport.vehicle_type_ids()
    if not type_ids:
        return 0.0
    return max(transport.vehicle_accel_mps2(type_id) for type_id in type_ids)


def _sidecar_path(path: Path) -> Path:
    return path.with_name(path.name + SNAPSHOT_SIDECAR_SUFFIX)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
