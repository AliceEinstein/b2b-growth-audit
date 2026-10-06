"""Stage-aware validation for BYO Agent artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from pydantic import ValidationError

from core.integrity import sha256_file
from core.profiler import PROCESSED_FILES
from core.rules import MODULES
from core.safety import scan_deliverables
from core.revisions import (
    REREVIEWS_DIR,
    REVISIONS_DIR,
    modules_needing_revision,
    reviewers_needing_rereview,
    round0_raw,
    round1_raw,
    stray_files,
    validate_rereview,
    validate_revision,
)
from core.schemas import ReportNarrative, ReviewEntry
from core.validators import (
    check_review_entries,
    validate_audit_profile,
    validate_business_context,
    validate_crm_context,
    validate_findings,
    validate_recommendations,
    validate_report_narrative,
    validate_report_structure,
    validate_reviews,
    validate_snapshot_completed,
)

from .workflow import STAGES, get_stage


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(str(exc))


def _require_files(run_dir: Path, paths: List[str]) -> List[str]:
    return [name + " not found" for name in paths if not (run_dir / name).is_file()]


def _validate_review_artifact(run_dir: Path, stage_id: str) -> List[str]:
    reviewer = stage_id.removeprefix("review_")
    path = run_dir / "harness" / "agent_outputs" / "reviews" / (reviewer + ".json")
    if not path.exists():
        return [str(path.relative_to(run_dir)) + " not found"]
    try:
        raw = _json(path)
    except (ValueError, json.JSONDecodeError) as exc:
        return [str(path.relative_to(run_dir)) + ": invalid JSON — " + str(exc)]
    if not isinstance(raw, list):
        return [str(path.relative_to(run_dir)) + " must contain a JSON array"]
    problems: List[str] = []
    for index, item in enumerate(raw):
        try:
            entry = ReviewEntry.model_validate(item)
        except ValidationError as exc:
            problems.append("review entry " + str(index) + ": " + str(exc))
            continue
        if entry.reviewer != reviewer:
            problems.append(
                "review entry " + str(index) + " has reviewer "
                + repr(entry.reviewer)
                + "; expected "
                + repr(reviewer)
            )
        if entry.revision_round != 0:
            problems.append(
                "review entry " + str(index) + " is a first review; re-reviews go in "
                + str(REREVIEWS_DIR / (reviewer + ".json"))
            )
    return problems


def review_round0_problems(run_dir: Path) -> List[str]:
    """Round-0 gate: all four reviewers judged every finding; no re-review required yet."""
    try:
        entries = round0_raw(run_dir) + round1_raw(run_dir)
    except (ValueError, json.JSONDecodeError) as exc:
        return ["review artifacts: " + str(exc)]
    return check_review_entries(
        run_dir, entries, require_rereview=False, source="harness/agent_outputs/reviews"
    )


def revisions_gate_problems(run_dir: Path) -> List[str]:
    needed = modules_needing_revision(run_dir)
    problems = stray_files(run_dir, REVISIONS_DIR, needed)
    for module in sorted(needed):
        problems.extend(validate_revision(run_dir, module))
    return problems


def rereviews_gate_problems(run_dir: Path) -> List[str]:
    needed = reviewers_needing_rereview(run_dir)
    problems = stray_files(run_dir, REREVIEWS_DIR, needed)
    for reviewer in sorted(needed):
        problems.extend(validate_rereview(run_dir, reviewer))
    return problems


def validate_stage_output(run_dir: Path, stage_id: str) -> List[str]:
    """Return deterministic problems for one stage; an empty list means pass."""
    run_dir = Path(run_dir)
    stage = get_stage(stage_id)
    if stage_id == "snapshot":
        return validate_snapshot_completed(run_dir)
    if stage_id == "profile":
        return _require_files(run_dir, ["processed/" + name for name in PROCESSED_FILES])
    if stage_id == "schema_discovery":
        return validate_crm_context(run_dir) + _require_files(
            run_dir, ["schema_discovery_report.md"]
        )
    if stage_id == "business_context":
        return validate_business_context(run_dir)
    if stage_id == "audit_profile":
        return validate_audit_profile(run_dir)
    if stage_id == "measurements":
        problems: List[str] = []
        for module in MODULES:
            measurement_path = run_dir / "processed" / "measurements" / (module + ".json")
            evidence_path = run_dir / "evidence" / (module + ".csv")
            if not measurement_path.is_file():
                problems.append(str(measurement_path.relative_to(run_dir)) + " not found")
            else:
                try:
                    document = _json(measurement_path)
                    if document.get("module") != module:
                        problems.append(module + ": measurement module mismatch")
                except (ValueError, json.JSONDecodeError) as exc:
                    problems.append(module + ": invalid measurement JSON — " + str(exc))
            if not evidence_path.is_file():
                problems.append(str(evidence_path.relative_to(run_dir)) + " not found")
        return problems
    if stage_id.startswith("audit_"):
        module = stage_id.removeprefix("audit_")
        return [problem for problem in validate_findings(run_dir, [module]).get(module, [])]
    if stage_id == "findings_validation":
        return [problem for problems in validate_findings(run_dir).values() for problem in problems]
    if stage_id.startswith("review_"):
        return _validate_review_artifact(run_dir, stage_id)
    if stage_id == "reviews_validation":
        return review_round0_problems(run_dir)
    if stage_id.startswith("revise_"):
        module = stage_id.removeprefix("revise_")
        if module not in modules_needing_revision(run_dir):
            return []
        return validate_revision(run_dir, module)
    if stage_id == "revisions_validation":
        return revisions_gate_problems(run_dir)
    if stage_id.startswith("rereview_"):
        reviewer = stage_id.removeprefix("rereview_")
        if reviewer not in reviewers_needing_rereview(run_dir):
            return []
        return validate_rereview(run_dir, reviewer)
    if stage_id == "rereviews_validation":
        return rereviews_gate_problems(run_dir) + validate_reviews(run_dir, require_rereview=True)
    if stage_id == "consolidate":
        return _require_files(run_dir, ["findings.json", "score.json", "evidence.csv"])
    if stage_id == "recommendations":
        return validate_recommendations(run_dir)
    if stage_id == "report_narrative":
        return validate_report_narrative(run_dir)
    if stage_id == "render_reports":
        return validate_report_structure(run_dir)
    if stage_id == "privacy_clearance":
        path = run_dir / "safety_clearance.json"
        if not path.exists():
            return ["safety_clearance.json not found"]
        try:
            data = _json(path)
        except (ValueError, json.JSONDecodeError) as exc:
            return ["safety_clearance.json: invalid JSON — " + str(exc)]
        if not isinstance(data, list):
            return ["safety_clearance.json must contain a JSON array"]
        problems = []
        for index, item in enumerate(data):
            if not isinstance(item, dict):
                problems.append("safety_clearance.json entry " + str(index) + " must be an object")
                continue
            for key in ("phrase", "file", "file_sha256", "reason"):
                if not str(item.get(key, "")).strip():
                    problems.append("safety_clearance.json entry " + str(index) + " missing " + key)
        # A clearance is a review of exact bytes, not a permanent phrase
        # allowlist. Any report edit must produce a new clearance or the
        # privacy task is reopened.
        clearances = [item for item in data if isinstance(item, dict)]
        for hit in scan_deliverables(run_dir):
            if hit.hard:
                continue
            filename = Path(hit.source).name
            current_hash = sha256_file(run_dir / filename) if (run_dir / filename).is_file() else None
            if not any(
                item.get("phrase") == hit.excerpt
                and item.get("file") == filename
                and item.get("file_sha256") == current_hash
                and str(item.get("reason", "")).strip()
                for item in clearances
            ):
                problems.append(
                    "safety clearance does not cover current phrase "
                    + repr(hit.excerpt)
                    + " in "
                    + filename
                )
        return problems
    if stage_id == "final_gate":
        path = run_dir / "final_gate_report.json"
        if not path.exists():
            return ["final_gate_report.json not found"]
        try:
            data = _json(path)
        except (ValueError, json.JSONDecodeError) as exc:
            return ["final_gate_report.json: invalid JSON — " + str(exc)]
        return [] if data.get("passed") is True else ["final gate did not pass"]
    return ["no validator registered for stage " + stage_id]


def validate_all(run_dir: Path) -> Dict[str, List[str]]:
    return {stage.id: validate_stage_output(run_dir, stage.id) for stage in STAGES}
