"""Invariants 10-12 of `05_DOMAIN_MODEL.md` SS8, which T1.4 owns.

The ownership table assigns these to the backend adapter because
`traffic_lab.domain` uses frozen dataclasses, which "cannot self-validate
cross-field properties". The adapter must therefore **uphold** them when
projecting rather than assume them, and that is what is tested here:

10. Every vehicle is on exactly one lane.
11. `is_halting` <=> `speed_mps < 0.1`.
12. `queue_count` counts exactly the vehicles halting for >= 1 s.

Two complementary levels:

* **Property-based**, over `Projector` directly with generated step sequences.
  Hypothesis is free to put speeds exactly on the 0.1 m/s threshold, to make a
  vehicle halt for exactly 1.0 s, and to churn the population -- the cases a
  live simulation reaches only by luck. The expected queue counts are computed
  by an independent model in the test, not by re-running the implementation.
* **Against a live SUMO run**, so the invariants are also shown to hold on
  states the real simulator produces, over both transports.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.backend.conftest import Scenario, make_config
from traffic_lab.backend import HALTING_SPEED_MPS, QUEUE_MIN_HALTING_S, SumoBackend
from traffic_lab.backend.projection import Projector
from traffic_lab.backend.transport import RawStep, RawVehicle
from traffic_lab.domain.network import VehicleType
from traffic_lab.domain.state import TrueState

LANE_IDS = ("lane_a", "lane_b", "lane_c")
LANE_LENGTHS_M = (100.0, 150.0, 80.0)
STEP_LENGTH_S = 1.0
VEHICLE_IDS = ("v0", "v1", "v2", "v3")

#: Speeds chosen to straddle the 0.1 m/s threshold from both sides, including
#: the exact boundary value -- `is_halting` is `<`, so 0.1 itself is *not*
#: halting, and an implementation using `<=` must fail here.
SPEEDS = st.sampled_from([0.0, 0.05, 0.09999, 0.1, 0.10001, 1.0, 13.89])


def _make_projector() -> Projector:
    return Projector(
        lane_sumo_ids=LANE_IDS,
        lane_lengths_m=LANE_LENGTHS_M,
        intersection_sumo_ids=(),
        vehicle_types=dict.fromkeys(("passenger",), VehicleType.CAR),
        step_length_s=STEP_LENGTH_S,
        gridlock_steps=10,
        max_accel_mps2=2.6,
    )


@st.composite
def step_sequences(draw: st.DrawFn) -> list[dict[str, tuple[str, float]]]:
    """A run as a list of steps, each mapping vehicle id -> (lane, speed).

    Vehicles may appear, disappear and reappear, and may change lane, so the
    projector's admission and retirement paths are exercised alongside the
    halting bookkeeping.
    """
    length = draw(st.integers(min_value=1, max_value=25))
    steps = []
    for _ in range(length):
        present = draw(st.lists(st.sampled_from(VEHICLE_IDS), unique=True, max_size=4))
        steps.append(
            {vehicle_id: (draw(st.sampled_from(LANE_IDS)), draw(SPEEDS)) for vehicle_id in present}
        )
    return steps


def _raw_step(time_s: float, step: dict[str, tuple[str, float]]) -> RawStep:
    return RawStep(
        time_s=time_s,
        vehicles={
            vehicle_id: RawVehicle(
                type_id="passenger",
                lane_id=lane_id,
                lane_position_m=10.0,
                position_x_m=0.0,
                position_y_m=0.0,
                speed_mps=speed,
                time_loss_s=0.0,
                waiting_time_s=0.0,
            )
            for vehicle_id, (lane_id, speed) in step.items()
        },
        signals={},
        arrived_ids=(),
        teleports_ending=0,
        pending=0,
        arrived=0,
    )


def _assert_invariants_10_and_11(state: TrueState) -> None:
    lane_ids = {lane.lane for lane in state.lanes}
    seen = set()
    for vehicle in state.vehicles:
        # 10: on exactly one lane -- one `lane` field, a lane that exists, and
        # the vehicle appearing exactly once in the projection.
        assert vehicle.lane in lane_ids
        assert vehicle.id not in seen
        seen.add(vehicle.id)
        # 11: the biconditional, both directions.
        assert vehicle.is_halting == (vehicle.speed_mps < HALTING_SPEED_MPS)


@settings(max_examples=200, deadline=None)
@given(steps=step_sequences())
def test_invariants_hold_over_generated_step_sequences(
    steps: list[dict[str, tuple[str, float]]],
) -> None:
    projector = _make_projector()
    lane_index = {lane_id: i for i, lane_id in enumerate(LANE_IDS)}
    # Independent oracle: when did each vehicle's current halting run begin?
    halting_since: dict[str, float | None] = {}

    for index, step in enumerate(steps):
        time_s = float(index + 1)
        state = projector.project(_raw_step(time_s, step))

        for vehicle_id in list(halting_since):
            if vehicle_id not in step:
                del halting_since[vehicle_id]
        for vehicle_id, (_lane_id, speed) in step.items():
            if speed < HALTING_SPEED_MPS:
                # A new halting run starts only when the previous step was not
                # halting -- `setdefault` is wrong here, because a vehicle that
                # has halted before carries an explicit `None`.
                if halting_since.get(vehicle_id) is None:
                    halting_since[vehicle_id] = time_s
            else:
                halting_since[vehicle_id] = None

        _assert_invariants_10_and_11(state)

        # 12: queue_count counts exactly the vehicles halting for >= 1 s.
        expected = dict.fromkeys(range(len(LANE_IDS)), 0)
        for vehicle_id, (lane_id, _speed) in step.items():
            since = halting_since[vehicle_id]
            if since is not None and time_s - since >= QUEUE_MIN_HALTING_S:
                expected[lane_index[lane_id]] += 1
        assert {lane.lane: lane.queue_count for lane in state.lanes} == expected


def test_a_vehicle_is_queued_only_from_the_second_second_of_halting() -> None:
    """The >= 1 s condition, at the boundary, spelled out.

    `research/M0_sumo_semantics.md` SS1.3: SUMO's native halting counter applies
    no duration condition, so this is entirely ours and worth pinning down
    rather than leaving to a generated case.
    """
    projector = _make_projector()
    stopped = {"v0": ("lane_a", 0.0)}

    first = projector.project(_raw_step(10.0, stopped))
    assert first.vehicles[0].is_halting
    assert first.vehicles[0].halting_since_s == 10.0
    assert first.lanes[0].queue_count == 0, "halting for 0 s is not yet a queue"

    second = projector.project(_raw_step(11.0, stopped))
    assert second.lanes[0].queue_count == 1, "halting for exactly 1 s is a queue"

    moving = projector.project(_raw_step(12.0, {"v0": ("lane_a", 5.0)}))
    assert moving.vehicles[0].halting_since_s is None
    assert moving.lanes[0].queue_count == 0

    restopped = projector.project(_raw_step(13.0, {"v0": ("lane_a", 0.0)}))
    assert restopped.lanes[0].queue_count == 0, "the timer restarts on a new halt"
    assert restopped.vehicles[0].stop_count == 2, "and the stop is counted"


@pytest.mark.parametrize("transport", ["traci", "libsumo"])
def test_invariants_hold_on_a_live_run(transport: str, scenario: Scenario) -> None:
    """The same three invariants, on states a real SUMO produced.

    The lane aggregates are additionally cross-checked against the vehicles they
    were derived from, which catches a projection that satisfies the invariants
    per-vehicle while reporting lane totals that do not match.
    """
    backend = SumoBackend()
    backend.start(scenario.net, scenario.routes, make_config(transport=transport))
    try:
        saw_a_queue = False
        for _ in range(400):
            backend.step()
            state = backend.project()
            _assert_invariants_10_and_11(state)

            per_lane: dict[int, int] = {}
            for vehicle in state.vehicles:
                queued = (
                    vehicle.halting_since_s is not None
                    and state.time_s - vehicle.halting_since_s >= QUEUE_MIN_HALTING_S
                )
                per_lane[vehicle.lane] = per_lane.get(vehicle.lane, 0) + int(queued)
            for lane in state.lanes:
                assert lane.queue_count == per_lane.get(lane.lane, 0)
                assert lane.queue_count <= lane.vehicle_count
            saw_a_queue |= any(lane.queue_count > 0 for lane in state.lanes)

            assert sum(lane.vehicle_count for lane in state.lanes) == len(state.vehicles)
        assert saw_a_queue, "the scenario never queued, so invariant 12 was never exercised"
    finally:
        backend.close()
