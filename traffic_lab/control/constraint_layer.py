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
from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from traffic_lab.domain.network import (
    Compatibility,
    ConflictMatrix,
    IntersectionId,
    MovementId,
    Network,
    PhaseId,
    SignalizedIntersection,
    compatibility,
)
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
