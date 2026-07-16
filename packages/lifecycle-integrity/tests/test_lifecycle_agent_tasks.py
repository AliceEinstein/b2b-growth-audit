from __future__ import annotations

from core.lifecycle_agent_tasks import write_agent_task_manifest
from lifecycle_test_support import build_lifecycle_run


def test_task_manifest_declares_isolated_artifacts_and_no_raw_access(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "clean_inbound_crm_sample")
    manifest = write_agent_task_manifest(run_dir)
    assert manifest["execution_model"] == "artifact_based_no_free_chat"
    assert len(manifest["tasks"]) == 27
    outputs = [task["output"] for task in manifest["tasks"]]
    assert len(outputs) == len(set(outputs))
    assert all(task["raw_access_allowed"] is False for task in manifest["tasks"])
    assert all(task["hubspot_api_allowed"] is False for task in manifest["tasks"])
    assert all(
        not any(path == "raw" or path.startswith("raw/") for path in task["inputs"])
        for task in manifest["tasks"]
    )
    automation = next(
        task for task in manifest["tasks"]
        if task["role"] == "automation_scoring_analysis_agent"
    )
    assert "processed/automation_scoring_measurements.json" in automation["inputs"]
    assert automation["output_schema"] == "automation_analysis_result"
    root_cause = next(
        task for task in manifest["tasks"]
        if task["role"] == "automation_root_cause_agent"
    )
    assert root_cause["phase"] == "root_cause"
    assert "findings.json" in root_cause["inputs"]
    recommendation = next(
        task for task in manifest["tasks"] if task["role"] == "recommendation_agent"
    )
    assert "agent_workspace/root_cause/automation_root_cause_agent.json" in recommendation[
        "inputs"
    ]
    audit_tasks = [task for task in manifest["tasks"] if task["phase"] == "audit"]
    assert all(
        "processed/high_intent_cohort_summary.json" in task["inputs"]
        for task in audit_tasks
    )
    final_task = next(task for task in manifest["tasks"] if task["role"] == "final_report_agent")
    assert "agent_workspace/hypotheses" in final_task["inputs"]
    assert "processed/high_intent_cohort_summary.json" in final_task["inputs"]
    assert (run_dir / "agent_workspace" / "task_manifest.json").exists()
