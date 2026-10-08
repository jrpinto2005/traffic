"""Trip records as NumPy columns, built once at run end (D-031: compute with NumPy).

Every trip-level metric is a reduction over these arrays, and the primary
delay is defined here exactly once (`delay_s`), for the metrics and for the
MSER-5 series alike (`07_EXPERIMENT_METHODOLOGY.md` SS2.5).

Missing values follow one convention: a float field that is `None` on the
record is `NaN` here, a lane that is `None` is `-1`, and a trip with no exit
has exit code `EXIT_NONE`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from traffic_lab.domain.network import VehicleType
from traffic_lab.domain.trip import TripExit, TripRecord

#: Every canonical vehicle type, in a fixed order; `type_code` indexes it.
VEHICLE_TYPES: tuple[VehicleType, ...] = tuple(VehicleType)
_TYPE_CODE = {vehicle_type: code for code, vehicle_type in enumerate(VEHICLE_TYPES)}

EXIT_NONE, EXIT_SINK, EXIT_MID_LINK = 0, 1, 2
_EXIT_CODE = {None: EXIT_NONE, TripExit.SINK: EXIT_SINK, TripExit.MID_LINK: EXIT_MID_LINK}

Floats = npt.NDArray[np.float64]
Ints = npt.NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class TripColumns:
    type_code: Ints
    scheduled_depart_s: Floats
    depart_s: Floats  # NaN: never inserted
    insertion_delay_s: Floats
    arrival_s: Floats  # NaN: not finished
    travel_time_s: Floats  # NaN: not finished
    time_loss_s: Floats
    waiting_time_s: Floats
    stops: Ints
    depart_lane: Ints  # -1: never inserted
    exit_code: Ints

    @classmethod
    def from_trips(cls, trips: Sequence[TripRecord]) -> TripColumns:
        def floats(values: list[float | None]) -> Floats:
            return np.array([np.nan if v is None else v for v in values], dtype=np.float64)

        def ints(values: list[int]) -> Ints:
            return np.array(values, dtype=np.int64)

        return cls(
            type_code=ints([_TYPE_CODE[t.vehicle_type] for t in trips]),
            scheduled_depart_s=floats([t.scheduled_depart_s for t in trips]),
            depart_s=floats([t.depart_s for t in trips]),
            insertion_delay_s=floats([t.insertion_delay_s for t in trips]),
            arrival_s=floats([t.arrival_s for t in trips]),
            travel_time_s=floats([t.travel_time_s for t in trips]),
            time_loss_s=floats([t.time_loss_s for t in trips]),
            waiting_time_s=floats([t.waiting_time_s for t in trips]),
            stops=ints([t.stops for t in trips]),
            depart_lane=ints([-1 if t.depart_lane is None else int(t.depart_lane) for t in trips]),
            exit_code=ints([_EXIT_CODE[t.exit] for t in trips]),
        )

    def __len__(self) -> int:
        return len(self.type_code)

    @property
    def delay_s(self) -> Floats:
        """The primary delay, `D-006` as amended 2026-10-07: SUMO's `timeLoss` plus
        its `departDelay`. Both parts are reported beside it, always."""
        return self.time_loss_s + self.insertion_delay_s

    @property
    def inserted(self) -> npt.NDArray[np.bool_]:
        return ~np.isnan(self.depart_s)

    @property
    def finished(self) -> npt.NDArray[np.bool_]:
        return ~np.isnan(self.arrival_s)
