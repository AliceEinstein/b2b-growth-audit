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
