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
        "# Example Business CRM Trust Audit",
        "HubSpot Marketing-to-Pipeline Trust Audit",
        "## Executive Summary", f"Attribution capture is degrading. **{total}/100**",
        "### How the score is calculated", "100 starting points minus validated deductions.",
        "## CRM Snapshot", "Full-history snapshot.",
        "## Data Quality and Usability", "Field-level completeness and validity.",
        "## Activity and Data Age", "Record modification age bands.",
        "## Funnel and Association Coverage", "Lifecycle and relationship coverage.",
        "## Key Findings", "### Priority 1\nAttribution risk.\n\n### Priority 2\nStructural gap.",
        "## Root Cause Hypotheses", "Import capture rule may be inconsistent.",
        "## Recommended Actions", "Confirm source capture rules.",
        "## What This Audit Cannot Determine", "Business performance is outside scope.",
        "## Evidence and Supporting Files", "Hashed record ids in evidence.csv.",
        "## Next Review", "Re-run in 90 days.",
        "## Sharing the Report", "Print the HTML to PDF before sharing.",
    ]
    return "\n\n".join(sections) + "\n"


def _html_report_text(total: int) -> str:
    sections = [
        "<h1>Example Business CRM Trust Audit</h1>",
        "<p>HubSpot Marketing-to-Pipeline Trust Audit</p>",
        f"<p>{total}/100</p>",
        "<h2>Executive Summary</h2>",
        "<h3>How this score is calculated</h3>",
        "<h2>CRM Snapshot</h2>",
        "<h2>Data Quality and Usability</h2>",
        "<h2>Activity and Data Age</h2>",
        "<h2>Funnel and Association Coverage</h2>",
        "<h2>Key Findings</h2>",
        "<h3>Priority 1</h3>",
        "<h3>Priority 2</h3>",
        "<h2>Root Cause Hypotheses</h2>",
        "<h2>Recommended Actions</h2>",
        "<h2>What This Audit Cannot Determine</h2>",
        "<h2>Evidence and Supporting Files</h2>",
        "<h2>Next Review</h2>",
        "<h2>Sharing the Report</h2>",
        '<a href="https://smartifymarketing.com">Smartify</a>',
    ]
    return "<!doctype html><html><body>" + "\n".join(sections) + "</body></html>"


def _appendix_text() -> str:
    sections = [
        "# CRM Audit Operator Appendix",
        "## How to Use This Appendix",
        "## All Validated Findings",
        "## Detailed Recommendations",
        "## Evidence Index",
        "## Schema and Context Files",
        "## Method and Audit Constraints",
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
                 "action": "Review the 40 recent contacts missing source and approve a disposition for each record.",
                 "classification_reason": "This is a reversible human review decision and does not change CRM truth.",
                 "evidence_file": "evidence/attribution_trust.csv",
                 "basis": "40 of 180 recent contacts lack original source.",
                 "expected_outcome": "All 40 records have an approved source-capture disposition or documented exception.",
                 "decision_owner": "Marketing operations owner",
                 "target": "40 contacts in evidence/attribution_trust.csv missing original source",
                 "current_state": "40 of 180 recent contacts lack original source.",
                 "desired_state": "All 40 records have an approved source-capture disposition or documented exception.",
                 "implementation_steps": ["Open the audit-prepared evidence cohort.", "Review each record.", "Approve a disposition or document an exception."],
                 "success_measure": "40 of 40 rows have a disposition.",
                 "approval_required": "Marketing operations must approve or decline each proposed source-capture disposition before any source change"}
            ],
            "needs_business_rule_confirmation": [
                {"finding_id": "won_deals_untraceable",
                 "action": "Decide how won deals should trace to acquisition source.",
                 "classification_reason": "The canonical attribution rule must be confirmed for this business.",
                 "evidence_file": "evidence/attribution_trust.csv",
                 "basis": "Closed-won deals without source traceability measurement.",
                 "expected_outcome": "A documented attribution rule for won deals.",
                 "decision_owner": "Marketing and revenue operations owner",
                 "target": "Closed-won deal attribution policy",
                 "current_state": "Some closed-won deals lack source traceability.",
                 "desired_state": "An approved rule defines source traceability for won deals.",
                 "implementation_steps": ["Review the measurement.", "Approve a canonical rule."],
                 "success_measure": "The policy names the canonical source and exception path.",
                 "approval_required": "Joint marketing and revenue operations approval"}
            ],
            "do_not_auto_fix": [],
        },
    )

    models = [Finding.model_validate(f) for f in findings]
    score = compute_score(models)
    write_json(run / "score.json", score)
    write_json(run / "findings.json", {"findings": findings})
    consolidate_evidence(run)
    (run / "report_record_evidence.csv").write_text(
        "finding_id,measurement_id,object_type,record_id_hash,company_name,deal_name,pipeline_label,deal_stage_label\n",
        encoding="utf-8",
    )

    (run / "crm_trust_report.md").write_text(
        _report_text(score["total"]), encoding="utf-8"
    )
    (run / "crm_trust_report.html").write_text(
        _html_report_text(score["total"]), encoding="utf-8"
    )
    (run / "operator_appendix.md").write_text(_appendix_text(), encoding="utf-8")
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
        report.read_text(encoding="utf-8").replace(
            "## What This Audit Cannot Determine", "## Notes"
        ),
        encoding="utf-8",
    )
    doc = run_final_gate(finalized_run)
    assert doc["passed"] is False
    assert any(
        "What This Audit Cannot Determine" in p
        for p in doc["problems"]["reports"]
    )


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


def test_blocked_phrase_clearance_outside_negative_safety_section_fails(finalized_run):
    report = finalized_run / "crm_trust_report.md"
    report.write_text(
        report.read_text(encoding="utf-8")
        + "\n## Recommended Actions\nRun a script to bulk update owner records.\n",
        encoding="utf-8",
    )
    clearance_path = finalized_run / "safety_clearance.json"
    clearances = json.loads(clearance_path.read_text(encoding="utf-8"))
    clearances.append(
        {
            "phrase": "bulk update owner",
            "file": report.name,
            "file_sha256": sha256_file(report),
            "reason": "incorrectly cleared outside a blocked section",
        }
    )
    write_json(clearance_path, clearances)
    doc = run_final_gate(finalized_run)
    assert doc["passed"] is False
    assert {"phrase": "bulk update owner", "file": report.name} in doc[
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


def test_pii_leak_in_agent_workspace_fails_hard(finalized_run):
    path = finalized_run / "harness" / "agent_outputs" / "unsafe_note.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"note": "Contact jane.doe@acme.com for context."}),
        encoding="utf-8",
    )
    doc = run_final_gate(finalized_run)
    assert doc["passed"] is False
    assert any(
        row["kind"] == "email" and row["file"] == "unsafe_note.json"
        for row in doc["hard_leaks"]
    )


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


def test_recommendation_requires_execution_detail(finalized_run):
    path = finalized_run / "recommendations.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["safe_operational_actions"][0]["implementation_steps"] = []
    write_json(path, data)
    doc = run_final_gate(finalized_run)
    assert doc["passed"] is False
    assert "recommendations" in doc["problems"]


def test_recommendation_rejects_queue_as_human_action_or_outcome(finalized_run):
    path = finalized_run / "recommendations.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    item = data["safe_operational_actions"][0]
    item["action"] = "Create a review queue for the 40 affected contacts."
    item["expected_outcome"] = "A decision-ready review queue."
    write_json(path, data)

    doc = run_final_gate(finalized_run)

    assert doc["passed"] is False
    problems = doc["problems"]["recommendations"]
    assert any("must begin with an explicit human review" in problem for problem in problems)
    assert any("treats a queue as completion" in problem for problem in problems)


@pytest.mark.parametrize(
    "action",
    [
        "Send the prepared review list to the CRM owner.",
        "Route the review queue to RevOps.",
        "Share the generated review set with Sales Ops.",
    ],
)
def test_recommendation_rejects_routed_queue_as_headline_action(finalized_run, action):
    path = finalized_run / "recommendations.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["safe_operational_actions"][0]["action"] = action
    write_json(path, data)

    doc = run_final_gate(finalized_run)

    assert doc["passed"] is False
    assert any(
        "must begin with an explicit human review" in problem
        for problem in doc["problems"]["recommendations"]
    )


def test_finding_rejects_spelled_out_measurable_quantity(finalized_run):
    path = finalized_run / "findings" / "attribution_trust_findings.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["findings"][0]["business_impact"] = "Eight records need review."
    write_json(path, data)

    doc = run_final_gate(finalized_run)

    assert doc["passed"] is False
    assert any(
        "Use Arabic numerals" in problem
        for problem in doc["problems"]["findings"]
    )


def test_recommendation_approval_must_name_the_decision(finalized_run):
    path = finalized_run / "recommendations.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    item = data["safe_operational_actions"][0]
    item["approval_required"] = item["decision_owner"]
    write_json(path, data)

    doc = run_final_gate(finalized_run)

    assert doc["passed"] is False
    assert any(
        "only repeats decision_owner" in problem
        for problem in doc["problems"]["recommendations"]
    )


def test_recommendation_basis_rejects_internal_metric_prefix(finalized_run):
    path = finalized_run / "recommendations.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["safe_operational_actions"][0]["basis"] = (
        "recent_source_breakdown: 40 of 180 Contacts are missing Original Source."
    )
    write_json(path, data)

    doc = run_final_gate(finalized_run)

    assert doc["passed"] is False
    assert any(
        "starts with an internal measurement ID" in problem
        for problem in doc["problems"]["recommendations"]
    )


def test_client_report_rejects_internal_audience_language(finalized_run):
    report = finalized_run / "crm_trust_report.md"
    report.write_text(
        report.read_text(encoding="utf-8") + "\nThis section is for CMO review.\n",
        encoding="utf-8",
    )
    doc = run_final_gate(finalized_run)
    assert doc["passed"] is False
    assert any("for cmo" in problem for problem in doc["problems"]["reports"])
