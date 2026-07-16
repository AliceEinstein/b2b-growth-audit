"""Findings validator tests: numbers must trace to measurements verbatim."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.profiler import profile_run
from core.rules import measure_all
from core.schemas import CrmContext
from core.validators import validate_findings
from connectors.hubspot.normalize import write_json

from test_rules import CONTEXT, add_deal_contact_associations


@pytest.fixture
def measured_run(synthetic_run) -> Path:
    profile_run(synthetic_run)
    add_deal_contact_associations(synthetic_run)
    context = CrmContext.model_validate(CONTEXT)
    results = measure_all(synthetic_run, context)
    for module, doc in results.items():
        write_json(
            synthetic_run / "processed" / "measurements" / f"{module}.json", doc
        )
    (synthetic_run / "findings").mkdir()
    return synthetic_run


BASE_FINDING = {
    "id": "missing_original_source",
    "module": "attribution_trust",
    "severity": "high",
    "confidence": "high",
    "object_type": "contacts",
    "measurement_id": "contacts_missing_original_source",
    "field_name": "hs_analytics_source",
    "denominator": 10,
    "affected_records": 3,
    "affected_percentage": 30.0,
    "evidence_file": "evidence/attribution_trust.csv",
    "business_impact": "Recent attribution reporting is unreliable.",
    "recommendation_type": "needs_business_rule_confirmation",
    "auto_fix_allowed": False,
    "review_status": "pending",
}


def write_findings(run: Path, findings: list, module="attribution_trust") -> None:
    (run / "findings" / f"{module}_findings.json").write_text(
        json.dumps({"module": module, "findings": findings}), encoding="utf-8"
    )


def test_valid_finding_passes(measured_run):
    write_findings(measured_run, [BASE_FINDING])
    problems = validate_findings(measured_run, modules=["attribution_trust"])
    assert problems["attribution_trust"] == []


def test_llm_adjusted_number_is_rejected(measured_run):
    doctored = dict(BASE_FINDING, affected_records=5)  # measurement says 3
    write_findings(measured_run, [doctored])
    problems = validate_findings(measured_run, modules=["attribution_trust"])
    assert any("does not match measurement" in p for p in problems["attribution_trust"])


def test_invented_measurement_is_rejected(measured_run):
    doctored = dict(BASE_FINDING, measurement_id="made_up_metric")
    write_findings(measured_run, [doctored])
    problems = validate_findings(measured_run, modules=["attribution_trust"])
    assert any("does not exist" in p for p in problems["attribution_trust"])


def test_citing_unavailable_measurement_is_rejected(synthetic_run):
    # No deal->contact associations: the trace measurement is a gap.
    profile_run(synthetic_run)
    context = CrmContext.model_validate(CONTEXT)
    results = measure_all(synthetic_run, context)
    for module, doc in results.items():
        write_json(synthetic_run / "processed" / "measurements" / f"{module}.json", doc)
    (synthetic_run / "findings").mkdir()
    doctored = dict(
        BASE_FINDING,
        measurement_id="closedwon_deals_without_source_trace",
        denominator=2,
        affected_records=2,
        affected_percentage=100.0,
    )
    write_findings(synthetic_run, [doctored])
    problems = validate_findings(synthetic_run, modules=["attribution_trust"])
    assert any("unavailable" in p for p in problems["attribution_trust"])


def test_qualitative_finding_must_not_carry_numbers(measured_run):
    doctored = dict(BASE_FINDING)
    doctored.pop("measurement_id")
    write_findings(measured_run, [doctored])
    problems = validate_findings(measured_run, modules=["attribution_trust"])
    assert any("without a measurement_id" in p for p in problems["attribution_trust"])


def test_auto_fix_is_always_rejected(measured_run):
    doctored = dict(BASE_FINDING, auto_fix_allowed=True)
    write_findings(measured_run, [doctored])
    problems = validate_findings(measured_run, modules=["attribution_trust"])
    assert any("auto_fix_allowed" in p for p in problems["attribution_trust"])


def test_evidence_file_cannot_escape_module_evidence(measured_run):
    doctored = dict(BASE_FINDING, evidence_file="../raw/contacts.jsonl")
    write_findings(measured_run, [doctored])
    problems = validate_findings(measured_run, modules=["attribution_trust"])
    assert any("must be exactly" in p for p in problems["attribution_trust"])


def test_missing_findings_file_is_reported(measured_run):
    problems = validate_findings(measured_run, modules=["lifecycle_funnel"])
    assert any("not found" in p for p in problems["lifecycle_funnel"])
