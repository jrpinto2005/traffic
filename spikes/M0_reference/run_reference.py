#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

from sumolib import checkBinary

import traci


BASE = Path(__file__).resolve().parent
NET = BASE / "reference.net.xml"


def build_net() -> None:
    cmd = [
        checkBinary("netconvert"),
        "--node-files",
        str(BASE / "reference.nod.xml"),
        "--edge-files",
        str(BASE / "reference.edg.xml"),
        "--connection-files",
        str(BASE / "reference.con.xml"),
        "--tllogic-files",
        str(BASE / "reference.tll.xml"),
        "--output-file",
        str(NET),
    ]
    subprocess.run(cmd, check=True, cwd=BASE)


def ensure_net() -> None:
    build_net()


def lane_ids() -> list[str]:
    return sorted(lane_id for lane_id in traci.lane.getIDList() if not lane_id.startswith(":"))


def print_step() -> None:
    now_s = traci.simulation.getTime()
    tls_state = traci.trafficlight.getRedYellowGreenState("j1")
    print(f"step={int(now_s)} tls={tls_state}")

    for lane_id in lane_ids():
        halting = traci.lane.getLastStepHaltingNumber(lane_id)
        occupancy = traci.lane.getLastStepOccupancy(lane_id)
        waiting = traci.lane.getWaitingTime(lane_id)
        print(f"  lane={lane_id} halting={halting} occupancy={occupancy:.3f} waiting={waiting:.1f}")

    for veh_id in sorted(traci.vehicle.getIDList()):
        lane_id = traci.vehicle.getLaneID(veh_id)
        x, y = traci.vehicle.getPosition(veh_id)
        print(
            "  veh="
            f"{veh_id} lane={lane_id} type={traci.vehicle.getTypeID(veh_id)} "
            f"pos=({x:.1f},{y:.1f}) speed={traci.vehicle.getSpeed(veh_id):.2f} "
            f"timeLoss={traci.vehicle.getTimeLoss(veh_id):.1f} "
            f"waitingTime={traci.vehicle.getWaitingTime(veh_id):.1f}"
        )


def main() -> int:
    ensure_net()
    sumo_binary = checkBinary("sumo")
    traci.start(
        [
            sumo_binary,
            "-c",
            str(BASE / "reference.sumocfg"),
            "--start",
            "--quit-on-end",
            "--no-step-log",
            "true",
            "--duration-log.disable",
            "true",
            "--time-to-teleport",
            "-1",
        ],
    )
    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            print_step()
    finally:
        traci.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
