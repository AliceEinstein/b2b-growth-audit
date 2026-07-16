"""Score arithmetic tests: deductions, caps, counted statuses."""
from __future__ import annotations

import pytest

from core.schemas import Finding
from core.scoring import compute_score


def finding(module, severity, status="approved", i=[0]):
    i[0] += 1
    return Finding(
        id=f"f{i[0]}",
        module=module,
        severity=severity,
        confidence="high",
        object_type="contacts",
        evidence_file=f"evidence/{module}.csv",
        business_impact="test",
        recommendation_type="needs_business_rule_confirmation",
        review_status=status,
    )


def test_perfect_score_with_no_findings():
    score = compute_score([])
    assert score["total"] == 100
    assert score["categories"]["attribution_trust"]["score"] == 25


def test_deductions_by_severity():
    score = compute_score(
        [
            finding("attribution_trust", "high"),      # -6
            finding("lifecycle_funnel", "medium"),     # -3
            finding("pipeline_hygiene", "low"),        # -1
        ]
    )
    assert score["categories"]["attribution_trust"]["score"] == 19
    assert score["categories"]["lifecycle_funnel"]["score"] == 17
    assert score["categories"]["pipeline_hygiene"]["score"] == 19
    assert score["total"] == 100 - 10


def test_category_cap():
    score = compute_score(
        [finding("property_governance", "critical") for _ in range(5)]  # 50 raw
    )
    category = score["categories"]["property_governance"]
    assert category["deducted"] == 15  # capped at category max
    assert category["score"] == 0


def test_only_approved_or_revised_count():
    score = compute_score(
        [
            finding("attribution_trust", "critical", status="pending"),
            finding("attribution_trust", "critical", status="rejected"),
            finding("attribution_trust", "low", status="revised"),
        ]
    )
    assert score["categories"]["attribution_trust"]["deducted"] == 1


def test_unknown_module_is_an_error():
    with pytest.raises(ValueError, match="unknown module"):
        compute_score([finding("full_sales_ops_audit", "low")])
