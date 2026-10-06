"""Control-level score arithmetic and evidence-coverage semantics."""
from __future__ import annotations

import pytest

from core.lifecycle_schemas import JourneyPatternRegistry, LifecycleFinding
from core.lifecycle_scoring import compute_lifecycle_score


def _registry() -> JourneyPatternRegistry:
    return JourneyPatternRegistry(
        primary_model="single_motion",
        overall_confidence=80,
        patterns=[],
        ambiguous_areas=[],
        human_confirmation_needed=[],
    )


def _measurement(
    measurement_id: str,
    *,
    link: str,
    control: str | None = None,
    population_key: str | None = None,
    role: str = "primary",
    denominator: int | None = 10,
    affected: int | None = 0,
    percentage: float | None = 0,
    available: bool = True,
    leakage_candidate: bool = False,
    outside_score_reason: str | None = None,
) -> dict:
    return {
        "id": measurement_id,
        "score_link": link,
        "score_control": control,
        "score_population_key": population_key or measurement_id,
        "score_role": role,
        "outside_score_reason": outside_score_reason,
        "leakage_candidate": leakage_candidate,
        "available": available,
        "denominator": denominator,
        "affected_records": affected,
        "affected_percentage": percentage,
    }


def _full_coverage() -> list[dict]:
    return [
        _measurement("contacts_without_owner", link="intent_to_owner", control="intent_owner"),
        _measurement("contacts_without_deal", link="owner_to_deal", control="owner_deal"),
        _measurement("lifecycle_state", link="deal_continuity", control="contact_lifecycle_state"),
        _measurement("deals_without_company", link="deal_continuity", control="deal_company_association"),
        _measurement("deals_without_contact", link="deal_continuity", control="deal_contact_association"),
        _measurement("source_trace", link="deal_continuity", control="inbound_source_continuity"),
        _measurement("deals_without_owner", link="deal_progression", control="open_deal_owner"),
        _measurement("active_deal_followup", link="deal_progression", control="active_deal_followup"),
        _measurement("expansion_customer_state", link="post_close_recovery", control="expansion_customer_state"),
    ]


def _finding(measurement_id: str, *, finding_id: str = "reviewed-finding") -> LifecycleFinding:
    return LifecycleFinding.model_validate(
        {
            "finding_id": finding_id,
            "journey_pattern": "inbound_new_business",
            "integrity_dimension": "handoff_integrity",
            "severity": "high",
            "confidence_score": 80,
            "confidence_label": "high",
            "object_type": "contacts",
            "affected_records": 5,
            "affected_percentage": 50,
            "denominator": 10,
            "evidence_refs": [f"evidence.csv#finding_id={measurement_id}"],
            "business_impact": "A handoff is incomplete.",
            "recommended_action": "Review the affected records.",
            "recommendation_type": "safe_operational_action",
            "auto_fix_allowed": False,
            "review_intensity": "high",
            "review_status": "approved",
        }
    )


def test_full_coverage_healthy_score_uses_valid_100_point_formula():
    score = compute_lifecycle_score([], _registry(), _full_coverage())
    assert score["overall_lifecycle_integrity_score"] == 100
    assert score["coverage_percentage"] == 100
    assert score["total_deducted"] == 0
    assert "100 baseline - 0 total normalized deductions = 100" in score["score_display_note"]


def test_low_coverage_withholds_score_instead_of_treating_unknown_as_failure():
    score = compute_lifecycle_score([], _registry(), _full_coverage()[:1])
    assert score["coverage_percentage"] == 20
    assert score["overall_lifecycle_integrity_score"] is None
    assert score["verdict"] == "insufficient_evidence"
    assert "Missing evidence is not treated as lifecycle failure" in score["score_display_note"]


def test_zero_population_is_not_scored_as_healthy():
    rows = _full_coverage()
    rows[0].update(denominator=0, affected_records=0, affected_percentage=0)
    score = compute_lifecycle_score([], _registry(), rows)
    assert score["journey_link_scores"]["intent_to_owner"]["status"] == "not_assessable"
    assert score["coverage_percentage"] == 80


def test_missing_one_continuity_control_reduces_only_its_coverage_weight():
    rows = _full_coverage()
    rows[4].update(available=False, denominator=None, affected_records=None, affected_percentage=None)
    score = compute_lifecycle_score([], _registry(), rows)
    continuity = score["journey_link_scores"]["deal_continuity"]
    assert continuity["assessed_weight"] == 15
    assert continuity["weight"] == 20
    assert continuity["status"].startswith("partially assessed")
    assert score["assessed_weight"] == 95
    assert score["coverage_percentage"] == 95


def test_motion_populations_are_weighted_by_their_actual_share():
    rows = _full_coverage()
    rows[0].update(
        id="inbound_without_owner",
        score_population_key="intent_owner:inbound",
        denominator=10,
        affected_records=10,
        affected_percentage=100,
        leakage_candidate=True,
    )
    rows.insert(
        1,
        _measurement(
            "outbound_without_owner",
            link="intent_to_owner",
            control="intent_owner",
            population_key="intent_owner:outbound",
            denominator=90,
            affected=0,
            percentage=0,
        ),
    )
    score = compute_lifecycle_score([], _registry(), rows)
    # The 100%-affected inbound motion is 10% of the eligible control
    # population. Pending review halves that 10% risk: 20 × 5% = 1 point.
    assert score["journey_link_scores"]["intent_to_owner"]["deducted"] == 1
    assert score["overall_lifecycle_integrity_score"] == 99


def test_review_status_follows_exact_measurement_citation_not_finding_name():
    rows = _full_coverage()
    rows[0].update(affected_records=5, affected_percentage=50, leakage_candidate=True)
    score = compute_lifecycle_score(
        [_finding("contacts_without_owner", finding_id="renamed-after-review")],
        _registry(),
        rows,
    )
    assert score["journey_link_scores"]["intent_to_owner"]["deducted"] == 10
    assert score["confirmed_finding_count"] == 1
    assert score["unresolved_candidate_count"] == 0


def test_measurement_id_prefix_does_not_inherit_other_measurements_review():
    rows = _full_coverage()
    rows[0].update(id="owner_gap", affected_records=5, affected_percentage=50, leakage_candidate=True)
    rows[0]["score_population_key"] = "intent_owner:inbound"
    score = compute_lifecycle_score(
        [_finding("owner_gap_extra")],
        _registry(),
        rows,
    )
    assert score["journey_link_scores"]["intent_to_owner"]["deducted"] == 5
    assert score["unresolved_candidate_count"] == 1


def test_breakdown_and_supporting_rows_never_change_score():
    rows = _full_coverage()
    rows[3].update(affected_records=2, affected_percentage=20, leakage_candidate=True)
    rows.extend(
        [
            _measurement(
                "abm_deals_without_company",
                link="deal_continuity",
                control="deal_company_association",
                population_key="deals_without_company",
                role="breakdown",
                denominator=2,
                affected=2,
                percentage=100,
                leakage_candidate=True,
            ),
            _measurement(
                "activity_without_deal",
                link="owner_to_deal",
                control="owner_deal",
                role="supporting",
                denominator=10,
                affected=10,
                percentage=100,
                leakage_candidate=True,
                outside_score_reason="Overlaps the journey-partitioned population.",
            ),
        ]
    )
    score = compute_lifecycle_score([], _registry(), rows)
    assert score["journey_link_scores"]["deal_continuity"]["deducted"] == 0.5
    assert score["journey_link_scores"]["owner_to_deal"]["deducted"] == 0


def test_recovery_opportunity_does_not_make_control_assessable():
    rows = [row for row in _full_coverage() if row["score_control"] != "expansion_customer_state"]
    rows.append(
        _measurement(
            "closed_lost_recovery_opportunity",
            link="post_close_recovery",
            role="opportunity_only",
            denominator=5,
            affected=2,
            percentage=40,
            outside_score_reason="Commercial opportunity, not a confirmed control break.",
        )
    )
    score = compute_lifecycle_score([], _registry(), rows)
    post_close = score["journey_link_scores"]["post_close_recovery"]
    assert post_close["score"] is None
    assert post_close["assessment_reason"] == "scored_control_population_unavailable"
    assert score["coverage_percentage"] == 85


@pytest.mark.parametrize(
    "malformed, message",
    [
        ("not-an-object", "must be an object"),
        ({"available": "yes"}, "available must be boolean"),
    ],
)
def test_malformed_measurements_fail_closed(malformed, message):
    rows = _full_coverage()
    if isinstance(malformed, dict):
        rows[0].update(malformed)
    else:
        rows.append(malformed)
    with pytest.raises(ValueError, match=message):
        compute_lifecycle_score([], _registry(), rows)


def _rejected(measurement_id: str, basis: str) -> LifecycleFinding:
    finding = _finding(measurement_id)
    return finding.model_copy(update={"review_status": "rejected", "rejection_basis": basis})


def test_valid_exception_counts_as_healthy_but_invalid_measurement_is_unassessed():
    rows = _full_coverage()
    rows[-1] = _measurement(
        "expansion_customer_state", link="post_close_recovery", control="expansion_customer_state",
        affected=6, percentage=60,
    )
    exception = compute_lifecycle_score([_rejected("expansion_customer_state", "valid_exception")], _registry(), rows)
    control = exception["control_scores"]["expansion_customer_state"]
    assert control["status"] == "healthy" and control["assessed_weight"] == 15
    assert exception["coverage_percentage"] == 100

    invalid = compute_lifecycle_score([_rejected("expansion_customer_state", "invalid_measurement")], _registry(), rows)
    control = invalid["control_scores"]["expansion_customer_state"]
    assert control["status"] == "not_assessable"
    assert control["assessment_reason"] == "measurement_rejected_as_invalid"
    assert control["assessed_weight"] == 0
    assert control["evidence_measurements"][0]["status"] == "invalid_measurement"
    assert invalid["coverage_percentage"] == 85


def test_invalid_motion_population_leaves_the_rest_of_the_control_assessed():
    rows = [row for row in _full_coverage() if row["score_control"] != "open_deal_owner"] + [
        _measurement("inbound_deals_without_owner", link="deal_progression", control="open_deal_owner",
                     population_key="open_deal_owner:inbound", denominator=10, affected=10, percentage=100),
        _measurement("expansion_deals_without_owner", link="deal_progression", control="open_deal_owner",
                     population_key="open_deal_owner:expansion", denominator=30, affected=0, percentage=0),
    ]
    score = compute_lifecycle_score([_rejected("inbound_deals_without_owner", "invalid_measurement")], _registry(), rows)
    control = score["control_scores"]["open_deal_owner"]
    assert control["assessed_weight"] == 10
    assert control["population_denominator"] == 30
    assert control["status"] == "healthy"
    statuses = {item["measurement_id"]: item["status"] for item in control["evidence_measurements"]}
    assert statuses["inbound_deals_without_owner"] == "invalid_measurement"
