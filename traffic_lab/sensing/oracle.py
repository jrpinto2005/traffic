"""The oracle sensor: perfect observation, as a sensor and not a bypass.

`06_ARCHITECTURE.md` SS4.1. Detection probability 1.0, zero noise, zero latency:
one `Detection` per vehicle, covering every lane. It is the experimental control
of the sensing axis -- the arm against which M3's degraded sensors are measured --
not a shortcut, and it returns the same `Observation` type as any other sensor.

Two of its outputs deserve a note, because they are what keep the oracle exact
under `D-033`:

* `lane` is copied from the vehicle. The domain has no lane geometry on which a
  position could be placed, so the sensor's lane assignment is a field of the
  detection rather than something an estimator derives.
* `stationary_s` is `time_s - halting_since_s`, i.e. D-025's continuous-halting
  clock, taken from `TrueState` where it is tracked every simulation step.
  A sensor sampling only every decision interval could not rebuild it from its
  own samples, and an oracle that disagreed with truth would not be one.

* `distance_to_stop_m` (`D-036`) is the lane's length from the `Network` minus the
  vehicle's `position_on_lane_m`.

`OracleSensor` takes no noise, latency or dropout parameters, not even disabled
ones: its zero error is structural, which is the point of calling it the oracle.
"""

from __future__ import annotations

from traffic_lab.domain.network import LaneId, Network, SensorId
from traffic_lab.domain.observation import Detection, Observation
from traffic_lab.domain.state import TrueState, VehicleState


class OracleSensor:
    """Perfect observation of every vehicle on every lane."""

    def __init__(self, sensor: SensorId, network: Network) -> None:
        self._sensor = sensor
        self._lane_length_m: dict[LaneId, float] = {
            lane.id: lane.length_m for lane in network.lanes
        }

    def observe(self, state: TrueState, now_s: float) -> Observation:
        """Observe `state` exactly.

        Raises `ValueError` if `now_s` is not `state.time_s`: the oracle has zero
        latency, so an observation taken at any other time would be of a state it
        is not looking at.
        """
        if now_s != state.time_s:
            raise ValueError(
                f"the oracle has zero latency, so it observes only the current state: "
                f"now_s={now_s!r} but state.time_s={state.time_s!r}"
            )
        return Observation(
            received_at_s=state.time_s,
            detections=tuple(self._detect(vehicle, state.time_s) for vehicle in state.vehicles),
            observed_lanes=frozenset(lane.lane for lane in state.lanes),
        )

    def _detect(self, vehicle: VehicleState, time_s: float) -> Detection:
        return Detection(
            sensor=self._sensor,
            observed_at_s=time_s,
            position_xy=vehicle.position_xy,
            position_cov=(0.0, 0.0, 0.0),
            speed_mps=vehicle.speed_mps,
            speed_std=0.0,
            vehicle_class=vehicle.type,
            class_confidence=1.0,
            track_id=int(vehicle.id),
            lane=vehicle.lane,
            stationary_s=(
                0.0 if vehicle.halting_since_s is None else time_s - vehicle.halting_since_s
            ),
            distance_to_stop_m=self._lane_length_m[vehicle.lane] - vehicle.position_on_lane_m,
        )
