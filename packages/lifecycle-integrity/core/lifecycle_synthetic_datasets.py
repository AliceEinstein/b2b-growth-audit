"""Synthetic portals required by the lifecycle design contract."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Tuple

from .synthetic_datasets import _company, _contact, _deal, _iso, _write_json, _write_jsonl, make_run

BuilderResult = Tuple[Path, Dict[str, Any]]


def _definition(name: str, label: str) -> Dict[str, Any]:
    return {"name": name, "label": label, "hubspotDefined": False}


def _expect(patterns: Dict[str, int], **extra: Any) -> Dict[str, Any]:
    return {
        "expected_patterns_min_confidence": patterns,
        "expected_confidence_ranges": {
            journey: [minimum, 100] for journey, minimum in patterns.items()
        },
        "expected_findings": [],
        "expected_observations": [],
        "blocked_recommendations": [
            "automatic CRM writes",
            "automatic lifecycle-stage resets",
            "automatic record merges or deletions",
        ],
        "unsafe_recommendations_allowed": False,
        "all_scored_findings_require_evidence": True,
        **extra,
    }


def _funnel_contact(i: int, month: int) -> Dict[str, Any]:
    """A customer with a fully timestamped lead→MQL→SQL→customer path."""
    return _contact(
        i,
        month,
        source="ORGANIC_SEARCH",
        lifecycle="customer",
        extra={
            "hs_v2_date_entered_lead": _iso(month),
            "hs_v2_date_entered_marketingqualifiedlead": _iso(month + 1),
            "hs_v2_date_entered_salesqualifiedlead": _iso(month + 2),
            "hs_v2_date_entered_customer": _iso(month + 3),
        },
    )


def clean_inbound(root: Path) -> BuilderResult:
    contacts = [
        _contact(i, i, source="ORGANIC_SEARCH" if i % 2 else "PAID_SEARCH")
        for i in range(1, 9)
    ] + [_funnel_contact(9, 2), _funnel_contact(10, 3)]
    companies = [
        _company(
            i,
            f"inbound-{i}.test",
            f"Inbound Account {i}",
            "customer" if i == 4 else "",
        )
        for i in range(1, 5)
    ]
    deals = [_deal(i, i + 3, stage="closedwon" if i == 4 else "appointmentscheduled") for i in range(1, 5)]
    run = make_run(
        root,
        "clean_inbound_crm_sample",
        contacts=contacts,
        companies=companies,
        deals=deals,
        assoc_contact_company=[
            {"from_id": f"c{i}", "to_ids": [f"co{(i - 1) % 4 + 1}"]}
            for i in range(1, 9)
        ],
        assoc_deal_company=[{"from_id": f"d{i}", "to_ids": [f"co{i}"]} for i in range(1, 5)],
        assoc_deal_contact=[{"from_id": f"d{i}", "to_ids": [f"c{i}"]} for i in range(1, 5)],
    )
    return run, _expect({"inbound_new_business": 50}, expected_assignment="inbound_new_business")


def outbound_sales_led(root: Path) -> BuilderResult:
    contacts = [
        _contact(i, i, source="", lifecycle="lead", object_source="IMPORT")
        for i in range(1, 7)
    ]
    deals = [_deal(i, i + 2) for i in range(1, 5)]
    for deal in deals:
        deal["properties"]["sales_motion"] = "Outbound SDR"
    pipelines = [{
        "id": "outbound",
        "label": "Outbound New Business",
        "stages": [
            {"id": "open", "label": "Prospecting", "metadata": {"isClosed": "false", "probability": "0.2"}},
            {"id": "won", "label": "Won", "metadata": {"isClosed": "true", "probability": "1.0"}},
        ],
    }]
    for deal in deals:
        deal["properties"].update({"pipeline": "outbound", "dealstage": "open"})
    run = make_run(
        root,
        "outbound_sales_led_sample",
        contacts=contacts,
        companies=[_company(1, "target.test", "Target")],
        deals=deals,
        pipelines=pipelines,
        extra_deal_defs=[_definition("sales_motion", "Sales Motion")],
        assoc_contact_company=[{"from_id": f"c{i}", "to_ids": ["co1"]} for i in range(1, 7)],
        assoc_deal_company=[{"from_id": f"d{i}", "to_ids": ["co1"]} for i in range(1, 5)],
        assoc_deal_contact=[{"from_id": f"d{i}", "to_ids": [f"c{i}"]} for i in range(1, 5)],
    )
    return run, _expect(
        {"outbound_sales_led": 50},
        no_mql_is_valid_exception=True,
        expected_observations=["no_prior_mql:valid_exception"],
    )


def abm(root: Path) -> BuilderResult:
    contacts = [_contact(i, i, source="") for i in range(1, 9)]
    companies = [_company(1, "named.test", "Named Account"), _company(2, "tier.test", "Tier Account")]
    for company in companies:
        company["properties"].update({"account_tier": "Tier 1", "target_account": "true", "hubspot_owner_id": "901"})
    deals = [_deal(1, 5), _deal(2, 6)]
    pipelines = [{
        "id": "abm",
        "label": "ABM Named Accounts",
        "stages": [{"id": "open", "label": "Engaged Account", "metadata": {"isClosed": "false", "probability": "0.3"}}],
    }]
    for deal in deals:
        deal["properties"].update({"pipeline": "abm", "dealstage": "open"})
    run = make_run(
        root,
        "abm_sample",
        contacts=contacts,
        companies=companies,
        deals=deals,
        pipelines=pipelines,
        extra_company_defs=[_definition("account_tier", "Account Tier"), _definition("target_account", "Target Account")],
        assoc_contact_company=[{"from_id": f"c{i}", "to_ids": ["co1" if i <= 4 else "co2"]} for i in range(1, 9)],
        assoc_deal_company=[{"from_id": "d1", "to_ids": ["co1"]}, {"from_id": "d2", "to_ids": ["co2"]}],
        assoc_deal_contact=[{"from_id": "d1", "to_ids": ["c1", "c2"]}, {"from_id": "d2", "to_ids": ["c5", "c6"]}],
    )
    return run, _expect({"abm_account_based": 50}, expected_assignment="abm_account_based")


def partner_led(root: Path) -> BuilderResult:
    contacts = [_contact(i, i, source="REFERRALS") for i in range(1, 6)]
    deals = [_deal(i, i + 2) for i in range(1, 4)]
    for deal in deals:
        deal["properties"].update({"pipeline": "partner", "dealstage": "open", "partner_source": "Referral Partner"})
    pipelines = [{
        "id": "partner",
        "label": "Partner Referral",
        "stages": [{"id": "open", "label": "Partner Qualified", "metadata": {"isClosed": "false", "probability": "0.3"}}],
    }]
    run = make_run(
        root,
        "partner_led_sample",
        contacts=contacts,
        companies=[_company(1, "partner.test", "Partner Customer")],
        deals=deals,
        pipelines=pipelines,
        extra_deal_defs=[_definition("partner_source", "Partner Source")],
        assoc_contact_company=[{"from_id": f"c{i}", "to_ids": ["co1"]} for i in range(1, 6)],
        assoc_deal_company=[{"from_id": f"d{i}", "to_ids": ["co1"]} for i in range(1, 4)],
        assoc_deal_contact=[{"from_id": f"d{i}", "to_ids": [f"c{i}"]} for i in range(1, 4)],
    )
    return run, _expect({"partner_led": 50}, expected_assignment="partner_led")


def expansion_renewal(root: Path) -> BuilderResult:
    contacts = [_contact(1, 1, source="", lifecycle="customer")]
    company = _company(1, "customer.test", "Customer", "customer")
    deals = [
        _deal(1, 2, pipeline="renewal", stage="won"),
        _deal(2, 7, pipeline="renewal", stage="open"),
        _deal(3, 8, pipeline="renewal", stage="open"),
    ]
    deals[0]["properties"]["dealtype"] = "renewal"
    deals[1]["properties"]["dealtype"] = "expansion"
    deals[2]["properties"]["dealtype"] = "renewal"
    pipelines = [{
        "id": "renewal",
        "label": "Expansion and Renewal",
        "stages": [
            {"id": "open", "label": "Renewal Open", "metadata": {"isClosed": "false", "probability": "0.5"}},
            {"id": "won", "label": "Renewed", "metadata": {"isClosed": "true", "probability": "1.0"}},
        ],
    }]
    run = make_run(
        root,
        "expansion_renewal_sample",
        contacts=contacts,
        companies=[company],
        deals=deals,
        pipelines=pipelines,
        extra_deal_defs=[{"name": "dealtype", "label": "Deal Type", "hubspotDefined": True}],
        assoc_contact_company=[{"from_id": "c1", "to_ids": ["co1"]}],
        assoc_deal_company=[{"from_id": f"d{i}", "to_ids": ["co1"]} for i in range(1, 4)],
        assoc_deal_contact=[{"from_id": f"d{i}", "to_ids": ["c1"]} for i in range(1, 4)],
    )
    return run, _expect({"expansion_renewal": 50}, expected_assignment="expansion_renewal")


def mixed_motion(root: Path) -> BuilderResult:
    contacts = [
        _contact(1, 1, source="ORGANIC_SEARCH"),
        _contact(2, 2, source="PAID_SEARCH"),
        _contact(3, 3, source="", object_source="IMPORT"),
        _contact(4, 4, source="", object_source="IMPORT", lifecycle="customer"),
    ]
    company = _company(1, "mixed.test", "Mixed", "customer")
    deals = [_deal(1, 5), _deal(2, 6), _deal(3, 7), _deal(4, 8)]
    deals[1]["properties"]["sales_motion"] = "Outbound SDR"
    deals[2]["properties"].update({"pipeline": "renewal", "dealstage": "won", "dealtype": "renewal"})
    deals[3]["properties"].update({"pipeline": "renewal", "dealstage": "open", "dealtype": "expansion"})
    pipelines = [
        {
            "id": "default",
            "label": "New Business",
            "stages": [{"id": "appointmentscheduled", "label": "Open", "metadata": {"isClosed": "false", "probability": "0.2"}}],
        },
        {
            "id": "renewal",
            "label": "Expansion Renewal",
            "stages": [
                {"id": "open", "label": "Open", "metadata": {"isClosed": "false", "probability": "0.5"}},
                {"id": "won", "label": "Won", "metadata": {"isClosed": "true", "probability": "1.0"}},
            ],
        },
    ]
    run = make_run(
        root,
        "mixed_motion_scaleup_sample",
        contacts=contacts,
        companies=[company],
        deals=deals,
        pipelines=pipelines,
        extra_deal_defs=[_definition("sales_motion", "Sales Motion"), {"name": "dealtype", "label": "Deal Type", "hubspotDefined": True}],
        assoc_contact_company=[{"from_id": f"c{i}", "to_ids": ["co1"]} for i in range(1, 5)],
        assoc_deal_company=[{"from_id": f"d{i}", "to_ids": ["co1"]} for i in range(1, 5)],
        assoc_deal_contact=[{"from_id": f"d{i}", "to_ids": [f"c{i}"]} for i in range(1, 5)],
    )
    return run, _expect(
        {"inbound_new_business": 45, "outbound_sales_led": 45, "expansion_renewal": 50},
        expected_primary_model="multi_motion",
    )


def legacy_property_sprawl(root: Path) -> BuilderResult:
    definitions = [
        _definition("old_lifecycle_2021", "Old Lifecycle 2021"),
        _definition("lead_source_backup", "Lead Source Backup"),
        _definition("utm_campaign_legacy", "UTM Campaign Legacy"),
    ]
    contacts = []
    for i in range(1, 9):
        contacts.append(
            _contact(
                i,
                i,
                source="ORGANIC_SEARCH",
                extra={
                    "old_lifecycle_2021": "mql" if i <= 4 else "",
                    "lead_source_backup": "google" if i <= 4 else "",
                    "utm_campaign_legacy": "old" if i <= 3 else "",
                },
            )
        )
    run = make_run(
        root,
        "legacy_property_sprawl_sample",
        contacts=contacts,
        extra_contact_defs=definitions,
        assoc_contact_company=[],
        assoc_deal_company=[],
        assoc_deal_contact=[],
    )
    return run, _expect(
        {"inbound_new_business": 30},
        expected_measurement="lifecycle_field_fragmentation",
        expected_findings=["lifecycle_field_fragmentation"],
    )


def broken_association(root: Path) -> BuilderResult:
    contacts = [_contact(i, i, source="ORGANIC_SEARCH") for i in range(1, 7)]
    deals = [_deal(i, i + 2) for i in range(1, 4)]
    run = make_run(
        root,
        "broken_association_sample",
        contacts=contacts,
        companies=[_company(1, "broken.test", "Broken")],
        deals=deals,
        assoc_contact_company=[{"from_id": "c1", "to_ids": ["co1"]}],
        assoc_deal_company=[{"from_id": "d1", "to_ids": ["co1"]}],
        assoc_deal_contact=[{"from_id": "d1", "to_ids": ["c1"]}],
    )
    return run, _expect(
        {"inbound_new_business": 30},
        expected_measurement="deals_without_company",
        expected_findings=["deals_without_company"],
    )


def pipeline_leakage(root: Path) -> BuilderResult:
    """Journey-first sample with traceable open-deal exposure and a
    separate no-deal recovery population.

    d1 and d2 carry real deal amounts and deterministic integrity gaps. c2,
    c3, and c5 are high-intent contacts without deals; they must be counted,
    never assigned synthetic pipeline value.
    """
    contacts = [
        _contact(1, 1, source="ORGANIC_SEARCH", lifecycle="marketingqualifiedlead"),
        _contact(2, 2, source="PAID_SEARCH", lifecycle="marketingqualifiedlead", owner=""),
        _contact(
            3,
            3,
            source="PAID_SEARCH",
            lifecycle="lead",
            owner="",
            extra={"demo_request_status": "submitted"},
        ),
        _contact(4, 4, source="ORGANIC_SEARCH", lifecycle="salesqualifiedlead"),
        _contact(5, 5, source="ORGANIC_SEARCH", lifecycle="marketingqualifiedlead"),
        _contact(
            6,
            6,
            source="ORGANIC_SEARCH",
            lifecycle="lead",
            extra={"demo_request_status": "submitted"},
        ),
        _contact(7, 7, source="ORGANIC_SEARCH", lifecycle="lead"),
    ]
    deals = [
        _deal(1, 4, pipeline="inbound", stage="qualified", amount="25000", owner=""),
        _deal(2, 6, pipeline="inbound", stage="proposal", amount="40000"),
        _deal(3, 8, pipeline="inbound", stage="won", amount="15000"),
    ]
    pipelines = [
        {
            "id": "inbound",
            "label": "Inbound New Business",
            "stages": [
                {
                    "id": "qualified",
                    "label": "Sales Qualified",
                    "metadata": {"isClosed": "false", "probability": "0.3"},
                },
                {
                    "id": "proposal",
                    "label": "Proposal",
                    "metadata": {"isClosed": "false", "probability": "0.6"},
                },
                {
                    "id": "won",
                    "label": "Closed Won",
                    "metadata": {"isClosed": "true", "probability": "1.0"},
                },
            ],
        }
    ]
    run = make_run(
        root,
        "pipeline_leakage_sample",
        contacts=contacts,
        companies=[
            _company(1, "inbound-one.test", "Inbound One"),
            _company(2, "inbound-two.test", "Inbound Two"),
            _company(3, "customer.test", "Existing Customer", "customer"),
        ],
        deals=deals,
        pipelines=pipelines,
        extra_contact_defs=[
            _definition("demo_request_status", "Synced Demo Request Status")
        ],
        assoc_contact_company=[
            {"from_id": "c1", "to_ids": ["co1"]},
            {"from_id": "c2", "to_ids": ["co1"]},
            {"from_id": "c3", "to_ids": ["co1"]},
            {"from_id": "c4", "to_ids": ["co2"]},
            {"from_id": "c5", "to_ids": ["co2"]},
            {"from_id": "c6", "to_ids": ["co3"]},
        ],
        assoc_deal_company=[
            {"from_id": "d1", "to_ids": ["co1"]},
            {"from_id": "d3", "to_ids": ["co3"]},
        ],
        assoc_deal_contact=[
            {"from_id": "d1", "to_ids": ["c1"]},
            {"from_id": "d2", "to_ids": ["c4"]},
            {"from_id": "d3", "to_ids": ["c6"]},
        ],
    )
    return run, _expect(
        {"inbound_new_business": 50},
        expected_measurement="inbound_new_business_high_intent_contacts_without_deal",
        expected_findings=[
            "inbound_new_business_deals_without_owner",
            "inbound_new_business_high_intent_contacts_without_deal",
        ],
        expected_open_deal_exposure="65000.00",
        expected_potential_recoverable_population=3,
    )


def complex_lifecycle_demo(root: Path) -> BuilderResult:
    """A mixed-motion demo with enough evidence to exercise the decision report.

    This fixture intentionally contains several distinct commercial situations:
    inbound intent with no deal, an open deal requiring escalation, outbound,
    ABM, partner, and expansion/renewal signals, a closed-lost reactivation,
    one open deal without an account association, and read-only workflow data.
    Amounts are only attached to existing deals; contact-only recovery remains
    unvalued.
    """
    def demo_iso(month: int, day: int = 15) -> str:
        # Keep every commercial event before the 16 Jul 2026 audit date while
        # making the response gaps recent enough to be decision-useful.
        return _iso(month, day=day, year=2026)

    contacts = [
        _contact(1, 1, source="ORGANIC_SEARCH", lifecycle="salesqualifiedlead", extra={"firstname": "Avery", "lastname": "Morgan"}),
        _contact(2, 2, source="PAID_SEARCH", lifecycle="marketingqualifiedlead", owner="", extra={"firstname": "Priya", "lastname": "Shah"}),
        _contact(3, 3, source="", lifecycle="lead", object_source="IMPORT", extra={"firstname": "Daniel", "lastname": "Ortiz", "sales_motion": "Outbound SDR"}),
        _contact(4, 4, source="", lifecycle="lead", extra={"firstname": "Nora", "lastname": "Kim", "account_tier": "Tier 1", "target_account": "true"}),
        _contact(5, 5, source="REFERRALS", lifecycle="lead", extra={"firstname": "Leo", "lastname": "Martin", "partner_source": "Northstar Referral"}),
        _contact(6, 6, source="", lifecycle="customer", extra={"firstname": "Sofia", "lastname": "Rossi", "dealtype": "renewal"}),
        _contact(7, 7, source="", lifecycle="customer", extra={"firstname": "Ethan", "lastname": "Brooks", "dealtype": "expansion"}),
        _contact(8, 8, source="ORGANIC_SEARCH", lifecycle="lead", owner="", extra={"firstname": "Maya", "lastname": "Patel", "demo_request_status": "submitted"}),
        _contact(9, 9, source="SOCIAL_MEDIA", lifecycle="lead", extra={"firstname": "Camille", "lastname": "Dubois"}),
        _contact(10, 10, source="", lifecycle="customer", extra={"firstname": "James", "lastname": "Liu"}),
    ]
    companies = [
        _company(1, "inbound.demo.test", "Inbound Demo Account"),
        _company(2, "target.demo.test", "Tier One Target", "lead"),
        _company(3, "partner.demo.test", "Partner Account"),
        _company(4, "customer.demo.test", "Existing Customer", "customer"),
        _company(5, "lost-customer.demo.test", "Reactivation Customer", "customer"),
    ]
    deals = [
        _deal(1, 4, pipeline="inbound", stage="qualified", amount="32000", owner="901", dealname="Inbound — Enterprise Evaluation"),
        _deal(2, 5, pipeline="inbound", stage="proposal", amount="28000", owner="901", dealname="Inbound — Security Expansion"),
        _deal(3, 6, pipeline="outbound", stage="discovery", amount="18000", owner="902", dealname="Outbound — Target Account Discovery"),
        _deal(4, 7, pipeline="abm", stage="engaged", amount="46000", owner="901", dealname="ABM — Tier One Evaluation"),
        _deal(5, 8, pipeline="partner", stage="qualified", amount="12000", owner="901", dealname="Partner — Referral Opportunity"),
        _deal(6, 9, pipeline="renewal", stage="open", amount="38000", owner="901", dealname="Renewal — Existing Customer"),
        _deal(7, 10, pipeline="renewal", stage="lost", amount="24000", owner="901", dealname="Renewal — Closed Lost", closedate=demo_iso(5, day=20)),
        _deal(8, 11, pipeline="abm", stage="engaged", amount="21000", owner="901", dealname="ABM — Unlinked Target Deal"),
    ]
    contact_created = [
        _iso(1, day=5, year=2025), _iso(2, day=5, year=2025),
        _iso(3, day=5, year=2025), _iso(4, day=5, year=2025),
        _iso(5, day=5, year=2025), _iso(6, day=5, year=2025),
        _iso(7, day=5, year=2025), _iso(1, day=5, year=2026),
        _iso(2, day=5, year=2026), _iso(3, day=5, year=2026),
    ]
    company_created = [_iso(index, day=6, year=2025) for index in range(1, 6)]
    deal_created = [
        demo_iso(1, day=10), demo_iso(2, day=10), demo_iso(3, day=5),
        demo_iso(3, day=12), demo_iso(4, day=2), demo_iso(4, day=15),
        demo_iso(1, day=20), demo_iso(5, day=1),
    ]
    for row, created_at in zip(contacts, contact_created):
        row["properties"]["createdate"] = created_at
    for row, created_at in zip(companies, company_created):
        row["properties"]["createdate"] = created_at
    for row, created_at in zip(deals, deal_created):
        row["properties"]["createdate"] = created_at
    pipelines = [
        {"id": "inbound", "label": "Inbound New Business", "stages": [
            {"id": "qualified", "label": "Sales Qualified", "metadata": {"isClosed": "false", "probability": "0.3"}},
            {"id": "proposal", "label": "Proposal", "metadata": {"isClosed": "false", "probability": "0.6"}},
        ]},
        {"id": "outbound", "label": "Outbound Sales", "stages": [
            {"id": "discovery", "label": "Discovery", "metadata": {"isClosed": "false", "probability": "0.25"}},
        ]},
        {"id": "abm", "label": "ABM Named Accounts", "stages": [
            {"id": "engaged", "label": "Target Account Engaged", "metadata": {"isClosed": "false", "probability": "0.35"}},
        ]},
        {"id": "partner", "label": "Partner Referral", "stages": [
            {"id": "qualified", "label": "Partner Qualified", "metadata": {"isClosed": "false", "probability": "0.3"}},
        ]},
        {"id": "renewal", "label": "Expansion and Renewal", "stages": [
            {"id": "open", "label": "Renewal Open", "metadata": {"isClosed": "false", "probability": "0.5"}},
            {"id": "lost", "label": "Closed Lost", "metadata": {"isClosed": "true", "probability": "0.0"}},
        ]},
    ]
    run = make_run(
        root,
        "complex_lifecycle_demo",
        contacts=contacts,
        companies=companies,
        deals=deals,
        pipelines=pipelines,
        extra_contact_defs=[
            _definition("sales_motion", "Sales Motion"),
            _definition("account_tier", "Account Tier"),
            _definition("target_account", "Target Account"),
            _definition("partner_source", "Partner Source"),
            _definition("demo_request_status", "Demo Request Status"),
            _definition("engagement_score", "Engagement Score"),
        ],
        extra_company_defs=[_definition("account_tier", "Account Tier"), _definition("target_account", "Target Account")],
        extra_deal_defs=[
            _definition("sales_motion", "Sales Motion"),
            _definition("partner_source", "Partner Source"),
            {"name": "dealtype", "label": "Deal Type", "hubspotDefined": True},
            {"name": "engagement_score", "label": "Engagement Score", "hubspotDefined": True},
        ],
        assoc_contact_company=[
            {"from_id": "c1", "to_ids": ["co1"]}, {"from_id": "c2", "to_ids": ["co1"]},
            {"from_id": "c3", "to_ids": ["co2"]}, {"from_id": "c4", "to_ids": ["co2"]},
            {"from_id": "c5", "to_ids": ["co3"]}, {"from_id": "c6", "to_ids": ["co4"]},
            {"from_id": "c7", "to_ids": ["co5"]}, {"from_id": "c8", "to_ids": ["co1"]},
            {"from_id": "c9", "to_ids": ["co3"]}, {"from_id": "c10", "to_ids": ["co4"]},
        ],
        assoc_deal_company=[
            {"from_id": "d1", "to_ids": ["co1"]}, {"from_id": "d2", "to_ids": ["co1"]},
            {"from_id": "d3", "to_ids": ["co2"]}, {"from_id": "d4", "to_ids": ["co2"]},
            {"from_id": "d5", "to_ids": ["co3"]}, {"from_id": "d6", "to_ids": ["co4"]},
            {"from_id": "d7", "to_ids": ["co5"]},
            # d8 is deliberately missing its account association.
        ],
        assoc_deal_contact=[
            {"from_id": "d1", "to_ids": ["c1"]}, {"from_id": "d2", "to_ids": ["c8"]},
            {"from_id": "d3", "to_ids": ["c3"]}, {"from_id": "d4", "to_ids": ["c4"]},
            {"from_id": "d5", "to_ids": ["c5"]}, {"from_id": "d6", "to_ids": ["c6"]},
            {"from_id": "d7", "to_ids": ["c7"]}, {"from_id": "d8", "to_ids": ["c4"]},
        ],
    )
    raw = run / "raw"
    (raw / "automation").mkdir(parents=True, exist_ok=True)
    _write_json(raw / "forms.json", [
        {"guid": "form-demo", "name": "Demo request"},
        {"guid": "form-contact", "name": "Contact sales"},
        {"guid": "form-renewal", "name": "Renewal review"},
    ])
    _write_jsonl(raw / "form_submissions.jsonl", [
        {"id": "fs1", "form_guid": "form-demo", "submittedAt": demo_iso(7, day=11), "contact": {"vid": "c2"}, "pageUrl": "https://example.test/demo"},
        {"id": "fs2", "form_guid": "form-contact", "submittedAt": demo_iso(7, day=8), "contact": {"vid": "c1"}, "pageUrl": "https://example.test/contact-sales"},
        {"id": "fs3", "form_guid": "form-renewal", "submittedAt": demo_iso(6, day=8), "contact": {"vid": "c7"}, "pageUrl": "https://example.test/renewal"},
        {"id": "fs4", "form_guid": "form-demo", "submittedAt": demo_iso(7, day=12), "contact": {"vid": "c8"}, "pageUrl": "https://example.test/demo"},
    ])
    _write_jsonl(raw / "event_occurrences.jsonl", [
        {"id": "ev1", "objectId": "c1", "objectType": "contact", "eventType": "pricing_page_view", "occurredAt": demo_iso(6, day=20), "pageUrl": "https://example.test/pricing"},
        {"id": "ev2", "objectId": "c2", "objectType": "contact", "eventType": "demo_page_view", "occurredAt": demo_iso(7, day=10), "pageUrl": "https://example.test/demo"},
        {"id": "ev3", "objectId": "c4", "objectType": "contact", "eventType": "account_security_page_view", "occurredAt": demo_iso(6, day=2), "pageUrl": "https://example.test/security"},
        {"id": "ev4", "objectId": "c7", "objectType": "contact", "eventType": "renewal_page_view", "occurredAt": demo_iso(6, day=5), "pageUrl": "https://example.test/renewal"},
        {"id": "ev5", "objectId": "c9", "objectType": "contact", "eventType": "social_click", "occurredAt": demo_iso(7, day=12), "pageUrl": "https://example.test/product"},
    ])
    _write_jsonl(raw / "calls.jsonl", [
        {"id": "call1", "properties": {"hs_timestamp": demo_iso(6, day=22), "hs_call_status": "COMPLETED", "hs_call_direction": "INBOUND"}},
        {"id": "call2", "properties": {"hs_timestamp": demo_iso(6, day=12), "hs_call_status": "COMPLETED", "hs_call_direction": "OUTBOUND"}},
        {"id": "call3", "properties": {"hs_timestamp": demo_iso(7, day=10), "hs_call_status": "COMPLETED", "hs_call_direction": "INBOUND"}},
    ])
    _write_jsonl(raw / "emails.jsonl", [
        {"id": "email1", "properties": {"hs_timestamp": demo_iso(6, day=14), "hs_email_status": "REPLIED", "hs_email_direction": "INCOMING"}},
        {"id": "email2", "properties": {"hs_timestamp": demo_iso(6, day=10), "hs_email_status": "SENT", "hs_email_direction": "OUTGOING"}},
    ])
    _write_jsonl(raw / "tasks.jsonl", [
        {"id": "task1", "properties": {"hs_timestamp": demo_iso(6, day=15), "hs_task_status": "COMPLETED"}},
        {"id": "task2", "properties": {"hs_timestamp": demo_iso(6, day=12), "hs_task_status": "COMPLETED"}},
    ])
    _write_jsonl(raw / "meetings.jsonl", [])
    _write_jsonl(raw / "notes.jsonl", [])
    _write_jsonl(raw / "communications.jsonl", [])
    for activity in ("calls", "emails", "tasks", "meetings", "notes", "communications"):
        contact_rows = []
        deal_rows = []
        if activity == "calls":
            contact_rows = [{"from_id": "call1", "to_ids": ["c1"]}, {"from_id": "call2", "to_ids": ["c3"]}, {"from_id": "call3", "to_ids": ["c9"]}]
            deal_rows = [{"from_id": "call1", "to_ids": ["d1"]}, {"from_id": "call2", "to_ids": ["d3"]}]
        elif activity == "emails":
            contact_rows = [{"from_id": "email1", "to_ids": ["c3"]}, {"from_id": "email2", "to_ids": ["c4"]}]
            deal_rows = [{"from_id": "email1", "to_ids": ["d3"]}, {"from_id": "email2", "to_ids": ["d4"]}]
        elif activity == "tasks":
            contact_rows = [{"from_id": "task1", "to_ids": ["c3"]}, {"from_id": "task2", "to_ids": ["c4"]}]
            deal_rows = [{"from_id": "task1", "to_ids": ["d3"]}, {"from_id": "task2", "to_ids": ["d4"]}]
        _write_jsonl(raw / f"associations_{activity}_contacts.jsonl", contact_rows)
        _write_jsonl(raw / f"associations_{activity}_deals.jsonl", deal_rows)
    _write_json(raw / "campaigns.json", [{"id": "camp1", "name": "Q3 Demand Program"}, {"id": "camp2", "name": "Partner Launch"}])
    _write_json(raw / "campaign_assets.json", [{"id": "asset1"}, {"id": "asset2"}, {"id": "asset3"}])
    _write_json(raw / "campaign_metrics.json", [{"campaign_id": "camp1", "metric": "clicks", "value": 340}, {"campaign_id": "camp2", "metric": "responses", "value": 28}])
    _write_json(raw / "automation" / "workflows.json", [
        {"id": "wf-owner", "name": "Assign inbound owner", "isEnabled": False, "actions": [{"type": "PROPERTY_SET", "fields": {"hubspot_owner_id": "901"}}], "enrollmentCriteria": {"type": "contact"}},
        {"id": "wf-stage", "name": "Create deal after demo request", "isEnabled": True, "actions": [{"type": "PROPERTY_SET", "fields": {"dealstage": "qualified"}}], "enrollmentCriteria": {"type": "contact"}},
        {"id": "wf-score-a", "name": "Route high engagement", "isEnabled": True, "actions": [{"type": "PROPERTY_SET", "fields": {"engagement_score": "80"}}], "enrollmentCriteria": {"type": "contact"}},
        {"id": "wf-score-b", "name": "Route low engagement", "isEnabled": True, "actions": [{"type": "PROPERTY_SET", "fields": {"engagement_score": "20"}}], "enrollmentCriteria": {"type": "contact"}},
    ])
    _write_json(raw / "automation" / "workflow_performance.json", [
        {"workflow_id": "wf-owner", "series": "ENROLLED", "frequency": 31},
        {"workflow_id": "wf-owner", "series": "COMPLETED", "frequency": 0},
        {"workflow_id": "wf-stage", "series": "ENROLLED", "frequency": 8},
        {"workflow_id": "wf-stage", "series": "COMPLETED", "frequency": 3},
    ])
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    manifest["automation"] = {"status": "full", "performance_window": {"label": "90 days"}, "limitations": ["Synthetic execution counts are illustrative."]}
    (run / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return run, _expect(
        {"inbound_new_business": 45, "outbound_sales_led": 45, "abm_account_based": 45, "partner_led": 45, "expansion_renewal": 40},
        expected_primary_model="multi_motion",
        expected_measurement="deals_without_company",
        expected_findings=["deals_without_company", "active_deal_intent_without_escalation", "closed_lost_recovery_opportunity"],
    )


def scaled_mixed_motion_demo(root: Path) -> BuilderResult:
    """A larger mixed-motion fixture for cohort and report-scale validation.

    The executive report must summarize repeated breaks by account and retain
    only representative records in the page.  This fixture deliberately adds
    several accounts to each commercial lane, three unresolved deal/account
    relationships, and three post-loss re-qualification opportunities.
    """
    base_root = Path(root) / "_scaled_base"
    base_root.mkdir(parents=True, exist_ok=True)
    base, _ = complex_lifecycle_demo(base_root)
    run = Path(root) / "scaled_mixed_motion_demo"
    if run.exists():
        raise FileExistsError(run)
    base.rename(run)
    # The temporary builder root should never become a public fixture.
    base_root.rmdir()

    def read_jsonl(path: Path) -> list[dict[str, Any]]:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def append_jsonl(filename: str, rows: list[dict[str, Any]]) -> None:
        path = run / "raw" / filename
        existing = read_jsonl(path) if path.exists() else []
        _write_jsonl(path, existing + rows)

    def ts(month: int, day: int) -> str:
        return _iso(month, day=day, year=2026)

    names = [
        ("Elena", "Vega"), ("Marcus", "Lee"), ("Rina", "Das"), ("Owen", "Foster"),
        ("Hana", "Ito"), ("Victor", "Cole"), ("Amara", "Ndlovu"), ("Jon", "Bell"),
        ("Nadia", "Petrov"), ("Luis", "Santos"), ("Grace", "Wong"), ("Theo", "Bennett"),
        ("Iris", "Meyer"), ("Sam", "Okafor"), ("Mina", "Kaur"), ("Rafael", "Costa"),
        ("Chloe", "Grant"), ("Noah", "Reed"), ("Tara", "Singh"), ("Eli", "Hughes"),
    ]
    added_contacts: list[dict[str, Any]] = []
    for offset, (first, last) in enumerate(names, start=11):
        if offset <= 14:
            lifecycle, source, owner, extra = "salesqualifiedlead", "ORGANIC_SEARCH", "", {"demo_request_status": "submitted"}
        elif offset <= 18:
            lifecycle, source, owner, extra = "marketingqualifiedlead", "PAID_SEARCH", "901", {"demo_request_status": "submitted"}
        elif offset <= 21:
            lifecycle, source, owner, extra = "salesqualifiedlead", "", "901", {}
        elif offset <= 24:
            lifecycle, source, owner, extra = "salesqualifiedlead", "", "901", {}
        elif offset <= 27:
            lifecycle, source, owner, extra = "customer", "", "901", {"dealtype": "renewal"}
        else:
            lifecycle, source, owner, extra = "customer", "", "901", {}
        extra = {"firstname": first, "lastname": last, **extra}
        added_contacts.append(_contact(offset, (offset - 1) % 12 + 1, source=source, lifecycle=lifecycle, owner=owner, extra=extra))
    append_jsonl("contacts.jsonl", added_contacts)

    added_companies = [
        _company(6, "northwind.demo.test", "Northwind Labs"),
        _company(7, "atlas.demo.test", "Atlas Manufacturing"),
        _company(8, "summit.demo.test", "Summit Health"),
        _company(9, "brightline.demo.test", "Brightline Systems"),
        _company(10, "orbit.demo.test", "Orbit Security"),
        _company(11, "harbor.demo.test", "Harbor Logistics"),
        _company(12, "cedar.demo.test", "Cedar Partners"),
        _company(13, "lumen.demo.test", "Lumen Retail"),
        _company(14, "veridian.demo.test", "Veridian Group"),
        _company(15, "pioneer.demo.test", "Pioneer Energy"),
    ]
    append_jsonl("companies.jsonl", added_companies)

    added_deals = [
        _deal(9, 9, pipeline="inbound", stage="qualified", amount="27000", dealname="Inbound — Northwind Evaluation"),
        _deal(10, 10, pipeline="outbound", stage="discovery", amount="22000", dealname="Outbound — Atlas Discovery"),
        _deal(11, 11, pipeline="partner", stage="qualified", amount="14000", dealname="Partner — Summit Referral"),
        _deal(12, 12, pipeline="abm", stage="engaged", amount="31000", dealname="ABM — Unresolved Orbit"),
        _deal(13, 1, pipeline="abm", stage="engaged", amount="29000", dealname="ABM — Unresolved Harbor"),
        _deal(14, 2, pipeline="inbound", stage="qualified", amount="25000", dealname="Inbound — Unresolved Cedar"),
        _deal(15, 3, pipeline="renewal", stage="lost", amount="17000", dealname="Renewal — Lumen Revisit", closedate=ts(5, 18)),
        _deal(16, 4, pipeline="renewal", stage="lost", amount="19000", dealname="Renewal — Veridian Revisit", closedate=ts(5, 20)),
        _deal(17, 5, pipeline="renewal", stage="lost", amount="21000", dealname="Renewal — Pioneer Revisit", closedate=ts(5, 22)),
        _deal(18, 6, pipeline="renewal", stage="open", amount="26000", dealname="Expansion — Pioneer Growth"),
    ]
    append_jsonl("deals.jsonl", added_deals)

    append_jsonl("associations_contact_company.jsonl", [
        {"from_id": "c11", "to_ids": ["co6"]}, {"from_id": "c12", "to_ids": ["co6"]},
        {"from_id": "c13", "to_ids": ["co7"]}, {"from_id": "c14", "to_ids": ["co7"]},
        {"from_id": "c15", "to_ids": ["co8"]}, {"from_id": "c16", "to_ids": ["co8"]},
        {"from_id": "c17", "to_ids": ["co9"]}, {"from_id": "c18", "to_ids": ["co9"]},
        {"from_id": "c19", "to_ids": ["co10"]}, {"from_id": "c20", "to_ids": ["co11"]},
        {"from_id": "c21", "to_ids": ["co12"]},
        {"from_id": "c25", "to_ids": ["co13"]}, {"from_id": "c26", "to_ids": ["co14"]},
        {"from_id": "c27", "to_ids": ["co15"]}, {"from_id": "c28", "to_ids": ["co15"]},
        {"from_id": "c29", "to_ids": ["co6"]}, {"from_id": "c30", "to_ids": ["co7"]},
    ])
    append_jsonl("associations_deal_company.jsonl", [
        {"from_id": "d9", "to_ids": ["co10"]}, {"from_id": "d10", "to_ids": ["co11"]},
        {"from_id": "d11", "to_ids": ["co12"]}, {"from_id": "d15", "to_ids": ["co13"]},
        {"from_id": "d16", "to_ids": ["co14"]}, {"from_id": "d17", "to_ids": ["co15"]},
        {"from_id": "d18", "to_ids": ["co15"]},
    ])
    append_jsonl("associations_deal_contact.jsonl", [
        {"from_id": "d9", "to_ids": ["c19"]}, {"from_id": "d10", "to_ids": ["c20"]},
        {"from_id": "d11", "to_ids": ["c21"]}, {"from_id": "d12", "to_ids": ["c22"]},
        {"from_id": "d13", "to_ids": ["c23"]}, {"from_id": "d14", "to_ids": ["c24"]},
        {"from_id": "d15", "to_ids": ["c25"]}, {"from_id": "d16", "to_ids": ["c26"]},
        {"from_id": "d17", "to_ids": ["c27"]}, {"from_id": "d18", "to_ids": ["c28"]},
    ])

    raw = run / "raw"
    append_jsonl("form_submissions.jsonl", [
        {"id": f"fs-scaled-{i}", "form_guid": "form-demo", "submittedAt": ts(7, 10 + (i % 4)), "contact": {"vid": f"c{i}"}, "pageUrl": "https://example.test/demo"}
        for i in (11, 12, 13, 14, 15, 16, 17, 18, 19, 21)
    ] + [
        {"id": f"fs-scaled-renewal-{i}", "form_guid": "form-renewal", "submittedAt": ts(6, 10 + (i % 3)), "contact": {"vid": f"c{i}"}, "pageUrl": "https://example.test/renewal"}
        for i in (25, 26, 27)
    ])
    append_jsonl("event_occurrences.jsonl", [
        {"id": f"ev-scaled-{i}", "objectId": f"c{i}", "objectType": "contact", "eventType": "pricing_page_view", "occurredAt": ts(7, 8 + (i % 5)), "pageUrl": "https://example.test/pricing"}
        for i in (11, 13, 15, 17, 19, 20, 21, 22, 23, 24)
    ] + [
        {"id": f"ev-scaled-renewal-{i}", "objectId": f"c{i}", "objectType": "contact", "eventType": "renewal_page_view", "occurredAt": ts(6, 12 + (i % 3)), "pageUrl": "https://example.test/renewal"}
        for i in (25, 26, 27)
    ])

    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    manifest["run_id"] = "scaled_mixed_motion_demo"
    manifest["counts"] = {"contacts": 30, "companies": 15, "deals": 18}
    (run / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return run, _expect(
        {"inbound_new_business": 45, "outbound_sales_led": 45, "abm_account_based": 45, "partner_led": 45, "expansion_renewal": 40},
        expected_primary_model="multi_motion",
        expected_measurement="deals_without_company",
        expected_findings=["deals_without_company", "active_deal_intent_without_escalation", "closed_lost_recovery_opportunity"],
    )


LIFECYCLE_DATASETS: Dict[str, Callable[[Path], BuilderResult]] = {
    "clean_inbound_crm_sample": clean_inbound,
    "outbound_sales_led_sample": outbound_sales_led,
    "abm_sample": abm,
    "mixed_motion_scaleup_sample": mixed_motion,
    "partner_led_sample": partner_led,
    "expansion_renewal_sample": expansion_renewal,
    "legacy_property_sprawl_sample": legacy_property_sprawl,
    "broken_association_sample": broken_association,
    "pipeline_leakage_sample": pipeline_leakage,
    "complex_lifecycle_demo": complex_lifecycle_demo,
    "scaled_mixed_motion_demo": scaled_mixed_motion_demo,
}


def write_expectations(run_dir: Path, expectations: Dict[str, Any]) -> None:
    (Path(run_dir) / "expected_lifecycle_invariants.json").write_text(
        json.dumps(expectations, ensure_ascii=False, indent=2), encoding="utf-8"
    )
