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
    log = json.loads((rebuilt[0] / "audit_log.json").read_text())
    assert log["events"][-1]["event"] == "rebuilt_from_snapshot"
    assert log["events"][-1]["source_run"] == source.name
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


# -- drafts, owner questions and confirmation ----------------------------------------


def test_source_values_are_material_text_with_keyword_suggestions():
    from core.journey_evidence import keyword_journey, summarize_source_values

    rows = summarize_source_values(
        {
            ("hs_object_source", "import"): {"d1", "d2", "d3"},
            ("hs_analytics_source", "offline"): {"d1", "d2", "d3", "d4"},
            ("lead_source", "trade show"): {"d1"},  # below the deal threshold
            ("lead_source", "jane@example.com"): {"d1", "d2", "d3"},  # redacted
        },
        None,
    )
    assert [(r["field"], r["deal_count"]) for r in rows] == [("hs_analytics_source", 4), ("hs_object_source", 3)]
    assert rows[1]["keyword_journey"] == "outbound_sales_led"
    assert rows[0]["keyword_journey"] == "unassigned"
    assert rows[0]["value"].endswith("offline")  # labelled as untrusted CRM data
    # A property name counts beside a free-text value, as in classification.
    assert keyword_journey("partner_name", "acme")[0] == "partner_led"


def _confirmation_run(tmp_path, *, proposal=None, overrides=None):
    import yaml

    run = tmp_path / "run"
    (run / "raw").mkdir(parents=True)
    (run / "raw" / "properties_contacts.json").write_text(json.dumps(PROP_DEFS["contacts"]))
    (run / "raw" / "properties_companies.json").write_text(json.dumps(PROP_DEFS["companies"]))
    canonical, _ = resolve_canonical_fields(run, PROP_DEFS, _candidates())
    context = {
        "canonical_fields": canonical,
        "candidate_fields": _candidates(),
        "source_values": [
            {"field": "hs_object_source", "value": "[CRM_FIELD_VALUE:UNTRUSTED_DATA_ONLY] import",
             "deal_count": 12, "keyword_journey": "outbound_sales_led", "keyword_basis": "keyword: import"},
            {"field": "lead_source", "value": "[CRM_FIELD_VALUE:UNTRUSTED_DATA_ONLY] trade show",
             "deal_count": 5, "keyword_journey": "inbound_new_business", "keyword_basis": "keyword: trade show"},
        ],
        "unassigned_deals": 7,
    }
    (run / "crm_context.yaml").write_text(yaml.safe_dump(context))
    if proposal is not None:
        (run / "agent_workspace" / "analysis").mkdir(parents=True)
        (run / "agent_workspace" / "analysis" / "schema_discovery_agent.json").write_text(
            json.dumps({"role": "schema_discovery_agent", "proposed_client_config": proposal})
        )
    if overrides is not None:
        (run / "config").mkdir()
        (run / "config" / "field_overrides.yaml").write_text(overrides)
    return run


def test_questions_cover_competing_fields_and_unconfirmed_values(tmp_path):
    from core.client_config import build_confirmation

    confirmation = build_confirmation(_confirmation_run(tmp_path))
    ids = [q["id"] for q in confirmation["questions"]]
    assert ids == ["field.lifecycle_stage", "field.original_source", "journey_mapping"]
    lifecycle = confirmation["questions"][0]
    assert (lifecycle["suggested"], lifecycle["alternatives"]) == ("lifecyclestage", ["ns_lifecycle_stage"])
    values = confirmation["questions"][2]["values"]
    assert values[0]["value"] == "import" and values[0]["suggested"] == "outbound_sales_led"
    assert confirmation["questions"][2]["unassigned_deals"] == 7


def test_schema_discovery_proposal_becomes_the_suggestion_within_bounds(tmp_path):
    from core.client_config import build_confirmation

    proposal = {
        "canonical_fields": {
            "lifecycle_stage": {"field": "ns_lifecycle_stage", "evidence": "Sales updates it daily."},
            "original_source": {"field": "invented_field"},
        },
        "journey_mapping": [
            {"field": "hs_object_source", "value": "IMPORT", "journey": "unassigned", "evidence": "How a record was created."},
            {"field": "lead_source", "value": "trade show", "journey": "not_a_journey"},
        ],
    }
    confirmation = build_confirmation(_confirmation_run(tmp_path, proposal=proposal))
    fields = {row["role"]: row for row in confirmation["field_overrides"]}
    assert fields["lifecycle_stage"]["suggested"] == "ns_lifecycle_stage"
    assert fields["lifecycle_stage"]["alternatives"] == ["lifecyclestage"]
    assert fields["original_source"]["suggested"] == "hs_analytics_source"  # invented field ignored
    values = {row["value"]: row for row in confirmation["journey_values"]}
    assert values["import"]["suggested"] == "unassigned"
    assert values["trade show"]["suggested"] == "inbound_new_business"


def test_confirmed_fields_are_not_asked_again(tmp_path):
    from core.client_config import build_confirmation

    run = _confirmation_run(
        tmp_path,
        overrides="canonical_fields:\n  lifecycle_stage: ns_lifecycle_stage\n  original_source: ns_original_source\n",
    )
    ids = [q["id"] for q in build_confirmation(run)["questions"]]
    assert ids == ["journey_mapping"]


def test_drafts_parse_and_confirmation_stamps_and_saves(tmp_path):
    import yaml

    from core.client_config import DRAFT_DIR, write_client_config_drafts
    from scripts.confirm_client_config import confirm

    run = _confirmation_run(tmp_path)
    write_client_config_drafts(run)
    draft = (run / DRAFT_DIR / "journey_mapping.yaml").read_text()
    assert "CONFIRM · 12 deals · keyword: import" in draft
    assert yaml.safe_load(draft)["fields"]["hs_object_source"]["import"] == "outbound_sales_led"
    assert json.loads((run / DRAFT_DIR / "questions.json").read_text())["questions"]

    # The owner says imports say nothing about the journey.
    (run / DRAFT_DIR / "journey_mapping.yaml").write_text(
        draft.replace('"import": outbound_sales_led', '"import": unassigned')
    )
    saved = confirm(run, "Alice, RevOps", tmp_path / "client_config", ["field_overrides.yaml", "journey_mapping.yaml"])
    mapping = yaml.safe_load(saved["journey_mapping.yaml"].read_text())
    assert mapping["confirmed_by"] == "Alice, RevOps" and mapping["confirmed_on"]
    assert mapping["fields"]["hs_object_source"]["import"] == "unassigned"
    assert "# CONFIRM" in saved["journey_mapping.yaml"].read_text()  # comments kept


def test_confirmation_refuses_unknown_fields_and_anonymous_owners(tmp_path):
    from core.client_config import DRAFT_DIR, write_client_config_drafts
    from scripts.confirm_client_config import confirm

    run = _confirmation_run(tmp_path)
    write_client_config_drafts(run)
    with pytest.raises(ClientConfigError, match="must name the owner"):
        confirm(run, "  ", tmp_path / "out", ["field_overrides.yaml"])
    path = run / DRAFT_DIR / "field_overrides.yaml"
    path.write_text(path.read_text().replace("original_source: hs_analytics_source", "original_source: nope"))
    with pytest.raises(ClientConfigError, match="not a contact property"):
        confirm(run, "Alice", tmp_path / "out", ["field_overrides.yaml"])
    assert not (tmp_path / "out").exists()


def test_confirm_command_rebuilds_with_the_confirmed_files(tmp_path):
    from core.client_config import DRAFT_DIR, write_client_config_drafts
    from scripts.confirm_client_config import main
    from lifecycle_test_support import build_lifecycle_run

    source, _ = build_lifecycle_run(tmp_path / "out", "complex_lifecycle_demo")
    write_client_config_drafts(source)
    assert (source / DRAFT_DIR / "field_overrides.yaml").exists()
    assert main(["--run", str(source), "--confirmed-by", "Test Owner"]) == 0
    saved = source.parent / "client_config"
    assert (saved / "field_overrides.yaml").exists() and (saved / "journey_mapping.yaml").exists()
    rebuilt = [p for p in source.parent.iterdir() if p.name.startswith("run_") and p != source]
    assert len(rebuilt) == 1
    manifest = json.loads((rebuilt[0] / "manifest.json").read_text())
    assert manifest["rebuilt_from"] == source.name
    assert manifest["client_config"]["field_overrides.yaml"]["confirmed_by"] == "Test Owner"
    import yaml

    context = yaml.safe_load((rebuilt[0] / "crm_context.yaml").read_text())
    assert context["client_config"]["field_overrides"] is True
    assert (rebuilt[0] / "config" / "journey_mapping.yaml").exists()


def test_latest_source_fields_do_not_compete_with_original_source(tmp_path):
    candidates = _candidates()
    candidates["source"].append(
        {"object_type": "contacts", "field": "ns_latest_source", "hubspot_defined": False,
         "fill_rate": 95.0, "top_values": candidates["source"][0]["top_values"]}
    )
    defs = {**PROP_DEFS, "contacts": PROP_DEFS["contacts"] + [{"name": "ns_latest_source"}]}
    canonical, _ = resolve_canonical_fields(tmp_path, defs, candidates)
    assert canonical["original_source"]["competing_fields"] == ["ns_original_source"]
