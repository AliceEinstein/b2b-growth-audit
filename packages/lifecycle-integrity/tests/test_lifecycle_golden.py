from __future__ import annotations

import csv
import json

import pytest

from core.lifecycle_final_gate import run_lifecycle_final_gate
from core.lifecycle_synthetic_datasets import LIFECYCLE_DATASETS
from core.lifecycle_validators import validate_findings, validate_reviews
from lifecycle_test_support import (
    build_lifecycle_run,
    generate_reports_and_clear_safety,
    measurement,
    write_judgment_artifacts,
)


@pytest.mark.parametrize("name", sorted(LIFECYCLE_DATASETS))
def test_lifecycle_dataset_golden_contract(tmp_path, name):
    run_dir, expected = build_lifecycle_run(tmp_path, name)
    registry = json.loads(
        (run_dir / "journey_pattern_registry.json").read_text(encoding="utf-8")
    )
    scores = {
        pattern["journey_type"]: pattern["confidence_score"]
        for pattern in registry["patterns"]
    }
    for journey, bounds in expected["expected_confidence_ranges"].items():
        assert bounds[0] <= scores[journey] <= bounds[1]

    expected_findings = expected["expected_findings"]
    for finding_id in expected_findings:
        row = measurement(run_dir, finding_id)
        assert row["affected_records"], f"{name}: expected finding has no affected records"

    if expected.get("expected_primary_model"):
        assert registry["primary_model"] == expected["expected_primary_model"]

    if expected.get("expected_assignment"):
        store = json.loads(
            (run_dir / "processed" / "journey_evidence_store.json").read_text(
                encoding="utf-8"
            )
        )
        assert store["assignment_counts"].get(expected["expected_assignment"], 0) > 0

    if expected["expected_observations"]:
        with (run_dir / "outlier_registry.csv").open(encoding="utf-8") as fh:
            outliers = list(csv.DictReader(fh))
        observed = {
            f"{row['outlier_type']}:{row['classification']}" for row in outliers
        }
        assert set(expected["expected_observations"]) <= observed

    selected = expected_findings[0] if expected_findings else None
    write_judgment_artifacts(run_dir, selected)
    assert validate_findings(run_dir) == []
    assert validate_reviews(run_dir, final=True) == []
    generate_reports_and_clear_safety(run_dir)
    gate = run_lifecycle_final_gate(run_dir)
    assert gate["passed"] is True, gate

    findings = json.loads((run_dir / "findings.json").read_text(encoding="utf-8"))
    assert all(row["auto_fix_allowed"] is False for row in findings["findings"])
    report = (run_dir / "lifecycle_integrity_report.md").read_text(encoding="utf-8")
    assert report.startswith("# ") and "Lifecycle Integrity Audit" in report.splitlines()[0]
    handoff = (run_dir / "agent_handoff.md").read_text(encoding="utf-8")
    assert "read-only mode" in handoff
    assert "Do not" in handoff
