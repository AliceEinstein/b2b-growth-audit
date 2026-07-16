from __future__ import annotations

import csv
import json

from lifecycle_test_support import build_lifecycle_run, measurement


def test_broken_associations_use_exact_denominators(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    company_gap = measurement(run_dir, "deals_without_company")
    contact_gap = measurement(run_dir, "deals_without_contact")
    assert company_gap["denominator"] == 3
    assert company_gap["affected_records"] == 2
    assert company_gap["affected_percentage"] == 66.7
    assert contact_gap["affected_records"] == 2


def test_legacy_lifecycle_fields_are_flagged_for_confirmation(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "legacy_property_sprawl_sample")
    gap = measurement(run_dir, "lifecycle_field_fragmentation")
    assert gap["affected_records"] >= 1
    assert "canonical-field confirmation" in gap["note"]


def test_missing_activity_data_skips_metric_instead_of_inventing_it(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "abm_sample")
    metric = measurement(run_dir, "activity_handoff_evidence_available")
    assert metric["available"] is False
    assert metric["denominator"] is None


def test_pipeline_exposure_uses_existing_deals_and_no_deal_contacts_have_no_amount(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "pipeline_leakage_sample")
    doc = json.loads(
        (run_dir / "processed" / "lifecycle_integrity_measurements.json").read_text(
            encoding="utf-8"
        )
    )
    exposure = doc["pipeline_exposure"]
    assert exposure["unique_open_deals_with_leakage_signals"] == 2
    assert exposure["actual_open_deal_amount_by_currency"] == {
        "portal_default": "65000.00"
    }
    assert exposure["potential_recoverable_pipeline_population"] == 3
    assert exposure["potential_population_amount"] is None

    with (run_dir / "evidence.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    deal_rows = [row for row in rows if row["object_type"] == "deals"]
    contact_rows = [row for row in rows if row["object_type"] == "contacts"]
    assert all(row["record_id_hash"] and row["pipeline_label"] for row in deal_rows)
    assert all(row["amount_included_in_aggregate"] == "" for row in contact_rows)
