"""A --days window must not turn out-of-snapshot lookups into defects."""
from __future__ import annotations

import json
from pathlib import Path

from core.lifecycle_rules import measure_lifecycle_integrity
from core.sanitizer import hash_record_id, load_or_create_salt


def _build_run(tmp_path: Path, *, full_history: bool) -> Path:
    run = tmp_path / ("full" if full_history else "windowed")
    raw = run / "raw"
    processed = run / "processed"
    raw.mkdir(parents=True)
    processed.mkdir(parents=True)
    (run / "manifest.json").write_text(
        json.dumps(
            {"status": "completed", "full_history": full_history}
            | ({} if full_history else {"days": 90})
        ),
        encoding="utf-8",
    )
    # One expansion deal linked to a company that is NOT in the snapshot
    # (created before the window / archived).
    (raw / "deals.jsonl").write_text(
        json.dumps(
            {
                "id": "d1",
                "properties": {
                    "pipeline": "default",
                    "dealstage": "open",
                    "hubspot_owner_id": "901",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (raw / "contacts.jsonl").write_text("", encoding="utf-8")
    (raw / "companies.jsonl").write_text("", encoding="utf-8")
    (raw / "associations_deal_company.jsonl").write_text(
        json.dumps({"from_id": "d1", "to_ids": ["old-company"]}) + "\n",
        encoding="utf-8",
    )
    (raw / "pipelines.json").write_text("[]", encoding="utf-8")
    salt = load_or_create_salt(run)
    (processed / "journey_evidence_store.json").write_text("{}", encoding="utf-8")
    (processed / "journey_record_assignments.json").write_text(
        json.dumps(
            [
                {
                    "record_id_hash": hash_record_id("deals", "d1", salt),
                    "assigned_journey": "expansion_renewal",
                }
            ]
        ),
        encoding="utf-8",
    )
    return run


def _expansion_measurement(run: Path) -> dict:
    doc = measure_lifecycle_integrity(run)
    return next(
        row
        for row in doc["measurements"]
        if row["id"] == "expansion_deals_without_customer_company"
    )


def test_windowed_run_excludes_out_of_snapshot_companies(tmp_path):
    row = _expansion_measurement(_build_run(tmp_path, full_history=False))
    assert row["affected_records"] == 0
    assert "created before the snapshot window" in row["note"]


def test_full_history_run_counts_missing_company_as_state_gap(tmp_path):
    row = _expansion_measurement(_build_run(tmp_path, full_history=True))
    assert row["affected_records"] == 1
    assert row["note"] == ""
