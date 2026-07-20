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
from harness.render import render_reports
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


def test_harness_rejects_raw_inputs(tmp_path):
    with pytest.raises(ValueError, match="raw snapshot"):
        expand_input_patterns(tmp_path, ["raw/*.jsonl"])


def test_privacy_clearance_is_reopened_for_current_report_bytes(tmp_path):
    run = _copy_fixture(tmp_path)
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
    assert "HubSpot Company:" in report or "HubSpot Deal:" in report
    assert "https://app.hubspot.com/contacts/123456/record/0-" in report
    assert 'target="_blank" rel="noopener noreferrer"' in report
    assert "app.hubspot.com" not in record_csv
    assert "123456" not in record_csv
    assert ",co001," not in record_csv
    assert ",d001," not in record_csv
