"""Saturation flow, measured in SUMO (D-037).

D-022 expresses demand as a fraction of saturation flow and D-013's Webster
computes from it; D-037 fixes where the number comes from: a pinned measurement
in SUMO, not the HCM.

**The procedure** (`calibrate_saturation_flow`, T1.5 Amendment A1). For one
(vehicle type, speed limit, turn direction):

1. Build a T1.3 intersection (`CALIBRATION_LANES` lanes per approach, the given
   speed limit) whose program greens that one movement of approach 0 and holds
   it green for longer than the run.
2. Feed that movement alone from approach 0 at `SATURATING_DEMAND_VPH_PER_LANE`
   per lane serving it -- more than any lane discharges, so a queue of vehicles
   waiting to enter forms at once and never empties.
3. Run `sumo` for `CALIBRATION_RUN_S` with each of `CALIBRATION_SEEDS`, and count
   the vehicles arriving at the movement's exit edge in `CALIBRATION_WINDOW_S`,
   after the queue has formed.
4. Per-lane saturation flow = count / window hours / lanes serving the movement
   (the distinct approach lanes its connections leave from: both lanes for the
   through movement, one for each turn, under netconvert's default assignment).

Each run checks its own precondition: every vehicle departing in the window
must have waited to enter (`departDelay > 0`), or the source was not saturated
and the count is a demand, not a capacity. The fraction of counted vehicles
that ever halted is recorded beside each result.

**Results** are stored in `configs/saturation_flow.json`, keyed by SUMO version
and a hash of the `vType` parameters (`vehicles.vtype_hash`). A lookup against
a different SUMO version or `vType` raises rather than reusing stale numbers.
Regenerate with `python -m traffic_lab.scenarios.saturation`.

**An approach's saturation flow** is its lane count times the per-lane through
value at its speed limit (D-037).
"""

from __future__ import annotations

import json
import math
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from traffic_lab.domain.network import (
    Network,
    SignalTiming,
    TurnDirection,
    VehicleType,
    movements_of,
)
from traffic_lab.scenarios.generator import IDS_SUFFIX, NET_STEM, approach_in_edge, build
from traffic_lab.scenarios.spec import IntersectionSpec, PhaseSpec
from traffic_lab.scenarios.tools import run_tool, sumo_version
from traffic_lab.scenarios.vehicles import (
    depart_xml,
    vtype_attributes,
    vtype_hash,
    vtype_id,
    vtype_xml,
)

#: At least five (A1). Fixed, so a recalibration reproduces the stored numbers.
CALIBRATION_SEEDS: tuple[int, ...] = (1, 2, 3, 4, 5)

#: Lanes per approach on the calibration intersection: T1.3's default.
CALIBRATION_LANES = 2

#: Simulated length of one calibration run, seconds.
CALIBRATION_RUN_S = 3600.0

#: The counting window [start, end), seconds: after the queue has formed.
CALIBRATION_WINDOW_S = (600.0, 3600.0)

#: Offered demand per serving lane, veh/h: one vehicle per second per lane, about
#: twice any per-lane discharge SUMO produces.
SATURATING_DEMAND_VPH_PER_LANE = 3600.0

#: SUMO's step length during calibration, seconds: the backend's default.
CALIBRATION_STEP_LENGTH_S = 1.0

#: The committed results (D-037).
SATURATION_FLOW_TABLE = Path(__file__).resolve().parents[2] / "configs" / "saturation_flow.json"

#: The turns a calibration covers: every turn the generator builds (no U-turns).
CALIBRATED_TURNS = (TurnDirection.THROUGH, TurnDirection.LEFT, TurnDirection.RIGHT)

#: The speed limits the committed table covers: T1.3's default.
CALIBRATED_SPEEDS_MPS = (13.89,)


class SaturationFlowLookupError(LookupError):
    """No usable calibration for the requested (vehicle type, speed, turn)."""


class StaleCalibrationError(SaturationFlowLookupError):
    """A calibration exists, but for a different SUMO version or `vType`."""


class UnsaturatedCalibrationError(RuntimeError):
    """A calibration run's source was not saturated, so it measured demand."""


@dataclass(frozen=True, slots=True)
class SaturationFlowCalibration:
    """One measured (vehicle type, speed limit, turn): mean and spread over seeds."""

    sumo_version: str
    vehicle_type: VehicleType
    vtype: dict[str, str]
    vtype_hash: str
    speed_limit_mps: float
    turn: TurnDirection
    lanes_per_approach: int
    serving_lanes: int
    step_length_s: float
    window_s: tuple[float, float]
    seeds: tuple[int, ...]
    per_seed_vph_per_lane: tuple[float, ...]
    halted_fraction: tuple[float, ...]  # per seed: counted vehicles that ever halted
    mean_vph_per_lane: float
    std_vph_per_lane: float  # sample standard deviation across seeds

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json_dict(cls, raw: dict[str, Any]) -> SaturationFlowCalibration:
        return cls(
            sumo_version=str(raw["sumo_version"]),
            vehicle_type=VehicleType(raw["vehicle_type"]),
            vtype={str(k): str(v) for k, v in raw["vtype"].items()},
            vtype_hash=str(raw["vtype_hash"]),
            speed_limit_mps=float(raw["speed_limit_mps"]),
            turn=TurnDirection(raw["turn"]),
            lanes_per_approach=int(raw["lanes_per_approach"]),
            serving_lanes=int(raw["serving_lanes"]),
            step_length_s=float(raw["step_length_s"]),
            window_s=(float(raw["window_s"][0]), float(raw["window_s"][1])),
            seeds=tuple(int(s) for s in raw["seeds"]),
            per_seed_vph_per_lane=tuple(float(v) for v in raw["per_seed_vph_per_lane"]),
            halted_fraction=tuple(float(v) for v in raw["halted_fraction"]),
            mean_vph_per_lane=float(raw["mean_vph_per_lane"]),
            std_vph_per_lane=float(raw["std_vph_per_lane"]),
        )


# --- Measurement ------------------------------------------------------------------


def calibrate_saturation_flow(
    vehicle_type: VehicleType,
    speed_limit_mps: float,
    turn: TurnDirection,
    work_dir: Path,
    *,
    seeds: Sequence[int] = CALIBRATION_SEEDS,
) -> SaturationFlowCalibration:
    """Measure per-lane saturation flow, veh/h/lane, by the procedure in the module docstring.

    Writes the calibration intersection and each run's tripinfo under `work_dir`.
    """
    if len(seeds) < 5:
        raise ValueError(f"D-037 calibration needs at least five seeds, got {len(seeds)}")
    if len(set(seeds)) != len(seeds):
        raise ValueError(f"calibration seeds repeat: {list(seeds)}")
    # Held green for longer than the run: the program's one phase never ends.
    timing = SignalTiming(
        min_green_s=10.0 * CALIBRATION_RUN_S, max_green_s=0.0, yellow_s=3.0, all_red_s=0.0
    )
    spec = IntersectionSpec(
        lanes_per_approach=CALIBRATION_LANES,
        speed_limit_mps=speed_limit_mps,
        phases=[PhaseSpec(green=[(0, turn)])],
        timing=timing,
    )
    net_file, network = build(spec, work_dir / "net")
    from_edge, to_edge, serving_lanes = _movement(network, net_file, turn)

    routes = work_dir / "saturating.rou.xml"
    demand_vph = SATURATING_DEMAND_VPH_PER_LANE * serving_lanes
    routes.write_text(
        "<routes>\n"
        f"    {vtype_xml(vehicle_type)}\n"
        f'    <route id="movement" edges="{from_edge} {to_edge}"/>\n'
        f'    <flow id="saturating" type="{vtype_id(vehicle_type)}" route="movement" '
        f'begin="0" end="{_number(CALIBRATION_RUN_S)}" vehsPerHour="{_number(demand_vph)}"'
        f"{depart_xml()}/>\n"
        "</routes>\n"
    )

    per_seed: list[float] = []
    halted: list[float] = []
    for seed in seeds:
        tripinfo = work_dir / f"tripinfo.seed{seed}.xml"
        run_tool(
            "sumo",
            [
                "--net-file",
                str(net_file),
                "--route-files",
                str(routes),
                "--seed",
                str(seed),
                "--step-length",
                _number(CALIBRATION_STEP_LENGTH_S),
                "--end",
                _number(CALIBRATION_RUN_S),
                # The backend's flags that bear on dynamics (D-008, D-022).
                "--time-to-teleport",
                "-1",
                "--eager-insert",
                "--tripinfo-output",
                str(tripinfo),
                "--no-step-log",
                "true",
                "--duration-log.disable",
                "true",
            ],
            # By construction: every link but the movement's stays red all run.
            expected_warnings=("Missing green phase in tlLogic",),
        )
        vph, halted_fraction = _count(tripinfo, to_edge, serving_lanes, seed)
        per_seed.append(vph)
        halted.append(halted_fraction)

    values = np.array(per_seed)
    return SaturationFlowCalibration(
        sumo_version=sumo_version(),
        vehicle_type=vehicle_type,
        vtype=vtype_attributes(vehicle_type),
        vtype_hash=vtype_hash(vehicle_type),
        speed_limit_mps=speed_limit_mps,
        turn=turn,
        lanes_per_approach=CALIBRATION_LANES,
        serving_lanes=serving_lanes,
        step_length_s=CALIBRATION_STEP_LENGTH_S,
        window_s=CALIBRATION_WINDOW_S,
        seeds=tuple(seeds),
        per_seed_vph_per_lane=tuple(per_seed),
        halted_fraction=tuple(halted),
        mean_vph_per_lane=float(values.mean()),
        std_vph_per_lane=float(values.std(ddof=1)),
    )


def _movement(network: Network, net_file: Path, turn: TurnDirection) -> tuple[str, str, int]:
    """(from edge SUMO ID, to edge SUMO ID, serving lane count) of approach 0's `turn`."""
    edge_ids: list[str] = json.loads((net_file.parent / f"{NET_STEM}{IDS_SUFFIX}").read_text())[
        "edges"
    ]
    (intersection,) = network.signalized_intersections
    lanes = {lane.id: lane for lane in network.lanes}
    connections = {c.id: c for c in network.connections}
    for movement in movements_of(network, intersection.junction):
        if edge_ids[movement.from_edge] == approach_in_edge(0) and movement.turn == turn:
            serving = {connections[c].from_lane for c in movement.connections}
            assert all(lanes[lane].edge == movement.from_edge for lane in serving)
            return edge_ids[movement.from_edge], edge_ids[movement.to_edge], len(serving)
    raise ValueError(f"approach 0 has no {turn.value} movement")


def _count(tripinfo: Path, to_edge: str, serving_lanes: int, seed: int) -> tuple[float, float]:
    """(veh/h/lane arriving on `to_edge` in the window, fraction of those that halted)."""
    start_s, end_s = CALIBRATION_WINDOW_S
    counted = halted = 0
    for trip in ET.parse(tripinfo).getroot().iter("tripinfo"):
        depart_s = float(trip.get("depart", "nan"))
        if start_s <= depart_s < end_s and not float(trip.get("departDelay", "nan")) > 0.0:
            raise UnsaturatedCalibrationError(
                f"seed {seed}: vehicle {trip.get('id')} entered at {depart_s} s without "
                f"waiting, so the source was not saturated (D-037 needs a saturated queue)"
            )
        arrival_s = float(trip.get("arrival", "nan"))
        if not start_s <= arrival_s < end_s:
            continue
        if trip.get("arrivalLane", "").rsplit("_", 1)[0] != to_edge:
            raise UnsaturatedCalibrationError(
                f"seed {seed}: vehicle {trip.get('id')} arrived on {trip.get('arrivalLane')}, "
                f"not on the movement's exit edge {to_edge}"
            )
        counted += 1
        halted += int(trip.get("waitingCount", "0")) > 0
    if counted == 0:
        raise UnsaturatedCalibrationError(f"seed {seed}: no vehicle arrived in the window")
    hours = (end_s - start_s) / 3600.0
    return counted / hours / serving_lanes, halted / counted


def _number(value: float) -> str:
    return str(int(value)) if value == int(value) else repr(value)


# --- The committed table -----------------------------------------------------------


def write_table(calibrations: Sequence[SaturationFlowCalibration], path: Path) -> None:
    payload = {"calibrations": [c.to_json_dict() for c in calibrations]}
    path.write_text(json.dumps(payload, indent=1) + "\n")


def read_table(path: Path) -> tuple[SaturationFlowCalibration, ...]:
    raw = json.loads(path.read_text())
    return tuple(SaturationFlowCalibration.from_json_dict(r) for r in raw["calibrations"])


def lookup_calibration(
    vehicle_type: VehicleType,
    speed_limit_mps: float,
    turn: TurnDirection,
    *,
    table: Path = SATURATION_FLOW_TABLE,
    version: str | None = None,
) -> SaturationFlowCalibration:
    """The stored calibration for this (type, speed, turn), for this SUMO and `vType`.

    `version` defaults to the running SUMO's. Raises `StaleCalibrationError` if
    the table holds this (type, speed, turn) only for another SUMO version or
    `vType`, and `SaturationFlowLookupError` if it does not hold it at all.
    """
    version = sumo_version() if version is None else version
    current_hash = vtype_hash(vehicle_type)
    candidates = [
        c
        for c in read_table(table)
        if c.vehicle_type == vehicle_type
        and c.turn == turn
        and math.isclose(c.speed_limit_mps, speed_limit_mps, rel_tol=0.0, abs_tol=1e-9)
    ]
    if not candidates:
        raise SaturationFlowLookupError(
            f"{table.name} has no calibration for {vehicle_type.value} at "
            f"{speed_limit_mps} m/s, {turn.value} (D-037); run calibrate_saturation_flow"
        )
    for c in candidates:
        if c.sumo_version == version and c.vtype_hash == current_hash:
            return c
    found = ", ".join(f"SUMO {c.sumo_version} vType {c.vtype_hash[:12]}" for c in candidates)
    raise StaleCalibrationError(
        f"{table.name} calibrates {vehicle_type.value} at {speed_limit_mps} m/s, "
        f"{turn.value} only for {found}; this is SUMO {version} vType {current_hash[:12]}. "
        f"Recalibrate rather than reuse stale numbers (D-037)"
    )


def per_lane_saturation_flow_vph(
    vehicle_type: VehicleType,
    speed_limit_mps: float,
    turn: TurnDirection,
    *,
    table: Path = SATURATION_FLOW_TABLE,
    version: str | None = None,
) -> float:
    """The calibrated mean saturation flow, veh/h/lane. See `lookup_calibration`."""
    return lookup_calibration(
        vehicle_type, speed_limit_mps, turn, table=table, version=version
    ).mean_vph_per_lane


def main() -> None:
    """Regenerate the committed table: every calibrated speed and turn, cars (M1)."""
    calibrations = []
    with tempfile.TemporaryDirectory() as tmp:
        for speed in CALIBRATED_SPEEDS_MPS:
            for turn in CALIBRATED_TURNS:
                work_dir = Path(tmp) / f"{speed}_{turn.value}"
                calibration = calibrate_saturation_flow(VehicleType.CAR, speed, turn, work_dir)
                print(
                    f"{turn.value:>8} at {speed} m/s: {calibration.mean_vph_per_lane:.1f} "
                    f"+- {calibration.std_vph_per_lane:.1f} veh/h/lane "
                    f"(seeds {list(calibration.seeds)})"
                )
                calibrations.append(calibration)
    write_table(calibrations, SATURATION_FLOW_TABLE)


if __name__ == "__main__":
    main()
