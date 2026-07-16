"""Artifact contracts for the lifecycle multi-agent judgment phase."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from connectors.hubspot.normalize import write_json

# Instruction paths are stored relative to the repository root so the manifest
# stays valid wherever the repository is cloned; the absolute root is resolved
# at write time and recorded alongside them.
REPO_ROOT = Path(__file__).resolve().parents[1]

COMMON_ANALYSIS_INPUTS = [
    "manifest.json",
    "processed/journey_evidence_store.json",
    "crm_context.yaml",
]
REGISTRY_INPUTS = COMMON_ANALYSIS_INPUTS + ["journey_pattern_registry.json"]
AUDIT_INPUTS = REGISTRY_INPUTS + [
    "processed/lifecycle_integrity_measurements.json",
    "processed/high_intent_cohort_summary.json",
    "evidence.csv",
    "outlier_registry.csv",
]
AUTOMATION_INPUTS = COMMON_ANALYSIS_INPUTS + [
    "processed/automation_coverage.json",
    "processed/workflow_inventory.json",
    "processed/workflow_dependency_graph.json",
    "processed/workflow_performance_summary.json",
    "processed/scoring_activation_summary.json",
    "processed/automation_scoring_measurements.json",
    "automation_evidence.csv",
]
ROOT_CAUSE_INPUTS = AUDIT_INPUTS + [
    "processed/automation_coverage.json",
    "processed/workflow_inventory.json",
    "processed/workflow_dependency_graph.json",
    "processed/workflow_performance_summary.json",
    "processed/scoring_activation_summary.json",
    "processed/automation_scoring_measurements.json",
    "automation_evidence.csv",
    "findings.json",
    "agent_workspace/analysis/automation_scoring_analysis_agent.json",
]
AUTOMATION_RECOMMENDATION_INPUTS = [
    "processed/automation_coverage.json",
    "processed/workflow_inventory.json",
    "processed/workflow_dependency_graph.json",
    "processed/workflow_performance_summary.json",
    "processed/scoring_activation_summary.json",
    "processed/automation_scoring_measurements.json",
    "automation_evidence.csv",
    "agent_workspace/root_cause/automation_root_cause_agent.json",
]


# Model routing tiers. The harness never calls a model itself; the tier is a
# contract field the HOST agent maps to its own delegation mechanism (Claude
# Code: the bundled .claude/agents/audit-role-<tier> subagents; other CLIs:
# profile/model flags). Assignment principles:
#   reasoning — open-ended or adversarial judgment, and everything
#               safety-critical (never route safety review to a cheap model)
#   standard  — structured judgment against explicit contracts
#   light     — mechanical verification/extraction over small inputs
MODEL_TIERS = ("reasoning", "standard", "light")
ROLE_MODEL_TIERS = {
    "schema_discovery_agent": "reasoning",
    "object_relationship_agent": "standard",
    "lifecycle_state_agent": "standard",
    "pipeline_structure_agent": "light",
    "source_attribution_agent": "standard",
    "activity_handoff_agent": "light",
    "automation_scoring_analysis_agent": "standard",
    "inbound_journey_hypothesis_agent": "reasoning",
    "outbound_journey_hypothesis_agent": "reasoning",
    "abm_journey_hypothesis_agent": "reasoning",
    "partner_journey_hypothesis_agent": "reasoning",
    "expansion_journey_hypothesis_agent": "reasoning",
    "mixed_motion_journey_agent": "reasoning",
    "lifecycle_integrity_audit_agent": "standard",
    "handoff_integrity_audit_agent": "standard",
    "association_integrity_audit_agent": "standard",
    "attribution_continuity_audit_agent": "standard",
    "state_coherence_audit_agent": "standard",
    "outlier_detection_agent": "standard",
    "automation_root_cause_agent": "reasoning",
    "data_fidelity_reviewer": "light",
    "journey_mapping_skeptic": "reasoning",
    "logic_reviewer": "reasoning",
    "false_positive_reviewer": "reasoning",
    "privacy_safety_reviewer": "reasoning",
    "recommendation_agent": "standard",
    "final_report_agent": "standard",
}


def _task(
    role: str,
    phase: str,
    inputs: list[str],
    output: str,
    schema: str,
) -> dict[str, Any]:
    return {
        "role": role,
        "instruction": f"skills/hubspot-lifecycle-integrity-audit/subagents/{role}.md",
        "phase": phase,
        "inputs": inputs,
        "output": output,
        "output_schema": schema,
        "model_tier": ROLE_MODEL_TIERS[role],
        "raw_access_allowed": False,
        "hubspot_api_allowed": False,
    }


TASKS = [
    _task(
        "schema_discovery_agent",
        "analysis",
        COMMON_ANALYSIS_INPUTS
        + [
            "processed/property_usage_summary.json",
            "processed/field_empty_rates.json",
            "processed/source_field_candidates.json",
            "processed/pipeline_summary.json",
        ],
        "agent_workspace/analysis/schema_discovery_agent.json",
        "analysis_result",
    ),
    _task(
        "object_relationship_agent",
        "analysis",
        COMMON_ANALYSIS_INPUTS
        + [
            "processed/association_summary.json",
            "processed/object_counts.json",
            "processed/journey_transition_candidates.json",
        ],
        "agent_workspace/analysis/object_relationship_agent.json",
        "analysis_result",
    ),
    _task(
        "lifecycle_state_agent",
        "analysis",
        COMMON_ANALYSIS_INPUTS
        + [
            "processed/lifecycle_distribution.json",
            "processed/property_usage_summary.json",
            "processed/stage_transition_summary.json",
        ],
        "agent_workspace/analysis/lifecycle_state_agent.json",
        "analysis_result",
    ),
    _task(
        "pipeline_structure_agent",
        "analysis",
        COMMON_ANALYSIS_INPUTS
        + ["processed/pipeline_summary.json", "processed/deal_stage_distribution.json"],
        "agent_workspace/analysis/pipeline_structure_agent.json",
        "analysis_result",
    ),
    _task(
        "source_attribution_agent",
        "analysis",
        COMMON_ANALYSIS_INPUTS
        + [
            "processed/source_field_candidates.json",
            "processed/property_usage_summary.json",
        ],
        "agent_workspace/analysis/source_attribution_agent.json",
        "analysis_result",
    ),
    _task(
        "activity_handoff_agent",
        "analysis",
        COMMON_ANALYSIS_INPUTS
        + [
            "processed/activity_summary.json",
            "processed/data_age_summary.json",
            "processed/high_intent_cohort_summary.json",
            "processed/owner_distribution.json",
        ],
        "agent_workspace/analysis/activity_handoff_agent.json",
        "analysis_result",
    ),
    _task(
        "automation_scoring_analysis_agent",
        "analysis",
        AUTOMATION_INPUTS,
        "agent_workspace/analysis/automation_scoring_analysis_agent.json",
        "automation_analysis_result",
    ),
    *[
        _task(
            role,
            "hypothesis",
            REGISTRY_INPUTS + ["agent_workspace/analysis"],
            f"agent_workspace/hypotheses/{role}.json",
            "journey_hypothesis",
        )
        for role in (
            "inbound_journey_hypothesis_agent",
            "outbound_journey_hypothesis_agent",
            "abm_journey_hypothesis_agent",
            "partner_journey_hypothesis_agent",
            "expansion_journey_hypothesis_agent",
        )
    ],
    _task(
        "mixed_motion_journey_agent",
        "hypothesis",
        REGISTRY_INPUTS + ["agent_workspace/analysis", "agent_workspace/hypotheses"],
        "agent_workspace/hypotheses/mixed_motion_journey_agent.json",
        "mixed_motion_assessment",
    ),
    *[
        _task(
            role,
            "audit",
            AUDIT_INPUTS + ["agent_workspace/hypotheses"],
            f"agent_workspace/candidates/{role}.json",
            "candidate_findings",
        )
        for role in (
            "lifecycle_integrity_audit_agent",
            "handoff_integrity_audit_agent",
            "association_integrity_audit_agent",
            "attribution_continuity_audit_agent",
            "state_coherence_audit_agent",
            "outlier_detection_agent",
        )
    ],
    _task(
        "automation_root_cause_agent",
        "root_cause",
        ROOT_CAUSE_INPUTS,
        "agent_workspace/root_cause/automation_root_cause_agent.json",
        "root_cause_assessments",
    ),
    *[
        _task(
            role,
            "review",
            AUDIT_INPUTS
            + [
                "findings.json",
                "agent_workspace/candidates",
                "agent_workspace/root_cause/automation_root_cause_agent.json",
            ],
            f"agent_workspace/reviews/{role}.json",
            "review_decisions",
        )
        for role in (
            "data_fidelity_reviewer",
            "journey_mapping_skeptic",
            "logic_reviewer",
            "false_positive_reviewer",
            "privacy_safety_reviewer",
        )
    ],
    _task(
        "recommendation_agent",
        "recommendation",
        REGISTRY_INPUTS
        + ["findings.json", "review_trace.json"]
        + AUTOMATION_RECOMMENDATION_INPUTS,
        "agent_workspace/recommendation_plan.json",
        "recommendation_lanes",
    ),
    _task(
        "final_report_agent",
        "report",
        REGISTRY_INPUTS
        + [
            "processed/lifecycle_integrity_measurements.json",
            "processed/high_intent_cohort_summary.json",
            "processed/automation_scoring_measurements.json",
            "processed/scoring_activation_summary.json",
            "agent_workspace/hypotheses",
            "agent_workspace/root_cause/automation_root_cause_agent.json",
            "findings.json",
            "review_trace.json",
            "agent_workspace/recommendation_plan.json",
        ],
        "final_gate_report.json",
        "deterministic_report_and_gate",
    ),
]


def expected_manifest_contract() -> dict[str, Any]:
    """The code-owned portion of the task manifest.

    Validators compare the stored manifest against this — the run directory
    copy is a convenience for agents, never the source of truth, so editing
    it cannot change what the gates enforce.
    """
    return {
        "execution_model": "artifact_based_no_free_chat",
        "code_owned_artifacts_must_not_be_edited": [
            "processed/journey_evidence_store.json",
            "processed/lifecycle_integrity_measurements.json",
            "processed/high_intent_cohort_summary.json",
            "evidence.csv",
            "outlier_registry.csv",
            "journey_pattern_registry.json",
            "lifecycle_score.json",
            "processed/automation_coverage.json",
            "processed/workflow_inventory.json",
            "processed/workflow_dependency_graph.json",
            "processed/workflow_performance_summary.json",
            "processed/scoring_activation_summary.json",
            "processed/automation_scoring_measurements.json",
            "automation_evidence.csv",
        ],
        "global_rules": {
            "read_only": True,
            "raw_access_allowed": False,
            "hubspot_api_allowed": False,
            "auto_fix_allowed": False,
        },
        "tasks": TASKS,
    }


def write_agent_task_manifest(run_dir: Path, *, portable: bool = False) -> dict[str, Any]:
    """Write the judgment-phase task manifest.

    ``portable=True`` records ``repo_root`` as ``.`` instead of the absolute
    local path — used for committed example datasets so no machine-specific
    path ever enters the repository.
    """
    run_dir = Path(run_dir)
    for task in TASKS:
        if any(path == "raw" or path.startswith("raw/") for path in task["inputs"]):
            raise ValueError(f"{task['role']} task illegally requests raw data")
    for directory in ("analysis", "hypotheses", "candidates", "root_cause", "reviews"):
        (run_dir / "agent_workspace" / directory).mkdir(parents=True, exist_ok=True)
    doc = {
        "version": 2,
        "run_id": run_dir.name,
        "repo_root": "." if portable else str(REPO_ROOT),
        "instruction_paths_relative_to": "repo_root",
        **expected_manifest_contract(),
    }
    write_json(run_dir / "agent_workspace" / "task_manifest.json", doc)
    return doc
