from __future__ import annotations

import json

import pytest

from core.lifecycle_reports import generate_lifecycle_reports
from core.lifecycle_validators import validate_findings
from lifecycle_test_support import build_lifecycle_run, write_judgment_artifacts


def _load_findings(run_dir):
    return json.loads((run_dir / "findings.json").read_text(encoding="utf-8"))


def test_validator_rejects_wrong_denominator(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    write_judgment_artifacts(run_dir, "deals_without_company")
    doc = _load_findings(run_dir)
    doc["findings"][0]["denominator"] += 1
    (run_dir / "findings.json").write_text(json.dumps(doc), encoding="utf-8")
    assert any("denominator does not match" in row for row in validate_findings(run_dir))
    with pytest.raises(ValueError, match="denominator does not match"):
        generate_lifecycle_reports(run_dir)


def test_low_confidence_pattern_can_only_produce_observation(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "legacy_property_sprawl_sample")
    write_judgment_artifacts(
        run_dir,
        "lifecycle_field_fragmentation",
        journey_pattern="inbound_new_business",
        severity="high",
    )
    assert any("below 50 can only produce observations" in row for row in validate_findings(run_dir))


def test_every_scored_finding_requires_an_evidence_row(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "clean_inbound_crm_sample")
    write_judgment_artifacts(run_dir, None)
    finding = {
        "finding_id": "invented_gap",
        "journey_pattern": "inbound_new_business",
        "integrity_dimension": "association_integrity",
        "severity": "medium",
        "confidence_score": 80,
        "confidence_label": "high",
        "object_type": "deals",
        "affected_records": 1,
        "affected_percentage": 25.0,
        "denominator": 4,
        "evidence_refs": ["evidence.csv#finding_id=invented_gap"],
        "business_impact": "Invented.",
        "recommended_action": "Review.",
        "recommendation_type": "safe_operational_action",
        "auto_fix_allowed": False,
        "review_intensity": "medium",
    }
    (run_dir / "findings.json").write_text(
        json.dumps({"findings": [finding]}), encoding="utf-8"
    )
    problems = validate_findings(run_dir)
    assert any("no deterministic measurement cited" in row for row in problems)
