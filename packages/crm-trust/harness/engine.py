"""Execution engine for the BYO Agent mode.

The engine performs deterministic work itself and pauses at agent stages by
writing a task packet.  A host agent writes the declared artifact, then calls
``advance`` again; the engine validates it before unlocking dependants.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from connectors.hubspot.normalize import write_json
from core.final_gate import run_final_gate
from core.profiler import profile_run
from core.rules import MODULES, measure_all
from core.safety import FINAL_DELIVERABLES, scan_deliverables
from core.schemas import CrmContext
from core.scoring import compute_score
from core.validators import (
    REVIEWERS,
    aggregate_verdicts,
    load_all_findings,
    validate_findings,
    validate_phase3_artifacts,
    validate_reviews,
)
from scripts.generate_reports import consolidate_evidence

from .render import render_reports
from .state import (
    RunState,
    stage_input_hash,
    stage_output_hash,
    state_path,
)
from .task_packets import create_task_packet
from .validation import validate_stage_output
from .workflow import STAGES, StageSpec

MAX_ATTEMPTS = 3


def ensure_run(run_dir: Path) -> RunState:
    run_dir = Path(run_dir).resolve()
    if not run_dir.is_dir():
        raise FileNotFoundError("run directory not found: " + str(run_dir))
    (run_dir / "harness" / "tasks").mkdir(parents=True, exist_ok=True)
    (run_dir / "harness" / "agent_outputs" / "reviews").mkdir(parents=True, exist_ok=True)
    state = RunState.load_or_initialize(run_dir)
    _import_legacy_reviews(run_dir)
    state.save(run_dir)
    return state


def _import_legacy_reviews(run_dir: Path) -> None:
    """Make old shared review_log.json usable by the new isolated review tasks."""
    source = run_dir / "review_log.json"
    target_dir = run_dir / "harness" / "agent_outputs" / "reviews"
    if not source.exists():
        return
    try:
        entries = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(entries, list):
        return
    for reviewer in REVIEWERS:
        target = target_dir / (reviewer + ".json")
        if target.exists():
            continue
        scoped = [entry for entry in entries if isinstance(entry, dict) and entry.get("reviewer") == reviewer]
        if scoped:
            target.write_text(json.dumps(scoped, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _outputs_exist(run_dir: Path, stage: StageSpec) -> bool:
    return bool(stage.output_paths) and all(
        (run_dir / relative).is_file() for relative in stage.output_paths
    )


def _record_success(run_dir: Path, state: RunState, stage: StageSpec, status: str = "passed") -> None:
    state.record(
        stage.id,
        status,
        input_hash=stage_input_hash(run_dir, stage),
        output_hash=stage_output_hash(run_dir, stage),
        last_error=None,
    )


def _record_failure(state: RunState, stage: StageSpec, problems: List[str]) -> None:
    state.record(stage.id, "failed", last_error="; ".join(problems[:20]))


def _run_measurements(run_dir: Path) -> None:
    phase3 = validate_phase3_artifacts(run_dir)
    problems = [problem for values in phase3.values() for problem in values]
    if problems:
        raise ValueError("phase 3 artifacts are not valid: " + "; ".join(problems))
    context = CrmContext.model_validate(
        yaml.safe_load((run_dir / "crm_context.yaml").read_text(encoding="utf-8"))
    )
    results = measure_all(run_dir, context)
    measurements_dir = run_dir / "processed" / "measurements"
    measurements_dir.mkdir(parents=True, exist_ok=True)
    for module, document in results.items():
        write_json(measurements_dir / (module + ".json"), document)
    (run_dir / "findings").mkdir(exist_ok=True)


def _aggregate_reviews(run_dir: Path) -> None:
    review_dir = run_dir / "harness" / "agent_outputs" / "reviews"
    entries: List[Dict[str, Any]] = []
    for reviewer in REVIEWERS:
        path = review_dir / (reviewer + ".json")
        if not path.exists():
            raise ValueError("missing isolated review artifact: " + str(path))
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(str(path) + " must contain a JSON array")
        entries.extend(raw)

    # review_log.json is code-owned aggregation.  Individual reviewers never
    # race to append to this shared file.
    write_json(run_dir / "review_log.json", entries)
    for module in MODULES:
        path = run_dir / "findings" / (module + "_findings.json")
        document = json.loads(path.read_text(encoding="utf-8"))
        for finding in document.get("findings", []):
            verdicts = [
                entry["verdict"]
                for entry in entries
                if entry.get("finding_id") == finding.get("id")
            ]
            if verdicts:
                finding["review_status"] = aggregate_verdicts(verdicts)
        write_json(path, document)


def _consolidate(run_dir: Path) -> None:
    problems = [problem for values in validate_findings(run_dir).values() for problem in values]
    problems.extend(validate_reviews(run_dir))
    if problems:
        raise ValueError("cannot consolidate before validation passes: " + "; ".join(problems))
    findings, finding_problems = load_all_findings(run_dir)
    if finding_problems:
        raise ValueError("cannot load findings: " + "; ".join(finding_problems))
    write_json(run_dir / "findings.json", {"findings": [finding.model_dump() for finding in findings]})
    write_json(run_dir / "score.json", compute_score(findings))
    consolidate_evidence(run_dir)


def _deterministic_stage(run_dir: Path, state: RunState, stage: StageSpec) -> None:
    if stage.id == "profile":
        profile_run(run_dir)
    elif stage.id == "measurements":
        _run_measurements(run_dir)
    elif stage.id == "findings_validation":
        problems = [problem for values in validate_findings(run_dir).values() for problem in values]
        if problems:
            raise ValueError("findings validation failed: " + "; ".join(problems))
    elif stage.id == "reviews_validation":
        _aggregate_reviews(run_dir)
        problems = validate_reviews(run_dir)
        if problems:
            raise ValueError("review validation failed: " + "; ".join(problems))
    elif stage.id == "consolidate":
        _consolidate(run_dir)
    elif stage.id == "render_reports":
        render_reports(run_dir)
    elif stage.id == "final_gate":
        document = run_final_gate(run_dir)
        if not document.get("passed"):
            problems = [problem for values in document.get("problems", {}).values() for problem in values]
            problems.extend("hard leak: " + str(item.get("kind")) for item in document.get("hard_leaks", []))
            problems.extend("uncleared phrase: " + str(item.get("phrase")) for item in document.get("uncleared_phrases", []))
            raise ValueError("final gate failed: " + "; ".join(problems))
    elif stage.id == "snapshot":
        problems = validate_stage_output(run_dir, stage.id)
        if problems:
            raise ValueError("snapshot gate failed: " + "; ".join(problems))
    else:
        raise ValueError("no deterministic executor for stage " + stage.id)


def _privacy_clearance_needed(run_dir: Path) -> bool:
    return any(not hit.hard for hit in scan_deliverables(run_dir))


def _handle_conditional_privacy(run_dir: Path, state: RunState, stage: StageSpec) -> bool:
    if stage.id != "privacy_clearance":
        return False
    if not _privacy_clearance_needed(run_dir):
        _record_success(run_dir, state, stage, status="skipped")
        return True
    return False


def _handle_agent(run_dir: Path, state: RunState, stage: StageSpec) -> None:
    current = state.stage(stage.id)
    if current.status == "failed" and current.attempts >= MAX_ATTEMPTS:
        return
    if _outputs_exist(run_dir, stage):
        problems = validate_stage_output(run_dir, stage.id)
        if not problems:
            _record_success(run_dir, state, stage)
            return
        if current.attempts >= MAX_ATTEMPTS:
            _record_failure(state, stage, problems)
            return
        current.attempts += 1
        state.record(stage.id, "ready", last_error="; ".join(problems[:20]))
        create_task_packet(run_dir, stage, state, errors=problems)
        return

    if current.status == "ready" and current.task_file:
        return
    current.attempts += 1
    current.input_hash = stage_input_hash(run_dir, stage)
    state.record(stage.id, "ready", input_hash=current.input_hash)
    create_task_packet(run_dir, stage, state)


def advance(run_dir: Path) -> Dict[str, Any]:
    """Run deterministic work and prepare every currently ready agent task."""
    run_dir = Path(run_dir).resolve()
    state = ensure_run(run_dir)
    state.refresh_invalidated_stages(run_dir)
    result: Dict[str, Any] = {"passed": [], "skipped": [], "failed": [], "ready_tasks": []}

    for stage in STAGES:
        current = state.stage(stage.id)
        if current.status == "passed" and stage.kind == "agent":
            # A legacy or manually edited artifact may have been marked
            # passed before a later report edit. Re-validate it on resume so
            # a stale safety clearance cannot silently carry forward.
            if validate_stage_output(run_dir, stage.id):
                state.invalidate_from(run_dir, stage.id)
                current = state.stage(stage.id)
        if current.status in {"passed", "skipped"}:
            continue
        if not state.dependencies_satisfied(stage):
            continue
        if _handle_conditional_privacy(run_dir, state, stage):
            result["skipped"].append(stage.id)
            continue
        if stage.kind == "agent":
            _handle_agent(run_dir, state, stage)
        else:
            try:
                _deterministic_stage(run_dir, state, stage)
                _record_success(run_dir, state, stage)
            except Exception as exc:
                _record_failure(state, stage, [str(exc)])

        if state.stage(stage.id).status == "passed":
            result["passed"].append(stage.id)
        elif state.stage(stage.id).status == "skipped":
            result["skipped"].append(stage.id)
        elif state.stage(stage.id).status == "failed":
            result["failed"].append(stage.id)
        elif state.stage(stage.id).status == "ready":
            result["ready_tasks"].append(stage.id)
    state.save(run_dir)
    return result


def status(run_dir: Path) -> Dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    state = ensure_run(run_dir)
    return {
        "run_id": state.run_id,
        "mode": state.mode,
        "state_file": str(state_path(run_dir)),
        "stages": {
            name: {
                "status": stage.status,
                "attempts": stage.attempts,
                "task_file": stage.task_file,
                "last_error": stage.last_error,
            }
            for name, stage in state.stages.items()
        },
    }


def validate(run_dir: Path, stage_id: Optional[str] = None) -> Dict[str, List[str]]:
    run_dir = Path(run_dir).resolve()
    if stage_id:
        return {stage_id: validate_stage_output(run_dir, stage_id)}
    return {stage.id: validate_stage_output(run_dir, stage.id) for stage in STAGES}
