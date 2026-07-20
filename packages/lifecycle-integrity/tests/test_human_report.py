"""Human-report contract: structure, language rules, charts, and footer."""
from __future__ import annotations

import csv
import json

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


def _complex_reports(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "complex_lifecycle_demo")
    write_judgment_artifacts(
        run_dir,
        measurement_ids=[
            "active_deal_intent_without_escalation",
            "closed_lost_recovery_opportunity",
            "deals_without_company",
            "inbound_new_business_high_intent_contacts_without_deal",
        ],
        severity="high",
    )
    generate_reports_and_clear_safety(run_dir)
    md = (run_dir / "lifecycle_integrity_report.md").read_text(encoding="utf-8")
    html = (run_dir / "lifecycle_integrity_report.html").read_text(encoding="utf-8")
    return run_dir, md, html


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
        assert "all_detected_journeys" not in text


def test_html_report_is_selfcontained_with_charts_and_footer(tmp_path):
    _, _, html, _ = _reports(tmp_path)
    assert "score-hero" in html and "Lifecycle Integrity Score" in html
    assert "How the score is calculated" in html
    assert "100 baseline" in html
    assert "total deductions" in html
    assert "CRM hygiene" in html
    assert "actual deal amount under review" in html
    assert "Smartify Marketing" in html and "Your Strategic B2B Marketing Partner" in html
    assert "smartifymarketing.com" in html and "github.com/AliceEinstein" in html
    for label in (
        "How Smartify Sells",
        "Where the Journey Breaks by Account, Contact, and Deal",
        "Action Queue",
        "Buyer signal",
        "operator_appendix.md",
        "report_record_evidence.csv",
        "report_account_evidence.csv",
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
        assert "USD 40,000.00" in text
        assert "No amount assigned" in text
        assert "Inbound One" in text
        assert "portal default currency" not in text
    assert "Lifecycle Integrity Score:" in md and "/100 —" in md
    assert "100 baseline" in md
    assert "total deductions" in md
    assert "half weight" not in md
    assert "Evidence confidence by motion" not in md
    assert "<span class='hero-number'>" in html
    assert "Inbound New Business" in html
    assert "report_record_evidence.csv" in html
    assert "report_account_evidence.csv" in html
    assert "[CRM_FIELD_VALUE:UNTRUSTED_DATA_ONLY]" not in md
    assert "[CRM_FIELD_VALUE:UNTRUSTED_DATA_ONLY]" not in html


def test_report_orders_every_commercial_lane_from_upstream_to_downstream(tmp_path):
    _, md, html = _complex_reports(tmp_path)
    for text in (md, html):
        demand = text.index("Demand reached sales readiness but was not assigned")
        open_pipeline = text.index("Open deals are missing account continuity")
        closed_lost = text.index("Buyer intent returned after closed-lost")
        assert demand < open_pipeline < closed_lost
        demand_action = text.index("Priya Shah")
        open_action = text.index("Inbound — Enterprise Evaluation")
        lost_action = text.index("Renewal — Closed Lost")
        assert demand_action < open_action < lost_action


def test_report_uses_record_level_reasoning_instead_of_control_templates(tmp_path):
    run_dir, md, html = _complex_reports(tmp_path)
    for text in (md, html):
        assert "Missing control" not in text
        assert "intent-escalation workflow" not in text
        assert "unresolved deterministic risk population" not in text
        assert "half weight" not in text
        assert "||" not in text
        for expected in (
            "Priya Shah",
            "Camille Dubois",
            "Inbound — Enterprise Evaluation",
            "ABM — Unlinked Target Deal",
            "Renewal — Closed Lost",
            "Evidence pattern",
            "Account-level reading",
            "Root-cause evidence",
            "Representative cases",
            "08 Jul 2026",
            "visible response gap is",
            "USD 32,000.00",
            "19 days later",
        ):
            assert expected in text, expected
        assert "does not appear applicable" in text
        assert "no visible automated handoff from engagement score to seller action" in text
        assert "outside the score" in text
    assert "problem-group" in html
    assert "report_account_evidence.csv" in html

    with (run_dir / "report_record_evidence.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert [row["lane"] for row in rows] == [
        "pre_deal",
        "pre_deal",
        "active_deal",
        "active_deal",
        "active_deal",
        "post_loss",
    ]
    assert {row["contact_name"] for row in rows} >= {"Priya Shah", "Camille Dubois", "Ethan Brooks"}
    csv_text = (run_dir / "report_record_evidence.csv").read_text(encoding="utf-8")
    assert "@" not in csv_text
    assert "phone" not in csv_text.lower()


def test_closed_lost_recovery_is_proved_but_not_scored_as_pipeline_loss(tmp_path):
    run_dir, md, _ = _complex_reports(tmp_path)
    assert "closed lost on 20 May 2026" in md
    assert "HubSpot form: renewal review" in md
    assert "No open successor deal" in md
    assert "no post-loss sales call, email, task, or meeting" in md
    assert "Historical context only" in md
    assert "outside the score and open pipeline" in md
    assert "Buyer intent returned after closed-lost without a successor path" in md
    score = json.loads((run_dir / "lifecycle_score.json").read_text(encoding="utf-8"))
    post_close = score["journey_link_scores"]["post_close_recovery"]
    assert post_close["deducted"] == 0
    assert post_close["status"] == "recovery opportunity shown outside score"


def test_hubspot_assets_are_labeled_and_records_link_back_to_hubspot(tmp_path):
    run_dir, md, html = _complex_reports(tmp_path)
    assert "<strong class='hubspot-asset'>Workflow: Assign inbound owner (WF-001)</strong>" in html
    assert "**Workflow: Assign inbound owner (WF-001)**" in md
    assert "<strong class='hubspot-asset'>HubSpot property: Contact owner</strong>" in html
    assert "**HubSpot property: Contact owner**" in md
    assert "Pipeline: Inbound New Business" in html
    assert "https://app.hubspot.com/contacts/123456/record/0-3/d1" in html
    assert "https://app.hubspot.com/contacts/123456/record/0-2/co1" in html
    assert "class='hubspot-record'" in html
    csv_text = (run_dir / "report_record_evidence.csv").read_text(encoding="utf-8")
    assert "app.hubspot.com" not in csv_text
    assert "123456" not in csv_text


def test_hubspot_record_links_are_omitted_without_portal_id(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "complex_lifecycle_demo")
    account_info_path = run_dir / "raw" / "account_info.json"
    account_info = json.loads(account_info_path.read_text(encoding="utf-8"))
    account_info.pop("portal_id", None)
    account_info_path.write_text(json.dumps(account_info), encoding="utf-8")
    write_judgment_artifacts(
        run_dir,
        measurement_ids=["deals_without_company"],
        severity="high",
    )
    generate_reports_and_clear_safety(run_dir)
    html = (run_dir / "lifecycle_integrity_report.html").read_text(encoding="utf-8")
    assert "app.hubspot.com/contacts/" not in html
    assert "ABM — Unlinked Target Deal" in html
