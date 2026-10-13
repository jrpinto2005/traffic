"""SUMO's tripinfo output, parsed into canonical `TripRecord`s (D-035).

The backend launches SUMO with `--tripinfo-output.write-unfinished` and
`--write-undeparted` (D-022), so the file holds one record for every vehicle
SUMO loaded: finished, still in the network, and never inserted. This module is
the only code that knows the file's attributes; everything downstream reads
`TripRecord`.

**Semantics measured on SUMO 1.27.1, not taken from documentation** (T1.8,
2026-10-07; `research/M0_sumo_semantics.md` SS3 is why). Checked against the
known schedules of generated flows on the T1.3 intersection, both transports:

* **finished** (`depart >= 0`, `arrival >= 0`): `duration == arrival - depart`;
  `arrivalPos` is the arrival lane's length at a boundary sink, and exactly the
  declared `arrivalPos` for a mid-link arrival.
* **unfinished** (`depart >= 0`, `arrival == -1`): `arrivalLane=""`,
  `arrivalPos=-1`, `duration == end - depart`; `timeLoss`, `waitingTime` and
  `waitingCount` are accumulated so far.
* **undeparted** (`depart == -1`): `departLane=""`; `timeLoss`, `waitingTime`
  and `waitingCount` are 0; `departDelay == end - scheduled`.

`vaporized` is **not** a usable discriminator: some unfinished records carry
`vaporized=""` and others `"end"`. For a departed record the scheduled
departure is `depart - departDelay`; for an undeparted one, `departDelay` is
measured to the instant the file was written, which the file does not record --
hence `end_s` (T1.8 ruling E2).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path

from traffic_lab.backend.adapter import BackendIndex
from traffic_lab.domain.network import LaneId
from traffic_lab.domain.trip import TripExit, TripRecord

#: How close, in metres, a finished trip's `arrivalPos` must be to its arrival
#: lane's length to count as a boundary-sink arrival rather than mid-link. Tripinfo
#: prints positions to two decimals (SUMO's default output precision), so a sink
#: arrival reads within 0.005 m of the length; anything further short of the end
#: was removed by a declared `arrivalPos`, which is D-022's mid-link attrition.
SINK_POSITION_TOLERANCE_M = 0.01

#: Slack on the `end_s` cross-check below. Tripinfo times are printed to 0.01 s.
_TIME_TOLERANCE_S = 0.005


class TripinfoError(ValueError):
    """A tripinfo file that does not describe this run as the backend launched it."""


def read_trips(path: Path, index: BackendIndex, *, end_s: float) -> tuple[TripRecord, ...]:
    """Every trip in `path`, in file order, as canonical records.

    `end_s` is the simulated time at which SUMO was closed -- the `time_s` of
    the last `TrueState` projected -- and is what an undeparted record's
    scheduled departure is recovered from. It is cross-checked against every
    unfinished record (`depart + duration` must equal it), so a wrong value
    raises instead of shifting every scheduled departure.

    Raises `TripinfoError` on a record whose vehicle type is not in
    `index.vehicle_types` (outside the canonical ontology), whose lane is not in
    the network, or whose fields contradict each other.
    """
    lanes = {sumo_id: LaneId(i) for i, sumo_id in enumerate(index.lane_sumo_ids)}
    trips: list[TripRecord] = []
    for _, element in ET.iterparse(path, events=("end",)):
        if element.tag == "tripinfo":
            trips.append(_record(element.attrib, index, lanes, end_s))
            element.clear()
    return tuple(trips)


def _record(
    attrs: Mapping[str, str], index: BackendIndex, lanes: Mapping[str, LaneId], end_s: float
) -> TripRecord:
    vehicle_id = attrs["id"]
    type_id = attrs["vType"]
    vehicle_type = index.vehicle_types.get(type_id)
    if vehicle_type is None:
        raise TripinfoError(
            f"trip {vehicle_id!r} has vType {type_id!r}, whose vClass is outside the canonical "
            f"ontology; known types: {sorted(index.vehicle_types)}"
        )

    depart = float(attrs["depart"])
    arrival = float(attrs["arrival"])
    insertion_delay_s = float(attrs["departDelay"])

    depart_s: float | None = None
    depart_lane: LaneId | None = None
    arrival_s: float | None = None
    travel_time_s: float | None = None
    arrival_lane: LaneId | None = None
    exit_: TripExit | None = None

    if depart < 0:  # undeparted
        if arrival >= 0:
            raise TripinfoError(f"trip {vehicle_id!r} arrived without departing: {dict(attrs)}")
        scheduled_depart_s = end_s - insertion_delay_s
    else:
        depart_s = depart
        depart_lane = _lane(attrs["departLane"], lanes, vehicle_id)
        scheduled_depart_s = depart - insertion_delay_s
        if arrival < 0:  # unfinished
            written_at_s = depart + float(attrs["duration"])
            if abs(written_at_s - end_s) > _TIME_TOLERANCE_S:
                raise TripinfoError(
                    f"unfinished trip {vehicle_id!r} was written at t={written_at_s} "
                    f"(depart + duration), but end_s={end_s}; end_s must be the simulated time "
                    f"at which SUMO was closed, or every undeparted trip's scheduled departure "
                    f"is wrong"
                )
        else:  # finished
            arrival_s = arrival
            travel_time_s = float(attrs["duration"])
            arrival_lane = _lane(attrs["arrivalLane"], lanes, vehicle_id)
            assert arrival_lane is not None
            reached_end = (
                float(attrs["arrivalPos"])
                >= index.lane_lengths_m[arrival_lane] - SINK_POSITION_TOLERANCE_M
            )
            exit_ = TripExit.SINK if reached_end else TripExit.MID_LINK

    return TripRecord(
        vehicle_type=vehicle_type,
        scheduled_depart_s=scheduled_depart_s,
        depart_s=depart_s,
        insertion_delay_s=insertion_delay_s,
        arrival_s=arrival_s,
        travel_time_s=travel_time_s,
        time_loss_s=float(attrs["timeLoss"]),
        waiting_time_s=float(attrs["waitingTime"]),
        stops=int(attrs["waitingCount"]),
        depart_lane=depart_lane,
        arrival_lane=arrival_lane,
        exit=exit_,
    )


def _lane(sumo_id: str, lanes: Mapping[str, LaneId], vehicle_id: str) -> LaneId | None:
    if not sumo_id:
        return None
    lane = lanes.get(sumo_id)
    if lane is None:
        raise TripinfoError(
            f"trip {vehicle_id!r} names lane {sumo_id!r}, which is not in this run's network"
        )
    return lane
