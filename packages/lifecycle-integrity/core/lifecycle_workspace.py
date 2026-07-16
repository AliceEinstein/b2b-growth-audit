"""Deterministic validation of the multi-agent judgment workspace.

The source of truth for what must exist is the code-owned task list in
lifecycle_agent_tasks.TASKS — never the task_manifest.json stored in the run
directory. The stored copy exists so agents can read their contracts; editing
it cannot change what these gates enforce, and any divergence from the
code-owned contract is itself a validation failure.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from .lifecycle_agent_tasks import TASKS, expected_manifest_contract
from .lifecycle_schemas import (
    AnalysisResult,
    AutomationAnalysisResult,
    CandidateFindingsDoc,
    JourneyHypothesis,
    MixedMotionAssessment,
    RecommendationPlan,
    ReviewDecisionsDoc,
    RootCauseAssessmentsDoc,
)

PHASE_ORDER = ["analysis", "hypothesis", "audit", "root_cause", "review", "recommendation", "report"]

# The report task's output is written by the deterministic final gate itself,
# so it is never a precondition for running that gate.
GATE_OWNED_SCHEMAS = {"deterministic_report_and_gate"}

SCHEMA_MODELS = {
    "analysis_result": AnalysisResult,
    "automation_analysis_result": AutomationAnalysisResult,
    "journey_hypothesis": JourneyHypothesis,
    "mixed_motion_assessment": MixedMotionAssessment,
    "candidate_findings": CandidateFindingsDoc,
    "root_cause_assessments": RootCauseAssessmentsDoc,
    "review_decisions": ReviewDecisionsDoc,
    "recommendation_lanes": RecommendationPlan,
}

# Phase prerequisites that live outside the workspace: reviewers read the
# consolidated findings.json, and the recommendation agent reads the
# consolidated review_trace.json.
PHASE_PREREQUISITES = {
    "root_cause": ["findings.json"],
    "review": ["findings.json"],
    "recommendation": ["findings.json", "review_trace.json"],
    "report": ["findings.json", "review_trace.json"],
}


def load_task_manifest(run_dir: Path) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Load the stored manifest and verify it matches the code-owned contract."""
    path = Path(run_dir) / "agent_workspace" / "task_manifest.json"
    if not path.exists():
        return None, ["agent_workspace/task_manifest.json not found"]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return None, [f"agent_workspace/task_manifest.json is invalid: {exc}"]
    problems = []
    expected = expected_manifest_contract()
    for key, value in expected.items():
        if manifest.get(key) != value:
            problems.append(
                f"agent_workspace/task_manifest.json field {key!r} does not "
                "match the code-owned task contract; regenerate it with "
                "write_agent_task_manifest instead of editing it"
            )
    return manifest, problems


def _validate_task_output(run_dir: Path, task: Dict[str, Any]) -> List[str]:
    schema = task.get("output_schema")
    if schema in GATE_OWNED_SCHEMAS:
        return []
    model = SCHEMA_MODELS.get(schema)
    if model is None:
        return [f"{task['output']}: unknown output schema {schema!r}"]
    output = Path(run_dir) / task["output"]
    try:
        data = json.loads(output.read_text(encoding="utf-8"))
        parsed = model.model_validate(data)
    except (json.JSONDecodeError, OSError, ValidationError) as exc:
        return [f"{task['output']} does not satisfy schema {schema}: {exc}"]
    problems = []
    declared_role = task.get("role")
    emitted_role = getattr(parsed, "role", None)
    if emitted_role is not None and declared_role and emitted_role != declared_role:
        problems.append(
            f"{task['output']}: role {emitted_role!r} does not match "
            f"declared task role {declared_role!r}"
        )
    if schema == "review_decisions" and declared_role:
        # Reviewer isolation: a reviewer artifact may carry only that
        # reviewer's own decisions.
        foreign = sorted(
            {
                review.reviewer
                for review in parsed.reviews
                if review.reviewer != declared_role
            }
        )
        if foreign:
            problems.append(
                f"{task['output']}: contains decisions attributed to "
                f"{', '.join(foreign)}; each reviewer writes only its own"
            )
    return problems


def validate_agent_workspace(
    run_dir: Path, *, require_complete: bool = False
) -> List[str]:
    """Validate workspace artifacts against the code-owned task list.

    Existing artifacts are always schema-checked. With ``require_complete``
    (the final gate), every non-gate task must also have produced its output.
    The stored manifest is additionally checked for tampering.
    """
    run_dir = Path(run_dir)
    _, problems = load_task_manifest(run_dir)
    for task in TASKS:
        if task.get("output_schema") in GATE_OWNED_SCHEMAS:
            continue
        output = run_dir / task["output"]
        if not output.exists():
            if require_complete:
                problems.append(
                    f"missing workspace artifact for {task.get('role')}: {task['output']}"
                )
            continue
        problems.extend(_validate_task_output(run_dir, task))
    # Harness journal: side-door writes and post-commit edits are detected
    # here; at the final gate the journal itself is mandatory.
    from .harness import verify_journal

    problems.extend(verify_journal(run_dir, require_complete=require_complete))
    return problems


def task_status(run_dir: Path, task: Dict[str, Any]) -> str:
    """``done`` | ``invalid`` | ``blocked`` | ``ready`` for one code-owned task."""
    run_dir = Path(run_dir)
    if task.get("output_schema") in GATE_OWNED_SCHEMAS:
        return "gate_owned"
    output = run_dir / task["output"]
    if output.exists():
        return "invalid" if _validate_task_output(run_dir, task) else "done"
    for prerequisite in PHASE_PREREQUISITES.get(task.get("phase", ""), []):
        if not (run_dir / prerequisite).exists():
            return "blocked"
    return "ready"


def next_tasks(run_dir: Path) -> Tuple[Optional[str], List[Dict[str, Any]], List[str]]:
    """Return the earliest incomplete phase, its pending tasks, and problems.

    Tasks come from the code-owned list; the stored manifest is only checked
    for tampering. A phase is not offered until every task of every earlier
    phase is done, mirroring the orchestrator's dispatch order.
    """
    _, problems = load_task_manifest(run_dir)
    by_phase: Dict[str, List[Dict[str, Any]]] = {}
    for task in TASKS:
        by_phase.setdefault(task.get("phase", "unknown"), []).append(task)
    for phase in PHASE_ORDER:
        pending = []
        for task in by_phase.get(phase, []):
            status = task_status(run_dir, task)
            if status == "gate_owned":
                continue
            if status == "invalid":
                problems.extend(_validate_task_output(run_dir, task))
                pending.append(task)
            elif status != "done":
                pending.append(task)
        if pending:
            return phase, pending, problems
    return None, [], problems
