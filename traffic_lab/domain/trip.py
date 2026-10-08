"""One trip as SUMO's tripinfo reports it at run end (D-035).

`TrueState` carries only vehicles still in the network, and a trip's final
values are fixed at the step it disappears, so trip-level metrics -- delay,
travel time, waiting time, stops, approach delay, throughput, completion --
are computed from these records instead (`07_EXPERIMENT_METHODOLOGY.md` SS2,
D-035). The backend builds them from tripinfo written with unfinished and
undeparted vehicles (D-022); `traffic_lab.backend.tripinfo.read_trips` is the
one place that knows the file format.

A record is in exactly one of three states, distinguished by which fields are
`None`:

* **undeparted** -- never inserted: `depart_s`, `depart_lane`, `arrival_s`,
  `travel_time_s`, `arrival_lane` and `exit` are all `None`;
* **unfinished** -- inserted, still in the network when the run ended:
  `arrival_s`, `travel_time_s`, `arrival_lane` and `exit` are `None`;
* **finished** -- arrived, at a boundary sink or mid-link (D-022): nothing is
  `None`.

Times are simulated seconds from the start of the run.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from traffic_lab.domain.network import LaneId, VehicleType


class TripExit(StrEnum):
    """How a finished trip left the network (D-022). Both are served demand."""

    SINK = "sink"  # ran off the end of its final lane: a boundary sink
    MID_LINK = "mid_link"  # removed part-way along its final lane: attrition


@dataclass(frozen=True, slots=True)
class TripRecord:
    vehicle_type: VehicleType
    scheduled_depart_s: float  # when the demand asked the vehicle to enter
    depart_s: float | None  # when it entered; None if it never did
    insertion_delay_s: float  # SUMO `departDelay`; for an undeparted trip, waited so far
    arrival_s: float | None  # None unless finished
    travel_time_s: float | None  # arrival - departure; None unless finished
    time_loss_s: float  # SUMO `timeLoss` (D-006); accumulated so far if unfinished
    waiting_time_s: float  # SUMO `waitingTime`, s below 0.1 m/s, insertion step excluded
    stops: int  # SUMO `waitingCount` (07 SS2.1 as amended 2026-10-07)
    depart_lane: LaneId | None  # None if undeparted
    arrival_lane: LaneId | None  # None unless finished
    exit: TripExit | None  # None unless finished

    @property
    def inserted(self) -> bool:
        """Entered the network: finished or still in it (D-022's denominator)."""
        return self.depart_s is not None

    @property
    def finished(self) -> bool:
        return self.arrival_s is not None
