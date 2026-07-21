"""Journey-first human reports for the HubSpot Lifecycle Integrity Audit.

The decision report answers four questions in order:
1. Which selling journeys are represented in HubSpot?
2. What evidence supports each journey and its expected operating path?
3. Where can records fall out of that specific path?
4. Which existing deals and pre-deal populations should be reviewed or repaired?

General CRM profiling stays in the operator appendix. All commercial amounts
come from existing HubSpot deals. Contacts without deals are counted only as a
potential recoverable population and never receive an estimated amount.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List

from .sanitizer import sanitize_untrusted_value
from .lifecycle_score_contract import cited_measurement_ids


CREDIT_URL = "https://smartifymarketing.com"
GITHUB_URL = "https://github.com/AliceEinstein"
BRAND_NAME = "Smartify Marketing"
SLOGAN = "Your Strategic B2B Marketing Partner"

UNTRUSTED_MARKER = "[CRM_FIELD_VALUE:UNTRUSTED_DATA_ONLY]"

JOURNEY_ORDER = (
    "inbound_new_business",
    "outbound_sales_led",
    "abm_account_based",
    "partner_led",
    "expansion_renewal",
)
JOURNEY_LABELS = {
    "inbound_new_business": "Inbound new business",
    "outbound_sales_led": "Outbound sales-led",
    "abm_account_based": "ABM / account-based",
    "partner_led": "Partner-led",
    "expansion_renewal": "Expansion / renewal",
    "all_detected_journeys": "All detected journeys",
    "unassigned": "Unassigned",
    "single_motion": "Single-motion",
    "multi_motion": "Mixed-motion",
    "insufficient_evidence": "Insufficient evidence",
}
DIMENSION_LABELS = {
    "lifecycle_integrity": "Lifecycle path",
    "association_integrity": "Relationship continuity",
    "handoff_integrity": "Ownership and handoff",
    "attribution_continuity": "Source continuity",
    "state_coherence": "State coherence",
    "property_governance": "Journey-field governance",
}
CLASSIFICATION_LABELS = {
    "priority_actions": "Priority recovery",
    "safe_operational_actions": "Safe operational review",
    "human_confirmation_needed": "Business-rule confirmation",
    "observations_to_monitor": "Monitor",
    "do_not_auto_fix": "Do not auto-fix",
}
def humanize(key: Any) -> str:
    text = str(key or "")
    return (
        JOURNEY_LABELS.get(text)
        or DIMENSION_LABELS.get(text)
        or CLASSIFICATION_LABELS.get(text)
        or text.replace("_", " ").strip().capitalize()
    )


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _read_hypotheses(run_dir: Path) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    root = run_dir / "agent_workspace" / "hypotheses"
    for journey in JOURNEY_ORDER:
        role = {
            "inbound_new_business": "inbound_journey_hypothesis_agent",
            "outbound_sales_led": "outbound_journey_hypothesis_agent",
            "abm_account_based": "abm_journey_hypothesis_agent",
            "partner_led": "partner_journey_hypothesis_agent",
            "expansion_renewal": "expansion_journey_hypothesis_agent",
        }[journey]
        result[journey] = _read_json(root / f"{role}.json", {})
    result["mixed_motion"] = _read_json(
        root / "mixed_motion_journey_agent.json", {}
    )
    return result


def _entry_value(entry: Any, name: str, fallback: str = "To be confirmed") -> str:
    if entry is None:
        return fallback
    if isinstance(entry, dict):
        return str(entry.get(name) or fallback)
    return str(getattr(entry, name, None) or fallback)


def _entry_list(entry: Any, name: str) -> List[str]:
    if entry is None:
        return []
    values = entry.get(name, []) if isinstance(entry, dict) else getattr(entry, name, [])
    return [str(value) for value in (values or []) if str(value).strip()]


def _scope_text(row: Dict[str, Any]) -> str:
    denominator = row.get("denominator")
    affected = row.get("affected_records")
    if denominator is not None:
        percentage = row.get("affected_percentage")
        pct_text = f" ({percentage}%)" if percentage is not None else ""
        return f"{affected or 0} of {denominator} {humanize(row.get('object_type'))}{pct_text}"
    return str(row.get("materiality_explanation") or "Portal-level observation")


def _decimal_display(value: Any) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    return f"{number:,.2f}"


def _amount_text(amounts: Dict[str, Any]) -> str:
    if not amounts:
        return "No deal amount available"
    values = []
    for currency, amount in sorted(amounts.items()):
        label = "portal default currency" if currency == "portal_default" else currency
        values.append(f"{_decimal_display(amount)} ({label})")
    return " · ".join(values)




def _md_cell(value: Any) -> str:
    return str(value if value not in (None, "") else "—").replace("|", "\\|").replace("\n", " ")


def _md_untrusted(value: Any) -> str:
    """Render agent/CRM-derived inline text without Markdown interpretation."""
    text = _md_cell(value)
    for character in ("\\", "`", "*", "_", "[", "]", "<", ">", "~"):
        text = text.replace(character, "\\" + character)
    return text


def _evidence_links(row: Dict[str, Any]) -> List[str]:
    links = []
    for ref in row.get("evidence_refs") or []:
        text = str(ref)
        path = text.split("#", 1)[0]
        links.append(f"[{_md_cell(text)}]({path})")
    if not links:
        links.append("[Lifecycle measurements](processed/lifecycle_integrity_measurements.json)")
    return links


def _automation_label(coverage: Dict[str, Any]) -> str:
    status = str(coverage.get("status") or "unavailable")
    return {
        "full": "Full workflow coverage",
        "partial": "Partial workflow coverage",
        "configuration_only": "Workflow configuration only",
        "unavailable": "Workflow coverage unavailable",
        "permission_denied": "Workflow scope unavailable",
    }.get(status, status.replace("_", " ").capitalize())


def _automation_root_cause(view: Dict[str, Any], finding: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return deterministic and agent-confirmed context for one finding."""
    finding_id = str(finding.get("finding_id") or "")
    rows: List[Dict[str, Any]] = []
    measurement_ids = cited_measurement_ids(
        finding.get("evidence_refs") or [], view.get("measurement_by_id", {})
    )
    for measurement_id in sorted(measurement_ids):
        deterministic = view.get("automation_by_measurement", {}).get(measurement_id)
        if deterministic and (
            deterministic.get("workflow_aliases")
            or deterministic.get("score_fields")
            or deterministic.get("configuration_status") not in {"unknown", None}
        ):
            rows.append({"source": "deterministic", **deterministic})
    rows.extend(view.get("root_cause_by_finding", {}).get(finding_id, []))
    return rows


def _automation_summary(view: Dict[str, Any]) -> Dict[str, Any]:
    coverage = view.get("automation_coverage", {})
    checks = view.get("automation_measurements", {}).get("checks", [])
    return {
        "label": _automation_label(coverage),
        "status": str(coverage.get("status") or "unavailable"),
        "workflow_count": int(view.get("workflow_count", 0) or 0),
        "relevant_workflow_count": int(view.get("relevant_workflow_count", 0) or 0),
        "score_candidate_count": int(view.get("score_candidate_count", 0) or 0),
        "configuration_signals": len(checks),
        "defect_signals": sum(
            1 for row in checks if row.get("configuration_status") == "defect_confirmed"
        ),
        "limitations": list(view.get("automation_measurements", {}).get("limitations") or [])
        + list(coverage.get("limitations") or []),
    }


def _build_base_view(
    run_dir: Path,
    score: Dict[str, Any],
    registry: Any,
    adjudicated: List[dict],
    plan_by_lane: Dict[str, dict],
) -> Dict[str, Any]:
    run_dir = Path(run_dir)
    store = _read_json(run_dir / "processed" / "journey_evidence_store.json", {})
    manifest = _read_json(run_dir / "manifest.json", {})
    business_context = _read_json(run_dir / "business_context.json", {})
    account_info = _read_json(run_dir / "raw" / "account_info.json", {})
    measurement_doc = _read_json(
        run_dir / "processed" / "lifecycle_integrity_measurements.json", {}
    )
    measurements = measurement_doc.get("measurements", [])
    measurement_by_id = {row.get("id"): row for row in measurements}
    automation_coverage = _read_json(
        run_dir / "processed" / "automation_coverage.json",
        manifest.get("automation") or {"status": "unavailable"},
    )
    automation_measurements = _read_json(
        run_dir / "processed" / "automation_scoring_measurements.json", {}
    )
    workflows = _read_json(run_dir / "processed" / "workflow_inventory.json", [])
    score_summary = _read_json(
        run_dir / "processed" / "scoring_activation_summary.json", {}
    )
    root_cause_doc = _read_json(
        run_dir / "agent_workspace" / "root_cause" / "automation_root_cause_agent.json",
        {},
    )
    root_cause_by_finding: Dict[str, List[Dict[str, Any]]] = {}
    root_cause_rows = (
        root_cause_doc.get("assessments", [])
        if isinstance(root_cause_doc, dict)
        else []
    )
    for assessment in root_cause_rows:
        if isinstance(assessment, dict) and assessment.get("finding_id"):
            root_cause_by_finding.setdefault(str(assessment["finding_id"]), []).append(assessment)
    high_intent = _read_json(
        run_dir / "processed" / "high_intent_cohort_summary.json",
        store.get("high_intent_summary", {}),
    )
    intent_summary = _read_json(
        run_dir / "processed" / "intent_signal_summary.json",
        store.get("intent_signal_summary", {}),
    )
    hypotheses = _read_hypotheses(run_dir)
    pipeline_summary = _read_json(run_dir / "processed" / "pipeline_summary.json", {})
    object_counts = _read_json(run_dir / "processed" / "object_counts.json", {})
    field_empty_rates = _read_json(run_dir / "processed" / "field_empty_rates.json", {})
    identity = _read_json(run_dir / "processed" / "identity_completeness.json", {})
    lifecycle_distribution = _read_json(
        run_dir / "processed" / "lifecycle_distribution.json", {}
    )
    association = _read_json(run_dir / "processed" / "association_summary.json", {})
    data_age = _read_json(run_dir / "processed" / "data_age_summary.json", {})
    outliers: List[Dict[str, Any]] = []
    outlier_path = run_dir / "outlier_registry.csv"
    if outlier_path.exists():
        with outlier_path.open(encoding="utf-8") as fh:
            outliers = list(csv.DictReader(fh))

    findings = [
        row
        for row in adjudicated
        if row.get("review_status")
        in {"approved", "revised", "observation", "human_confirmation"}
    ]
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "observation": 4}
    findings.sort(key=lambda row: (severity_order.get(row.get("severity"), 9), row.get("finding_id", "")))
    finding_ids = {row.get("finding_id") for row in findings}
    reviewed_measurement_ids = set().union(
        *(
            cited_measurement_ids(row.get("evidence_refs") or [], measurement_by_id)
            for row in findings
        )
    ) if findings else set()
    leakage_rows = [
        row
        for row in measurements
        if row.get("leakage_candidate")
        and row.get("available")
        and (row.get("affected_records") or 0) > 0
    ]
    leakage_rows.sort(
        key=lambda row: (
            0 if row.get("id") in reviewed_measurement_ids else 1,
            -(row.get("affected_records") or 0),
            row.get("id", ""),
        )
    )
    assignment_counts_by_object = store.get("assignment_counts_by_object", {})
    counts = store.get("object_counts", {}) or object_counts
    window = (
        "Full portal history"
        if manifest.get("full_history")
        else f"Records created in the last {manifest.get('days')} days"
    )
    business_name = None
    for candidate in (
        business_context.get("business_name") if isinstance(business_context, dict) else None,
        manifest.get("business_name"),
        account_info.get("business_name") if isinstance(account_info, dict) else None,
        account_info.get("companyName") if isinstance(account_info, dict) else None,
        account_info.get("accountName") if isinstance(account_info, dict) else None,
    ):
        if candidate not in (None, ""):
            cleaned = sanitize_untrusted_value(str(candidate)).strip()
            marker = UNTRUSTED_MARKER + " "
            while cleaned.startswith(marker):
                cleaned = cleaned[len(marker):].lstrip()
            if cleaned and not cleaned.startswith("[REDACTED:"):
                business_name = cleaned[:120]
                break
    patterns = {pattern.journey_type: pattern for pattern in registry.patterns}
    journey_paths = []
    for journey in JOURNEY_ORDER:
        pattern = patterns.get(journey)
        hypothesis = hypotheses.get(journey, {})
        journey_paths.append(
            {
                "journey": journey,
                "pattern": pattern,
                "hypothesis": hypothesis,
                "entry_signals": _entry_list(hypothesis, "entry_signals"),
                "milestones": _entry_list(hypothesis, "expected_milestones"),
                "handoffs": _entry_list(hypothesis, "handoff_expectations"),
                "valid_skips": _entry_list(hypothesis, "valid_skips"),
                "leakage_tests": _entry_list(hypothesis, "leakage_tests"),
                "support": _entry_list(hypothesis, "supporting_evidence")
                or list(getattr(pattern, "supporting_evidence", []) or []),
            }
        )
    top_findings = [row for row in findings if row.get("severity") in {"critical", "high", "medium"}][:3]
    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "business_name": business_name,
        "score": score,
        "registry": registry,
        "patterns": patterns,
        "journey_paths": journey_paths,
        "mixed_assessment": hypotheses.get("mixed_motion", {}),
        "findings": findings,
        "finding_ids": finding_ids,
        "top_findings": top_findings,
        "plan_by_lane": plan_by_lane,
        "measurements": measurements,
        "measurement_by_id": measurement_by_id,
        "leakage_rows": leakage_rows,
        "pipeline_exposure": measurement_doc.get("pipeline_exposure", {}),
        "recovery_routing": measurement_doc.get("recovery_routing", {}),
        "intent_summary": intent_summary,
        "intent_coverage": intent_summary.get("coverage", {}),
        "high_intent": high_intent,
        "counts": counts,
        "window": window,
        "assignment_counts_by_object": assignment_counts_by_object,
        "ambiguous": list(registry.ambiguous_areas),
        "confirmations": list(registry.human_confirmation_needed),
        "truncated": sorted(k for k, value in (manifest.get("truncated") or {}).items() if value),
        "outliers": outliers,
        "pipeline_summary": pipeline_summary,
        "field_empty_rates": field_empty_rates,
        "identity": identity,
        "lifecycle_distribution": lifecycle_distribution,
        "association": association,
        "data_age": data_age,
        "activity": store.get("activity_summary", {}),
        "automation_coverage": automation_coverage,
        "automation_measurements": automation_measurements,
        "automation_by_measurement": {
            str(row.get("measurement_id")): row
            for row in automation_measurements.get("root_cause_links", [])
            if row.get("measurement_id")
        },
        "root_cause_by_finding": root_cause_by_finding,
        "workflow_count": len(workflows) if isinstance(workflows, list) else 0,
        "relevant_workflow_count": sum(
            1 for row in workflows if isinstance(row, dict) and row.get("relevant")
        )
        if isinstance(workflows, list)
        else 0,
        "score_candidate_count": len(score_summary.get("score_candidates", []))
        if isinstance(score_summary, dict)
        else 0,
    }






def _finding_recovery_class(view: Dict[str, Any], finding: Dict[str, Any]) -> str:
    measurement_ids = cited_measurement_ids(
        finding.get("evidence_refs") or [], view.get("measurement_by_id", {})
    )
    measurement = next(
        (view["measurement_by_id"][row] for row in sorted(measurement_ids)), {}
    )
    recoverability = measurement.get("recoverability")
    if recoverability == "open_deal_review":
        return "Immediate open-deal review"
    if recoverability == "potential_recoverable_population":
        return "Pre-deal recovery review"
    if recoverability == "system_repair":
        return "System repair"
    return "Business-rule confirmation"


def _recommendation_rows(view: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for finding in view["findings"]:
        lane = finding.get("action_lane")
        entry = view.get("plan_by_lane", {}).get(lane, {}).get(finding.get("finding_id"))
        rows.append(
            {
                "finding": finding,
                "entry": entry,
                "lane": humanize(lane),
                "recovery_class": _finding_recovery_class(view, finding),
            }
        )
    return rows




















def render_operator_appendix(view: Dict[str, Any]) -> str:
    automation = _automation_summary(view)
    lines = [
        "# Operator Appendix: Lifecycle Integrity Audit",
        "",
        "This appendix carries technical profile and implementation detail that supports, but does not replace, the journey-first decision report. It does not authorise CRM writes.",
        "",
        "## Validated Findings",
        "",
    ]
    if not view["findings"]:
        lines.append("No finding survived adjudication.")
    for finding in view["findings"]:
        measurement_ids = cited_measurement_ids(
            finding.get("evidence_refs") or [], view.get("measurement_by_id", {})
        )
        measurement = next(
            (view["measurement_by_id"][row] for row in sorted(measurement_ids)), {}
        )
        lines += [
            f"### {finding['finding_id']} — {humanize(finding['finding_id'])}",
            "",
            f"- Journey: {humanize(finding['journey_pattern'])}",
            f"- Dimension: {humanize(finding['integrity_dimension'])}",
            f"- Severity / confidence: {finding['severity']} / {finding['confidence_score']}/100",
            f"- Affected scope: {_scope_text(finding)}",
            f"- Leakage point: {measurement.get('leakage_point') or 'Not classified'}",
            f"- Existing deal amount in this measurement: {_amount_text(measurement.get('affected_deal_amount_by_currency', {}))}",
            f"- Evidence: {', '.join(_evidence_links(finding))}",
            f"- Assumptions: {'; '.join(finding.get('assumptions') or ['None recorded.'])}",
            f"- Limitations: {'; '.join(finding.get('limitations') or ['None recorded.'])}",
            "",
        ]

    lines += ["## Implementation Detail", ""]
    for row in _recommendation_rows(view):
        finding, entry = row["finding"], row["entry"]
        steps = _entry_list(entry, "implementation_steps") or ["Review evidence with the accountable owner."]
        lines += [
            f"### {finding['finding_id']} — {row['recovery_class']}",
            "",
            f"- Target: {_entry_value(entry, 'target', finding.get('object_type', 'HubSpot scope'))}",
            f"- Current state: {_entry_value(entry, 'current_state', _scope_text(finding))}",
            f"- Desired state: {_entry_value(entry, 'desired_state')}",
            f"- Owner: {_entry_value(entry, 'owner_role')}",
            f"- Approval gate: {_entry_value(entry, 'approval_required')}",
            f"- Expected result: {_entry_value(entry, 'expected_outcome')}",
            f"- Success measure: {_entry_value(entry, 'success_measure')}",
            "- Ordered steps:",
            *[f"  {index}. {step}" for index, step in enumerate(steps, 1)],
            f"- Evidence basis: {', '.join(_evidence_links(finding))}",
            f"- Risk note: {_entry_value(entry, 'risk_note', 'Keep the change reversible and log the approved scope.')}",
            "",
        ]

    lines += [
        "## Automation and Scoring Integrity",
        "",
        f"- Coverage: {automation['label']}; workflows observed: {automation['workflow_count']}; journey-relevant workflows: {automation['relevant_workflow_count']}; score-like outputs: {automation['score_candidate_count']}.",
        f"- Configuration signals: {automation['configuration_signals']}; confirmed configuration defects: {automation['defect_signals']}.",
        "- This layer identifies configuration evidence and possible root causes for lifecycle leaks. It does not prove per-record execution, reconstruct the full score model, or authorize workflow changes.",
        *[f"- Limitation: {item}" for item in automation["limitations"]],
        "- [Automation coverage](processed/automation_coverage.json)",
        "- [Workflow inventory](processed/workflow_inventory.json)",
        "- [Workflow dependency graph](processed/workflow_dependency_graph.json)",
        "- [Workflow performance summary](processed/workflow_performance_summary.json)",
        "- [Scoring activation summary](processed/scoring_activation_summary.json)",
        "- [Automation evidence](automation_evidence.csv)",
        "",
        "## Journey and Measurement Detail",
        "",
        "| Measurement | Journey | Dimension | Score link | Score control | Score role | Population key | Available | Affected | Denominator | Leakage point | Actual deal amount |",
        "|---|---|---|---|---|---|---|---|---:|---:|---|---:|",
    ]
    for row in view["measurements"]:
        lines.append(
            f"| `{_md_cell(row.get('id'))}` | {humanize(row.get('journey_pattern'))} | {humanize(row.get('integrity_dimension'))} | "
            f"{humanize(row.get('score_link')) if row.get('score_link') else '—'} | "
            f"{humanize(row.get('score_control')) if row.get('score_control') else '—'} | {humanize(row.get('score_role'))} | "
            f"{'`' + _md_cell(row.get('score_population_key')) + '`' if row.get('score_population_key') else '—'} | "
            f"{'Yes' if row.get('available') else 'No'} | {_md_cell(row.get('affected_records'))} | {_md_cell(row.get('denominator'))} | "
            f"{_md_cell(row.get('leakage_point'))} | {_md_cell(_amount_text(row.get('affected_deal_amount_by_currency', {})))} |"
        )
    lines += [
        "",
        "## Technical CRM Profile",
        "",
        f"- Snapshot scope: {view['window']}.",
        f"- Contacts: {view['counts'].get('contacts', 0)}; companies: {view['counts'].get('companies', 0)}; deals: {view['counts'].get('deals', 0)}.",
        f"- Deal pipelines: {len(view.get('pipeline_summary', {}).get('pipelines', []))}.",
        f"- Outlier rows: {len(view['outliers'])}.",
        f"- Activity metadata available: {'yes' if view.get('activity', {}).get('available') else 'no'}.",
        f"- Intent/activity coverage: {humanize(view.get('intent_coverage', {}).get('status', 'not_requested'))}; normalized signals: {view.get('intent_summary', {}).get('event_count', 0)}.",
        "",
        "Association, field-completeness, identity-validity, lifecycle-distribution, and data-age aggregates remain available in the processed JSON files. They are supporting diagnostics, not the purpose or main narrative of this audit.",
        "",
        "## Method and Constraints",
        "",
        f"- Deterministic lifecycle integrity score: {view['score']['overall_lifecycle_integrity_score']}/100."
        if view["score"]["overall_lifecycle_integrity_score"] is not None
        else "- Deterministic lifecycle integrity score: not issued because scored control coverage is below the reportable threshold.",
        "- Journey hypotheses are evidence-backed and isolated by motion; the mixed-motion role runs after the five journey roles.",
        "- A residual unclassified motion can be surfaced only as a human-confirmation observation. It cannot enter the registry, score, assignments, or leakage audit.",
        "- Raw HubSpot records are not available to judgment roles; evidence uses aggregates, sanitised labels, and salted record hashes.",
        "- Workflow and scoring configuration is read with one `automation`-scoped token, but the connector allowlist contains no workflow mutation endpoint; the runtime is structurally read-only.",
        "- Commercial amounts are aggregated only from existing deals. No amount is inferred for contacts without deals.",
        "- Every scored measurement declares one score link, one score control, one canonical population key, and one role. Mutually exclusive motion populations are denominator-weighted inside their control; breakdowns and overlapping supporting evidence do not score twice; recovery opportunities remain outside the score unless a separate primary control break exists.",
        "- Every recommendation remains read-only until a separate, explicitly approved implementation step.",
        "",
        "## Supporting Files",
        "",
        "- [Evidence rows](evidence.csv)",
        "- [Lifecycle measurements](processed/lifecycle_integrity_measurements.json)",
        "- [High-intent cohort summary](processed/high_intent_cohort_summary.json)",
        "- [Intent signal coverage](processed/intent_signal_coverage.json)",
        "- [Intent record index](processed/intent_record_index.json)",
        "- [Journey pattern registry](journey_pattern_registry.json)",
        "- [Outlier registry](outlier_registry.csv)",
        "- [Validated findings](findings.json)",
        "- [Review trace](review_trace.json)",
        "- [CRM context](crm_context.yaml)",
        "- [Schema discovery](schema_discovery_report.md)",
    ]
    return "\n".join(lines) + "\n"


















# The executive renderer is kept in a separate module so the report's
# business narrative can evolve without changing the older operator helpers
# above. These aliases are the only public renderer entry points imported by
# lifecycle_reports.py.
from .lifecycle_record_evidence import (  # noqa: E402  (late import avoids a cycle)
    build_report_record_evidence,
    write_report_record_evidence,
)
from .lifecycle_executive_report import (  # noqa: E402
    render_html as _render_executive_html,
    render_markdown as _render_executive_markdown,
)
from .lifecycle_cohorts import build_account_cohorts, write_account_cohort_evidence


def build_view(
    run_dir: Path,
    score: Dict[str, Any],
    registry: Any,
    adjudicated: List[dict],
    plan_by_lane: Dict[str, dict],
) -> Dict[str, Any]:
    view = _build_base_view(run_dir, score, registry, adjudicated, plan_by_lane)
    record_evidence = build_report_record_evidence(run_dir, view)
    write_report_record_evidence(run_dir, record_evidence)
    view["record_evidence"] = record_evidence
    account_cohorts = build_account_cohorts(run_dir, record_evidence)
    write_account_cohort_evidence(run_dir, account_cohorts)
    view["account_cohorts"] = account_cohorts
    return view


def render_markdown(view: Dict[str, Any]) -> str:
    return _render_executive_markdown(view)


def render_html(view: Dict[str, Any], markdown_text: str) -> str:
    return _render_executive_html(view, markdown_text)
