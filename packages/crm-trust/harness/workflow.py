"""The code-owned BYO Agent workflow graph.

The graph deliberately contains no model calls.  It describes which local
artifact a host agent must produce, what may be read to produce it, and which
deterministic gate unlocks the next stage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from core.client_config import FIELD_OVERRIDES_PATH
from core.profiler import PROCESSED_FILES
from core.rules import MODULES
from core.validators import REVIEWERS


@dataclass(frozen=True)
class StageSpec:
    id: str
    kind: str  # deterministic | agent | gate
    dependencies: Tuple[str, ...] = ()
    input_patterns: Tuple[str, ...] = ()
    output_paths: Tuple[str, ...] = ()
    role_file: Optional[str] = None
    module: Optional[str] = None
    conditional: bool = False
    # Read when present; a missing optional input leaves the hash unchanged.
    optional_inputs: Tuple[str, ...] = ()


def _tuple(values: Iterable[str]) -> Tuple[str, ...]:
    return tuple(values)


def _context_inputs() -> Tuple[str, ...]:
    return _tuple("processed/" + name for name in PROCESSED_FILES)


def _audit_inputs(module: str) -> Tuple[str, ...]:
    return (
        "processed/measurements/" + module + ".json",
        "processed/snapshot_summary.json",
        "audit_profile.json",
        "crm_context.yaml",
        "business_context.json",
    )


def _review_inputs() -> Tuple[str, ...]:
    return (
        "findings/*_findings.json",
        "processed/measurements/*.json",
        "processed/snapshot_summary.json",
        "audit_profile.json",
        "crm_context.yaml",
        "business_context.json",
    )


def _context_for_revision() -> Tuple[str, ...]:
    return (
        "processed/snapshot_summary.json",
        "audit_profile.json",
        "crm_context.yaml",
        "business_context.json",
    )


REVIEWS_OUTPUT = "harness/agent_outputs/reviews/"
REVISIONS_OUTPUT = "harness/agent_outputs/revisions/"
REREVIEWS_OUTPUT = "harness/agent_outputs/rereviews/"


def _role(name: str) -> str:
    return "skills/hubspot-crm-trust-audit/subagents/" + name


def _build_stages() -> List[StageSpec]:
    stages: List[StageSpec] = [
        StageSpec(
            id="snapshot",
            kind="gate",
            output_paths=("manifest.json",),
        ),
        StageSpec(
            id="profile",
            kind="deterministic",
            dependencies=("snapshot",),
            input_patterns=("manifest.json",),
            output_paths=tuple("processed/" + name for name in PROCESSED_FILES),
        ),
        StageSpec(
            id="schema_discovery",
            kind="agent",
            dependencies=("profile",),
            input_patterns=_context_inputs(),
            output_paths=("crm_context.yaml", "schema_discovery_report.md"),
            role_file=_role("schema_discovery_agent.md"),
            optional_inputs=(FIELD_OVERRIDES_PATH,),
        ),
        StageSpec(
            id="business_context",
            kind="agent",
            dependencies=("schema_discovery",),
            input_patterns=_context_inputs() + ("crm_context.yaml",),
            output_paths=("business_context.json",),
            role_file=_role("business_context_agent.md"),
        ),
        StageSpec(
            id="audit_profile",
            kind="agent",
            dependencies=("schema_discovery", "business_context"),
            input_patterns=(
                "crm_context.yaml",
                "business_context.json",
                "processed/snapshot_summary.json",
            ),
            output_paths=("audit_profile.json",),
            role_file=_role("audit_model_selector.md"),
        ),
        StageSpec(
            id="measurements",
            kind="deterministic",
            dependencies=("audit_profile",),
            input_patterns=("crm_context.yaml", "business_context.json", "audit_profile.json"),
            output_paths=tuple(
                "processed/measurements/" + module + ".json" for module in MODULES
            ),
        ),
    ]

    for module in MODULES:
        stages.append(
            StageSpec(
                id="audit_" + module,
                kind="agent",
                dependencies=("measurements",),
                input_patterns=_audit_inputs(module),
                output_paths=("findings/" + module + "_findings.json",),
                role_file=_role(module + "_agent.md"),
                module=module,
            )
        )

    stages.append(
        StageSpec(
            id="findings_validation",
            kind="gate",
            dependencies=tuple("audit_" + module for module in MODULES),
            input_patterns=("findings/*_findings.json", "processed/measurements/*.json"),
        )
    )

    for reviewer in REVIEWERS:
        stages.append(
            StageSpec(
                id="review_" + reviewer,
                kind="agent",
                dependencies=("findings_validation",),
                input_patterns=_review_inputs(),
                output_paths=(REVIEWS_OUTPUT + reviewer + ".json",),
                role_file=_role(reviewer + ".md"),
            )
        )

    # Round 0 gate: every reviewer has judged every finding. A ``revise``
    # verdict opens one revision task for the finding's module and one
    # re-review task for each reviewer who asked; both are skipped when no
    # finding was sent back.
    stages.append(
        StageSpec(
            id="reviews_validation",
            kind="gate",
            dependencies=tuple("review_" + reviewer for reviewer in REVIEWERS),
            input_patterns=(
                REVIEWS_OUTPUT + "*.json",
                "findings/*_findings.json",
            ),
        )
    )

    for module in MODULES:
        stages.append(
            StageSpec(
                id="revise_" + module,
                kind="agent",
                dependencies=("reviews_validation",),
                input_patterns=(
                    "findings/" + module + "_findings.json",
                    REVIEWS_OUTPUT + "*.json",
                    "processed/measurements/" + module + ".json",
                )
                + _context_for_revision(),
                output_paths=(REVISIONS_OUTPUT + module + ".json",),
                role_file=_role("revision_agent.md"),
                module=module,
                conditional=True,
            )
        )

    stages.append(
        StageSpec(
            id="revisions_validation",
            kind="gate",
            dependencies=tuple("revise_" + module for module in MODULES),
            input_patterns=(
                REVISIONS_OUTPUT + "*.json",
                REVIEWS_OUTPUT + "*.json",
                "findings/*_findings.json",
            ),
        )
    )

    for reviewer in REVIEWERS:
        stages.append(
            StageSpec(
                id="rereview_" + reviewer,
                kind="agent",
                dependencies=("revisions_validation",),
                # The reviewer sees its own round-0 reasons, never the other
                # reviewers' verdicts.
                input_patterns=(
                    "findings/*_findings.json",
                    REVISIONS_OUTPUT + "*.json",
                    REVIEWS_OUTPUT + reviewer + ".json",
                    "processed/measurements/*.json",
                )
                + _context_for_revision(),
                output_paths=(REREVIEWS_OUTPUT + reviewer + ".json",),
                role_file=_role(reviewer + ".md"),
                conditional=True,
            )
        )

    stages.extend(
        [
            StageSpec(
                id="rereviews_validation",
                kind="gate",
                dependencies=tuple("rereview_" + reviewer for reviewer in REVIEWERS),
                input_patterns=(
                    REVIEWS_OUTPUT + "*.json",
                    REREVIEWS_OUTPUT + "*.json",
                    REVISIONS_OUTPUT + "*.json",
                    "findings/*_findings.json",
                ),
                output_paths=("review_log.json",),
            ),
            StageSpec(
                id="consolidate",
                kind="deterministic",
                dependencies=("rereviews_validation",),
                input_patterns=(
                    "findings/*_findings.json",
                    REVISIONS_OUTPUT + "*.json",
                    "review_log.json",
                    "evidence/*.csv",
                ),
                output_paths=("findings.json", "score.json", "evidence.csv"),
            ),
            StageSpec(
                id="recommendations",
                kind="agent",
                dependencies=("consolidate",),
                input_patterns=(
                    "findings.json",
                    "score.json",
                    "review_log.json",
                    "evidence.csv",
                    "evidence/*.csv",
                ),
                output_paths=("recommendations.json",),
                role_file=_role("recommendation_agent.md"),
            ),
            StageSpec(
                id="report_narrative",
                kind="agent",
                dependencies=("consolidate", "recommendations"),
                input_patterns=(
                    "manifest.json",
                    "processed/snapshot_summary.json",
                    "processed/object_counts.json",
                    "processed/activity_summary.json",
                    "processed/identity_completeness.json",
                    "processed/lifecycle_distribution.json",
                    "processed/association_summary.json",
                    "processed/pipeline_summary.json",
                    "crm_context.yaml",
                    "business_context.json",
                    "audit_profile.json",
                    "findings.json",
                    "score.json",
                    "recommendations.json",
                    "evidence.csv",
                ),
                output_paths=("report_narrative.json",),
                role_file=_role("report_narrative_agent.md"),
            ),
            StageSpec(
                id="render_reports",
                kind="deterministic",
                dependencies=("recommendations", "report_narrative"),
                input_patterns=(
                    "manifest.json",
                    "processed/*.json",
                    "findings.json",
                    "score.json",
                    "recommendations.json",
                    "report_narrative.json",
                    "evidence.csv",
                ),
                output_paths=(
                    "crm_trust_report.md",
                    "crm_trust_report.html",
                    "operator_appendix.md",
                    "agent_handoff.md",
                    "report_record_evidence.csv",
                ),
            ),
            StageSpec(
                id="privacy_clearance",
                kind="agent",
                dependencies=("render_reports",),
                input_patterns=(
                    "crm_trust_report.md",
                    "crm_trust_report.html",
                    "operator_appendix.md",
                    "agent_handoff.md",
                    "report_record_evidence.csv",
                ),
                output_paths=("safety_clearance.json",),
                role_file=_role("privacy_safety_reviewer.md"),
                conditional=True,
            ),
            StageSpec(
                id="final_gate",
                kind="gate",
                dependencies=("render_reports", "privacy_clearance"),
                input_patterns=(
                    "crm_trust_report.md",
                    "crm_trust_report.html",
                    "operator_appendix.md",
                    "agent_handoff.md",
                    "findings.json",
                    "evidence.csv",
                    "report_record_evidence.csv",
                    "score.json",
                    "recommendations.json",
                    "crm_context.yaml",
                    "schema_discovery_report.md",
                    "audit_log.json",
                    "manifest.json",
                    "safety_clearance.json",
                ),
                output_paths=("final_gate_report.json",),
            ),
        ]
    )
    return stages


STAGES = _build_stages()
STAGE_BY_ID: Dict[str, StageSpec] = {stage.id: stage for stage in STAGES}


def get_stage(stage_id: str) -> StageSpec:
    try:
        return STAGE_BY_ID[stage_id]
    except KeyError:
        raise KeyError("unknown harness stage: " + stage_id)


def dependents(stage_id: str) -> List[StageSpec]:
    return [stage for stage in STAGES if stage_id in stage.dependencies]
