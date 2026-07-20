"""Workspace contract validation, task progression, and consolidation."""
from __future__ import annotations

import json
from pathlib import Path

from core.lifecycle_consolidation import consolidate_candidates, consolidate_reviews
from core.lifecycle_validators import validate_lifecycle_run
from core.lifecycle_workspace import next_tasks, validate_agent_workspace
from lifecycle_test_support import build_lifecycle_run, write_judgment_artifacts


def _first_output(run_dir: Path, phase: str) -> Path:
    manifest = json.loads(
        (run_dir / "agent_workspace" / "task_manifest.json").read_text(encoding="utf-8")
    )
    task = next(t for t in manifest["tasks"] if t["phase"] == phase)
    return run_dir / task["output"]


def test_manifest_records_portable_repo_root(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "clean_inbound_crm_sample")
    manifest = json.loads(
        (run_dir / "agent_workspace" / "task_manifest.json").read_text(encoding="utf-8")
    )
    root = Path(manifest["repo_root"])
    assert root.is_absolute()
    assert manifest["instruction_paths_relative_to"] == "repo_root"
    assert (root / manifest["tasks"][0]["instruction"]).exists()

    from core.lifecycle_agent_tasks import write_agent_task_manifest

    portable = write_agent_task_manifest(run_dir, portable=True)
    assert portable["repo_root"] == "."


def test_complete_workspace_passes_and_missing_artifact_fails_final(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    write_judgment_artifacts(run_dir, "deals_without_company")
    assert validate_agent_workspace(run_dir, require_complete=True) == []
    victim = _first_output(run_dir, "hypothesis")
    victim.unlink()
    problems = validate_agent_workspace(run_dir, require_complete=True)
    assert any("missing workspace artifact" in p for p in problems)
    # Non-final validation tolerates the gap; the final gate does not.
    assert validate_agent_workspace(run_dir) == []
    assert validate_lifecycle_run(run_dir, final=True)["workspace"]


def test_schema_violation_and_role_mismatch_are_reported(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "clean_inbound_crm_sample")
    write_judgment_artifacts(run_dir, None)
    analysis = _first_output(run_dir, "analysis")
    analysis.write_text(json.dumps({"summary": "missing role"}), encoding="utf-8")
    problems = validate_agent_workspace(run_dir)
    assert any("does not satisfy schema analysis_result" in p for p in problems)
    doc = {"role": "somebody_else", "summary": "wrong role"}
    analysis.write_text(json.dumps(doc), encoding="utf-8")
    problems = validate_agent_workspace(run_dir)
    assert any("does not match declared task role" in p for p in problems)


def test_next_tasks_walks_phases_in_order(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "clean_inbound_crm_sample")
    phase, pending, problems = next_tasks(run_dir)
    assert (phase, problems) == ("analysis", [])
    assert len(pending) == 8
    write_judgment_artifacts(run_dir, None)
    phase, pending, problems = next_tasks(run_dir)
    assert (phase, pending, problems) == (None, [], [])
    victim = _first_output(run_dir, "audit")
    victim.unlink()
    phase, pending, _ = next_tasks(run_dir)
    assert phase == "audit"
    assert len(pending) == 1


def test_review_phase_is_blocked_until_findings_are_consolidated(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "clean_inbound_crm_sample")
    write_judgment_artifacts(run_dir, None)
    (run_dir / "findings.json").unlink()
    for path in (run_dir / "agent_workspace" / "reviews").glob("*.json"):
        path.unlink()
    from core.lifecycle_workspace import load_task_manifest, task_status

    manifest, _ = load_task_manifest(run_dir)
    review_task = next(t for t in manifest["tasks"] if t["phase"] == "review")
    assert task_status(run_dir, review_task) == "blocked"
    consolidate_candidates(run_dir)
    assert task_status(run_dir, review_task) == "ready"


def test_consolidation_rejects_conflicts_and_duplicates(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    write_judgment_artifacts(run_dir, "deals_without_company")
    candidates_dir = run_dir / "agent_workspace" / "candidates"
    docs = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(candidates_dir.glob("*.json"))
    ]
    populated = next(doc for doc in docs if doc["candidate_findings"])
    clone = json.loads(json.dumps(populated))
    clone["candidate_findings"][0]["business_impact"] = "A different story."
    (candidates_dir / "zz_conflict.json").write_text(
        json.dumps(clone), encoding="utf-8"
    )
    count, problems = consolidate_candidates(run_dir)
    assert any("conflicting candidate payloads" in p for p in problems)
    (candidates_dir / "zz_conflict.json").unlink()

    reviews_dir = run_dir / "agent_workspace" / "reviews"
    populated_review = next(
        path
        for path in sorted(reviews_dir.glob("*.json"))
        if json.loads(path.read_text(encoding="utf-8"))["reviews"]
    )
    # Forgery: decisions attributed to another reviewer are rejected even
    # when the containing document is otherwise schema-valid.
    doc = json.loads(populated_review.read_text(encoding="utf-8"))
    (reviews_dir / "zz_forgery.json").write_text(
        json.dumps({"reviews": doc["reviews"]}), encoding="utf-8"
    )
    count, problems = consolidate_reviews(run_dir)
    assert any("may only contain 'zz_forgery' decisions" in p for p in problems)
    (reviews_dir / "zz_forgery.json").unlink()

    # A duplicated decision inside the reviewer's own file is still caught.
    doc["reviews"] = doc["reviews"] + doc["reviews"]
    populated_review.write_text(json.dumps(doc), encoding="utf-8")
    count, problems = consolidate_reviews(run_dir)
    assert any("duplicate review decision" in p for p in problems)
