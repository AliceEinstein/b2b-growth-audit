"""Read-only CRM activity metadata snapshot.

The activity layer is deliberately metadata-first. Bodies, recordings,
subjects, email addresses, and free-text descriptions are never requested.
Associations are fetched separately by the snapshot runner so deterministic
code can build record-linked timelines without exposing raw activity content
to judgment agents.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .client import HubSpotClient, HubSpotError
from .paging import fetch_object_records

ACTIVITY_PROPERTIES = {
    "tasks": ["createdate", "hs_timestamp", "hubspot_owner_id", "hs_task_status"],
    "meetings": [
        "createdate",
        "hs_timestamp",
        "hubspot_owner_id",
        "hs_meeting_outcome",
    ],
    "notes": ["createdate", "hs_timestamp", "hubspot_owner_id"],
    "calls": [
        "createdate",
        "hs_timestamp",
        "hubspot_owner_id",
        "hs_call_status",
        "hs_call_disposition",
        "hs_call_direction",
        "hs_activity_type",
    ],
    "emails": [
        "createdate",
        "hs_timestamp",
        "hubspot_owner_id",
        "hs_email_status",
        "hs_email_direction",
        "hs_email_type",
    ],
    "communications": [
        "createdate",
        "hs_timestamp",
        "hubspot_owner_id",
        "hs_communication_channel_type",
        "hs_communication_logged_from",
    ],
}


def fetch_all(
    client: HubSpotClient,
    raw_dir: Path,
    *,
    days: int | None = None,
    log: Any = None,
    resume: bool = False,
) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for object_type, properties in ACTIVITY_PROPERTIES.items():
        try:
            summary = fetch_object_records(
                client,
                object_type,
                properties,
                Path(raw_dir) / f"{object_type}.jsonl",
                days=days,
                log=log,
                resume=resume,
            )
            summary["available"] = True
            summaries[object_type] = summary
        except HubSpotError:
            # Activity products have different portal entitlements. Keep the
            # other channels running and let coverage distinguish unavailable
            # from observed zero events.
            # Do not leave a partially written JSONL file behind: the
            # normalization layer must not mistake a failed source for an
            # observed empty/available source on a later phase.
            partial_path = Path(raw_dir) / f"{object_type}.jsonl"
            if partial_path.exists():
                partial_path.unlink()
            summaries[object_type] = {
                "object_type": object_type,
                "count": 0,
                "ids": [],
                "truncated": False,
                "properties": properties,
                "available": False,
                "status": "permission_or_api_unavailable",
            }
    return summaries
