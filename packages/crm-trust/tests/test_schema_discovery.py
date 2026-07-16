"""Validation tests for LLM judgment artifacts (fidelity gate)."""
from __future__ import annotations

import json

import yaml

from core.validators import (
    validate_audit_profile,
    validate_business_context,
    validate_crm_context,
)

VALID_CONTEXT = {
    "audit_focus": "marketing_to_pipeline_trust",
    "crm_complexity": {"tier": "lean_smb", "confidence": "medium"},
    "canonical_fields": {
        "lifecycle_stage": {
            "object": "contact",
            "field": "lifecyclestage",
            "confidence": "high",
            "requires_confirmation": False,
            "evidence": "fill_rate 90.0, standard HubSpot field",
        },
        "original_source": {
            "object": "contact",
            "field": "hs_analytics_source",
            "confidence": "high",
            "requires_confirmation": False,
            "evidence": "fill_rate 70.0 overall",
        },
    },
    "suspected_legacy_fields": ["old_lead_source_2021"],
    "manual_confirmation_needed": ["utm_notes"],
}


def write_context(run, data):
    (run / "crm_context.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


def test_valid_crm_context_passes(synthetic_run):
    write_context(synthetic_run, VALID_CONTEXT)
    assert validate_crm_context(synthetic_run) == []


def test_missing_artifact_is_reported(synthetic_run):
    problems = validate_crm_context(synthetic_run)
    assert problems and "not found" in problems[0]


def test_invented_field_is_rejected(synthetic_run):
    data = json.loads(json.dumps(VALID_CONTEXT))
    data["canonical_fields"]["original_source"]["field"] = "hallucinated_field"
    write_context(synthetic_run, data)
    problems = validate_crm_context(synthetic_run)
    assert any("does not exist" in p for p in problems)


def test_invented_legacy_field_is_rejected(synthetic_run):
    data = json.loads(json.dumps(VALID_CONTEXT))
    data["suspected_legacy_fields"] = ["field_that_never_existed"]
    write_context(synthetic_run, data)
    problems = validate_crm_context(synthetic_run)
    assert any("does not exist" in p for p in problems)


def test_low_confidence_requires_confirmation(synthetic_run):
    data = json.loads(json.dumps(VALID_CONTEXT))
    data["canonical_fields"]["original_source"]["confidence"] = "medium"
    data["canonical_fields"]["original_source"]["requires_confirmation"] = False
    write_context(synthetic_run, data)
    problems = validate_crm_context(synthetic_run)
    assert any("requires_confirmation" in p for p in problems)


def test_business_context_validation(synthetic_run):
    path = synthetic_run / "business_context.json"
    path.write_text(
        json.dumps(
            {
                "crm_complexity_tier": "lean_smb",
                "likely_motion": "b2b_sales_led",
                "pipeline_complexity": "single_pipeline",
                "attribution_maturity": "partial",
                "confidence": "medium",
                "evidence": ["10 contacts, 5 deals, 1 pipeline"],
            }
        ),
        encoding="utf-8",
    )
    assert validate_business_context(synthetic_run) == []

    path.write_text(json.dumps({"confidence": "medium"}), encoding="utf-8")
    assert validate_business_context(synthetic_run)


def test_audit_profile_validation(synthetic_run):
    path = synthetic_run / "audit_profile.json"
    path.write_text(
        json.dumps(
            {
                "selected_profile": "lean_b2b_crm",
                "reason": "small portal, single pipeline",
                "threshold_adjustments": {},
            }
        ),
        encoding="utf-8",
    )
    assert validate_audit_profile(synthetic_run) == []

    path.write_text(
        json.dumps({"selected_profile": "not_a_real_profile", "reason": "x"}),
        encoding="utf-8",
    )
    assert validate_audit_profile(synthetic_run)
