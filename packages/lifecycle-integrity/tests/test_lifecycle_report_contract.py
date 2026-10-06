from __future__ import annotations

import json

from core.lifecycle_final_gate import (
    run_lifecycle_final_gate,
    verify_lifecycle_final_gate_report,
)
from core.lifecycle_reports import generate_lifecycle_reports
from lifecycle_test_support import (
    build_lifecycle_run,
    generate_reports_and_clear_safety,
    write_judgment_artifacts,
)


def test_final_gate_requires_contextual_clearance_for_blocked_phrases(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    write_judgment_artifacts(run_dir, "deals_without_company")
    generate_lifecycle_reports(run_dir)
    first = run_lifecycle_final_gate(run_dir)
    assert first["passed"] is False
    assert first["uncleared_phrases"]

    generate_reports_and_clear_safety(run_dir)
    second = run_lifecycle_final_gate(run_dir)
    assert second["passed"] is True, second


def test_final_gate_hard_fails_on_pii_even_after_reviewer_clearance(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    write_judgment_artifacts(run_dir, "deals_without_company")
    generate_reports_and_clear_safety(run_dir)
    report = run_dir / "lifecycle_integrity_report.md"
    report.write_text(
        report.read_text(encoding="utf-8")
        + "\nContact leaked.person@example.test for details.\n",
        encoding="utf-8",
    )
    gate = run_lifecycle_final_gate(run_dir)
    assert gate["passed"] is False
    assert any(row["kind"] == "email" for row in gate["hard_leaks"])


def test_final_gate_scans_sanitized_root_cause_artifacts_for_pii(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    write_judgment_artifacts(run_dir, "deals_without_company")
    generate_reports_and_clear_safety(run_dir)
    root_cause = (
        run_dir
        / "agent_workspace"
        / "root_cause"
        / "automation_root_cause_agent.json"
    )
    root_cause.write_text(
        json.dumps(
            {
                "role": "automation_root_cause_agent",
                "assessments": [
                    {
                        "finding_id": "deals_without_company",
                        "configuration_status": "unknown",
                        "causal_status": "unverified",
                        "confidence_score": 0,
                        "workflow_aliases": [],
                        "score_fields": [],
                        "evidence_refs": [
                            "processed/automation_scoring_measurements.json"
                        ],
                        "limitations": ["Contact leaked.person@example.test."],
                        "recommendation_category": "monitor_only",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    gate = run_lifecycle_final_gate(run_dir)
    assert gate["passed"] is False
    assert any(
        row["kind"] == "email"
        and "automation_root_cause_agent" in row["file"]
        for row in gate["hard_leaks"]
    )


def test_final_gate_scans_every_general_agent_artifact_for_pii(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    write_judgment_artifacts(run_dir, "deals_without_company")
    generate_reports_and_clear_safety(run_dir)
    analysis = run_dir / "agent_workspace" / "analysis" / "schema_discovery_agent.json"
    doc = json.loads(analysis.read_text(encoding="utf-8"))
    doc["unsafe_extra"] = "Contact leaked.person@example.test."
    analysis.write_text(json.dumps(doc), encoding="utf-8")
    gate = run_lifecycle_final_gate(run_dir)
    assert gate["passed"] is False
    assert any(
        row["kind"] == "email" and "schema_discovery_agent" in row["file"]
        for row in gate["hard_leaks"]
    )


def test_lifecycle_stored_pass_covers_committed_agent_artifacts(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    write_judgment_artifacts(run_dir, "deals_without_company")
    generate_reports_and_clear_safety(run_dir)
    gate = run_lifecycle_final_gate(run_dir)
    assert gate["passed"] is True, gate
    assert verify_lifecycle_final_gate_report(run_dir) == []

    analysis = run_dir / "agent_workspace" / "analysis" / "schema_discovery_agent.json"
    analysis.write_text(
        analysis.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    assert any(
        "protected artifacts changed" in problem
        for problem in verify_lifecycle_final_gate_report(run_dir)
    )


def test_affirmative_write_recommendation_cannot_be_cleared(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    write_judgment_artifacts(run_dir, "deals_without_company")
    findings_path = run_dir / "findings.json"
    import json

    doc = json.loads(findings_path.read_text(encoding="utf-8"))
    doc["findings"][0][
        "recommended_action"
    ] = "Automatically update CRM records to repair every association."
    findings_path.write_text(json.dumps(doc), encoding="utf-8")
    generate_reports_and_clear_safety(run_dir)
    gate = run_lifecycle_final_gate(run_dir)
    assert gate["passed"] is False
    assert any(
        row["file"] == "findings.json" and row["phrase"] == "automatically update"
        for row in gate["uncleared_phrases"]
    )


def test_report_lists_owner_questions_and_writes_config_drafts(tmp_path):
    import yaml

    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    write_judgment_artifacts(run_dir, "deals_without_company")
    generate_reports_and_clear_safety(run_dir)
    report = (run_dir / "lifecycle_integrity_report.md").read_text(encoding="utf-8")
    assert "### Questions to Confirm" in report
    assert "Questions to Confirm" in (run_dir / "lifecycle_integrity_report.html").read_text(encoding="utf-8")
    drafts = run_dir / "client_config_draft"
    for name in ("field_overrides.yaml", "journey_mapping.yaml"):
        data = yaml.safe_load((drafts / name).read_text(encoding="utf-8"))
        assert data["confirmed_by"] is None
    questions = json.loads((drafts / "questions.json").read_text(encoding="utf-8"))
    handoff = (run_dir / "agent_handoff.md").read_text(encoding="utf-8")
    if questions["questions"]:
        assert "confirm_client_config" in handoff and "never answer them yourself" in handoff
    assert run_lifecycle_final_gate(run_dir)["passed"] is True
