"""Stage-entry timestamp capture and deterministic transition analysis."""
from __future__ import annotations

import json
from pathlib import Path

from connectors.hubspot.fetch_properties import select_stage_timestamp_candidates
from core.lifecycle_rules import measure_lifecycle_integrity
from core.stage_transitions import (
    analyze_contact_stages,
    build_stage_transition_summary,
    stage_entries,
)

DAY_MS = 86_400_000


def _contact(record_id: str, stage: str, entered: dict[str, int]) -> dict:
    props = {"lifecyclestage": stage}
    for name, day in entered.items():
        props[f"hs_v2_date_entered_{name}"] = str(day * DAY_MS)
    return {"id": record_id, "properties": props}


def test_stage_timestamp_candidates_come_from_real_definitions_and_prefer_v2():
    definitions = [
        {"name": "hs_v2_date_entered_customer", "hubspotDefined": True},
        {"name": "hs_date_entered_customer", "hubspotDefined": True},
        {"name": "hs_date_entered_appointmentscheduled", "hubspotDefined": True},
        {"name": "hs_v2_date_entered_qualifiedtobuy", "hubspotDefined": True},
        {"name": "dealname", "hubspotDefined": True},
        {"name": "custom_source", "hubspotDefined": False},
    ]
    names = select_stage_timestamp_candidates(definitions)
    assert names == [
        "hs_date_entered_appointmentscheduled",
        "hs_v2_date_entered_customer",
        "hs_v2_date_entered_qualifiedtobuy",
    ]


def test_stage_entries_prefer_v2_and_sort_by_time():
    record = {
        "id": "c1",
        "properties": {
            "hs_date_entered_lead": str(99 * DAY_MS),  # stale v1 value
            "hs_v2_date_entered_lead": str(1 * DAY_MS),
            "hs_v2_date_entered_customer": str(30 * DAY_MS),
        },
    }
    assert stage_entries(record) == [
        ("lead", float(1 * DAY_MS)),
        ("customer", float(30 * DAY_MS)),
    ]


def test_contact_analysis_separates_paths_direct_sets_and_regressions():
    contacts = [
        # Ordered funnel path through MQL, ends customer.
        _contact(
            "c1",
            "customer",
            {"lead": 1, "marketingqualifiedlead": 5, "salesqualifiedlead": 9, "customer": 20},
        ),
        # Direct-set customer: no pre-customer stage timestamp.
        _contact("c2", "customer", {"customer": 3}),
        # Regression: re-entered lead after becoming customer.
        _contact("c3", "lead", {"customer": 10, "lead": 40}),
        # No timestamps at all.
        {"id": "c4", "properties": {"lifecyclestage": "lead"}},
    ]
    summary = analyze_contact_stages(contacts)
    assert summary["with_stage_timestamps"] == 3
    assert summary["ordered_progressions"] == 1
    assert summary["mql_progressions"] == 1
    assert summary["stage_regression_ids"] == ["c3"]
    assert summary["customers_total"] == 2
    assert summary["customers_without_timestamped_path_ids"] == ["c2"]


def test_summary_reports_unavailable_without_timestamps():
    doc = build_stage_transition_summary(
        [{"id": "c1", "properties": {"lifecyclestage": "lead"}}], [], []
    )
    assert doc["available"] is False
    assert "creation order" in doc["limitation"]


def _minimal_run(tmp_path: Path, contacts: list[dict]) -> Path:
    run = tmp_path / "run"
    (run / "raw").mkdir(parents=True)
    (run / "processed").mkdir()
    (run / "manifest.json").write_text(
        json.dumps({"status": "completed", "full_history": True}), encoding="utf-8"
    )
    (run / "raw" / "contacts.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in contacts), encoding="utf-8"
    )
    (run / "raw" / "deals.jsonl").write_text("", encoding="utf-8")
    (run / "raw" / "companies.jsonl").write_text("", encoding="utf-8")
    (run / "raw" / "pipelines.json").write_text("[]", encoding="utf-8")
    (run / "processed" / "journey_evidence_store.json").write_text("{}", encoding="utf-8")
    (run / "processed" / "journey_record_assignments.json").write_text("[]", encoding="utf-8")
    return run


def _measurement(doc: dict, measurement_id: str) -> dict:
    return next(row for row in doc["measurements"] if row["id"] == measurement_id)


def test_lifecycle_measurements_expose_stage_history_facts(tmp_path):
    run = _minimal_run(
        tmp_path,
        [
            _contact("c1", "customer", {"lead": 1, "marketingqualifiedlead": 5, "customer": 20}),
            _contact("c2", "customer", {"customer": 3}),
            _contact("c3", "lead", {"customer": 10, "lead": 40}),
        ],
    )
    doc = measure_lifecycle_integrity(run)
    direct_set = _measurement(doc, "customers_without_stage_history")
    assert direct_set["available"] is True
    assert direct_set["denominator"] == 2
    assert direct_set["affected_records"] == 1
    regression = _measurement(doc, "contacts_stage_regression")
    assert regression["affected_records"] == 1


def test_lifecycle_measurements_degrade_without_stage_timestamps(tmp_path):
    run = _minimal_run(
        tmp_path, [{"id": "c1", "properties": {"lifecyclestage": "customer"}}]
    )
    doc = measure_lifecycle_integrity(run)
    direct_set = _measurement(doc, "customers_without_stage_history")
    assert direct_set["available"] is False
    assert "re-run the acquisition pass" in direct_set["note"].lower()
