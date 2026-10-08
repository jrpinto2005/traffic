"""The constraint layer: `08_AGENT_HANDOFF_PROTOCOL.md` SS9, implementing D-020.

Every controller acts through this layer, including fixed-time. It enforces
minimum and maximum green, yellow and all-red transition timing, and phase
legality against the D-023 conflict matrix, so that no controller has to and no
controller can bypass it.

Two tiers, and the separation is a **safety** property rather than an efficiency
one (D-020, `06_ARCHITECTURE.md` SS6.2): `step()` runs every simulation step
(timers, transitions -- negligible cost); the controller policy runs every Dt.
If the layer only ran at decision points, a yellow interval could overrun by up
to Dt, which is a safety-model defect rather than an approximation.

**Invariant 7 -- timers depend only on simulated time.** Nothing here reads a
wall clock. `now_s` is always simulated seconds, supplied by the caller, which
is what makes runs reproducible under D-017.

This module owns invariant 9's third clause (`05_DOMAIN_MODEL.md` SS8):
`decision_interval_s <= min_green_s`. `SignalTiming` (SS2.7) has no such field --
it is controller-layer configuration, not network structure -- so T1.2's
`validate_network()` correctly left it here. It is checked at load, before the
simulator starts.

`ConstraintLayer` is a concrete class, not a `typing.Protocol`, despite SS9
writing the interface as one. Non-goal 4 of the contract is explicit -- "do NOT
add a base class for future constraint layers. There is one." -- and SS7's
anti-pattern list forbids an interface introduced for a second implementation
that does not exist. SS9's `Protocol` describes the interface; the class provides
exactly it.

Time conventions, stated once because several invariants depend on them:

- A **green interval** runs from the step at which a phase's green begins to the
  step at which it ends (the start of the outgoing yellow). `min_green_s` and
  `max_green_s` both measure that interval and nothing else.
- `active_phase` during a transition is the **target** phase: once a change is
  granted it is irrevocable, so the phase in effect after the transition is the
  one a controller needs to reason about, and it makes `HELD` ("the request
  equals the current phase; nothing to do") mean what it says. `in_transition`
  on the returned `SignalState` distinguishes committed-but-not-yet-green from
  green.
- `phase_started_s` is when the active phase *became active* -- the step the
  transition to it began -- not when its green began. It therefore never jumps
  for a phase that is already active.
- Stage boundaries are scheduled in absolute simulated time (`stage_ends_s`), so
  a coarse step length cannot make yellow or all-red shorter than nominal and
  cannot accumulate drift across a transition. Each stage lasts at least its
  nominal duration and at most that plus one step.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, model_validator

from traffic_lab.domain.action import ActionResult, PhaseRequest, RequestOutcome
from traffic_lab.domain.network import (
    ConflictMatrix,
    IntersectionId,
    MovementId,
    Network,
    PhaseId,
    SignalizedIntersection,
    conflicting_pair,
)

# `SignalStage` moved to the domain in T1.14 (the backend needs it too) and is
# re-exported here so existing imports keep working.
from traffic_lab.domain.state import SignalStage as SignalStage
from traffic_lab.domain.state import SignalState

# Simulated seconds. Absorbs binary-floating-point error in accumulated step
# times (0.1 + 0.1 + 0.1 != 0.3) so a timer that should expire exactly on a step
# boundary does, rather than one step late. It is not a tolerance on the timings
# themselves -- it is four orders of magnitude below the smallest step length
# any SUMO scenario uses.
_TIME_EPS_S = 1e-9


class ConstraintConfigError(ValueError):
    """Raised at load when the constraint layer's configuration is invalid.

    Carries the `05_DOMAIN_MODEL.md` SS8 invariant number when the violation is
    one of them, mirroring `NetworkValidationError`, so tests and callers can
    assert on it precisely rather than on message text.
    """

    def __init__(self, message: str, *, invariant: int | None = None) -> None:
        self.invariant = invariant
        prefix = f"invariant {invariant} violated: " if invariant is not None else ""
        super().__init__(f"{prefix}{message}")


class ConstraintLayerConfig(BaseModel):
    """The constraint layer's own configuration, per SS9's config schema.

    SS9 lists five fields. Four of them -- `min_green_s`, `max_green_s`,
    `yellow_s`, `all_red_s` -- are already `SignalTiming` (`05_DOMAIN_MODEL.md`
    SS2.7), per-intersection network structure validated at load by T1.2's
    `validate_network()`. They are deliberately **not** duplicated here: two
    sources of truth for a timing that affects results is the D-031 anti-pattern
    the register warns about most loudly. The fifth, `decision_interval_s`, has
    no home in the domain model and lives here.

    `step_length_s` is not in SS9's field list but is required to check D-020's
    other stated constraint on Dt ("it must be an integer multiple of the SUMO
    step length"), which SS9 writes as a comment on `decision_interval_s`. It is
    required rather than defaulted: a step length silently assumed to be 1 s
    would be exactly the "default parameter that affects results and is not in
    the register" anti-pattern.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_interval_s: float = Field(
        gt=0.0,
        description="Dt, simulated seconds. How often the controller policy is asked for a "
        "phase. D-020: per-controller, and reported next to every result.",
    )
    step_length_s: float = Field(
        gt=0.0,
        description="The simulator step length, simulated seconds. D-020 requires Dt to be an "
        "integer multiple of it.",
    )

    @model_validator(mode="after")
    def _decision_interval_is_a_multiple_of_the_step_length(self) -> ConstraintLayerConfig:
        """D-020: Dt must be an integer multiple of the simulator step length.

        Compared with an absolute-plus-relative tolerance rather than `%`,
        because `0.3 % 0.1` is `0.0999...` in binary floating point and would
        reject a config that is exactly right.

        Raises `ValueError`, which Pydantic surfaces as a `ValidationError`
        naming the offending field -- the same failure mode as every other
        config error in the project (D-004, `traffic_lab.experiments.config`).
        The cross-check against the network's `min_green_s` cannot work this way
        (it needs the network) and lives in `validate_decision_interval` below.
        """
        multiples = round(self.decision_interval_s / self.step_length_s)
        exact = multiples * self.step_length_s
        tolerance = 1e-9 * max(1.0, self.decision_interval_s)
        if multiples < 1 or abs(exact - self.decision_interval_s) > tolerance:
            raise ValueError(
                f"decision_interval_s = {self.decision_interval_s} s is not an integer "
                f"multiple of step_length_s = {self.step_length_s} s (D-020)"
            )
        return self


def validate_decision_interval(config: ConstraintLayerConfig, network: Network) -> None:
    """Check invariant 9's `decision_interval_s <= min_green_s` clause.

    Checked against **every** signalized intersection in the network, because Dt
    is one value applied to all of them: an intersection with a shorter minimum
    green than Dt is one whose shortest legal phase the controller cannot
    express (D-020, "it must be at least as fine as the minimum green").

    Raises `ConstraintConfigError` naming the offending intersection and both
    numbers. Called by `ConstraintLayer.__init__`, so the failure happens when
    the layer is built -- before the simulator starts -- not at the first
    request.
    """
    for intersection in network.signalized_intersections:
        min_green_s = intersection.timing.min_green_s
        if config.decision_interval_s > min_green_s:
            raise ConstraintConfigError(
                f"decision_interval_s = {config.decision_interval_s} s exceeds "
                f"min_green_s = {min_green_s} s of intersection {intersection.id}; the "
                "controller could not express that intersection's shortest legal phase",
                invariant=9,
            )


@dataclass(slots=True)
class ConstraintCounters:
    """One counter per `RequestOutcome`, plus D-020's overshoot accounting.

    Exposed for the run manifest. D-020: "the RL policy requested an illegal
    switch 400 times" is diagnostic information, not something to swallow
    silently -- which is why the counters stay even though `allowed_phases()`
    lets a controller avoid the illegal request in the first place. A masked
    controller that still requests an illegal phase is a bug worth seeing.

    The last three fields are D-020's known gap made visible rather than silent;
    see `ConstraintLayer._max_green_override_target`.
    """

    granted: int = 0
    deferred: int = 0
    held: int = 0
    forced: int = 0
    rejected: int = 0

    max_green_overshoot_s: float = 0.0
    """Cumulative simulated seconds by which green intervals outlasted `max_green_s`."""

    max_green_worst_overshoot_s: float = 0.0
    """The largest single such excess. A total alone cannot distinguish one bad
    event from many negligible ones."""

    overrides_deferred_by_transition: int = 0
    """Times a max-green override was withheld because a transition was already in
    progress -- D-020's provisional answer, instrumented. Expected to stay 0; see
    `_max_green_override_target` for why."""


@dataclass(slots=True)
class _Runtime:
    """Per-intersection static lookup plus the mutable stage of its machine.

    Static and mutable live together so the step loop does one dict lookup per
    intersection rather than three. Everything above `stage` is computed once at
    construction and never written again.
    """

    intersection: SignalizedIntersection
    conflicts: ConflictMatrix
    phase_order: tuple[PhaseId, ...]
    movements_by_phase: Mapping[PhaseId, frozenset[MovementId]]
    legal_phases: frozenset[PhaseId]

    stage: SignalStage
    active_phase: PhaseId
    leaving_phase: PhaseId
    """The phase the current transition is leaving; meaningful only outside GREEN,
    where `active_phase` is already the target. Kept so `display()` can say which
    links are yellow."""
    phase_started_s: float
    green_started_s: float
    stage_ends_s: float


# Bound on `_advance`'s loop. Three stage changes in one step already means a
# step spanning a whole transition; a fourth would mean the machine is not
# making progress, which is worth raising rather than hanging the run.
_MAX_STAGE_CHANGES_PER_STEP = 8


class ConstraintLayer:
    """Enforces signal timing and phase legality between every controller and the backend.

    Built from a validated `Network` (T1.2's `validate_network()`) and a
    `ConstraintLayerConfig`. Construction is load time: invariant 9's
    `decision_interval_s <= min_green_s` clause is checked here, so an
    unsatisfiable configuration fails before the simulator starts.

    Every intersection starts green on its **first authored phase** at
    `start_s`. That is not a configuration option -- an initial phase nothing
    sets would be the D-031 anti-pattern -- it is the convention SUMO applies to
    the first `<phase>` of a `<tlLogic>`, and it is deterministic, which is what
    D-017 requires.
    """

    def __init__(
        self,
        network: Network,
        config: ConstraintLayerConfig,
        *,
        start_s: float = 0.0,
    ) -> None:
        validate_decision_interval(config, network)
        self._config = config
        self._now_s = start_s
        self._counters = ConstraintCounters()
        self._runtimes: dict[IntersectionId, _Runtime] = {}
        # Invariant 6's memory: the results already returned at `_decisions_at_s`.
        self._decisions: dict[tuple[IntersectionId, PhaseId], ActionResult] = {}
        self._decisions_at_s: float | None = None

        conflicts_by_junction = {j.id: j.conflicts for j in network.junctions}
        for intersection in network.signalized_intersections:
            if not intersection.phases:
                raise ConstraintConfigError(
                    f"intersection {intersection.id} declares no phases; the constraint "
                    "layer has nothing to hold green"
                )
            conflicts = conflicts_by_junction[intersection.junction]
            movements_by_phase = _movements_by_phase(intersection)
            phase_order = tuple(phase.id for phase in intersection.phases)
            legal_phases = frozenset(
                phase_id
                for phase_id, movements in movements_by_phase.items()
                if conflicting_pair(conflicts, movements) is None
            )
            initial_phase = next(
                (phase_id for phase_id in phase_order if phase_id in legal_phases), None
            )
            if initial_phase is None:
                raise ConstraintConfigError(
                    f"intersection {intersection.id} has no phase free of CONFLICTING "
                    "movement pairs; the constraint layer has nothing safe to hold green"
                )
            self._runtimes[intersection.id] = _Runtime(
                intersection=intersection,
                conflicts=conflicts,
                phase_order=phase_order,
                movements_by_phase=movements_by_phase,
                legal_phases=legal_phases,
                stage=SignalStage.GREEN,
                # The first *legal* authored phase. Invariant 7 of
                # `05_DOMAIN_MODEL.md` SS8 means a validated network's first
                # phase is already legal; taking the first legal one keeps the
                # layer safe even when it is handed a network that was not
                # validated, which is the whole point of a constraint layer.
                active_phase=initial_phase,
                leaving_phase=initial_phase,
                phase_started_s=start_s,
                green_started_s=start_s,
                stage_ends_s=math.inf,
            )

    # --- The every-simulation-step tier --------------------------------------

    def step(self, now_s: float) -> None:
        """Advance timers and execute yellow / all-red. Called every simulation step.

        Invariant 5: pure with respect to requests. It advances a machine
        through stages already committed, and may start a max-green override,
        but it never changes which phase a granted request was for.

        Invariant 7: `now_s` is simulated seconds. No wall clock is read here or
        anywhere else in this module.
        """
        if now_s + _TIME_EPS_S < self._now_s:
            raise ValueError(
                f"step(now_s={now_s}) is before the previous step at {self._now_s} s; "
                "simulated time does not run backwards"
            )
        self._now_s = now_s
        for runtime in self._runtimes.values():
            self._advance(runtime, now_s)

    # --- The every-Dt tier ----------------------------------------------------

    def submit(self, request: PhaseRequest, now_s: float) -> ActionResult:
        """Grant, defer, hold, or reject a phase request. Called every Dt (D-020).

        A controller *requests*; this layer grants, defers, or overrides, and
        records which -- the record is the point, not a side effect. The
        outcome is decided in this order, and the order is what makes each
        outcome mean one thing:

        1. **REJECTED** -- the phase is not authored for this intersection, or
           it contains a `CONFLICTING` movement pair. Illegal requests are
           refused before any timer is consulted, so a REJECTED count is never
           contaminated by requests that were merely early.
        2. **HELD** -- the request is the phase already in effect. Checked
           before the timers, because keeping the current phase is always
           available: a controller that names what is already running is not
           blocked by minimum green, it simply has nothing to do.
        3. **DEFERRED** -- legal, but a transition is in progress or minimum
           green has not elapsed.
        4. **GRANTED** -- the change is committed here and executed by `step()`.

        FORCED is never produced here. It is a max-green override, which
        happens between decision points and therefore belongs to `step()`.

        `now_s` must be the simulated time of the most recent `step()`.
        Submitting at a time the timers have not reached would mean deciding on
        stale state, which is precisely the defect the two-tier structure exists
        to prevent, so it raises rather than guessing.
        """
        self._require_current_time(now_s)
        runtime = self._runtime(request.intersection)

        # Invariant 6: within one decision interval, a repeated request replays
        # its first result and applies nothing a second time.
        if self._decisions_at_s is None or abs(self._decisions_at_s - now_s) > _TIME_EPS_S:
            self._decisions.clear()
            self._decisions_at_s = now_s
        key = (request.intersection, request.phase)
        cached = self._decisions.get(key)
        if cached is not None:
            return cached

        result = self._decide(runtime, request, now_s)
        self._decisions[key] = result
        return result

    def allowed_phases(self, intersection_id: IntersectionId) -> frozenset[PhaseId]:
        """The phases `submit()` would accept right now -- the legal-action mask.

        Adopted from PyTSC via T0.1 and added to D-020 on 2026-08-18. It
        generalises `actionable()` from "can I act" to "which actions are
        legal", and it leaks nothing: it is derived from the controller's own
        signal state (which `05_DOMAIN_MODEL.md` SS4.2 says a controller knows
        exactly) plus the static conflict matrix. No `TrueState` is involved.

        "Accept" means GRANTED or HELD -- the outcomes that are not a refusal.
        When the layer is actionable that is every legal phase; when it is not,
        it is the active phase alone, because holding what is already in effect
        is always available. **The mask is therefore never empty**, which
        matters for the RL consumer it was added for: a masked action space with
        no legal action is not a constrained policy, it is a stuck one.

        It describes **one** action. Acting on a phase the mask offered changes
        the state the rest of the mask was computed against, which is what a
        controller does anyway -- one request per decision point.

        The per-outcome counters stay regardless. A masked controller that still
        requests an illegal phase is a bug worth seeing (D-020).
        """
        runtime = self._runtime(intersection_id)
        if self.actionable(intersection_id):
            return runtime.legal_phases | {runtime.active_phase}
        return frozenset({runtime.active_phase})

    def actionable(self, intersection_id: IntersectionId) -> bool:
        """True if a request could be granted now: green, and past minimum green.

        Takes no `now_s`: the layer knows the current simulated time because
        `step()` is called every simulation step. That is the two-tier structure
        working -- a layer that had to be told the time at a decision point
        would be a layer whose timers were only as fine as Dt.
        """
        runtime = self._runtime(intersection_id)
        return runtime.stage is SignalStage.GREEN and self._min_green_elapsed(runtime, self._now_s)

    def signal_state(self, intersection_id: IntersectionId) -> SignalState:
        """The intersection's own signal state, as the domain type.

        A controller knows its own signals exactly (`05_DOMAIN_MODEL.md` SS4.2),
        so this is the one thing the control path may read without a sensor. It
        carries no vehicle information and no `TrueState`.
        """
        runtime = self._runtime(intersection_id)
        return SignalState(
            intersection=intersection_id,
            active_phase=runtime.active_phase,
            phase_started_s=runtime.phase_started_s,
            green_started_s=(
                runtime.green_started_s if runtime.stage is SignalStage.GREEN else None
            ),
            in_transition=runtime.stage is not SignalStage.GREEN,
        )

    def display(self, intersection_id: IntersectionId) -> tuple[SignalStage, PhaseId | None]:
        """What the signal must show now (D-034): `(GREEN, active)`, `(YELLOW, phase
        being left)`, or `(ALL_RED, None)`.

        Read-only. During a yellow `signal_state()` already names the *target*
        phase, so it no longer says which links should be yellow; this does. The
        backend turns it into SUMO's state string (`display_state`).
        """
        runtime = self._runtime(intersection_id)
        if runtime.stage is SignalStage.GREEN:
            return SignalStage.GREEN, runtime.active_phase
        if runtime.stage is SignalStage.YELLOW:
            return SignalStage.YELLOW, runtime.leaving_phase
        return SignalStage.ALL_RED, None

    @property
    def counters(self) -> ConstraintCounters:
        """Per-outcome counters, for the run manifest."""
        return self._counters

    @property
    def decision_interval_s(self) -> float:
        """Dt, recorded in the manifest and reported next to every result (D-020)."""
        return self._config.decision_interval_s

    # --- The one state machine -----------------------------------------------

    def _advance(self, runtime: _Runtime, now_s: float) -> None:
        """Run `runtime`'s machine forward to `now_s`.

        A loop rather than a single test, because one simulation step may be
        coarse enough to span a whole transition (a 5 s step over a 3 s yellow
        and a 2 s all-red). It terminates: entering GREEN puts the next boundary
        `max_green_s` away, and invariant 9 guarantees `max_green_s >
        min_green_s > 0`.
        """
        for _ in range(_MAX_STAGE_CHANGES_PER_STEP):
            if runtime.stage is SignalStage.GREEN:
                target = self._max_green_override_target(runtime, now_s)
                if target is None:
                    return
                self._record_max_green_overshoot(runtime, now_s)
                self._counters.forced += 1
                self._begin_transition(runtime, target, now_s)
                continue
            if now_s + _TIME_EPS_S < runtime.stage_ends_s:
                return
            all_red_s = runtime.intersection.timing.all_red_s
            if runtime.stage is SignalStage.YELLOW and all_red_s > 0.0:
                # Scheduled from the yellow's nominal end, not from `now_s`, so
                # a coarse step cannot lengthen the all-red as well.
                runtime.stage = SignalStage.ALL_RED
                runtime.stage_ends_s = runtime.stage_ends_s + all_red_s
                continue
            runtime.stage = SignalStage.GREEN
            runtime.green_started_s = now_s
            runtime.stage_ends_s = math.inf
            return
        raise RuntimeError(  # pragma: no cover -- see the loop bound
            f"intersection {runtime.intersection.id} changed stage "
            f"{_MAX_STAGE_CHANGES_PER_STEP} times in one step at {now_s} s"
        )

    def _max_green_override_target(self, runtime: _Runtime, now_s: float) -> PhaseId | None:
        """The phase a max-green override switches to now, or `None` for no override.

        **D-020's known gap.** The register leaves open what happens when max
        green expires while a phase transition is in progress, with the
        provisional answer that the override *waits* and the overshoot is
        recorded. The second branch below is that answer, written explicitly
        rather than left implicit in the control flow.

        It is also **unreachable**, which is the finding this ticket owed the
        register: `max_green_s` measures the green interval (invariant 2, "green
        never longer than max_green_s"), and a green interval is by definition
        not running during a transition, so the expiry cannot occur
        mid-transition. Preempting -- the alternative the register names -- would
        have violated invariant 3. `overrides_deferred_by_transition` counts the
        branch anyway: an unreachable case that is merely asserted is a claim;
        one that is counted is a measurement.

        What the register calls an overshoot "up to `yellow_s + all_red_s`" does
        exist, but as a property of *service* rather than of green: a phase
        forced off at `max_green_s` still holds the intersection for the
        clearance that follows, so the next green begins `max_green_s +
        yellow_s + all_red_s` after this one did. That is a real property of the
        system and belongs in the results document. The overshoot recorded here
        is the separate, smaller one that `max_green_s` itself suffers: a green
        interval can outlast it by up to one step length when `max_green_s` does
        not fall on the step grid.

        The layer's "own choice" of replacement phase (SS9's wording for FORCED)
        is the **next legal phase in authored order, wrapping**. Authored order
        is the order an engineer wrote the program in, so this is the phase a
        fixed-time program would run next; it is deterministic, and it is the
        only choice that does not require the layer to hold a policy. An
        intersection with a single legal phase has nothing to override to and is
        left alone.
        """
        max_green_s = runtime.intersection.timing.max_green_s
        if max_green_s <= 0.0:  # 0.0 disables the override (SS2.7, SS9)
            return None
        expired = now_s + _TIME_EPS_S >= runtime.green_started_s + max_green_s
        if runtime.stage is not SignalStage.GREEN:
            if expired:
                self._counters.overrides_deferred_by_transition += 1
            return None
        if not expired:
            return None
        return self._next_legal_phase(runtime)

    def _record_max_green_overshoot(self, runtime: _Runtime, now_s: float) -> None:
        overshoot_s = (now_s - runtime.green_started_s) - runtime.intersection.timing.max_green_s
        if overshoot_s <= _TIME_EPS_S:
            return
        self._counters.max_green_overshoot_s += overshoot_s
        self._counters.max_green_worst_overshoot_s = max(
            self._counters.max_green_worst_overshoot_s, overshoot_s
        )

    def _next_legal_phase(self, runtime: _Runtime) -> PhaseId | None:
        order = [phase_id for phase_id in runtime.phase_order if phase_id in runtime.legal_phases]
        if runtime.active_phase not in order or len(order) < 2:
            return None
        return order[(order.index(runtime.active_phase) + 1) % len(order)]

    def _begin_transition(self, runtime: _Runtime, target: PhaseId, now_s: float) -> None:
        """Commit a phase change: the green interval ends here, the clearance begins.

        The change is committed at `now_s` -- SS9: "GRANTED: phase change begins
        this step" -- but the yellow and all-red are counted down by `step()`
        alone, per invariant 3.
        """
        runtime.stage = SignalStage.YELLOW
        runtime.stage_ends_s = now_s + runtime.intersection.timing.yellow_s
        runtime.leaving_phase = runtime.active_phase
        runtime.active_phase = target
        runtime.phase_started_s = now_s

    # --- Shared queries ------------------------------------------------------

    def _runtime(self, intersection_id: IntersectionId) -> _Runtime:
        try:
            return self._runtimes[intersection_id]
        except KeyError:
            raise KeyError(
                f"intersection {intersection_id} is not signalized, or is not in the "
                "network this constraint layer was built from"
            ) from None

    def _require_current_time(self, now_s: float) -> None:
        if abs(now_s - self._now_s) > _TIME_EPS_S:
            raise ValueError(
                f"submit(now_s={now_s}) but the constraint layer last stepped at "
                f"{self._now_s} s. Call step() every simulation step before submitting: "
                "deciding on timers that have not been advanced is the defect D-020's "
                "two-tier structure exists to prevent"
            )

    def _decide(self, runtime: _Runtime, request: PhaseRequest, now_s: float) -> ActionResult:
        movements = runtime.movements_by_phase.get(request.phase)
        if movements is None:
            return self._refuse(
                runtime,
                now_s,
                RequestOutcome.REJECTED,
                f"phase {request.phase} is not an authored phase of intersection "
                f"{request.intersection}",
            )
        if request.phase not in runtime.legal_phases:
            # Legality was decided once, at construction. The pair is recomputed
            # only here, on the refusal path, because D-023 requires naming it.
            pair = conflicting_pair(runtime.conflicts, movements)
            return self._refuse(
                runtime,
                now_s,
                RequestOutcome.REJECTED,
                f"phase {request.phase} contains conflicting movement pair "
                f"{pair} and never reaches the backend",
            )
        if request.phase == runtime.active_phase:
            self._counters.held += 1
            return self._result(runtime, now_s, RequestOutcome.HELD, "")
        if runtime.stage is not SignalStage.GREEN:
            return self._refuse(
                runtime,
                now_s,
                RequestOutcome.DEFERRED,
                f"a phase transition to {runtime.active_phase} is in progress",
            )
        if not self._min_green_elapsed(runtime, now_s):
            elapsed_s = now_s - runtime.green_started_s
            return self._refuse(
                runtime,
                now_s,
                RequestOutcome.DEFERRED,
                f"phase {runtime.active_phase} has been green for {elapsed_s} s of its "
                f"{runtime.intersection.timing.min_green_s} s minimum",
            )

        self._begin_transition(runtime, request.phase, now_s)
        self._counters.granted += 1
        return self._result(runtime, now_s, RequestOutcome.GRANTED, "")

    def _refuse(
        self, runtime: _Runtime, now_s: float, outcome: RequestOutcome, reason: str
    ) -> ActionResult:
        if outcome is RequestOutcome.REJECTED:
            self._counters.rejected += 1
        else:
            self._counters.deferred += 1
        return self._result(runtime, now_s, outcome, reason)

    def _result(
        self, runtime: _Runtime, now_s: float, outcome: RequestOutcome, reason: str
    ) -> ActionResult:
        return ActionResult(
            outcome=outcome,
            active_phase=runtime.active_phase,
            reason=reason,
            seconds_until_actionable=max(0.0, self._actionable_at_s(runtime) - now_s),
        )

    def _min_green_elapsed(self, runtime: _Runtime, now_s: float) -> bool:
        min_green_s = runtime.intersection.timing.min_green_s
        return now_s + _TIME_EPS_S >= runtime.green_started_s + min_green_s

    def _actionable_at_s(self, runtime: _Runtime) -> float:
        """The earliest simulated time at which a request could be granted."""
        timing = runtime.intersection.timing
        if runtime.stage is SignalStage.GREEN:
            return runtime.green_started_s + timing.min_green_s
        if runtime.stage is SignalStage.YELLOW:
            return runtime.stage_ends_s + timing.all_red_s + timing.min_green_s
        return runtime.stage_ends_s + timing.min_green_s


def _movements_by_phase(
    intersection: SignalizedIntersection,
) -> Mapping[PhaseId, frozenset[MovementId]]:
    """The movements each authored phase turns green, via its signal groups."""
    movements_by_group = {group.id: group.movements for group in intersection.signal_groups}
    return {
        phase.id: frozenset(
            movement
            for group_id in phase.green_groups
            for movement in movements_by_group.get(group_id, ())
        )
        for phase in intersection.phases
    }
