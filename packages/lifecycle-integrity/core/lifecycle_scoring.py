"""Deterministic, control-level lifecycle integrity scoring."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable

from .lifecycle_score_contract import (
    SCORE_CONTROL_DEFINITIONS,
    cited_measurement_ids,
    validate_scoring_contract,
)
from .lifecycle_schemas import JourneyPatternRegistry, LifecycleFinding


LINK_DEFINITIONS = {
    "intent_to_owner": {"label": "Intent to accountable owner", "weight": 20},
    "owner_to_deal": {"label": "Owner to deal or valid skip", "weight": 20},
    "deal_continuity": {
        "label": "Deal, account, contact, and source continuity",
        "weight": 20,
    },
    "deal_progression": {"label": "Open deal to next action", "weight": 25},
    "post_close_recovery": {
        "label": "Closed-lost/customer to recovery or renewal",
        "weight": 15,
    },
}

MINIMUM_REPORTABLE_COVERAGE = 70


def _measurement_statuses(
    findings: Iterable[LifecycleFinding], measurements: Iterable[dict[str, Any]]
) -> dict[str, str]:
    """Bind reviewer decisions to exact cited measurement IDs."""
    rows = list(measurements)
    known = {str(row.get("id") or "") for row in rows}
    primary_ids = {
        str(row.get("id") or "")
        for row in rows
        if row.get("score_role") == "primary"
    }
    statuses: dict[str, list[str]] = defaultdict(list)
    for finding in findings:
        cited = cited_measurement_ids(finding.evidence_refs, known)
        scored_citations = cited & primary_ids
        # One reviewer decision may confirm one canonical scored population.
        # Extra breakdown/supporting citations remain evidence context only.
        if len(scored_citations) != 1:
            continue
        for measurement_id in scored_citations:
            statuses[measurement_id].append(str(finding.review_status))

    resolved: dict[str, str] = {}
    for measurement_id, values in statuses.items():
        if any(value in {"approved", "revised"} for value in values):
            resolved[measurement_id] = "approved"
        elif any(value in {"pending", "human_confirmation"} for value in values):
            resolved[measurement_id] = "pending"
        elif values and all(value in {"rejected", "observation"} for value in values):
            resolved[measurement_id] = "rejected"
    return resolved


def _risk_multiplier(measurement_id: str, statuses: dict[str, str]) -> tuple[float, str]:
    status = statuses.get(measurement_id)
    if status in {"approved", "revised"}:
        return 1.0, "confirmed"
    if status in {"rejected", "observation"}:
        return 0.0, "not_counted"
    return 0.5, "review_candidate"


def _coverage_label(coverage: float) -> str:
    if coverage >= 95:
        return "assessed"
    if coverage >= 70:
        return "partially assessed"
    return "limited evidence"


def _control_assessment(
    control_id: str,
    rows: list[dict[str, Any]],
    statuses: dict[str, str],
    candidate_populations: set[str],
    confirmed_populations: set[str],
) -> dict[str, Any]:
    definition = SCORE_CONTROL_DEFINITIONS[control_id]
    weight = int(definition["weight"])
    primary = [
        row
        for row in rows
        if row.get("score_role") == "primary"
        and row.get("score_control") == control_id
    ]
    evidence = [
        {
            "measurement_id": row.get("id"),
            "population_key": row.get("score_population_key"),
            "denominator": row.get("denominator"),
            "affected_records": row.get("affected_records"),
            "affected_percentage": row.get("affected_percentage"),
            "available": row.get("available"),
        }
        for row in primary
    ]
    if not primary or any(not row.get("available") for row in primary):
        return {
            "control_id": control_id,
            "weight": weight,
            "assessed_weight": 0,
            "score": None,
            "deducted": None,
            "status": "not_assessable",
            "assessment_reason": "source_or_denominator_unavailable",
            "affected_percentage": None,
            "evidence_measurements": evidence,
        }

    denominators = [row.get("denominator") for row in primary]
    if any(
        not isinstance(value, (int, float)) or isinstance(value, bool)
        for value in denominators
    ):
        return {
            "control_id": control_id,
            "weight": weight,
            "assessed_weight": 0,
            "score": None,
            "deducted": None,
            "status": "not_assessable",
            "assessment_reason": "denominator_unavailable",
            "affected_percentage": None,
            "evidence_measurements": evidence,
        }

    total_denominator = sum(float(value) for value in denominators)
    if total_denominator <= 0:
        return {
            "control_id": control_id,
            "weight": weight,
            "assessed_weight": 0,
            "score": None,
            "deducted": None,
            "status": "not_assessable",
            "assessment_reason": "no_eligible_population",
            "affected_percentage": None,
            "evidence_measurements": evidence,
        }

    adjusted_affected = 0.0
    has_confirmed = False
    has_candidate = False
    for row, item in zip(primary, evidence):
        affected = float(row.get("affected_records") or 0)
        multiplier, state = _risk_multiplier(str(row.get("id") or ""), statuses)
        adjusted_affected += affected * multiplier
        item["status"] = state if affected > 0 else "healthy"
        item["risk_multiplier"] = multiplier if affected > 0 else 0.0
        if affected <= 0 or multiplier == 0:
            continue
        population_key = str(row.get("score_population_key"))
        if state == "confirmed":
            has_confirmed = True
            confirmed_populations.add(population_key)
        elif state == "review_candidate":
            has_candidate = True
            candidate_populations.add(population_key)

    risk = min(1.0, adjusted_affected / total_denominator)
    retained = round(weight * (1 - risk), 1)
    deducted = round(weight - retained, 1)
    if has_confirmed and has_candidate:
        status = "confirmed break with review candidates"
    elif has_confirmed:
        status = "confirmed break"
    elif has_candidate:
        status = "review candidate included provisionally"
    else:
        status = "healthy"
    return {
        "control_id": control_id,
        "weight": weight,
        "assessed_weight": weight,
        "score": retained,
        "deducted": deducted,
        "status": status,
        "assessment_reason": "assessed",
        "affected_percentage": round(risk * 100, 1),
        "population_denominator": round(total_denominator),
        "evidence_measurements": evidence,
    }


def compute_lifecycle_score(
    findings: Iterable[LifecycleFinding],
    registry: JourneyPatternRegistry,
    measurements: Iterable[dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Score observable controls; weight mutually exclusive motions by size."""
    raw_rows = list(measurements or [])
    contract_problems = validate_scoring_contract(raw_rows)
    if contract_problems:
        raise ValueError("invalid lifecycle scoring contract: " + "; ".join(contract_problems))
    rows = [row for row in raw_rows if isinstance(row, dict)]
    statuses = _measurement_statuses(list(findings), rows)
    candidate_populations: set[str] = set()
    confirmed_populations: set[str] = set()
    controls = {
        control_id: _control_assessment(
            control_id,
            rows,
            statuses,
            candidate_populations,
            confirmed_populations,
        )
        for control_id in SCORE_CONTROL_DEFINITIONS
    }

    link_scores: dict[str, dict[str, Any]] = {}
    for link_id, definition in LINK_DEFINITIONS.items():
        link_controls = [
            row
            for control_id, row in controls.items()
            if SCORE_CONTROL_DEFINITIONS[control_id]["link"] == link_id
        ]
        assessed = sum(int(row["assessed_weight"]) for row in link_controls)
        retained = round(
            sum(float(row.get("score") or 0) for row in link_controls), 1
        )
        deducted = round(
            sum(float(row.get("deducted") or 0) for row in link_controls), 1
        )
        opportunities = [
            row
            for row in rows
            if row.get("score_role") == "opportunity_only"
            and row.get("score_link") == link_id
            and row.get("available")
            and float(row.get("affected_records") or 0) > 0
        ]
        evidence = [
            item
            for control in link_controls
            for item in control["evidence_measurements"]
        ]
        evidence.extend(
            {
                "measurement_id": row.get("id"),
                "affected_percentage": row.get("affected_percentage"),
                "status": "opportunity_not_scored",
                "risk_multiplier": 0.0,
                "population_key": row.get("score_population_key"),
            }
            for row in opportunities
        )
        if assessed == 0:
            status = "not_assessable"
            reasons = {row["assessment_reason"] for row in link_controls}
            assessment_reason = (
                "scored_control_population_unavailable"
                if opportunities
                else "no_eligible_population"
                if reasons == {"no_eligible_population"}
                else "source_or_denominator_unavailable"
            )
        else:
            has_confirmed = any("confirmed break" in row["status"] for row in link_controls)
            has_candidate = any("review candidate" in row["status"] for row in link_controls)
            status = (
                "confirmed break with review candidates"
                if has_confirmed and has_candidate
                else "confirmed break"
                if has_confirmed
                else "review candidate included provisionally"
                if has_candidate
                else "recovery opportunity shown outside score"
                if opportunities and deducted == 0
                else "healthy"
            )
            if assessed < int(definition["weight"]):
                status = f"partially assessed; {status}"
            assessment_reason = "partially_assessed" if assessed < int(definition["weight"]) else "assessed"

        link_scores[link_id] = {
            "label": definition["label"],
            "weight": definition["weight"],
            "assessed_weight": assessed,
            "score": retained if assessed else None,
            "deducted": deducted if assessed else None,
            "status": status,
            "assessment_reason": assessment_reason,
            "affected_percentage": round(deducted / assessed * 100, 1) if assessed else None,
            "controls": link_controls,
            "evidence_measurements": evidence,
            "scoring_note": (
                "Motion populations inside a control are weighted by their denominators; each independent control is assessed only from its own evidence."
                if assessed
                else "No scored control in this handoff had a usable eligible population."
            ),
        }

    total_weight = sum(int(row["weight"]) for row in SCORE_CONTROL_DEFINITIONS.values())
    assessed_weight = sum(int(row["assessed_weight"]) for row in controls.values())
    score_total = round(sum(float(row.get("score") or 0) for row in controls.values()), 1)
    assessed_points_deducted = round(
        sum(float(row.get("deducted") or 0) for row in controls.values()), 1
    )
    coverage = round(assessed_weight / total_weight * 100)
    normalized_assessed_score = (
        round(score_total / assessed_weight * 100, 1) if assessed_weight else None
    )
    reportable = coverage >= MINIMUM_REPORTABLE_COVERAGE
    unrounded_score = normalized_assessed_score if reportable else None
    overall = round(normalized_assessed_score) if reportable else None
    total_deducted = round(100 - normalized_assessed_score, 1) if reportable else None
    if not reportable:
        verdict = "insufficient_evidence"
    elif candidate_populations:
        verdict = "provisional_material_leakage"
    elif overall is not None and overall >= 90:
        verdict = "healthy_with_confirmed_gaps"
    elif overall is not None and overall >= 70:
        verdict = "material_lifecycle_risk"
    else:
        verdict = "severe_lifecycle_risk"

    dimension_scores = {
        link_id: {
            "max_points": row["weight"],
            "assessed_points": row["assessed_weight"],
            "score": row["score"],
            "deducted": row["deducted"],
            "findings": row["evidence_measurements"],
        }
        for link_id, row in link_scores.items()
    }
    return {
        "scoring_method": "lifecycle_control_health_v4",
        "overall_lifecycle_integrity_score": overall,
        "score_baseline": 100 if reportable else None,
        "unrounded_score": unrounded_score,
        "total_deducted": total_deducted,
        "normalized_assessed_score": normalized_assessed_score,
        "assessed_points_retained": score_total,
        "assessed_points_deducted": assessed_points_deducted,
        "score_display_note": (
            f"100 baseline - {total_deducted:g} total normalized deductions = {unrounded_score:g}; "
            f"displayed as {overall}/100 after rounding. Based on {assessed_weight}/{total_weight} "
            f"weighted control points that were assessable ({coverage}% scored control coverage). "
            "Within a control, each motion is weighted by its eligible population size. "
            "Unavailable controls are excluded from both retained points and deductions."
            if reportable
            else f"No score issued: {assessed_weight}/{total_weight} weighted control points were assessable "
            f"({coverage}% scored control coverage), below the {MINIMUM_REPORTABLE_COVERAGE}% minimum. "
            "Missing evidence is not treated as lifecycle failure."
        ),
        "mapping_confidence_score": registry.overall_confidence,
        "dimension_scores": dimension_scores,
        "journey_link_scores": link_scores,
        "control_scores": controls,
        "assessed_weight": assessed_weight,
        "coverage_percentage": coverage,
        "coverage_label": _coverage_label(coverage),
        "confirmed_finding_count": len(confirmed_populations),
        "unresolved_candidate_count": len(candidate_populations),
        "verdict": verdict,
        "formula": (
            "Start at 100. Independent controls carry fixed weights. Mutually exclusive motion populations within one control are denominator-weighted. Confirmed breaks use their full affected records; unresolved candidates use half until review. Missing controls reduce score coverage rather than earning healthy points or creating deductions."
        ),
    }
