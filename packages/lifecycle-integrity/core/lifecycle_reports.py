"""Deterministic assembly of lifecycle audit deliverables."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List

from connectors.hubspot.normalize import write_json

from .adjudication import adjudicate_findings
from .automation_integrity import build_automation_integrity_artifacts
from .lifecycle_human_report import (
    build_view,
    render_html,
    render_markdown,
    render_operator_appendix,
)
from .lifecycle_schemas import JourneyPatternRegistry, LifecycleFinding, ReviewDecision
from .lifecycle_scoring import compute_lifecycle_score
from .lifecycle_validators import (
    load_findings,
    load_recommendation_plan,
    load_registry,
    load_reviews,
    validate_findings,
    validate_measurement_scoring_contract,
    validate_recommendation_plan,
    validate_reviews,
)


def _items(
    rows: Iterable[dict],
    *,
    use_action: bool = False,
    plan_entries: dict | None = None,
) -> List[str]:
    field = "recommended_action" if use_action else "business_impact"
    rows = list(rows)
    if plan_entries:
        # The recommendation agent owns ordering, owner, and expected outcome;
        # which findings appear here was already fixed by adjudication.
        order = {finding_id: i for i, finding_id in enumerate(plan_entries)}
        rows.sort(key=lambda row: order.get(row["finding_id"], len(order)))
    values = []
    for row in rows:
        line = f"- {row['finding_id']}: {row[field]}"
        entry = (plan_entries or {}).get(row["finding_id"])
        if entry is not None:
            line += (
                f" (owner: {entry.owner_role}; "
                f"expected outcome: {entry.expected_outcome})"
            )
        values.append(line)
    return values or ["- None."]


def generate_lifecycle_reports(run_dir: Path) -> Dict[str, object]:
    run_dir = Path(run_dir)
    # Keep the report path deterministic for both live snapshots and legacy
    # example runs.  When the token has no automation scope, this produces
    # explicit unavailable/empty artifacts and leaves the lifecycle score and
    # seven-section report contract unchanged.
    build_automation_integrity_artifacts(run_dir)
    registry, registry_problems = load_registry(run_dir)
    findings, finding_problems = load_findings(run_dir)
    reviews, review_problems = load_reviews(run_dir)
    problems = (
        registry_problems
        + finding_problems
        + review_problems
        + validate_findings(run_dir)
        + validate_measurement_scoring_contract(run_dir)
        + validate_reviews(run_dir, final=True)
        + validate_recommendation_plan(run_dir)
    )
    if registry is None or problems:
        raise ValueError("cannot generate reports: " + "; ".join(problems))
    plan, _ = load_recommendation_plan(run_dir)
    plan_by_lane = {
        lane: {entry.finding_id: entry for entry in getattr(plan, lane)}
        for lane in (
            "priority_actions",
            "safe_operational_actions",
            "human_confirmation_needed",
            "observations_to_monitor",
            "do_not_auto_fix",
        )
    }
    adjudicated = adjudicate_findings(findings, reviews)
    finalized_findings = [LifecycleFinding.model_validate({k: v for k, v in row.items() if k != "action_lane"}) for row in adjudicated]
    write_json(run_dir / "findings.json", {"findings": adjudicated})
    measurement_doc = json.loads(
        (run_dir / "processed" / "lifecycle_integrity_measurements.json").read_text(
            encoding="utf-8"
        )
    )
    score = compute_lifecycle_score(
        finalized_findings,
        registry,
        measurement_doc.get("measurements", []),
    )
    write_json(run_dir / "lifecycle_score.json", score)

    lanes: Dict[str, List[dict]] = {}
    for row in adjudicated:
        lanes.setdefault(row["action_lane"], []).append(row)
    pattern_rows = [pattern for pattern in registry.patterns if pattern.exists]
    view = build_view(run_dir, score, registry, adjudicated, plan_by_lane)
    markdown_text = render_markdown(view)
    (run_dir / "lifecycle_integrity_report.md").write_text(markdown_text, encoding="utf-8")
    (run_dir / "lifecycle_integrity_report.html").write_text(
        render_html(view, markdown_text), encoding="utf-8"
    )
    (run_dir / "operator_appendix.md").write_text(
        render_operator_appendix(view), encoding="utf-8"
    )

    journey_map = ["# Revenue Journey Map", ""]
    for pattern in pattern_rows:
        journey_map.extend(
            [
                f"## {pattern.journey_type}",
                "",
                f"Confidence: {pattern.confidence_score}/100 ({pattern.confidence_label})",
                "",
                "Observed evidence:",
                *([f"- {item}" for item in pattern.supporting_evidence] or ["- No positive evidence recorded."]),
                "",
                "Contradictions and limits:",
                *([f"- {item}" for item in pattern.contradicting_evidence] or ["- None recorded."]),
                "",
            ]
        )
    (run_dir / "journey_map.md").write_text("\n".join(journey_map) + "\n", encoding="utf-8")

    recommendations = ["# Lifecycle Integrity Recommendations", ""]
    for lane, heading in (
        ("priority_actions", "Priority Actions"),
        ("safe_operational_actions", "Safe Operational Actions"),
        ("human_confirmation_needed", "Human Confirmation Needed"),
        ("observations_to_monitor", "Observations to Monitor"),
        ("do_not_auto_fix", "Do Not Auto-Fix"),
    ):
        recommendations.extend(
            [
                f"## {heading}",
                "",
                *_items(
                    lanes.get(lane, []),
                    use_action=True,
                    plan_entries=plan_by_lane[lane],
                ),
                "",
            ]
        )
    (run_dir / "recommendations.md").write_text("\n".join(recommendations), encoding="utf-8")

    handoff = [
        "# Agent Handoff: Lifecycle Integrity Audit Follow-up",
        "",
        "## Safety Boundary",
        "",
        "This audit was generated in read-only mode. Do not perform CRM write actions unless the user explicitly grants write access and approves a fix plan.",
        "",
        "## Validated Findings",
        "",
        *_items([row for row in adjudicated if row["review_status"] in {"approved", "revised"}]),
        "",
        "## Low-Risk Follow-up Tasks",
        "",
        *_items(lanes.get("safe_operational_actions", []), use_action=True, plan_entries=plan_by_lane["safe_operational_actions"]),
        "",
        "## Manual Confirmation Required",
        "",
        *_items(lanes.get("human_confirmation_needed", []), use_action=True, plan_entries=plan_by_lane["human_confirmation_needed"]),
        "",
        "## Blocked Actions",
        "",
        "- Do not overwrite original source, merge records, delete properties, reset lifecycle stages, move deal stages, or reassign owners automatically.",
        "",
        "## Suggested Implementation Sequence",
        "",
        "1. Confirm canonical business rules.\n2. Export a review list.\n3. Approve a separate implementation plan before any write access.",
        "",
        "## Evidence Files",
        "",
        "- `evidence.csv`\n- `outlier_registry.csv`\n- `journey_pattern_registry.json`",
        "",
        "## Questions to Ask Human Owner Before Any Write Action",
        "",
        "- Which source, lifecycle, deal-type, and pipeline fields are canonical?\n- Which journeys intentionally skip MQL?\n- Which exceptions are valid business behavior?",
    ]
    (run_dir / "agent_handoff.md").write_text("\n".join(handoff) + "\n", encoding="utf-8")
    return {"score": score, "findings": adjudicated, "lanes": lanes}
