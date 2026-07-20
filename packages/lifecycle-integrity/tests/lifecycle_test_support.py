"""Reusable lifecycle-audit fixtures for golden and gate tests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.adjudication import action_lane, aggregate_review_status
from core.audit_logger import AuditLog
from core.harness import submit_task
from core.integrity import hash_files
from core.intent_evidence import build_intent_evidence
from core.journey_evidence import build_journey_evidence_store
from core.lifecycle_agent_tasks import TASKS, write_agent_task_manifest
from core.lifecycle_consolidation import consolidate_candidates, consolidate_reviews
from core.lifecycle_final_gate import FINAL_DELIVERABLES
from core.lifecycle_reports import generate_lifecycle_reports
from core.lifecycle_rules import measure_lifecycle_integrity
from core.lifecycle_synthetic_datasets import LIFECYCLE_DATASETS
from core.lifecycle_schemas import LifecycleFinding, ReviewDecision
from core.profiler import profile_run
from core.safety import scan_file


def build_lifecycle_run(root: Path, name: str) -> tuple[Path, dict[str, Any]]:
    run_dir, expectations = LIFECYCLE_DATASETS[name](root)
    profile_run(run_dir)
    build_intent_evidence(run_dir)
    build_journey_evidence_store(run_dir)
    measure_lifecycle_integrity(run_dir)
    write_agent_task_manifest(run_dir)
    AuditLog({"synthetic_dataset": name}).write(run_dir / "audit_log.json")
    return run_dir, expectations


def measurement(run_dir: Path, measurement_id: str) -> dict[str, Any]:
    doc = json.loads(
        (run_dir / "processed" / "lifecycle_integrity_measurements.json").read_text(
            encoding="utf-8"
        )
    )
    return next(row for row in doc["measurements"] if row["id"] == measurement_id)


def write_judgment_artifacts(
    run_dir: Path,
    measurement_id: str | None = None,
    *,
    measurement_ids: list[str] | None = None,
    journey_pattern: str = "all_detected_journeys",
    severity: str = "medium",
    recommendation_type: str = "safe_operational_action",
) -> None:
    findings: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    selected_ids = list(measurement_ids or ([] if measurement_id is None else [measurement_id]))
    for selected_id in selected_ids:
        row = measurement(run_dir, selected_id)
        recoverability = row.get("recoverability")
        if recoverability == "open_deal_review":
            business_impact = (
                "Existing deals in this population can lose ownership, "
                "relationship, or follow-up continuity."
            )
            recommended_action = (
                "Review the hashed open-deal exception list with the pipeline "
                "owner, then confirm the journey rule before any HubSpot change."
            )
        elif recoverability == "potential_recoverable_population":
            business_impact = (
                "High-intent contacts may fail to progress through the expected "
                "handoff or deal-creation step. This is a potential recoverable "
                "population, not booked pipeline."
            )
            recommended_action = (
                "Confirm the journey-specific deal-creation timing and review "
                "the hashed contact population; do not assign a monetary value."
            )
        else:
            business_impact = "The HubSpot journey cannot represent this relationship consistently."
            recommended_action = (
                "Confirm the canonical business rule, then prepare a review-only exception list."
            )
        intensity = (
            "high"
            if severity in {"critical", "high"}
            else "medium"
            if severity == "medium"
            else "low"
        )
        finding = {
            "finding_id": selected_id,
            "journey_pattern": journey_pattern,
            "integrity_dimension": row["integrity_dimension"],
            "severity": severity,
            "confidence_score": 80,
            "confidence_label": "high",
            "object_type": row["object_type"],
            "field_name": row.get("field_name"),
            "affected_records": row.get("affected_records"),
            "affected_percentage": row.get("affected_percentage"),
            "denominator": row.get("denominator"),
            "materiality_explanation": (
                (row.get("note") or "Portal-level deterministic measurement.")
                if row.get("denominator") is None
                else None
            ),
            "evidence_refs": [f"evidence.csv#finding_id={selected_id}"],
            "business_impact": business_impact,
            "recommended_action": recommended_action,
            "recommendation_type": recommendation_type,
            "auto_fix_allowed": False,
            "assumptions": [],
            "limitations": [],
            "review_intensity": intensity,
            "review_status": "pending",
        }
        findings.append(finding)
        required = {
            "low": ["privacy_safety_reviewer"],
            "medium": [
                "data_fidelity_reviewer",
                "logic_reviewer",
                "privacy_safety_reviewer",
            ],
            "high": [
                "data_fidelity_reviewer",
                "journey_mapping_skeptic",
                "logic_reviewer",
                "false_positive_reviewer",
                "privacy_safety_reviewer",
            ],
        }[intensity]
        reviews.extend(
            {
                "finding_id": selected_id,
                "reviewer": reviewer,
                "verdict": "approved",
                "reason": "Synthetic golden evidence and arithmetic match.",
                "evidence_refs": [f"evidence.csv#finding_id={selected_id}"],
                "revision_round": 0,
            }
            for reviewer in required
        )
    write_workspace_artifacts(run_dir, findings, reviews)
    count, problems = consolidate_candidates(run_dir)
    assert not problems, problems
    count, problems = consolidate_reviews(run_dir)
    assert not problems, problems


def write_workspace_artifacts(
    run_dir: Path,
    findings: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
) -> None:
    """Emit a minimal, schema-valid artifact for every judgment-phase role."""
    write_agent_task_manifest(run_dir)
    reviews_by_reviewer: dict[str, list[dict[str, Any]]] = {}
    for review in reviews:
        reviews_by_reviewer.setdefault(review["reviewer"], []).append(review)
    findings_placed = False
    for task in TASKS:
        schema = task["output_schema"]
        role = task["role"]
        if schema == "analysis_result":
            doc: dict[str, Any] = {
                "role": role,
                "summary": "Synthetic golden analysis.",
                "limitations": [],
                "human_confirmation_needed": [],
            }
        elif schema == "automation_analysis_result":
            doc = {
                "role": role,
                "summary": "Synthetic fixture has no workflow configuration.",
                "available_signals": [],
                "control_gaps": [],
                "evidence_refs": [],
                "limitations": [
                    "Synthetic fixture does not include workflow configuration."
                ],
                "human_confirmation_needed": [],
            }
        elif schema == "journey_hypothesis":
            journey = role.replace("_journey_hypothesis_agent", "")
            journey_contracts = {
                "inbound": {
                    "entry": ["Inbound source or a positive form, demo, or contact-sales property in HubSpot"],
                    "milestones": ["Inbound intent captured", "Owner handoff", "Deal created or documented valid skip", "Open deal progression"],
                    "handoff": ["A high-intent contact has an accountable owner before the agreed SLA expires"],
                    "skips": ["Low-intent nurture contacts may remain without a deal"],
                    "tests": ["Check high-intent contacts for missing owner or deal progression", "Check inbound deals for source continuity"],
                },
                "outbound": {
                    "entry": ["Outbound, SDR, prospecting, or import signal in HubSpot"],
                    "milestones": ["Target selected", "Sales engagement", "Qualified response", "Deal progression"],
                    "handoff": ["Sales ownership remains explicit from prospecting through deal creation"],
                    "skips": ["A prior MQL stage is not required by default"],
                    "tests": ["Check qualified outbound records for owner and deal continuity"],
                },
                "abm": {
                    "entry": ["Target-account or account-tier property in HubSpot"],
                    "milestones": ["Account selected", "Buying group engaged", "Sales handoff", "Account-level deal progression"],
                    "handoff": ["The target account, buying contacts, owner, and deal remain associated"],
                    "skips": ["Contact-level MQL may be optional when the account rule is explicit"],
                    "tests": ["Check target accounts for missing buying-contact or deal associations"],
                },
                "partner": {
                    "entry": ["Partner, referral, reseller, or channel property in HubSpot"],
                    "milestones": ["Referral captured", "Partner source preserved", "Owner handoff", "Deal progression"],
                    "handoff": ["Partner context and internal ownership survive deal creation"],
                    "skips": ["A partner-qualified record may bypass marketing qualification"],
                    "tests": ["Check partner deals for owner, account, contact, and source continuity"],
                },
                "expansion": {
                    "entry": ["Customer state plus renewal, expansion, upsell, or cross-sell signal in HubSpot"],
                    "milestones": ["Customer eligibility", "Renewal or expansion trigger", "Account-owner handoff", "Commercial progression"],
                    "handoff": ["The deal remains connected to the customer company and accountable owner"],
                    "skips": ["A new-business MQL path is not required"],
                    "tests": ["Check renewal and expansion deals for customer-state and account continuity"],
                },
            }[journey]
            doc = {
                "role": role,
                "journey_pattern": journey,
                "verdict": "consistent_with_registry",
                "entry_signals": journey_contracts["entry"],
                "expected_milestones": journey_contracts["milestones"],
                "handoff_expectations": journey_contracts["handoff"],
                "valid_skips": journey_contracts["skips"],
                "leakage_tests": journey_contracts["tests"],
            }
        elif schema == "mixed_motion_assessment":
            doc = {
                "role": role,
                "journey_model_assessment": "Single dominant motion; no coexistence conflict.",
                "coexisting_patterns": [],
                "conflicts": [],
                "unclassified_motion_candidate": None,
                "unclassified_motion_evidence_refs": [],
                "unclassified_motion_limitations": [],
                "unclassified_motion_requires_confirmation": False,
            }
        elif schema == "candidate_findings":
            doc = {
                "candidate_findings": findings if not findings_placed else [],
                "rejected_checks": [],
                "coverage_limitations": [],
            }
            findings_placed = True
        elif schema == "root_cause_assessments":
            doc = {
                "role": role,
                "assessments": [],
            }
        elif schema == "review_decisions":
            doc = {"role": role, "reviews": reviews_by_reviewer.get(role, [])}
        elif schema == "recommendation_lanes":
            # Lane membership mirrors the deterministic adjudication rules.
            doc = {
                "priority_actions": [],
                "safe_operational_actions": [],
                "human_confirmation_needed": [],
                "observations_to_monitor": [],
                "do_not_auto_fix": [],
            }
            for finding in findings:
                model = LifecycleFinding.model_validate(finding)
                decisions = [
                    ReviewDecision.model_validate(row)
                    for row in reviews
                    if row["finding_id"] == finding["finding_id"]
                ]
                lane = action_lane(model, aggregate_review_status(decisions))
                doc[lane].append(
                    {
                        "finding_id": finding["finding_id"],
                        "owner_role": "revops_owner",
                        "expected_outcome": "Reviewed exception list confirmed with the business owner.",
                        "target": finding.get("field_name") or finding["object_type"],
                        "current_state": finding["business_impact"],
                        "desired_state": "Canonical lifecycle and association rule confirmed and measured.",
                        "implementation_steps": [
                            "Review the evidence with the accountable owner.",
                            "Approve the business rule and exception criteria.",
                            "Measure the result in the next audit run.",
                        ],
                        "approval_required": "Yes — business owner approval before any CRM change.",
                        "success_measure": "The next audit confirms the affected rate is reduced or the exception is documented.",
                        "evidence_refs": finding.get("evidence_refs") or ["evidence.csv"],
                    }
                )
        else:
            continue
        ok, problems = submit_task(run_dir, role, doc, resubmit=True)
        assert ok, (role, problems)


def generate_reports_and_clear_safety(run_dir: Path) -> None:
    generate_lifecycle_reports(run_dir)
    hashes = hash_files(run_dir, FINAL_DELIVERABLES)
    clearances = []
    for filename in FINAL_DELIVERABLES:
        path = run_dir / filename
        if not path.exists():
            continue
        for hit in scan_file(path):
            if hit.kind == "blocked_phrase":
                clearances.append(
                    {
                        "phrase": hit.excerpt,
                        "file": filename,
                        "file_sha256": hashes[filename],
                        "reason": "Privacy reviewer confirmed this appears only in an explicit blocked-actions boundary.",
                    }
                )
    (run_dir / "safety_clearance.json").write_text(
        json.dumps(clearances, ensure_ascii=False, indent=2), encoding="utf-8"
    )
