"""Deterministic, journey-link based lifecycle integrity scoring.

The score answers a business question: how much of the represented journey is
currently protected by an observable control?  It is deliberately separate
from journey-type confidence and from pipeline amount.  Amounts help rank the
action queue; they do not make a process control more or less healthy.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

from .lifecycle_schemas import JourneyPatternRegistry, LifecycleFinding

LINK_DEFINITIONS = {
    "intent_to_owner": {
        "label": "Intent to accountable owner",
        "weight": 20,
        "match": lambda row: (
            "without_owner" in str(row.get("id") or "")
            or "owner" in str(row.get("leakage_point") or "").lower()
        ),
    },
    "owner_to_deal": {
        "label": "Owner to deal or valid skip",
        "weight": 20,
        "match": lambda row: (
            "without_deal" in str(row.get("id") or "")
            or "signals_without_deal" in str(row.get("id") or "")
            or "deal path" in str(row.get("note") or "").lower()
        ),
    },
    "deal_continuity": {
        "label": "Deal, account, contact, and source continuity",
        "weight": 20,
        "match": lambda row: (
            row.get("integrity_dimension") in {"association_integrity", "attribution_continuity"}
            or "without_company" in str(row.get("id") or "")
            or "without_contact" in str(row.get("id") or "")
            or "source_trace" in str(row.get("id") or "")
        ),
    },
    "deal_progression": {
        "label": "Open deal to next action",
        "weight": 25,
        "match": lambda row: (
            "active_deal_intent" in str(row.get("id") or "")
            or "stage_regression" in str(row.get("id") or "")
            or "deals_without_owner" in str(row.get("id") or "")
        ),
    },
    "post_close_recovery": {
        "label": "Closed-lost/customer to recovery or renewal",
        "weight": 15,
        "match": lambda row: (
            "closed_lost" in str(row.get("id") or "")
            or "renewal" in str(row.get("id") or "")
            or "expansion" in str(row.get("id") or "")
        ),
    },
}


def _finding_statuses(findings: Iterable[LifecycleFinding]) -> dict[str, str]:
    return {str(row.finding_id): str(row.review_status) for row in findings}


def _risk_multiplier(measurement_id: str, statuses: dict[str, str]) -> tuple[float, str]:
    # Renewed intent after closed-lost is a commercial recovery opportunity,
    # not proof that the previous lifecycle control failed. Keep it visible
    # without moving the integrity score unless a separate scored control
    # finding establishes the break.
    if measurement_id == "closed_lost_recovery_opportunity":
        return 0.0, "opportunity_not_scored"
    status = statuses.get(measurement_id)
    if status in {"approved", "revised"}:
        return 1.0, "confirmed"
    if status in {"rejected", "observation"}:
        return 0.0, "not_counted"
    # A deterministic affected population with no completed reviewer decision
    # remains visible as exposure, but carries only half weight until reviewed.
    return 0.5, "review_candidate"


def _coverage_label(coverage: float) -> str:
    if coverage >= 95:
        return "assessed"
    if coverage >= 70:
        return "partially assessed"
    return "limited evidence"


def compute_lifecycle_score(
    findings: Iterable[LifecycleFinding],
    registry: JourneyPatternRegistry,
    measurements: Iterable[dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Compute the executive lifecycle score from five observable links.

    Candidate populations receive half weight until adjudicated.  This avoids
    the previous failure mode where a portal could show material leakage while
    retaining a misleading 94/100 headline simply because only one finding
    had completed review.
    """
    finding_list = list(findings)
    statuses = _finding_statuses(finding_list)
    rows = [row for row in (measurements or []) if isinstance(row, dict)]
    link_scores: dict[str, dict[str, Any]] = {}
    assessed_weight = 0
    score_total = 0.0
    candidate_count = 0
    confirmed_count = sum(
        status in {"approved", "revised"}
        and measurement_id != "closed_lost_recovery_opportunity"
        for measurement_id, status in statuses.items()
    )

    for link_id, definition in LINK_DEFINITIONS.items():
        matched = [row for row in rows if definition["match"](row)]
        available = [row for row in matched if row.get("available", True)]
        affected = [row for row in available if (row.get("affected_records") or 0) > 0]
        if not available:
            link_scores[link_id] = {
                "label": definition["label"],
                "weight": definition["weight"],
                "score": None,
                "deducted": None,
                "status": "not_assessable",
                "affected_percentage": None,
                "evidence_measurements": [],
                "scoring_note": "Required source or denominator was unavailable.",
            }
            continue

        assessed_weight += int(definition["weight"])
        selected: list[dict[str, Any]] = []
        max_risk = 0.0
        dominant_state = "healthy"
        opportunity_not_scored = False
        for row in affected:
            multiplier, state = _risk_multiplier(str(row.get("id") or ""), statuses)
            if multiplier == 0:
                if state == "opportunity_not_scored":
                    opportunity_not_scored = True
                    selected.append(
                        {
                            "measurement_id": row.get("id"),
                            "affected_percentage": row.get("affected_percentage"),
                            "status": state,
                            "risk_multiplier": 0.0,
                        }
                    )
                continue
            percentage = float(row.get("affected_percentage") or 0.0) / 100
            risk = min(1.0, percentage * multiplier)
            if risk >= max_risk:
                max_risk = risk
                dominant_state = state
            selected.append(
                {
                    "measurement_id": row.get("id"),
                    "affected_percentage": row.get("affected_percentage"),
                    "status": state,
                    "risk_multiplier": multiplier,
                }
            )
            if state == "review_candidate":
                candidate_count += 1
        link_score = round(definition["weight"] * (1 - max_risk), 1)
        deducted = round(definition["weight"] - link_score, 1)
        score_total += link_score
        label = {
            "healthy": "healthy",
            "confirmed": "confirmed break",
            "review_candidate": "review candidate included provisionally",
        }.get(dominant_state, dominant_state)
        if opportunity_not_scored and max_risk == 0:
            label = "recovery opportunity shown outside score"
        link_scores[link_id] = {
            "label": definition["label"],
            "weight": definition["weight"],
            "score": link_score,
            "deducted": deducted,
            "status": label,
            "affected_percentage": round(max_risk * 100, 1),
            "evidence_measurements": selected,
            "scoring_note": (
                "Recovery opportunities are shown outside the score."
                if opportunity_not_scored and max_risk == 0
                else "The highest affected share in this link is used; overlapping measurements are not added twice."
            ),
        }

    total_weight = sum(int(row["weight"]) for row in LINK_DEFINITIONS.values())
    total_deducted = round(
        sum(
            float(row.get("deducted") or 0)
            for row in link_scores.values()
            if isinstance(row.get("deducted"), (int, float))
        ),
        1,
    )
    unrounded_score = round(score_total, 1)
    overall = round(score_total) if assessed_weight else 0
    coverage = round(assessed_weight / sum(int(row["weight"]) for row in LINK_DEFINITIONS.values()) * 100)
    if candidate_count:
        verdict = "provisional_material_leakage"
    elif overall >= 90:
        verdict = "healthy_with_confirmed_gaps"
    elif overall >= 70:
        verdict = "material_lifecycle_risk"
    else:
        verdict = "severe_lifecycle_risk"

    # Keep a dimension-shaped view for operator compatibility. The executive
    # report uses link_scores; this map is now a trace, not the headline math.
    dimension_scores = {
        link_id: {
            "max_points": row["weight"],
            "score": row["score"],
            "deducted": row["deducted"],
            "findings": row["evidence_measurements"],
        }
        for link_id, row in link_scores.items()
    }
    return {
        "scoring_method": "lifecycle_link_health_v2",
        "overall_lifecycle_integrity_score": overall,
        "score_baseline": total_weight if assessed_weight else 0,
        "unrounded_score": unrounded_score if assessed_weight else 0,
        "total_deducted": total_deducted if assessed_weight else 0,
        "score_display_note": (
            f"{total_weight} baseline - {total_deducted:g} total deductions "
            f"= {unrounded_score:g}; displayed as {overall}/100 after rounding."
            if assessed_weight
            else "No weighted lifecycle handoff was assessable."
        ),
        "mapping_confidence_score": registry.overall_confidence,
        "dimension_scores": dimension_scores,
        "journey_link_scores": link_scores,
        "assessed_weight": assessed_weight,
        "coverage_percentage": coverage,
        "coverage_label": _coverage_label(coverage),
        "confirmed_finding_count": confirmed_count,
        "unresolved_candidate_count": candidate_count,
        "verdict": verdict,
        "formula": (
            "Start at 100. Each lifecycle link has a fixed business weight. "
            "A confirmed break uses its affected share; an unresolved deterministic "
            "candidate uses half weight; overlapping measurements within one link "
            "are deduplicated by taking the highest affected share. Closed-lost "
            "recovery opportunities remain visible but do not move the score by themselves."
        ),
    }
