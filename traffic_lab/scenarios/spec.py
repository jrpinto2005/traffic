"""The authored half of a single-intersection scenario: geometry and phases.

Implements the `IntersectionSpec` / `PhaseSpec` contract of T1.3 (as amended
2026-10-07, A4). Geometry is data (`00_RESEARCH_SPECIFICATION.md` SS8.1): the
number of approaches is a field, and approach *k* of *n* sits at bearing
360*k/n degrees clockwise from north.

Phases are **authored, then validated** (D-023): a `PhaseSpec` names the
(approach, turn) pairs it greens, and `build()` rejects a phase containing a
`CONFLICTING` pair against the matrix SUMO computes. Nothing here enumerates
phases.

`extra="forbid"` and `frozen=True` follow `traffic_lab.experiments.config`: a
misspelled key fails at load rather than being silently ignored.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from traffic_lab.domain.network import SignalTiming, TurnDirection


class PhaseSpec(BaseModel):
    """One authored phase: the movements it shows green."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    green: list[tuple[int, TurnDirection]] = Field(
        description="The (approach index, turn) pairs green in this phase. Approach k of n "
        "sits at bearing 360*k/n degrees clockwise from north."
    )


class IntersectionSpec(BaseModel):
    """A parametric single signalized intersection (T1.3 contract)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    approaches: int = Field(
        default=4,
        ge=3,
        description="Number of two-way streets meeting at the junction. No four-way "
        "assumption: 3 is a T-intersection (00_RESEARCH_SPECIFICATION.md SS8.1).",
    )
    lanes_per_approach: int = Field(
        default=2, ge=1, description="Lanes per direction on every approach street."
    )
    approach_length_m: float = Field(
        default=200.0,
        gt=0.0,
        description="Distance from the junction's centre to each approach's boundary node, "
        "metres. This is the nominal node spacing: junction geometry consumes part of it, "
        "so built lanes are shorter (189.6 m at the default) and anything needing a lane "
        "length must read it from the built network (research/M0_reference_scenario.md SS1).",
    )
    speed_limit_mps: float = Field(
        default=13.89, gt=0.0, description="Speed limit on every approach lane, m/s (50 km/h)."
    )
    turn_lanes: bool = Field(
        default=False,
        description="M1: protected turns, no dedicated turn lanes. Lanes are shared between "
        "turns as netconvert assigns them. `True` is not specified at M1 and is rejected.",
    )
    phases: list[PhaseSpec] = Field(
        min_length=1,
        description="Authored phases, run in this order by the emitted static program and "
        "validated against the conflict matrix (D-023).",
    )
    timing: SignalTiming = Field(
        description="Required, no default: it affects results. The emitted static program "
        "uses min_green_s, yellow_s and all_red_s."
    )

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.turn_lanes:
            raise ValueError(
                "turn_lanes=True is not specified at M1 (T1.3 contract: protected turns, no "
                "dedicated turn lanes); which lanes would be dedicated is a design decision "
                "the contract has not made"
            )
        for k, phase in enumerate(self.phases):
            for approach, turn in phase.green:
                if not 0 <= approach < self.approaches:
                    raise ValueError(
                        f"phase {k} greens ({approach}, {turn.value}), but approaches are "
                        f"numbered 0..{self.approaches - 1}"
                    )
        # The emitted program shows yellow on every green-to-red change; a zero-length
        # yellow is a green-to-red switch SUMO reports as "Missing yellow phase".
        if not self.timing.yellow_s > 0.0:
            raise ValueError(f"timing.yellow_s = {self.timing.yellow_s}, must be > 0")
        if not self.timing.all_red_s >= 0.0:
            raise ValueError(f"timing.all_red_s = {self.timing.all_red_s}, must be >= 0")
        return self
