"""BYO Agent harness regression tests."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from connectors.hubspot.normalize import write_json
from core.profiler import profile_run
from core.rules import measure_all
from core.schemas import CrmContext
from harness.engine import advance
from harness.providers.base import ProviderNotConfigured, unavailable_provider
from harness.render import _narrative_plain, render_reports
from harness.state import expand_input_patterns
from harness.validation import validate_stage_output
from scripts.generate_reports import consolidate_evidence


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "mock_midmarket_abm_sales"


def _copy_fixture(tmp_path: Path) -> Path:
    run = tmp_path / "run_mock"
    shutil.copytree(FIXTURE, run)
    return run


def _write_narrative(run: Path) -> None:
    (run / "report_narrative.json").write_text(
        json.dumps(
            {
                "executive_summary": "The snapshot supports a directional CRM trust review.",
                "data_quality_summary": "Identity completeness is strong while relationship coverage has material gaps.",
                "root_causes": [],
                "limitations": ["This measures CRM data trust, not business performance."],
                "suggested_next_review": "Re-run quarterly after governance changes.",
            }
        ),
        encoding="utf-8",
    )


def test_byo_harness_pauses_at_narrative_without_provider_key(tmp_path, monkeypatch):
    run = _copy_fixture(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = advance(run)

    assert result["ready_tasks"] == ["report_narrative"]
    assert (run / "harness" / "tasks" / "report_narrative.md").exists()
    packet = json.loads((run / "harness" / "tasks" / "report_narrative.json").read_text())
    assert packet["mode"] == "byo_agent"
    assert packet["outputs"] == [str((run / "report_narrative.json").resolve())]
    assert all("/raw/" not in path for path in packet["allowed_inputs"])


def test_review_stage_does_not_reopen_after_deterministic_status_aggregation(tmp_path):
    run = _copy_fixture(tmp_path)
    first = advance(run)
    assert first["ready_tasks"] == ["report_narrative"]

    # Existing legacy report artifacts are not trusted as the new narrative;
    # the important invariant is that review stages remain complete.
    second = advance(run)
    assert not any(stage.startswith("review_") for stage in second["ready_tasks"])
    assert validate_stage_output(run, "reviews_validation") == []


def _send_back(run: Path, reviewer: str, finding_id: str, reason: str) -> None:
    path = run / "harness" / "agent_outputs" / "reviews" / (reviewer + ".json")
    entries = json.loads(path.read_text(encoding="utf-8"))
    for entry in entries:
        if entry["finding_id"] == finding_id:
            entry.update(verdict="revise", reason=reason)
    path.write_text(json.dumps(entries), encoding="utf-8")


def test_revise_verdict_opens_one_revision_round(tmp_path):
    run = _copy_fixture(tmp_path)
    first = advance(run)
    assert first["ready_tasks"] == ["report_narrative"]
    assert "revise_pipeline_hygiene" in first["skipped"]
    assert "rereview_logic_reviewer" in first["skipped"]

    target = "deals_without_amount"
    reason = "Severity overstated: amount is optional before proposal stage."
    _send_back(run, "logic_reviewer", target, reason)
    # Editing a passed review reopens that review task; the reviewer resubmits.
    reopened = advance(run)
    assert reopened["ready_tasks"] == ["review_logic_reviewer"]
    stale = next((run / "harness" / "stale").rglob("logic_reviewer.json"))
    shutil.copyfile(stale, run / "harness" / "agent_outputs" / "reviews" / "logic_reviewer.json")

    result = advance(run)
    assert result["ready_tasks"] == ["revise_pipeline_hygiene"]
    packet = json.loads((run / "harness" / "tasks" / "revise_pipeline_hygiene.json").read_text())
    assert packet["revision_requests"] == [
        {"finding_id": target, "reviewer": "logic_reviewer", "reason": reason}
    ]
    assert packet["role_instruction"].endswith("revision_agent.md")

    findings_path = run / "findings" / "pipeline_hygiene_findings.json"
    original = next(
        f for f in json.loads(findings_path.read_text())["findings"] if f["id"] == target
    )
    assert original["review_status"] == "revised"
    revision = dict(original, severity="low", revision_note="Lowered to low per logic review.")
    revision.pop("review_status")
    revisions_dir = run / "harness" / "agent_outputs" / "revisions"
    (revisions_dir / "pipeline_hygiene.json").write_text(
        json.dumps({"module": "pipeline_hygiene", "findings": [revision]}), encoding="utf-8"
    )

    result = advance(run)
    assert result["ready_tasks"] == ["rereview_logic_reviewer"]
    packet = json.loads((run / "harness" / "tasks" / "rereview_logic_reviewer.json").read_text())
    assert [item["finding_id"] for item in packet["revision_requests"]] == [target]
    allowed = "\n".join(packet["allowed_inputs"])
    assert "reviews/logic_reviewer.json" in allowed
    assert "reviews/data_fidelity_reviewer.json" not in allowed

    rereview = run / "harness" / "agent_outputs" / "rereviews" / "logic_reviewer.json"
    rereview.write_text(
        json.dumps([{"finding_id": target, "reviewer": "logic_reviewer", "verdict": "revise",
                     "reason": "Still not right.", "revision_round": 1}]),
        encoding="utf-8",
    )
    assert any("1 revision round" in p for p in validate_stage_output(run, "rereview_logic_reviewer"))
    rereview.write_text(
        json.dumps([{"finding_id": target, "reviewer": "logic_reviewer", "verdict": "approve",
                     "reason": "Severity now matches the stage rule.", "revision_round": 1}]),
        encoding="utf-8",
    )

    result = advance(run)
    assert "rereviews_validation" in result["passed"]
    assert "consolidate" in result["passed"]
    log = json.loads((run / "review_log.json").read_text())
    rounds = {
        e["revision_round"]
        for e in log
        if e["reviewer"] == "logic_reviewer" and e["finding_id"] == target
    }
    assert rounds == {0, 1}
    consolidated = {f["id"]: f for f in json.loads((run / "findings.json").read_text())["findings"]}
    assert consolidated[target]["severity"] == "low"
    assert consolidated[target]["review_status"] == "revised"
    # The audit role's own file keeps the original wording.
    kept = {f["id"]: f for f in json.loads(findings_path.read_text())["findings"]}
    assert kept[target]["severity"] == original["severity"]

    # Resuming does not reopen the review, revision or re-review tasks.
    again = advance(run)
    assert not any(
        stage.startswith(("review_", "revise_", "rereview_")) for stage in again["ready_tasks"]
    )


def test_every_agent_stage_has_a_role_file():
    from harness.task_packets import REPO_ROOT
    from harness.workflow import STAGES

    for stage in STAGES:
        if stage.kind == "agent":
            assert (REPO_ROOT / stage.role_file).is_file(), stage.id


def test_harness_rejects_raw_inputs(tmp_path):
    with pytest.raises(ValueError, match="raw snapshot"):
        expand_input_patterns(tmp_path, ["raw/*.jsonl"])


def test_privacy_clearance_is_reopened_for_current_report_bytes(tmp_path):
    run = _copy_fixture(tmp_path)
    clearance_path = run / "safety_clearance.json"
    clearance = json.loads(clearance_path.read_text(encoding="utf-8"))
    for entry in clearance:
        entry["file_sha256"] = "0" * 64
    clearance_path.write_text(json.dumps(clearance, indent=2) + "\n", encoding="utf-8")
    _write_narrative(run)
    result = advance(run)
    assert "privacy_clearance" in result["ready_tasks"]
    assert validate_stage_output(run, "privacy_clearance")
    report = (run / "crm_trust_report.md").read_text(encoding="utf-8")
    assert "**Recent Original Source Capture Gap**" in report
    assert "r\ne\nc\ne\n" not in report
    assert (run / "crm_trust_report.html").exists()
    assert (run / "operator_appendix.md").exists()
    visual = (run / "crm_trust_report.html").read_text(encoding="utf-8")
    assert "--primary:#964900" in visual
    assert 'class="stack"' in visual
    assert "Funnel and Association Coverage" in visual
    assert "Smartify Marketing" in visual
    assert "Your Strategic B2B Marketing Partner" in visual
    assert "Marketing systems, made clearer." not in visual
    assert "Sharing the Report" in visual
    assert "Print → Save as PDF" in visual
    assert "https://smartifymarketing.com" in visual
    assert "https://github.com/AliceEinstein" in visual
    assert "for the CMO" not in visual
    appendix = (run / "operator_appendix.md").read_text(encoding="utf-8")
    assert "**Exact scope:**" in appendix
    assert "**Implementation:**" in appendix
    assert "**Success measure:**" in appendix


def test_provider_stub_is_not_a_v1_dependency():
    with pytest.raises(ProviderNotConfigured):
        unavailable_provider({"stage": "example"})


def test_narrative_renderer_does_not_rewrite_number_words():
    text = "No one approved the one-to-one matching rule."
    assert _narrative_plain(text) == text


def test_report_uses_business_name_typed_hubspot_assets_and_safe_record_links(tmp_path):
    run = _copy_fixture(tmp_path)
    profile_run(run)
    context = CrmContext.model_validate(
        yaml.safe_load((run / "crm_context.yaml").read_text(encoding="utf-8"))
    )
    for module, document in measure_all(run, context).items():
        write_json(run / "processed" / "measurements" / f"{module}.json", document)
    consolidate_evidence(run)
    write_json(
        run / "raw" / "account_info.json",
        {
            "status": "available",
            "portal_id": "123456",
            "business_name": "Northstar Systems",
            "business_name_source": "synthetic_fixture",
        },
    )
    _write_narrative(run)

    render_reports(run)

    report = (run / "crm_trust_report.html").read_text(encoding="utf-8")
    markdown = (run / "crm_trust_report.md").read_text(encoding="utf-8")
    record_csv = (run / "report_record_evidence.csv").read_text(encoding="utf-8")
    assert "Northstar Systems CRM Trust Audit" in report
    assert "# Northstar Systems CRM Trust Audit" in markdown
    assert 'class="hubspot-asset"' in report
    assert "HubSpot property:" in report
    assert "HubSpot pipeline:" in report
    assert 'class="hubspot-record"' in report
    assert "Company:" in report or "Deal:" in report
    assert "https://app.hubspot.com/contacts/123456/record/0-" in report
    assert 'target="_blank" rel="noopener noreferrer"' in report
    assert 'class="quality-grid"' in report
    assert "Priority 1" in report
    assert "Recommended accountable role" in report
    assert "How this score is calculated" in report
    assert "100 starting points − 52 deducted points = 48" in report
    # The final gate needs the score as "<total>/100"; the renderer states it
    # so the gate never depends on the narrative wording.
    assert "deducted points = 48/100" in markdown
    assert "8 key properties" in report
    assert "Priority 3" in report
    assert report.index("Priority 1 · Customers Without Closed Won Deal Trace") < report.index(
        "Priority 3 · Companies Without Domain"
    )
    assert "### Priority 1 — Decisions at immediate risk" in markdown
    assert "### Priority 2 — Structural trust gaps" in markdown
    assert "### Priority 3 — Maintenance and hygiene debt" in markdown
    assert "Treat this as a confidential CRM report" in report
    assert "complete sanitized output package" not in report
    assert "Eight companies" not in report
    assert "8 companies" in report
    assert "app.hubspot.com" not in record_csv
    assert "123456" not in record_csv
    assert ",co001," not in record_csv
    assert ",d001," not in record_csv


def _write_overrides(path: Path, source_field: str = "hs_analytics_source") -> Path:
    path.write_text(
        "canonical_fields:\n"
        "  lifecycle_stage: lifecyclestage\n"
        f"  original_source: {source_field}\n"
        "confirmed_by: RevOps owner\nconfirmed_on: 2026-10-06\n",
        encoding="utf-8",
    )
    return path


def test_confirmed_fields_reopen_schema_discovery_and_bind_crm_context(tmp_path):
    from harness.cli import main as harness_main
    from harness.state import RunState

    run = _copy_fixture(tmp_path)
    advance(run)
    assert RunState.load(run).stage("schema_discovery").status == "passed"
    # A run without the file keeps its hashes: nothing reopens on resume.
    assert not any(s.startswith("schema") for s in advance(run)["ready_tasks"])

    overrides = _write_overrides(tmp_path / "field_overrides.yaml", "lead_source")
    assert harness_main(["init", "--run", str(run), "--field-overrides", str(overrides)]) == 0
    assert (run / "config" / "field_overrides.yaml").exists()
    assert RunState.load(run).stage("schema_discovery").status == "ready"
    packet = json.loads((run / "harness" / "tasks" / "schema_discovery.json").read_text())
    assert any(path.endswith("config/field_overrides.yaml") for path in packet["allowed_inputs"])

    # The old crm_context.yaml moved to stale; restoring it unchanged fails
    # because the owner confirmed a different source field.
    stale_root = run / "harness" / "stale"
    for name in ("crm_context.yaml", "schema_discovery_report.md"):
        shutil.copyfile(next(stale_root.rglob(name)), run / name)
    problems = validate_stage_output(run, "schema_discovery")
    assert any("owner confirmed contact.lead_source" in p for p in problems)

    context = yaml.safe_load((run / "crm_context.yaml").read_text())
    context["canonical_fields"]["original_source"].update(
        field="lead_source", confidence="high", requires_confirmation=False,
        evidence="Confirmed by RevOps owner in config/field_overrides.yaml",
    )
    context["canonical_fields"]["lifecycle_stage"].update(confidence="high", requires_confirmation=False)
    (run / "crm_context.yaml").write_text(yaml.safe_dump(context), encoding="utf-8")
    assert validate_stage_output(run, "schema_discovery") == []


def test_field_overrides_must_name_snapshot_properties(tmp_path):
    from harness.cli import main as harness_main

    run = _copy_fixture(tmp_path)
    overrides = _write_overrides(tmp_path / "field_overrides.yaml", "invented_source")
    assert harness_main(["init", "--run", str(run), "--field-overrides", str(overrides)]) == 1
    assert not (run / "config" / "field_overrides.yaml").exists()
