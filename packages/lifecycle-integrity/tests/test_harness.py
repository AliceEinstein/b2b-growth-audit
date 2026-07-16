"""Agent-driven harness: claim/submit loop, isolation, and tamper evidence."""
from __future__ import annotations

import json
from pathlib import Path

from core.harness import claim_next, load_journal, submit_task
from core.lifecycle_workspace import validate_agent_workspace
from lifecycle_test_support import build_lifecycle_run, write_judgment_artifacts


def test_claim_materializes_only_declared_inputs(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "clean_inbound_crm_sample")
    task, inbox, problems = claim_next(run_dir)
    assert problems == []
    assert task["phase"] == "analysis"
    assert (inbox / "instruction.md").exists()
    contract = json.loads((inbox / "contract.json").read_text(encoding="utf-8"))
    assert contract["json_schema"]["properties"]
    materialized = {
        str(p.relative_to(inbox / "inputs"))
        for p in (inbox / "inputs").rglob("*")
        if p.is_file()
    }
    # Every materialized file sits under one of the declared input paths,
    # and raw/ can never appear in an inbox.
    declared = tuple(task["inputs"])
    assert materialized
    for path in materialized:
        assert any(path == d or path.startswith(d + "/") for d in declared), path
        assert not path.startswith("raw"), path


def test_submit_rejects_invalid_output_and_commits_nothing(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "clean_inbound_crm_sample")
    task, inbox, _ = claim_next(run_dir)
    ok, problems = submit_task(run_dir, task["role"], {"summary": "missing role"})
    assert not ok
    assert any("does not satisfy schema" in p for p in problems)
    assert not (run_dir / task["output"]).exists()
    journal = load_journal(run_dir)
    assert journal["tasks"][task["role"]]["status"] == "rejected"
    assert journal["tasks"][task["role"]]["attempts"] == 1


def test_submit_loop_reaches_completion_and_autoconsolidates(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    # write_judgment_artifacts drives every role through submit_task.
    write_judgment_artifacts(run_dir, "deals_without_company")
    assert (run_dir / "findings.json").exists()
    assert (run_dir / "review_trace.json").exists()
    task, inbox, problems = claim_next(run_dir)
    assert task is None
    assert problems == []
    assert validate_agent_workspace(run_dir, require_complete=True) == []


def test_post_commit_edit_is_detected(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "clean_inbound_crm_sample")
    write_judgment_artifacts(run_dir, None)
    target = run_dir / "agent_workspace" / "analysis" / "schema_discovery_agent.json"
    doc = json.loads(target.read_text(encoding="utf-8"))
    doc["summary"] = "edited after commit"
    target.write_text(json.dumps(doc), encoding="utf-8")
    problems = validate_agent_workspace(run_dir)
    assert any("modified after harness commit" in p for p in problems)


def test_direct_writes_without_journal_fail_the_final_gate(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "clean_inbound_crm_sample")
    target = run_dir / "agent_workspace" / "analysis" / "schema_discovery_agent.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"role": "schema_discovery_agent", "summary": "manual"}),
        encoding="utf-8",
    )
    problems = validate_agent_workspace(run_dir, require_complete=True)
    assert any("harness_journal.json not found" in p for p in problems)


def test_resubmit_requires_explicit_flag(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "clean_inbound_crm_sample")
    doc = {"role": "schema_discovery_agent", "summary": "first"}
    ok, _ = submit_task(run_dir, "schema_discovery_agent", doc)
    assert ok
    ok, problems = submit_task(run_dir, "schema_discovery_agent", doc)
    assert not ok
    assert any("already committed" in p for p in problems)
    ok, _ = submit_task(run_dir, "schema_discovery_agent", doc, resubmit=True)
    assert ok


def test_every_task_declares_a_model_tier_and_safety_is_never_light():
    from core.lifecycle_agent_tasks import MODEL_TIERS, TASKS

    for task in TASKS:
        assert task["model_tier"] in MODEL_TIERS, task["role"]
    never_light = {
        "privacy_safety_reviewer",
        "journey_mapping_skeptic",
        "logic_reviewer",
        "false_positive_reviewer",
    }
    for task in TASKS:
        if task["role"] in never_light:
            assert task["model_tier"] == "reasoning", task["role"]


def test_contract_carries_model_tier(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "clean_inbound_crm_sample")
    task, inbox, _ = claim_next(run_dir)
    contract = json.loads((inbox / "contract.json").read_text(encoding="utf-8"))
    assert contract["model_tier"] == task["model_tier"]
    hint = contract["model_routing_hint"]
    assert "advisory" in hint
    assert "session model" in hint


def test_bundled_claude_subagents_cover_all_tiers():
    from core.lifecycle_agent_tasks import MODEL_TIERS, REPO_ROOT

    for tier in MODEL_TIERS:
        path = REPO_ROOT / ".claude" / "agents" / f"audit-role-{tier}.md"
        text = path.read_text(encoding="utf-8")
        assert f"name: audit-role-{tier}" in text
        # Default is the user's session model; tier mapping is opt-in.
        assert "model: inherit" in text
