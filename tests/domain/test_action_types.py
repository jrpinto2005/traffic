"""Construction of the SS5 action types (D-020)."""

from __future__ import annotations

from traffic_lab.domain.action import ActionResult, PhaseRequest, RequestOutcome
from traffic_lab.domain.network import IntersectionId, PhaseId


def test_phase_request_names_an_intersection_and_a_phase() -> None:
    request = PhaseRequest(intersection=IntersectionId(0), phase=PhaseId(1))
    assert request.intersection == IntersectionId(0)
    assert request.phase == PhaseId(1)


def test_request_outcome_has_all_five_values() -> None:
    assert {o.value for o in RequestOutcome} == {
        "granted",
        "deferred",
        "held",
        "forced",
        "rejected",
    }


def test_action_result_reason_is_meaningful_when_not_granted() -> None:
    result = ActionResult(
        outcome=RequestOutcome.REJECTED,
        active_phase=PhaseId(0),
        reason="phase 3 contains a conflicting movement pair",
        seconds_until_actionable=0.0,
    )
    assert result.outcome is RequestOutcome.REJECTED
    assert result.reason  # non-empty, per D-020: diagnostic, not swallowed
