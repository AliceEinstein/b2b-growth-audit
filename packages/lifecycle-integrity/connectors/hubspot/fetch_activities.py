"""Optional read-only activity metadata snapshot.

Note bodies and free-text descriptions are intentionally excluded. Activity
associations are not fetched in v1, so downstream handoff checks must treat
these records as portal-level availability and owner/timestamp signals only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .client import HubSpotClient
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
        summaries[object_type] = fetch_object_records(
            client,
            object_type,
            properties,
            Path(raw_dir) / f"{object_type}.jsonl",
            days=days,
            log=log,
            resume=resume,
        )
    return summaries
