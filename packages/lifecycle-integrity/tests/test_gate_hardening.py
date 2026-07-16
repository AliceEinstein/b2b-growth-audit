"""Regression tests for the reported gate-bypass vectors."""
from __future__ import annotations

import json
from pathlib import Path

from core.lifecycle_validators import (
    validate_lifecycle_run,
    validate_recommendation_plan,
)
from core.lifecycle_workspace import validate_agent_workspace
from lifecycle_test_support import build_lifecycle_run, write_judgment_artifacts


def _manifest_path(run_dir: Path) -> Path:
    return run_dir / "agent_workspace" / "task_manifest.json"


def test_emptying_manifest_tasks_cannot_bypass_completeness(tmp_path):
    """PoC: delete an artifact, set tasks=[] — the gate must still fail."""
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    write_judgment_artifacts(run_dir, "deals_without_company")
    assert validate_agent_workspace(run_dir, require_complete=True) == []
    victim = run_dir / "agent_workspace" / "analysis" / "schema_discovery_agent.json"
    victim.unlink()
    manifest = json.loads(_manifest_path(run_dir).read_text(encoding="utf-8"))
    manifest["tasks"] = []
    _manifest_path(run_dir).write_text(json.dumps(manifest), encoding="utf-8")
    problems = validate_agent_workspace(run_dir, require_complete=True)
    assert any("missing workspace artifact" in p for p in problems)
    assert any("does not match the code-owned task contract" in p for p in problems)


def test_manifest_schema_swap_is_reported_as_tampering(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "clean_inbound_crm_sample")
    write_judgment_artifacts(run_dir, None)
    manifest = json.loads(_manifest_path(run_dir).read_text(encoding="utf-8"))
    manifest["tasks"][0]["output_schema"] = "anything_goes"
    _manifest_path(run_dir).write_text(json.dumps(manifest), encoding="utf-8")
    problems = validate_agent_workspace(run_dir)
    assert any("does not match the code-owned task contract" in p for p in problems)


def test_reviewer_decisions_smuggled_into_one_file_fail_workspace(tmp_path):
    """PoC: all reviewers' decisions inside data_fidelity_reviewer.json."""
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    write_judgment_artifacts(run_dir, "deals_without_company")
    reviews_dir = run_dir / "agent_workspace" / "reviews"
    all_reviews = []
    for path in sorted(reviews_dir.glob("*.json")):
        all_reviews.extend(json.loads(path.read_text(encoding="utf-8"))["reviews"])
        path.write_text(
            json.dumps({"role": path.stem, "reviews": []}), encoding="utf-8"
        )
    (reviews_dir / "data_fidelity_reviewer.json").write_text(
        json.dumps({"role": "data_fidelity_reviewer", "reviews": all_reviews}),
        encoding="utf-8",
    )
    problems = validate_agent_workspace(run_dir)
    assert any("each reviewer writes only its own" in p for p in problems)


def test_empty_recommendation_plan_fails_when_findings_exist(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    write_judgment_artifacts(run_dir, "deals_without_company")
    plan_path = run_dir / "agent_workspace" / "recommendation_plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "priority_actions": [],
                "safe_operational_actions": [],
                "human_confirmation_needed": [],
                "observations_to_monitor": [],
                "do_not_auto_fix": [],
            }
        ),
        encoding="utf-8",
    )
    problems = validate_recommendation_plan(run_dir)
    assert any("is missing from lane" in p for p in problems)


def test_misplaced_lane_entry_fails(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    write_judgment_artifacts(run_dir, "deals_without_company")
    plan_path = run_dir / "agent_workspace" / "recommendation_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["priority_actions"] = plan["safe_operational_actions"]
    plan["safe_operational_actions"] = []
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    problems = validate_recommendation_plan(run_dir)
    assert any("per adjudication" in p for p in problems)
    # And the run-level validator surfaces it too.
    assert validate_lifecycle_run(run_dir)["recommendation_plan"]
