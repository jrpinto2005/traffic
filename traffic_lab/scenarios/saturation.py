"""Saturation flow, measured in SUMO (D-037).

D-022 expresses demand as a fraction of saturation flow and D-013's Webster
computes from it; D-037 fixes where the number comes from: a pinned measurement
in SUMO, not the HCM.

**The quantity** is Webster's: the rate at which a **standing queue** discharges
across the stop line once the light turns green. Holding a movement green from
an empty start does not measure it -- no queue ever forms at the stop line (under
1 % of counted through vehicles halted, T1.5 escalation E1), so the count is the
boundary's insertion capacity, about 11 % below the discharge of a real queue.

**The procedure** (`calibrate_saturation_flow`). For one (vehicle type, speed
limit, turn direction):

1. Build a T1.3 intersection with `CALIBRATION_LANES` lanes per approach,
   approaches `CALIBRATION_APPROACH_M` long (room for the queue) and the given
   speed limit. Its program first greens a movement nobody uses (approach 1's
   through) for `CALIBRATION_PHASE_S` plus the yellow -- the red pre-load of the
   measured movement -- then greens approach 0's `turn` for `CALIBRATION_PHASE_S`.
2. Feed that movement alone from approach 0 at `SATURATING_DEMAND_VPH_PER_LANE`
   per serving lane, so the queue builds through the red and outlasts the green's
   start.
3. Record each vehicle crossing the stop line with an `instantInductionLoop` at
   the end of every serving lane, for each of `CALIBRATION_SEEDS`.
4. On each serving lane, the vehicles **queued at green onset** are those that
   entered the network before it (nothing can pass the red). Of those, in
   crossing order, take the headways from the `FIRST_COUNTED_VEHICLE`-th (the
   HCM convention: start-up lost time is in the first four). A lane must have
   queued at least `MIN_QUEUE_PER_LANE` vehicles, or the run raises.
5. Per-lane saturation flow = 3600 / mean headway, pooling the serving lanes
   (both lanes for the through movement, one for each turn, under netconvert's
   default assignment). Mean and sample SD across seeds are stored, with the
   fraction of counted vehicles that halted -- 1.0 when the queue was real.

**Results** are stored in `configs/saturation_flow.json`, keyed by SUMO version,
a hash of the `vType` parameters (`vehicles.vtype_hash`) and the step length. A
lookup for a different key raises rather than reusing stale numbers.
Regenerate with `python -m traffic_lab.scenarios.saturation`.

**An approach's saturation flow** is its lane count times the per-lane through
value at its speed limit (D-037).
"""

from __future__ import annotations

import itertools
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

#: Node spacing of the calibration intersection, metres: a ~990 m approach lane
#: stores ~130 standing cars, more than the pre-load queues.
CALIBRATION_APPROACH_M = 1000.0

#: Duration of each of the program's two greens, seconds. The measured movement is
#: red for this plus the yellow (the pre-load), then green for this.
CALIBRATION_PHASE_S = 240.0

#: Yellow after each green, seconds; no all-red.
CALIBRATION_YELLOW_S = 3.0

#: Simulated time after the measured green ends, seconds, so every vehicle that
#: crossed in it reaches the end of the exit edge and appears in tripinfo.
CALIBRATION_TAIL_S = 120.0

#: Headways are counted from this vehicle in the queue onward (HCM convention).
FIRST_COUNTED_VEHICLE = 5

#: A serving lane must have queued at least this many vehicles at green onset.
MIN_QUEUE_PER_LANE = 30

#: Offered demand per serving lane, veh/h: one vehicle per second per lane, more
#: than a lane can take in, so the queue fills as fast as insertion allows.
SATURATING_DEMAND_VPH_PER_LANE = 3600.0

#: SUMO's step length during calibration, seconds: the backend's default. Part of
#: the lookup key.
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
    """A calibration exists, but for a different SUMO version, `vType` or step length."""


class UnsaturatedCalibrationError(RuntimeError):
    """A calibration run's queue was too short to measure discharge from."""


@dataclass(frozen=True, slots=True)
class SaturationFlowCalibration:
    """One measured (vehicle type, speed limit, turn): mean and spread over seeds."""

    sumo_version: str
    vehicle_type: VehicleType
    vtype: dict[str, str]
    vtype_hash: str
    step_length_s: float
    speed_limit_mps: float
    turn: TurnDirection
    lanes_per_approach: int
    serving_lanes: int
    approach_length_m: float
    red_s: float  # pre-load before the measured green
    green_s: float
    first_counted_vehicle: int
    seeds: tuple[int, ...]
    queued_per_lane: tuple[tuple[int, ...], ...]  # per seed, per serving lane, at green onset
    counted_headways: tuple[int, ...]  # per seed, all serving lanes
    halted_fraction: tuple[float, ...]  # per seed: counted vehicles that had halted
    per_seed_vph_per_lane: tuple[float, ...]
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
            step_length_s=float(raw["step_length_s"]),
            speed_limit_mps=float(raw["speed_limit_mps"]),
            turn=TurnDirection(raw["turn"]),
            lanes_per_approach=int(raw["lanes_per_approach"]),
            serving_lanes=int(raw["serving_lanes"]),
            approach_length_m=float(raw["approach_length_m"]),
            red_s=float(raw["red_s"]),
            green_s=float(raw["green_s"]),
            first_counted_vehicle=int(raw["first_counted_vehicle"]),
            seeds=tuple(int(s) for s in raw["seeds"]),
            queued_per_lane=tuple(tuple(int(q) for q in qs) for qs in raw["queued_per_lane"]),
            counted_headways=tuple(int(n) for n in raw["counted_headways"]),
            halted_fraction=tuple(float(v) for v in raw["halted_fraction"]),
            per_seed_vph_per_lane=tuple(float(v) for v in raw["per_seed_vph_per_lane"]),
            mean_vph_per_lane=float(raw["mean_vph_per_lane"]),
            std_vph_per_lane=float(raw["std_vph_per_lane"]),
        )


@dataclass(frozen=True, slots=True)
class _SeedResult:
    vph_per_lane: float
    queued_per_lane: tuple[int, ...]
    counted_headways: int
    halted_fraction: float


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

    Writes the calibration intersection and each run's outputs under `work_dir`.
    """
    if len(seeds) < 5:
        raise ValueError(f"D-037 calibration needs at least five seeds, got {len(seeds)}")
    if len(set(seeds)) != len(seeds):
        raise ValueError(f"calibration seeds repeat: {list(seeds)}")
    timing = SignalTiming(
        min_green_s=CALIBRATION_PHASE_S,
        max_green_s=0.0,
        yellow_s=CALIBRATION_YELLOW_S,
        all_red_s=0.0,
    )
    spec = IntersectionSpec(
        lanes_per_approach=CALIBRATION_LANES,
        approach_length_m=CALIBRATION_APPROACH_M,
        speed_limit_mps=speed_limit_mps,
        # A green for an unused movement (the measured one's red), then the measured one.
        phases=[PhaseSpec(green=[(1, TurnDirection.THROUGH)]), PhaseSpec(green=[(0, turn)])],
        timing=timing,
    )
    net_file, network = build(spec, work_dir / "net")
    from_edge, to_edge, lanes = _movement(network, net_file, turn)
    green_start_s = CALIBRATION_PHASE_S + CALIBRATION_YELLOW_S
    green_end_s = green_start_s + CALIBRATION_PHASE_S
    end_s = green_end_s + CALIBRATION_TAIL_S

    routes = work_dir / "saturating.rou.xml"
    routes.write_text(
        "<routes>\n"
        f"    {vtype_xml(vehicle_type)}\n"
        f'    <route id="movement" edges="{from_edge} {to_edge}"/>\n'
        f'    <flow id="saturating" type="{vtype_id(vehicle_type)}" route="movement" '
        f'begin="0" end="{_number(green_end_s)}" '
        f'vehsPerHour="{_number(SATURATING_DEMAND_VPH_PER_LANE * len(lanes))}"{depart_xml()}/>\n'
        "</routes>\n"
    )

    results: list[_SeedResult] = []
    for seed in seeds:
        loops = work_dir / f"stopline.seed{seed}.xml"
        detectors = work_dir / f"stopline.seed{seed}.add.xml"
        detectors.write_text(
            "<additional>\n"
            + "".join(
                f'    <instantInductionLoop id="{lane}" lane="{lane}" pos="-0.1" file="{loops}"/>\n'
                for lane in lanes
            )
            + "</additional>\n"
        )
        tripinfo = work_dir / f"tripinfo.seed{seed}.xml"
        run_tool(
            "sumo",
            [
                "--net-file",
                str(net_file),
                "--route-files",
                str(routes),
                "--additional-files",
                str(detectors),
                "--seed",
                str(seed),
                "--step-length",
                _number(CALIBRATION_STEP_LENGTH_S),
                "--end",
                _number(end_s),
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
            # By construction: most links stay red all run.
            expected_warnings=("Missing green phase in tlLogic",),
        )
        results.append(_discharge(loops, tripinfo, lanes, green_start_s, green_end_s, seed))

    values = np.array([r.vph_per_lane for r in results])
    return SaturationFlowCalibration(
        sumo_version=sumo_version(),
        vehicle_type=vehicle_type,
        vtype=vtype_attributes(vehicle_type),
        vtype_hash=vtype_hash(vehicle_type),
        step_length_s=CALIBRATION_STEP_LENGTH_S,
        speed_limit_mps=speed_limit_mps,
        turn=turn,
        lanes_per_approach=CALIBRATION_LANES,
        serving_lanes=len(lanes),
        approach_length_m=CALIBRATION_APPROACH_M,
        red_s=green_start_s,
        green_s=CALIBRATION_PHASE_S,
        first_counted_vehicle=FIRST_COUNTED_VEHICLE,
        seeds=tuple(seeds),
        queued_per_lane=tuple(r.queued_per_lane for r in results),
        counted_headways=tuple(r.counted_headways for r in results),
        halted_fraction=tuple(r.halted_fraction for r in results),
        per_seed_vph_per_lane=tuple(float(v) for v in values),
        mean_vph_per_lane=float(values.mean()),
        std_vph_per_lane=float(values.std(ddof=1)),
    )


def _movement(
    network: Network, net_file: Path, turn: TurnDirection
) -> tuple[str, str, tuple[str, ...]]:
    """(from edge, to edge, serving lanes) of approach 0's `turn`, as SUMO IDs."""
    raw = json.loads((net_file.parent / f"{NET_STEM}{IDS_SUFFIX}").read_text())
    edge_ids: list[str] = raw["edges"]
    lane_ids: list[str] = raw["lanes"]
    (intersection,) = network.signalized_intersections
    connections = {c.id: c for c in network.connections}
    for movement in movements_of(network, intersection.junction):
        if edge_ids[movement.from_edge] == approach_in_edge(0) and movement.turn == turn:
            serving = sorted({lane_ids[connections[c].from_lane] for c in movement.connections})
            return edge_ids[movement.from_edge], edge_ids[movement.to_edge], tuple(serving)
    raise ValueError(f"approach 0 has no {turn.value} movement")


def _discharge(
    loops: Path,
    tripinfo: Path,
    lanes: Sequence[str],
    green_start_s: float,
    green_end_s: float,
    seed: int,
) -> _SeedResult:
    """Headways of the standing queue's discharge, from the stop-line crossings."""
    trips = {t.get("id", ""): t for t in ET.parse(tripinfo).getroot().iter("tripinfo")}
    crossings: dict[str, list[tuple[float, str]]] = {lane: [] for lane in lanes}
    for event in ET.parse(loops).getroot().iter("instantOut"):
        if event.get("state") != "enter":
            continue
        time_s = float(event.get("time", "nan"))
        if green_start_s <= time_s < green_end_s:
            crossings[event.get("id", "")].append((time_s, event.get("vehID", "")))

    headways: list[float] = []
    queued: list[int] = []
    counted = halted = 0
    for lane in lanes:
        # The queue at green onset: in crossing order, the vehicles that entered the
        # network before it, up to the first that did not.
        queue: list[tuple[float, str]] = []
        for time_s, vehicle in sorted(crossings[lane]):
            trip = trips.get(vehicle)
            if trip is None:
                raise UnsaturatedCalibrationError(
                    f"seed {seed}: vehicle {vehicle} crossed the stop line of {lane} but is "
                    f"not in tripinfo; lengthen CALIBRATION_TAIL_S"
                )
            if not float(trip.get("depart", "nan")) < green_start_s:
                break
            queue.append((time_s, vehicle))
        queued.append(len(queue))
        if len(queue) < MIN_QUEUE_PER_LANE:
            raise UnsaturatedCalibrationError(
                f"seed {seed}: {lane} queued {len(queue)} vehicles at green onset, fewer "
                f"than {MIN_QUEUE_PER_LANE}; the queue is too short to measure discharge"
            )
        times = [t for t, _ in queue]
        # Vehicle k (1-based) has headway t_k - t_(k-1); count from k = FIRST_COUNTED_VEHICLE.
        headways += [b - a for a, b in itertools.pairwise(times)][FIRST_COUNTED_VEHICLE - 2 :]
        for _, vehicle in queue[FIRST_COUNTED_VEHICLE - 1 :]:
            counted += 1
            halted += int(trips[vehicle].get("waitingCount", "0")) > 0
    return _SeedResult(
        vph_per_lane=3600.0 / float(np.mean(headways)),
        queued_per_lane=tuple(queued),
        counted_headways=len(headways),
        halted_fraction=halted / counted,
    )


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
    step_length_s: float = CALIBRATION_STEP_LENGTH_S,
    table: Path = SATURATION_FLOW_TABLE,
    version: str | None = None,
) -> SaturationFlowCalibration:
    """The stored calibration for this (type, speed, turn), for this SUMO, `vType` and
    step length.

    `version` defaults to the running SUMO's, `step_length_s` to the backend's
    default. Raises `StaleCalibrationError` if the table holds this (type,
    speed, turn) only under another key, and `SaturationFlowLookupError` if it
    does not hold it at all.
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
        if (
            c.sumo_version == version
            and c.vtype_hash == current_hash
            and c.step_length_s == step_length_s
        ):
            return c
    found = ", ".join(
        f"SUMO {c.sumo_version} vType {c.vtype_hash[:12]} step {c.step_length_s} s"
        for c in candidates
    )
    raise StaleCalibrationError(
        f"{table.name} calibrates {vehicle_type.value} at {speed_limit_mps} m/s, "
        f"{turn.value} only for {found}; this is SUMO {version} vType {current_hash[:12]} "
        f"step {step_length_s} s. Recalibrate rather than reuse stale numbers (D-037)"
    )


def per_lane_saturation_flow_vph(
    vehicle_type: VehicleType,
    speed_limit_mps: float,
    turn: TurnDirection,
    *,
    step_length_s: float = CALIBRATION_STEP_LENGTH_S,
    table: Path = SATURATION_FLOW_TABLE,
    version: str | None = None,
) -> float:
    """The calibrated mean saturation flow, veh/h/lane. See `lookup_calibration`."""
    return lookup_calibration(
        vehicle_type,
        speed_limit_mps,
        turn,
        step_length_s=step_length_s,
        table=table,
        version=version,
    ).mean_vph_per_lane


def main() -> None:
    """Regenerate the committed table: every calibrated speed and turn, cars (M1)."""
    calibrations = []
    with tempfile.TemporaryDirectory() as tmp:
        for speed in CALIBRATED_SPEEDS_MPS:
            for turn in CALIBRATED_TURNS:
                work_dir = Path(tmp) / f"{speed}_{turn.value}"
                c = calibrate_saturation_flow(VehicleType.CAR, speed, turn, work_dir)
                print(
                    f"{turn.value:>8} at {speed} m/s: {c.mean_vph_per_lane:.1f} "
                    f"+- {c.std_vph_per_lane:.1f} veh/h/lane over seeds {list(c.seeds)}; "
                    f"per seed {[round(v, 1) for v in c.per_seed_vph_per_lane]}; "
                    f"queued per lane {list(c.queued_per_lane)}; "
                    f"headways {list(c.counted_headways)}; halted {list(c.halted_fraction)}"
                )
                calibrations.append(c)
    write_table(calibrations, SATURATION_FLOW_TABLE)


if __name__ == "__main__":
    main()
