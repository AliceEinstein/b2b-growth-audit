"""Validation gates for lifecycle audit artifacts."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Tuple

from pydantic import ValidationError

from .adjudication import REQUIRED_REVIEWERS, adjudicate_findings, aggregate_review_status
from .automation_integrity import AUTOMATION_EVIDENCE_COLUMNS
from .journey_confidence import (
    JOURNEYS,
    audit_level,
    build_registry,
    confidence_label,
    score_components,
)
from .lifecycle_schemas import (
    JourneyPatternRegistry,
    LifecycleFinding,
    RecommendationPlan,
    ReviewDecision,
    RootCauseAssessmentsDoc,
)
from pydantic import ValidationError as _ValidationError
from .lifecycle_workspace import validate_agent_workspace
from .outliers import OUTLIER_COLUMNS, classify_outliers
from .validators import validate_snapshot_completed

REQUIRED_REPORT_SECTIONS = [
    "# HubSpot Lifecycle Integrity Audit",
    "## 1. Executive Decision Summary",
    "## 2. Detected Selling Journey Model",
    "## 3. Journey Evidence and Operating Paths",
    "## 4. Journey Leakage Map",
    "## 5. Pipeline Exposure and Recoverable Population",
    "## 6. Leakage Findings and Root Causes",
    "## 7. Recovery and System Repair Plan",
    "## 8. Monitoring and Next Review",
    "## 9. Evidence, Assumptions, and Limits",
]
REQUIRED_APPENDIX_SECTIONS = [
    "# Operator Appendix: Lifecycle Integrity Audit",
    "## Validated Findings",
    "## Implementation Detail",
    "## Journey and Measurement Detail",
    "## Technical CRM Profile",
    "## Method and Constraints",
    "## Supporting Files",
]
REQUIRED_HANDOFF_SECTIONS = [
    "# Agent Handoff: Lifecycle Integrity Audit Follow-up",
    "## Safety Boundary",
    "## Validated Findings",
    "## Low-Risk Follow-up Tasks",
    "## Manual Confirmation Required",
    "## Blocked Actions",
    "## Suggested Implementation Sequence",
    "## Evidence Files",
    "## Questions to Ask Human Owner Before Any Write Action",
]


def load_registry(run_dir: Path) -> Tuple[JourneyPatternRegistry | None, List[str]]:
    path = Path(run_dir) / "journey_pattern_registry.json"
    if not path.exists():
        return None, ["journey_pattern_registry.json not found"]
    try:
        registry = JourneyPatternRegistry.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, json.JSONDecodeError) as exc:
        return None, [f"journey_pattern_registry.json is invalid: {exc}"]
    problems = []
    journey_types = [pattern.journey_type for pattern in registry.patterns]
    if len(journey_types) != len(set(journey_types)):
        problems.append("journey_pattern_registry.json contains duplicate journey types")
    missing_journeys = sorted(set(JOURNEYS) - set(journey_types))
    extra_journeys = sorted(set(journey_types) - set(JOURNEYS))
    if missing_journeys:
        problems.append(f"journey_pattern_registry.json missing patterns: {', '.join(missing_journeys)}")
    if extra_journeys:
        problems.append(f"journey_pattern_registry.json has unknown patterns: {', '.join(extra_journeys)}")
    for pattern in registry.patterns:
        try:
            recomputed = score_components(pattern.evidence_components)
        except ValueError as exc:
            problems.append(f"{pattern.journey_type}: {exc}")
            continue
        if pattern.confidence_score != recomputed:
            problems.append(
                f"{pattern.journey_type}: confidence score {pattern.confidence_score} "
                f"does not match components ({recomputed})"
            )
        if pattern.confidence_label != confidence_label(recomputed):
            problems.append(f"{pattern.journey_type}: confidence label is inconsistent")
        if pattern.audit_level != audit_level(recomputed):
            problems.append(f"{pattern.journey_type}: audit level is inconsistent")
        if pattern.exists != (recomputed >= 30):
            problems.append(f"{pattern.journey_type}: exists flag is inconsistent")
    detected = [pattern for pattern in registry.patterns if pattern.confidence_score >= 30]
    auditable = [pattern for pattern in registry.patterns if pattern.confidence_score >= 50]
    expected_model = (
        "multi_motion"
        if len(auditable) >= 2
        else "single_motion"
        if detected
        else "insufficient_evidence"
    )
    if registry.primary_model != expected_model:
        problems.append(
            f"primary_model {registry.primary_model} does not match confidence evidence ({expected_model})"
        )
    expected_overall = (
        round(sum(pattern.confidence_score for pattern in detected) / len(detected))
        if detected
        else 0
    )
    if registry.overall_confidence != expected_overall:
        problems.append(
            f"overall_confidence {registry.overall_confidence} does not match detected-pattern mean ({expected_overall})"
        )
    evidence_store_path = Path(run_dir) / "processed" / "journey_evidence_store.json"
    if not evidence_store_path.exists():
        problems.append("processed/journey_evidence_store.json not found")
    else:
        try:
            evidence_store = json.loads(
                evidence_store_path.read_text(encoding="utf-8")
            )
            expected_registry = build_registry(evidence_store)
            if registry.model_dump() != expected_registry.model_dump():
                problems.append(
                    "journey_pattern_registry.json does not match deterministic "
                    "Journey Evidence Store recomputation"
                )
        except (json.JSONDecodeError, OSError, TypeError, ValidationError, ValueError) as exc:
            problems.append(f"journey evidence store is invalid: {exc}")
    return registry, problems


def load_findings(run_dir: Path) -> Tuple[List[LifecycleFinding], List[str]]:
    path = Path(run_dir) / "findings.json"
    if not path.exists():
        return [], ["findings.json not found"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("findings", []) if isinstance(data, dict) else data
        findings = [LifecycleFinding.model_validate(row) for row in rows]
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        return [], [f"findings.json is invalid: {exc}"]
    return findings, []


def validate_findings(run_dir: Path) -> List[str]:
    run_dir = Path(run_dir)
    registry, problems = load_registry(run_dir)
    findings, finding_problems = load_findings(run_dir)
    problems.extend(finding_problems)
    if registry is None:
        return problems
    patterns = {pattern.journey_type: pattern for pattern in registry.patterns}
    measurement_path = run_dir / "processed" / "lifecycle_integrity_measurements.json"
    if measurement_path.exists():
        try:
            measurement_doc = json.loads(measurement_path.read_text(encoding="utf-8"))
            if not isinstance(measurement_doc, dict) or not isinstance(
                measurement_doc.get("measurements"), list
            ):
                raise TypeError("measurements must be a JSON array")
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            problems.append(
                f"processed/lifecycle_integrity_measurements.json is invalid: {exc}"
            )
            measurement_doc = {"measurements": []}
    else:
        problems.append("processed/lifecycle_integrity_measurements.json not found")
        measurement_doc = {"measurements": []}
    measurements = {
        row.get("id"): row
        for row in measurement_doc.get("measurements", [])
        if row.get("id")
    }
    measurement_ids = set(measurements)
    evidence_rows: Dict[str, int] = {}
    evidence_path = run_dir / "evidence.csv"
    if evidence_path.exists():
        with evidence_path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                evidence_rows[row.get("finding_id", "")] = evidence_rows.get(row.get("finding_id", ""), 0) + 1
    for finding in findings:
        if finding.confidence_label != confidence_label(finding.confidence_score):
            problems.append(f"{finding.finding_id}: confidence label is inconsistent")
        expected_intensity = (
            "high"
            if finding.severity in {"critical", "high"}
            else "medium"
            if finding.severity == "medium"
            else "low"
        )
        if finding.review_intensity != expected_intensity:
            problems.append(
                f"{finding.finding_id}: {finding.severity} severity requires {expected_intensity} review intensity"
            )
        if finding.journey_pattern != "all_detected_journeys":
            pattern = patterns.get(finding.journey_pattern)
            if pattern is None:
                problems.append(f"{finding.finding_id}: unknown journey pattern")
            else:
                if pattern.confidence_score < 50 and finding.severity != "observation":
                    problems.append(
                        f"{finding.finding_id}: journey below 50 can only produce observations"
                    )
                if pattern.confidence_score < 70 and finding.severity == "critical":
                    problems.append(
                        f"{finding.finding_id}: critical severity is not allowed below high journey confidence"
                    )
        for ref in finding.evidence_refs:
            filename = ref.split("#", 1)[0]
            if not (run_dir / filename).exists():
                problems.append(f"{finding.finding_id}: missing evidence file {filename}")
        cited_measurements = [
            measurement_id
            for measurement_id in measurement_ids
            if any(measurement_id in ref for ref in finding.evidence_refs)
        ]
        if not cited_measurements:
            problems.append(f"{finding.finding_id}: no deterministic measurement cited")
        else:
            cited = [measurements[measurement_id] for measurement_id in cited_measurements]
            if finding.severity != "observation" and not any(
                evidence_rows.get(measurement_id, 0) > 0
                for measurement_id in cited_measurements
            ):
                problems.append(f"{finding.finding_id}: scored finding has no evidence row")
            if finding.denominator is not None and not any(
                row.get("denominator") == finding.denominator for row in cited
            ):
                problems.append(f"{finding.finding_id}: denominator does not match cited measurement")
            if finding.affected_records is not None and not any(
                row.get("affected_records") == finding.affected_records for row in cited
            ):
                problems.append(f"{finding.finding_id}: affected_records does not match cited measurement")
            if finding.affected_percentage is not None and not any(
                row.get("affected_percentage") == finding.affected_percentage for row in cited
            ):
                problems.append(f"{finding.finding_id}: affected_percentage does not match cited measurement")
    return problems


def validate_outlier_registry(run_dir: Path) -> List[str]:
    path = Path(run_dir) / "outlier_registry.csv"
    if not path.exists():
        return ["outlier_registry.csv not found"]
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames != OUTLIER_COLUMNS:
                return ["outlier_registry.csv columns do not match the contract"]
            actual = list(reader)
        expected = [
            {key: str(value) for key, value in row.model_dump().items()}
            for row in classify_outliers(Path(run_dir))
        ]
    except (OSError, ValueError, csv.Error) as exc:
        return [f"outlier_registry.csv is invalid: {exc}"]
    if actual != expected:
        return ["outlier_registry.csv does not match deterministic recomputation"]
    return []


def load_reviews(run_dir: Path) -> Tuple[List[ReviewDecision], List[str]]:
    path = Path(run_dir) / "review_trace.json"
    if not path.exists():
        return [], ["review_trace.json not found"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("reviews", []) if isinstance(data, dict) else data
        reviews = [ReviewDecision.model_validate(row) for row in rows]
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        return [], [f"review_trace.json is invalid: {exc}"]
    return reviews, []


def validate_reviews(run_dir: Path, *, final: bool = False) -> List[str]:
    findings, problems = load_findings(run_dir)
    reviews, review_problems = load_reviews(run_dir)
    problems.extend(review_problems)
    by_finding: Dict[str, List[ReviewDecision]] = {}
    for review in reviews:
        by_finding.setdefault(review.finding_id, []).append(review)
    known = {finding.finding_id for finding in findings}
    for review in reviews:
        if review.finding_id not in known:
            problems.append(f"review_trace.json: unknown finding {review.finding_id}")
    for finding in findings:
        rows = by_finding.get(finding.finding_id, [])
        latest: Dict[str, ReviewDecision] = {}
        seen = set()
        for row in sorted(rows, key=lambda item: item.revision_round):
            key = (row.reviewer, row.revision_round)
            if key in seen:
                problems.append(f"{finding.finding_id}: duplicate reviewer decision")
            seen.add(key)
            latest[row.reviewer] = row
        missing = REQUIRED_REVIEWERS[finding.review_intensity] - set(latest)
        if missing:
            problems.append(
                f"{finding.finding_id}: missing reviewers {', '.join(sorted(missing))}"
            )
        latest_rows = list(latest.values())
        if final and any(row.verdict == "needs_revision" for row in latest_rows):
            problems.append(f"{finding.finding_id}: unresolved needs_revision verdict")
        if latest_rows and not any(row.verdict == "needs_revision" for row in latest_rows):
            expected = aggregate_review_status(latest_rows)
            if expected == "approved" and any(row.revision_round == 1 for row in rows):
                expected = "revised"
            if finding.review_status not in {"pending", expected}:
                problems.append(
                    f"{finding.finding_id}: review_status {finding.review_status} does not match {expected}"
                )
    return problems


RECOMMENDATION_LANES = (
    "priority_actions",
    "safe_operational_actions",
    "human_confirmation_needed",
    "observations_to_monitor",
    "do_not_auto_fix",
)


def load_recommendation_plan(
    run_dir: Path,
) -> Tuple[RecommendationPlan | None, List[str]]:
    path = Path(run_dir) / "agent_workspace" / "recommendation_plan.json"
    if not path.exists():
        return None, ["agent_workspace/recommendation_plan.json not found"]
    try:
        plan = RecommendationPlan.model_validate_json(path.read_text(encoding="utf-8"))
    except (_ValidationError, json.JSONDecodeError) as exc:
        return None, [f"recommendation_plan.json is invalid: {exc}"]
    return plan, []


def validate_recommendation_plan(run_dir: Path) -> List[str]:
    """The plan must mirror the adjudicated action lanes exactly.

    The recommendation agent adds owner/outcome/ordering judgment, but which
    finding belongs to which lane is decided by the adjudication rules —
    a plan that omits, invents, or relocates findings is invalid.
    """
    plan, problems = load_recommendation_plan(run_dir)
    findings, finding_problems = load_findings(run_dir)
    reviews, review_problems = load_reviews(run_dir)
    if plan is None or finding_problems or review_problems:
        return problems + finding_problems + review_problems
    try:
        adjudicated = adjudicate_findings(findings, reviews)
    except ValueError as exc:
        return problems + [f"cannot adjudicate findings for plan check: {exc}"]
    expected_lanes = {
        row["finding_id"]: row["action_lane"]
        for row in adjudicated
        if row["action_lane"] in RECOMMENDATION_LANES
    }
    for lane in RECOMMENDATION_LANES:
        entries = getattr(plan, lane)
        cited = [entry.finding_id for entry in entries]
        for entry in entries:
            for field_name in (
                "target",
                "current_state",
                "desired_state",
                "approval_required",
                "success_measure",
            ):
                if not getattr(entry, field_name, ""):
                    problems.append(
                        f"recommendation_plan.json: {entry.finding_id} is missing {field_name}"
                    )
            if not entry.implementation_steps:
                problems.append(
                    f"recommendation_plan.json: {entry.finding_id} has no implementation_steps"
                )
            if not entry.evidence_refs:
                problems.append(
                    f"recommendation_plan.json: {entry.finding_id} has no evidence_refs"
                )
        for finding_id in cited:
            if finding_id not in expected_lanes:
                problems.append(
                    f"recommendation_plan.json: {lane} cites unknown or "
                    f"non-actionable finding {finding_id}"
                )
            elif expected_lanes[finding_id] != lane:
                problems.append(
                    f"recommendation_plan.json: {finding_id} belongs to "
                    f"{expected_lanes[finding_id]} per adjudication, not {lane}"
                )
        duplicated = {f for f in cited if cited.count(f) > 1}
        if duplicated:
            problems.append(
                f"recommendation_plan.json: duplicate entries in {lane}: "
                f"{', '.join(sorted(duplicated))}"
            )
    planned = {
        entry.finding_id
        for lane in RECOMMENDATION_LANES
        for entry in getattr(plan, lane)
    }
    for finding_id, lane in sorted(expected_lanes.items()):
        if finding_id not in planned:
            problems.append(
                f"recommendation_plan.json: adjudicated finding {finding_id} "
                f"is missing from lane {lane}"
            )
    return problems


def validate_report_structure(run_dir: Path) -> List[str]:
    problems = []
    for filename, sections in (
        ("lifecycle_integrity_report.md", REQUIRED_REPORT_SECTIONS),
        ("operator_appendix.md", REQUIRED_APPENDIX_SECTIONS),
        ("agent_handoff.md", REQUIRED_HANDOFF_SECTIONS),
    ):
        path = Path(run_dir) / filename
        if not path.exists():
            problems.append(f"{filename} not found")
            continue
        text = path.read_text(encoding="utf-8")
        for section in sections:
            if section not in text:
                problems.append(f"{filename}: missing section {section}")
    return problems


def validate_automation_artifacts(run_dir: Path) -> List[str]:
    """Validate the sanitized automation layer without reading raw payloads."""
    run_dir = Path(run_dir)
    problems: List[str] = []
    required = [
        "processed/automation_coverage.json",
        "processed/workflow_inventory.json",
        "processed/workflow_dependency_graph.json",
        "processed/workflow_performance_summary.json",
        "processed/scoring_activation_summary.json",
        "processed/automation_scoring_measurements.json",
        "automation_evidence.csv",
    ]
    missing = [name for name in required if not (run_dir / name).exists()]
    problems.extend(f"missing automation artifact: {name}" for name in missing)
    if missing:
        return problems
    try:
        coverage = json.loads(
            (run_dir / "processed" / "automation_coverage.json").read_text(
                encoding="utf-8"
            )
        )
        if coverage.get("status") not in {
            "full",
            "partial",
            "configuration_only",
            "unavailable",
            "permission_denied",
        }:
            problems.append("automation coverage status is invalid")
        measurements = json.loads(
            (run_dir / "processed" / "automation_scoring_measurements.json").read_text(
                encoding="utf-8"
            )
        )
        if not isinstance(measurements, dict) or not isinstance(
            measurements.get("root_cause_links"), list
        ):
            problems.append("automation_scoring_measurements.json has invalid root_cause_links")
    except (OSError, json.JSONDecodeError, AttributeError, TypeError) as exc:
        problems.append(f"automation JSON artifact is invalid: {exc}")
    try:
        with (run_dir / "automation_evidence.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != AUTOMATION_EVIDENCE_COLUMNS:
                problems.append("automation_evidence.csv columns are invalid")
            for row in reader:
                if not row.get("measurement_id") or not row.get("evidence_id"):
                    problems.append("automation_evidence.csv contains an untraceable row")
                    break
    except (OSError, csv.Error) as exc:
        problems.append(f"automation_evidence.csv is invalid: {exc}")
    problems.extend(validate_root_cause_assessments(run_dir))
    return problems


def validate_root_cause_assessments(run_dir: Path) -> List[str]:
    """Enforce cross-artifact references for the automation root-cause role."""
    run_dir = Path(run_dir)
    path = run_dir / "agent_workspace" / "root_cause" / "automation_root_cause_agent.json"
    if not path.exists():
        return ["automation_root_cause_agent.json not found"]
    try:
        document = RootCauseAssessmentsDoc.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        return [f"automation_root_cause_agent.json is invalid: {exc}"]

    problems: List[str] = []
    findings, finding_problems = load_findings(run_dir)
    if finding_problems:
        problems.extend(
            f"root-cause cross-reference unavailable: {problem}"
            for problem in finding_problems
        )
    finding_ids = {finding.finding_id for finding in findings}

    workflow_path = run_dir / "processed" / "workflow_inventory.json"
    score_path = run_dir / "processed" / "scoring_activation_summary.json"
    try:
        workflows = json.loads(workflow_path.read_text(encoding="utf-8"))
        score_summary = json.loads(score_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return problems + [f"root-cause reference artifacts are invalid: {exc}"]
    if not isinstance(workflows, list):
        problems.append("workflow_inventory.json must contain a list")
        workflows = []
    if not isinstance(score_summary, dict):
        problems.append("scoring_activation_summary.json must contain an object")
        score_summary = {}

    workflow_aliases = {
        str(row.get("workflow_alias"))
        for row in workflows
        if isinstance(row, dict) and row.get("workflow_alias")
    }
    score_fields = {
        str(row.get("field"))
        for row in score_summary.get("score_candidates", [])
        if isinstance(row, dict) and row.get("field")
    }
    automation_measurement_ids: set[str] = set()
    evidence_path = run_dir / "automation_evidence.csv"
    try:
        with evidence_path.open(encoding="utf-8", newline="") as handle:
            automation_measurement_ids = {
                str(row.get("measurement_id"))
                for row in csv.DictReader(handle)
                if row.get("measurement_id")
            }
    except (OSError, csv.Error) as exc:
        problems.append(f"cannot read automation evidence for root-cause checks: {exc}")

    allowed_evidence_files = {
        "automation_evidence.csv",
        "evidence.csv",
        "processed/automation_scoring_measurements.json",
        "processed/lifecycle_integrity_measurements.json",
        "processed/scoring_activation_summary.json",
        "processed/workflow_inventory.json",
    }
    for assessment in document.assessments:
        prefix = f"root-cause {assessment.finding_id}"
        if assessment.finding_id not in finding_ids:
            problems.append(f"{prefix}: finding_id is not present in findings.json")
        unknown_aliases = sorted(set(assessment.workflow_aliases) - workflow_aliases)
        if unknown_aliases:
            problems.append(
                f"{prefix}: unknown workflow aliases {', '.join(unknown_aliases)}"
            )
        unknown_score_fields = sorted(set(assessment.score_fields) - score_fields)
        if unknown_score_fields:
            problems.append(
                f"{prefix}: unknown score fields {', '.join(unknown_score_fields)}"
            )
        for reference in assessment.evidence_refs:
            reference_path, _, fragment = str(reference).partition("#")
            path_obj = Path(reference_path)
            if (
                not reference_path
                or path_obj.is_absolute()
                or ".." in path_obj.parts
                or reference_path not in allowed_evidence_files
            ):
                problems.append(f"{prefix}: evidence ref is outside the allowlist: {reference}")
                continue
            if not (run_dir / reference_path).exists():
                problems.append(f"{prefix}: missing evidence file {reference_path}")
            if reference_path == "automation_evidence.csv":
                if not fragment.startswith("measurement_id="):
                    problems.append(
                        f"{prefix}: automation evidence ref must identify a measurement"
                    )
                else:
                    measurement_id = fragment.split("=", 1)[1]
                    if measurement_id not in automation_measurement_ids:
                        problems.append(
                            f"{prefix}: automation evidence measurement does not exist: {measurement_id}"
                        )
    return problems


def validate_lifecycle_run(run_dir: Path, *, final: bool = False) -> Dict[str, List[str]]:
    run_dir = Path(run_dir)
    _, registry_problems = load_registry(run_dir)
    return {
        "snapshot": validate_snapshot_completed(run_dir),
        "registry": registry_problems,
        "findings": validate_findings(run_dir),
        "reviews": validate_reviews(run_dir, final=final),
        "outliers": validate_outlier_registry(run_dir),
        "workspace": validate_agent_workspace(run_dir, require_complete=final),
        "recommendation_plan": (
            validate_recommendation_plan(run_dir)
            if final
            or (run_dir / "agent_workspace" / "recommendation_plan.json").exists()
            else []
        ),
        "reports": validate_report_structure(run_dir) if final else [],
        "automation": validate_automation_artifacts(run_dir) if final else [],
    }
