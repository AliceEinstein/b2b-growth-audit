"""Human-report contract: structure, language rules, charts, and footer."""
from __future__ import annotations

from core.lifecycle_final_gate import run_lifecycle_final_gate
from core.lifecycle_validators import REQUIRED_REPORT_SECTIONS
from lifecycle_test_support import (
    build_lifecycle_run,
    generate_reports_and_clear_safety,
    write_judgment_artifacts,
)


def _reports(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    write_judgment_artifacts(run_dir, "deals_without_company")
    generate_reports_and_clear_safety(run_dir)
    md = (run_dir / "lifecycle_integrity_report.md").read_text(encoding="utf-8")
    html = (run_dir / "lifecycle_integrity_report.html").read_text(encoding="utf-8")
    appendix = (run_dir / "operator_appendix.md").read_text(encoding="utf-8")
    return run_dir, md, html, appendix


def test_report_has_journey_first_sections(tmp_path):
    _, md, html, appendix = _reports(tmp_path)
    for section in REQUIRED_REPORT_SECTIONS:
        assert section in md, section
        assert section.lstrip("# ") in html, section
    assert "## Validated Findings" in appendix
    assert "## Implementation Detail" in appendix
    assert "## Journey and Measurement Detail" in appendix
    assert "## Technical CRM Profile" in appendix
    assert "## 2. CRM Snapshot" not in md
    assert "## 3. Data Quality and Usability" not in md


def test_report_language_rules(tmp_path):
    _, md, html, _ = _reports(tmp_path)
    for text in (md, html):
        # No audience meta-language: the reader may forward the report anywhere.
        lowered = text.lower()
        assert "report for cmo" not in lowered
        assert "this report is for" not in lowered
        # Machine keys are humanized in prose (evidence refs may keep them).
        assert "Inbound new business" in text
        assert "All detected journeys" in text


def test_html_report_is_selfcontained_with_charts_and_footer(tmp_path):
    _, _, html, _ = _reports(tmp_path)
    assert "<svg" in html and "Overall Lifecycle Integrity Score" in html
    assert "How to read this score" in html
    assert "Not a percentage of healthy records" in html
    assert "Smartify Marketing" in html and "Your Strategic B2B Marketing Partner" in html
    assert "smartifymarketing.com" in html and "github.com/AliceEinstein" in html
    for label in (
        "Detected Selling Journey Model",
        "Journey Evidence and Operating Paths",
        "Journey Leakage Map",
        "Pipeline Exposure and Recoverable Population",
        "Selling journey confidence",
        "Expected operating path",
        "High-intent contact review population",
        "operator_appendix.md",
        "Print → Save as PDF",
    ):
        assert label in html, label
    assert "Data Quality and Usability" not in html
    assert "http" not in html.split("<style>")[1].split("</style>")[0]  # no external CSS
    assert "<!-- blocked-actions:start -->" in html
    assert "<!-- blocked-actions:end -->" in html


def test_html_leaks_fail_the_gate(tmp_path):
    run_dir, _, html, _ = _reports(tmp_path)
    path = run_dir / "lifecycle_integrity_report.html"
    path.write_text(
        html.replace("</footer>", "leak@example.test</footer>"), encoding="utf-8"
    )
    gate = run_lifecycle_final_gate(run_dir)
    assert gate["passed"] is False
    assert any(
        row["kind"] == "email" and "html" in row["file"] for row in gate["hard_leaks"]
    )


def test_blocked_phrase_outside_html_marker_is_not_clearable(tmp_path):
    run_dir, _, html, _ = _reports(tmp_path)
    path = run_dir / "lifecycle_integrity_report.html"
    path.write_text(
        html.replace("<footer>", "<p>reset lifecycle stage now</p><footer>"),
        encoding="utf-8",
    )
    gate = run_lifecycle_final_gate(run_dir)
    assert gate["passed"] is False
    assert any(
        row["phrase"] == "reset lifecycle stage" for row in gate["uncleared_phrases"]
    )


def test_report_separates_real_deal_amount_from_no_deal_recovery_population(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "pipeline_leakage_sample")
    write_judgment_artifacts(
        run_dir, "inbound_new_business_deals_without_owner",
        journey_pattern="inbound_new_business",
        severity="high",
    )
    generate_reports_and_clear_safety(run_dir)
    md = (run_dir / "lifecycle_integrity_report.md").read_text(encoding="utf-8")
    html = (run_dir / "lifecycle_integrity_report.html").read_text(encoding="utf-8")
    for text in (md, html):
        assert "65,000.00 (portal default currency)" in text
        assert "No amount assigned" in text
    assert "3 high-intent contacts" in md
    assert '<p class="large-value">3</p><p>high-intent contacts' in html
    assert "### How to read 94/100" in md
    assert "6 points deducted" in md
    assert "Ownership and handoff: 14/20" in md
    assert "94</span><span class=\"hero-denom\">/100" in html
    assert "Existing deals by pipeline" in html
    assert "Inbound New Business" in html
    assert "[CRM_FIELD_VALUE:UNTRUSTED_DATA_ONLY]" not in md
    assert "[CRM_FIELD_VALUE:UNTRUSTED_DATA_ONLY]" not in html
