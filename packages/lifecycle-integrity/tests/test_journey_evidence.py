from __future__ import annotations

import json

from core.journey_evidence import build_journey_evidence_store
from core.lifecycle_synthetic_datasets import LIFECYCLE_DATASETS
from core.profiler import profile_run


def test_journey_evidence_contains_hashes_not_raw_identity(tmp_path):
    run_dir, _ = LIFECYCLE_DATASETS["clean_inbound_crm_sample"](tmp_path)
    contacts_path = run_dir / "raw" / "contacts.jsonl"
    rows = [
        json.loads(line)
        for line in contacts_path.read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["properties"].update(
        {
            "email": "private.person@example.test",
            "firstname": "Private",
            "phone": "+1 (415) 555-0113",
        }
    )
    contacts_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    company_path = run_dir / "raw" / "companies.jsonl"
    company_text = company_path.read_text(encoding="utf-8")
    assert "Inbound Account" in company_text
    profile_run(run_dir)
    build_journey_evidence_store(run_dir)
    for path in (run_dir / "processed").rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "private.person@example.test" not in text
            assert "+1 (415) 555-0113" not in text
            assert "Inbound Account" not in text
            assert "inbound-1.test" not in text
    assignments = json.loads(
        (run_dir / "processed" / "journey_record_assignments.json").read_text(
            encoding="utf-8"
        )
    )
    assert assignments
    assert all(len(row["record_id_hash"]) == 64 for row in assignments)
    assert all(
        row["record_id_hash"] not in {"d1", "d2", "d3", "d4"}
        for row in assignments
    )


def test_unavailable_associations_are_explicit_limitations(tmp_path):
    run_dir, _ = LIFECYCLE_DATASETS["broken_association_sample"](tmp_path)
    (run_dir / "raw" / "associations_deal_contact.jsonl").unlink()
    profile_run(run_dir)
    store = build_journey_evidence_store(run_dir)
    assert "Deal-contact associations unavailable" in store["ambiguous_areas"]
    assert store["contains_raw_pii"] is False


def test_window_and_truncation_lower_confidence_and_surface_limitations(tmp_path):
    run_dir, _ = LIFECYCLE_DATASETS["clean_inbound_crm_sample"](tmp_path)
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "days": 90,
            "full_history": False,
            "truncated": {"contacts": True, "companies": False, "deals": False},
        }
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    profile_run(run_dir)
    store = build_journey_evidence_store(run_dir)
    assert any("Recent-only snapshot" in row for row in store["ambiguous_areas"])
    assert any("Snapshot truncated for contacts" in row for row in store["ambiguous_areas"])
    registry = json.loads(
        (run_dir / "journey_pattern_registry.json").read_text(encoding="utf-8")
    )
    inbound = next(
        row for row in registry["patterns"] if row["journey_type"] == "inbound_new_business"
    )
    assert inbound["evidence_components"]["contradiction_penalty"] >= 5


def test_property_names_do_not_classify_deals_or_contacts():
    from core.journey_evidence import classify_contact, classify_deal

    candidate_names = {"ns_renewal_date", "ns_original_source", "ns_deal_type"}
    company = {"properties": {"ns_renewal_date": None, "ns_original_source": "email_marketing"}}
    deal = {"properties": {"ns_deal_type": None}}
    journey, _, _ = classify_deal(
        deal,
        linked_contacts=[],
        linked_companies=[company],
        pipeline_label="Sales Pipeline",
        candidate_names=candidate_names,
    )
    assert journey == "inbound_new_business"

    contact = {"properties": {"ns_original_source": "paid_search"}}
    journey, _, _ = classify_contact(
        contact,
        linked_companies=[company],
        candidate_names=candidate_names,
        intent_signals=["lifecycle stage marketingqualifiedlead"],
    )
    assert journey == "inbound_new_business"


def test_new_business_deal_is_not_reclassified_by_customer_company():
    from core.journey_evidence import classify_deal

    candidate_names = {"ns_renewal_date", "ns_deal_type", "ns_lead_source"}
    customer_company = {"properties": {"ns_renewal_date": "2027-03-01", "ns_lead_source": "renewal"}}
    new_deal = {"properties": {"ns_deal_type": "new_business", "ns_lead_source": "partner"}}
    journey, _, _ = classify_deal(
        new_deal,
        linked_contacts=[],
        linked_companies=[customer_company],
        pipeline_label="New Business",
        candidate_names=candidate_names,
    )
    assert journey == "partner_led"

    upsell = {"properties": {"ns_deal_type": "up_sell"}}
    journey, _, _ = classify_deal(
        upsell,
        linked_contacts=[],
        linked_companies=[customer_company],
        pipeline_label="Expansion",
        candidate_names=candidate_names,
    )
    assert journey == "expansion_renewal"


def test_set_flag_property_name_still_counts():
    from core.journey_evidence import classify_contact

    contact = {"properties": {"is_partner_referral": "true"}}
    journey, _, _ = classify_contact(
        contact,
        linked_companies=[],
        candidate_names={"is_partner_referral"},
        intent_signals=["positive signal"],
    )
    assert journey == "partner_led"


def test_deal_own_source_outranks_linked_records():
    from core.journey_evidence import classify_deal

    candidate_names = {"ns_lead_source", "ns_original_source", "ns_source_detail"}
    deal = {"properties": {"ns_lead_source": "outbound"}}
    referral_contact = {"properties": {"ns_original_source": "referral"}}
    journey, _, evidence = classify_deal(
        deal,
        linked_contacts=[referral_contact],
        linked_companies=[],
        pipeline_label="New Business",
        candidate_names=candidate_names,
    )
    assert journey == "outbound_sales_led"
    assert "on deal" in evidence[0]

    silent_deal = {"properties": {"ns_lead_source": "trade_show"}}
    journey, _, evidence = classify_deal(
        silent_deal,
        linked_contacts=[referral_contact],
        linked_companies=[],
        pipeline_label="New Business",
        candidate_names=candidate_names,
    )
    assert journey == "partner_led"
    assert "on linked contacts" in evidence[0]


def test_generic_acquisition_channel_is_not_partner():
    from core.journey_evidence import classify_deal

    candidate_names = {"ns_source_detail", "ns_lead_source"}
    company = {"properties": {"ns_source_detail": "Standard acquisition channel"}}
    deal = {"properties": {"ns_lead_source": "trade_show"}}
    journey, _, _ = classify_deal(
        deal,
        linked_contacts=[],
        linked_companies=[company],
        pipeline_label="New Business",
        candidate_names=candidate_names,
    )
    assert journey == "unassigned"
