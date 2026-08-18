#!/usr/bin/env python3
from __future__ import annotations

import statistics as stats
import time
from pathlib import Path

import traci as traci_api
import traci.constants as tc
from sumolib import checkBinary

import libsumo as libsumo_api


BASE = Path(__file__).resolve().parent
SUMOCFG = str(BASE / "reference.sumocfg")
SUMO_BIN = checkBinary("sumo")


def run(api, subscription: bool) -> float:
    api.start(
        [
            SUMO_BIN,
            "-c",
            SUMOCFG,
            "--start",
            "--quit-on-end",
            "--no-step-log",
            "true",
            "--duration-log.disable",
            "true",
            "--no-warnings",
            "true",
            "--time-to-teleport",
            "-1",
        ]
    )
    known = set()
    lane_ids = [lane_id for lane_id in api.lane.getIDList() if not lane_id.startswith(":")]
    tls_id = "j1"
    if subscription:
        for lane_id in lane_ids:
            api.lane.subscribe(
                lane_id, [tc.LAST_STEP_VEHICLE_HALTING_NUMBER, tc.LAST_STEP_OCCUPANCY]
            )
        api.trafficlight.subscribe(tls_id, [tc.TL_RED_YELLOW_GREEN_STATE])

    start = time.perf_counter()
    try:
        while api.simulation.getMinExpectedNumber() > 0:
            api.simulationStep()
            veh_ids = api.vehicle.getIDList()
            if subscription:
                for veh_id in veh_ids:
                    if veh_id not in known:
                        api.vehicle.subscribe(
                            veh_id,
                            [
                                tc.VAR_POSITION,
                                tc.VAR_SPEED,
                                tc.VAR_TYPE,
                                tc.VAR_LANE_ID,
                                tc.VAR_TIMELOSS,
                                tc.VAR_WAITING_TIME,
                            ],
                        )
                        known.add(veh_id)
                for lane_id in lane_ids:
                    api.lane.getSubscriptionResults(lane_id)
                api.trafficlight.getSubscriptionResults(tls_id)
                for veh_id in veh_ids:
                    api.vehicle.getSubscriptionResults(veh_id)
            else:
                for lane_id in lane_ids:
                    api.lane.getLastStepVehicleNumber(lane_id)
                    api.lane.getLastStepHaltingNumber(lane_id)
                    api.lane.getLastStepOccupancy(lane_id)
                api.trafficlight.getRedYellowGreenState(tls_id)
                for veh_id in veh_ids:
                    api.vehicle.getPosition(veh_id)
                    api.vehicle.getSpeed(veh_id)
                    api.vehicle.getTypeID(veh_id)
                    api.vehicle.getLaneID(veh_id)
                    api.vehicle.getTimeLoss(veh_id)
                    api.vehicle.getWaitingTime(veh_id)
    finally:
        elapsed = time.perf_counter() - start
        api.close()
    return elapsed


def measure(api, subscription: bool, reps: int = 2) -> list[float]:
    return [run(api, subscription) for _ in range(reps)]


def main() -> None:
    results = {
        ("TraCI", "polling"): measure(traci_api, False),
        ("TraCI", "subscriptions"): measure(traci_api, True),
        ("LibSUMO", "polling"): measure(libsumo_api, False),
        ("LibSUMO", "subscriptions"): measure(libsumo_api, True),
    }
    for (backend, mode), values in results.items():
        print(
            backend,
            mode,
            "mean",
            stats.mean(values),
            "stdev",
            stats.stdev(values),
            "samples",
            values,
        )


if __name__ == "__main__":
    main()
