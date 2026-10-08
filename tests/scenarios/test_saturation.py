"""D-037: saturation flow is measured in SUMO, stored versioned, and never reused stale.

The calibration runs real SUMO (five seeds per movement). The committed table is
checked against a fresh calibration, so the numbers in `configs/` are exactly
what the procedure produces today, not what it produced once.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from traffic_lab.domain.network import TurnDirection, VehicleType
from traffic_lab.scenarios import saturation
from traffic_lab.scenarios.saturation import (
    CALIBRATED_TURNS,
    SATURATION_FLOW_TABLE,
    SaturationFlowLookupError,
    StaleCalibrationError,
    UnsaturatedCalibrationError,
    calibrate_saturation_flow,
    lookup_calibration,
    per_lane_saturation_flow_vph,
    read_table,
    write_table,
)
from traffic_lab.scenarios.tools import sumo_version
from traffic_lab.scenarios.vehicles import vtype_hash

CAR = VehicleType.CAR
SPEED_MPS = 13.89

#: Standing-queue discharge from T1.5's diagnostic (escalation E1: seed 1, a red-then-green
#: program, headways after the 4th vehicle at an instantaneous stop-line loop), veh/h/lane.
#: Through is the midpoint of 1830-1866 over two approach lengths.
REFERENCE_VPH_PER_LANE = {
    TurnDirection.THROUGH: 1848.0,
    TurnDirection.LEFT: 1666.0,
    TurnDirection.RIGHT: 1390.0,
}


@pytest.mark.parametrize("turn", CALIBRATED_TURNS, ids=lambda t: t.value)
def test_a_fresh_calibration_reproduces_the_committed_table(
    turn: TurnDirection, tmp_path: Path
) -> None:
    """Amendment A4: two calibrations with the same seeds give the same numbers."""
    fresh = calibrate_saturation_flow(CAR, SPEED_MPS, turn, tmp_path)
    assert fresh == lookup_calibration(CAR, SPEED_MPS, turn)


@pytest.mark.parametrize("turn", CALIBRATED_TURNS, ids=lambda t: t.value)
def test_the_committed_calibration_measures_a_standing_queue(turn: TurnDirection) -> None:
    """Every counted vehicle stood in the queue (the held-green procedure counted under
    1 % that had), each lane queued at least 30, five seeds, and the spread is stated."""
    calibration = lookup_calibration(CAR, SPEED_MPS, turn)
    assert len(calibration.seeds) >= 5
    assert len(calibration.per_seed_vph_per_lane) == len(calibration.seeds)
    assert all(f >= 0.95 for f in calibration.halted_fraction), calibration.halted_fraction
    assert all(q >= 30 for queue in calibration.queued_per_lane for q in queue)
    assert all(n >= 50 for n in calibration.counted_headways)
    assert calibration.first_counted_vehicle == 5
    assert calibration.approach_length_m >= 1000.0
    assert 0.0 < calibration.std_vph_per_lane < 0.03 * calibration.mean_vph_per_lane


@pytest.mark.parametrize("turn", CALIBRATED_TURNS, ids=lambda t: t.value)
def test_the_committed_calibration_lands_near_the_diagnostic(turn: TurnDirection) -> None:
    """Within 3 % of the short-platoon diagnostic: a single seed varies by up to 2.6 %."""
    reference = REFERENCE_VPH_PER_LANE[turn]
    assert abs(lookup_calibration(CAR, SPEED_MPS, turn).mean_vph_per_lane - reference) < (
        0.03 * reference
    )


def test_through_discharge_exceeds_the_turns() -> None:
    through, left, right = (
        per_lane_saturation_flow_vph(CAR, SPEED_MPS, t) for t in CALIBRATED_TURNS
    )
    assert through > left > right


def test_the_committed_table_is_for_this_sumo_and_vtype() -> None:
    for calibration in read_table(SATURATION_FLOW_TABLE):
        assert calibration.sumo_version == sumo_version()
        assert calibration.vtype_hash == vtype_hash(calibration.vehicle_type)
    assert per_lane_saturation_flow_vph(CAR, SPEED_MPS, TurnDirection.THROUGH) > 0.0


def test_a_lookup_with_a_mismatched_sumo_version_raises() -> None:
    with pytest.raises(StaleCalibrationError, match=r"SUMO 1\.26\.0"):
        per_lane_saturation_flow_vph(CAR, SPEED_MPS, TurnDirection.THROUGH, version="1.26.0")


def test_a_lookup_with_a_mismatched_vtype_raises(tmp_path: Path) -> None:
    stale = [
        dataclasses.replace(c, vtype={"vClass": "passenger", "tau": "1.5"}, vtype_hash="0" * 64)
        for c in read_table(SATURATION_FLOW_TABLE)
    ]
    table = tmp_path / "stale.json"
    write_table(stale, table)
    with pytest.raises(StaleCalibrationError, match="vType 000000000000"):
        per_lane_saturation_flow_vph(CAR, SPEED_MPS, TurnDirection.THROUGH, table=table)


def test_a_lookup_at_another_step_length_raises() -> None:
    with pytest.raises(StaleCalibrationError, match=r"step 0\.5 s"):
        per_lane_saturation_flow_vph(CAR, SPEED_MPS, TurnDirection.THROUGH, step_length_s=0.5)


def test_an_uncalibrated_speed_or_type_raises() -> None:
    with pytest.raises(SaturationFlowLookupError, match="no calibration"):
        per_lane_saturation_flow_vph(CAR, 20.0, TurnDirection.THROUGH)
    with pytest.raises(SaturationFlowLookupError, match="no calibration"):
        per_lane_saturation_flow_vph(VehicleType.MOTORCYCLE, SPEED_MPS, TurnDirection.THROUGH)


def test_the_table_round_trips(tmp_path: Path) -> None:
    table = tmp_path / "copy.json"
    write_table(read_table(SATURATION_FLOW_TABLE), table)
    assert read_table(table) == read_table(SATURATION_FLOW_TABLE)


def test_fewer_than_five_seeds_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least five seeds"):
        calibrate_saturation_flow(CAR, SPEED_MPS, TurnDirection.THROUGH, tmp_path, seeds=(1, 2))


def test_a_short_queue_is_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The queue check is not vacuous: 300 veh/h queues ~20 vehicles in the red."""
    monkeypatch.setattr(saturation, "SATURATING_DEMAND_VPH_PER_LANE", 300.0)
    with pytest.raises(UnsaturatedCalibrationError, match="fewer than 30"):
        calibrate_saturation_flow(CAR, SPEED_MPS, TurnDirection.THROUGH, tmp_path)
