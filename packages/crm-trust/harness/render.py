"""Render decision-maker and operator reports from validated artifacts.

The narrative role supplies bounded interpretation only. Counts, percentages,
finding samples, evidence links, score, and recommendation metadata are
rendered from validated artifacts so every published number remains traceable.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from core.report_record_evidence import build_report_record_evidence, report_identity
from core.schemas import Finding, RecommendationItem, Recommendations, ReportNarrative


UNTRUSTED_PREFIX = "[CRM_FIELD_VALUE:UNTRUSTED_DATA_ONLY] "
MODULES = (
    "attribution_trust",
    "lifecycle_funnel",
    "association_architecture",
    "pipeline_hygiene",
    "property_governance",
)
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
DECISION_IMPACTS = {
    "attribution_trust": ["Attribution reporting", "Budget allocation"],
    "lifecycle_funnel": [
        "Marketing Qualified Lead (MQL) quality",
        "Sales handoff",
        "Funnel conversion",
    ],
    "association_architecture": ["Account coverage", "Sales handoff", "Account attribution"],
    "pipeline_hygiene": ["Forecast confidence", "Pipeline reporting"],
    "property_governance": ["Reporting consistency", "Data governance"],
}
CATEGORY_LABELS = {
    "safe_operational_actions": "Human review and disposition",
    "needs_business_rule_confirmation": "Business rule confirmation",
    "do_not_auto_fix": "Explicit approval before a CRM change",
}
SCORE_CATEGORY_LABELS = {
    "attribution_trust": "Attribution Trust",
    "lifecycle_funnel": "Lifecycle + Funnel Trust",
    "association_architecture": "Association + Account Trust",
    "pipeline_hygiene": "Pipeline Hygiene",
    "property_governance": "Property Governance",
}
DISPLAY_TERMS = {
    "abm": "ABM",
    "crm": "CRM",
    "mql": "MQL",
    "sql": "SQL",
    "closedwon": "Closed Won",
    "closedlost": "Closed Lost",
}
LIFECYCLE_LABELS = {
    "lead": "Lead",
    "marketingqualifiedlead": "Marketing Qualified Lead (MQL)",
    "salesqualifiedlead": "Sales Qualified Lead (SQL)",
    "opportunity": "Opportunity",
    "customer": "Customer",
    "closedlost": "Closed Lost",
}


def _load(run_dir: Path, relative: str, default: Any = None) -> Any:
    path = Path(run_dir) / relative
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _plain(value: Any) -> str:
    if value is None:
        return "—"
    text = str(value).replace(UNTRUSTED_PREFIX, "")
    return re.sub(r"\s+", " ", text).strip() or "—"


def _narrative_plain(value: Any) -> str:
    """Normalize whitespace while preserving the author's exact wording."""
    return _plain(value)


def _md(value: Any) -> str:
    return _plain(value).replace("|", "\\|")


def _narrative_md(value: Any) -> str:
    return _narrative_plain(value).replace("|", "\\|")


def _asset_md(asset_type: str, label: Any) -> str:
    return f"**HubSpot {asset_type}: {_md(label)}**"


def _record_asset_md(asset_type: str, label: Any, url: Any) -> str:
    value = f"**{_md(label)}**"
    value = f"[{value}]({url})" if url else value
    return f"{asset_type}: {value}"


def _record_term_md(asset_type: str, label: Any) -> str:
    return f"{asset_type}: **{_md(label)}**"


def _property_asset_md(
    object_type: str,
    field: str,
    property_labels: Dict[Tuple[str, str], str],
) -> str:
    label = property_labels.get((object_type, field), field)
    display = f"{label} ({field})" if label != field else field
    return _asset_md("property", display)


def _pct(value: Any) -> str:
    return "—" if value is None else f"{value}%"


def _link(relative: str, label: str = "open") -> str:
    return f"[{label}]({relative.replace(' ', '%20')})"


def _list(items: Iterable[str], empty: str = "None recorded.") -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    return "\n".join(f"- {item}" for item in values) if values else empty


def _findings(run_dir: Path) -> List[Finding]:
    raw = _load(run_dir, "findings.json", {}).get("findings", [])
    return [Finding.model_validate(item) for item in raw]


def _recommendations(run_dir: Path) -> Recommendations:
    return Recommendations.model_validate(_load(run_dir, "recommendations.json", {}))


def _finding_title(finding: Finding) -> str:
    if finding.title:
        return _plain(finding.title)
    return _identifier_title(finding.id)


def _identifier_title(identifier: str) -> str:
    words = identifier.replace("_", " ").split()
    return " ".join(DISPLAY_TERMS.get(word.lower(), word.title()) for word in words)


def _finding_impacts(finding: Finding) -> List[str]:
    return [_plain(value) for value in finding.decision_impacts] or DECISION_IMPACTS.get(
        finding.module, ["Management reporting"]
    )


def _sample(finding: Finding) -> str:
    if finding.affected_records is None:
        return "Qualitative evidence"
    text = f"{finding.affected_records} of {finding.denominator} records"
    if finding.affected_percentage is not None:
        text += f" ({finding.affected_percentage}%)"
    return text


def _accepted_findings(findings: List[Finding]) -> List[Finding]:
    accepted = [f for f in findings if f.review_status in {"approved", "revised"}]
    return sorted(
        accepted,
        key=lambda f: (
            SEVERITY_RANK.get(f.severity, 9),
            -(f.affected_percentage or 0),
            f.id,
        ),
    )


def _finding_priority(finding: Finding | None) -> int:
    if finding is None:
        return 3
    if finding.severity in {"critical", "high"}:
        return 1
    if finding.severity == "medium":
        return 2
    return 3


def _recommendation_groups(recommendations: Recommendations) -> List[Tuple[str, List[RecommendationItem]]]:
    return [
        ("safe_operational_actions", recommendations.safe_operational_actions),
        ("needs_business_rule_confirmation", recommendations.needs_business_rule_confirmation),
        ("do_not_auto_fix", recommendations.do_not_auto_fix),
    ]


def _all_recommendations(
    recommendations: Recommendations,
    findings: List[Finding],
) -> List[Tuple[str, RecommendationItem]]:
    items = [
        (category, item)
        for category, items in _recommendation_groups(recommendations)
        for item in items
    ]
    findings_by_id = {finding.id: finding for finding in findings}

    def sort_key(entry: Tuple[str, RecommendationItem]) -> Tuple[int, float, str]:
        finding = findings_by_id.get(entry[1].finding_id)
        return (
            _finding_priority(finding),
            -(finding.affected_percentage or 0) if finding else 0,
            entry[1].finding_id,
        )

    return sorted(
        items,
        key=sort_key,
    )


def _snapshot_table(manifest: Dict[str, Any], counts: Dict[str, Any]) -> List[str]:
    full_history = bool(manifest.get("full_history", manifest.get("days") is None))
    truncated = manifest.get("truncated", counts.get("truncated", {})) or {}
    rows = [
        ("Contacts", "contacts"),
        ("Companies", "companies"),
        ("Deals", "deals"),
        ("Pipelines", "deal_pipelines"),
    ]
    lines = ["| CRM object | Records | Coverage | Complete extract |", "|---|---:|---|---|"]
    for label, key in rows:
        lines.append(
            f"| {label} | {_md(counts.get(key, 0))} | "
            f"{'Full history' if full_history else 'Selected time window'} | "
            f"{'No' if truncated.get(key, False) else 'Yes'} |"
        )
    return lines


def _completeness_rows(summary: Dict[str, Any], limit: int = 30) -> List[Tuple[str, str, float, int, int]]:
    rows: List[Tuple[str, str, float, int, int]] = []
    for object_type, fields in (summary.get("field_completeness", {}) or {}).items():
        if object_type not in {"contacts", "companies", "deals"}:
            continue
        for field, stats in (fields or {}).items():
            rows.append(
                (
                    object_type,
                    field,
                    float(stats.get("fill_rate", 0.0)),
                    int(stats.get("total", 0)),
                    int(stats.get("non_empty", 0)),
                )
            )
    rows.sort(key=lambda row: (row[0], row[2], row[1]))
    return rows[:limit]


def _completeness_table(
    summary: Dict[str, Any],
    property_labels: Dict[Tuple[str, str], str],
) -> List[str]:
    lines = ["| Object | Field | Present | Total | Complete |", "|---|---|---:|---:|---:|"]
    rows = _completeness_rows(summary)
    for object_type, field, fill, total, present in rows:
        lines.append(
            f"| {object_type.title()} | {_property_asset_md(object_type, field, property_labels)} | "
            f"{present} | {total} | {_pct(round(fill, 1))} |"
        )
    if not rows:
        lines.append("| — | Field completeness was not available | — | — | — |")
    return lines


def _identity_table(
    identity: Dict[str, Any],
    property_labels: Dict[Tuple[str, str], str],
) -> List[str]:
    fields = identity.get("fields", {}) if isinstance(identity, dict) else {}
    lines = ["| Contact field | Complete | Valid format when present |", "|---|---:|---:|"]
    for field, stats in fields.items():
        lines.append(
            f"| {_property_asset_md('contacts', field, property_labels)} | {_pct(stats.get('fill_rate'))} | "
            f"{_pct(stats.get('valid_format_rate_among_present'))} |"
        )
    if not fields:
        lines.append("| — | — | — |")
    return lines


def _association_table(associations: Dict[str, Any]) -> List[str]:
    lines = ["| Relationship | Associated records | Total | Coverage |", "|---|---:|---:|---:|"]
    for name, stats in associations.items():
        if not isinstance(stats, dict):
            continue
        lines.append(
            f"| {_md(name.replace('_', ' ').title())} | {_md(stats.get('with_association'))} | "
            f"{_md(stats.get('total'))} | {_pct(stats.get('coverage_pct'))} |"
        )
    if len(lines) == 2:
        lines.append("| — | — | — | — |")
    return lines


def _activity_table(activity: Dict[str, Any]) -> List[str]:
    lines = ["| Object | Updated ≤30 days | 31–90 days | 91–180 days | Over 180 days |", "|---|---:|---:|---:|---:|"]
    for object_type, stats in (activity.get("objects", {}) or {}).items():
        buckets = stats.get("recency_buckets", {})
        lines.append(
            f"| {object_type.title()} | {_md(buckets.get('within_30_days', 0))} | "
            f"{_md(buckets.get('31_to_90_days', 0))} | {_md(buckets.get('91_to_180_days', 0))} | "
            f"{_md(buckets.get('over_180_days', 0))} |"
        )
    if len(lines) == 2:
        lines.append("| — | — | — | — | — |")
    return lines


def _lifecycle_table(lifecycle: Dict[str, Any]) -> List[str]:
    lines = ["| Object | Lifecycle stage | Records |", "|---|---|---:|"]
    for object_type, distribution in lifecycle.items():
        if not isinstance(distribution, dict):
            continue
        for stage, count in sorted(distribution.items(), key=lambda item: -int(item[1])):
            label = LIFECYCLE_LABELS.get(_plain(stage).lower(), _plain(stage))
            lines.append(
                f"| {object_type.title()} | {_asset_md('lifecycle stage', label)} | {_md(count)} |"
            )
    if len(lines) == 2:
        lines.append("| — | Lifecycle distribution was not available | — |")
    return lines


def _pipeline_table(pipelines: Dict[str, Any]) -> List[str]:
    lines = ["| Pipeline | Stages | Deals |", "|---|---:|---:|"]
    for pipeline in pipelines.get("pipelines", []) or []:
        lines.append(
            f"| {_asset_md('pipeline', pipeline.get('label') or pipeline.get('pipeline_id'))} | "
            f"{_md(pipeline.get('stage_count'))} | {_md(pipeline.get('deal_count'))} |"
        )
    unknown = pipelines.get("deals_in_unknown_pipeline")
    if unknown:
        lines.append(f"| Unknown pipeline | — | {_md(unknown)} |")
    if len(lines) == 2:
        lines.append("| — | — | — |")
    return lines


def _score_table(score: Dict[str, Any]) -> List[str]:
    lines = [
        "| Trust category | Starting points | Deducted | Remaining |",
        "|---|---:|---:|---:|",
    ]
    for category, stats in (score.get("categories", {}) or {}).items():
        if not isinstance(stats, dict):
            continue
        lines.append(
            f"| {SCORE_CATEGORY_LABELS.get(category, _identifier_title(category))} | "
            f"{_md(stats.get('max_points', 0))} | "
            f"−{_md(stats.get('deducted', 0))} | "
            f"{_md(stats.get('score', 0))} |"
        )
    if len(lines) == 2:
        lines.append("| Score detail unavailable | — | — | — |")
    return lines


def _finding_table(
    findings: List[Finding],
    property_labels: Dict[Tuple[str, str], str],
) -> List[str]:
    lines = [
        "| Finding | Severity | Evidence sample | Decisions affected | What it can distort | Evidence |",
        "|---|---|---:|---|---|---|",
    ]
    for finding in findings:
        field_context = (
            "<br>" + _property_asset_md(finding.object_type, finding.field_name, property_labels)
            if finding.field_name
            else ""
        )
        lines.append(
            f"| **{_md(_finding_title(finding))}**{field_context}<br><small>{_md(finding.id)}</small> | "
            f"{finding.severity.title()} | {_md(_sample(finding))} | "
            f"{_md('; '.join(_finding_impacts(finding)))} | {_narrative_md(finding.business_impact)} | "
            f"{_link(finding.evidence_file, 'CSV')} · "
            f"{_link('processed/measurements/' + finding.module + '.json', 'measurement')} |"
        )
    if len(lines) == 2:
        lines.append("| No major finding was validated | — | — | — | — | — |")
    return lines


def _finding_sections(
    findings: List[Finding],
    property_labels: Dict[Tuple[str, str], str],
) -> List[str]:
    sections = [
        (
            1,
            "Decisions at immediate risk",
            [finding for finding in findings if _finding_priority(finding) == 1],
        ),
        (
            2,
            "Structural trust gaps",
            [finding for finding in findings if _finding_priority(finding) == 2],
        ),
        (
            3,
            "Maintenance and hygiene debt",
            [finding for finding in findings if _finding_priority(finding) == 3],
        ),
    ]
    lines: List[str] = []
    for priority, label, items in sections:
        if not items:
            continue
        lines.extend([f"### Priority {priority} — {label}", ""])
        lines.extend(_finding_table(items, property_labels))
        lines.append("")
    if not lines:
        lines.extend(_finding_table([], property_labels))
    return lines


def _records_by_finding(rows: Iterable[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    grouped: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("finding_id") or ""), []).append(row)
    return grouped


def _record_line_md(row: Dict[str, str]) -> str:
    assets: List[str] = []
    if row.get("company_name"):
        assets.append(_record_asset_md("Company", row["company_name"], row.get("company_url")))
    if row.get("deal_name"):
        assets.append(_record_asset_md("Deal", row["deal_name"], row.get("deal_url")))
    if row.get("pipeline_label"):
        assets.append(_record_term_md("Pipeline", row["pipeline_label"]))
    if row.get("deal_stage_label"):
        assets.append(_record_term_md("Deal stage", row["deal_stage_label"]))
    return " · ".join(assets) or "No linked HubSpot Company or Deal is visible for this evidence row."


def _representative_record_sections(
    findings: Iterable[Finding],
    grouped: Dict[str, List[Dict[str, str]]],
    *,
    limit: int = 3,
) -> List[str]:
    lines: List[str] = []
    for finding in findings:
        rows = grouped.get(finding.id, [])
        named = [row for row in rows if row.get("company_name") or row.get("deal_name")]
        if not named:
            continue
        lines.extend([f"#### {_finding_title(finding)}", ""])
        lines.extend(f"- {_record_line_md(row)}" for row in named[:limit])
        if len(named) > limit:
            lines.append(
                f"- Showing {limit} of {len(named)} mapped records; open "
                f"{_link('report_record_evidence.csv', 'the local record evidence CSV')} for the full set."
            )
        lines.append("")
    return lines


def _root_cause_lines(narrative: ReportNarrative) -> List[str]:
    lines = ["| Hypothesis | Linked findings | Confidence | Evidence and confirmation |", "|---|---|---|---|"]
    for root in narrative.root_causes:
        artifacts = " · ".join(_link(path, Path(path).name) for path in root.supporting_artifacts)
        detail = _narrative_md(root.confirmation_question)
        if artifacts:
            detail += "<br>" + artifacts
        lines.append(
            f"| {_narrative_md(root.hypothesis)} | {_md(', '.join(root.finding_ids))} | "
            f"{root.confidence.title()} | {detail} |"
        )
    if len(lines) == 2:
        lines.append("| No root cause can be stated confidently from the available evidence | — | — | Confirm operating rules with the CRM owner. |")
    return lines


def _recommendation_summary(
    items: List[Tuple[str, RecommendationItem]],
    findings: List[Finding],
) -> List[str]:
    findings_by_id = {finding.id: finding for finding in findings}
    lines = [
        "| Priority | Finding | Human action | Recommended accountable role | Human decision required | Completion condition | Evidence |",
        "|---:|---|---|---|---|---|---|",
    ]
    for category, item in items:
        priority = _finding_priority(findings_by_id.get(item.finding_id))
        lines.append(
            f"| P{priority} | {_md(item.finding_id)} | {_narrative_md(item.action)} | {_narrative_md(item.decision_owner)} | "
            f"{_narrative_md(item.approval_required or CATEGORY_LABELS[category])} | "
            f"{_narrative_md(item.expected_outcome)} | {_link(item.evidence_file, 'CSV')} |"
        )
    if len(lines) == 2:
        lines.append("| — | — | No recommendation was recorded | — | — | — | — |")
    return lines


def _recommendation_detail(category: str, item: RecommendationItem) -> List[str]:
    lines = [
        f"### {_plain(item.finding_id)}",
        "",
        f"- **Human action:** {_narrative_plain(item.action)}",
        f"- **Why:** {_recommendation_basis_plain(item.basis)}",
        f"- **Recommended accountable role:** {_narrative_plain(item.decision_owner)}",
        f"- **Human decision required:** {_narrative_plain(item.approval_required or CATEGORY_LABELS[category])}",
    ]
    if item.target:
        lines.append(f"- **Exact scope:** {_narrative_plain(item.target)}")
    if item.current_state:
        lines.append(f"- **Current state:** {_narrative_plain(item.current_state)}")
    if item.desired_state:
        lines.append(f"- **Desired state:** {_narrative_plain(item.desired_state)}")
    if item.implementation_steps:
        lines.extend(["- **Implementation:**"] + [f"  {index}. {_narrative_plain(step)}" for index, step in enumerate(item.implementation_steps, 1)])
    lines.append(f"- **Completion condition:** {_narrative_plain(item.expected_outcome)}")
    if item.success_measure:
        lines.append(f"- **Success measure:** {_narrative_plain(item.success_measure)}")
    lines.append(f"- **Evidence:** {_link(item.evidence_file, 'evidence CSV')}")
    if item.evidence_refs:
        lines.append("- **Additional references:** " + " · ".join(_link(path, Path(path).name) for path in item.evidence_refs))
    if item.risk_notes:
        lines.append(f"- **Risk note:** {_plain(item.risk_notes)}")
    lines.append("")
    return lines


def _automatic_limitations(manifest: Dict[str, Any]) -> List[str]:
    limitations = [
        "Record age is based on the last-modified timestamp. It does not prove that a person, marketing program, or sales representative actively engaged with the record.",
        "A long or resumed full-history extract is a close operational snapshot, not a database transaction taken at one instant.",
    ]
    if not manifest.get("full_history"):
        limitations.append("This run covers a selected time window. Absence outside that window cannot be assessed.")
    if any((manifest.get("truncated") or {}).values()):
        limitations.append("At least one object extract was truncated. Measurements that depend on that object are incomplete.")
    return limitations


def _evidence_index() -> List[str]:
    lines: List[str] = []
    for module in MODULES:
        label = module.replace("_", " ").title()
        lines.append(
            f"- {label}: {_link('evidence/' + module + '.csv', 'evidence CSV')} · "
            f"{_link('processed/measurements/' + module + '.json', 'measurement file')}"
        )
    return lines


def _html_text(value: Any) -> str:
    return html.escape(_plain(value))


def _narrative_html(value: Any) -> str:
    return html.escape(_narrative_plain(value))


def _html_link(path: str, label: str) -> str:
    return f'<a href="{html.escape(path.replace(" ", "%20"), quote=True)}">{html.escape(label)}</a>'


def _asset_html(asset_type: str, label: Any) -> str:
    return (
        '<span class="hubspot-asset"><span class="hubspot-kind">HubSpot '
        f'{html.escape(asset_type)}:</span> <strong class="hubspot-name">{_html_text(label)}</strong></span>'
    )


def _record_asset_html(asset_type: str, label: Any, url: Any) -> str:
    value = f'<strong class="hubspot-name">{_html_text(label)}</strong>'
    if url:
        value = (
            f'<a class="hubspot-record" href="{html.escape(str(url), quote=True)}" '
            f'target="_blank" rel="noopener noreferrer">{value}</a>'
        )
    return f'<span class="record-kind">{html.escape(asset_type)}:</span> {value}'


def _record_term_html(asset_type: str, label: Any) -> str:
    return (
        f'<span class="record-kind">{html.escape(asset_type)}:</span> '
        f'<strong class="hubspot-name">{_html_text(label)}</strong>'
    )


def _property_asset_html(
    object_type: str,
    field: str,
    property_labels: Dict[Tuple[str, str], str],
) -> str:
    label = property_labels.get((object_type, field), field)
    display = f"{label} ({field})" if label != field else field
    return _asset_html("property", display)


def _property_summary_html(
    object_type: str,
    field: str,
    property_labels: Dict[Tuple[str, str], str],
) -> str:
    """Compact property reference for narrow visual cards.

    The internal name remains available as a tooltip and in the Markdown and
    operator evidence, but it does not force unreadable wrapping in the HTML
    dashboard.
    """
    label = property_labels.get((object_type, field), field)
    return (
        f'<span class="hubspot-asset" title="Internal name: {html.escape(field, quote=True)}">'
        '<span class="hubspot-kind">HubSpot property:</span> '
        f'<strong class="hubspot-name">{_html_text(label)}</strong></span>'
    )


def _recommendation_basis_plain(value: Any) -> str:
    text = _narrative_plain(value)
    match = re.match(r"^[a-z][a-z0-9_]*:\s*(.+)$", text)
    return match.group(1) if match else text


def _record_line_html(row: Dict[str, str]) -> str:
    assets: List[str] = []
    if row.get("company_name"):
        assets.append(
            _record_asset_html("Company", row["company_name"], row.get("company_url"))
        )
    if row.get("deal_name"):
        assets.append(_record_asset_html("Deal", row["deal_name"], row.get("deal_url")))
    if row.get("pipeline_label"):
        assets.append(_record_term_html("Pipeline", row["pipeline_label"]))
    if row.get("deal_stage_label"):
        assets.append(_record_term_html("Deal stage", row["deal_stage_label"]))
    return " <span aria-hidden=\"true\">·</span> ".join(assets)


def _representative_record_html(
    finding: Finding,
    grouped: Dict[str, List[Dict[str, str]]],
    *,
    limit: int = 3,
) -> str:
    rows = grouped.get(finding.id, [])
    named = [row for row in rows if row.get("company_name") or row.get("deal_name")]
    if not named:
        return ""
    items = "".join(f"<li>{_record_line_html(row)}</li>" for row in named[:limit])
    remainder = ""
    if len(named) > limit:
        remainder = (
            f'<p class="record-more">Showing {limit} of {len(named)} mapped records. '
            f'{_html_link("report_record_evidence.csv", "Open the local record evidence CSV")} '
            "for the full set.</p>"
        )
    return (
        '<div class="record-samples"><h4>HubSpot records in this finding</h4>'
        f"<ul>{items}</ul>{remainder}</div>"
    )


def _html_bar(value: float, label_html: str, tone: str = "primary") -> str:
    width = max(0.0, min(float(value), 100.0))
    return (
        f'<div class="metric-row"><div class="metric-label">{label_html}</div>'
        f'<div class="bar"><span class="{tone}" style="width:{width:.1f}%"></span></div>'
        f'<div class="metric-value">{width:.1f}%</div></div>'
    )


def _score_explainer_html(score: Dict[str, Any]) -> str:
    max_total = int(score.get("max_total", 100) or 100)
    total = int(score.get("total", 0) or 0)
    deducted = max(0, max_total - total)
    rows = "".join(
        "<div class=\"score-row\">"
        f"<span>{html.escape(SCORE_CATEGORY_LABELS.get(category, _identifier_title(category)))}</span>"
        f"<strong>{html.escape(str(stats.get('score', 0)))}/{html.escape(str(stats.get('max_points', 0)))}</strong>"
        f"<small>−{html.escape(str(stats.get('deducted', 0)))}</small>"
        "</div>"
        for category, stats in (score.get("categories", {}) or {}).items()
        if isinstance(stats, dict)
    )
    return (
        '<div class="score-explainer">'
        '<div class="score-copy"><h3>How this score is calculated</h3>'
        f'<p><strong>{max_total} starting points − {deducted} deducted points = {total}.</strong> '
        "Only approved or revised findings count. Critical findings deduct 10 points, high 6, medium 3, and low 1, capped at each category maximum.</p>"
        f'<p>{_html_link("score.json", "Open the complete score calculation")}</p></div>'
        f'<div class="score-rows">{rows}</div></div>'
    )


def _render_html(
    run_dir: Path,
    manifest: Dict[str, Any],
    counts: Dict[str, Any],
    summary: Dict[str, Any],
    activity: Dict[str, Any],
    identity: Dict[str, Any],
    lifecycle: Dict[str, Any],
    associations: Dict[str, Any],
    pipelines: Dict[str, Any],
    score: Dict[str, Any],
    narrative: ReportNarrative,
    report_findings: List[Finding],
    recommendation_items: List[Tuple[str, RecommendationItem]],
    limitations: List[str],
    business_name: str,
    property_labels: Dict[Tuple[str, str], str],
    record_groups: Dict[str, List[Dict[str, str]]],
) -> Path:
    report_title = (
        f"{business_name} CRM Trust Audit"
        if business_name
        else "HubSpot Marketing-to-Pipeline Trust Audit"
    )
    record_counts = {**counts, **summary.get("record_counts", {})}
    cards = [
        ("Contacts", record_counts.get("contacts", 0)),
        ("Companies", record_counts.get("companies", 0)),
        ("Deals", record_counts.get("deals", 0)),
        ("Pipelines", record_counts.get("deal_pipelines", 0)),
        ("Trust score", f"{score.get('total', '—')}/{score.get('max_total', 100)}"),
    ]
    completeness_rows = _completeness_rows(summary, limit=100)
    completeness_by_object: Dict[str, List[Tuple[str, str, float, int, int]]] = {
        object_type: [row for row in completeness_rows if row[0] == object_type]
        for object_type in ("contacts", "companies", "deals")
    }
    quality_cards = ""
    for object_type, rows in completeness_by_object.items():
        if not rows:
            continue
        bars = "".join(
            _html_bar(
                fill,
                _property_summary_html(object_type, field, property_labels),
                "accent" if fill >= 90 else "warm",
            )
            for _object_type, field, fill, _total, _present in rows
        )
        quality_cards += (
            f'<article class="quality-card"><div class="quality-card-head"><h3>{html.escape(object_type.title())}</h3>'
            f'<span>{len(rows)} key properties</span></div>{bars}</article>'
        )
    if not quality_cards:
        quality_cards = '<p class="empty">Field completeness was not available.</p>'
    validity = "".join(
        _html_bar(
            float(stats.get("valid_format_rate_among_present", 0)),
            _property_summary_html("contacts", field, property_labels),
            "primary",
        )
        for field, stats in (identity.get("fields", {}) or {}).items()
    ) or '<p class="empty">Identity format checks were not available.</p>'
    activity_rows = ""
    for object_type, stats in (activity.get("objects", {}) or {}).items():
        buckets = stats.get("recency_buckets", {})
        total = max(int(stats.get("total", 0)), 1)
        segments = [
            ("Recent", buckets.get("within_30_days", 0), "accent"),
            ("Active", buckets.get("31_to_90_days", 0), "primary"),
            ("Aging", buckets.get("91_to_180_days", 0), "warm"),
            ("Stale", buckets.get("over_180_days", 0), "error"),
        ]
        bars = "".join(
            f'<span class="{tone}" style="width:{(int(value) / total) * 100:.2f}%" title="{label}: {value}"></span>'
            for label, value, tone in segments
        )
        legend = " · ".join(f"{label}: {value}" for label, value, _tone in segments)
        activity_rows += (
            f'<div class="stack-row"><strong>{html.escape(object_type.title())}</strong>'
            f'<div class="stack">{bars}</div><small>{html.escape(legend)}</small></div>'
        )
    funnel_rows = ""
    contact_lifecycle = lifecycle.get("contacts", {}) if isinstance(lifecycle, dict) else {}
    max_stage = max([int(value) for value in contact_lifecycle.values()] or [1])
    for stage, count in sorted(contact_lifecycle.items(), key=lambda item: -int(item[1])):
        stage_label = LIFECYCLE_LABELS.get(_plain(stage).lower(), _plain(stage))
        funnel_rows += (
            f'<div class="metric-row"><div class="metric-label">{_asset_html("lifecycle stage", stage_label)}</div>'
            f'<div class="bar"><span class="primary" style="width:{(int(count) / max_stage) * 100:.1f}%"></span></div>'
            f'<div class="metric-value">{int(count):,}</div></div>'
        )
    association_rows = "".join(
        _html_bar(
            float(stats.get("coverage_pct", 0)),
            html.escape(name.replace("_", " ").title()),
            "accent",
        )
        for name, stats in associations.items() if isinstance(stats, dict)
    ) or "<p>Association coverage was not available.</p>"
    pipeline_rows = "".join(
        f'<tr><td>{_asset_html("pipeline", p.get("label") or p.get("pipeline_id"))}</td><td>{int(p.get("stage_count", 0))}</td><td>{int(p.get("deal_count", 0))}</td></tr>'
        for p in pipelines.get("pipelines", []) or []
    ) or '<tr><td colspan="3">Pipeline details were not available.</td></tr>'
    def render_finding_card(finding: Finding, priority: int) -> str:
        impacts = ", ".join(_finding_impacts(finding))
        property_context = (
            f'<p class="field-context">{_property_asset_html(finding.object_type, finding.field_name, property_labels)}</p>'
            if finding.field_name
            else ""
        )
        record_context = _representative_record_html(
            finding,
            record_groups,
            limit=3 if priority == 1 else 2,
        )
        detail_class = "finding-detail-grid" if record_context else "finding-detail-grid no-record-context"
        return f"""
        <article class="finding finding-priority-{priority} severity-{html.escape(finding.severity)}">
          <div class="finding-head"><span class="priority-badge">Priority {priority}</span><span>{html.escape(finding.severity.title())} severity · {html.escape(finding.confidence.title())} confidence</span></div>
          <div class="{detail_class}">
            <div class="finding-copy">
              <h3>{html.escape(_finding_title(finding))}</h3>
              {property_context}
              <dl class="finding-facts">
                <div><dt>Records affected</dt><dd>{html.escape(_sample(finding))}</dd></div>
                <div><dt>Management decisions exposed</dt><dd>{html.escape(impacts)}</dd></div>
              </dl>
              <p class="finding-impact">{_narrative_html(finding.business_impact)}</p>
              <p class="evidence-links">{_html_link(finding.evidence_file, "Evidence CSV")} · {_html_link('processed/measurements/' + finding.module + '.json', "Measurement")}</p>
            </div>
            {record_context}
          </div>
        </article>"""

    priority_one = [finding for finding in report_findings if _finding_priority(finding) == 1]
    priority_two = [finding for finding in report_findings if _finding_priority(finding) == 2]
    priority_three = [finding for finding in report_findings if _finding_priority(finding) == 3]
    finding_groups: List[str] = []
    if priority_one:
        priority_cards = "".join(render_finding_card(finding, 1) for finding in priority_one)
        priority_one_label = "finding" if len(priority_one) == 1 else "findings"
        finding_groups.append(
            '<div class="finding-group priority-one"><div class="finding-group-head">'
            f'<div><span class="group-number">P1</span></div><div><h3>Decisions at immediate risk</h3><p>{len(priority_one)} validated {priority_one_label} can materially distort management reporting and should be resolved first.</p></div>'
            f'</div><div class="finding-list">{priority_cards}</div></div>'
        )
    if priority_two:
        priority_cards = "".join(render_finding_card(finding, 2) for finding in priority_two)
        priority_two_label = "finding" if len(priority_two) == 1 else "findings"
        finding_groups.append(
            '<div class="finding-group priority-two"><div class="finding-group-head">'
            f'<div><span class="group-number">P2</span></div><div><h3>Structural trust gaps</h3><p>{len(priority_two)} validated {priority_two_label} weaken reporting confidence or CRM operating consistency.</p></div>'
            f'</div><div class="finding-list secondary-list">{priority_cards}</div></div>'
        )
    if priority_three:
        priority_cards = "".join(render_finding_card(finding, 3) for finding in priority_three)
        priority_three_label = "finding" if len(priority_three) == 1 else "findings"
        finding_groups.append(
            '<div class="finding-group priority-three"><div class="finding-group-head">'
            f'<div><span class="group-number">P3</span></div><div><h3>Maintenance and hygiene debt</h3><p>{len(priority_three)} validated {priority_three_label} should be resolved after decision-critical gaps.</p></div>'
            f'</div><div class="finding-list secondary-list">{priority_cards}</div></div>'
        )
    findings_html = "".join(finding_groups) or '<p class="empty">No major finding was validated.</p>'
    roots_html = "".join(
        f'<tr><td>{_narrative_html(root.hypothesis)}</td><td>{html.escape(", ".join(root.finding_ids))}</td><td>{html.escape(root.confidence.title())}</td><td>{_narrative_html(root.confirmation_question)}</td></tr>'
        for root in narrative.root_causes
    ) or '<tr><td colspan="4">No root cause can be stated confidently from the available evidence.</td></tr>'
    recs_html = ""
    findings_by_id = {finding.id: finding for finding in report_findings}
    for index, (category, item) in enumerate(recommendation_items, 1):
        priority = _finding_priority(findings_by_id.get(item.finding_id))
        recs_html += f"""
        <article class="recommendation">
          <div class="recommendation-head"><span class="action-number">{index}</span><div><div class="eyebrow" title="Finding ID: {html.escape(item.finding_id, quote=True)}">Priority {priority} · {html.escape(_identifier_title(item.finding_id))}</div><span class="approval-class">{html.escape(CATEGORY_LABELS[category])}</span></div></div>
          <h3>{_narrative_html(item.action)}</h3>
          <div class="rec-grid">
            <p><span class="rec-label">Why this matters</span>{html.escape(_recommendation_basis_plain(item.basis))}</p>
            <p><span class="rec-label">Recommended accountable role</span>{_narrative_html(item.decision_owner)}</p>
            <p><span class="rec-label">Human decision required</span>{_narrative_html(item.approval_required or CATEGORY_LABELS[category])}</p>
            <p><span class="rec-label">Completion condition</span>{_narrative_html(item.expected_outcome)}</p>
          </div>
          <p class="evidence-links">{_html_link(item.evidence_file, "Evidence CSV")} · {_html_link('operator_appendix.md', "Implementation detail")}</p>
        </article>"""
    if not recs_html:
        recs_html = '<p class="empty">No recommendation was recorded.</p>'
    evidence_html = "".join(
        f'<li><strong>{html.escape(module.replace("_", " ").title())}</strong>: {_html_link("evidence/" + module + ".csv", "CSV")} · {_html_link("processed/measurements/" + module + ".json", "measurement")}</li>'
        for module in MODULES
    )
    limitation_html = "".join(f"<li>{_narrative_html(item)}</li>" for item in limitations)
    card_html = "".join(f'<div class="kpi"><span>{html.escape(label)}</span><strong>{html.escape(str(value))}</strong></div>' for label, value in cards)
    mode = "Full history" if manifest.get("full_history") else "Selected time window"
    generated = _plain(manifest.get("snapshot_completed_at"))
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(report_title)}</title>
  <style>
    :root{{--ink:#1f1b18;--muted:#5d544d;--line:rgba(31,27,24,.12);--canvas:#fcf9f6;--paper:#f5efe9;--wash:#f6f0ea;--blush:#f3dfd2;--primary:#964900;--accent:#fe810e;--accent-ink:#5f2b00;--warm:#c98f60;--error:#c1121f;--dark:#1b1714;--dark-text:#fffaf5}}
    *{{box-sizing:border-box}} body{{margin:0;background:var(--canvas);color:var(--ink);font:15px/1.6 "Manrope",ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
    a{{color:var(--primary);font-weight:600;text-decoration-color:rgba(150,73,0,.28);text-underline-offset:3px}} a:hover{{color:var(--accent);text-decoration-color:rgba(254,129,14,.42)}} a:focus-visible{{outline:3px solid var(--accent);outline-offset:3px}} .page{{max-width:1200px;margin:0 auto;background:var(--canvas);box-shadow:0 20px 60px rgba(31,27,24,.07)}}
    header{{padding:64px 72px 52px;background:radial-gradient(110% 150% at 82% 20%,rgba(150,73,0,.48),transparent 55%),var(--dark);color:var(--dark-text)}} .brand{{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:800}}
    h1,h2,h3{{font-family:"Newsreader",Georgia,"Times New Roman",serif}} h1{{font-size:44px;line-height:1.04;max-width:850px;margin:16px 0 20px;letter-spacing:-.025em}} .subtitle{{max-width:780px;color:#fffaf5;font-size:18px}} .meta{{display:flex;gap:24px;flex-wrap:wrap;margin-top:28px;color:#eadfd6;font-size:13px}}
    main{{padding:0 72px 72px}} section{{padding:50px 0;border-bottom:1px solid var(--line)}} section:last-child{{border:0}} h2{{font-size:32px;line-height:1.15;letter-spacing:-.02em;margin:0 0 12px}} h3{{font-size:20px;line-height:1.25}} .lede{{max-width:850px;color:var(--muted);font-size:17px}}
    .kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:26px 0}} .kpi{{background:rgba(255,255,255,.78);padding:18px;border-radius:14px;border:1px solid rgba(31,27,24,.08);box-shadow:0 16px 34px rgba(31,27,24,.035)}} .kpi span{{display:block;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}} .kpi strong{{display:block;font-family:"Newsreader",Georgia,serif;font-size:29px;margin-top:7px}} .score-explainer{{display:grid;grid-template-columns:minmax(260px,.8fr) minmax(0,1.2fr);gap:28px;margin-top:24px;padding:22px 24px;background:var(--dark);color:var(--dark-text);border-radius:18px}} .score-copy h3{{margin:0 0 8px;color:var(--dark-text)}} .score-copy p{{margin:8px 0;color:rgba(255,250,245,.82)}} .score-copy a{{color:var(--accent)}} .score-rows{{display:grid;gap:8px}} .score-row{{display:grid;grid-template-columns:minmax(0,1fr) 70px 42px;gap:10px;align-items:center;padding:8px 10px;border:1px solid rgba(255,255,255,.12);border-radius:10px}} .score-row strong,.score-row small{{text-align:right;font-variant-numeric:tabular-nums}} .score-row small{{color:rgba(255,250,245,.68)}}
    .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:40px}} .panel{{background:rgba(247,240,234,.8);border:1px solid rgba(31,27,24,.08);border-radius:20px;padding:24px}} .panel h3{{margin-top:0}}
    .quality-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-top:24px;align-items:start}} .quality-card{{background:rgba(247,240,234,.8);border:1px solid rgba(31,27,24,.08);border-radius:18px;padding:20px;min-width:0}} .quality-card-head{{display:flex;justify-content:space-between;gap:16px;align-items:baseline;margin-bottom:12px}} .quality-card-head h3{{margin:0}} .quality-card-head span{{color:var(--muted);font-size:12px}} .identity-panel{{display:grid;grid-template-columns:minmax(210px,.7fr) minmax(0,2fr);gap:30px;align-items:start;margin-top:16px;padding:22px 24px;background:rgba(255,255,255,.58);border:1px solid var(--line);border-radius:18px}} .identity-panel h3{{margin:0 0 6px}} .identity-panel p{{color:var(--muted);margin:0}} .identity-metrics{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 16px}}
    .metric-row{{display:grid;grid-template-columns:minmax(120px,1.45fr) minmax(70px,1fr) 52px;gap:10px;align-items:center;margin:10px 0}} .metric-label{{font-size:12px;line-height:1.35;overflow-wrap:anywhere}} .metric-value{{font-variant-numeric:tabular-nums;text-align:right;font-size:12px;font-weight:700}} .hubspot-asset{{color:var(--ink)}} .hubspot-kind{{font-weight:600;color:var(--muted)}} .hubspot-name{{font-weight:750;color:var(--ink)}} .hubspot-record{{font-weight:inherit;text-decoration-thickness:1px}} .record-kind{{color:var(--muted);font-size:.92em}}
    .bar,.stack{{height:10px;background:#e8ded5;border-radius:999px;overflow:hidden;display:flex}} .bar span,.stack span{{display:block;height:100%}} .primary{{background:var(--primary)}} .accent{{background:var(--accent)}} .warm{{background:var(--warm)}} .error{{background:var(--error)}}
    .stack-row{{margin:18px 0}} .stack-row strong{{display:block;margin-bottom:7px}} .stack-row small{{display:block;color:var(--muted);margin-top:6px}}
    table{{width:100%;border-collapse:collapse;margin-top:20px}} th,td{{text-align:left;padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:top}} th{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em}}
    .findings{{margin-top:26px}} .finding-group+.finding-group{{margin-top:42px;padding-top:38px;border-top:1px solid var(--line)}} .finding-group-head{{display:grid;grid-template-columns:54px 1fr;gap:14px;align-items:start;margin-bottom:18px}} .finding-group-head h3{{font-size:23px;margin:1px 0 4px}} .finding-group-head p{{margin:0;color:var(--muted);max-width:760px}} .group-number{{display:grid;place-items:center;width:48px;height:48px;border-radius:14px;background:var(--dark);color:var(--dark-text);font-weight:800;letter-spacing:.04em}} .priority-two .group-number{{background:var(--paper);color:var(--primary);border:1px solid rgba(150,73,0,.25)}} .priority-three .group-number{{background:transparent;color:var(--muted);border:1px solid var(--line)}} .finding-list{{display:grid;gap:18px}} .secondary-list{{grid-template-columns:repeat(2,minmax(0,1fr));align-items:start}} .finding{{background:rgba(255,255,255,.72);border:1px solid var(--line);border-radius:18px;padding:24px;min-width:0}} .finding-priority-1{{border-top:4px solid var(--error)}} .finding-priority-2{{border-top:3px solid var(--warm);padding:20px}} .finding-priority-3{{border-top:2px solid var(--line);padding:20px}} .finding h3{{margin:10px 0 6px;font-size:23px}} .finding-priority-2 h3,.finding-priority-3 h3{{font-size:20px}} .finding p{{margin:9px 0}} .finding-head{{display:flex;justify-content:space-between;gap:20px;color:var(--muted);font-size:12px}} .priority-badge{{font-weight:800;color:var(--ink);text-transform:uppercase;letter-spacing:.05em}} .finding-detail-grid{{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(280px,.85fr);gap:24px;align-items:start}} .finding-detail-grid.no-record-context,.finding-priority-2 .finding-detail-grid,.finding-priority-3 .finding-detail-grid{{grid-template-columns:1fr}} .no-record-context .finding-copy{{max-width:820px}} .field-context{{font-size:13px;color:var(--muted)}} .finding-facts{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:16px 0}} .finding-facts div{{padding:11px 12px;background:var(--wash);border-radius:10px}} .finding-facts dt{{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em}} .finding-facts dd{{margin:3px 0 0;font-weight:650}} .finding-impact{{font-size:15px}} .evidence-links{{font-size:13px;color:var(--muted)}} .record-samples{{margin:8px 0 0;padding:15px 16px;background:var(--wash);border-radius:12px;border:1px solid var(--line)}} .record-samples h4{{font-family:inherit;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:0 0 8px}} .record-samples ul{{list-style:none;margin:0;padding:0}} .record-samples li{{margin:0;padding:8px 0;border-top:1px solid rgba(31,27,24,.08);overflow-wrap:anywhere}} .record-samples li:first-child{{border-top:0;padding-top:2px}} .record-more{{color:var(--muted);font-size:12px;margin-bottom:0}}
    .recommendation{{border-top:3px solid var(--primary);background:rgba(247,240,234,.8);padding:24px;border-radius:8px 8px 20px 20px;margin:18px 0}} .recommendation h3{{font-size:21px;margin:14px 0 14px;max-width:900px}} .recommendation-head{{display:flex;gap:12px;align-items:center}} .action-number{{display:grid;place-items:center;width:34px;height:34px;border-radius:10px;background:var(--primary);color:white;font-weight:800}} .eyebrow{{font-size:11px;color:var(--primary);font-weight:750;text-transform:uppercase;letter-spacing:.06em}} .approval-class{{display:block;color:var(--muted);font-size:12px}} .rec-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:2px 28px}} .rec-grid p{{margin:8px 0}} .rec-label{{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:2px}}
    .note{{background:var(--blush);border-left:4px solid var(--primary);padding:16px 18px;border-radius:10px}} .footer-note{{color:var(--muted);font-size:13px}} ul{{padding-left:20px}} .report-footer{{padding:34px 72px;background:var(--dark);color:var(--dark-text);display:flex;justify-content:space-between;gap:24px;align-items:center}} .report-footer p{{margin:0}} .report-footer a{{color:var(--accent);text-decoration-color:rgba(254,129,14,.45)}}
    @media(max-width:920px){{.quality-grid,.identity-metrics,.secondary-list{{grid-template-columns:1fr 1fr}} .finding-detail-grid,.score-explainer{{grid-template-columns:1fr}}}}
    @media(max-width:820px){{header,main,.report-footer{{padding-left:28px;padding-right:28px}} h1{{font-size:34px}} .kpis{{grid-template-columns:repeat(2,1fr)}} .two-col,.quality-grid,.identity-panel,.identity-metrics,.secondary-list,.rec-grid{{grid-template-columns:1fr}} .finding-group-head{{grid-template-columns:42px 1fr}} .group-number{{width:38px;height:38px;border-radius:10px}} .report-footer{{align-items:flex-start;flex-direction:column}}}}
    @media print{{body{{background:white;font-size:11pt}} .page{{max-width:none;box-shadow:none}} header{{padding:35px 42px;background:var(--dark)!important;-webkit-print-color-adjust:exact;print-color-adjust:exact}} main{{padding:0 42px 42px}} section{{padding:30px 0}} a{{color:var(--ink);text-decoration:underline}} .finding,.recommendation,.panel{{break-inside:avoid}} .report-footer{{padding:24px 42px;-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}
  </style>
</head>
<body><div class="page">
  <header>
    <div class="brand">Smartify Marketing · CRM Trust Audit</div>
    <h1>{html.escape(report_title)}</h1>
    <p class="subtitle">HubSpot Marketing-to-Pipeline Trust Audit · A factual view of {html.escape(business_name + "’s " if business_name else "the ")}CRM scale, data usability, reporting risk, and the actions needed to improve decision confidence.</p>
    <div class="meta"><span>Snapshot: {html.escape(generated)}</span><span>Coverage: {html.escape(mode)}</span><span>No CRM records were changed</span></div>
  </header>
  <main>
    <section id="summary"><h2>Executive Summary</h2><p class="lede">{_narrative_html(narrative.executive_summary)}</p><p><strong>CRM trust score: {html.escape(str(score.get('total', '—')))}/{html.escape(str(score.get('max_total', 100)))}.</strong> The score summarizes reviewed data-quality findings; it does not measure revenue performance or return on investment.</p>{_score_explainer_html(score)}<p>{_html_link('crm_trust_report.md', 'Text version')} · {_html_link('operator_appendix.md', 'Operator appendix')}</p></section>
    <section id="snapshot"><h2>CRM Snapshot</h2><p class="lede">{html.escape(mode)} extract completed {html.escape(generated)}. Counts and extraction coverage are taken from the completed snapshot manifest.</p><div class="kpis">{card_html}</div></section>
    <section id="quality"><h2>Data Quality and Usability</h2><p class="lede">{_narrative_html(narrative.data_quality_summary)}</p><div class="quality-grid">{quality_cards}</div><div class="identity-panel"><div><h3>Contact identity validity</h3><p>Format validity among populated values. Empty-field coverage is shown in the Contact property card above.</p></div><div class="identity-metrics">{validity}</div></div></section>
    <section id="activity"><h2>Activity and Data Age</h2><p class="lede">Updated within 30 days, active within 31–90 days, aging within 91–180 days, and stale after 180 days. These bands use record modification dates.</p>{activity_rows}</section>
    <section id="funnel"><h2>Funnel and Association Coverage</h2><div class="two-col"><div class="panel"><h3>Contact lifecycle distribution</h3>{funnel_rows or '<p>Lifecycle distribution was not available.</p>'}</div><div class="panel"><h3>Association coverage</h3>{association_rows}</div></div><h3>Deal pipelines</h3><table><thead><tr><th>Pipeline</th><th>Stages</th><th>Deals</th></tr></thead><tbody>{pipeline_rows}</tbody></table></section>
    <section id="findings"><h2>Key Findings</h2><p class="lede">Every finding below has passed review and links to its record-level evidence and measurement file.</p><div class="findings">{findings_html}</div></section>
    <section id="causes"><h2>Root Cause Hypotheses</h2><p class="lede">These are evidence-based hypotheses, not confirmed facts. Confidence and the question needed for confirmation are shown explicitly.</p><table><thead><tr><th>Hypothesis</th><th>Findings</th><th>Confidence</th><th>What to confirm</th></tr></thead><tbody>{roots_html}</tbody></table></section>
    <section id="actions"><h2>Recommended Actions</h2><p class="lede">The audit has already prepared each affected cohort and its evidence. “Recommended accountable role” names the business role that should review the records and make or authorize the decision; it is not presented as a verified HubSpot owner name. Exact implementation detail is in the appendix.</p>{recs_html}</section>
    <section id="limits"><h2>What This Audit Cannot Determine</h2><ul>{limitation_html}</ul></section>
    <section id="evidence"><h2>Evidence and Supporting Files</h2><p class="note">The main report shows decision-relevant evidence. The operator appendix contains every validated finding, detailed actions, and links to supporting artifacts.</p><ul>{evidence_html}<li>{_html_link('report_record_evidence.csv', 'Mapped Company and Deal evidence')}</li><li>{_html_link('findings.json', 'Validated findings')}</li><li>{_html_link('operator_appendix.md', 'Operator appendix')}</li><li>{_html_link('schema_discovery_report.md', 'Schema discovery report')}</li></ul></section>
    <section id="next"><h2>Next Review</h2><p class="lede">{_narrative_html(narrative.suggested_next_review)}</p></section>
    <section id="sharing"><h2>Sharing the Report</h2><p class="lede">This HTML file is generated locally. It is not a public URL, and its supporting-file links work only when the related output folder stays together.</p><p><strong>Treat this as a confidential CRM report.</strong> It can contain identifiable HubSpot Company and Deal names plus direct record links. For a fixed copy, choose <strong>Print → Save as PDF</strong>, then share the PDF only with authorized recipients through an approved channel. If you share interactive HTML, keep the complete report package together, use approved access-controlled hosting or file sharing, and never include the raw data folder, environment files, or secrets.</p><p class="footer-note">The HTML and Markdown versions are generated from the same validated artifacts.</p></section>
  </main>
  <footer class="report-footer"><p><strong>Smartify Marketing</strong><br>Your Strategic B2B Marketing Partner</p><p>For more marketing systems insights and updates: <a href="https://smartifymarketing.com">smartifymarketing.com</a> · <a href="https://github.com/AliceEinstein">GitHub</a></p></footer>
</div></body></html>"""
    document = "\n".join(line.rstrip() for line in document.splitlines()) + "\n"
    path = run_dir / "crm_trust_report.html"
    path.write_text(document, encoding="utf-8")
    return path


def render_reports(run_dir: Path) -> Tuple[Path, Path, Path, Path]:
    run_dir = Path(run_dir)
    manifest = _load(run_dir, "manifest.json", {})
    counts = _load(run_dir, "processed/object_counts.json", {})
    summary = _load(run_dir, "processed/snapshot_summary.json", {}) or {"field_completeness": {}}
    activity = _load(run_dir, "processed/activity_summary.json", {})
    identity = _load(run_dir, "processed/identity_completeness.json", {})
    lifecycle = _load(run_dir, "processed/lifecycle_distribution.json", {})
    associations = _load(run_dir, "processed/association_summary.json", {})
    pipelines = _load(run_dir, "processed/pipeline_summary.json", {})
    score = _load(run_dir, "score.json", {})
    narrative = ReportNarrative.model_validate(_load(run_dir, "report_narrative.json", {}))
    recommendations = _recommendations(run_dir)
    findings = _findings(run_dir)
    accepted = _accepted_findings(findings)
    report_findings = accepted
    record_rows, property_labels = build_report_record_evidence(run_dir, accepted)
    record_groups = _records_by_finding(record_rows)
    identity_info = report_identity(run_dir)
    business_name = str(identity_info.get("business_name") or "")
    report_title = (
        f"{business_name} CRM Trust Audit"
        if business_name
        else "HubSpot Marketing-to-Pipeline Trust Audit"
    )
    recommendation_items = _all_recommendations(recommendations, report_findings)
    record_counts = {**counts, **summary.get("record_counts", {})}
    limitations = _automatic_limitations(manifest) + narrative.limitations

    lines: List[str] = [
        f"# {report_title}",
        "",
        "*HubSpot Marketing-to-Pipeline Trust Audit*",
        "",
        "## Executive Summary",
        "",
        _narrative_plain(narrative.executive_summary),
        "",
        f"**CRM trust score: {score.get('total', '—')}/{score.get('max_total', 100)}.**",
        "The score summarizes the reviewed data-quality findings. It is not a measure of revenue performance or return on investment.",
        "",
        "### How the score is calculated",
        "",
        f"**{score.get('max_total', 100)} starting points − {max(0, int(score.get('max_total', 100) or 100) - int(score.get('total', 0) or 0))} deducted points = {score.get('total', '—')}.** Only approved or revised findings count. Critical findings deduct 10 points, high 6, medium 3, and low 1, capped at each category maximum.",
        "",
    ]
    lines.extend(_score_table(score))
    lines.extend([
        "",
        f"- {_link('score.json', 'Complete score calculation')}",
        "",
        "No CRM records were changed during this audit.",
        "",
        "## CRM Snapshot",
        "",
    ])
    lines.extend(_snapshot_table(manifest, record_counts))
    lines.extend(
        [
            "",
            f"- Snapshot completed: {_plain(manifest.get('snapshot_completed_at'))}",
            f"- Coverage: {'Full history' if manifest.get('full_history') else 'Selected time window'}",
            "",
            "## Data Quality and Usability",
            "",
            _narrative_plain(narrative.data_quality_summary),
            "",
            "### Key field completeness",
            "",
        ]
    )
    lines.extend(_completeness_table(summary, property_labels))
    lines.extend(["", "### Contact identity completeness and validity", ""])
    lines.extend(_identity_table(identity, property_labels))
    lines.extend(
        [
            "",
            "## Activity and Data Age",
            "",
            "The table uses each record's last-modified date. It shows recency, not confirmed human engagement.",
            "",
        ]
    )
    lines.extend(_activity_table(activity))
    lines.extend(["", "## Funnel and Association Coverage", "", "### Lifecycle distribution", ""])
    lines.extend(_lifecycle_table(lifecycle))
    lines.extend(["", "### Association coverage", ""])
    lines.extend(_association_table(associations))
    lines.extend(["", "### Deal pipelines", ""])
    lines.extend(_pipeline_table(pipelines))
    lines.extend(["", "## Key Findings", "", "Validated findings are ordered by decision priority: P1 first, then structural P2 gaps, followed by P3 maintenance debt.", ""])
    lines.extend(_finding_sections(report_findings, property_labels))
    representative_sections = _representative_record_sections(report_findings, record_groups)
    if representative_sections:
        lines.extend(
            [
                "",
                "### Representative HubSpot Companies and Deals",
                "",
                "These named records connect material findings to the CRM. Up to three records are shown per finding; the local CSV contains the full mapped set.",
                "",
            ]
        )
        lines.extend(representative_sections)
    lines.extend(["", "## Root Cause Hypotheses", "", "These are evidence-based hypotheses. Confidence and the question needed for confirmation are shown explicitly.", ""])
    lines.extend(_root_cause_lines(narrative))
    lines.extend([
        "",
        "## Recommended Actions",
        "",
        "The audit has already prepared each affected cohort and its evidence. The recommended accountable role reviews the records, makes or authorizes the decision, and records the disposition. It is a recommended business role, not a verified HubSpot owner name.",
        "",
    ])
    lines.extend(_recommendation_summary(recommendation_items, report_findings))
    lines.extend(["", "## What This Audit Cannot Determine", "", _list(_narrative_plain(item) for item in limitations), "", "## Evidence and Supporting Files", ""])
    lines.extend(_evidence_index())
    lines.extend(
        [
            f"- {_link('findings.json', 'Validated findings')}",
            f"- {_link('report_record_evidence.csv', 'Mapped Company and Deal evidence')}",
            f"- {_link('operator_appendix.md', 'Operator appendix')}",
            f"- {_link('schema_discovery_report.md', 'Schema discovery report')}",
            "",
            "## Next Review",
            "",
            _narrative_plain(narrative.suggested_next_review),
            "",
            "## Sharing the Report",
            "",
            "This HTML file is generated locally. It is not a public URL, and its supporting-file links work only when the related output folder stays together.",
            "",
            "**Treat this as a confidential CRM report.** It can contain identifiable HubSpot Company and Deal names plus direct record links. For a fixed copy, choose **Print → Save as PDF**, then share the PDF only with authorized recipients through an approved channel. If you share interactive HTML, keep the complete report package together, use approved access-controlled hosting or file sharing, and never include the raw data folder, environment files, or secrets.",
            "",
            "---",
            "",
            "Smartify Marketing · For more marketing systems insights and updates: [smartifymarketing.com](https://smartifymarketing.com) · [GitHub](https://github.com/AliceEinstein)",
            "",
        ]
    )
    report_path = run_dir / "crm_trust_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    appendix: List[str] = [
        "# CRM Audit Operator Appendix",
        "",
        "## How to Use This Appendix",
        "",
        "Use this file to verify findings, inspect sample sizes, and plan approved implementation work. Record identifiers in evidence files are hashed.",
        "",
        "## All Validated Findings",
        "",
    ]
    for module in MODULES:
        appendix.extend([f"### {module.replace('_', ' ').title()}", ""])
        module_findings = [finding for finding in accepted if finding.module == module]
        appendix.extend(_finding_table(module_findings, property_labels))
        appendix.extend(_representative_record_sections(module_findings, record_groups))
        appendix.append("")
    appendix.extend(["## Detailed Recommendations", ""])
    for category, items in _recommendation_groups(recommendations):
        appendix.extend([f"## {CATEGORY_LABELS[category]}", ""])
        if not items:
            appendix.extend(["None recorded.", ""])
        for item in items:
            appendix.extend(_recommendation_detail(category, item))
    appendix.extend(["## Evidence Index", ""])
    appendix.extend(_evidence_index())
    appendix.extend(
        [
            f"- {_link('evidence.csv', 'Consolidated evidence CSV')}",
            f"- {_link('report_record_evidence.csv', 'Mapped Company and Deal evidence')}",
            f"- {_link('findings.json', 'Validated findings JSON')}",
            f"- {_link('score.json', 'Score calculation')}",
            "",
            "## Schema and Context Files",
            "",
            f"- {_link('crm_context.yaml', 'CRM context map')}",
            f"- {_link('schema_discovery_report.md', 'Schema discovery report')}",
            f"- {_link('business_context.json', 'Business context')}",
            f"- {_link('audit_profile.json', 'Audit profile')}",
            "",
            "## Method and Audit Constraints",
            "",
            _list(_narrative_plain(item) for item in limitations),
            "",
        ]
    )
    appendix_path = run_dir / "operator_appendix.md"
    appendix_path.write_text("\n".join(appendix), encoding="utf-8")

    handoff: List[str] = [
        "# Agent Handoff: CRM Trust Audit Follow-up",
        "",
        "## Safety Boundary",
        "",
        "This audit is read-only. Do not perform CRM write actions, bulk edits, merges, owner changes, lifecycle changes, pipeline changes, or property deletion without an explicit human-approved implementation plan and separately authorized tooling.",
        "",
        "## Approved Low-Risk Follow-ups",
        "",
    ]
    for item in recommendations.safe_operational_actions:
        handoff.extend(_recommendation_detail("safe_operational_actions", item))
    handoff.extend(["## Manual Confirmation Required", ""])
    for item in recommendations.needs_business_rule_confirmation:
        handoff.extend(_recommendation_detail("needs_business_rule_confirmation", item))
    handoff.extend(
        [
            "## Blocked Actions",
            "",
            "- Do not execute CRM writes from this audit output.",
            "- Do not automatically merge companies.",
            "- Do not automatically delete properties.",
            "- Do not automatically reset lifecycle stages.",
            "- Do not automatically bulk-update owners.",
            "",
            "## Suggested Implementation Sequence",
            "",
            "1. Confirm business rules and canonical fields.",
            "2. Review the audit-prepared evidence cohorts with the accountable business owner.",
            "3. Define an approved change plan outside this read-only audit.",
            "4. Re-run the audit after approved changes.",
            "",
            "## Evidence Files",
            "",
        ]
    )
    handoff.extend(_evidence_index())
    handoff.extend(["", "## Questions to Ask Human Owner Before Any Write Action", ""])
    handoff.append(_list((root.confirmation_question for root in narrative.root_causes), "- Which CRM fields and associations are canonical for this business?"))
    handoff.append("")
    handoff_path = run_dir / "agent_handoff.md"
    handoff_path.write_text("\n".join(handoff), encoding="utf-8")

    html_path = _render_html(
        run_dir,
        manifest,
        counts,
        summary,
        activity,
        identity,
        lifecycle,
        associations,
        pipelines,
        score,
        narrative,
        report_findings,
        recommendation_items,
        limitations,
        business_name,
        property_labels,
        record_groups,
    )
    return report_path, html_path, appendix_path, handoff_path
