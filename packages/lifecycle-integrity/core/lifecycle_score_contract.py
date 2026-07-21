"""Explicit scoring ownership and validation for lifecycle measurements."""
from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any, Iterable
from urllib.parse import unquote


SCORE_CONTROL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "intent_owner": {
        "link": "intent_to_owner",
        "weight": 20,
        "aggregation": "weighted_partition",
    },
    "owner_deal": {
        "link": "owner_to_deal",
        "weight": 20,
        "aggregation": "weighted_partition",
    },
    "contact_lifecycle_state": {
        "link": "deal_continuity",
        "weight": 5,
        "aggregation": "single",
    },
    "deal_company_association": {
        "link": "deal_continuity",
        "weight": 5,
        "aggregation": "single",
    },
    "deal_contact_association": {
        "link": "deal_continuity",
        "weight": 5,
        "aggregation": "single",
    },
    "inbound_source_continuity": {
        "link": "deal_continuity",
        "weight": 5,
        "aggregation": "single",
    },
    "open_deal_owner": {
        "link": "deal_progression",
        "weight": 10,
        "aggregation": "weighted_partition",
    },
    "active_deal_followup": {
        "link": "deal_progression",
        "weight": 15,
        "aggregation": "single",
    },
    "expansion_customer_state": {
        "link": "post_close_recovery",
        "weight": 15,
        "aggregation": "single",
    },
}

SCORE_LINKS = {row["link"] for row in SCORE_CONTROL_DEFINITIONS.values()}
SCORE_ROLES = {
    "primary",
    "breakdown",
    "supporting",
    "opportunity_only",
    "not_scored",
}


def cited_measurement_ids(
    evidence_refs: Iterable[str], known_ids: Iterable[str]
) -> set[str]:
    """Extract exact evidence.csv finding_id fragments, never substrings."""
    known = set(known_ids)
    cited: set[str] = set()
    for reference in evidence_refs:
        fragment = str(reference).partition("#")[2]
        for part in re.split(r"[&;]", fragment):
            key, separator, value = part.partition("=")
            if separator and key == "finding_id":
                measurement_id = unquote(value).strip()
                if measurement_id in known:
                    cited.add(measurement_id)
    return cited


def _valid_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def validate_scoring_contract(measurements: Iterable[Any]) -> list[str]:
    """Return deterministic contract errors without mutating measurements."""
    rows = list(measurements)
    problems: list[str] = []
    ids: set[str] = set()
    population_links: dict[str, set[str]] = defaultdict(set)
    primaries: dict[tuple[str, str], list[str]] = defaultdict(list)
    control_primaries: dict[str, list[str]] = defaultdict(list)
    breakdowns: list[tuple[str, str, str, str]] = []

    for index, raw_row in enumerate(rows):
        if not isinstance(raw_row, dict):
            problems.append(f"measurement[{index}]: must be an object")
            continue
        row = raw_row
        measurement_id = str(row.get("id") or "").strip()
        prefix = measurement_id or f"measurement[{index}]"
        if not measurement_id:
            problems.append(f"{prefix}: id is required")
        elif measurement_id in ids:
            problems.append(f"{prefix}: duplicate measurement id")
        ids.add(measurement_id)

        role = str(row.get("score_role") or "").strip()
        link = str(row.get("score_link") or "").strip()
        control = str(row.get("score_control") or "").strip()
        population_key = str(row.get("score_population_key") or "").strip()
        outside_reason = str(row.get("outside_score_reason") or "").strip()

        if not isinstance(row.get("available"), bool):
            problems.append(f"{prefix}: available must be boolean")
        if not isinstance(row.get("leakage_candidate"), bool):
            problems.append(f"{prefix}: leakage_candidate must be boolean")
        denominator = row.get("denominator")
        affected = row.get("affected_records")
        percentage = row.get("affected_percentage")
        if denominator is not None and (
            not isinstance(denominator, int)
            or isinstance(denominator, bool)
            or denominator < 0
        ):
            problems.append(f"{prefix}: denominator must be a non-negative integer or null")
        if affected is not None and (
            not isinstance(affected, int)
            or isinstance(affected, bool)
            or affected < 0
        ):
            problems.append(f"{prefix}: affected_records must be a non-negative integer or null")
        if percentage is not None and (
            not _valid_number(percentage) or not 0 <= float(percentage) <= 100
        ):
            problems.append(f"{prefix}: affected_percentage must be between 0 and 100 or null")
        if _valid_number(denominator) and _valid_number(affected):
            if float(affected) > float(denominator):
                problems.append(f"{prefix}: affected_records cannot exceed denominator")
            expected = None if float(denominator) == 0 else round(float(affected) / float(denominator) * 100, 1)
            if expected is not None and (
                percentage is None
                or not _valid_number(percentage)
                or abs(float(percentage) - expected) > 0.11
            ):
                problems.append(
                    f"{prefix}: affected_percentage must match affected_records / denominator ({expected:g})"
                )

        if role not in SCORE_ROLES:
            problems.append(
                f"{prefix}: score_role must be one of {', '.join(sorted(SCORE_ROLES))}"
            )
            continue

        if role == "not_scored":
            if link or control or population_key:
                problems.append(
                    f"{prefix}: not_scored measurements cannot declare score_link, score_control, or score_population_key"
                )
            if row.get("leakage_candidate"):
                problems.append(
                    f"{prefix}: leakage_candidate requires an explicit scored, supporting, or outside-score role"
                )
            if outside_reason:
                problems.append(
                    f"{prefix}: outside_score_reason is not valid for not_scored measurements"
                )
            continue

        if link not in SCORE_LINKS:
            problems.append(
                f"{prefix}: score_link must be one of {', '.join(sorted(SCORE_LINKS))}"
            )
        if not population_key:
            problems.append(f"{prefix}: score_population_key is required for {role}")

        if role in {"primary", "breakdown", "supporting"}:
            definition = SCORE_CONTROL_DEFINITIONS.get(control)
            if definition is None:
                problems.append(f"{prefix}: score_control is required and must be a defined control for {role}")
            elif link and definition["link"] != link:
                problems.append(
                    f"{prefix}: score_control {control} belongs to {definition['link']}, not {link}"
                )
        elif control:
            problems.append(f"{prefix}: opportunity_only measurements cannot declare score_control")

        if role in {"opportunity_only", "supporting"} and not outside_reason:
            problems.append(f"{prefix}: {role} measurements require outside_score_reason")
        if role in {"primary", "breakdown"} and outside_reason:
            problems.append(
                f"{prefix}: outside_score_reason is only valid for opportunity_only or supporting measurements"
            )

        if link and population_key:
            population_links[population_key].add(link)
            if role == "primary":
                primaries[(link, population_key)].append(prefix)
                control_primaries[control].append(prefix)
            elif role == "breakdown":
                breakdowns.append((prefix, link, control, population_key))

    for population_key, links in sorted(population_links.items()):
        if len(links) > 1:
            problems.append(
                f"{population_key}: score population maps to multiple links: {', '.join(sorted(links))}"
            )
    for (link, population_key), measurement_ids in sorted(primaries.items()):
        if len(measurement_ids) > 1:
            problems.append(
                f"{link}/{population_key}: multiple primary measurements: "
                + ", ".join(sorted(measurement_ids))
            )
    for control, measurement_ids in sorted(control_primaries.items()):
        definition = SCORE_CONTROL_DEFINITIONS.get(control, {})
        if definition.get("aggregation") == "single" and len(measurement_ids) > 1:
            problems.append(
                f"{control}: single-population control has multiple primary measurements: "
                + ", ".join(sorted(measurement_ids))
            )
    for measurement_id, link, control, population_key in breakdowns:
        if not primaries.get((link, population_key)):
            problems.append(
                f"{measurement_id}: breakdown has no primary measurement for {link}/{population_key}"
            )
        elif not any(
            str(row.get("score_control") or "") == control
            and str(row.get("score_population_key") or "") == population_key
            and str(row.get("score_role") or "") == "primary"
            for row in rows
            if isinstance(row, dict)
        ):
            problems.append(
                f"{measurement_id}: breakdown score_control does not match its primary"
            )
    return problems
