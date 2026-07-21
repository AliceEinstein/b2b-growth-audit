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
JOURNEY_CANDIDATE_PATTERN = re.compile(
    r"(source|attribution|campaign|channel|utm|medium|lead|lifecycle|"
    r"deal.?type|account.?tier|target.?account|partner|referr|reseller|"
    r"renew|expansion|motion|intent|hand.?rais|demo|contact.?sales|"
    r"sales.?request|meeting|book|reply|response|respond|conversion|"
    r"form|inquir|qualif|routing|route|handoff|sla)",
    re.IGNORECASE,
)
CANDIDATE_CAP = 40

# HubSpot writes a plain (no history API needed) timestamp property every time
# a record enters a lifecycle stage or deal stage: hs_v2_date_entered_<stage>
# on contacts/companies, hs_date_entered_<stageId> / hs_v2_date_entered_<stageId>
# on deals. These are the only direct evidence of actual stage TRANSITIONS —
# without them, journeys can only be inferred from record creation order.
STAGE_TIMESTAMP_PATTERN = re.compile(r"^hs(_v2)?_date_entered_", re.IGNORECASE)
STAGE_TIMESTAMP_CAP = 80


def _is_protected_value_property(definition: dict[str, Any]) -> bool:
    """Return True when HubSpot marks a property value as protected.

    Schema reads remain useful for governance without a Sensitive Data value
    scope.  Never promote a protected value into a journey snapshot merely
    because the supplied token happens to have additional read permissions.
    """
    sensitivity = str(definition.get("dataSensitivity") or "").lower()
    return sensitivity not in {"", "non_sensitive"}


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
    matching = [
        d
        for d in definitions
        if not d.get("hubspotDefined")
        and (
            SOURCE_CANDIDATE_PATTERN.search(d.get("name", ""))
            or SOURCE_CANDIDATE_PATTERN.search(d.get("label", ""))
        )
    ]
    protected_count = sum(_is_protected_value_property(d) for d in matching)
    if protected_count and log is not None:
        log.warn(
            f"{object_type}: excluded {protected_count} source-like Sensitive "
            "Data property value(s) from the snapshot candidate list."
        )
    names = [d["name"] for d in matching if not _is_protected_value_property(d)]
    if len(names) > cap:
        if log is not None:
            log.warn(
                f"{object_type}: {len(names)} source-like custom properties "
                f"found; snapshotting first {cap}. Property sprawl itself will "
                "be reported by the Property Governance module."
            )
        names = names[:cap]
    return names


def select_stage_timestamp_candidates(
    definitions: list[dict[str, Any]],
    *,
    cap: int = STAGE_TIMESTAMP_CAP,
    log: Any = None,
    object_type: str = "",
) -> list[str]:
    """Stage-entry timestamp properties, taken from the portal's real
    definitions so custom lifecycle stages and per-pipeline deal stages are
    covered automatically. Prefer v2 names when both generations exist."""
    names = sorted(
        d["name"]
        for d in definitions
        if STAGE_TIMESTAMP_PATTERN.match(str(d.get("name", "")))
        and not _is_protected_value_property(d)
    )
    v2 = {name for name in names if name.startswith("hs_v2_date_entered_")}
    names = [
        name
        for name in names
        if name in v2 or "hs_v2" + name.removeprefix("hs") not in v2
    ]
    if len(names) > cap:
        if log is not None:
            log.warn(
                f"{object_type}: {len(names)} stage-entry timestamp properties "
                f"found; snapshotting first {cap}."
            )
        names = names[:cap]
    return names


def select_journey_candidates(
    definitions: list[dict[str, Any]],
    *,
    cap: int = CANDIDATE_CAP,
    log: Any = None,
    object_type: str = "",
) -> list[str]:
    """Fields whose values can help infer lifecycle and journey intent."""
    matching = [
        d
        for d in definitions
        if not d.get("hubspotDefined")
        and (
            JOURNEY_CANDIDATE_PATTERN.search(d.get("name", ""))
            or JOURNEY_CANDIDATE_PATTERN.search(d.get("label", ""))
        )
    ]
    protected_count = sum(_is_protected_value_property(d) for d in matching)
    if protected_count and log is not None:
        log.warn(
            f"{object_type}: excluded {protected_count} journey-relevant Sensitive "
            "Data property value(s) from the snapshot candidate list."
        )
    names = [d["name"] for d in matching if not _is_protected_value_property(d)]
    if len(names) > cap:
        if log is not None:
            log.warn(
                f"{object_type}: {len(names)} journey-relevant custom properties "
                f"found; snapshotting first {cap}."
            )
        names = names[:cap]
    return names
