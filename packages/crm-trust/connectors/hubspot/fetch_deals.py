"""Deal snapshot fetch."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .client import HubSpotClient
from .paging import fetch_object_records

DEFAULT_PROPERTIES = [
    "createdate",
    "hs_lastmodifieddate",
    "dealname",
    "amount",
    "dealstage",
    "pipeline",
    "closedate",
    "hubspot_owner_id",
    "hs_object_source",
]


def fetch(
    client: HubSpotClient,
    out_path: Path,
    *,
    days: int | None = None,
    extra_properties: tuple[str, ...] | list[str] = (),
    log: Any = None,
    resume: bool = False,
) -> dict[str, Any]:
    return fetch_object_records(
        client,
        "deals",
        DEFAULT_PROPERTIES,
        out_path,
        days=days,
        extra_properties=extra_properties,
        log=log,
        resume=resume,
    )
