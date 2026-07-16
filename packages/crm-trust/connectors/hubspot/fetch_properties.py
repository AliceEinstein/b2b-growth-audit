"""Property definition fetch + source-like custom property candidates.

The candidate regex below is a FETCH-SCOPE heuristic, not a judgment: it
decides which custom property VALUES are worth snapshotting so the schema
discovery LLM can later judge which fields are canonical / legacy /
duplicates. Missing a candidate means less evidence, not a wrong verdict.
"""
from __future__ import annotations

import re
from typing import Any

from .client import HubSpotClient

SOURCE_CANDIDATE_PATTERN = re.compile(
    r"(source|attribution|campaign|channel|utm|medium|lead)", re.IGNORECASE
)
CANDIDATE_CAP = 40


def fetch_property_definitions(
    client: HubSpotClient, object_type: str
) -> list[dict[str, Any]]:
    return client.get(f"/crm/v3/properties/{object_type}").get("results", [])


def select_source_candidates(
    definitions: list[dict[str, Any]],
    *,
    cap: int = CANDIDATE_CAP,
    log: Any = None,
    object_type: str = "",
) -> list[str]:
    """Custom (non-HubSpot-defined) properties that look attribution-related."""
    names = [
        d["name"]
        for d in definitions
        if not d.get("hubspotDefined")
        and (
            SOURCE_CANDIDATE_PATTERN.search(d.get("name", ""))
            or SOURCE_CANDIDATE_PATTERN.search(d.get("label", ""))
        )
    ]
    if len(names) > cap:
        if log is not None:
            log.warn(
                f"{object_type}: {len(names)} source-like custom properties "
                f"found; snapshotting first {cap}. Property sprawl itself will "
                "be reported by the Property Governance module."
            )
        names = names[:cap]
    return names
