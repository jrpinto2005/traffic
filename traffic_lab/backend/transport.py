"""The two SUMO transports, and the raw per-step record they both produce.

Implements D-002 (one interface, two interchangeable transports) and D-031 as
amended 2026-08-18.

**What is invariant, and what is not.** The architectural rule is that the
adapter performs *one batched projection per simulation step* and exposes *no
per-object query method* to any other layer. That rule is upheld here: the only
state-reading method on a transport is `fetch()`, which returns the whole step
at once. **How** a transport batches is an implementation detail chosen by
measurement, and the measurements disagree by transport
(`research/M0_performance.md`, per simulated hour on the M0 reference scenario):

| Transport | Subscriptions | Per-object getters |
| --- | --- | --- |
| TraCI   | **7.30 s** | 71.05 s |
| LibSUMO | 2.57 s | **1.49 s** |

TraCI pays a socket round-trip per call, so subscriptions — whose results ride
along with the step response — are ~10x faster. LibSUMO is an in-process
binding with no socket, so subscription bookkeeping is pure overhead and direct
getters win by ~1.7x. LibSUMO is the transport intended for every heavy
workload, so mandating subscriptions everywhere would have taxed exactly the
runs that matter. Hence: subscriptions under TraCI, direct batched getters
under LibSUMO.

The two are kept honest by `tests/backend/test_transport_equivalence.py`, which
asserts byte-identical `TrueState` sequences across transports. Both build the
same `RawStep`, and all projection logic lives in `projection.py` downstream of
it, so that test exercises precisely the part that differs.

`traci` and `libsumo` are imported here and in no other package
(`06_ARCHITECTURE.md` §10 rule 2, asserted by `tests/backend/test_import_boundary.py`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple, Protocol

import libsumo
import traci
import traci.constants as tc

# --- The raw step ------------------------------------------------------------
# NamedTuples rather than dataclasses: one is allocated per vehicle per step, and
# D-031's anti-pattern list names per-vehicle object churn in the step loop. A
# NamedTuple is a tuple, which is the cheapest record Python has.


class RawVehicle(NamedTuple):
    """One vehicle's SUMO state for one step, before canonicalisation."""

    type_id: str
    lane_id: str
    lane_position_m: float
    position_x_m: float
    position_y_m: float
    speed_mps: float
    time_loss_s: float
    waiting_time_s: float


class RawSignal(NamedTuple):
    """One traffic light's SUMO state for one step, before canonicalisation."""

    phase_index: int
    ryg_state: str
    spent_duration_s: float


class RawStep(NamedTuple):
    """Everything one batched fetch returns.

    `vehicles` is keyed by SUMO vehicle ID and is authoritative for which
    vehicles are currently in the network; the projector reconciles its own
    active set against it rather than trusting the departed/arrived lists.
    """

    time_s: float
    vehicles: dict[str, RawVehicle]
    signals: dict[str, RawSignal]
    arrived_ids: tuple[str, ...]
    teleports_ending: int
    loaded: int
    departed: int
    arrived: int


class Transport(Protocol):
    """The `D-002` seam. Two implementations; no third without a register entry."""

    def start(self, argv: list[str]) -> None: ...

    def register(self, tls_ids: tuple[str, ...]) -> None:
        """Prepare for stepping, given the traffic lights whose state is projected."""

    def step(self) -> None: ...

    def fetch(self) -> RawStep:
        """The single batched state read. The only state-reading method that exists."""

    def apply_ryg_state(self, tls_sumo_id: str, ryg_state: str) -> None: ...

    def lane_ids(self) -> tuple[str, ...]: ...

    def lane_length_m(self, lane_sumo_id: str) -> float: ...

    def traffic_light_ids(self) -> tuple[str, ...]: ...

    def vehicle_type_ids(self) -> tuple[str, ...]: ...

    def vehicle_class(self, type_id: str) -> str: ...

    def vehicle_accel_mps2(self, type_id: str) -> float: ...

    def option(self, name: str) -> str: ...

    def version(self) -> str: ...

    def save_state(self, path: Path) -> None: ...

    def load_state(self, path: Path) -> None: ...

    def close(self) -> None: ...


# --- Shared, transport-independent parts -------------------------------------
# The two transports differ only in `register` and `fetch`. Everything else is a
# call with an identical signature on either module (D-002: "the signatures
# match, so the abstraction is nearly free"), so it is written once here. This
# base has two subclasses, not one — the shape `D-031`'s anti-pattern list
# forbids is a base class with a single subclass.


class _SumoTransport:
    """Calls that TraCI and LibSUMO implement identically."""

    _api: Any

    def __init__(self) -> None:
        self._tls_ids: tuple[str, ...] = ()

    def register(self, tls_ids: tuple[str, ...]) -> None:
        self._tls_ids = tls_ids

    def start(self, argv: list[str]) -> None:
        self._api.start(argv)

    def step(self) -> None:
        self._api.simulationStep()

    def apply_ryg_state(self, tls_sumo_id: str, ryg_state: str) -> None:
        self._api.trafficlight.setRedYellowGreenState(tls_sumo_id, ryg_state)

    def lane_ids(self) -> tuple[str, ...]:
        # Internal (`:`-prefixed) lanes are included. A vehicle crossing the
        # junction is genuinely on one of them, and `05_DOMAIN_MODEL.md` §8
        # invariant 10 requires every vehicle to be on exactly one lane -- a lane
        # that must therefore exist in the projection.
        return tuple(sorted(self._api.lane.getIDList()))

    def lane_length_m(self, lane_sumo_id: str) -> float:
        return float(self._api.lane.getLength(lane_sumo_id))

    def traffic_light_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._api.trafficlight.getIDList()))

    def vehicle_type_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._api.vehicletype.getIDList()))

    def vehicle_class(self, type_id: str) -> str:
        return str(self._api.vehicletype.getVehicleClass(type_id))

    def vehicle_accel_mps2(self, type_id: str) -> float:
        return float(self._api.vehicletype.getAccel(type_id))

    def option(self, name: str) -> str:
        return str(self._api.simulation.getOption(name))

    def version(self) -> str:
        return str(self._api.getVersion()[1])

    def save_state(self, path: Path) -> None:
        self._api.simulation.saveState(str(path))

    def load_state(self, path: Path) -> None:
        self._api.simulation.loadState(str(path))

    def close(self) -> None:
        self._api.close()


# --- TraCI: subscriptions ----------------------------------------------------

#: The per-vehicle variables `TrueState` needs, in one subscription.
_VEHICLE_VARS = (
    tc.VAR_TYPE,
    tc.VAR_LANE_ID,
    tc.VAR_LANEPOSITION,
    tc.VAR_POSITION,
    tc.VAR_SPEED,
    tc.VAR_TIMELOSS,
    tc.VAR_WAITING_TIME,
)

#: Per traffic light. `TL_SPENT_DURATION` is what makes `SignalState.phase_started_s`
#: exact after a snapshot load, where our own bookkeeping would not survive.
_TLS_VARS = (tc.TL_CURRENT_PHASE, tc.TL_RED_YELLOW_GREEN_STATE, tc.TL_SPENT_DURATION)

#: The validity and accounting counters, in one `simulation.subscribe` call, at
#: zero per-step cost -- `research/M0_prior_art.md` §9.3 item 3. PyTSC's list also
#: carries `n_colliding` and `n_emergency_brakes`; those are omitted because
#: `RunCounters` (D-008) has no field for them and unread data is exactly the
#: abstraction tax D-003's inclusion test exists to refuse. Adding them is a
#: domain-model change, not a backend one.
_SIMULATION_VARS = (
    tc.VAR_TIME,
    tc.VAR_DEPARTED_VEHICLES_IDS,
    tc.VAR_ARRIVED_VEHICLES_IDS,
    tc.VAR_TELEPORT_ENDING_VEHICLES_NUMBER,
    tc.VAR_LOADED_VEHICLES_NUMBER,
    tc.VAR_DEPARTED_VEHICLES_NUMBER,
    tc.VAR_ARRIVED_VEHICLES_NUMBER,
)


class TraciTransport(_SumoTransport):
    """Subscriptions, registered once and read whole.

    Measured ~10x faster than per-object polling on TraCI, because every
    subscription result arrives with the step response rather than costing its
    own socket round-trip.

    Per step this makes exactly three result-reading calls — one each for
    simulation, vehicle and traffic-light subscriptions — regardless of how many
    vehicles are in the network. The only calls that scale are
    `vehicle.subscribe` for vehicles that departed *this step*, which is a
    registration, not a read, and is bounded by the departure rate rather than
    by the population.
    """

    def __init__(self) -> None:
        super().__init__()
        self._api = traci

    def register(self, tls_ids: tuple[str, ...]) -> None:
        super().register(tls_ids)
        traci.simulation.subscribe(list(_SIMULATION_VARS))
        for tls_id in tls_ids:
            traci.trafficlight.subscribe(tls_id, list(_TLS_VARS))

    def load_state(self, path: Path) -> None:
        """Load, then re-register every subscription.

        **SUMO drops all TraCI subscriptions when a state is loaded**, silently:
        the next `getSubscriptionResults()` returns an empty dict rather than
        raising. Measured on 1.27.1 -- simulation, traffic-light and per-vehicle
        subscriptions were all gone after one step past a `loadState`.

        Re-registering the simulation and traffic-light subscriptions is not
        enough on its own. `fetch()` learns about new vehicles from
        `VAR_DEPARTED_VEHICLES_IDS`, and the vehicles restored by a snapshot
        departed long before it was taken, so they would never be re-subscribed
        and would simply be missing from every subsequent projection. The
        population present at load is therefore subscribed explicitly here --
        once per load, not per step, so the batching constraint is untouched.

        LibSUMO needs none of this because it subscribes to nothing. That is a
        difference in *mechanism*, which is what the D-002 seam exists to
        absorb; `tests/backend/test_counters_and_snapshots.py` asserts the
        observable behaviour is identical across both.
        """
        super().load_state(path)
        self.register(self._tls_ids)
        for vehicle_id in traci.vehicle.getIDList():
            traci.vehicle.subscribe(vehicle_id, list(_VEHICLE_VARS))

    def fetch(self) -> RawStep:
        simulation_result = traci.simulation.getSubscriptionResults()
        # Newly departed vehicles are subscribed the step they appear; SUMO
        # returns their first result immediately and drops the subscription
        # itself when the vehicle leaves, so `getAllSubscriptionResults()` is
        # exactly the live population with no membership bookkeeping of ours.
        for vehicle_id in simulation_result[tc.VAR_DEPARTED_VEHICLES_IDS]:
            traci.vehicle.subscribe(vehicle_id, list(_VEHICLE_VARS))

        vehicle_results = traci.vehicle.getAllSubscriptionResults()
        signal_results = traci.trafficlight.getAllSubscriptionResults()

        vehicles = {}
        for vehicle_id, values in vehicle_results.items():
            position = values[tc.VAR_POSITION]
            vehicles[vehicle_id] = RawVehicle(
                type_id=values[tc.VAR_TYPE],
                lane_id=values[tc.VAR_LANE_ID],
                lane_position_m=values[tc.VAR_LANEPOSITION],
                position_x_m=position[0],
                position_y_m=position[1],
                speed_mps=values[tc.VAR_SPEED],
                time_loss_s=values[tc.VAR_TIMELOSS],
                waiting_time_s=values[tc.VAR_WAITING_TIME],
            )

        signals = {
            tls_id: RawSignal(
                phase_index=values[tc.TL_CURRENT_PHASE],
                ryg_state=values[tc.TL_RED_YELLOW_GREEN_STATE],
                spent_duration_s=values[tc.TL_SPENT_DURATION],
            )
            for tls_id, values in signal_results.items()
        }

        return RawStep(
            time_s=simulation_result[tc.VAR_TIME],
            vehicles=vehicles,
            signals=signals,
            arrived_ids=tuple(simulation_result[tc.VAR_ARRIVED_VEHICLES_IDS]),
            teleports_ending=simulation_result[tc.VAR_TELEPORT_ENDING_VEHICLES_NUMBER],
            loaded=simulation_result[tc.VAR_LOADED_VEHICLES_NUMBER],
            departed=simulation_result[tc.VAR_DEPARTED_VEHICLES_NUMBER],
            arrived=simulation_result[tc.VAR_ARRIVED_VEHICLES_NUMBER],
        )


# --- LibSUMO: direct batched getters -----------------------------------------


class LibsumoTransport(_SumoTransport):
    """Direct getters, batched into one `fetch()`.

    Measured ~1.7x *faster* than subscriptions here: LibSUMO is in-process, so
    there is no round-trip for a subscription to amortise and the bookkeeping is
    a net cost. The call count therefore scales with the vehicle population by
    design — but it is still one batched projection per step, and no per-object
    getter is reachable from outside this module.
    """

    def __init__(self) -> None:
        super().__init__()
        self._api = libsumo

    def fetch(self) -> RawStep:
        simulation = libsumo.simulation
        vehicle = libsumo.vehicle

        vehicles = {}
        for vehicle_id in vehicle.getIDList():
            position = vehicle.getPosition(vehicle_id)
            vehicles[vehicle_id] = RawVehicle(
                type_id=vehicle.getTypeID(vehicle_id),
                lane_id=vehicle.getLaneID(vehicle_id),
                lane_position_m=vehicle.getLanePosition(vehicle_id),
                position_x_m=position[0],
                position_y_m=position[1],
                speed_mps=vehicle.getSpeed(vehicle_id),
                time_loss_s=vehicle.getTimeLoss(vehicle_id),
                waiting_time_s=vehicle.getWaitingTime(vehicle_id),
            )

        trafficlight = libsumo.trafficlight
        signals = {
            tls_id: RawSignal(
                phase_index=trafficlight.getPhase(tls_id),
                ryg_state=trafficlight.getRedYellowGreenState(tls_id),
                spent_duration_s=trafficlight.getSpentDuration(tls_id),
            )
            for tls_id in self._tls_ids
        }

        return RawStep(
            time_s=simulation.getTime(),
            vehicles=vehicles,
            signals=signals,
            arrived_ids=tuple(simulation.getArrivedIDList()),
            teleports_ending=simulation.getEndingTeleportNumber(),
            loaded=simulation.getLoadedNumber(),
            departed=simulation.getDepartedNumber(),
            arrived=simulation.getArrivedNumber(),
        )
