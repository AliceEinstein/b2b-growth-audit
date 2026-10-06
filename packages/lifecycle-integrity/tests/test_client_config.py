from __future__ import annotations

import json

import pytest

from core.client_config import (
    ClientConfigError,
    install_client_config,
    load_journey_mapping,
    parse_field_overrides,
    parse_journey_mapping,
    resolve_canonical_fields,
)

PROP_DEFS = {
    "contacts": [{"name": "lifecyclestage"}, {"name": "hs_analytics_source"}, {"name": "ns_lifecycle_stage"}, {"name": "ns_original_source"}],
    "companies": [{"name": "lifecyclestage"}],
}


def _candidates(custom_fill: float = 90.0):
    lifecycle_values = [{"value": v, "count": 10} for v in ("customer", "marketingqualifiedlead", "lead")]
    source_values = [{"value": v, "count": 10} for v in ("email_marketing", "paid_search", "event")]
    return {
        "lifecycle": [
            {"object_type": "contacts", "field": "lifecyclestage", "hubspot_defined": True, "fill_rate": 100.0, "top_values": lifecycle_values},
            {"object_type": "contacts", "field": "ns_lifecycle_stage", "hubspot_defined": False, "fill_rate": custom_fill, "top_values": lifecycle_values},
        ],
        "source": [
            {"object_type": "contacts", "field": "ns_original_source", "hubspot_defined": False, "fill_rate": custom_fill, "top_values": source_values},
        ],
    }


def test_competing_custom_fields_lower_confidence_and_add_notes(tmp_path):
    canonical, notes = resolve_canonical_fields(tmp_path, PROP_DEFS, _candidates())
    assert canonical["lifecycle_stage"]["field"] == "lifecyclestage"
    assert canonical["lifecycle_stage"]["confidence"] == "medium"
    assert canonical["lifecycle_stage"]["requires_confirmation"] is True
    assert canonical["lifecycle_stage"]["competing_fields"] == ["ns_lifecycle_stage"]
    assert canonical["original_source"]["competing_fields"] == ["ns_original_source"]
    assert canonical["company_lifecycle_stage"]["confidence"] == "high"
    assert any("ns_lifecycle_stage" in note for note in notes)


def test_sparse_custom_field_does_not_compete(tmp_path):
    canonical, notes = resolve_canonical_fields(tmp_path, PROP_DEFS, _candidates(custom_fill=20.0))
    assert canonical["lifecycle_stage"]["confidence"] == "high"
    assert notes == []


def test_owner_override_wins_and_is_recorded(tmp_path):
    source = tmp_path / "field_overrides.yaml"
    source.write_text(
        "canonical_fields:\n  lifecycle_stage: ns_lifecycle_stage\n  original_source: ns_original_source\n"
        "confirmed_by: RevOps owner\nconfirmed_on: 2026-10-06\n",
        encoding="utf-8",
    )
    run = tmp_path / "run"
    run.mkdir()
    (run / "manifest.json").write_text("{}", encoding="utf-8")
    installed = install_client_config(run, field_overrides=source)
    assert installed["field_overrides.yaml"]["confirmed_by"] == "RevOps owner"
    assert json.loads((run / "manifest.json").read_text())["client_config"]["field_overrides.yaml"]["sha256"]
    canonical, notes = resolve_canonical_fields(run, PROP_DEFS, _candidates())
    assert canonical["lifecycle_stage"]["field"] == "ns_lifecycle_stage"
    assert canonical["lifecycle_stage"]["confidence"] == "high"
    assert canonical["original_source"]["field"] == "ns_original_source"
    assert any("Stage-entry timestamps" in note for note in notes)


def test_override_naming_a_missing_property_fails(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "field_overrides.yaml").write_text(
        "canonical_fields:\n  lifecycle_stage: not_a_property\n", encoding="utf-8"
    )
    with pytest.raises(ClientConfigError, match="not a contact property"):
        resolve_canonical_fields(tmp_path, PROP_DEFS, _candidates())


def test_config_files_are_validated():
    with pytest.raises(ClientConfigError, match="unknown canonical field"):
        parse_field_overrides({"canonical_fields": {"deal_stage": "dealstage"}})
    with pytest.raises(ClientConfigError, match="is not a journey"):
        parse_journey_mapping({"values": {"trade_show": "events"}})
    mapping = parse_journey_mapping({"values": {"Trade-Show": "inbound_new_business"}})
    assert mapping.lookup("any_field", "trade_show") == "inbound_new_business"


def test_missing_mapping_file_is_empty(tmp_path):
    assert not load_journey_mapping(tmp_path)


def test_measurements_read_the_confirmed_source_field(tmp_path):
    from core.client_config import CONFIG_DIR, FIELD_OVERRIDES_FILE
    from core.intent_evidence import build_intent_evidence
    from core.journey_evidence import build_journey_evidence_store
    from core.lifecycle_rules import measure_lifecycle_integrity
    from core.lifecycle_synthetic_datasets import LIFECYCLE_DATASETS
    from core.profiler import profile_run

    def source_trace(run_dir):
        profile_run(run_dir)
        build_intent_evidence(run_dir)
        build_journey_evidence_store(run_dir)
        doc = measure_lifecycle_integrity(run_dir)
        rows = doc["measurements"] if isinstance(doc, dict) else doc
        if not isinstance(rows, list):
            rows = json.loads((run_dir / "processed" / "lifecycle_integrity_measurements.json").read_text())["measurements"]
        return next(row for row in rows if row["id"] == "inbound_deals_without_source_trace")

    default_run, _ = LIFECYCLE_DATASETS["clean_inbound_crm_sample"](tmp_path / "default")
    default_row = source_trace(default_run)
    assert default_row["field_name"] == "hs_analytics_source"

    run, _ = LIFECYCLE_DATASETS["clean_inbound_crm_sample"](tmp_path / "override")
    defs_path = run / "raw" / "properties_contacts.json"
    defs = json.loads(defs_path.read_text(encoding="utf-8"))
    defs.append({"name": "team_source", "label": "Team Source", "hubspotDefined": False})
    defs_path.write_text(json.dumps(defs), encoding="utf-8")
    (run / CONFIG_DIR).mkdir()
    (run / CONFIG_DIR / FIELD_OVERRIDES_FILE).write_text(
        "canonical_fields:\n  original_source: team_source\n", encoding="utf-8"
    )
    row = source_trace(run)
    assert row["field_name"] == "team_source"
    # team_source is empty on every contact, so every inbound deal with a
    # contact now lacks a source trace.
    assert row["denominator"] == default_row["denominator"]
    assert row["affected_records"] == row["denominator"] > default_row["affected_records"]


def test_rebuild_rederives_a_completed_snapshot_with_new_config(tmp_path):
    from core.lifecycle_synthetic_datasets import LIFECYCLE_DATASETS
    from scripts.run_lifecycle_integrity_audit import main
    from lifecycle_test_support import build_lifecycle_run

    source, _ = build_lifecycle_run(tmp_path / "source", "complex_lifecycle_demo")
    before = json.loads((source / "processed" / "journey_evidence_store.json").read_text())["assignment_counts"]
    mapping = tmp_path / "journey_mapping.yaml"
    mapping.write_text("values:\n  inbound: partner_led\nconfirmed_by: test owner\n", encoding="utf-8")
    out = tmp_path / "out"
    assert main(["--rebuild-from", str(source), "--output-root", str(out), "--journey-mapping", str(mapping)]) == 0
    rebuilt = [p for p in out.iterdir() if p.is_dir() and p.name.startswith("run_")]
    assert len(rebuilt) == 1
    manifest = json.loads((rebuilt[0] / "manifest.json").read_text())
    assert manifest["rebuilt_from"] == source.name
    assert manifest["client_config"]["journey_mapping.yaml"]["confirmed_by"] == "test owner"
    after = json.loads((rebuilt[0] / "processed" / "journey_evidence_store.json").read_text())["assignment_counts"]
    assert after.get("partner_led", 0) > before.get("partner_led", 0)
    # The source run is untouched.
    assert json.loads((source / "processed" / "journey_evidence_store.json").read_text())["assignment_counts"] == before


def test_example_config_templates_parse():
    from pathlib import Path

    import yaml

    root = Path(__file__).resolve().parents[1] / "examples" / "client_config"
    parse_field_overrides(yaml.safe_load((root / "field_overrides.example.yaml").read_text()))
    assert parse_journey_mapping(yaml.safe_load((root / "journey_mapping.example.yaml").read_text())).values
