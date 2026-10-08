"""Trip-level and network-level metrics over one group of trips (07 SS2).

One group is either every trip (the aggregate) or one vehicle type's
(SS2.4): the same function computes both, so the per-type figures cannot be
defined differently from the aggregate ones.

Definitions, as pinned by T1.8 Amendment A2:

* **Completed in the window** -- arrival time in `[start_s, end_s)`, at a
  boundary sink or mid-link (D-022). Mean delay, its two parts, travel time,
  waiting time, stops, approach delay and throughput are over these trips.
* **Delay** -- `timeLoss + departDelay` (D-006 as amended), with both parts
  beside it.
* **Still in network** -- vehicles in the `TrueState` at the instant the window
  closes. Completion rate = completed / (completed + still in network).
* **Total time loss** -- the completed trips' `timeLoss` plus the time loss
  accumulated so far by the vehicles still in the network at window close
  (SS2.3: "the mean alone hides unserved demand").
* **Approach delay** -- mean primary delay (`timeLoss + departDelay`) of the
  completed trips, by the edge their departure lane belongs to, with both
  components beside it (SS2.2 as amended 2026-10-07; A2: "by departure lane's
  approach"). Insertion delay is the approach's own spillback.

A mean over no trips is `None`, not 0: an empty sample has no mean.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from traffic_lab.domain.network import EdgeId
from traffic_lab.metrics.columns import EXIT_MID_LINK, EXIT_SINK, Floats, Ints, TripColumns
from traffic_lab.metrics.phases import MeasurementWindow

_SECONDS_PER_HOUR = 3600.0


@dataclass(frozen=True, slots=True)
class InNetwork:
    """One group's vehicles in the network at the instant the window closes."""

    count: int  # vehicles
    time_loss_s: float  # their summed time loss so far, seconds


@dataclass(frozen=True, slots=True)
class ApproachDelay:
    """One approach's mean primary delay over its completed trips, and its parts."""

    delay_s: float  # timeLoss + departDelay
    time_loss_s: float
    insertion_delay_s: float


@dataclass(frozen=True, slots=True)
class TripMetrics:
    completed: int  # vehicles; arrived in the window, sink or mid-link
    arrived_at_sink: int  # vehicles; of `completed`
    arrived_mid_link: int  # vehicles; of `completed`
    still_in_network: int  # vehicles; at window close
    completion_rate: float | None  # fraction; None if no vehicle was served or waiting
    throughput_veh_per_h: float
    mean_delay_s: float | None  # timeLoss + departDelay
    mean_time_loss_s: float | None
    mean_insertion_delay_s: float | None
    mean_travel_time_s: float | None
    mean_waiting_time_s: float | None
    mean_stops: float | None  # stops per vehicle
    total_time_loss_veh_h: float
    approach_delay: Mapping[EdgeId, ApproachDelay]  # by departure edge


def trip_metrics(
    columns: TripColumns,
    group: npt.NDArray[np.bool_],
    window: MeasurementWindow,
    in_network: InNetwork,
    lane_edge: Ints,
) -> TripMetrics:
    """The SS2 trip and network metrics of the trips selected by `group`.

    `lane_edge[i]` is the `EdgeId` of `LaneId(i)`.
    """
    arrival = columns.arrival_s
    with np.errstate(invalid="ignore"):  # NaN arrivals compare False, as intended
        completed = group & (arrival >= window.start_s) & (arrival < window.end_s)
    n_completed = int(completed.sum())

    def mean(values: Floats | Ints) -> float | None:
        return float(values[completed].mean()) if n_completed else None

    served_and_waiting = n_completed + in_network.count
    total_time_loss_s = float(columns.time_loss_s[completed].sum()) + in_network.time_loss_s

    return TripMetrics(
        completed=n_completed,
        arrived_at_sink=int((completed & (columns.exit_code == EXIT_SINK)).sum()),
        arrived_mid_link=int((completed & (columns.exit_code == EXIT_MID_LINK)).sum()),
        still_in_network=in_network.count,
        completion_rate=n_completed / served_and_waiting if served_and_waiting else None,
        throughput_veh_per_h=n_completed / (window.duration_s / _SECONDS_PER_HOUR),
        mean_delay_s=mean(columns.delay_s),
        mean_time_loss_s=mean(columns.time_loss_s),
        mean_insertion_delay_s=mean(columns.insertion_delay_s),
        mean_travel_time_s=mean(columns.travel_time_s),
        mean_waiting_time_s=mean(columns.waiting_time_s),
        mean_stops=mean(columns.stops),
        total_time_loss_veh_h=total_time_loss_s / _SECONDS_PER_HOUR,
        approach_delay=_approach_delay(columns, completed, lane_edge),
    )


def _approach_delay(
    columns: TripColumns, completed: npt.NDArray[np.bool_], lane_edge: Ints
) -> dict[EdgeId, ApproachDelay]:
    edges = lane_edge[columns.depart_lane[completed]]
    delay = columns.delay_s[completed]
    time_loss = columns.time_loss_s[completed]
    insertion_delay = columns.insertion_delay_s[completed]
    approaches: dict[EdgeId, ApproachDelay] = {}
    for edge in np.unique(edges):
        on_edge = edges == edge
        approaches[EdgeId(int(edge))] = ApproachDelay(
            delay_s=float(delay[on_edge].mean()),
            time_loss_s=float(time_loss[on_edge].mean()),
            insertion_delay_s=float(insertion_delay[on_edge].mean()),
        )
    return approaches
