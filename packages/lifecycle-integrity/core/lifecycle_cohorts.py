"""Build scalable, account-aware summaries for the executive report.

The evidence CSV remains record-complete.  The executive layer groups those
records into a small number of primary leakage cohorts so a large portal can
be read without expanding one long card per contact or deal.  A record is
assigned to the earliest observable break; secondary measurements remain on
the record row and do not inflate the cohort headline.
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from .metrics import load_association_map, read_json, read_jsonl
from .safety import csv_safe


UNRESOLVED_ACCOUNT = "Account relationship not identified"


def _props(row: dict[str, Any] | None) -> dict[str, Any]:
    value = row.get("properties") if isinstance(row, dict) else None
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[str]:
    return [row.strip() for row in str(value or "").split("||") if row.strip()]


def _amount(value: Any) -> tuple[str | None, Decimal | None]:
    text = str(value or "")
    match = re.search(r"\b([A-Z]{3})\s+([0-9,]+(?:\.[0-9]+)?)", text)
    if not match:
        return None, None
    try:
        return match.group(1), Decimal(match.group(2).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None, None


def _primary_break(row: dict[str, Any]) -> tuple[str, str, int]:
    lane = str(row.get("lane") or "")
    measurements = set(_items(row.get("measurement_ids")))
    if lane == "pre_deal":
        if any("without_owner" in item for item in measurements):
            return ("pre_deal_owner", "Sales-ready demand has no accountable owner", 1)
        return ("pre_deal_deal_path", "Sales-ready demand has no visible deal path", 2)
    if lane == "active_deal":
        if any("without_company" in item for item in measurements):
            return ("active_deal_account_link", "Open pipeline is not linked to an account", 3)
        return ("active_deal_follow_up", "Open pipeline has buyer intent without a visible next action", 4)
    if lane == "post_loss":
        return ("closed_lost_recovery", "Buyer intent returned after closed-lost without a recovery path", 5)
    return ("other", "Lifecycle exception requires review", 99)


def _cohort_label(key: str) -> str:
    return {
        "pre_deal_owner": "Demand reached sales readiness but was not assigned",
        "pre_deal_deal_path": "Demand showed buying intent but never entered a deal path",
        "active_deal_account_link": "Open deals are missing account continuity",
        "active_deal_follow_up": "Open deals received buyer intent without a visible follow-up",
        "closed_lost_recovery": "Buyer intent returned after closed-lost without a successor path",
        "other": "Other lifecycle exceptions",
    }.get(key, key.replace("_", " ").capitalize())


def _cohort_action(key: str, accounts: str, unresolved: int = 0) -> str:
    scope = f"{accounts} named account(s)"
    if unresolved:
        scope = f"{scope} and {unresolved} unresolved account relationship(s)"
    return {
        "pre_deal_owner": f"Sales leadership reviews the named contacts across {scope}, assigns the correct owner, and records the response SLA.",
        "pre_deal_deal_path": f"Sales leadership reviews the named accounts across {scope} and creates a deal or records a valid no-deal decision for each contact.",
        "active_deal_account_link": f"Deal owners confirm the correct account across {scope}; RevOps repairs only approved associations and checks downstream reporting.",
        "active_deal_follow_up": f"Deal owners review the buyer-signal timeline across {scope} and record the next action or a documented reason not to proceed.",
        "closed_lost_recovery": f"Account owners re-qualify the renewed demand across {scope}; create a successor path only when the new signal represents active commercial intent.",
        "other": "Review the named records and confirm the business rule before changing CRM configuration.",
    }.get(key, "Review the named records and confirm the business rule before changing CRM configuration.")


def _raw_company_context(run_dir: Path) -> dict[str, dict[str, Any]]:
    raw = Path(run_dir) / "raw"
    companies = {str(row.get("id")): row for row in read_jsonl(raw / "companies.jsonl") if isinstance(row, dict)}
    contact_company = load_association_map(raw, "associations_contact_company.jsonl") or {}
    deal_company = load_association_map(raw, "associations_deal_company.jsonl") or {}
    pipelines = read_json(raw / "pipelines.json", [])
    closed_stages: set[tuple[str, str]] = set()
    for pipeline in pipelines if isinstance(pipelines, list) else []:
        pipeline_id = str(pipeline.get("id") or "")
        for stage in pipeline.get("stages", []) if isinstance(pipeline, dict) else []:
            metadata = stage.get("metadata", {}) if isinstance(stage, dict) else {}
            if str(metadata.get("isClosed", "false")).lower() == "true":
                closed_stages.add((pipeline_id, str(stage.get("id") or "")))
    deals = {str(row.get("id")): row for row in read_jsonl(raw / "deals.jsonl") if isinstance(row, dict)}
    contact_ids: dict[str, set[str]] = defaultdict(set)
    deal_ids: dict[str, set[str]] = defaultdict(set)
    for contact_id, company_ids in contact_company.items():
        for company_id in company_ids:
            contact_ids[str(company_id)].add(str(contact_id))
    for deal_id, company_ids in deal_company.items():
        for company_id in company_ids:
            deal_ids[str(company_id)].add(str(deal_id))
    result: dict[str, dict[str, Any]] = {}
    for company_id, company in companies.items():
        props = _props(company)
        result[str(props.get("name") or company_id)] = {
            "company_id": company_id,
            "owner": props.get("hubspot_owner_id") or "Unassigned",
            "tier": props.get("account_tier") or props.get("tier") or "Not recorded",
            "lifecycle": props.get("lifecyclestage") or "Not recorded",
            "contact_count": len(contact_ids.get(company_id, set())),
            "deal_count": len(deal_ids.get(company_id, set())),
            "open_deal_count": sum(
                1
                for deal_id in deal_ids.get(company_id, set())
                if (str(_props(deals.get(deal_id)).get("pipeline")), str(_props(deals.get(deal_id)).get("dealstage"))) not in closed_stages
            ),
        }
    return result


def _representative_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def rank(row: dict[str, Any]) -> tuple[int, int, str]:
        _, amount = _amount(row.get("amount"))
        return (-(int(amount or 0)), -len(_items(row.get("evidence_timeline"))), str(row.get("record_reference") or ""))

    return sorted(rows, key=rank)[:3]


def build_account_cohorts(run_dir: Path, record_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate record evidence into account-level, human-readable cohorts."""
    company_context = _raw_company_context(Path(run_dir))
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in record_rows:
        account = str(row.get("account_name") or "").strip()
        if not account or account in {"Account unavailable", "No company association found"}:
            account = UNRESOLVED_ACCOUNT
        key, _, order = _primary_break(row)
        grouped[(key, account)].append(row)

    cohorts: dict[str, dict[str, Any]] = {}
    for (key, account), rows in grouped.items():
        group = cohorts.setdefault(
            key,
            {
                "cohort_id": key,
                "title": _cohort_label(key),
                "journey_order": _primary_break(rows[0])[2],
                "rows": [],
                "accounts": set(),
                "contacts": set(),
                "deals": set(),
                "amounts": defaultdict(Decimal),
                "pipelines": defaultdict(int),
                "unresolved_account_relationships": 0,
            },
        )
        group["rows"].extend(rows)
        group["accounts"].add(account)
        if account == UNRESOLVED_ACCOUNT:
            group["unresolved_account_relationships"] += len(rows)
        for row in rows:
            contact_name = str(row.get("contact_name") or "")
            deal_name = str(row.get("deal_name") or "")
            if contact_name and contact_name != "Contact unavailable":
                group["contacts"].add((account, contact_name))
            if row.get("record_type") == "Deal" and deal_name and deal_name != "No deal created":
                group["deals"].add((account, deal_name))
                currency, amount = _amount(row.get("amount"))
                if currency and amount is not None:
                    group["amounts"][currency] += amount
            pipeline = str(row.get("pipeline") or "").strip()
            if pipeline and pipeline != "No deal created":
                group["pipelines"][pipeline] += 1

    output: list[dict[str, Any]] = []
    for group in cohorts.values():
        key = str(group["cohort_id"])
        accounts = sorted(group["accounts"])
        sample_rows = _representative_rows(group["rows"])
        named_accounts = [account for account in accounts if account != UNRESOLVED_ACCOUNT]
        context = [company_context.get(account, {}) for account in named_accounts]
        account_count = len(named_accounts)
        contact_count = len(group["contacts"])
        deal_count = len(group["deals"])
        amount_text = " · ".join(
            f"{currency} {amount:,.2f}" for currency, amount in sorted(group["amounts"].items())
        ) or "No deal amount assigned"
        no_open_deal_accounts = sum(1 for item in context if item.get("deal_count", 0) == 0)
        open_deal_accounts = sum(1 for item in context if item.get("open_deal_count", 0) > 0)
        unowned_contacts = sum(1 for row in group["rows"] if str(row.get("owner") or "").lower() in {"", "unassigned", "none"})
        unassigned_accounts = sum(1 for item in context if str(item.get("owner") or "").lower() in {"", "unassigned", "none"})
        multiple_contact_accounts = sum(1 for item in context if item.get("contact_count", 0) > 1)
        pattern = (
            f"{contact_count} affected contact(s) across {account_count} account(s); "
            f"{deal_count} existing deal(s) are in this cohort."
        )
        unresolved = int(group["unresolved_account_relationships"])
        if key.startswith("pre_deal"):
            pattern = f"{contact_count} contact(s) across {account_count} named account(s) produced buyer-intent evidence but have no accountable next step into a deal path."
            if unresolved:
                pattern += f" {unresolved} record(s) cannot be rolled up to a named account from the available associations."
        elif key == "active_deal_account_link":
            pattern = f"{deal_count} open deal(s) cannot be tied directly to the account relationship used for reporting and routing."
            if account_count:
                pattern += f" {account_count} named account(s) remain in the affected population for comparison."
            if unresolved:
                pattern += f" {unresolved} deal/account relationship(s) cannot be resolved from the available associations."
        elif key == "active_deal_follow_up":
            pattern = f"{deal_count} open deal(s) across {account_count} account(s) received buyer intent without a later seller action in the available activity timeline."
        elif key == "closed_lost_recovery":
            pattern = f"{deal_count} closed-lost deal(s) across {account_count} account(s) show renewed buyer activity without a successor or re-engagement route."
        output.append(
            {
                "cohort_id": key,
                "title": group["title"],
                "journey_order": group["journey_order"],
                "status": "Recovery opportunity" if key == "closed_lost_recovery" else "Confirmed break",
                "account_count": account_count,
                "contact_count": contact_count,
                "deal_count": deal_count,
                "amount": amount_text,
                "no_open_deal_accounts": no_open_deal_accounts,
                "open_deal_accounts": open_deal_accounts,
                "unowned_contacts": unowned_contacts,
                "unassigned_accounts": unassigned_accounts,
                "multiple_contact_accounts": multiple_contact_accounts,
                "pipelines": [{"label": label, "count": count} for label, count in sorted(group["pipelines"].items(), key=lambda item: (-item[1], item[0]))],
                "pattern": pattern,
                "evidence_basis": list(dict.fromkeys(
                    item
                    for row in sample_rows
                    for item in (_items(row.get("why_this_record")) + _items(row.get("observed_break")))
                ))[:4],
                "action": _cohort_action(key, str(account_count), unresolved),
                "sample_rows": sample_rows,
                "all_record_count": len(group["rows"]),
                "account_names": named_accounts or [UNRESOLVED_ACCOUNT],
                "unresolved_account_relationships": unresolved,
            }
        )
    return sorted(output, key=lambda row: (int(row.get("journey_order", 99)), str(row.get("title"))))


def write_account_cohort_evidence(run_dir: Path, cohorts: Iterable[dict[str, Any]]) -> None:
    """Write a sanitized, shareable account-level evidence table."""
    path = Path(run_dir) / "report_account_evidence.csv"
    columns = [
        "cohort_id", "title", "status", "account_count", "contact_count", "deal_count",
        "amount", "no_open_deal_accounts", "unassigned_accounts", "multiple_contact_accounts",
        "unresolved_account_relationships",
        "pattern", "evidence_basis", "action", "account_names", "sample_record_references",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in cohorts:
            writer.writerow({
                "cohort_id": csv_safe(row.get("cohort_id", "")),
                "title": csv_safe(row.get("title", "")),
                "status": csv_safe(row.get("status", "")),
                "account_count": row.get("account_count", 0),
                "contact_count": row.get("contact_count", 0),
                "deal_count": row.get("deal_count", 0),
                "amount": row.get("amount", ""),
                "no_open_deal_accounts": row.get("no_open_deal_accounts", 0),
                "unassigned_accounts": row.get("unassigned_accounts", 0),
                "multiple_contact_accounts": row.get("multiple_contact_accounts", 0),
                "unresolved_account_relationships": row.get("unresolved_account_relationships", 0),
                "pattern": csv_safe(row.get("pattern", "")),
                "evidence_basis": csv_safe(" || ".join(row.get("evidence_basis", []))),
                "action": csv_safe(row.get("action", "")),
                "account_names": csv_safe(" || ".join(row.get("account_names", []))),
                "sample_record_references": csv_safe(" || ".join(str(item.get("record_reference") or "") for item in row.get("sample_rows", []))),
            })
