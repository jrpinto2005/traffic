"""`MetricAccumulator`: step-level collection during the run, every metric at its end.

The two sources of D-035 meet here:

* **Every step**, `accumulate(state)` reads `TrueState`. During the measurement
  window it appends one row of per-lane queue counts -- D-025's queue, already
  computed by the backend as `LaneState.queue_count` and not recomputed here
  (`07_EXPERIMENT_METHODOLOGY.md` SS2.5). At the instant the window closes it
  takes one snapshot: the vehicles still in the network, their time loss so
  far, and SUMO's pending-insertion count. Nothing else happens in the step
  loop: no per-vehicle work, no metric arithmetic, no I/O (D-031).
* **At run end**, `finalize(trips)` takes the `TripRecord`s parsed from tripinfo
  and computes everything with NumPy: the trip and network metrics, in
  aggregate and per vehicle type; the lane queue metrics; the validity gate;
  invariant 14; and MSER-5's truncation.

**Calling convention.** `accumulate` is called with every projected state, from
the first step to the last, in order -- the last one it sees is the run's end
state, whose counters the validity gate reads. One state must fall exactly on
the window's end: that is the instant "at window close" refers to (a vehicle is
in the state stamped `T` iff it departed before `T` and has not arrived before
`T`, so completed-in-window and still-in-network at `end_s` partition the
trips with no overlap and no gap).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from operator import attrgetter

import numpy as np

from traffic_lab.domain.network import Network, VehicleType
from traffic_lab.domain.state import TrueState
from traffic_lab.domain.trip import TripRecord
from traffic_lab.metrics.columns import EXIT_MID_LINK, VEHICLE_TYPES, TripColumns
from traffic_lab.metrics.mser import warmup_from_columns
from traffic_lab.metrics.phases import MeasurementWindow
from traffic_lab.metrics.trips import InNetwork, TripMetrics, trip_metrics
from traffic_lab.metrics.validity import Validity, assess_validity, check_trip_accounting

_QUEUE_COUNT = attrgetter("queue_count")

#: Slack when matching a state's time to the window's end. SUMO's clock is in
#: integer milliseconds, so a state either lands on the end or misses it by a
#: whole step.
_TIME_TOLERANCE_S = 1e-6

#: The aggregate's name in `MetricResult.to_row()`; each type is named by its value.
AGGREGATE = "all"

RowValue = float | int | bool | str | None


@dataclass(frozen=True, slots=True)
class _WindowClose:
    """What `TrueState` says at the instant the window closes."""

    pending: int  # vehicles; SUMO's pending-insertion list
    in_network: dict[VehicleType, InNetwork]


@dataclass(frozen=True, slots=True)
class MetricResult:
    """One run's metrics. Invalid runs carry all of them too, with their causes."""

    window: MeasurementWindow
    validity: Validity
    aggregate: TripMetrics
    by_type: Mapping[VehicleType, TripMetrics]  # every VehicleType, present or not
    queue_mean_veh: tuple[float, ...]  # by LaneId; time-average over the window
    max_queue_veh: tuple[int, ...]  # by LaneId; maximum over the window
    mid_link_arrivals_tripinfo: int  # vehicles, whole run; authoritative (D-035)
    mid_link_arrivals_kinematic: int  # vehicles, whole run; RunCounters' estimate
    mser5_truncation_s: float | None  # None when too few trips to batch

    def to_row(self) -> dict[str, RowValue]:
        """One flat row, every key naming its metric and unit, for the run's results."""
        validity = self.validity
        row: dict[str, RowValue] = {
            "window_start_s": self.window.start_s,
            "window_end_s": self.window.end_s,
            "valid": validity.valid,
            "invalid_causes": ",".join(validity.causes),
            "teleports": validity.teleports,
            "gridlock_detected": validity.gridlock_detected,
            "snapshot_mismatch": validity.snapshot_mismatch,
            "pending_at_window_close": validity.pending_at_window_close,
            "due_in_window": validity.due_in_window,
            "insertion_loss": validity.insertion_loss,
            "mid_link_arrivals_tripinfo": self.mid_link_arrivals_tripinfo,
            "mid_link_arrivals_kinematic": self.mid_link_arrivals_kinematic,
            "mser5_truncation_s": self.mser5_truncation_s,
        }
        groups = {AGGREGATE: self.aggregate} | {str(t): m for t, m in self.by_type.items()}
        for name, metrics in groups.items():
            for field in fields(TripMetrics):
                if field.name != "approach_delay_s":
                    row[f"{name}.{field.name}"] = getattr(metrics, field.name)
            for edge, value in sorted(metrics.approach_delay_s.items()):
                row[f"{name}.approach_delay_s.edge_{int(edge)}"] = value
        for lane, (mean, peak) in enumerate(
            zip(self.queue_mean_veh, self.max_queue_veh, strict=True)
        ):
            row[f"queue_mean_veh.lane_{lane}"] = mean
            row[f"max_queue_veh.lane_{lane}"] = peak
        return row


class MetricAccumulator:
    """See the module docstring for when to call what."""

    def __init__(self, window: MeasurementWindow, network: Network) -> None:
        self._window = window
        lanes = sorted(network.lanes, key=lambda lane: lane.id)
        if [int(lane.id) for lane in lanes] != list(range(len(lanes))):
            raise ValueError("network lanes must be LaneId(0..n-1), the backend's order")
        self._lane_edge = np.array([int(lane.edge) for lane in lanes], dtype=np.int64)
        self._queue_rows: list[list[int]] = []
        self._close: _WindowClose | None = None
        self._last: TrueState | None = None

    def accumulate(self, state: TrueState) -> None:
        """Every step; appends only."""
        time_s = state.time_s
        last = self._last
        if last is not None and time_s <= last.time_s:
            raise ValueError(f"states must arrive in time order: {time_s} after {last.time_s}")
        self._last = state
        if time_s < self._window.start_s:
            return
        if time_s < self._window.end_s:
            self._queue_rows.append(list(map(_QUEUE_COUNT, state.lanes)))
            return
        if self._close is None:
            if time_s - self._window.end_s > _TIME_TOLERANCE_S:
                raise ValueError(
                    f"no state at the window's end {self._window.end_s}; the first after it is "
                    f"at {time_s}. The window must end on a step"
                )
            self._close = _snapshot(state)

    def finalize(self, trips: Sequence[TripRecord], *, snapshot_mismatch: bool) -> MetricResult:
        """Every metric, at run end, from the trips tripinfo reports for this run.

        Raises `TripAccountingError` if invariant 14 fails -- a defect, not a
        property of the run. An invalid run does **not** raise: its result
        carries its causes and every metric, to be written like any other.
        """
        close, last = self._close, self._last
        if close is None or last is None:
            raise RuntimeError(
                f"the measurement window {self._window} never closed: finalize() needs every "
                f"state up to and past its end"
            )
        if not self._queue_rows:
            raise RuntimeError(f"no state fell inside the measurement window {self._window}")

        columns = TripColumns.from_trips(trips)
        run_end = last.counters
        check_trip_accounting(run_end, int(columns.inserted.sum()))

        scheduled = columns.scheduled_depart_s
        due = int(((scheduled >= self._window.start_s) & (scheduled < self._window.end_s)).sum())
        validity = assess_validity(
            run_end=run_end,
            pending_at_window_close=close.pending,
            due_in_window=due,
            snapshot_mismatch=snapshot_mismatch,
        )

        everyone = np.ones(len(columns), dtype=np.bool_)
        aggregate = trip_metrics(
            columns,
            everyone,
            self._window,
            InNetwork(
                count=sum(g.count for g in close.in_network.values()),
                time_loss_s=sum(g.time_loss_s for g in close.in_network.values()),
            ),
            self._lane_edge,
        )
        by_type = {
            vehicle_type: trip_metrics(
                columns,
                columns.type_code == code,
                self._window,
                close.in_network[vehicle_type],
                self._lane_edge,
            )
            for code, vehicle_type in enumerate(VEHICLE_TYPES)
        }

        queue = np.asarray(self._queue_rows, dtype=np.int64)
        try:
            mser5_truncation_s: float | None = warmup_from_columns(columns).truncation_s
        except ValueError:
            mser5_truncation_s = None

        return MetricResult(
            window=self._window,
            validity=validity,
            aggregate=aggregate,
            by_type=by_type,
            queue_mean_veh=tuple(float(v) for v in queue.mean(axis=0)),
            max_queue_veh=tuple(int(v) for v in queue.max(axis=0)),
            mid_link_arrivals_tripinfo=int((columns.exit_code == EXIT_MID_LINK).sum()),
            mid_link_arrivals_kinematic=run_end.arrived_mid_link,
            mser5_truncation_s=mser5_truncation_s,
        )


def _snapshot(state: TrueState) -> _WindowClose:
    """Once per run, at window close: the one place the accumulator visits vehicles."""
    counts = dict.fromkeys(VEHICLE_TYPES, 0)
    losses = dict.fromkeys(VEHICLE_TYPES, 0.0)
    for vehicle in state.vehicles:
        counts[vehicle.type] += 1
        losses[vehicle.type] += vehicle.time_loss_s
    return _WindowClose(
        pending=state.counters.insertion_failures,
        in_network={t: InNetwork(count=counts[t], time_loss_s=losses[t]) for t in VEHICLE_TYPES},
    )
