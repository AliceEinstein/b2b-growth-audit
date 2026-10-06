from __future__ import annotations

import pytest

from core.adjudication import adjudicate_findings
from core.lifecycle_schemas import LifecycleFinding, ReviewDecision


def _finding(**updates):
    data = {
        "finding_id": "f1",
        "journey_pattern": "inbound_new_business",
        "integrity_dimension": "association_integrity",
        "severity": "high",
        "confidence_score": 80,
        "confidence_label": "high",
        "object_type": "deals",
        "affected_records": 2,
        "affected_percentage": 20.0,
        "denominator": 10,
        "evidence_refs": ["evidence.csv#finding_id=f1"],
        "business_impact": "Pipeline joins are incomplete.",
        "recommended_action": "Confirm the association rule and prepare a review list.",
        "recommendation_type": "safe_operational_action",
        "auto_fix_allowed": False,
        "review_intensity": "high",
    }
    data.update(updates)
    return LifecycleFinding.model_validate(data)


REVIEWERS = [
    "data_fidelity_reviewer",
    "journey_mapping_skeptic",
    "logic_reviewer",
    "false_positive_reviewer",
    "privacy_safety_reviewer",
]


def _reviews(verdict="approved"):
    return [
        ReviewDecision(
            finding_id="f1",
            reviewer=reviewer,
            verdict=verdict,
            reason="Evidence checked.",
            rejection_basis="valid_exception" if verdict == "rejected" else None,
        )
        for reviewer in REVIEWERS
    ]


@pytest.mark.parametrize(
    ("verdict", "status", "lane"),
    [
        ("approved", "approved", "priority_actions"),
        ("needs_revision", "needs_revision", "needs_revision"),
        ("downgrade_to_observation", "observation", "observations_to_monitor"),
        (
            "requires_human_confirmation",
            "human_confirmation",
            "human_confirmation_needed",
        ),
        ("rejected", "rejected", "rejected"),
    ],
)
def test_all_reviewer_statuses_route_deterministically(verdict, status, lane):
    result = adjudicate_findings([_finding()], _reviews(verdict))[0]
    assert result["review_status"] == status
    assert result["action_lane"] == lane


def test_missing_required_reviewer_is_rejected_by_engine():
    with pytest.raises(ValueError, match="missing required reviewers"):
        adjudicate_findings([_finding()], _reviews()[:-1])


def test_do_not_auto_fix_has_its_own_lane():
    result = adjudicate_findings(
        [_finding(severity="medium", recommendation_type="do_not_auto_fix")],
        _reviews(),
    )[0]
    assert result["action_lane"] == "do_not_auto_fix"


def test_review_revision_round_is_capped_at_one():
    with pytest.raises(ValueError):
        ReviewDecision(
            finding_id="f1",
            reviewer="logic_reviewer",
            verdict="approved",
            reason="Too many loops.",
            revision_round=2,
        )


def _decision(reviewer, verdict, basis=None, refs=("evidence.csv#finding_id=f1",)):
    return ReviewDecision(
        finding_id="f1", reviewer=reviewer, verdict=verdict, reason="Checked.",
        rejection_basis=basis, evidence_refs=list(refs),
    )


def test_invalid_measurement_needs_two_reviewers():
    one = [_decision(r, "approved") for r in REVIEWERS[:4]] + [_decision(REVIEWERS[4], "rejected", "invalid_measurement")]
    assert adjudicate_findings([_finding()], one)[0]["rejection_basis"] == "valid_exception"
    two = [_decision(r, "approved") for r in REVIEWERS[:3]] + [
        _decision(REVIEWERS[3], "rejected", "invalid_measurement"),
        _decision(REVIEWERS[4], "rejected", "invalid_measurement"),
    ]
    result = adjudicate_findings([_finding()], two)[0]
    assert result["review_status"] == "rejected"
    assert result["rejection_basis"] == "invalid_measurement"
    approved = adjudicate_findings([_finding()], _reviews("approved"))[0]
    assert approved["rejection_basis"] is None


def test_rejection_basis_contract():
    with pytest.raises(ValueError, match="must state rejection_basis"):
        _decision("logic_reviewer", "rejected")
    with pytest.raises(ValueError, match="must cite evidence_refs"):
        _decision("logic_reviewer", "rejected", "invalid_measurement", refs=())
    with pytest.raises(ValueError, match="only allowed on rejected"):
        _decision("logic_reviewer", "approved", "valid_exception")
