"""The oracle arm is exact, against the real simulator (T1.9 A5, first criterion).

`OracleSensor` followed by `IdentityEstimator` must reproduce `TrueState`'s lane
counts exactly -- not within a tolerance. If it does not, the oracle arm is not a
control, and every later claim about what a degraded sensor costs is measured
against the wrong baseline.

The scenario is a T1.3-generated intersection with one flow per movement,
driven through the real `SumoBackend`, never a mock (`tests/backend/conftest.py`).
It is run three ways:

* a sample at **every simulation step**;
* a sample every **5 s** (`D-020`'s decision interval) over 1 s steps, which is
  the case `D-033` exists for: a sensor that times halting from its own samples
  would miss up to 5 s of it, and the estimate would disagree with truth;
* a sample every 5 s over **0.5 s** steps, so that the halting clock the oracle
  reads and the clock the projection keeps are compared on sub-second values too.

In every case the projection runs on every step -- its halting bookkeeping needs
it -- while the sensor and estimator run only when a decision is due, exactly as
`06_ARCHITECTURE.md` SS6.2's step loop has them.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from tests.backend.conftest import Scenario, make_config
from traffic_lab.backend import QUEUE_MIN_HALTING_S, SumoBackend
from traffic_lab.domain.network import SensorId
from traffic_lab.estimation import IdentityEstimator
from traffic_lab.sensing import OracleSensor

#: Steps per run, at either step length. Several full cycles of the static
#: program (`Built.static_cycle_s()`, checked below), with a queue on every red, so
#: that queues form, discharge and reform rather than the empty network being
#: compared with itself.
STEPS = 600


@dataclass
class _Coverage:
    """What a run actually compared, so a passing run cannot be a vacuous one."""

    samples: int = 0
    lane_comparisons: int = 0
    max_vehicles: int = 0
    queued_lane_samples: int = 0
    halting_but_not_yet_queued: int = 0
    exactly_at_the_threshold: int = 0
    occupied_zone_lane_samples: int = 0
    empty_zone_lane_samples: int = 0
    vehicles_in_a_lane_but_outside_its_zone: int = 0
    distances_checked: int = 0


def _drive_and_compare(
    scenario: Scenario, *, step_length_s: float, sample_every_s: float
) -> _Coverage:
    backend = SumoBackend()
    backend.start(
        scenario.net,
        scenario.routes,
        make_config(step_length_s=step_length_s, decision_interval_s=sample_every_s),
        network=scenario.network,
    )
    sensor = OracleSensor(SensorId(0), scenario.network)
    estimator = IdentityEstimator(scenario.network)
    lanes = {lane.id: lane for lane in scenario.network.lanes}
    assert {lane.lane for lane in backend.project().lanes} <= lanes.keys()  # T1.3's A2
    coverage = _Coverage()
    next_sample_s = sample_every_s
    try:
        for _ in range(STEPS):
            backend.step()
            state = backend.project()
            if state.time_s < next_sample_s:
                continue
            next_sample_s += sample_every_s

            observation = sensor.observe(state, state.time_s)
            # `state.signals` stands in for the constraint layer's own signal state.
            estimate = estimator.update(observation, state.signals, state.time_s)

            assert estimate.time_s == state.time_s
            assert estimate.signals == state.signals
            assert [e.lane for e in estimate.lanes] == [t.lane for t in state.lanes], (
                f"t={state.time_s}: the estimate does not cover exactly the lanes of the truth"
            )
            for detection, vehicle in zip(observation.detections, state.vehicles, strict=True):
                assert detection.distance_to_stop_m == (
                    lanes[vehicle.lane].length_m - vehicle.position_on_lane_m
                ), f"distance_to_stop_m of vehicle {int(vehicle.id)} at t={state.time_s}"
                coverage.distances_checked += 1
            for estimated, true in zip(estimate.lanes, state.lanes, strict=True):
                where = f"t={state.time_s} lane={int(true.lane)}"
                assert estimated.queue_count == true.queue_count, f"queue_count at {where}"
                assert estimated.vehicle_count == true.vehicle_count, f"vehicle_count at {where}"
                # D-036: counted directly from the truth and the network, not via
                # the sensor or the estimator.
                zone_m = 2.0 * lanes[true.lane].speed_limit_mps
                expected_zone = sum(
                    1
                    for v in state.vehicles
                    if v.lane == true.lane
                    and 0.0 <= lanes[v.lane].length_m - v.position_on_lane_m <= zone_m
                )
                assert estimated.zone_count == expected_zone, f"zone_count at {where}"
                coverage.occupied_zone_lane_samples += expected_zone > 0
                coverage.empty_zone_lane_samples += expected_zone == 0
                coverage.vehicles_in_a_lane_but_outside_its_zone += (
                    true.vehicle_count - expected_zone
                )
                assert estimated.queue_count_std == 0.0, where
                assert estimated.last_observed_s == state.time_s, where
                coverage.lane_comparisons += 1
                coverage.queued_lane_samples += true.queue_count > 0

            coverage.samples += 1
            coverage.max_vehicles = max(coverage.max_vehicles, len(state.vehicles))
            for vehicle in state.vehicles:
                if vehicle.halting_since_s is None:
                    continue
                stationary_s = state.time_s - vehicle.halting_since_s
                coverage.halting_but_not_yet_queued += stationary_s < QUEUE_MIN_HALTING_S
                coverage.exactly_at_the_threshold += stationary_s == QUEUE_MIN_HALTING_S
    finally:
        backend.close()
    return coverage


@pytest.mark.parametrize(
    ("step_length_s", "sample_every_s", "expected_samples"),
    [
        pytest.param(1.0, 1.0, 600, id="every-step"),
        pytest.param(1.0, 5.0, 120, id="dt-5s"),
        pytest.param(0.5, 5.0, 60, id="dt-5s-over-half-second-steps"),
    ],
)
def test_oracle_and_identity_estimator_reproduce_the_true_lane_state_exactly(
    scenario: Scenario,
    step_length_s: float,
    sample_every_s: float,
    expected_samples: int,
) -> None:
    # At least two full cycles of the static program, even at half-second steps.
    assert STEPS * step_length_s >= 2 * scenario.built.static_cycle_s()
    coverage = _drive_and_compare(
        scenario, step_length_s=step_length_s, sample_every_s=sample_every_s
    )

    # The comparisons above all passed. These say they were comparing something.
    assert coverage.samples == expected_samples
    assert coverage.lane_comparisons > 0
    # More vehicles at once than the network holds when nothing waits.
    assert coverage.max_vehicles > scenario.free_flow_population, (
        "the network never filled; nothing was counted"
    )
    assert coverage.queued_lane_samples > 0, "no queue ever formed; queue_count was always 0"
    # D-036: zones are occupied at some sampled steps and empty at others, and
    # vehicles are counted in lanes but kept out of the zone, so neither
    # "everything" nor "nothing" would have passed.
    assert coverage.distances_checked > 0
    assert coverage.occupied_zone_lane_samples > 0
    assert coverage.empty_zone_lane_samples > 0
    assert coverage.vehicles_in_a_lane_but_outside_its_zone > 0
    # D-025's 1 s condition is met from both sides, at the sampled instants: a
    # vehicle seen halting for less than 1 s, and one at exactly 1 s. Agreement on
    # the easy cases alone would not show the threshold is applied correctly.
    assert coverage.halting_but_not_yet_queued > 0
    assert coverage.exactly_at_the_threshold > 0
