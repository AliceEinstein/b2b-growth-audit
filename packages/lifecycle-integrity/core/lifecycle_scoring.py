"""Deterministic lifecycle-integrity score arithmetic."""
from __future__ import annotations

from typing import Any, Dict, Iterable

from .lifecycle_schemas import JourneyPatternRegistry, LifecycleFinding

DIMENSION_POINTS = {
    "lifecycle_integrity": 20,
    "association_integrity": 20,
    "handoff_integrity": 20,
    "attribution_continuity": 20,
    "state_coherence": 10,
    "property_governance": 10,
}
SEVERITY_DEDUCTION = {
    "critical": 10,
    "high": 6,
    "medium": 3,
    "low": 1,
    "observation": 0,
}
COUNTED_STATUSES = {"approved", "revised"}


def compute_lifecycle_score(
    findings: Iterable[LifecycleFinding],
    registry: JourneyPatternRegistry,
) -> Dict[str, Any]:
    finding_list = list(findings)
    dimensions: Dict[str, Dict[str, Any]] = {
        name: {"max_points": points, "deducted": 0, "score": points, "findings": []}
        for name, points in DIMENSION_POINTS.items()
    }
    for finding in finding_list:
        if finding.review_status not in COUNTED_STATUSES:
            continue
        dimension = dimensions[finding.integrity_dimension]
        deduction = SEVERITY_DEDUCTION[finding.severity]
        dimension["deducted"] += deduction
        dimension["findings"].append(
            {"finding_id": finding.finding_id, "severity": finding.severity}
        )
    overall = 0
    for dimension in dimensions.values():
        dimension["deducted"] = min(dimension["deducted"], dimension["max_points"])
        dimension["score"] = dimension["max_points"] - dimension["deducted"]
        overall += dimension["score"]

    pattern_scores: Dict[str, int] = {}
    for pattern in registry.patterns:
        if not pattern.exists:
            continue
        deduction = sum(
            SEVERITY_DEDUCTION[f.severity]
            for f in finding_list
            if f.journey_pattern == pattern.journey_type
            and f.review_status in COUNTED_STATUSES
        )
        pattern_scores[pattern.journey_type] = max(0, 100 - deduction)
    return {
        "overall_lifecycle_integrity_score": overall,
        "mapping_confidence_score": registry.overall_confidence,
        "dimension_scores": dimensions,
        "pattern_scores": pattern_scores,
    }
