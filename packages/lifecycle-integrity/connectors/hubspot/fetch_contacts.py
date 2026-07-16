"""Contact snapshot fetch.

Identity fields are fetched because this is a local, owner-authorized data
quality audit: the audit must be able to distinguish an empty contact schema
from a populated one. They remain in the local raw snapshot only; the
profiler emits counts and format checks, never raw identity values, to LLM-
facing artifacts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .client import HubSpotClient
from .paging import fetch_object_records

DEFAULT_PROPERTIES = [
    "createdate",
    "lastmodifieddate",
    "lifecyclestage",
    "email",
    "firstname",
    "lastname",
    "phone",
    "hs_analytics_source",
    "hs_analytics_source_data_1",
    "hs_analytics_source_data_2",
    "hs_latest_source",
    "hs_latest_source_data_1",
    "hs_latest_source_data_2",
    "hubspot_owner_id",
    "hs_object_source",
    "hs_object_source_label",
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
        "contacts",
        DEFAULT_PROPERTIES,
        out_path,
        days=days,
        extra_properties=extra_properties,
        log=log,
        resume=resume,
    )
