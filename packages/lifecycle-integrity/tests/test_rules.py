"""Measurement layer tests: exact facts, evidence, graceful gaps."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from core.profiler import profile_run
from core.metrics import stage_flags
from core.rules import measure_all
from core.schemas import CrmContext

CONTEXT = {
    "audit_focus": "marketing_to_pipeline_trust",
    "crm_complexity": {"tier": "lean_smb", "confidence": "medium"},
    "canonical_fields": {
        "lifecycle_stage": {
            "object": "contact",
            "field": "lifecyclestage",
            "confidence": "high",
            "requires_confirmation": False,
            "evidence": "standard field",
        },
        "original_source": {
            "object": "contact",
            "field": "hs_analytics_source",
            "confidence": "high",
            "requires_confirmation": False,
            "evidence": "standard field",
        },
    },
}


@pytest.fixture
def context() -> CrmContext:
    return CrmContext.model_validate(CONTEXT)


def add_deal_contact_associations(run: Path) -> None:
    rows = [
        {"from_id": "d1", "to_ids": ["c1"]},
        {"from_id": "d3", "to_ids": ["c8"]},  # c8 has empty source
    ]
    (run / "raw" / "associations_deal_contact.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )


def by_id(result, module):
    return {m["id"]: m for m in result[module]["measurements"]}


def test_attribution_measurements(synthetic_run, context):
    profile_run(synthetic_run)
    add_deal_contact_associations(synthetic_run)
    result = measure_all(synthetic_run, context)
    ms = by_id(result, "attribution_trust")

    missing = ms["contacts_missing_original_source"]
    assert (missing["denominator"], missing["affected_records"]) == (10, 3)
    assert missing["affected_percentage"] == 30.0

    recent = ms["recent_half_contacts_missing_original_source"]
    assert (recent["denominator"], recent["affected_records"]) == (5, 3)
    assert recent["affected_percentage"] == 60.0

    # won deals: d3 (traced to c8, empty source) and d4 (no contacts)
    trace = ms["closedwon_deals_without_source_trace"]
    assert (trace["denominator"], trace["affected_records"]) == (2, 2)
    assert trace["affected_percentage"] == 100.0


def test_association_gap_degrades_not_invents(synthetic_run, context):
    profile_run(synthetic_run)  # deal->contact association file absent
    result = measure_all(synthetic_run, context)
    trace = by_id(result, "attribution_trust")["closedwon_deals_without_source_trace"]
    assert trace["available"] is False
    assert trace["affected_records"] is None
    assert "unavailable" in trace["note"]


def test_windowed_relationship_measurements_are_unavailable(synthetic_run, context):
    profile_run(synthetic_run)
    add_deal_contact_associations(synthetic_run)
    manifest_path = synthetic_run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({"days": 90, "full_history": False})
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = measure_all(synthetic_run, context)
    attribution = by_id(result, "attribution_trust")
    lifecycle = by_id(result, "lifecycle_funnel")
    assert attribution["closedwon_deals_without_source_trace"]["available"] is False
    assert lifecycle["customers_without_closedwon_deal"]["available"] is False
    assert "90-day window" in attribution["closedwon_deals_without_source_trace"]["note"]


def test_stage_semantics_are_scoped_to_pipeline():
    flags = stage_flags(
        [
            {
                "id": "sales",
                "stages": [
                    {
                        "id": "closed",
                        "metadata": {"isClosed": "true", "probability": "1.0"},
                    }
                ],
            },
            {
                "id": "services",
                "stages": [
                    {
                        "id": "closed",
                        "metadata": {"isClosed": "false", "probability": "0.0"},
                    }
                ],
            },
        ]
    )
    assert flags[("sales", "closed")] == {"closed": True, "won": True}
    assert flags[("services", "closed")] == {"closed": False, "won": False}

    metadata_override = stage_flags(
        [{"id": "sales", "stages": [{
            "id": "closedwon",
            "metadata": {"isClosed": "true", "probability": "0"},
        }]}]
    )
    assert metadata_override[("sales", "closedwon")]["won"] is False


def test_lifecycle_measurements(synthetic_run, context):
    profile_run(synthetic_run)
    add_deal_contact_associations(synthetic_run)
    result = measure_all(synthetic_run, context)
    ms = by_id(result, "lifecycle_funnel")

    assert ms["contacts_missing_lifecycle"]["affected_records"] == 1
    # customers: c8 (has won deal d3), c9 (no deal) -> 1 of 2
    cust = ms["customers_without_closedwon_deal"]
    assert (cust["denominator"], cust["affected_records"]) == (2, 1)
    assert cust["affected_percentage"] == 50.0
    # MQLs c6, c7 have no deals at all
    mql = ms["mql_plus_contacts_without_deal"]
    assert (mql["denominator"], mql["affected_records"]) == (2, 2)


def test_association_measurements(synthetic_run, context):
    profile_run(synthetic_run)
    add_deal_contact_associations(synthetic_run)
    result = measure_all(synthetic_run, context)
    ms = by_id(result, "association_architecture")

    assert ms["contacts_without_company"]["affected_records"] == 6
    assert ms["deals_without_company"]["affected_records"] == 2
    assert ms["deals_without_contact"]["affected_records"] == 3
    dupes = ms["duplicate_company_domain_candidates"]
    assert (dupes["denominator"], dupes["affected_records"]) == (3, 2)
    assert ms["companies_without_domain"]["affected_records"] == 1


def test_pipeline_hygiene_measurements(synthetic_run, context):
    profile_run(synthetic_run)
    result = measure_all(synthetic_run, context)
    ms = by_id(result, "pipeline_hygiene")

    # open deals: d1, d2, d5; only d2 has a (past) closedate
    past_due = ms["open_deals_past_close_date"]
    assert (past_due["denominator"], past_due["affected_records"]) == (3, 1)
    assert ms["deals_without_amount"]["affected_records"] == 2
    assert ms["deals_in_unknown_pipeline"]["affected_records"] == 1
    assert ms["deals_stuck_in_stage"]["available"] is False


def test_property_governance_measurements(synthetic_run, context):
    profile_run(synthetic_run)
    result = measure_all(synthetic_run, context)
    ms = by_id(result, "property_governance")

    decayed = ms["decayed_source_fields"]
    # old_lead_source_2021 (100 -> 0) and utm_notes (20 -> 0)
    assert (decayed["denominator"], decayed["affected_records"]) == (3, 2)
    assert ms["similar_name_field_groups"]["affected_records"] == 0


def test_evidence_uses_hashed_ids_and_prd_columns(synthetic_run, context):
    profile_run(synthetic_run)
    add_deal_contact_associations(synthetic_run)
    measure_all(synthetic_run, context)

    path = synthetic_run / "evidence" / "attribution_trust.csv"
    with path.open() as fh:
        rows = list(csv.DictReader(fh))
    assert rows, "expected evidence rows"
    assert set(rows[0].keys()) == {
        "finding_id", "object_type", "record_id_hash", "field_name",
        "issue_type", "current_value_redacted", "confidence",
        "recommended_review",
    }
    raw_ids = {f"c{i}" for i in range(1, 11)} | {f"d{i}" for i in range(1, 6)}
    for row in rows:
        assert row["record_id_hash"] not in raw_ids
