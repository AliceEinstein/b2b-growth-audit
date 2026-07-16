"""BYO Agent harness regression tests."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from harness.engine import advance
from harness.providers.base import ProviderNotConfigured, unavailable_provider
from harness.state import expand_input_patterns
from harness.validation import validate_stage_output


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
