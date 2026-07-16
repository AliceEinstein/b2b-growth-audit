"""CRM Trust Score arithmetic (legacy CRM trust audit flow).

The lifecycle flow scores in lifecycle_scoring.py.

Severity is assigned by the LLM audit agents and confirmed through review
gates; this module only converts validated findings into deductions. The
LLM may explain the score but must not change it.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

from .schemas import Finding

CATEGORY_POINTS = {
    "attribution_trust": 25,
    "lifecycle_funnel": 20,
    "association_architecture": 20,
    "pipeline_hygiene": 20,
    "property_governance": 15,
}

SEVERITY_DEDUCTION = {"critical": 10, "high": 6, "medium": 3, "low": 1}

COUNTED_STATUSES = {"approved", "revised"}


def compute_score(findings: Iterable[Finding]) -> Dict[str, Any]:
    categories: Dict[str, Dict[str, Any]] = {
        name: {
            "max_points": points,
            "deducted": 0,
            "score": points,
            "counted_findings": [],
        }
        for name, points in CATEGORY_POINTS.items()
    }

    for finding in findings:
        if finding.module not in categories:
            raise ValueError(
                f"finding {finding.id!r} has unknown module {finding.module!r}"
            )
        if finding.review_status not in COUNTED_STATUSES:
            continue
        category = categories[finding.module]
        category["deducted"] += SEVERITY_DEDUCTION[finding.severity]
        category["counted_findings"].append(
            {"id": finding.id, "severity": finding.severity}
        )

    total = 0
    for category in categories.values():
        category["deducted"] = min(category["deducted"], category["max_points"])
        category["score"] = category["max_points"] - category["deducted"]
        total += category["score"]

    return {"total": total, "max_total": 100, "categories": categories}
