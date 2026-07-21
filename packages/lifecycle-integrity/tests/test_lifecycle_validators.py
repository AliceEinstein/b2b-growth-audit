from __future__ import annotations

import json

import pytest

from core.lifecycle_reports import generate_lifecycle_reports
from core.lifecycle_validators import (
    validate_findings,
    validate_measurement_scoring_contract,
)
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


def test_validator_rejects_duplicate_or_inferred_scoring_ownership(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "pipeline_leakage_sample")
    path = run_dir / "processed" / "lifecycle_integrity_measurements.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    primary = next(
        row
        for row in document["measurements"]
        if row.get("score_role") == "primary"
    )
    duplicate = dict(primary)
    duplicate["id"] = "duplicate_primary_population"
    document["measurements"].append(duplicate)
    path.write_text(json.dumps(document), encoding="utf-8")

    problems = validate_measurement_scoring_contract(run_dir)
    assert any("multiple primary measurements" in row for row in problems)
    write_judgment_artifacts(run_dir)
    with pytest.raises(ValueError, match="multiple primary measurements"):
        generate_lifecycle_reports(run_dir)


def test_validator_rejects_leakage_candidate_without_explicit_score_role(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "pipeline_leakage_sample")
    path = run_dir / "processed" / "lifecycle_integrity_measurements.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    row = next(
        item for item in document["measurements"] if item.get("leakage_candidate")
    )
    row["score_role"] = "not_scored"
    row["score_link"] = None
    row["score_population_key"] = None
    path.write_text(json.dumps(document), encoding="utf-8")

    problems = validate_measurement_scoring_contract(run_dir)
    assert any("leakage_candidate requires" in problem for problem in problems)


def test_finding_cannot_confirm_multiple_primary_score_populations(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "pipeline_leakage_sample")
    write_judgment_artifacts(run_dir, "deals_without_company")
    measurement_doc = json.loads(
        (run_dir / "processed" / "lifecycle_integrity_measurements.json").read_text(
            encoding="utf-8"
        )
    )
    second_primary = next(
        row["id"]
        for row in measurement_doc["measurements"]
        if row.get("score_role") == "primary" and row["id"] != "deals_without_company"
    )
    findings = _load_findings(run_dir)
    findings["findings"][0]["evidence_refs"].append(
        f"evidence.csv#finding_id={second_primary}"
    )
    (run_dir / "findings.json").write_text(json.dumps(findings), encoding="utf-8")

    assert any(
        "cites multiple primary score populations" in problem
        for problem in validate_findings(run_dir)
    )
