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
import html as html_mod
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .sanitizer import sanitize_untrusted_value


CREDIT_URL = "https://smartifymarketing.com"
GITHUB_URL = "https://github.com/AliceEinstein"
BRAND_NAME = "Smartify Marketing"
SLOGAN = "Your Strategic B2B Marketing Partner"

ACCENT = "#fe810e"
PRIMARY = "#964900"
TRACK = "#eadfd5"
INK = "#1f1b18"
INK_2 = "#5d544d"
CANVAS = "#fcf9f6"
DARK = "#1b1714"
DARK_TEXT = "#fffaf5"
ERROR = "#c1121f"
WARM = "#c98f60"
SERIF = '"Newsreader",Georgia,"Times New Roman",serif'
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
DO_NOT_AUTOMATE = [
    "Do not reset lifecycle stages in bulk.",
    "Do not overwrite original source values automatically.",
    "Do not move deals between pipeline stages without review.",
    "Do not reassign owners automatically.",
    "Do not create deal amounts for contacts that do not have deals.",
    "Do not merge companies without manual review.",
]


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


def _display_crm_value(value: Any) -> str:
    """Remove the machine-only untrusted-data marker for final presentation.

    The value has already passed deterministic redaction and remains escaped by
    the Markdown/HTML renderer. Removing the marker does not promote it to an
    instruction; it only keeps sanitized labels readable in the human report.
    """
    text = str(value or "")
    prefix = UNTRUSTED_MARKER + " "
    return text[len(prefix) :] if text.startswith(prefix) else text


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
    deterministic = view.get("automation_by_measurement", {}).get(finding_id)
    rows: List[Dict[str, Any]] = []
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


def build_view(
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
    leakage_rows = [
        row
        for row in measurements
        if row.get("leakage_candidate")
        and row.get("available")
        and (row.get("affected_records") or 0) > 0
    ]
    leakage_rows.sort(
        key=lambda row: (
            0 if row.get("id") in finding_ids else 1,
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


def _journey_status(pattern: Any) -> str:
    if pattern is None or not pattern.exists:
        return "Not detected"
    return humanize(pattern.audit_level)


def _journey_assignment(view: Dict[str, Any], journey: str, object_type: str) -> int:
    return int(
        view.get("assignment_counts_by_object", {})
        .get(object_type, {})
        .get(journey, 0)
    )


def _finding_recovery_class(view: Dict[str, Any], finding: Dict[str, Any]) -> str:
    measurement = view["measurement_by_id"].get(finding.get("finding_id"), {})
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


def _score_context(score: Dict[str, Any]) -> Dict[str, Any]:
    """Explain the deterministic score without turning it into a health rate."""
    overall = int(score.get("overall_lifecycle_integrity_score", 0))
    if overall >= 90:
        band = "Strong structural integrity with contained validated breaks"
    elif overall >= 75:
        band = "Usable foundation with material integrity gaps"
    elif overall >= 50:
        band = "Material lifecycle integrity risk"
    else:
        band = "Severe lifecycle integrity risk"
    deductions = []
    for dimension, row in score.get("dimension_scores", {}).items():
        deducted = int(row.get("deducted", 0) or 0)
        if not deducted:
            continue
        deductions.append(
            {
                "dimension": humanize(dimension),
                "score": int(row.get("score", 0) or 0),
                "max_points": int(row.get("max_points", 0) or 0),
                "deducted": deducted,
                "findings": [humanize(item.get("finding_id")) for item in row.get("findings", [])],
            }
        )
    deductions.sort(key=lambda row: (-row["deducted"], row["dimension"]))
    return {
        "band": band,
        "total_deducted": sum(row["deducted"] for row in deductions),
        "deductions": deductions,
    }


def _render_markdown_legacy(view: Dict[str, Any]) -> str:
    registry = view["registry"]
    score = view["score"]
    exposure = view["pipeline_exposure"]
    overall = score["overall_lifecycle_integrity_score"]
    open_deals = exposure.get("unique_open_deals_with_leakage_signals", 0)
    potential = exposure.get("potential_recoverable_pipeline_population", 0)
    actual_amount = _amount_text(exposure.get("actual_open_deal_amount_by_currency", {}))
    score_context = _score_context(score)
    automation = _automation_summary(view)
    routing = view.get("recovery_routing", {}).get("lanes", {})
    intent = view.get("intent_summary", {})
    intent_coverage = view.get("intent_coverage", {})
    lines = [
        "# HubSpot Lifecycle Integrity Audit",
        "",
        f"Audit date: {view['generated']} · Scope: {view['window']} · Read-only audit",
        "",
        "## 1. Executive Decision Summary",
        "",
        f"- Lifecycle integrity score: **{overall}/100**.",
        f"- Selling journey model: **{humanize(registry.primary_model)}**; mapping confidence **{score['mapping_confidence_score']}/100**.",
        f"- Validated leakage findings: **{len(view['findings'])}**.",
        f"- Existing open deals with deterministic leakage-candidate signals: **{open_deals}**; actual amount on those deals: **{actual_amount}**.",
        f"- Potential recoverable pipeline population: **{potential} high-intent contacts** across missing-owner or missing-deal checks. **No monetary amount is assigned to contacts without deals.**",
        f"- Automation & scoring coverage: **{automation['label']}** — {automation['workflow_count']} workflows observed ({automation['relevant_workflow_count']} journey-relevant), {automation['score_candidate_count']} score-like outputs visible, and {automation['configuration_signals']} configuration signal(s).",
        "",
        f"### How to read {overall}/100",
        "",
        f"**{score_context['band']}.** The score begins at 100 and deducts points only for findings that survived reviewer adjudication as approved or revised.",
        "",
    ]
    if score_context["deductions"]:
        lines.extend(
            f"- **{row['dimension']}: {row['score']}/{row['max_points']}** — {row['deducted']} point{'s' if row['deducted'] != 1 else ''} deducted"
            + (f" for {', '.join(row['findings'])}." if row["findings"] else ".")
            for row in score_context["deductions"]
        )
    else:
        lines.append("- No approved or revised finding caused a point deduction in this run.")
    pipeline_exposure_rows = [
        f"| {_md_cell(_display_crm_value(row.get('pipeline_label')))} | {row.get('open_deals_with_leakage_signals', 0)} | {_md_cell(_amount_text(row.get('amount_by_currency', {})))} | [evidence.csv](evidence.csv) |"
        for row in exposure.get("by_pipeline", [])
    ] or ["| — | 0 | No deal amount available | [evidence.csv](evidence.csv) |"]
    lines += [
        f"- Journey mapping confidence is reported separately at **{score['mapping_confidence_score']}/100**; it describes how confidently HubSpot evidence identifies the selling model.",
        "- Candidate leakage populations do not reduce the score until they survive review. They remain visible in the leakage map and pipeline-exposure sections.",
        "- This is not a percentage of healthy records, a funnel-conversion score, or an estimate of revenue loss. A high score can coexist with a small number of commercially important leaks.",
        "",
        "The report prioritises the selling journey and its breakpoints. General CRM completeness, identity, association, and data-age profiling is retained in the operator appendix.",
        "",
        "### Decisions to make now",
        "",
    ]
    if view["top_findings"]:
        for finding in view["top_findings"]:
            lines.append(
                f"- {humanize(finding['finding_id'])}: {_scope_text(finding)}. {finding['business_impact']}"
            )
    else:
        lines.append("- No reviewed finding is above observation level; continue monitoring the measured journey checks.")

    lines += [
        "",
        "## 2. Detected Selling Journey Model",
        "",
        f"The portal is classified as **{humanize(registry.primary_model)}**. Journey confidence is evidence confidence, not funnel performance.",
        "",
        "| Journey | Confidence | Audit level | Assigned deals | High-intent contacts |",
        "|---|---:|---|---:|---:|",
    ]
    for journey in JOURNEY_ORDER:
        pattern = view["patterns"].get(journey)
        confidence = pattern.confidence_score if pattern else 0
        lines.append(
            f"| {humanize(journey)} | {confidence}/100 | {_journey_status(pattern)} | "
            f"{_journey_assignment(view, journey, 'deals')} | "
            f"{_journey_assignment(view, journey, 'high_intent_contacts')} |"
        )
    mixed = view.get("mixed_assessment", {})
    if mixed.get("journey_model_assessment"):
        lines += ["", f"Mixed-motion assessment: {mixed['journey_model_assessment']}"]
    if mixed.get("unclassified_motion_candidate"):
        lines += [
            "",
            f"Residual HubSpot signals suggest an **unclassified motion candidate: {mixed['unclassified_motion_candidate']}**. This is an observation requiring human confirmation; it is not a registered journey, scored pattern, record assignment, or leakage audit.",
        ]

    lines += ["", "## 3. Journey Evidence and Operating Paths", ""]
    for path in view["journey_paths"]:
        pattern = path["pattern"]
        if pattern is None or (not pattern.exists and not pattern.confidence_score):
            continue
        lines += [
            f"### {humanize(path['journey'])}",
            "",
            f"Confidence: **{pattern.confidence_score}/100** · Audit level: **{humanize(pattern.audit_level)}**.",
            "",
            "Observed entry signals:",
            *([f"- {item}" for item in path["entry_signals"]] or ["- Entry rule not confirmed from the available evidence."]),
            "",
            "Expected operating path:",
            "",
            " → ".join(path["milestones"]) if path["milestones"] else "Path milestones require business confirmation.",
            "",
            "Handoff expectations:",
            *([f"- {item}" for item in path["handoffs"]] or ["- Handoff rule requires confirmation."]),
            "",
            "Valid skips and exceptions:",
            *([f"- {item}" for item in path["valid_skips"]] or ["- No journey-specific skip was confirmed."]),
            "",
            "Evidence basis:",
            *([f"- {item}" for item in path["support"]] or ["- No positive evidence beyond the deterministic confidence components."]),
            "",
        ]

    lines += [
        "## 4. Journey Leakage Map",
        "",
        "A validated finding survived the reviewer gates. A candidate remains a deterministic review population and must not be treated as proven leakage until adjudicated.",
        "",
        "| Journey | Leakage point | Affected scope | Status | Trace |",
        "|---|---|---:|---|---|",
    ]
    if view["leakage_rows"]:
        for row in view["leakage_rows"]:
            status = "Validated finding" if row.get("id") in view["finding_ids"] else "Candidate for review"
            lines.append(
                f"| {humanize(row.get('journey_pattern'))} | {_md_cell(row.get('leakage_point') or humanize(row.get('id')))} | "
                f"{_md_cell(_scope_text(row))} | {status} | [evidence rows](evidence.csv) · `{_md_cell(row.get('id'))}` |"
            )
    else:
        lines.append("| — | No affected leakage candidate was measured | — | — | [measurements](processed/lifecycle_integrity_measurements.json) |")

    lines += [
        "",
        "## 5. Pipeline Exposure and Recoverable Population",
        "",
        "### Existing deals with leakage-candidate signals",
        "",
        f"- Unique open deals: **{open_deals}**.",
        f"- Open deals with amount: **{exposure.get('open_deals_with_amount', 0)}**; without amount: **{exposure.get('open_deals_without_amount', 0)}**.",
        f"- Actual amount recorded on those open deals: **{actual_amount}**.",
        "- This is exposed pipeline for review, not a forecast of revenue loss. Each deal is traceable by salted record hash, pipeline, and stage in `evidence.csv`.",
        "",
        "| Pipeline | Open deals with signals | Actual deal amount | Trace |",
        "|---|---:|---:|---|",
    ]
    pipeline_rows = exposure.get("by_pipeline", [])
    if pipeline_rows:
        for row in pipeline_rows:
            lines.append(
                f"| {_md_cell(_display_crm_value(row.get('pipeline_label')))} | {row.get('open_deals_with_leakage_signals', 0)} | "
                f"{_md_cell(_amount_text(row.get('amount_by_currency', {})))} | [evidence rows](evidence.csv) |"
            )
    else:
        lines.append("| — | 0 | No deal amount available | [evidence rows](evidence.csv) |")
    lines += [
        "",
        "### Potential recoverable pipeline population",
        "",
        "These are high-intent HubSpot contacts with missing ownership and/or missing deal progression. They may warrant recovery action, but they are not booked pipeline.",
        "",
        "| Journey | High-intent contacts | Without owner | Without associated deal | Amount |",
        "|---|---:|---:|---:|---|",
    ]
    high_intent_rows = view.get("high_intent", {}).get("by_journey", {})
    if high_intent_rows:
        for journey, row in sorted(high_intent_rows.items(), key=lambda item: JOURNEY_ORDER.index(item[0]) if item[0] in JOURNEY_ORDER else 99):
            lines.append(
                f"| {humanize(journey)} | {row.get('total', 0)} | {row.get('without_owner', 0)} | "
                f"{row.get('without_associated_deal', 0) if row.get('deal_association_available') else 'Unavailable'} | **No amount assigned** |"
            )
    else:
        lines.append("| — | 0 | 0 | 0 | **No amount assigned** |")

    routing = view.get("recovery_routing", {}).get("lanes", {})
    intent = view.get("intent_summary", {})
    intent_coverage = view.get("intent_coverage", {})
    lines += [
        "",
        "### Intent evidence and commercial recovery lanes",
        "",
        f"Normalized intent/activity coverage: **{humanize(intent_coverage.get('status', 'not_requested'))}** · **{intent.get('event_count', 0)}** record-linked signal(s). This evidence enriches the existing leakage engine; it does not replace its measurements or lower the score by itself.",
        "",
        "| Recovery lane | Population | Count | Amount treatment |",
        "|---|---|---:|---|",
        f"| Missing-deal / pre-deal recovery | Contacts with intent or existing high-intent evidence and no deal path | {routing.get('missing_deal_predeal_recovery', {}).get('count', potential)} | No amount assigned without an existing deal |",
        f"| Active-deal leakage / escalation | Open deals with intent signal and no deterministic escalation continuity | {routing.get('active_deal_leakage_and_escalation', {}).get('count', 0)} | Actual open-deal amount only; not a forecast |",
        f"| Closed-lost recovery | Closed-lost deals with post-loss intent and no successor/handoff path | {routing.get('closed_lost_recovery', {}).get('count', 0)} | Historical closed-lost amount is context only; excluded from open pipeline |",
        "",
        "Closed-lost recovery opportunities are intentionally displayed separately from score-bearing leakage findings. A recovery signal is a commercial review opportunity, not proof of recoverable revenue.",
    ]

    lines += [
        "",
        "## 6. Leakage Findings and Root Causes",
        "",
    ]
    if not view["findings"]:
        lines.append("No candidate finding survived review. Deterministic candidate populations remain visible in the leakage map.")
    for finding in view["findings"]:
        assumptions = finding.get("assumptions") or [
            "Root cause is unconfirmed; validate the journey rule and accountable owner before changing HubSpot."
        ]
        automation_rows = _automation_root_cause(view, finding)
        automation_lines = []
        if automation_rows:
            automation_lines = ["Automation/scoring root-cause signal:"]
            for row in automation_rows:
                aliases = _md_untrusted(
                    ", ".join(row.get("workflow_aliases") or []) or "No workflow alias"
                )
                score_fields = _md_untrusted(
                    ", ".join(row.get("score_fields") or []) or "None observed"
                )
                evidence = _md_untrusted(
                    ", ".join(row.get("evidence_refs") or [])
                    or "No automation evidence ref"
                )
                automation_lines.append(
                    f"- Configuration **{_md_untrusted(row.get('configuration_status', 'unknown'))}**; causal status **{_md_untrusted(row.get('causal_status', 'unverified'))}**; confidence **{row.get('confidence', row.get('confidence_score', 0))}/100**; workflows: **{aliases}**; score outputs: **{score_fields}**; evidence: `{evidence}`."
                )
                automation_lines.extend(
                    f"  - Limitation: {_md_untrusted(item)}"
                    for item in (row.get("limitations") or [])
                )
        else:
            automation_lines = [
                "Automation/scoring root-cause signal: **Not established for this finding.** "
                + (
                    "Workflow coverage was unavailable, so configuration causality was not assessed."
                    if automation["status"] in {"unavailable", "permission_denied"}
                    else "No relevant workflow or score relationship was established."
                )
            ]
        lines += [
            f"### {humanize(finding['finding_id'])}",
            "",
            f"Stable ID: `{finding['finding_id']}` · Journey: **{humanize(finding['journey_pattern'])}** · Severity: **{finding['severity']}** · Confidence: **{finding['confidence_score']}/100**.",
            f"Affected scope: **{_scope_text(finding)}**.",
            f"Business impact: {finding['business_impact']}",
            "Evidence: " + ", ".join(_evidence_links(finding)),
            *automation_lines,
            "Root-cause hypotheses:",
            *[f"- {item}" for item in assumptions],
            "",
        ]

    lines += [
        "## 7. Recovery and System Repair Plan",
        "",
        "The recovery plan separates immediate record review from system repair. No item authorises a HubSpot write.",
        "",
        "| Workstream | Finding | Owner | Expected result | Approval |",
        "|---|---|---|---|---|",
    ]
    recommendations = _recommendation_rows(view)
    if recommendations:
        for row in recommendations:
            finding, entry = row["finding"], row["entry"]
            lines.append(
                f"| {row['recovery_class']} | {humanize(finding['finding_id'])} | {_md_cell(_entry_value(entry, 'owner_role'))} | "
                f"{_md_cell(_entry_value(entry, 'expected_outcome'))} | {_md_cell(_entry_value(entry, 'approval_required'))} |"
            )
    else:
        lines.append("| Monitor | No validated recovery action | — | Continue measurement | — |")
    for row in recommendations:
        finding, entry = row["finding"], row["entry"]
        steps = _entry_list(entry, "implementation_steps") or ["Review the evidence with the accountable business owner."]
        lines += [
            "",
            f"### {humanize(finding['finding_id'])} · {row['recovery_class']}",
            "",
            f"- Target: {_entry_value(entry, 'target', finding.get('field_name') or finding.get('object_type', 'HubSpot records'))}",
            f"- Current state: {_entry_value(entry, 'current_state', _scope_text(finding))}",
            f"- Desired state: {_entry_value(entry, 'desired_state')}",
            f"- Owner: {_entry_value(entry, 'owner_role')}",
            f"- Approval: {_entry_value(entry, 'approval_required')}",
            "- Steps:",
            *[f"  {index}. {step}" for index, step in enumerate(steps, 1)],
            f"- Success measure: {_entry_value(entry, 'success_measure')}",
            f"- Evidence basis: {', '.join(_evidence_links(finding))}",
        ]

    lines += [
        "",
        "## 8. Monitoring and Next Review",
        "",
        "Re-run after approved ownership, association, lifecycle, source, routing, or deal-creation changes and before the next pipeline review.",
        "",
        "Monitor these controls:",
    ]
    monitor_rows = view["leakage_rows"][:8]
    lines.extend(
        [
            f"- {humanize(row['id'])}: current affected population {row.get('affected_records', 0)}; trace with `{row['id']}` in `evidence.csv`."
            for row in monitor_rows
        ]
        or ["- No affected deterministic leakage candidate is currently measurable."]
    )
    lines += [
        "",
        "## 9. Evidence, Assumptions, and Limits",
        "",
        "- The audit uses HubSpot records and properties only. A field synced from another tool is used only after it exists as a HubSpot property and carries journey or leakage evidence.",
        "- Deal and pipeline claims use existing HubSpot deal records and are traceable through salted record hashes in `evidence.csv`.",
        "- Contacts without deals may be labelled a potential recoverable pipeline population, but they never receive a monetary value.",
        f"- Intent/activity coverage: {humanize(view.get('intent_coverage', {}).get('status', 'not_requested'))}; {view.get('intent_summary', {}).get('event_count', 0)} normalized record-linked signal(s). High/medium signals support review and journey mapping but do not prove buying intent.",
        "- Closed-lost recovery is a separate commercial review lane. Historical closed-lost amount is context only and is excluded from open pipeline and integrity scoring.",
        "- Aggregate campaign, social, and advertising metrics provide channel context; they are not treated as person-level intent without a HubSpot record link.",
        "- Deterministic leakage candidates are not automatically validated findings; reviewer adjudication remains authoritative.",
        f"- Automation & scoring coverage: {automation['label']}; configuration evidence does not prove per-record workflow execution or full score-model correctness.",
        *[f"- Automation limitation: {item}" for item in automation["limitations"]],
        *[f"- Limitation: {item}" for item in view["ambiguous"]],
        *[f"- Business confirmation needed: {item}" for item in view["confirmations"][:8]],
    ]
    if view["truncated"]:
        lines.append(f"- Snapshot truncation affected: {', '.join(view['truncated'])}.")
    lines += [
        "",
        "### Actions That Should Not Be Automated",
        "",
        *[f"- {item}" for item in DO_NOT_AUTOMATE],
        "",
        "Supporting files:",
        "",
        "- [Evidence rows](evidence.csv)",
        "- [Lifecycle measurements](processed/lifecycle_integrity_measurements.json)",
        "- [High-intent cohort summary](processed/high_intent_cohort_summary.json)",
        "- [Intent signal coverage](processed/intent_signal_coverage.json)",
        "- [Intent signal store](processed/intent_signal_store.jsonl)",
        "- [Journey pattern registry](journey_pattern_registry.json)",
        "- [Automation/scoring measurements](processed/automation_scoring_measurements.json)",
        "- [Workflow inventory](processed/workflow_inventory.json)",
        "- [Automation evidence](automation_evidence.csv)",
        "- [Validated findings](findings.json)",
        "- [Review trace](review_trace.json)",
        "- [Operator appendix](operator_appendix.md)",
        "",
        "Keep the HTML file with the output folder so relative evidence links work. For distribution, use Print → Save as PDF and share the rendered report, not the raw snapshot.",
        "",
        "---",
        f"{BRAND_NAME} · {SLOGAN}",
        f"Website: {CREDIT_URL}",
        f"GitHub: {GITHUB_URL}",
    ]
    return "\n".join(lines) + "\n"


def _detected_paths(view: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        path
        for path in view["journey_paths"]
        if path["pattern"] is not None
        and (path["pattern"].exists or path["pattern"].confidence_score)
    ]


def _business_verdict(view: Dict[str, Any]) -> str:
    registry = view["registry"]
    model = humanize(registry.primary_model)
    finding_count = len(view["findings"])
    candidate_count = len(view["leakage_rows"])
    if finding_count:
        return (
            f"HubSpot is currently organised around a {model.lower()} selling motion. "
            f"The main journey is visible, but {finding_count} reviewed break(s) and "
            f"{max(candidate_count - finding_count, 0)} additional review population(s) "
            "can interrupt the path from buyer intent to owned, traceable pipeline."
        )
    if candidate_count:
        return (
            f"HubSpot shows a {model.lower()} selling motion with review populations at "
            "the handoff points. The evidence is useful for prioritisation, but no "
            "candidate has yet been confirmed as an integrity break."
        )
    return (
        f"HubSpot shows a {model.lower()} selling motion with no affected deterministic "
        "leakage population in this snapshot. Continue monitoring the handoffs that "
        "connect intent, ownership, deal creation, and progression."
    )


def _decision_rows(view: Dict[str, Any]) -> List[Dict[str, str]]:
    exposure = view["pipeline_exposure"]
    routing = view.get("recovery_routing", {}).get("lanes", {})
    active = routing.get("active_deal_leakage_and_escalation", {})
    closed = routing.get("closed_lost_recovery", {})
    return [
        {
            "priority": "Protect open pipeline",
            "headline": f"{exposure.get('unique_open_deals_with_leakage_signals', 0)} open deal(s) · {_amount_text(exposure.get('actual_open_deal_amount_by_currency', {}))}",
            "detail": "Review the existing deals named by the leakage engine. This is actual HubSpot deal amount, not a loss forecast.",
        },
        {
            "priority": "Capture missed demand",
            "headline": f"{routing.get('missing_deal_predeal_recovery', {}).get('count', exposure.get('potential_recoverable_pipeline_population', 0))} contact(s) without a deal path",
            "detail": "These contacts may create recoverable pipeline. No amount is assigned until a deal exists.",
        },
        {
            "priority": "Recover renewed demand",
            "headline": f"{closed.get('count', 0)} closed-lost deal(s) with post-loss intent",
            "detail": f"Historical context only: {_amount_text(closed.get('historical_closed_lost_amount_by_currency', {}))}. Check for a successor deal, owner, task, or re-engagement route.",
        },
        {
            "priority": "Escalate live intent",
            "headline": f"{active.get('count', 0)} open deal(s) with no clear next step",
            "detail": "Fresh buyer activity after the latest deal signal should create a visible follow-up action.",
        },
    ]


def _breakpoint_detail(row: Dict[str, Any], view: Dict[str, Any]) -> Dict[str, str]:
    measurement_id = str(row.get("id") or "")
    expected = {
        "deals_without_company": "Every deal remains connected to an account.",
        "deals_without_contact": "Every deal has a traceable buying contact.",
        "inbound_deals_without_source_trace": "Inbound source survives the handoff into the deal.",
        "active_deal_intent_without_escalation": "Fresh intent on an open deal creates a next action.",
        "intent_signals_without_deal": "A qualified intent signal reaches an owner and a deal decision.",
        "closed_lost_recovery_opportunity": "Post-loss intent enters a recovery path or successor deal.",
        "lifecycle_field_fragmentation": "One canonical lifecycle field governs the path.",
    }.get(measurement_id, "The next journey step is explicit and traceable.")
    consequence = {
        "deals_without_company": "Pipeline reporting and account-level follow-up can break.",
        "deals_without_contact": "Sales may not know which buying group to progress.",
        "inbound_deals_without_source_trace": "Marketing contribution cannot be tied cleanly to pipeline.",
        "active_deal_intent_without_escalation": "A live buying signal can go quiet inside an open deal.",
        "intent_signals_without_deal": "Demand may remain outside pipeline and never receive sales follow-up.",
        "closed_lost_recovery_opportunity": "Renewed demand may be ignored after the original deal is lost.",
        "lifecycle_field_fragmentation": "Different teams can read different lifecycle states.",
    }.get(measurement_id, "The next team or system control may not receive the record.")
    if row.get("id") in view["finding_ids"]:
        status = "Validated break"
    elif not row.get("available", True):
        status = "Not assessable"
    else:
        status = "Review candidate"
    return {
        "connection": str(row.get("leakage_point") or humanize(measurement_id)),
        "expected": expected,
        "observed": _scope_text(row),
        "consequence": consequence,
        "status": status,
        "trace": measurement_id,
    }


def _root_cause_summary(view: Dict[str, Any], finding: Dict[str, Any], automation: Dict[str, Any]) -> str:
    rows = _automation_root_cause(view, finding)
    if rows:
        row = rows[0]
        return (
            f"Configuration: {_md_untrusted(row.get('configuration_status', 'unknown'))}; "
            f"causal status: {_md_untrusted(row.get('causal_status', 'unverified'))}; "
            f"confidence: {row.get('confidence', row.get('confidence_score', 0))}/100."
        )
    if automation["status"] in {"unavailable", "permission_denied"}:
        return "Workflow coverage was unavailable, so configuration causality was not assessed."
    return "No relevant workflow or score relationship was established."


def _monitor_rows(view: Dict[str, Any]) -> List[str]:
    rows = [
        "High-intent contacts without an owner or deal after the agreed SLA.",
        "Open deals with a fresh intent signal and no later task, call, meeting, or email.",
        "Closed-lost deals with post-loss intent and no successor or recovery action.",
    ]
    rows.extend(
        f"{humanize(row['id'])}: {row.get('affected_records', 0)} affected in this snapshot."
        for row in view["leakage_rows"][:5]
    )
    return list(dict.fromkeys(rows))


def render_markdown(view: Dict[str, Any]) -> str:
    registry = view["registry"]
    score = view["score"]
    exposure = view["pipeline_exposure"]
    overall = score["overall_lifecycle_integrity_score"]
    automation = _automation_summary(view)
    intent = view.get("intent_summary", {})
    intent_coverage = view.get("intent_coverage", {})
    routing = view.get("recovery_routing", {}).get("lanes", {})
    decisions = _decision_rows(view)
    detected = _detected_paths(view)
    score_context = _score_context(score)
    lines = [
        "# HubSpot Lifecycle Integrity Audit",
        "",
        f"Audit date: {view['generated']} · Scope: {view['window']} · Read-only audit",
        "",
        "## 1. Executive Verdict",
        "",
        _business_verdict(view),
        "",
        f"### Lifecycle Integrity Score: {overall}/100",
        "",
        f"**{score_context['band']}.** This score starts at 100 and deducts points only for findings that passed reviewer adjudication as approved or revised.",
        "",
    ]
    if score_context["deductions"]:
        lines.extend(
            f"- **{row['dimension']}: {row['score']}/{row['max_points']}** — {row['deducted']} point{'s' if row['deducted'] != 1 else ''} deducted"
            + (f" for {', '.join(row['findings'])}." if row["findings"] else ".")
            for row in score_context["deductions"]
        )
    else:
        lines.append("- No approved or revised finding caused a point deduction in this run.")
    lines += [
        f"- Mapping confidence is separate at **{score['mapping_confidence_score']}/100**. It measures how confidently HubSpot evidence identifies the selling model, not how well the funnel converts.",
        "- The score is not a healthy-record percentage, conversion rate, or estimate of revenue loss. Candidate leakage and recovery opportunities remain visible without lowering the score until they are adjudicated.",
        "",
        "### Decisions this week",
        "",
        "| Decision | What the audit found | Why it matters |",
        "|---|---|---|",
    ]
    lines.extend(f"| **{row['priority']}** | {row['headline']} | {row['detail']} |" for row in decisions)
    lines += [
        "",
        f"Automation and scoring root-cause coverage: **{automation['label']}**. This is a diagnostic layer; it does not prove per-record workflow execution or permit CRM writes.",
        "",
        "## 2. How This HubSpot Selling Journey Works",
        "",
        f"The current portal is classified as **{humanize(registry.primary_model)}**. The classification is based on HubSpot properties, pipelines, associations, and record-linked activity; it is evidence confidence, not a performance score.",
        "",
        "**Expected operating path:** Demand captured → intent recognised → owner assigned → deal created or valid skip recorded → deal progressed → won, lost, or re-engaged.",
        "",
        "| Motion | Evidence confidence | What is actually represented |",
        "|---|---:|---|",
    ]
    for path in detected:
        pattern = path["pattern"]
        support = ", ".join(path["support"][:2]) or "Evidence threshold reached."
        lines.append(
            f"| {humanize(path['journey'])} | {pattern.confidence_score}/100 | {_md_cell(support)} ({_journey_assignment(view, path['journey'], 'deals')} deal(s), {_journey_assignment(view, path['journey'], 'high_intent_contacts')} high-intent contact(s)) |"
        )
    if not detected:
        lines.append("| Insufficient evidence | — | No journey reached the evidence threshold. |")
    mixed = view.get("mixed_assessment", {})
    if mixed.get("journey_model_assessment"):
        lines += ["", f"Mixed-motion review: {mixed['journey_model_assessment']}"]
    if mixed.get("unclassified_motion_candidate"):
        lines += [
            "",
            f"Residual signals suggest an **unclassified motion candidate: {_md_untrusted(mixed['unclassified_motion_candidate'])}**. It requires human confirmation and is not registered, scored, assigned, or audited as a journey.",
        ]
    for path in detected:
        milestones = path["milestones"] or ["Path milestones require business confirmation"]
        lines += [
            "",
            f"**{humanize(path['journey'])} path:** {' → '.join(milestones)}.",
            f"Entry evidence: {_md_cell('; '.join(path['entry_signals'][:3]) or 'Requires confirmation.')}",
            f"Handoff expectation: {_md_cell('; '.join(path['handoffs'][:2]) or 'Requires confirmation.')}",
        ]

    lines += [
        "",
        "## 3. Where the Journey Breaks",
        "",
        "The existing leakage engine identifies structural breaks. The intent/activity layer adds timing and commercial context: it helps prioritise a break, detect escalation points, and surface recovery opportunities; it does not replace the deterministic checks.",
        "",
        "| Journey connection | What should happen | What was observed | Business consequence | Status | Trace |",
        "|---|---|---|---|---|---|",
    ]
    breakpoint_rows = [_breakpoint_detail(row, view) for row in view["leakage_rows"]]
    if breakpoint_rows:
        lines.extend(
            f"| {row['connection']} | {row['expected']} | {row['observed']} | {row['consequence']} | **{row['status']}** | `evidence.csv#{row['trace']}` |"
            for row in breakpoint_rows
        )
    else:
        lines.append("| — | No affected break measured | — | Continue monitoring | **No current break** | `processed/lifecycle_integrity_measurements.json` |")
    pipeline_exposure_rows = [
        f"| {_md_cell(_display_crm_value(row.get('pipeline_label')))} | {row.get('open_deals_with_leakage_signals', 0)} | {_md_cell(_amount_text(row.get('amount_by_currency', {})))} | [evidence.csv](evidence.csv) |"
        for row in exposure.get("by_pipeline", [])
    ] or ["| — | 0 | No deal amount available | [evidence.csv](evidence.csv) |"]
    lines += [
        "",
        "A **validated break** affects the score only after reviewer approval. A **review candidate** is a deterministic population that needs business confirmation. A **recovery opportunity** can be commercially important without being a score-bearing defect. **Not assessable** means the required data or permission was unavailable; it never means zero.",
        "",
        "## 4. Pipeline to Protect and Demand to Recover",
        "",
        "These lanes keep commercial amounts separate and prevent double-counting.",
        "",
        "| Lane | Population | Amount shown | Recommended reading |",
        "|---|---:|---|---|",
        f"| **Protect open pipeline** | {exposure.get('unique_open_deals_with_leakage_signals', 0)} open deal(s) | {_amount_text(exposure.get('actual_open_deal_amount_by_currency', {}))} | Existing deal amount to review; not a forecast of loss. |",
        f"| **Active-deal escalation** | {routing.get('active_deal_leakage_and_escalation', {}).get('count', 0)} open deal(s) with intent and no clear next step | {_amount_text(routing.get('active_deal_leakage_and_escalation', {}).get('amount_by_currency', {}))} | Escalate the live deal review; actual amount only. |",
        f"| **Capture missed demand** | {routing.get('missing_deal_predeal_recovery', {}).get('count', exposure.get('potential_recoverable_pipeline_population', 0))} contact(s) without a deal path | **No amount assigned** | Potential recoverable pipeline, not booked pipeline. |",
        f"| **Recover renewed demand** | {routing.get('closed_lost_recovery', {}).get('count', 0)} closed-lost deal(s) with post-loss intent | {_amount_text(routing.get('closed_lost_recovery', {}).get('historical_closed_lost_amount_by_currency', {}))} historical context | Check successor deal, owner, task, or re-engagement route; excluded from open pipeline and score. |",
        "",
        "**Existing deal exposure by pipeline:**",
        "",
        "| Pipeline | Open deals with leakage signals | Actual deal amount | Trace |",
        "|---|---:|---:|---|",
        *pipeline_exposure_rows,
        "",
        f"Intent evidence: **{intent.get('event_count', 0)}** normalized record-linked signal(s), coverage **{humanize(intent_coverage.get('status', 'not_requested'))}**. Sources observed: **{', '.join(sorted(intent.get('counts_by_source', {}).keys())) or 'none'}**. Aggregate campaign, social, and advertising metrics remain channel context unless linked to a HubSpot record.",
        "",
        "## 5. Why the Breaks Are Happening",
        "",
        "For each material break, the diagnostic chain is: symptom → expected control → available configuration evidence → root-cause conclusion → repair direction.",
        "",
    ]
    if view["findings"]:
        for finding in view["findings"]:
            assumptions = finding.get("assumptions") or ["Confirm the journey rule and accountable owner before changing HubSpot."]
            lines += [
                f"### {humanize(finding['finding_id'])}",
                "",
                f"**Symptom:** {_scope_text(finding)}. **Business effect:** {_md_untrusted(finding['business_impact'])}",
                f"**Expected control:** {_md_untrusted(assumptions[0])}",
                f"**Root-cause conclusion:** {_md_untrusted(_root_cause_summary(view, finding, automation))}",
                f"**Repair direction:** {_md_untrusted(finding.get('recommended_action') or 'Review the evidence with the accountable owner.')}",
                f"Evidence: {', '.join(_evidence_links(finding))}",
                "",
            ]
    else:
        lines.append("No finding survived review. The break table above still shows deterministic populations that need monitoring or business confirmation.")
    lines += [
        f"Automation coverage state: **{automation['label']}**. "
        + (
            "Configuration causality could not be assessed because workflow access was unavailable."
            if automation["status"] in {"unavailable", "permission_denied"}
            else f"{automation['workflow_count']} workflow(s), {automation['relevant_workflow_count']} journey-relevant, and {automation['score_candidate_count']} score-like output(s) were observed."
        ),
        "",
        "## 6. Action Plan",
        "",
        "The first actions are deliberately review-only. Every item has an owner, an approval gate, and a measurable result in the operator appendix.",
        "",
        "| Priority | Action | Owner | Success measure |",
        "|---|---|---|---|",
    ]
    recommendations = _recommendation_rows(view)
    if recommendations:
        for row in recommendations:
            finding, entry = row["finding"], row["entry"]
            lines.append(
                f"| **{row['recovery_class']}** | {humanize(finding['finding_id'])}: {_md_cell(_entry_value(entry, 'expected_outcome'))} | {_md_cell(_entry_value(entry, 'owner_role'))} | {_md_cell(_entry_value(entry, 'success_measure'))} |"
            )
    else:
        lines.append("| Monitor | No validated action is ready | — | Continue measurement |")
    lines += [
        "",
        "No item in this report authorises a HubSpot write.",
        "",
        "### Actions That Should Not Be Automated",
        "",
        *[f"- {item}" for item in DO_NOT_AUTOMATE],
        "",
        "## 7. Monitor and Verify",
        "",
        "Re-run after approved ownership, association, lifecycle, source, routing, deal-creation, workflow, or scoring changes and before the next pipeline review.",
        "",
        *[f"- {item}" for item in _monitor_rows(view)],
        "",
        f"Evidence coverage: **{humanize(intent_coverage.get('status', 'not_requested'))}** intent/activity data; **{automation['label']}** automation data. Missing coverage is reported as unavailable, never as zero.",
        "",
        "Detailed measurements, reviewer trace, technical CRM profile, automation evidence, and implementation steps are in [operator_appendix.md](operator_appendix.md). Deal and pipeline claims trace to salted record hashes and sanitised pipeline/stage labels in [evidence.csv](evidence.csv).",
        "",
        "Keep the HTML file with the output folder so relative evidence links work. For distribution, use Print → Save as PDF and share the rendered report, not the raw snapshot.",
        "",
        "---",
        f"{BRAND_NAME} · {SLOGAN}",
        f"Website: {CREDIT_URL}",
        f"GitHub: {GITHUB_URL}",
    ]
    return "\n".join(lines) + "\n"


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
        measurement = view["measurement_by_id"].get(finding["finding_id"], {})
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
        "| Measurement | Journey | Dimension | Available | Affected | Denominator | Leakage point | Actual deal amount |",
        "|---|---|---|---|---:|---:|---|---:|",
    ]
    for row in view["measurements"]:
        lines.append(
            f"| `{_md_cell(row.get('id'))}` | {humanize(row.get('journey_pattern'))} | {humanize(row.get('integrity_dimension'))} | "
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
        f"- Deterministic lifecycle integrity score: {view['score']['overall_lifecycle_integrity_score']}/100.",
        "- Journey hypotheses are evidence-backed and isolated by motion; the mixed-motion role runs after the five journey roles.",
        "- A residual unclassified motion can be surfaced only as a human-confirmation observation. It cannot enter the registry, score, assignments, or leakage audit.",
        "- Raw HubSpot records are not available to judgment roles; evidence uses aggregates, sanitised labels, and salted record hashes.",
        "- Workflow and scoring configuration is read with one `automation`-scoped token, but the connector allowlist contains no workflow mutation endpoint; the runtime is structurally read-only.",
        "- Commercial amounts are aggregated only from existing deals. No amount is inferred for contacts without deals.",
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


class _RawHtml(str):
    pass


def _raw(value: str) -> _RawHtml:
    return _RawHtml(value)


def _html_table(headers: List[str], rows: List[List[Any]]) -> str:
    head = "".join(f"<th>{html_mod.escape(str(value))}</th>" for value in headers)
    body = []
    for row in rows:
        cells = []
        for value in row:
            rendered = str(value) if isinstance(value, _RawHtml) else html_mod.escape(str(value if value not in (None, "") else "—"))
            cells.append(f"<td>{rendered}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def _hbar_svg(rows: Iterable[Any], title: str) -> str:
    rows = list(rows)
    width = 760
    left = 205
    bar_width = 440
    row_height = 42
    height = 52 + len(rows) * row_height
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{html_mod.escape(title)}">',
        f"<title>{html_mod.escape(title)}</title>",
    ]
    for index, (label, value) in enumerate(rows):
        y = 30 + index * row_height
        fill_width = max(0, min(bar_width, bar_width * float(value) / 100))
        parts += [
            f'<text x="0" y="{y + 14}" class="chart-label">{html_mod.escape(str(label))}</text>',
            f'<rect x="{left}" y="{y}" width="{bar_width}" height="14" rx="7" fill="{TRACK}"/>',
            f'<rect x="{left}" y="{y}" width="{fill_width:.1f}" height="14" rx="7" fill="{PRIMARY}"/>',
            f'<text x="{left + bar_width + 12}" y="{y + 13}" class="chart-value">{html_mod.escape(str(value))}/100</text>',
        ]
    parts.append("</svg>")
    return "".join(parts)


def _html_list(items: Iterable[Any], empty: str) -> str:
    values = list(items)
    if not values:
        values = [empty]
    return "<ul>" + "".join(f"<li>{html_mod.escape(str(item))}</li>" for item in values) + "</ul>"


def _html_evidence(finding: Dict[str, Any]) -> str:
    values = []
    for ref in finding.get("evidence_refs") or []:
        text = str(ref)
        path = text.split("#", 1)[0]
        values.append(f'<a href="{html_mod.escape(path, quote=True)}">{html_mod.escape(text)}</a>')
    return ", ".join(values) or '<a href="processed/lifecycle_integrity_measurements.json">Lifecycle measurements</a>'


def _render_html_legacy(view: Dict[str, Any], markdown_text: str) -> str:
    del markdown_text
    registry = view["registry"]
    score = view["score"]
    exposure = view["pipeline_exposure"]
    overall = score["overall_lifecycle_integrity_score"]
    open_deals = exposure.get("unique_open_deals_with_leakage_signals", 0)
    potential = exposure.get("potential_recoverable_pipeline_population", 0)
    actual_amount = _amount_text(exposure.get("actual_open_deal_amount_by_currency", {}))
    score_context = _score_context(score)
    automation = _automation_summary(view)
    routing = view.get("recovery_routing", {}).get("lanes", {})
    intent = view.get("intent_summary", {})
    intent_coverage = view.get("intent_coverage", {})

    kpis = "".join(
        f'<div class="kpi"><div class="kpi-value">{html_mod.escape(str(value))}</div><div class="kpi-label">{html_mod.escape(label)}</div></div>'
        for label, value in (
            ("Journey model", humanize(registry.primary_model)),
            ("Mapping confidence", f"{score['mapping_confidence_score']}/100"),
            ("Validated findings", len(view["findings"])),
            ("Open deals to review", open_deals),
            ("Potential recoverable contacts", potential),
            ("Automation coverage", automation["label"]),
            ("Intent signals", intent.get("event_count", 0)),
        )
    )
    journey_rows = [
        (humanize(journey), view["patterns"].get(journey).confidence_score if view["patterns"].get(journey) else 0)
        for journey in JOURNEY_ORDER
    ]
    journey_table = _html_table(
        ["Journey", "Confidence", "Audit level", "Assigned deals", "High-intent contacts"],
        [
            [
                humanize(journey),
                f"{view['patterns'].get(journey).confidence_score if view['patterns'].get(journey) else 0}/100",
                _journey_status(view["patterns"].get(journey)),
                _journey_assignment(view, journey, "deals"),
                _journey_assignment(view, journey, "high_intent_contacts"),
            ]
            for journey in JOURNEY_ORDER
        ],
    )

    path_cards = []
    for path in view["journey_paths"]:
        pattern = path["pattern"]
        if pattern is None or (not pattern.exists and not pattern.confidence_score):
            continue
        milestones = path["milestones"] or ["Path milestones require confirmation"]
        flow = '<div class="journey-flow">' + '<span class="arrow">→</span>'.join(
            f'<span class="milestone">{html_mod.escape(item)}</span>' for item in milestones
        ) + "</div>"
        path_cards.append(
            f'<article class="journey-card"><div class="card-top"><span class="eyebrow">{html_mod.escape(humanize(path["journey"]))}</span><span>{pattern.confidence_score}/100 confidence</span></div>'
            f'<h3>Expected operating path</h3>{flow}<div class="grid-2 compact"><div><h4>Entry signals</h4>{_html_list(path["entry_signals"], "Entry rule requires confirmation.")}</div>'
            f'<div><h4>Handoff expectations</h4>{_html_list(path["handoffs"], "Handoff rule requires confirmation.")}</div></div>'
            f'<h4>Valid skips</h4>{_html_list(path["valid_skips"], "No journey-specific skip was confirmed.")}'
            f'<h4>Evidence basis</h4>{_html_list(path["support"], "No positive evidence beyond deterministic confidence components.")}</article>'
        )

    leakage_table = _html_table(
        ["Journey", "Leakage point", "Affected scope", "Status", "Trace"],
        [
            [
                humanize(row.get("journey_pattern")),
                row.get("leakage_point") or humanize(row.get("id")),
                _scope_text(row),
                "Validated finding" if row.get("id") in view["finding_ids"] else "Candidate for review",
                _raw(f'<a href="evidence.csv"><code>{html_mod.escape(str(row.get("id")))}</code></a>'),
            ]
            for row in view["leakage_rows"]
        ]
        or [["—", "No affected leakage candidate measured", "—", "—", _raw('<a href="processed/lifecycle_integrity_measurements.json">Measurements</a>')]],
    )

    pipeline_table = _html_table(
        ["Pipeline", "Open deals with signals", "Actual deal amount", "Trace"],
        [
            [
                _display_crm_value(row.get("pipeline_label")) or "Unknown pipeline",
                row.get("open_deals_with_leakage_signals", 0),
                _amount_text(row.get("amount_by_currency", {})),
                _raw('<a href="evidence.csv">Hashed deal evidence</a>'),
            ]
            for row in exposure.get("by_pipeline", [])
        ]
        or [["—", 0, "No deal amount available", _raw('<a href="evidence.csv">Evidence rows</a>')]],
    )
    high_intent_table = _html_table(
        ["Journey", "High-intent contacts", "Without owner", "Without associated deal", "Amount"],
        [
            [
                humanize(journey),
                row.get("total", 0),
                row.get("without_owner", 0),
                row.get("without_associated_deal", 0) if row.get("deal_association_available") else "Unavailable",
                "No amount assigned",
            ]
            for journey, row in sorted(
                view.get("high_intent", {}).get("by_journey", {}).items(),
                key=lambda item: JOURNEY_ORDER.index(item[0]) if item[0] in JOURNEY_ORDER else 99,
            )
        ]
        or [["—", 0, 0, 0, "No amount assigned"]],
    )

    finding_cards = []
    for finding in view["findings"]:
        assumptions = finding.get("assumptions") or ["Root cause is unconfirmed; validate the journey rule and accountable owner."]
        automation_rows = _automation_root_cause(view, finding)
        automation_items = []
        for row in automation_rows:
            aliases = ", ".join(row.get("workflow_aliases") or []) or "No workflow alias"
            scores = ", ".join(row.get("score_fields") or []) or "None observed"
            automation_items.append(
                f"Configuration {row.get('configuration_status', 'unknown')}; causal status {row.get('causal_status', 'unverified')}; confidence {row.get('confidence', row.get('confidence_score', 0))}/100; workflows {aliases}; score outputs {scores}."
            )
            automation_items.extend(
                f"Limitation: {item}" for item in (row.get("limitations") or [])
            )
        if not automation_items:
            automation_items = [
                "No automation/scoring root cause established for this finding."
                if automation["status"] not in {"unavailable", "permission_denied"}
                else "Workflow coverage unavailable; configuration causality was not assessed."
            ]
        finding_cards.append(
            f'<article class="finding {"critical" if finding["severity"] in {"critical", "high"} else "watch"}"><div class="card-top"><span class="chip">{html_mod.escape(finding["severity"].upper())}</span><span>{finding["confidence_score"]}/100 confidence</span></div>'
            f'<h3>{html_mod.escape(humanize(finding["finding_id"]))}</h3><p class="stable-id"><code>{html_mod.escape(finding["finding_id"])}</code> · {html_mod.escape(humanize(finding["journey_pattern"]))}</p>'
            f'<p class="finding-stat">{html_mod.escape(_scope_text(finding))}</p><p>{html_mod.escape(finding["business_impact"])}</p>'
            f'<h4>Automation/scoring root-cause signal</h4>{_html_list(automation_items, "No automation evidence.")}'
            f'<h4>Root-cause hypotheses</h4>{_html_list(assumptions, "Root cause unconfirmed.")}'
            f'<p><strong>Evidence:</strong> {_html_evidence(finding)}</p></article>'
        )
    if not finding_cards:
        finding_cards.append('<div class="panel"><p>No candidate finding survived review. Deterministic candidate populations remain visible above.</p></div>')

    recommendation_cards = []
    for row in _recommendation_rows(view):
        finding, entry = row["finding"], row["entry"]
        steps = _entry_list(entry, "implementation_steps") or ["Review evidence with the accountable owner."]
        recommendation_cards.append(
            f'<article class="recommendation"><div class="eyebrow">{html_mod.escape(row["recovery_class"])}</div><h3>{html_mod.escape(humanize(finding["finding_id"]))}</h3>'
            f'<p><strong>Target:</strong> {html_mod.escape(_entry_value(entry, "target", finding.get("object_type", "HubSpot scope")))}</p>'
            f'<p><strong>Desired state:</strong> {html_mod.escape(_entry_value(entry, "desired_state"))}</p>'
            f'<p><strong>Owner:</strong> {html_mod.escape(_entry_value(entry, "owner_role"))}</p>'
            f'<p><strong>Approval:</strong> {html_mod.escape(_entry_value(entry, "approval_required"))}</p>'
            f'<ol>{"".join(f"<li>{html_mod.escape(step)}</li>" for step in steps)}</ol>'
            f'<p><strong>Success measure:</strong> {html_mod.escape(_entry_value(entry, "success_measure"))}</p></article>'
        )
    if not recommendation_cards:
        recommendation_cards.append('<div class="panel"><p>No validated recovery action was produced.</p></div>')

    monitor_items = "".join(
        f'<li><strong>{html_mod.escape(humanize(row["id"]))}:</strong> {row.get("affected_records", 0)} affected; trace with <code>{html_mod.escape(row["id"])}</code>.</li>'
        for row in view["leakage_rows"][:8]
    ) or "<li>No affected deterministic leakage candidate is currently measurable.</li>"
    limitation_items = [
        "The audit uses HubSpot records and properties only. Synced external fields count only after they exist as HubSpot properties.",
        "Existing-deal amounts are exposed pipeline for review, not a forecast of revenue loss.",
        "Contacts without deals may be a potential recoverable population but never receive a monetary value.",
        "Deterministic leakage candidates are not automatically validated findings.",
        f"{automation['label']}; configuration evidence does not prove per-record workflow execution or full score-model correctness.",
        *automation["limitations"],
        *view["ambiguous"],
        *[f"Business confirmation needed: {item}" for item in view["confirmations"][:8]],
    ]
    if view["truncated"]:
        limitation_items.append("Snapshot truncation affected: " + ", ".join(view["truncated"]))
    safety_items = "".join(f"<li>{html_mod.escape(item)}</li>" for item in DO_NOT_AUTOMATE)
    mixed = view.get("mixed_assessment", {})
    mixed_note = ""
    if mixed.get("unclassified_motion_candidate"):
        mixed_note = (
            f'<div class="warning"><strong>Unclassified motion candidate:</strong> {html_mod.escape(str(mixed["unclassified_motion_candidate"]))}. '
            "Human confirmation only; it is not registered, scored, assigned, or audited for leakage.</div>"
        )
    score_deductions = "".join(
        f'<div class="deduction"><span><strong>{html_mod.escape(row["dimension"])}</strong> {row["score"]}/{row["max_points"]}</span>'
        f'<span>−{row["deducted"]} point{"s" if row["deducted"] != 1 else ""}</span></div>'
        for row in score_context["deductions"]
    ) or '<div class="deduction"><span>No approved or revised finding caused a deduction.</span><span>−0</span></div>'

    automation_limitations = "".join(
        f"<li>{html_mod.escape(item)}</li>" for item in automation["limitations"]
    ) or "<li>No additional automation limitation recorded.</li>"
    automation_panel = (
        f'<div class="panel automation-panel"><div class="eyebrow">Automation &amp; scoring root-cause layer</div>'
        f'<h3>{html_mod.escape(automation["label"])}</h3>'
        f'<div class="grid-2 compact"><div><p class="large-value">{automation["workflow_count"]}</p><p>workflows observed · {automation["relevant_workflow_count"]} journey-relevant</p></div>'
        f'<div><p class="large-value">{automation["score_candidate_count"]}</p><p>score-like outputs visible · {automation["configuration_signals"]} configuration signal(s)</p></div></div>'
        f'<p class="muted">This layer identifies configuration evidence behind lifecycle leaks. It does not prove per-record execution, reconstruct the full score model, or authorize workflow changes.</p>'
        f'<ul>{automation_limitations}</ul>'
        f'<p><a href="processed/automation_scoring_measurements.json">View sanitized automation measurements</a> · <a href="automation_evidence.csv">View automation evidence</a></p></div>'
    )

    cover = (
        '<header class="cover"><div class="eyebrow light">Smartify Marketing · Lifecycle Integrity Audit</div>'
        '<h1>HubSpot Lifecycle Integrity Audit</h1>'
        '<p class="lede">Understand the selling journeys represented in HubSpot, find where records fall out of those journeys, and prioritise recoverable pipeline without inventing revenue.</p>'
        f'<p class="cover-meta">Audit date: {html_mod.escape(view["generated"])} · Scope: {html_mod.escape(view["window"])}</p>'
        '<p class="cover-meta">Read-only audit — no CRM records were changed.</p></header>'
    )
    html_body = f"""
{cover}
<section id="executive"><h2>1. Executive Decision Summary</h2>
<div class="score-hero"><div class="score-mark"><div class="eyebrow light">Overall Lifecycle Integrity Score: {overall}/100</div><div><span class="hero-number">{overall}</span><span class="hero-denom">/100</span></div><div class="score-status">{html_mod.escape(score_context['band'])}</div></div>
<div class="score-context"><h3>How to read this score</h3><p>The score begins at 100 and deducts points only for approved or revised findings. <strong>{score_context['total_deducted']} point{"s were" if score_context['total_deducted'] != 1 else " was"} deducted in this run.</strong></p>{score_deductions}<p>Journey mapping confidence is separate at <strong>{score['mapping_confidence_score']}/100</strong>. Candidate leakage populations stay visible and do not reduce the score unless they survive review as approved or revised.</p><p class="score-caveat">Not a percentage of healthy records, a conversion score, or an estimate of revenue loss.</p></div></div>
<div class="kpis">{kpis}</div>
<div class="grid-2"><div class="panel"><div class="eyebrow">Existing deals</div><p class="large-value">{html_mod.escape(str(open_deals))}</p><p>open deals with deterministic leakage-candidate signals</p><p><strong>{html_mod.escape(actual_amount)}</strong> actual amount recorded on those deals</p></div>
<div class="panel"><div class="eyebrow">Pre-deal recovery</div><p class="large-value">{potential}</p><p>high-intent contacts across missing-owner or missing-deal checks</p><p class="warning-inline">No monetary amount is assigned to contacts without deals.</p></div></div>{automation_panel}</section>
<section id="journey-model"><h2>2. Detected Selling Journey Model</h2><p>The portal is classified as <strong>{html_mod.escape(humanize(registry.primary_model))}</strong>. Confidence measures evidence for the journey, not funnel performance.</p>{journey_table}<div class="panel"><h3>Selling journey confidence</h3>{_hbar_svg(journey_rows, "Selling journey confidence")}</div>{mixed_note}</section>
<section id="journey-paths"><h2>3. Journey Evidence and Operating Paths</h2><p>Each path is based on its dedicated journey hypothesis and the deterministic HubSpot evidence registry.</p><div class="journey-grid">{"".join(path_cards) or '<div class="panel"><p>No journey reached the evidence threshold.</p></div>'}</div></section>
<section id="leakage-map"><h2>4. Journey Leakage Map</h2><p>A validated finding survived reviewer gates. A candidate remains a deterministic review population and is not yet proven leakage.</p>{leakage_table}</section>
<section id="pipeline-exposure"><h2>5. Pipeline Exposure and Recoverable Population</h2><div class="grid-2"><div class="panel"><div class="eyebrow">Existing open deals</div><p class="large-value">{open_deals}</p><p>with leakage-candidate signals</p><p><strong>{html_mod.escape(actual_amount)}</strong></p><p class="muted">Actual deal amount; exposed for review, not a loss forecast.</p></div><div class="panel"><div class="eyebrow">Potential recoverable population</div><p class="large-value">{potential}</p><p>high-intent contacts</p><p class="muted">No amount assigned where no deal exists.</p></div></div>
<div class="grid-2"><div class="panel"><div class="eyebrow">Missing-deal / pre-deal recovery</div><p class="large-value">{routing.get("missing_deal_predeal_recovery", {}).get("count", potential)}</p><p>contacts with intent evidence and no deal path</p><p class="muted">No amount assigned without an existing deal.</p></div><div class="panel"><div class="eyebrow">Active-deal escalation</div><p class="large-value">{routing.get("active_deal_leakage_and_escalation", {}).get("count", 0)}</p><p>open deals needing next-step review</p><p class="muted">Actual open-deal amounts only.</p></div><div class="panel"><div class="eyebrow">Closed-lost recovery</div><p class="large-value">{routing.get("closed_lost_recovery", {}).get("count", 0)}</p><p>post-loss intent without a recovery path</p><p class="muted">Historical amount is context only; excluded from open pipeline and score.</p></div><div class="panel"><div class="eyebrow">Intent coverage</div><p class="large-value">{intent.get("event_count", 0)}</p><p>normalized record-linked signals</p><p class="muted">{html_mod.escape(humanize(intent_coverage.get("status", "not_requested")))}; aggregate campaign metrics are context only.</p></div></div>
<h3>Existing deals by pipeline</h3>{pipeline_table}<h3>High-intent contact review population</h3>{high_intent_table}<p class="muted">Every deal claim is traceable by salted record hash, pipeline, and stage in <a href="evidence.csv">evidence.csv</a>.</p></section>
<section id="findings"><h2>6. Leakage Findings and Root Causes</h2><div class="finding-grid">{"".join(finding_cards)}</div></section>
<section id="repair-plan"><h2>7. Recovery and System Repair Plan</h2><p>Immediate record recovery is separated from system repair. No item authorises a HubSpot write.</p><div class="recommendation-grid">{"".join(recommendation_cards)}</div></section>
<section id="monitoring"><h2>8. Monitoring and Next Review</h2><p>Re-run after approved ownership, association, lifecycle, source, routing, or deal-creation changes and before the next pipeline review.</p><div class="panel"><ul>{monitor_items}</ul></div></section>
<section id="evidence-limits"><h2>9. Evidence, Assumptions, and Limits</h2>{_html_list(limitation_items, "No additional limitation recorded.")}
<!-- blocked-actions:start --><h3>Actions That Should Not Be Automated</h3><ul>{safety_items}</ul><!-- blocked-actions:end -->
<div class="grid-2"><div class="panel"><h3>Supporting files</h3><ul><li><a href="evidence.csv">Evidence rows</a></li><li><a href="processed/lifecycle_integrity_measurements.json">Lifecycle measurements</a></li><li><a href="processed/high_intent_cohort_summary.json">High-intent cohort summary</a></li><li><a href="journey_pattern_registry.json">Journey registry</a></li><li><a href="processed/automation_scoring_measurements.json">Automation/scoring measurements</a></li><li><a href="automation_evidence.csv">Automation evidence</a></li><li><a href="operator_appendix.md">Operator appendix</a></li></ul></div><div class="panel"><h3>Sharing</h3><p>Keep this HTML with the output folder so relative links work. Use <strong>Print → Save as PDF</strong> for distribution. Do not share the raw snapshot.</p></div></div></section>
"""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>HubSpot Lifecycle Integrity Audit</title>
<style>
:root{{--canvas:{CANVAS};--paper:#f5efe9;--ink:{INK};--muted:{INK_2};--primary:{PRIMARY};--accent:{ACCENT};--track:{TRACK};--dark:{DARK};--dark-text:{DARK_TEXT};--error:{ERROR};--warm:{WARM}}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--canvas);color:var(--ink);font:15px/1.55 Manrope,system-ui,-apple-system,sans-serif}} main{{max-width:1180px;margin:0 auto;padding:0 28px 48px}} .cover{{background:var(--dark);color:var(--dark-text);margin:0 -28px;padding:62px 28px 50px;border-radius:0 0 22px 22px}} .cover h1{{font:700 48px/1.05 {SERIF};max-width:760px;margin:10px 0 18px}} .lede{{font-size:18px;max-width:760px;color:#eadfd5}} .cover-meta{{font-size:13px;color:#cfc2b8;margin:7px 0 0}} h2,h3,h4{{font-family:{SERIF};color:var(--ink)}} h2{{font-size:30px;line-height:1.15;border-bottom:1px solid var(--track);padding-bottom:10px;margin:48px 0 20px}} h3{{font-size:21px;margin:20px 0 12px}} h4{{font-size:16px;margin:16px 0 5px}} p{{margin:10px 0}} a{{color:var(--primary);text-decoration:underline;text-underline-offset:3px}} code{{background:var(--paper);padding:2px 5px;border-radius:5px;font-size:.88em}} .eyebrow{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--primary);font-weight:800}} .eyebrow.light{{color:var(--accent)}} .score-hero{{display:grid;grid-template-columns:minmax(260px,.8fr) minmax(0,1.7fr);overflow:hidden;background:var(--dark);color:var(--dark-text);border-radius:20px;margin:20px 0 24px;box-shadow:0 10px 28px rgba(31,27,24,.14)}} .score-mark{{padding:28px 30px;border-right:1px solid #443a33;background:linear-gradient(145deg,#1b1714,#2b211b)}} .score-mark .hero-number{{font-size:88px;color:var(--accent)}} .score-mark .hero-denom{{color:#d8cabf}} .score-status{{font:600 18px/1.3 {SERIF};margin-top:10px;max-width:290px}} .score-context{{padding:24px 28px}} .score-context h3{{color:var(--dark-text);margin:0 0 8px}} .score-context p{{color:#e9ded5}} .score-caveat{{border-left:3px solid var(--accent);padding-left:11px;font-weight:700}} .deduction{{display:flex;justify-content:space-between;gap:18px;border-top:1px solid #443a33;padding:8px 0;color:#fff}} .kpis{{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin:24px 0}} .kpi,.panel,.journey-card,.finding,.recommendation{{background:#fff;border:1px solid var(--track);border-radius:16px;padding:18px;box-shadow:0 4px 16px rgba(31,27,24,.05)}} .kpi-value,.large-value{{font:700 29px/1.1 {SERIF};color:var(--primary)}} .kpi-label{{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-top:7px}} .hero-number{{font:700 72px/1 {SERIF};color:var(--primary)}} .hero-denom{{font:24px {SERIF};color:var(--muted)}} .grid-2{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin:18px 0}} .grid-2.compact{{gap:12px;margin:10px 0}} .journey-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}} .journey-card{{border-top:4px solid var(--primary)}} .card-top{{display:flex;justify-content:space-between;gap:12px;color:var(--muted);font-size:12px}} .journey-flow{{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:14px 0 20px}} .milestone{{background:var(--paper);border:1px solid var(--track);border-radius:999px;padding:7px 10px;font-size:12px;font-weight:700}} .arrow{{color:var(--primary);font-weight:900}} .table-wrap{{overflow-x:auto;margin:14px 0 24px}} table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px}} th{{background:var(--paper);font-weight:800;text-align:left}} th,td{{padding:10px 11px;border:1px solid var(--track);vertical-align:top}} .chart{{display:block;width:100%;height:auto;max-width:760px}} .chart-label{{font:12px Manrope,system-ui,sans-serif;fill:var(--ink)}} .chart-value{{font:700 12px Manrope,system-ui,sans-serif;fill:var(--primary)}} .finding-grid,.recommendation-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}} .finding{{border-top:4px solid var(--warm)}} .finding.critical{{border-top-color:var(--error)}} .recommendation{{border-top:4px solid var(--primary)}} .chip{{font-size:11px;letter-spacing:.1em;font-weight:800;color:var(--error)}} .stable-id,.muted{{color:var(--muted)}} .finding-stat{{font:700 21px {SERIF};color:var(--primary)}} .warning{{border-left:4px solid var(--error);background:#fff4f2;padding:12px 14px;margin:16px 0}} .warning-inline{{color:var(--error);font-weight:700}} ul,ol{{padding-left:23px}} li{{margin:5px 0}} footer{{border-top:1px solid var(--track);margin-top:55px;padding-top:20px;color:var(--muted);font-size:13px}} footer a{{margin-right:14px}} @media(max-width:820px){{main{{padding:0 17px 35px}}.cover{{margin:0 -17px;padding:42px 17px}}.cover h1{{font-size:38px}}.score-hero{{grid-template-columns:1fr}}.score-mark{{border-right:0;border-bottom:1px solid #443a33}}.kpis{{grid-template-columns:repeat(2,minmax(0,1fr))}}.grid-2,.journey-grid,.finding-grid,.recommendation-grid{{grid-template-columns:1fr}}}} @media print{{body{{background:#fff;font-size:11px}}main{{max-width:none;padding:0}}.cover{{border-radius:0;padding:35px 0}}h2{{break-before:page;margin-top:25px}}.cover+h2{{break-before:auto}}.score-hero{{box-shadow:none;break-inside:avoid}}.kpi,.panel,.journey-card,.finding,.recommendation{{box-shadow:none;break-inside:avoid}}a{{color:inherit;text-decoration:none}}}}
</style></head><body><main>{html_body}<footer><strong>{BRAND_NAME}</strong> · {SLOGAN}<br><a href="{CREDIT_URL}">{CREDIT_URL}</a><a href="{GITHUB_URL}">GitHub</a></footer></main></body></html>"""


def render_html(view: Dict[str, Any], markdown_text: str) -> str:
    """Render the decision report as a responsive, self-contained HTML page."""
    del markdown_text
    registry = view["registry"]
    score = view["score"]
    exposure = view["pipeline_exposure"]
    overall = score["overall_lifecycle_integrity_score"]
    automation = _automation_summary(view)
    intent = view.get("intent_summary", {})
    intent_coverage = view.get("intent_coverage", {})
    routing = view.get("recovery_routing", {}).get("lanes", {})
    score_context = _score_context(score)
    detected = _detected_paths(view)

    decisions = _decision_rows(view)[:3]
    decision_cards = "".join(
        f'<article class="decision-card"><div class="eyebrow">{html_mod.escape(row["priority"])}</div>'
        f'<h3>{html_mod.escape(row["headline"])}</h3><p>{html_mod.escape(row["detail"])}</p></article>'
        for row in decisions
    )
    score_deductions = "".join(
        f'<div class="deduction"><span><strong>{html_mod.escape(row["dimension"])}</strong> {row["score"]}/{row["max_points"]}</span>'
        f'<span>−{row["deducted"]}</span></div>'
        for row in score_context["deductions"]
    ) or '<div class="deduction"><span>No approved or revised finding caused a deduction.</span><span>−0</span></div>'

    journey_rows = [
        (humanize(path["journey"]), path["pattern"].confidence_score)
        for path in detected
    ] or [("Insufficient evidence", 0)]
    journey_table = _html_table(
        ["Motion", "Evidence confidence", "Records represented"],
        [
            [
                humanize(path["journey"]),
                f'{path["pattern"].confidence_score}/100',
                f'{_journey_assignment(view, path["journey"], "deals")} deal(s) · {_journey_assignment(view, path["journey"], "high_intent_contacts")} high-intent contact(s)',
            ]
            for path in detected
        ] or [["Insufficient evidence", "—", "No journey reached the evidence threshold."]],
    )
    journey_paths_html = []
    for path in detected:
        milestones = path["milestones"] or ["Path milestones require confirmation"]
        flow = '<div class="journey-flow">' + '<span class="arrow">→</span>'.join(
            f'<span class="milestone">{html_mod.escape(item)}</span>' for item in milestones
        ) + "</div>"
        journey_paths_html.append(
            f'<article class="journey-card"><div class="card-top"><span class="eyebrow">{html_mod.escape(humanize(path["journey"]))}</span><span>{path["pattern"].confidence_score}/100</span></div>{flow}'
            f'<p><strong>Entry:</strong> {html_mod.escape("; ".join(path["entry_signals"][:2]) or "Requires confirmation.")}</p>'
            f'<p><strong>Handoff:</strong> {html_mod.escape("; ".join(path["handoffs"][:2]) or "Requires confirmation.")}</p></article>'
        )

    breakpoint_rows = [_breakpoint_detail(row, view) for row in view["leakage_rows"]]
    breakpoint_table = _html_table(
        ["Journey connection", "Expected control", "Observed", "Business consequence", "Status", "Trace"],
        [
            [
                row["connection"],
                row["expected"],
                row["observed"],
                row["consequence"],
                _raw(f'<span class="status {"validated" if row["status"] == "Validated break" else "candidate"}">{html_mod.escape(row["status"])}</span>'),
                _raw(f'<a href="evidence.csv"><code>{html_mod.escape(row["trace"])}</code></a>'),
            ]
            for row in breakpoint_rows
        ] or [["—", "No affected break measured", "—", "Continue monitoring", "No current break", _raw('<a href="processed/lifecycle_integrity_measurements.json">Measurements</a>')]],
    )

    lane_rows = [
        ["Protect open pipeline", exposure.get("unique_open_deals_with_leakage_signals", 0), _amount_text(exposure.get("actual_open_deal_amount_by_currency", {})), "Actual deal amount to review; not a loss forecast."],
        ["Active-deal escalation", routing.get("active_deal_leakage_and_escalation", {}).get("count", 0), _amount_text(routing.get("active_deal_leakage_and_escalation", {}).get("amount_by_currency", {})), "Actual open-deal amount only."],
        ["Capture missed demand", routing.get("missing_deal_predeal_recovery", {}).get("count", exposure.get("potential_recoverable_pipeline_population", 0)), "No amount assigned", "Potential recoverable pipeline, not booked pipeline."],
        ["Recover renewed demand", routing.get("closed_lost_recovery", {}).get("count", 0), _amount_text(routing.get("closed_lost_recovery", {}).get("historical_closed_lost_amount_by_currency", {})), "Historical context only; excluded from open pipeline and score."],
    ]
    lane_table = _html_table(["Lane", "Population", "Amount shown", "Reading"], lane_rows)

    finding_cards = []
    for finding in view["findings"]:
        assumptions = finding.get("assumptions") or ["Confirm the journey rule and accountable owner before changing HubSpot."]
        root_cause = _root_cause_summary(view, finding, automation)
        finding_cards.append(
            f'<article class="finding"><div class="card-top"><span class="chip">{html_mod.escape(str(finding["severity"]).upper())}</span><span>{finding["confidence_score"]}/100 confidence</span></div>'
            f'<h3>{html_mod.escape(humanize(finding["finding_id"]))}</h3><p class="finding-stat">{html_mod.escape(_scope_text(finding))}</p>'
            f'<p><strong>Business effect:</strong> {html_mod.escape(finding["business_impact"])}</p>'
            f'<div class="chain"><p><strong>Expected control</strong><br>{html_mod.escape(assumptions[0])}</p><p><strong>Root-cause conclusion</strong><br>{html_mod.escape(root_cause)}</p><p><strong>Repair direction</strong><br>{html_mod.escape(finding.get("recommended_action") or "Review the evidence with the accountable owner.")}</p></div>'
            f'<p><strong>Evidence:</strong> {_html_evidence(finding)}</p></article>'
        )
    if not finding_cards:
        finding_cards.append('<div class="panel"><p>No finding survived review. Deterministic populations remain visible above.</p></div>')

    recommendations = _recommendation_rows(view)
    action_rows = [
        [
            row["recovery_class"],
            humanize(row["finding"]["finding_id"]),
            _entry_value(row["entry"], "owner_role"),
            _entry_value(row["entry"], "success_measure"),
        ]
        for row in recommendations
    ] or [["Monitor", "No validated action is ready", "—", "Continue measurement"]]
    action_table = _html_table(["Priority", "Action", "Owner", "Success measure"], action_rows)
    pipeline_table = _html_table(
        ["Pipeline", "Open deals with leakage signals", "Actual deal amount", "Trace"],
        [
            [
                _display_crm_value(row.get("pipeline_label")) or "Unknown pipeline",
                row.get("open_deals_with_leakage_signals", 0),
                _amount_text(row.get("amount_by_currency", {})),
                _raw('<a href="evidence.csv">evidence.csv</a>'),
            ]
            for row in exposure.get("by_pipeline", [])
        ] or [["—", 0, "No deal amount available", _raw('<a href="evidence.csv">evidence.csv</a>')]],
    )
    monitor_items = _html_list(_monitor_rows(view), "No affected deterministic leakage candidate is currently measurable.")
    safety_items = "".join(f"<li>{html_mod.escape(item)}</li>" for item in DO_NOT_AUTOMATE)
    mixed = view.get("mixed_assessment", {})
    mixed_note = ""
    if mixed.get("unclassified_motion_candidate"):
        mixed_note = f'<div class="notice"><strong>Human confirmation needed:</strong> {html_mod.escape(str(mixed["unclassified_motion_candidate"]))}.</div>'

    automation_text = (
        "Workflow coverage was unavailable, so configuration causality was not assessed."
        if automation["status"] in {"unavailable", "permission_denied"}
        else f'{automation["workflow_count"]} workflow(s), {automation["relevant_workflow_count"]} journey-relevant, and {automation["score_candidate_count"]} score-like output(s) were observed.'
    )
    cover = (
        '<header class="cover"><div class="eyebrow light">Smartify Marketing · Lifecycle Integrity Audit</div>'
        '<h1>HubSpot Lifecycle Integrity Audit</h1>'
        '<p class="lede">Understand the selling journey represented in HubSpot, see where buyer intent fails to become owned pipeline, and decide what to recover or repair next.</p>'
        f'<p class="cover-meta">Audit date: {html_mod.escape(view["generated"])} · Scope: {html_mod.escape(view["window"])} · Read-only audit</p></header>'
    )
    html_body = f"""
{cover}
<section id="executive"><h2>1. Executive Verdict</h2>
<div class="verdict"><div class="score-block"><div class="eyebrow light">Overall Lifecycle Integrity Score: {overall}/100</div><div><span class="hero-number">{overall}</span><span class="hero-denom">/100</span></div><div class="score-status">{html_mod.escape(score_context['band'])}</div></div><div class="score-context"><h3>What this score means</h3><p>The score starts at 100. <strong>{score_context['total_deducted']} point{'s were' if score_context['total_deducted'] != 1 else ' was'} deducted</strong> for approved or revised findings in this run.</p>{score_deductions}<p>Mapping confidence is separate at <strong>{score['mapping_confidence_score']}/100</strong>. Candidate leakage stays visible but does not lower the score before review.</p><p class="score-caveat">Not a percentage of healthy records, a conversion score, or a revenue-loss estimate.</p></div></div>
<p class="verdict-copy">{html_mod.escape(_business_verdict(view))}</p><div class="decision-grid">{decision_cards}</div><p class="coverage-strip"><strong>Automation &amp; scoring:</strong> {html_mod.escape(automation["label"])} · {html_mod.escape(automation_text)}</p></section>
<section id="journey"><h2>2. How This HubSpot Selling Journey Works</h2><p>The portal is classified as <strong>{html_mod.escape(humanize(registry.primary_model))}</strong>. Evidence confidence describes the model identification, not funnel performance.</p><h3>Expected operating path</h3><div class="journey-rail"><span>Demand captured</span><b>→</b><span>Intent recognised</span><b>→</b><span>Owner assigned</span><b>→</b><span>Deal created or valid skip</span><b>→</b><span>Deal progressed</span><b>→</b><span>Won, lost, or re-engaged</span></div>{journey_table}<div class="chart-panel"><h3>Evidence confidence by motion</h3>{_hbar_svg(journey_rows, 'Evidence confidence by selling motion')}</div><div class="journey-grid">{"".join(journey_paths_html) or '<div class="panel"><p>No journey reached the evidence threshold.</p></div>'}</div>{mixed_note}</section>
<section id="breaks"><h2>3. Where the Journey Breaks</h2><p>The structural leakage engine and record-linked intent signals are shown together so the reader can see the broken connection, its consequence, and its trace.</p>{breakpoint_table}<div class="legend"><span class="status validated">Validated break</span><span class="status candidate">Review candidate</span><span class="status unavailable">Not assessable</span><span class="status opportunity">Recovery opportunity</span></div></section>
<section id="pipeline"><h2>4. Pipeline to Protect and Demand to Recover</h2><p>Commercial lanes are intentionally separate. Contacts without deals never receive a monetary value.</p>{lane_table}<h3>Existing deal exposure by pipeline</h3>{pipeline_table}<div class="signal-summary"><div><strong>{intent.get('event_count', 0)}</strong><span>record-linked intent signals</span></div><div><strong>{html_mod.escape(humanize(intent_coverage.get('status', 'not_requested')))}</strong><span>intent coverage</span></div><div><strong>{html_mod.escape(', '.join(sorted(intent.get('counts_by_source', {}).keys())) or 'None')}</strong><span>sources observed</span></div></div></section>
<section id="causes"><h2>5. Why the Breaks Are Happening</h2><p>Each finding follows the same diagnostic chain: symptom → expected control → configuration evidence → conclusion → repair direction.</p><div class="finding-grid">{"".join(finding_cards)}</div><div class="panel automation-note"><h3>Automation &amp; scoring root-cause layer</h3><p>{html_mod.escape(automation_text)}</p><p class="muted">This layer is diagnostic only. It does not prove per-record execution, reconstruct the full score model, or authorize workflow changes.</p></div></section>
<section id="actions"><h2>6. Action Plan</h2><p>These actions are review-only until a separate plan is approved.</p>{action_table}<p class="notice">No item authorises a HubSpot write. The operator appendix contains target, current state, desired state, owner, approval gate, steps, and success measure.</p><!-- blocked-actions:start --><h3>Actions that should not be automated</h3><ul>{safety_items}</ul><!-- blocked-actions:end --></section>
<section id="monitor"><h2>7. Monitor and Verify</h2><p>Re-run after approved ownership, association, lifecycle, source, routing, deal-creation, workflow, or scoring changes and before the next pipeline review.</p><div class="panel">{monitor_items}</div><p class="coverage-strip"><strong>Coverage:</strong> {html_mod.escape(humanize(intent_coverage.get('status', 'not_requested')))} intent/activity data · {html_mod.escape(automation["label"])} automation data. Missing coverage is unavailable, never zero.</p><div class="support-grid"><div class="panel"><h3>Evidence and detail</h3><ul><li><a href="evidence.csv">Evidence rows</a></li><li><a href="processed/lifecycle_integrity_measurements.json">Lifecycle measurements</a></li><li><a href="processed/intent_signal_store.jsonl">Intent signal store</a></li><li><a href="processed/automation_scoring_measurements.json">Automation measurements</a></li><li><a href="automation_evidence.csv">Automation evidence</a></li><li><a href="operator_appendix.md">Operator appendix</a></li></ul></div><div class="panel"><h3>Sharing</h3><p>Keep this HTML with the output folder so relative evidence links work. Use <strong>Print → Save as PDF</strong> for distribution. Do not share the raw snapshot.</p></div></div></section>
"""
    css = f"""
:root{{--canvas:{CANVAS};--paper:#f5efe9;--ink:{INK};--muted:{INK_2};--primary:{PRIMARY};--accent:{ACCENT};--track:{TRACK};--dark:{DARK};--dark-text:{DARK_TEXT};--error:{ERROR};--warm:{WARM}}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--canvas);color:var(--ink);font:15px/1.55 Manrope,system-ui,-apple-system,sans-serif}} main{{max-width:1240px;margin:0 auto;padding:0 28px 52px}} section{{min-width:0}} .cover{{background:var(--dark);color:var(--dark-text);margin:0 -28px;padding:58px 28px 46px;border-radius:0 0 22px 22px}} .cover h1{{font:700 48px/1.05 {SERIF};max-width:780px;margin:10px 0 18px}} .lede{{font-size:18px;max-width:780px;color:#eadfd5}} .cover-meta{{font-size:13px;color:#cfc2b8;margin:8px 0 0}} h2,h3,h4{{font-family:{SERIF};color:var(--ink)}} h2{{font-size:31px;line-height:1.15;border-bottom:1px solid var(--track);padding-bottom:11px;margin:48px 0 20px}} h3{{font-size:21px;margin:18px 0 11px}} p{{margin:10px 0;overflow-wrap:anywhere}} a{{color:var(--primary);text-decoration:underline;text-underline-offset:3px}} code{{background:var(--paper);padding:2px 5px;border-radius:5px;font-size:.88em;overflow-wrap:anywhere}} .eyebrow{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--primary);font-weight:800}} .eyebrow.light{{color:var(--accent)}} .verdict{{display:grid;grid-template-columns:minmax(270px,.8fr) minmax(0,1.7fr);overflow:hidden;background:var(--dark);color:var(--dark-text);border-radius:20px;margin:20px 0 18px;box-shadow:0 10px 28px rgba(31,27,24,.14)}} .score-block{{padding:29px 31px;border-right:1px solid #443a33;background:linear-gradient(145deg,#1b1714,#2b211b)}} .hero-number{{font:700 88px/1 {SERIF};color:var(--accent)}} .hero-denom{{font:24px {SERIF};color:#d8cabf}} .score-status{{font:600 18px/1.3 {SERIF};margin-top:10px;max-width:300px}} .score-context{{padding:25px 29px}} .score-context h3{{color:var(--dark-text);margin:0 0 8px}} .score-context p{{color:#e9ded5}} .score-caveat{{border-left:3px solid var(--accent);padding-left:11px;font-weight:700}} .deduction{{display:flex;justify-content:space-between;gap:18px;border-top:1px solid #443a33;padding:8px 0;color:#fff;overflow-wrap:anywhere}} .verdict-copy{{font:600 22px/1.35 {SERIF};max-width:950px;margin:22px 0}} .decision-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}} .decision-card,.panel,.journey-card,.finding{{background:#fff;border:1px solid var(--track);border-radius:16px;padding:19px;box-shadow:0 4px 16px rgba(31,27,24,.05);min-width:0}} .decision-card{{border-top:4px solid var(--primary)}} .decision-card h3{{font-family:system-ui,-apple-system,sans-serif;font-size:18px;line-height:1.25;margin:10px 0}} .coverage-strip,.notice,.legend{{background:var(--paper);border-radius:10px;padding:11px 14px;margin:18px 0;overflow-wrap:anywhere}} .notice{{border-left:4px solid var(--primary)}} .journey-rail{{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;background:#fff;border:1px solid var(--track);border-radius:16px;padding:19px;margin:18px 0}} .journey-rail span{{background:var(--paper);border:1px solid var(--track);border-radius:999px;padding:8px 11px;font-size:12px;font-weight:750}} .journey-rail b{{color:var(--primary);font-size:20px}} .table-wrap{{overflow-x:auto;margin:16px 0 22px}} table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px;min-width:760px}} th{{background:var(--paper);font-weight:800;text-align:left}} th,td{{padding:11px;border:1px solid var(--track);vertical-align:top;overflow-wrap:anywhere}} .chart-panel{{background:#fff;border:1px solid var(--track);border-radius:16px;padding:18px;margin:18px 0}} .chart{{display:block;width:100%;height:auto;max-width:760px}} .chart-label{{font:12px Manrope,system-ui,sans-serif;fill:var(--ink)}} .chart-value{{font:700 12px Manrope,system-ui,sans-serif;fill:var(--primary)}} .journey-grid,.finding-grid,.support-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:18px 0}} .journey-card{{border-top:4px solid var(--primary)}} .card-top{{display:flex;justify-content:space-between;gap:12px;color:var(--muted);font-size:12px;overflow-wrap:anywhere}} .journey-flow{{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:15px 0}} .milestone{{background:var(--paper);border:1px solid var(--track);border-radius:999px;padding:7px 10px;font-size:12px;font-weight:700;overflow-wrap:anywhere}} .arrow{{color:var(--primary);font-weight:900}} .status{{display:inline-block;border-radius:999px;padding:4px 8px;font-size:11px;font-weight:800;white-space:nowrap}} .validated{{color:#7d0a13;background:#ffe1e3}} .candidate{{color:#815000;background:#fff0c7}} .opportunity{{color:#0b5e72;background:#dff5fb}} .unavailable{{color:#5d544d;background:#eee8e2}} .legend{{display:flex;gap:8px;flex-wrap:wrap;align-items:center}} .finding{{border-top:4px solid var(--warm)}} .finding-stat{{font:700 22px {SERIF};color:var(--primary)}} .chip{{font-size:11px;letter-spacing:.1em;font-weight:800;color:var(--error)}} .stable-id,.muted{{color:var(--muted)}} .chain{{border-left:3px solid var(--track);padding-left:13px;margin:15px 0}} .chain p{{margin:12px 0}} .signal-summary{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:18px 0}} .signal-summary div{{background:#fff;border:1px solid var(--track);border-radius:14px;padding:17px;min-width:0}} .signal-summary strong{{display:block;font:700 26px/1.15 {SERIF};color:var(--primary);overflow-wrap:anywhere}} .signal-summary span{{display:block;color:var(--muted);margin-top:5px}} ul,ol{{padding-left:23px}} li{{margin:5px 0;overflow-wrap:anywhere}} footer{{border-top:1px solid var(--track);margin-top:55px;padding-top:20px;color:var(--muted);font-size:13px}} footer a{{margin-right:14px}} @media(max-width:900px){{.decision-grid,.signal-summary{{grid-template-columns:1fr}}.journey-rail{{justify-content:flex-start}}}} @media(max-width:760px){{main{{padding:0 17px 35px}}.cover{{margin:0 -17px;padding:42px 17px}}.cover h1{{font-size:38px}}.verdict{{grid-template-columns:1fr}}.score-block{{border-right:0;border-bottom:1px solid #443a33}}.journey-grid,.finding-grid,.support-grid{{grid-template-columns:1fr}}.journey-rail b{{display:none}}}} @media print{{body{{background:#fff;font-size:11px}}main{{max-width:none;padding:0}}.cover{{border-radius:0;padding:35px 0}}h2{{break-before:page;margin-top:25px}}.cover+h2{{break-before:auto}}.verdict,.decision-card,.panel,.journey-card,.finding{{box-shadow:none;break-inside:avoid}}.table-wrap{{overflow:visible}}table{{min-width:0;font-size:9px}}a{{color:inherit;text-decoration:none}}}}
"""
    return f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>HubSpot Lifecycle Integrity Audit</title><style>{css}</style></head><body><main>{html_body}<footer><strong>{BRAND_NAME}</strong> · {SLOGAN}<br><a href="{CREDIT_URL}">{CREDIT_URL}</a><a href="{GITHUB_URL}">GitHub</a></footer></main></body></html>'


# The executive renderer is kept in a separate module so the report's
# business narrative can evolve without changing the older operator helpers
# above. These aliases are the only public renderer entry points imported by
# lifecycle_reports.py.
_BASE_BUILD_VIEW = build_view
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
    view = _BASE_BUILD_VIEW(run_dir, score, registry, adjudicated, plan_by_lane)
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
