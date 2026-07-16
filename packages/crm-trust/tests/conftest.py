"""Shared fixtures: a synthetic messy-ish CRM snapshot."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _jsonl(path: Path, rows: list) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )


def _json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def measured_run(synthetic_run: Path) -> Path:
    """synthetic_run + profiling + deal-contact assoc + written measurements."""
    from test_rules import CONTEXT, add_deal_contact_associations

    from connectors.hubspot.normalize import write_json
    from core.profiler import profile_run
    from core.rules import measure_all
    from core.schemas import CrmContext

    profile_run(synthetic_run)
    add_deal_contact_associations(synthetic_run)
    results = measure_all(synthetic_run, CrmContext.model_validate(CONTEXT))
    for module, doc in results.items():
        write_json(
            synthetic_run / "processed" / "measurements" / f"{module}.json", doc
        )
    (synthetic_run / "findings").mkdir()
    return synthetic_run


@pytest.fixture
def synthetic_run(tmp_path: Path) -> Path:
    """A run dir with known gaps: decayed legacy source field, missing
    sources on recent contacts, partial associations, an unknown pipeline,
    and one PII value hiding in a custom field."""
    run = tmp_path / "run_20260712_000000"
    raw = run / "raw"
    raw.mkdir(parents=True)

    # 10 contacts created monthly Jan..Oct 2026.
    contacts = []
    for i in range(1, 11):
        props = {
            "createdate": f"2026-{i:02d}-15T00:00:00Z",
            "lifecyclestage": (
                "lead" if i <= 5
                else "marketingqualifiedlead" if i <= 7
                else "customer" if i <= 9
                else ""
            ),
            # canonical source: filled for c1..c7, empty for the 3 newest
            "hs_analytics_source": (
                ("ORGANIC_SEARCH" if i <= 4 else "PAID_SEARCH") if i <= 7 else ""
            ),
            # legacy field: filled only in the older half (usage decay)
            "old_lead_source_2021": "google-ads" if i <= 5 else "",
            "hubspot_owner_id": "901",
        }
        if i == 3:  # PII smuggled into a custom source-ish field
            props["utm_notes"] = "reach me at jane.doe@acme.com re campaign"
        contacts.append({"id": f"c{i}", "properties": props})
    _jsonl(raw / "contacts.jsonl", contacts)

    companies = [
        {"id": "co1", "properties": {"createdate": "2026-01-01T00:00:00Z", "domain": "acme.com", "name": "Acme", "lifecyclestage": "customer"}},
        {"id": "co2", "properties": {"createdate": "2026-02-01T00:00:00Z", "domain": "acme.com", "name": "Acme Inc", "lifecyclestage": ""}},
        {"id": "co3", "properties": {"createdate": "2026-03-01T00:00:00Z", "domain": "beta.io", "name": "Beta", "lifecyclestage": "lead"}},
        {"id": "co4", "properties": {"createdate": "2026-04-01T00:00:00Z", "domain": "", "name": "Ghost LLC", "lifecyclestage": ""}},
    ]
    _jsonl(raw / "companies.jsonl", companies)

    deals = [
        {"id": "d1", "properties": {"createdate": "2026-03-01T00:00:00Z", "pipeline": "default", "dealstage": "appointmentscheduled", "amount": "5000"}},
        {"id": "d2", "properties": {"createdate": "2026-04-01T00:00:00Z", "pipeline": "default", "dealstage": "appointmentscheduled", "amount": "", "closedate": "2026-01-01T00:00:00Z"}},
        {"id": "d3", "properties": {"createdate": "2026-05-01T00:00:00Z", "pipeline": "default", "dealstage": "closedwon", "amount": "12000"}},
        {"id": "d4", "properties": {"createdate": "2026-06-01T00:00:00Z", "pipeline": "default", "dealstage": "closedwon", "amount": "8000"}},
        {"id": "d5", "properties": {"createdate": "2026-07-01T00:00:00Z", "pipeline": "legacy_pipe", "dealstage": "mystery_stage", "amount": ""}},
    ]
    _jsonl(raw / "deals.jsonl", deals)

    _json(
        raw / "properties_contacts.json",
        [
            {"name": "createdate", "label": "Create Date", "hubspotDefined": True},
            {"name": "lifecyclestage", "label": "Lifecycle Stage", "hubspotDefined": True},
            {"name": "hs_analytics_source", "label": "Original Source", "hubspotDefined": True},
            {"name": "hubspot_owner_id", "label": "Contact owner", "hubspotDefined": True},
            {"name": "old_lead_source_2021", "label": "Old Lead Source 2021", "hubspotDefined": False},
            {"name": "utm_notes", "label": "UTM Notes", "hubspotDefined": False},
        ],
    )
    _json(
        raw / "properties_companies.json",
        [
            {"name": "domain", "label": "Domain", "hubspotDefined": True},
            {"name": "name", "label": "Name", "hubspotDefined": True},
            {"name": "lifecyclestage", "label": "Lifecycle Stage", "hubspotDefined": True},
        ],
    )
    _json(
        raw / "properties_deals.json",
        [
            {"name": "dealstage", "label": "Deal Stage", "hubspotDefined": True},
            {"name": "pipeline", "label": "Pipeline", "hubspotDefined": True},
            {"name": "amount", "label": "Amount", "hubspotDefined": True},
        ],
    )
    _json(raw / "owners.json", [{"id": "901"}, {"id": "902"}])
    _json(
        raw / "pipelines.json",
        [
            {
                "id": "default",
                "label": "Sales Pipeline",
                "stages": [
                    {"id": "appointmentscheduled", "label": "Appointment"},
                    {"id": "closedwon", "label": "Closed Won"},
                ],
            }
        ],
    )

    # Associations: c1-c3 → one company, c4 → two, rest orphaned.
    _jsonl(
        raw / "associations_contact_company.jsonl",
        [
            {"from_id": "c1", "to_ids": ["co1"]},
            {"from_id": "c2", "to_ids": ["co1"]},
            {"from_id": "c3", "to_ids": ["co3"]},
            {"from_id": "c4", "to_ids": ["co1", "co2"]},
        ],
    )
    _jsonl(
        raw / "associations_deal_company.jsonl",
        [
            {"from_id": "d1", "to_ids": ["co1"]},
            {"from_id": "d3", "to_ids": ["co1"]},
            {"from_id": "d4", "to_ids": ["co3"]},
        ],
    )
    # deal→contact association file deliberately missing (403 scenario)

    _json(
        run / "manifest.json",
        {
            "run_id": run.name,
            "created_at": "2026-07-12T00:00:00+00:00",
            "status": "completed",
            # Relationship measurements in this fixture are intended to test
            # exact arithmetic. Windowed-coverage behavior has a dedicated
            # test and must not be mixed into those assertions.
            "days": None,
            "full_history": True,
            "counts": {"contacts": 10, "companies": 4, "deals": 5},
            "truncated": {"contacts": False, "companies": False, "deals": False},
            "source_candidates": {},
            "warnings": [],
        },
    )
    return run
