"""Timestamped lifecycle/deal stage transition analysis.

HubSpot stamps hs_v2_date_entered_<stage> (contacts/companies) and
hs(_v2)_date_entered_<stageId> (deals) whenever a record enters a stage.
These are the only direct evidence of actual stage TRANSITIONS in a snapshot
of current property values: without them, "this contact is a customer" says
nothing about whether it travelled a funnel or was set to customer in one
step. This module turns those timestamps into deterministic path facts.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .metrics import parse_ms

STAGE_ENTERED_V2 = "hs_v2_date_entered_"
STAGE_ENTERED_V1 = "hs_date_entered_"

# Standard HubSpot lifecycle funnel order; custom stages have no rank and are
# counted in paths but excluded from order/regression checks.
LIFECYCLE_FUNNEL_ORDER = [
    "subscriber",
    "lead",
    "marketingqualifiedlead",
    "salesqualifiedlead",
    "opportunity",
    "customer",
    "evangelist",
]
FUNNEL_RANK = {stage: rank for rank, stage in enumerate(LIFECYCLE_FUNNEL_ORDER)}
CUSTOMER_STATES = {"customer", "evangelist"}


def _props(record: Dict[str, Any]) -> Dict[str, Any]:
    return record.get("properties") or {}


def stage_entries(record: Dict[str, Any]) -> List[Tuple[str, float]]:
    """(stage, entered_ms) pairs sorted by entry time; v2 wins over v1."""
    by_stage: Dict[str, float] = {}
    for prefix in (STAGE_ENTERED_V1, STAGE_ENTERED_V2):  # v2 second: overwrites
        for field, value in _props(record).items():
            if not field.startswith(prefix):
                continue
            # hs_v2_date_entered_x also startswith-matches nothing for v1
            # prefix ("hs_date_entered_"), so no double counting.
            stage = field[len(prefix):].lower()
            ms = parse_ms(value)
            if stage and ms is not None:
                by_stage[stage] = ms
    return sorted(by_stage.items(), key=lambda item: item[1])


def _ranked(entries: List[Tuple[str, float]]) -> List[Tuple[int, float]]:
    return [(FUNNEL_RANK[stage], ms) for stage, ms in entries if stage in FUNNEL_RANK]


def analyze_contact_stages(contacts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministic lifecycle-path facts for contacts (aggregates + id lists)."""
    with_timestamps = 0
    multi_stage = 0
    ordered_progressions = 0
    mql_progressions = 0
    regression_ids: List[str] = []
    ranked_multi = 0
    customers_total = 0
    customers_without_path_ids: List[str] = []
    for contact in contacts:
        record_id = str(contact.get("id"))
        entries = stage_entries(contact)
        if entries:
            with_timestamps += 1
        if len(entries) >= 2:
            multi_stage += 1
        ranked = _ranked(entries)
        if len(ranked) >= 2:
            ranked_multi += 1
            ranks_by_time = [rank for rank, _ in sorted(ranked, key=lambda item: item[1])]
            if all(a <= b for a, b in zip(ranks_by_time, ranks_by_time[1:])):
                ordered_progressions += 1
                if any(stage == "marketingqualifiedlead" for stage, _ in entries):
                    mql_progressions += 1
            else:
                regression_ids.append(record_id)
        current = str(_props(contact).get("lifecyclestage") or "").lower()
        if current in CUSTOMER_STATES:
            customers_total += 1
            has_path = any(stage not in CUSTOMER_STATES for stage, _ in entries)
            if not has_path:
                customers_without_path_ids.append(record_id)
    return {
        "total": len(contacts),
        "with_stage_timestamps": with_timestamps,
        "multi_stage_paths": multi_stage,
        "ranked_multi_stage_paths": ranked_multi,
        "ordered_progressions": ordered_progressions,
        "mql_progressions": mql_progressions,
        "stage_regressions": len(regression_ids),
        "stage_regression_ids": regression_ids,
        "customers_total": customers_total,
        "customers_without_timestamped_path": len(customers_without_path_ids),
        "customers_without_timestamped_path_ids": customers_without_path_ids,
    }


def analyze_deal_stage_paths(deals: List[Dict[str, Any]]) -> Dict[str, Any]:
    with_timestamps = 0
    multi_stage = 0
    for deal in deals:
        entries = stage_entries(deal)
        if entries:
            with_timestamps += 1
        if len(entries) >= 2:
            multi_stage += 1
    return {
        "total": len(deals),
        "with_stage_timestamps": with_timestamps,
        "multi_stage_paths": multi_stage,
    }


def _without_ids(summary: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in summary.items() if not key.endswith("_ids")}


def build_stage_transition_summary(
    contacts: List[Dict[str, Any]],
    companies: List[Dict[str, Any]],
    deals: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Sanitized (aggregate-only) summary for the evidence store and agents."""
    contact_summary = analyze_contact_stages(contacts)
    company_summary = analyze_contact_stages(companies)
    deal_summary = analyze_deal_stage_paths(deals)
    available = any(
        summary["with_stage_timestamps"]
        for summary in (contact_summary, company_summary, deal_summary)
    )
    doc: Dict[str, Any] = {
        "available": available,
        "contacts": _without_ids(contact_summary),
        "companies": _without_ids(company_summary),
        "deals": deal_summary,
    }
    if not available:
        doc["limitation"] = (
            "No stage-entry timestamps in this snapshot; journey paths are "
            "inferred from record creation order only. Re-run the acquisition "
            "pass with the current connector to capture hs_v2_date_entered_* "
            "properties."
        )
    return doc
