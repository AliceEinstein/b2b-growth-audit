"""Build record-level, human-facing lifecycle evidence.

The agent boundary remains hash-only. This module runs locally after the
deterministic measurements and reviewer consolidation. It joins those hashes
back to the minimum business context an executive needs to act: account,
contact/deal name, owner, amount, dated signal chain, observed break, and
configuration evidence. It never emits email addresses, phone numbers, note
or message bodies. The local HTML/Markdown view may carry HubSpot record URLs
when a portal ID is available; the shareable evidence CSV remains hash-only.
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from .metrics import load_association_map, parse_ms, read_json, read_jsonl
from .safety import csv_safe
from .sanitizer import hash_record_id, load_or_create_salt, sanitize_untrusted_value

REPORT_EVIDENCE_COLUMNS = [
    "journey_order",
    "lane",
    "status",
    "record_reference",
    "record_type",
    "account_name",
    "contact_name",
    "deal_name",
    "pipeline",
    "stage",
    "owner",
    "amount",
    "why_this_record",
    "evidence_timeline",
    "observed_break",
    "commercial_consequence",
    "automation_evidence",
    "recommended_action",
    "last_signal_at",
    "measurement_ids",
    "trace",
]

_JOURNEY_ORDER = {"pre_deal": 1, "active_deal": 2, "post_loss": 3}
_SELLER_SOURCES = {"tasks", "meetings", "notes"}
_ACTIVITY_SOURCES = _SELLER_SOURCES | {"calls", "emails", "communications"}


def _props(row: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    value = row.get("properties")
    return value if isinstance(value, dict) else {}


def _safe_business_label(value: Any, fallback: str) -> str:
    """Keep a useful local label while neutralising PII-shaped free text."""
    if value in (None, ""):
        return fallback
    sanitized = sanitize_untrusted_value(str(value))
    if not sanitized:
        return fallback
    if sanitized.startswith("[REDACTED:"):
        return sanitized
    marker = "[CRM_FIELD_VALUE:UNTRUSTED_DATA_ONLY] "
    while sanitized.startswith(marker):
        sanitized = sanitized[len(marker) :].lstrip()
    sanitized = re.sub(r"[\x00-\x1f\x7f]", " ", sanitized).strip()
    return sanitized[:160] or fallback


def _datetime(value: Any) -> datetime | None:
    parsed = parse_ms(value)
    if parsed is None:
        return None
    return datetime.fromtimestamp(parsed / 1000, tz=timezone.utc)


def _date_text(value: Any) -> str:
    parsed = _datetime(value)
    return parsed.strftime("%d %b %Y") if parsed else "Date unavailable"


def _audit_datetime(view: dict[str, Any]) -> datetime:
    generated = str(view.get("generated") or "")
    try:
        return datetime.strptime(generated, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    parsed = _datetime(view.get("generated"))
    return parsed or datetime.now(timezone.utc)


def _amount_text(props: dict[str, Any], portal_currency: str | None) -> str:
    raw_amount = props.get("amount")
    if raw_amount in (None, ""):
        return "No amount recorded"
    try:
        amount = Decimal(str(raw_amount).replace(",", ""))
    except (InvalidOperation, ValueError):
        return "Amount unavailable"
    currency = (
        props.get("hs_currency")
        or props.get("deal_currency_code")
        or props.get("currency")
        or props.get("currency_code")
        or portal_currency
    )
    if not currency:
        return "Amount withheld — currency unavailable"
    return f"{str(currency).upper()} {amount:,.2f}"


def _owner_labels(raw: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    for row in read_json(raw / "owners.json", []):
        if not isinstance(row, dict):
            continue
        owner_id = row.get("id") or row.get("userId") or row.get("user_id")
        if owner_id in (None, ""):
            continue
        name = " ".join(
            str(value).strip()
            for value in (row.get("firstName"), row.get("lastName"))
            if value not in (None, "")
        )
        labels[str(owner_id)] = _safe_business_label(name, f"Owner {str(owner_id)[-4:]}")
    return labels


def _portal_currency(raw: Path, manifest: dict[str, Any]) -> str | None:
    account_info = read_json(raw / "account_info.json", {})
    for candidate in (
        manifest.get("portal_currency"),
        manifest.get("account_currency"),
        account_info.get("currency"),
        account_info.get("currencyCode"),
        account_info.get("currency_code"),
    ):
        if candidate not in (None, ""):
            return str(candidate).upper()
    return None


def _portal_id(raw: Path) -> str | None:
    account_info = read_json(raw / "account_info.json", {})
    candidate = account_info.get("portal_id") or account_info.get("portalId")
    value = str(candidate or "").strip()
    return value if re.fullmatch(r"\d+", value) else None


def _hubspot_record_url(portal_id: str | None, object_type_id: str, record_id: Any) -> str:
    record = str(record_id or "").strip()
    if not portal_id or not record:
        return ""
    return f"https://app.hubspot.com/contacts/{quote(portal_id, safe='')}/record/{object_type_id}/{quote(record, safe='')}"


def _contact_name(contact: dict[str, Any] | None, reference: str) -> str:
    props = _props(contact)
    name = " ".join(
        str(value).strip()
        for value in (props.get("firstname"), props.get("lastname"))
        if value not in (None, "")
    )
    return _safe_business_label(name, f"Contact {reference[-8:]}")


def _lifecycle_label(value: Any) -> str:
    labels = {
        "lead": "Lead",
        "marketingqualifiedlead": "Marketing-qualified lead",
        "salesqualifiedlead": "Sales-qualified lead",
        "opportunity": "Opportunity",
        "customer": "Customer",
        "evangelist": "Evangelist",
    }
    text = str(value or "").lower().replace("_", "")
    return labels.get(text, _safe_business_label(value, "Lifecycle stage unavailable"))


def _signal_map(run_dir: Path) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    path = Path(run_dir) / "processed" / "intent_signal_store.jsonl"
    if not path.exists():
        return index
    for row in read_jsonl(path):
        if not isinstance(row, dict):
            continue
        for record_hash in (row.get("deal_id_hashes") or []) + (row.get("contact_id_hashes") or []):
            index[str(record_hash)].append(row)
    return index


def _dedupe_signals(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        if _datetime(row.get("occurred_at")) is None:
            continue
        key = (
            str(row.get("source") or ""),
            str(row.get("signal_type") or ""),
            str(row.get("occurred_at") or ""),
            str(row.get("event_label") or ""),
        )
        unique[key] = row
    return sorted(unique.values(), key=lambda row: _datetime(row.get("occurred_at")) or datetime.min.replace(tzinfo=timezone.utc))


def _signal_role(row: dict[str, Any]) -> str:
    source = str(row.get("source") or "").lower()
    direction = str(row.get("direction") or "").lower()
    status = str(row.get("status") or "").lower()
    signal_type = str(row.get("signal_type") or "").lower()
    if source in {"forms", "events"}:
        return "buyer"
    if "inbound" in direction or "incoming" in direction or "reply" in status or "reply" in signal_type:
        return "buyer"
    if source in _SELLER_SOURCES or "outbound" in direction or "outgoing" in direction:
        return "seller"
    if source == "communications":
        return "seller" if "out" in direction else "unknown"
    return "unknown"


def _signal_text(row: dict[str, Any]) -> str:
    source = str(row.get("source") or "activity").lower()
    signal_type = str(row.get("signal_type") or source).replace("_", " ")
    label = _safe_business_label(row.get("event_label"), signal_type)
    direction = str(row.get("direction") or "").lower()
    strength = str(row.get("signal_strength") or "unknown").lower()
    role = _signal_role(row)
    if source == "forms":
        action = f"HubSpot form: {label} submitted"
    elif source == "events":
        action = label
    elif source == "calls":
        action = f"{direction + ' ' if direction not in {'', 'unknown'} else ''}connected call"
    elif source == "emails":
        action = "incoming email reply" if role == "buyer" else "outbound email"
    elif source == "tasks":
        action = "sales task completed"
    elif source == "meetings":
        action = "meeting activity"
    else:
        action = label
    role_text = {
        "buyer": f"{strength} buyer-intent evidence",
        "seller": "sales follow-up",
        "unknown": f"{strength} record-linked activity",
    }[role]
    return f"{_date_text(row.get('occurred_at'))} — {action} ({role_text})"


def _is_reportable(measurement_id: str) -> bool:
    return any(
        (
            measurement_id.endswith("high_intent_contacts_without_owner"),
            measurement_id.endswith("high_intent_contacts_without_deal"),
            measurement_id == "intent_signals_without_deal",
            measurement_id == "deals_without_company",
            measurement_id.endswith("deals_without_company"),
            measurement_id == "active_deal_intent_without_escalation",
            measurement_id == "closed_lost_recovery_opportunity",
        )
    )


def _owner_gap(measurements: set[str]) -> bool:
    return any(row.endswith("high_intent_contacts_without_owner") for row in measurements)


def _no_deal_gap(measurements: set[str]) -> bool:
    return any(row.endswith("high_intent_contacts_without_deal") for row in measurements) or "intent_signals_without_deal" in measurements


def _association_gap(measurements: set[str]) -> bool:
    return any(row == "deals_without_company" or row.endswith("deals_without_company") for row in measurements)


def _status_for_measurements(measurements: set[str], finding_statuses: dict[str, str]) -> str:
    if "closed_lost_recovery_opportunity" in measurements:
        return "Recovery opportunity"
    if any(finding_statuses.get(row) in {"approved", "revised"} for row in measurements):
        return "Confirmed break"
    if any(finding_statuses.get(row) == "observation" for row in measurements):
        return "Monitor"
    return "Review candidate"


def _record_reference(object_type: str, record_hash: str) -> str:
    prefix = "DEAL" if object_type == "deals" else "CONTACT"
    return f"{prefix}-{record_hash[:8].upper()}"


def _workflow_name(row: dict[str, Any]) -> str:
    return _safe_business_label(row.get("workflow_name_redacted"), str(row.get("workflow_alias") or "Workflow"))


def _workflow_performance(row: dict[str, Any], window: str) -> str:
    performance = row.get("performance") if isinstance(row.get("performance"), dict) else {}
    enrolled = int(performance.get("enrolled", 0) or 0)
    completed = int(performance.get("completed", 0) or 0)
    return f"{window}: {enrolled} enrolled, {completed} completed"


def _field_label(value: Any) -> str:
    return {
        "hubspot_owner_id": "HubSpot property: Contact owner",
        "dealstage": "HubSpot property: Deal stage",
        "engagement_score": "HubSpot property: Engagement score",
    }.get(
        str(value or ""),
        f"HubSpot property: {str(value or 'Undisclosed field').replace('_', ' ').strip().title()}",
    )


def _automation_diagnosis(
    measurements: set[str],
    workflows: list[dict[str, Any]],
    automation_doc: dict[str, Any],
    coverage: dict[str, Any],
    signals: list[dict[str, Any]],
) -> str:
    status = str(coverage.get("status") or "unavailable")
    if status not in {"full", "partial", "available"}:
        return "Automation configuration was unavailable, so the audit cannot name a workflow cause."
    aliases = {str(row.get("workflow_alias")): row for row in workflows if row.get("workflow_alias")}
    links = {
        str(row.get("measurement_id")): row
        for row in automation_doc.get("root_cause_links", [])
        if isinstance(row, dict) and row.get("measurement_id")
    }
    window = str((coverage.get("performance_window") or {}).get("label") or "Available aggregate window")
    statements: list[str] = []

    if _owner_gap(measurements):
        linked_aliases = []
        for measurement_id in measurements:
            linked_aliases.extend(links.get(measurement_id, {}).get("workflow_aliases") or [])
        for alias in dict.fromkeys(str(row) for row in linked_aliases):
            workflow = aliases.get(alias)
            if not workflow:
                continue
            enabled = "enabled" if workflow.get("is_enabled") else "disabled"
            statements.append(
                f"Workflow: {_workflow_name(workflow)} ({alias}) is {enabled}; {_workflow_performance(workflow, window)}. "
                "Its configured field action targets HubSpot property: Contact owner. This can explain an ownership gap, but the snapshot does not prove this record enrolled."
            )

    if _no_deal_gap(measurements):
        deal_workflows = [row for row in workflows if re.search(r"create\s+deal|deal\s+creation", _workflow_name(row), re.I)]
        signal_labels = " ".join(
            f"{row.get('event_label') or ''} {row.get('signal_type') or ''}"
            for row in signals
            if _signal_role(row) == "buyer"
        ).lower()
        demo_signal_present = "demo" in signal_labels
        if deal_workflows:
            for workflow in deal_workflows[:2]:
                alias = str(workflow.get("workflow_alias") or "Workflow")
                fields = sorted(
                    str(write.get("field"))
                    for write in (workflow.get("action_writes") or [])
                    if isinstance(write, dict) and write.get("field")
                )
                field_text = ", ".join(_field_label(field) for field in fields) or "no visible field write"
                enabled = "enabled" if workflow.get("is_enabled") else "disabled"
                if demo_signal_present:
                    statements.append(
                        f"Workflow: {_workflow_name(workflow)} ({alias}) is {enabled}; {_workflow_performance(workflow, window)}. "
                        f"The workflow's visible action list shows a configured field action targeting {field_text} but no create-deal action. Verify this record's workflow history before treating the workflow as the cause."
                    )
                else:
                    statements.append(
                        f"Workflow: {_workflow_name(workflow)} ({alias}) is the only visible deal-creation candidate, but this record's qualifying signal is not a demo request, so that workflow does not appear applicable. No other deal-creation workflow was found in the available inventory."
                    )
        elif status == "full":
            statements.append("No workflow with a visible deal-creation purpose was found in the complete workflow inventory; a manual process may still exist.")

    if "active_deal_intent_without_escalation" in measurements:
        scoring_workflows = [
            row for row in workflows
            if re.search(r"intent|engagement|score", _workflow_name(row), re.I)
        ]
        if scoring_workflows:
            names = ", ".join(
                f"Workflow: {_workflow_name(row)} ({row.get('workflow_alias')})"
                for row in scoring_workflows[:3]
            )
            fields = sorted(
                {
                    str(write.get("field"))
                    for row in scoring_workflows
                    for write in (row.get("action_writes") or [])
                    if isinstance(write, dict) and write.get("field")
                }
            )
            statements.append(
                f"The only workflows related to engagement are {names}; their configured field actions target {', '.join(_field_label(field) for field in fields) or 'no disclosed field'}. "
                "Neither shows a task, notification, owner, or deal action, so there is no visible automated handoff from engagement score to seller action. This does not prove either workflow failed on this deal."
            )
        elif status == "full":
            statements.append("No workflow that visibly turns a new buyer signal into a task, notification, owner handoff, or deal action was found in the complete inventory.")

    if _association_gap(measurements):
        association_workflows = [
            row for row in workflows
            if any(
                re.search(r"company|association", str(write.get("field") or ""), re.I)
                for write in (row.get("action_writes") or [])
                if isinstance(write, dict)
            )
        ]
        if not association_workflows and status == "full":
            statements.append("No workflow with a visible company-association action was found in the complete inventory; the association may be maintained manually or by another integration.")

    if "closed_lost_recovery_opportunity" in measurements:
        recovery_workflows = [
            row for row in workflows
            if re.search(r"closed.?lost|recover|re.?engage|win.?back|reactivat", _workflow_name(row), re.I)
        ]
        if recovery_workflows:
            statements.append(
                "Matching recovery configuration: "
                + ", ".join(f"Workflow: {_workflow_name(row)} ({row.get('workflow_alias')})" for row in recovery_workflows[:3])
                + ". Per-record execution is not available."
            )
        elif status == "full":
            statements.append("No closed-lost recovery or re-engagement workflow was found in the complete workflow inventory; a manual recovery process may still exist.")

    return " || ".join(dict.fromkeys(statements)) or "No configuration evidence was specific enough to support a workflow diagnosis for this record."


def _join_items(items: Iterable[str]) -> str:
    return " || ".join(dict.fromkeys(item.strip() for item in items if item and item.strip()))


def build_report_record_evidence(run_dir: Path, view: dict[str, Any]) -> list[dict[str, Any]]:
    """Join hashed findings to local records and calculate a defensible evidence chain."""
    run_dir = Path(run_dir)
    raw = run_dir / "raw"
    manifest = read_json(run_dir / "manifest.json", {})
    salt = load_or_create_salt(run_dir)
    contacts = {str(row.get("id")): row for row in read_jsonl(raw / "contacts.jsonl")}
    companies = {str(row.get("id")): row for row in read_jsonl(raw / "companies.jsonl")}
    deals = {str(row.get("id")): row for row in read_jsonl(raw / "deals.jsonl")}
    deal_company = load_association_map(raw, "associations_deal_company.jsonl") or {}
    deal_contact = load_association_map(raw, "associations_deal_contact.jsonl") or {}
    contact_company = load_association_map(raw, "associations_contact_company.jsonl") or {}
    # Invert once instead of scanning every deal association for every
    # contact. This keeps report generation linear in the association count.
    contact_deals: dict[str, list[str]] = {contact_id: [] for contact_id in contacts}
    for deal_id, contact_ids in deal_contact.items():
        for contact_id in contact_ids or []:
            contact_id = str(contact_id)
            if contact_id in contact_deals:
                contact_deals[contact_id].append(str(deal_id))
    owners = _owner_labels(raw)
    portal_currency = _portal_currency(raw, manifest)
    portal_id = _portal_id(raw)
    audit_at = _audit_datetime(view)
    signal_index = _signal_map(run_dir)

    pipeline_summary = read_json(run_dir / "processed" / "pipeline_summary.json", {})
    pipeline_labels = {
        str(row.get("pipeline_id")): _safe_business_label(row.get("label"), str(row.get("pipeline_id") or "Unknown pipeline"))
        for row in pipeline_summary.get("pipelines", [])
    }
    stage_labels = {
        (str(pipeline.get("pipeline_id")), str(stage.get("stage_id"))): _safe_business_label(stage.get("label"), str(stage.get("stage_id") or "Unknown stage"))
        for pipeline in pipeline_summary.get("pipelines", [])
        for stage in pipeline.get("stages", [])
    }
    finding_statuses = {
        str(row.get("finding_id")): str(row.get("review_status"))
        for row in view.get("findings", [])
    }
    workflows = read_json(run_dir / "processed" / "workflow_inventory.json", [])
    if not isinstance(workflows, list):
        workflows = []
    automation_doc = read_json(run_dir / "processed" / "automation_scoring_measurements.json", {})
    automation_coverage = read_json(run_dir / "processed" / "automation_coverage.json", manifest.get("automation") or {})

    hash_lookup: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
    for object_type, records in (("contacts", contacts), ("deals", deals)):
        for raw_id, record in records.items():
            hash_lookup[(object_type, hash_record_id(object_type, raw_id, salt))] = (raw_id, record)

    evidence_path = run_dir / "evidence.csv"
    if not evidence_path.exists():
        return []
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    with evidence_path.open(encoding="utf-8", newline="") as fh:
        for evidence in csv.DictReader(fh):
            measurement_id = str(evidence.get("finding_id") or "")
            object_type = str(evidence.get("object_type") or "")
            record_hash = str(evidence.get("record_id_hash") or "")
            if not _is_reportable(measurement_id) or object_type not in {"contacts", "deals"}:
                continue
            matched = hash_lookup.get((object_type, record_hash))
            if not matched:
                continue
            raw_id, _ = matched
            primary_type, primary_id = object_type, raw_id
            source_contact_ids: set[str] = set()
            if object_type == "contacts":
                source_contact_ids.add(raw_id)
                associated_deals = contact_deals.get(raw_id, [])
                if len(associated_deals) == 1 and not _no_deal_gap({measurement_id}):
                    primary_type, primary_id = "deals", associated_deals[0]
            else:
                source_contact_ids.update(str(row) for row in deal_contact.get(raw_id, []) or [])
            group = groups.setdefault(
                (primary_type, primary_id),
                {
                    "primary_type": primary_type,
                    "primary_id": primary_id,
                    "measurement_ids": set(),
                    "contact_ids": set(),
                    "traces": set(),
                },
            )
            group["measurement_ids"].add(measurement_id)
            group["contact_ids"].update(source_contact_ids)
            group["traces"].add(f"evidence.csv#finding_id={measurement_id}")

    output: list[dict[str, Any]] = []
    for group in groups.values():
        primary_type = str(group["primary_type"])
        primary_id = str(group["primary_id"])
        measurements = set(group["measurement_ids"])
        deal = deals.get(primary_id) if primary_type == "deals" else None
        contact = contacts.get(primary_id) if primary_type == "contacts" else None
        if deal:
            group["contact_ids"].update(str(row) for row in deal_contact.get(primary_id, []) or [])
        contact_ids = sorted(str(row) for row in group["contact_ids"] if str(row) in contacts)
        primary_contact = contacts.get(contact_ids[0]) if contact_ids else contact

        primary_hash = hash_record_id(primary_type, primary_id, salt)
        record_reference = _record_reference(primary_type, primary_hash)
        contact_reference = _record_reference("contacts", hash_record_id("contacts", contact_ids[0], salt)) if contact_ids else record_reference
        contact_name = _contact_name(primary_contact, contact_reference)

        direct_company_ids = list(deal_company.get(primary_id, []) or []) if deal else list(contact_company.get(primary_id, []) or [])
        inferred_company_ids: list[str] = []
        if deal and not direct_company_ids:
            for contact_id in contact_ids:
                inferred_company_ids.extend(str(row) for row in contact_company.get(contact_id, []) or [])
        company_ids = list(dict.fromkeys(str(row) for row in direct_company_ids + inferred_company_ids))
        company = companies.get(company_ids[0]) if company_ids else None
        account_name = _safe_business_label(
            _props(company).get("name") if company else None,
            "No company association found" if deal else "Account unavailable",
        )
        company_id = company_ids[0] if company_ids and company_ids[0] in companies else ""

        deal_props = _props(deal)
        contact_props = _props(primary_contact)
        deal_name = _safe_business_label(
            deal_props.get("dealname") if deal else None,
            "No deal created" if not deal else f"Unnamed deal ({record_reference})",
        )
        pipeline_id = str(deal_props.get("pipeline") or "") if deal else ""
        stage_id = str(deal_props.get("dealstage") or "") if deal else ""
        pipeline = pipeline_labels.get(pipeline_id, _safe_business_label(pipeline_id, "No deal created")) if deal else "No deal created"
        stage = stage_labels.get((pipeline_id, stage_id), _safe_business_label(stage_id, "Stage unavailable")) if deal else "No deal stage"
        owner_id = str(deal_props.get("hubspot_owner_id") or "") if deal else str(contact_props.get("hubspot_owner_id") or "")
        owner = owners.get(owner_id, "Unassigned") if owner_id else "Unassigned"
        contact_owner_id = str(contact_props.get("hubspot_owner_id") or "")
        contact_owner = owners.get(contact_owner_id, "Unassigned") if contact_owner_id else "Unassigned"
        amount = _amount_text(deal_props, portal_currency) if deal else "No amount assigned — no deal exists"

        signal_rows: list[dict[str, Any]] = list(signal_index.get(primary_hash, []))
        for contact_id in contact_ids:
            signal_rows.extend(signal_index.get(hash_record_id("contacts", contact_id, salt), []))
        signals = _dedupe_signals(signal_rows)
        all_buyer_signals = [row for row in signals if _signal_role(row) == "buyer"]
        buyer_signals = [row for row in all_buyer_signals if row.get("signal_strength") in {"high", "medium"}]
        seller_signals = [row for row in signals if _signal_role(row) == "seller"]
        latest_signal = signals[-1] if signals else None
        latest_buyer = buyer_signals[-1] if buyer_signals else None
        latest_buyer_at = _datetime(latest_buyer.get("occurred_at")) if latest_buyer else None
        seller_after = [row for row in seller_signals if latest_buyer_at and (_datetime(row.get("occurred_at")) or audit_at) > latest_buyer_at]
        close_at = _datetime(deal_props.get("closedate")) if deal else None
        post_loss_buyer = [row for row in buyer_signals if close_at and (_datetime(row.get("occurred_at")) or close_at) > close_at]
        post_loss_buyer_context = [row for row in all_buyer_signals if close_at and (_datetime(row.get("occurred_at")) or close_at) > close_at]
        post_loss_seller = [row for row in seller_signals if close_at and (_datetime(row.get("occurred_at")) or close_at) > close_at]

        why: list[str] = []
        timeline: list[str] = []
        breaks: list[str] = []
        consequences: list[str] = []
        actions: list[str] = []

        if not deal:
            stage_label = _lifecycle_label(contact_props.get("lifecyclestage"))
            signal_reason = "; ".join(_signal_text(row) for row in buyer_signals[-3:]) or "no dated buyer signal was available"
            why.append(f"{contact_name} is recorded as {stage_label} and produced record-linked high/medium intent: {signal_reason}.")
            timeline.extend(_signal_text(row) for row in all_buyer_signals[-5:])
            if _owner_gap(measurements) and contact_owner == "Unassigned":
                breaks.append(f"As of {audit_at.strftime('%d %b %Y')}, the contact has no HubSpot owner.")
            if _no_deal_gap(measurements):
                breaks.append(f"As of {audit_at.strftime('%d %b %Y')}, HubSpot shows no associated deal for this contact.")
            consequences.append("The contact produced sales-ready signals but never entered a traceable deal path. This is recoverable demand, not booked pipeline; no amount is assigned.")
            decision_owner = contact_owner if contact_owner != "Unassigned" else "Sales manager"
            actions.append(f"{decision_owner} reviews {contact_name}, decides whether to create a deal or record a valid no-deal decision, and documents the reason.")
        else:
            if "active_deal_intent_without_escalation" in measurements:
                signal_reason = _signal_text(latest_buyer) if latest_buyer else "No dated buyer signal available"
                why.append(f"{deal_name} is an open {stage} deal worth {amount}. The latest qualifying buyer signal was {signal_reason}.")
                timeline.extend(_signal_text(row) for row in (buyer_signals + seller_signals)[-6:])
                if latest_buyer_at and not seller_after:
                    gap_days = max(0, (audit_at.date() - latest_buyer_at.date()).days)
                    breaks.append(f"No later outbound call, email, task, meeting, or other sales follow-up is recorded after {_date_text(latest_buyer.get('occurred_at'))}; the visible response gap is {gap_days} day{'s' if gap_days != 1 else ''}.")
                elif latest_buyer_at:
                    breaks.append("A later sales activity exists, so this record requires reviewer confirmation rather than a no-response claim.")
                consequences.append(f"{amount} of actual open pipeline is exposed to follow-up delay. This is review exposure, not a forecast loss.")
                actions.append(f"{owner} reviews {deal_name}, confirms the response to the {_date_text(latest_buyer.get('occurred_at')) if latest_buyer else 'latest'} buyer signal, and records the next step or a valid reason not to proceed.")
            if _association_gap(measurements):
                why.append(f"{deal_name} is an open {stage} deal worth {amount}, but its direct deal-to-company association is absent.")
                if signals:
                    timeline.extend(_signal_text(row) for row in signals[-4:])
                inferred_text = f" The account name {account_name} is inferred through an associated contact; it is not a direct deal-company link." if inferred_company_ids else " No account could be inferred from associated contacts."
                breaks.append(f"HubSpot has no direct company association for this deal.{inferred_text}")
                consequences.append(f"The {amount} deal can be omitted from account-level ABM reporting, routing, and buying-group continuity even though it remains open pipeline.")
                actions.append(f"{owner} confirms whether {account_name} is the correct account for {deal_name}; RevOps changes the association only after that confirmation.")
            if _owner_gap(measurements) and primary_contact:
                why.append(f"The buying contact {contact_name} is linked to {deal_name}, but the contact owner field is empty.")
                breaks.append(f"The deal owner is {owner}, while the associated buying contact is unassigned; ownership continuity is incomplete across the handoff.")
                actions.append(f"{owner} confirms who should own {contact_name}; RevOps records the approved ownership rule before changing the contact.")
            if "closed_lost_recovery_opportunity" in measurements:
                why.clear()
                timeline.clear()
                breaks.clear()
                consequences.clear()
                actions.clear()
                post_loss_text = "; ".join(_signal_text(row) for row in post_loss_buyer[-4:]) or "No dated post-loss buyer signal available"
                days_after = None
                if close_at and post_loss_buyer:
                    first_post_loss = _datetime(post_loss_buyer[0].get("occurred_at"))
                    if first_post_loss:
                        days_after = max(0, (first_post_loss.date() - close_at.date()).days)
                why.append(
                    f"{deal_name} closed lost on {_date_text(deal_props.get('closedate'))}. New high/medium buyer activity appeared{f' {days_after} days later' if days_after is not None else ' after close'}: {post_loss_text}."
                )
                timeline.append(f"{_date_text(deal_props.get('closedate'))} — deal moved to Closed Lost")
                timeline.extend(_signal_text(row) for row in post_loss_buyer_context[-5:])
                breaks.append("No open successor deal linked through the same company/contact and no post-loss sales call, email, task, or meeting is visible in the available record-linked evidence.")
                consequences.append(f"This record qualifies for re-qualification because buyer activity resumed after the loss. {amount} is historical context only; it is not recoverable revenue or open pipeline.")
                actions.append(f"{owner} reviews the post-loss signal for {deal_name}, confirms whether the account has renewed commercial intent, and creates a successor path only if the opportunity is re-qualified.")

        automation_evidence = _automation_diagnosis(measurements, workflows, automation_doc, automation_coverage, signals)
        aliases_mentioned = sorted(set(re.findall(r"WF-\d+", automation_evidence)))
        if aliases_mentioned and "does not appear applicable" not in automation_evidence:
            actions.append(f"RevOps checks this record's execution history for {', '.join(aliases_mentioned)} before changing any workflow configuration.")
        if not timeline:
            timeline.append("No record-linked signal timeline was available; the finding rests on the CRM relationship state shown above.")

        lane = "post_loss" if "closed_lost_recovery_opportunity" in measurements else "active_deal" if deal else "pre_deal"
        output.append(
            {
                "journey_order": _JOURNEY_ORDER[lane],
                "lane": lane,
                "status": _status_for_measurements(measurements, finding_statuses),
                "record_reference": record_reference,
                "record_type": "Deal" if deal else "Contact",
                "account_url": _hubspot_record_url(portal_id, "0-2", company_id),
                "contact_url": _hubspot_record_url(portal_id, "0-1", contact_ids[0] if contact_ids else primary_id if contact else ""),
                "deal_url": _hubspot_record_url(portal_id, "0-3", primary_id if deal else ""),
                "account_name": account_name,
                "contact_name": contact_name,
                "deal_name": deal_name,
                "pipeline": pipeline,
                "stage": stage,
                "owner": owner,
                "amount": amount,
                "why_this_record": _join_items(why),
                "evidence_timeline": _join_items(timeline),
                "observed_break": _join_items(breaks),
                "commercial_consequence": _join_items(consequences),
                "automation_evidence": automation_evidence,
                "recommended_action": _join_items(actions),
                "last_signal_at": _date_text(latest_signal.get("occurred_at")) if latest_signal else "Date unavailable",
                "measurement_ids": " | ".join(sorted(measurements)),
                "trace": " || ".join(sorted(group["traces"])),
            }
        )

    status_rank = {"Confirmed break": 0, "Review candidate": 1, "Recovery opportunity": 2, "Monitor": 3}
    output.sort(
        key=lambda row: (
            int(row["journey_order"]),
            status_rank.get(str(row.get("status")), 9),
            str(row.get("account_name")),
            str(row.get("deal_name")),
        )
    )
    return output


def write_report_record_evidence(run_dir: Path, rows: list[dict[str, Any]]) -> None:
    path = Path(run_dir) / "report_record_evidence.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REPORT_EVIDENCE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: csv_safe(row.get(column, "")) for column in REPORT_EVIDENCE_COLUMNS})
