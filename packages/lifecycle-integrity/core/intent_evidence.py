"""Normalize HubSpot intent/activity sources into a sanitized evidence layer.

The connector may keep raw responses in the local guarded snapshot, but this
module is the only layer that crosses into agent-visible artifacts.  It emits
event types, timestamps, channel direction, evidence strength, salted record
hashes, and coverage state; it never emits names, email addresses, form field
values, subjects, message bodies, full URLs, or campaign free text.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from connectors.hubspot.normalize import JsonlWriter, write_json

from .metrics import is_empty, load_association_map, parse_ms, read_json, read_jsonl
from .sanitizer import hash_record_id, load_or_create_salt, sanitize_untrusted_value

EVENT_SOURCE_FILES = {
    "activities": ("tasks", "meetings", "notes", "calls", "emails", "communications"),
    "events": ("event_occurrences.jsonl",),
    "forms": ("form_submissions.jsonl",),
    "campaigns": ("campaigns.json", "campaign_assets.json", "campaign_metrics.json"),
}

HIGH = "high"
MEDIUM = "medium"
LOW = "low"

_PATH_SIGNAL = re.compile(
    r"pricing|product|demo|contact.?sales|book|trial|request|solution|case.?stud|security",
    re.IGNORECASE,
)
_HIGH_SIGNAL = re.compile(
    r"demo|contact.?sales|sales.?request|book|meeting|conversion|reply|qualified|hand.?raise|intent",
    re.IGNORECASE,
)


def _props(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("properties")
    return value if isinstance(value, dict) else {}


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) not in (None, ""):
            return row.get(key)
        if _props(row).get(key) not in (None, ""):
            return _props(row).get(key)
    return None


def _timestamp(row: dict[str, Any], *keys: str) -> str | None:
    value = _first(row, *keys, "occurredAt", "occurred_at", "submittedAt", "createdAt")
    if value in (None, ""):
        return None
    parsed = parse_ms(value)
    if parsed is None:
        return None
    return datetime.fromtimestamp(parsed / 1000, tz=timezone.utc).isoformat()


def _safe_label(value: Any, *, fallback: str = "unknown") -> str:
    text = str(value or fallback).strip().lower().replace("_", " ")
    text = re.sub(r"[^a-z0-9 /-]+", "", text)
    return text[:80] or fallback


def _contact_id(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("vid", "id", "objectId", "contactId"):
            if value.get(key) not in (None, ""):
                return str(value[key])
        return None
    if value not in (None, ""):
        return str(value)
    return None


def _event_id(source: str, row: dict[str, Any], index: int) -> str:
    candidate = row.get("id") or row.get("eventId") or row.get("conversionId")
    if candidate not in (None, ""):
        return f"{source}:{candidate}"
    digest = hashlib.sha256(
        f"{source}|{row.get('occurredAt')}|{row.get('submittedAt')}|{index}".encode()
    ).hexdigest()[:20]
    return f"{source}:{digest}"


def _path_class(row: dict[str, Any]) -> str:
    # Events API places page-view URL fields inside `properties` for the
    # standard e_visited_page event. Keep URL parsing here so every source
    # (Events and Forms) gets the same coarse, query-string-free classification.
    path = _first(row, "pageUrl", "url", "page_url", "hs_url", "hs_base_url")
    if not path:
        return "unknown"
    # Only a coarse path class crosses the deterministic boundary. Query
    # strings, domains, and full URLs are intentionally discarded.
    text = str(path).split("?", 1)[0].lower()
    if _PATH_SIGNAL.search(text):
        return "commercial_intent_page"
    return "website_page"


def _activity_signal(object_type: str, row: dict[str, Any]) -> tuple[str, str, str, str]:
    props = _props(row)
    direction = _safe_label(
        props.get(
            {
                "calls": "hs_call_direction",
                "emails": "hs_email_direction",
                "communications": "hs_communication_channel_type",
            }.get(object_type, "")
        ),
        fallback="unknown",
    )
    status = _safe_label(
        props.get(
            {
                "calls": "hs_call_status",
                "emails": "hs_email_status",
                "tasks": "hs_task_status",
                "meetings": "hs_meeting_outcome",
            }.get(object_type, "")
        ),
        fallback="logged",
    )
    if object_type == "calls":
        signal_type = "call_connected" if status in {"completed", "connected"} else "call_logged"
        strength = HIGH if signal_type == "call_connected" and "inbound" in direction else MEDIUM
    elif object_type == "emails":
        signal_type = "email_reply" if "reply" in status or "incoming" in direction else "email_activity"
        strength = HIGH if signal_type == "email_reply" else MEDIUM
    elif object_type == "meetings":
        signal_type = "meeting_activity"
        strength = HIGH if status in {"completed", "held", "booked"} else MEDIUM
    elif object_type == "communications":
        signal_type = "communication_activity"
        strength = MEDIUM
    elif object_type == "tasks":
        signal_type = "task_activity"
        strength = LOW
    else:
        signal_type = "note_activity"
        strength = LOW
    return signal_type, strength, direction, status


def _event_signal(row: dict[str, Any]) -> tuple[str, str, str]:
    event_type = _safe_label(
        row.get("eventType") or row.get("eventTypeId") or row.get("fullyQualifiedName"),
        fallback="event",
    )
    text = event_type.replace("_", " ")
    path_class = _path_class(row)
    if (
        "form" in text
        or "conversion" in text
        or "reply" in text
        or "demo" in text
        or "contact sales" in text
        or "meeting" in text
    ):
        signal_type = "high_intent_event"
        strength = HIGH
    elif (
        "click" in text
        or _PATH_SIGNAL.search(text)
        or "visit" in text
        or "page" in text
        or path_class == "commercial_intent_page"
    ):
        signal_type = "commercial_page_or_visit"
        strength = MEDIUM if _PATH_SIGNAL.search(text) or path_class == "commercial_intent_page" else LOW
    elif "open" in text or "delivered" in text:
        signal_type = "marketing_email_event"
        strength = LOW
    else:
        signal_type = "marketing_event"
        strength = LOW
    return signal_type, strength, event_type


def _source_status(
    raw: Path,
    source: str,
    reported: dict[str, Any] | None = None,
) -> dict[str, Any]:
    files = EVENT_SOURCE_FILES[source]
    present = [
        f"{name}.jsonl" if source == "activities" else name
        for name in files
        if (
            raw / (f"{name}.jsonl" if source == "activities" else name)
        ).exists()
    ]
    if reported and reported.get("status") in {
        "permission_or_api_unavailable",
        "permission_denied",
        "unavailable",
    }:
        # The acquisition manifest is authoritative when an endpoint failed.
        # A partial raw file may exist after a page-level failure, but it is
        # not safe to reinterpret that prefix as complete source coverage.
        return {
            **reported,
            "status": reported.get("status"),
            "files_present": present,
            "metadata_only": True,
        }
    if reported and reported.get("status") == "partial":
        return {
            **reported,
            "status": "partial",
            "files_present": present,
            "metadata_only": True,
        }
    if not present:
        return {"status": "not_requested", "files_present": []}
    return {
        **(reported or {}),
        "status": "available",
        "files_present": present,
        "metadata_only": True,
    }


def _association_maps(raw: Path) -> dict[str, dict[str, dict[str, list[str]] | None]]:
    maps: dict[str, dict[str, dict[str, list[str]] | None]] = {}
    for activity_type in EVENT_SOURCE_FILES["activities"]:
        maps[activity_type] = {}
        for target in ("contacts", "companies", "deals"):
            maps[activity_type][target] = load_association_map(
                raw, f"associations_{activity_type}_{target}.jsonl"
            )
    return maps


def _add_event(
    events: list[dict[str, Any]],
    *,
    run_dir: Path,
    salt: str,
    source: str,
    signal_type: str,
    strength: str,
    occurred_at: str | None,
    direction: str = "unknown",
    status: str = "unknown",
    event_label: str = "unknown",
    contact_ids: Iterable[str] = (),
    deal_ids: Iterable[str] = (),
    association_quality: str = "direct",
    path_class: str = "unknown",
    ordinal: int = 0,
) -> None:
    contacts = list(dict.fromkeys(str(value) for value in contact_ids if value not in (None, "")))
    deals = list(dict.fromkeys(str(value) for value in deal_ids if value not in (None, "")))
    if not contacts and not deals:
        return
    event_key = _event_id(source, {"occurredAt": occurred_at, "eventType": event_label}, ordinal)
    events.append(
        {
            "event_id_hash": hashlib.sha256(event_key.encode()).hexdigest()[:24],
            "source": source,
            "signal_type": _safe_label(signal_type),
            "signal_strength": strength,
            "occurred_at": occurred_at,
            "direction": _safe_label(direction),
            "status": _safe_label(status),
            "event_label": sanitize_untrusted_value(_safe_label(event_label)),
            "path_class": path_class,
            "contact_id_hashes": sorted(hash_record_id("contacts", value, salt) for value in contacts),
            "deal_id_hashes": sorted(hash_record_id("deals", value, salt) for value in deals),
            "association_quality": association_quality,
            "evidence_ref": "processed/intent_signal_store.jsonl",
        }
    )


def build_intent_evidence(run_dir: Path) -> dict[str, Any]:
    """Build the sanitized, record-linked intent store for one audit run."""
    run_dir = Path(run_dir)
    raw = run_dir / "raw"
    processed = run_dir / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    salt = load_or_create_salt(run_dir)
    maps = _association_maps(raw)
    events: list[dict[str, Any]] = []
    counts_by_source: Counter[str] = Counter()
    counts_by_strength: Counter[str] = Counter()
    counts_by_type: Counter[str] = Counter()

    manifest = read_json(run_dir / "manifest.json", {})
    manifest_intent = manifest.get("intent") if isinstance(manifest, dict) else {}
    manifest_intent = manifest_intent if isinstance(manifest_intent, dict) else {}
    reported_sources = manifest_intent.get("sources")
    reported_sources = reported_sources if isinstance(reported_sources, dict) else {}
    source_status = {
        source: _source_status(
            raw,
            source,
            reported_sources.get(source)
            if isinstance(reported_sources.get(source), dict)
            else None,
        )
        for source in EVENT_SOURCE_FILES
    }
    reported_activity = reported_sources.get("activities")
    reported_activity = reported_activity if isinstance(reported_activity, dict) else {}
    allowed_activity_objects = set(reported_activity.get("objects") or [])

    for activity_type in EVENT_SOURCE_FILES["activities"]:
        path = raw / f"{activity_type}.jsonl"
        if not path.exists() or (
            allowed_activity_objects
            and activity_type not in allowed_activity_objects
        ):
            continue
        rows = read_jsonl(path)
        contact_map = maps[activity_type]["contacts"]
        deal_map = maps[activity_type]["deals"]
        for index, row in enumerate(rows):
            signal_type, strength, direction, status = _activity_signal(activity_type, row)
            activity_id = str(row.get("id") or "")
            contacts = (contact_map or {}).get(activity_id, []) if contact_map is not None else []
            deals = (deal_map or {}).get(activity_id, []) if deal_map is not None else []
            quality = "direct" if contact_map is not None or deal_map is not None else "association_unavailable"
            _add_event(
                events,
                run_dir=run_dir,
                salt=salt,
                source=activity_type,
                signal_type=signal_type,
                strength=strength,
                occurred_at=_timestamp(row, "hs_timestamp", "createdate"),
                direction=direction,
                status=status,
                event_label=signal_type,
                contact_ids=contacts,
                deal_ids=deals,
                association_quality=quality,
                ordinal=index,
            )

    event_path = raw / "event_occurrences.jsonl"
    if event_path.exists() and source_status["events"].get("status") not in {
        "permission_or_api_unavailable",
        "permission_denied",
        "unavailable",
    }:
        for index, row in enumerate(read_jsonl(event_path)):
            signal_type, strength, label = _event_signal(row)
            object_id = _first(row, "objectId", "object_id", "associatedObjectId")
            object_type = _safe_label(_first(row, "objectType", "object_type"), fallback="contact")
            contacts = [str(object_id)] if object_id and object_type in {"contact", "contacts", "0-1"} else []
            deals = [str(object_id)] if object_id and "deal" in object_type else []
            _add_event(
                events,
                run_dir=run_dir,
                salt=salt,
                source="events",
                signal_type=signal_type,
                strength=strength,
                occurred_at=_timestamp(row),
                event_label=label,
                contact_ids=contacts,
                deal_ids=deals,
                association_quality="direct" if object_id else "unlinked",
                path_class=_path_class(row),
                ordinal=index,
            )

    form_path = raw / "form_submissions.jsonl"
    forms = read_json(raw / "forms.json", [])
    forms_by_id = {
        str(item.get("guid") or item.get("id") or ""): item
        for item in forms
        if isinstance(item, dict)
    }
    contact_email_to_ids: dict[str, list[str]] = defaultdict(list)
    for contact_row in read_jsonl(raw / "contacts.jsonl") if (raw / "contacts.jsonl").exists() else []:
        contact_props = _props(contact_row)
        email = contact_props.get("email") or contact_row.get("email")
        if email not in (None, ""):
            contact_email_to_ids[str(email).strip().lower()].append(str(contact_row.get("id")))
    unlinked_form_submissions = 0
    if form_path.exists() and source_status["forms"].get("status") not in {
        "permission_or_api_unavailable",
        "permission_denied",
        "unavailable",
    }:
        for index, row in enumerate(read_jsonl(form_path)):
            form_id = str(row.get("form_guid") or "")
            form_name = next(
                (
                    str(item.get("name") or item.get("guid") or "")
                    for item in forms_by_id.values()
                    if str(item.get("guid") or item.get("id") or "") == form_id
                ),
                form_id,
            )
            contact = _contact_id(row.get("contact"))
            if not contact:
                email = str(row.get("contact_email") or "").strip().lower()
                matches = contact_email_to_ids.get(email, []) if email else []
                if len(matches) == 1:
                    contact = matches[0]
            signal_type = "form_submission"
            strength = HIGH if _HIGH_SIGNAL.search(form_name) else MEDIUM
            if not contact:
                unlinked_form_submissions += 1
            _add_event(
                events,
                run_dir=run_dir,
                salt=salt,
                source="forms",
                signal_type=signal_type,
                strength=strength,
                occurred_at=_timestamp(row),
                event_label=form_name,
                contact_ids=[contact] if contact else [],
                path_class=_path_class(row),
                association_quality="direct" if contact else "unlinked",
                ordinal=index,
            )

    # Campaign records are aggregate context. They are deliberately not
    # turned into contact intent events because aggregate engagement cannot
    # prove an individual buyer journey or a recoverable deal.
    campaigns_available = source_status["campaigns"].get("status") not in {
        "permission_or_api_unavailable",
        "permission_denied",
        "unavailable",
    }
    campaign_rows = read_json(raw / "campaigns.json", []) if campaigns_available else []
    asset_rows = read_json(raw / "campaign_assets.json", []) if campaigns_available else []
    metric_rows = read_json(raw / "campaign_metrics.json", []) if campaigns_available else []
    asset_type_counts: Counter[str] = Counter()
    channel_counts: Counter[str] = Counter()
    channel_by_asset_type = {
        "AD_CAMPAIGN": "paid_ad",
        "SOCIAL_BROADCAST": "social",
        "FORM": "inbound_form",
        "MARKETING_EMAIL": "email",
        "SITE_PAGE": "web_content",
        "LANDING_PAGE": "web_content",
        "WEB_INTERACTIVE": "web_content",
    }
    for asset in asset_rows:
        asset_type = _safe_label(asset.get("asset_type"), fallback="unknown_asset")
        asset_type_counts[asset_type] += 1
        channel_counts[channel_by_asset_type.get(str(asset.get("asset_type") or ""), "other")] += 1
    campaign_context = {
        "campaign_count": len(campaign_rows),
        "asset_count": len(asset_rows),
        "metric_count": len(metric_rows),
        "campaigns_with_assets": len({str(row.get("campaign_id")) for row in asset_rows if row.get("campaign_id")}),
        "asset_type_counts": dict(sorted(asset_type_counts.items())),
        "channel_counts": dict(sorted(channel_counts.items())),
        "metrics_available": sum(1 for row in metric_rows if row.get("metrics") not in (None, {}, [])),
        "context_only": True,
        "evidence_scope": "aggregate_channel_context_only; not person-level proof",
    }

    for row in events:
        counts_by_source[row["source"]] += 1
        counts_by_strength[row["signal_strength"]] += 1
        counts_by_type[row["signal_type"]] += 1

    # A separate per-record index makes downstream recovery checks cheap and
    # keeps all raw ids outside the agent boundary.
    contact_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    deal_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in events:
        for record_hash in row["contact_id_hashes"]:
            contact_index[record_hash].append(row)
        for record_hash in row["deal_id_hashes"]:
            deal_index[record_hash].append(row)

    contact_to_deals = load_association_map(raw, "associations_deal_contact.jsonl")
    deal_to_contacts: dict[str, list[str]] = defaultdict(list)
    if contact_to_deals is not None:
        for deal_id, contact_ids in contact_to_deals.items():
            for contact_id in contact_ids:
                deal_to_contacts[str(contact_id)].append(str(deal_id))

    # Propagate activity/event signals from a linked contact to its deals only
    # for timeline analysis. This is an association-derived link, never a
    # claim that the signal created or influenced the deal.
    for contact_id, deal_ids in deal_to_contacts.items():
        contact_hash = hash_record_id("contacts", contact_id, salt)
        for event in contact_index.get(contact_hash, []):
            for deal_id in deal_ids:
                deal_hash = hash_record_id("deals", deal_id, salt)
                if deal_hash not in event["deal_id_hashes"]:
                    event["deal_id_hashes"].append(deal_hash)
                    event["association_quality"] = "contact_to_deal_inferred"
                    deal_index[deal_hash].append(event)

    source_status["activities"]["activity_objects"] = {
        object_type: {
            "count": len(read_jsonl(raw / f"{object_type}.jsonl"))
            if (raw / f"{object_type}.jsonl").exists()
            and (
                not allowed_activity_objects
                or object_type in allowed_activity_objects
            )
            else 0,
            "contact_association_available": maps[object_type]["contacts"] is not None,
            "deal_association_available": maps[object_type]["deals"] is not None,
        }
        for object_type in EVENT_SOURCE_FILES["activities"]
    }
    source_row_counts = {
        "activities": sum(
            int(value.get("count") or 0)
            for value in source_status["activities"].get("activity_objects", {}).values()
            if isinstance(value, dict)
        ),
        "events": counts_by_source.get("events", 0),
        "forms": counts_by_source.get("forms", 0),
        "campaigns": len(asset_rows) + len(metric_rows),
    }
    for source, row in source_status.items():
        if row.get("status") in {"available", "full"} and source_row_counts.get(source, 0) == 0:
            row["status"] = "observed_no_events"
        if source == "forms":
            row["unlinked_submission_count"] = unlinked_form_submissions
    requested_sources = [
        row for row in source_status.values() if row.get("status") != "not_requested"
    ]
    if not requested_sources:
        overall_status = "not_requested"
    else:
        unavailable = any(
            row.get("status") in {
                "permission_or_api_unavailable",
                "permission_denied",
                "unavailable",
            }
            for row in requested_sources
        )
        observed = any(
            row.get("status") in {"available", "full", "partial", "observed_no_events"}
            for row in requested_sources
        )
        overall_status = "partial" if unavailable and observed else "unavailable" if unavailable else "available"

    store = {
        "run_id": run_dir.name,
        "coverage": {
            "status": overall_status,
            "sources": source_status,
            "metadata_only": True,
            "limitations": [
                "Marketing email opens/clicks and aggregate social/ad metrics are context signals, not person-level proof.",
                "A source with a successful endpoint and zero rows is reported as observed_no_events; this is different from unavailable access.",
                "Missing activity associations prevent record-level recovery claims for that activity type.",
            ],
        },
        "event_count": len(events),
        "counts_by_source": dict(counts_by_source),
        "counts_by_strength": dict(counts_by_strength),
        "counts_by_signal_type": dict(counts_by_type),
        "linked_to_contact_count": sum(1 for row in events if row["contact_id_hashes"]),
        "linked_to_deal_count": sum(1 for row in events if row["deal_id_hashes"]),
        "high_intent_contact_count": sum(
            1 for rows in contact_index.values() if any(row["signal_strength"] == HIGH for row in rows)
        ),
        "high_intent_deal_count": sum(
            1 for rows in deal_index.values() if any(row["signal_strength"] == HIGH for row in rows)
        ),
        "campaign_context": campaign_context,
        "source_row_counts": source_row_counts,
        "contains_raw_values": False,
        "contains_raw_pii": False,
    }
    # Keep the manifest's source contract aligned with the processed coverage
    # artifact. In particular, a successful zero-row source must be visible as
    # observed_no_events to downstream validators and operators, rather than
    # remaining ambiguously labelled as available.
    manifest_intent = manifest.get("intent")
    manifest_intent = manifest_intent if isinstance(manifest_intent, dict) else {}
    manifest["intent"] = {
        **manifest_intent,
        "status": overall_status,
        "sources": source_status,
        "metadata_only": True,
        "limitations": list(store["coverage"].get("limitations") or []),
    }
    write_json(run_dir / "manifest.json", manifest)
    write_json(processed / "intent_signal_summary.json", store)
    write_json(processed / "intent_signal_coverage.json", store["coverage"])
    write_json(
        processed / "intent_record_index.json",
        {
            "contacts": {
                key: [
                    {
                        "signal_type": row["signal_type"],
                        "signal_strength": row["signal_strength"],
                        "source": row["source"],
                        "occurred_at": row["occurred_at"],
                        "deal_id_hashes": row["deal_id_hashes"],
                    }
                    for row in value
                ]
                for key, value in contact_index.items()
            },
            "deals": {
                key: [
                    {
                        "signal_type": row["signal_type"],
                        "signal_strength": row["signal_strength"],
                        "source": row["source"],
                        "occurred_at": row["occurred_at"],
                    }
                    for row in value
                ]
                for key, value in deal_index.items()
            },
            "contains_raw_values": False,
        },
    )
    with JsonlWriter(processed / "intent_signal_store.jsonl") as writer:
        for row in sorted(events, key=lambda item: (item.get("occurred_at") or "", item["event_id_hash"])):
            writer.write(row)
    return store
