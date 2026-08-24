"""Shared fixtures for the constraint layer tests. Test-only, not a `traffic_lab` package.

Builds constraint layers over `tests.domain.factories.build_valid_network()` --
the standard two-phase intersection, north-south and east-west, each pair
conflicting with the other -- with the signal timing varied per test.

`run_steps` is the every-simulation-step tier of D-020 written out: the thing
under test is what happens when `step()` is called at every simulated step and
`submit()` only at decision points, so the tests drive it that way rather than
calling `submit()` in isolation.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence

from tests.domain.factories import INTERSECTION, SG_EW, SG_NS, build_valid_network
from traffic_lab.control.constraint_layer import (
    ConstraintLayer,
    ConstraintLayerConfig,
    SignalStage,
)
from traffic_lab.domain.network import IntersectionId, Network, Phase, PhaseId, SignalTiming

DEFAULT_MIN_GREEN_S = 5.0
DEFAULT_MAX_GREEN_S = 60.0
DEFAULT_YELLOW_S = 3.0
DEFAULT_ALL_RED_S = 2.0

PHASE_CONFLICTING = PhaseId(2)
"""A third, illegal phase: north-south and east-west green together."""


def network_with_a_conflicting_phase() -> Network:
    """The fixture network plus one phase that `validate_network()` would reject.

    Deliberately invalid, per invariant 7 of `05_DOMAIN_MODEL.md` SS8. The
    constraint layer is the last line of defence and must refuse a request for
    this phase on its own reading of the D-023 matrix, rather than trusting that
    load-time validation happened. It is appended rather than made first so the
    layer still has a legal phase to start green on.
    """
    network = build_valid_network()
    intersection = network.signalized_intersections[0]
    intersection = dataclasses.replace(
        intersection,
        phases=(
            *intersection.phases,
            Phase(id=PHASE_CONFLICTING, green_groups=frozenset({SG_NS, SG_EW})),
        ),
    )
    return dataclasses.replace(network, signalized_intersections=(intersection,))


def timed_network(
    *,
    min_green_s: float = DEFAULT_MIN_GREEN_S,
    max_green_s: float = DEFAULT_MAX_GREEN_S,
    yellow_s: float = DEFAULT_YELLOW_S,
    all_red_s: float = DEFAULT_ALL_RED_S,
) -> Network:
    """The fixture network with its one intersection's `SignalTiming` replaced."""
    network = build_valid_network()
    intersection = dataclasses.replace(
        network.signalized_intersections[0],
        timing=SignalTiming(
            min_green_s=min_green_s,
            max_green_s=max_green_s,
            yellow_s=yellow_s,
            all_red_s=all_red_s,
        ),
    )
    return dataclasses.replace(network, signalized_intersections=(intersection,))


def build_layer(
    *,
    min_green_s: float = DEFAULT_MIN_GREEN_S,
    max_green_s: float = DEFAULT_MAX_GREEN_S,
    yellow_s: float = DEFAULT_YELLOW_S,
    all_red_s: float = DEFAULT_ALL_RED_S,
    decision_interval_s: float = 5.0,
    step_length_s: float = 1.0,
    network: Network | None = None,
) -> ConstraintLayer:
    if network is None:
        network = timed_network(
            min_green_s=min_green_s,
            max_green_s=max_green_s,
            yellow_s=yellow_s,
            all_red_s=all_red_s,
        )
    config = ConstraintLayerConfig(
        decision_interval_s=decision_interval_s, step_length_s=step_length_s
    )
    return ConstraintLayer(network, config)


def stage_of(layer: ConstraintLayer, intersection_id: IntersectionId = INTERSECTION) -> SignalStage:
    """The machine's stage.

    Reaches into `_runtimes` deliberately: invariant 3 is about the *split*
    between yellow and all-red, and the public surface reports only
    `in_transition`. A test that could not see the split could not check the
    invariant it is named for.
    """
    return layer._runtimes[intersection_id].stage


def green_phase(
    layer: ConstraintLayer, intersection_id: IntersectionId = INTERSECTION
) -> PhaseId | None:
    """The phase actually showing green now, or `None` during a transition.

    This -- not `active_phase` -- is what the conflict-freedom property is about:
    during yellow and all-red no phase is green, so no pair can be
    simultaneously green.
    """
    state = layer.signal_state(intersection_id)
    return None if state.in_transition else state.active_phase


def run_steps(
    layer: ConstraintLayer,
    times_s: Sequence[float],
    *,
    on_step: Callable[[float], None] | None = None,
) -> list[PhaseId | None]:
    """Call `step()` at each simulated time, returning the green phase after each.

    `on_step` runs after `step()` at that time, which is the order
    `06_ARCHITECTURE.md` SS6.2's loop uses: timers first, then the decision
    point.
    """
    greens: list[PhaseId | None] = []
    for now_s in times_s:
        layer.step(now_s)
        if on_step is not None:
            on_step(now_s)
        greens.append(green_phase(layer))
    return greens


def green_intervals(times_s: Sequence[float], greens: Sequence[PhaseId | None]) -> list[float]:
    """Durations of each *completed* green interval in a step-by-step history.

    A green interval runs from the first step showing a phase green to the first
    step that no longer does. The final, still-running interval is excluded: it
    has not ended, so its length is not yet a fact -- and invariant 1 exempts
    simulation shutdown for exactly that reason.
    """
    durations: list[float] = []
    started_s: float | None = None
    current: PhaseId | None = None
    for now_s, green in zip(times_s, greens, strict=True):
        if green == current:
            continue
        if current is not None and started_s is not None:
            durations.append(now_s - started_s)
        current = green
        started_s = now_s if green is not None else None
    return durations
