"""Full-chain final gate test on the broken_attribution sample.

Simulates the LLM roles with recorded fixtures (findings copied verbatim
from real measurements, complete review log, reports with all required
sections) and asserts the deterministic gate passes — then breaks each
safety property and asserts it fails.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from connectors.hubspot.normalize import write_json
from core.final_gate import run_final_gate, verify_final_gate_report
from core.integrity import sha256_file
from core.profiler import profile_run
from core.rules import MODULES, measure_all
from core.schemas import CrmContext, Finding
from core.scoring import compute_score
from core.synthetic_datasets import DATASETS
from core.validators import REVIEWERS
from scripts.generate_reports import consolidate_evidence


def _finding_from(measurement, fid, severity, rec_type):
    return {
        "id": fid,
        "module": "attribution_trust",
        "severity": severity,
        "confidence": "high",
        "object_type": measurement["object_type"],
        "measurement_id": measurement["id"],
        "field_name": measurement["field_name"],
        "denominator": measurement["denominator"],
        "affected_records": measurement["affected_records"],
        "affected_percentage": measurement["affected_percentage"],
        "evidence_file": "evidence/attribution_trust.csv",
        "business_impact": "Source capture is unreliable for recent records.",
        "recommendation_type": rec_type,
        "auto_fix_allowed": False,
        "review_status": "approved",
    }


def _report_text(total: int) -> str:
    sections = [
        "# HubSpot Marketing-to-Pipeline Trust Audit",
        "## CRM Trust Score", f"**{total}/100**",
        "## Executive Summary", "Attribution capture is degrading.",
        "## Business Context Detected", "Lean B2B portal.",
        "## Audit Scope", "Marketing-to-pipeline trust only.",
        "## Critical Findings", "See findings.json.",
        "## Evidence Summary", "Hashed record ids in evidence.csv.",
        "## Priority Recommendations", "Confirm source capture rules.",
        "## Safe Actions", "Draft a review list.",
        "## Needs Business Rule Confirmation", "Source governance for imports.",
        "## Do Not Auto-Fix", "Anything rewriting source history.",
        "## Limitations", "90-day window; associations partially available.",
        "## Suggested Next Review", "Re-run in 90 days.",
    ]
    return "\n\n".join(sections) + "\n"


def _handoff_text() -> str:
    sections = [
        "# Agent Handoff: CRM Trust Audit Follow-up",
        "## Safety Boundary",
        "This audit was generated in read-only mode. Do not perform CRM "
        "write actions unless the user explicitly provides write access "
        "and approves an implementation plan.",
        "## Approved Low-Risk Follow-ups", "Build the source review list.",
        "## Manual Confirmation Required", "Import attribution policy.",
        "## Blocked Actions", "- delete properties (prohibited)",
        "## Suggested Implementation Sequence", "Review list first.",
        "## Evidence Files", "evidence.csv",
        "## Questions to Ask Human Owner Before Any Write Action",
        "Which source field is canonical?",
    ]
    return "\n\n".join(sections) + "\n"


@pytest.fixture
def finalized_run(tmp_path) -> Path:
    run, context_data, _ = DATASETS["broken_attribution_sample"](tmp_path)
    profile_run(run)
    results = measure_all(run, CrmContext.model_validate(context_data))
    for module, doc in results.items():
        write_json(run / "processed" / "measurements" / f"{module}.json", doc)

    measurements = {m["id"]: m for m in results["attribution_trust"]["measurements"]}
    findings = [
        _finding_from(
            measurements["recent_half_contacts_missing_original_source"],
            "recent_source_breakdown", "high", "needs_business_rule_confirmation",
        ),
        _finding_from(
            measurements["closedwon_deals_without_source_trace"],
            "won_deals_untraceable", "medium", "needs_business_rule_confirmation",
        ),
    ]
    (run / "findings").mkdir()
    write_json(
        run / "findings" / "attribution_trust_findings.json",
        {"module": "attribution_trust", "findings": findings},
    )
    for module in MODULES:
        if module != "attribution_trust":
            write_json(
                run / "findings" / f"{module}_findings.json",
                {"module": module, "findings": []},
            )

    write_json(
        run / "review_log.json",
        [
            {"finding_id": f["id"], "reviewer": r, "verdict": "approve",
             "reason": "verified against measurements"}
            for f in findings
            for r in REVIEWERS
        ],
    )
    write_json(
        run / "recommendations.json",
        {
            "safe_operational_actions": [
                {"finding_id": "recent_source_breakdown",
                 "action": "Draft a review list of recent contacts missing source.",
                 "classification_reason": "This is a reversible review-list draft and does not change CRM truth."}
            ],
            "needs_business_rule_confirmation": [
                {"finding_id": "won_deals_untraceable",
                 "action": "Decide how won deals should trace to acquisition source.",
                 "classification_reason": "The canonical attribution rule must be confirmed for this business."}
            ],
            "do_not_auto_fix": [],
        },
    )

    models = [Finding.model_validate(f) for f in findings]
    score = compute_score(models)
    write_json(run / "score.json", score)
    write_json(run / "findings.json", {"findings": findings})
    consolidate_evidence(run)

    (run / "crm_trust_report.md").write_text(
        _report_text(score["total"]), encoding="utf-8"
    )
    (run / "agent_handoff.md").write_text(_handoff_text(), encoding="utf-8")
    (run / "schema_discovery_report.md").write_text(
        "# Schema Discovery Report\n\nValidated synthetic context.\n",
        encoding="utf-8",
    )
    write_json(run / "audit_log.json", {"events": [], "warnings": []})
    write_json(
        run / "safety_clearance.json",
        [{"phrase": "delete properties", "file": "agent_handoff.md",
          "file_sha256": sha256_file(run / "agent_handoff.md"),
          "reason": "listed under Blocked Actions as prohibited, not recommended"}],
    )
    return run


def test_complete_run_passes_final_gate(finalized_run):
    doc = run_final_gate(finalized_run)
    assert doc["hard_leaks"] == []
    assert doc["uncleared_phrases"] == []
    assert doc["problems"] == {}
    assert doc["passed"] is True
    assert doc["cleared_phrases"] == 1
    assert (finalized_run / "final_gate_report.json").exists()


def test_stored_pass_is_invalidated_when_a_deliverable_changes(finalized_run):
    run_final_gate(finalized_run)
    assert verify_final_gate_report(finalized_run) == []
    path = finalized_run / "agent_handoff.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
    assert any("deliverables changed" in p for p in verify_final_gate_report(finalized_run))


def test_missing_report_section_fails(finalized_run):
    report = finalized_run / "crm_trust_report.md"
    report.write_text(
        report.read_text(encoding="utf-8").replace("## Limitations", "## Notes"),
        encoding="utf-8",
    )
    doc = run_final_gate(finalized_run)
    assert doc["passed"] is False
    assert any("Limitations" in p for p in doc["problems"]["reports"])


def test_uncleared_blocked_phrase_fails(finalized_run):
    report = finalized_run / "crm_trust_report.md"
    report.write_text(
        report.read_text(encoding="utf-8")
        + "\nConsider a script to bulk update owner records.\n",
        encoding="utf-8",
    )
    doc = run_final_gate(finalized_run)
    assert doc["passed"] is False
    assert {"phrase": "bulk update owner", "file": "crm_trust_report.md"} in doc[
        "uncleared_phrases"
    ]


def test_pii_leak_fails_hard_even_with_clean_reviews(finalized_run):
    report = finalized_run / "crm_trust_report.md"
    report.write_text(
        report.read_text(encoding="utf-8") + "\nContact: jane.doe@acme.com\n",
        encoding="utf-8",
    )
    doc = run_final_gate(finalized_run)
    assert doc["passed"] is False
    assert doc["hard_leaks"] and doc["hard_leaks"][0]["kind"] == "email"
    # the leaked value itself is never reproduced in the gate report
    assert "jane.doe@acme.com" not in json.dumps(doc)


def test_edited_score_fails(finalized_run):
    score_path = finalized_run / "score.json"
    stored = json.loads(score_path.read_text(encoding="utf-8"))
    stored["total"] = 99  # LLM "improves" the score
    write_json(score_path, stored)
    doc = run_final_gate(finalized_run)
    assert doc["passed"] is False
    assert any("code-owned" in p for p in doc["problems"]["score"])


def test_recommendation_requires_classification_reason(finalized_run):
    path = finalized_run / "recommendations.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["safe_operational_actions"][0]["classification_reason"]
    write_json(path, data)
    doc = run_final_gate(finalized_run)
    assert doc["passed"] is False
    assert "recommendations" in doc["problems"]
