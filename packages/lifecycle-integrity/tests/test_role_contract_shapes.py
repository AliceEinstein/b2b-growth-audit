"""Prompt-shaped contract tests.

Each fixture below is shaped exactly as the corresponding subagents/*.md file
instructs the role to write its output. If a schema and a prompt drift apart,
these tests fail — a correctly-obedient agent must never produce an artifact
the deterministic gates reject, and a wrong-keyed artifact must never be
silently accepted as empty.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.lifecycle_agent_tasks import TASKS
from core.lifecycle_workspace import GATE_OWNED_SCHEMAS, SCHEMA_MODELS

FULL_FINDING = {
    "finding_id": "deals_without_company",
    "journey_pattern": "all_detected_journeys",
    "integrity_dimension": "association_integrity",
    "severity": "medium",
    "confidence_score": 80,
    "confidence_label": "high",
    "object_type": "deals",
    "denominator": 4,
    "affected_records": 1,
    "evidence_refs": ["evidence.csv#finding_id=deals_without_company"],
    "business_impact": "Deals detached from companies break pipeline reporting.",
    "recommended_action": "Confirm the canonical association rule.",
    "recommendation_type": "safe_operational_action",
    "auto_fix_allowed": False,
    "review_intensity": "medium",
}
FULL_REVIEW = {
    "finding_id": "deals_without_company",
    "reviewer": "data_fidelity_reviewer",
    "verdict": "approved",
    "reason": "Numbers match deterministic artifacts.",
    "evidence_refs": ["evidence.csv#finding_id=deals_without_company"],
    "revision_round": 0,
}


def test_every_declared_schema_has_a_model():
    for task in TASKS:
        schema = task["output_schema"]
        if schema in GATE_OWNED_SCHEMAS:
            continue
        assert schema in SCHEMA_MODELS, f"{task['role']} declares unmodeled schema {schema}"


def test_reviewer_doc_shape_matches_reviewer_prompts():
    doc = {"role": "data_fidelity_reviewer", "reviews": [FULL_REVIEW]}
    parsed = SCHEMA_MODELS["review_decisions"].model_validate(doc)
    assert parsed.reviews[0].reviewer == "data_fidelity_reviewer"


def test_automation_analysis_contract_is_strict_and_complete():
    valid = {
        "role": "automation_scoring_analysis_agent",
        "summary": "Workflow configuration was unavailable.",
        "available_signals": [],
        "control_gaps": [],
        "evidence_refs": [],
        "limitations": ["No automation scope was available."],
        "human_confirmation_needed": [],
    }
    parsed = SCHEMA_MODELS["automation_analysis_result"].model_validate(valid)
    assert parsed.summary.startswith("Workflow")
    with pytest.raises(ValidationError):
        SCHEMA_MODELS["automation_analysis_result"].model_validate(
            {"role": "automation_scoring_analysis_agent"}
        )
    with pytest.raises(ValidationError):
        SCHEMA_MODELS["automation_analysis_result"].model_validate(
            {**valid, "raw_workflow_payload": {"email": "person@example.com"}}
        )


def test_root_cause_contract_rejects_unbounded_and_untraceable_output():
    valid = {
        "role": "automation_root_cause_agent",
        "assessments": [
            {
                "finding_id": "finding-1",
                "configuration_status": "control_absent",
                "causal_status": "possible",
                "confidence_score": 30,
                "workflow_aliases": [],
                "score_fields": [],
                "evidence_refs": ["automation_evidence.csv#measurement_id=m-1"],
                "limitations": [],
                "recommendation_category": "review_configuration",
            }
        ],
    }
    SCHEMA_MODELS["root_cause_assessments"].model_validate(valid)
    with pytest.raises(ValidationError):
        SCHEMA_MODELS["root_cause_assessments"].model_validate(
            {
                **valid,
                "assessments": [
                    {**valid["assessments"][0], "raw_workflow_payload": {"x": 1}}
                ],
            }
        )


def test_legacy_review_decisions_key_fails_loudly():
    with pytest.raises(ValidationError):
        SCHEMA_MODELS["review_decisions"].model_validate(
            {"role": "data_fidelity_reviewer", "review_decisions": [FULL_REVIEW]}
        )


def test_outlier_doc_shape_matches_outlier_prompt():
    doc = {
        "candidate_findings": [FULL_FINDING],
        "classification_review": [{"outlier_id": "x", "agrees": True}],
        "observations": ["one benign outlier"],
        "assumptions": [],
        "coverage_limitations": [],
    }
    parsed = SCHEMA_MODELS["candidate_findings"].model_validate(doc)
    assert len(parsed.candidate_findings) == 1


def test_promoted_findings_under_wrong_key_fail_loudly():
    with pytest.raises(ValidationError):
        SCHEMA_MODELS["candidate_findings"].model_validate(
            {"promoted_candidate_findings": [FULL_FINDING]}
        )


def test_mixed_motion_doc_shape_matches_its_prompt():
    doc = {
        "role": "mixed_motion_journey_agent",
        "journey_model_assessment": "Two motions coexist; do not collapse them.",
        "coexisting_patterns": ["inbound_new_business", "expansion_renewal"],
        "conflicts": [],
        "global_rules_that_must_not_be_applied": ["single-funnel MQL requirement"],
        "evidence_refs": ["journey_pattern_registry.json"],
        "assumptions": [],
        "limitations": [],
        "human_confirmation_needed": [],
        "unclassified_motion_candidate": None,
        "unclassified_motion_evidence_refs": [],
        "unclassified_motion_limitations": [],
        "unclassified_motion_requires_confirmation": False,
    }
    parsed = SCHEMA_MODELS["mixed_motion_assessment"].model_validate(doc)
    assert parsed.journey_model_assessment
    # The generic journey schema would reject this shape — the dedicated
    # schema exists precisely because the prompts differ.
    with pytest.raises(ValidationError):
        SCHEMA_MODELS["journey_hypothesis"].model_validate(doc)


def test_journey_hypothesis_doc_shape_matches_its_prompt():
    doc = {
        "role": "inbound_journey_hypothesis_agent",
        "journey_pattern": "inbound_new_business",
        "verdict": "supported",
        "confidence_assessment": "registry arithmetic is consistent",
        "supporting_evidence": ["source fields populated"],
        "contradicting_evidence": [],
        "record_assignment_constraints": [],
        "entry_signals": ["Inbound source or form intent"],
        "expected_milestones": ["Qualified lead", "Owner handoff", "Deal"],
        "handoff_expectations": ["Owner present before sales follow-up"],
        "valid_skips": [],
        "leakage_tests": ["Qualified contacts without an owner or associated deal"],
        "assumptions": [],
        "limitations": [],
        "human_confirmation_needed": [],
    }
    SCHEMA_MODELS["journey_hypothesis"].model_validate(doc)


def test_unclassified_motion_requires_evidence_and_confirmation():
    with pytest.raises(ValidationError):
        SCHEMA_MODELS["mixed_motion_assessment"].model_validate(
            {
                "role": "mixed_motion_journey_agent",
                "journey_model_assessment": "Residual signals may indicate another motion.",
                "unclassified_motion_candidate": "product-led assist",
                "unclassified_motion_evidence_refs": [],
                "unclassified_motion_requires_confirmation": False,
            }
        )


def test_schema_discovery_doc_shape_matches_its_prompt():
    doc = {
        "role": "schema_discovery_agent",
        "status": "complete",
        "confidence_score": 70,
        "candidate_mappings": [
            {
                "object": "contacts",
                "property": "hs_analytics_source",
                "intent": "source",
                "confidence": "high",
                "evidence": "processed/source_field_candidates.json",
            }
        ],
        "legacy_fields": [],
        "contradictions": [],
        "evidence_refs": [],
        "assumptions": [],
        "limitations": [],
        "human_confirmation_needed": [],
    }
    SCHEMA_MODELS["analysis_result"].model_validate(doc)


def test_recommendation_plan_shape_matches_its_prompt():
    doc = {
        "priority_actions": [],
        "safe_operational_actions": [
            {
                "finding_id": "deals_without_company",
                "owner_role": "revops_owner",
                "expected_outcome": "Reviewed exception list.",
                "target": "deal-company association",
                "current_state": "Some deals have no company association.",
                "desired_state": "Every intentional deal exception is documented and the remaining coverage is restored.",
                "implementation_steps": ["Review", "Approve", "Measure"],
                "approval_required": "Business owner approval required.",
                "success_measure": "Association coverage improves in the next audit.",
                "evidence_refs": ["evidence.csv"],
            }
        ],
        "human_confirmation_needed": [],
        "observations_to_monitor": [],
        "do_not_auto_fix": [],
    }
    SCHEMA_MODELS["recommendation_lanes"].model_validate(doc)
