"""Synthetic portals required by the lifecycle design contract."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Tuple

from .synthetic_datasets import _company, _contact, _deal, _iso, make_run

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
}


def write_expectations(run_dir: Path, expectations: Dict[str, Any]) -> None:
    (Path(run_dir) / "expected_lifecycle_invariants.json").write_text(
        json.dumps(expectations, ensure_ascii=False, indent=2), encoding="utf-8"
    )
