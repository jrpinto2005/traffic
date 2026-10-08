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

#: The architect's single-seed reference (D-037), veh/h/lane.
REFERENCE_VPH_PER_LANE = {
    TurnDirection.THROUGH: 1652.0,
    TurnDirection.LEFT: 1624.0,
    TurnDirection.RIGHT: 1392.0,
}


@pytest.mark.parametrize("turn", CALIBRATED_TURNS, ids=lambda t: t.value)
def test_a_fresh_calibration_reproduces_the_committed_table(
    turn: TurnDirection, tmp_path: Path
) -> None:
    """Amendment A4: two calibrations with the same seeds give the same numbers."""
    fresh = calibrate_saturation_flow(CAR, SPEED_MPS, turn, tmp_path)
    assert fresh == lookup_calibration(CAR, SPEED_MPS, turn)


@pytest.mark.parametrize("turn", CALIBRATED_TURNS, ids=lambda t: t.value)
def test_the_committed_calibration_lands_near_the_reference(turn: TurnDirection) -> None:
    """Within 2 % of the architect's single-seed measurement, at least five seeds, spread
    reported. A single seed varies by about 1 % here, so 2 % is a real bound."""
    calibration = lookup_calibration(CAR, SPEED_MPS, turn)
    assert len(calibration.seeds) >= 5
    assert len(calibration.per_seed_vph_per_lane) == len(calibration.seeds)
    assert 0.0 < calibration.std_vph_per_lane < 0.02 * calibration.mean_vph_per_lane
    reference = REFERENCE_VPH_PER_LANE[turn]
    assert abs(calibration.mean_vph_per_lane - reference) < 0.02 * reference


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
    with pytest.raises(StaleCalibrationError, match="vType"):
        per_lane_saturation_flow_vph(CAR, SPEED_MPS, TurnDirection.THROUGH, table=table)


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


def test_an_unsaturated_source_is_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The saturation check is not vacuous: an under-supplied movement is caught."""
    monkeypatch.setattr(saturation, "SATURATING_DEMAND_VPH_PER_LANE", 300.0)
    with pytest.raises(UnsaturatedCalibrationError, match="not saturated"):
        calibrate_saturation_flow(CAR, SPEED_MPS, TurnDirection.THROUGH, tmp_path)
