"""Rule-based lifecycle finding adjudication."""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List

from .lifecycle_schemas import LifecycleFinding, ReviewDecision

REQUIRED_REVIEWERS = {
    "low": {"privacy_safety_reviewer"},
    "medium": {"data_fidelity_reviewer", "logic_reviewer", "privacy_safety_reviewer"},
    "high": {
        "data_fidelity_reviewer",
        "journey_mapping_skeptic",
        "logic_reviewer",
        "false_positive_reviewer",
        "privacy_safety_reviewer",
    },
}


def aggregate_review_status(decisions: Iterable[ReviewDecision]) -> str:
    verdicts = [decision.verdict for decision in decisions]
    if "rejected" in verdicts:
        return "rejected"
    if "needs_revision" in verdicts:
        return "needs_revision"
    if "requires_human_confirmation" in verdicts:
        return "human_confirmation"
    if "downgrade_to_observation" in verdicts:
        return "observation"
    return "approved"


def action_lane(finding: LifecycleFinding, status: str) -> str:
    if status == "rejected":
        return "rejected"
    if status == "needs_revision":
        return "needs_revision"
    if status == "observation" or finding.severity == "observation":
        return "observations_to_monitor"
    if status == "human_confirmation" or finding.recommendation_type == "requires_human_confirmation":
        return "human_confirmation_needed"
    if finding.recommendation_type == "do_not_auto_fix":
        return "do_not_auto_fix"
    if finding.severity in {"critical", "high"}:
        return "priority_actions"
    return "safe_operational_actions"


def adjudicate_findings(
    findings: Iterable[LifecycleFinding],
    decisions: Iterable[ReviewDecision],
) -> List[Dict[str, Any]]:
    by_finding: Dict[str, List[ReviewDecision]] = {}
    for decision in decisions:
        by_finding.setdefault(decision.finding_id, []).append(decision)
    result = []
    for finding in findings:
        reviews = by_finding.get(finding.finding_id, [])
        required = REQUIRED_REVIEWERS[finding.review_intensity]
        latest_by_reviewer: Dict[str, ReviewDecision] = {}
        for review in sorted(reviews, key=lambda item: item.revision_round):
            latest_by_reviewer[review.reviewer] = review
        latest_reviews = list(latest_by_reviewer.values())
        present = set(latest_by_reviewer)
        missing = sorted(required - present)
        if missing:
            raise ValueError(
                f"{finding.finding_id} missing required reviewers: {', '.join(missing)}"
            )
        counts = Counter((r.reviewer, r.revision_round) for r in reviews)
        duplicates = [key for key, count in counts.items() if count > 1]
        if duplicates:
            raise ValueError(f"duplicate reviewer decisions for {finding.finding_id}")
        status = aggregate_review_status(latest_reviews)
        if status == "approved" and any(review.revision_round == 1 for review in reviews):
            status = "revised"
        item = finding.model_dump()
        item["review_status"] = status
        item["action_lane"] = action_lane(finding, status)
        result.append(item)
    return result
