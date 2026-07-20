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
    "safe_operational_actions": "Owner review",
    "needs_business_rule_confirmation": "Business rule confirmation",
    "do_not_auto_fix": "Explicit approval before a CRM change",
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


def _md(value: Any) -> str:
    return _plain(value).replace("|", "\\|")


def _asset_md(asset_type: str, label: Any) -> str:
    return f"**HubSpot {asset_type}: {_md(label)}**"


def _record_asset_md(asset_type: str, label: Any, url: Any) -> str:
    text = _asset_md(asset_type, label)
    return f"[{text}]({url})" if url else text


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
    words = finding.id.replace("_", " ").split()
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


def _major_findings(findings: List[Finding]) -> List[Finding]:
    return [f for f in _accepted_findings(findings) if f.severity != "low"]


def _recommendation_groups(recommendations: Recommendations) -> List[Tuple[str, List[RecommendationItem]]]:
    return [
        ("safe_operational_actions", recommendations.safe_operational_actions),
        ("needs_business_rule_confirmation", recommendations.needs_business_rule_confirmation),
        ("do_not_auto_fix", recommendations.do_not_auto_fix),
    ]


def _all_recommendations(recommendations: Recommendations) -> List[Tuple[str, RecommendationItem]]:
    return [
        (category, item)
        for category, items in _recommendation_groups(recommendations)
        for item in items
    ]


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
            f"{_md('; '.join(_finding_impacts(finding)))} | {_md(finding.business_impact)} | "
            f"{_link(finding.evidence_file, 'CSV')} · "
            f"{_link('processed/measurements/' + finding.module + '.json', 'measurement')} |"
        )
    if len(lines) == 2:
        lines.append("| No major finding was validated | — | — | — | — | — |")
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
        assets.append(_asset_md("pipeline", row["pipeline_label"]))
    if row.get("deal_stage_label"):
        assets.append(_asset_md("deal stage", row["deal_stage_label"]))
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
        detail = _md(root.confirmation_question)
        if artifacts:
            detail += "<br>" + artifacts
        lines.append(
            f"| {_md(root.hypothesis)} | {_md(', '.join(root.finding_ids))} | "
            f"{root.confidence.title()} | {detail} |"
        )
    if len(lines) == 2:
        lines.append("| No root cause can be stated confidently from the available evidence | — | — | Confirm operating rules with the CRM owner. |")
    return lines


def _recommendation_summary(items: List[Tuple[str, RecommendationItem]]) -> List[str]:
    lines = ["| Finding | Recommended action | Owner | Approval needed | Expected result | Evidence |", "|---|---|---|---|---|---|"]
    for category, item in items:
        lines.append(
            f"| {_md(item.finding_id)} | {_md(item.action)} | {_md(item.decision_owner)} | "
            f"{_md(item.approval_required or CATEGORY_LABELS[category])} | "
            f"{_md(item.expected_outcome)} | {_link(item.evidence_file, 'CSV')} |"
        )
    if len(lines) == 2:
        lines.append("| — | No recommendation was recorded | — | — | — | — |")
    return lines


def _recommendation_detail(category: str, item: RecommendationItem) -> List[str]:
    lines = [
        f"### {_plain(item.finding_id)}",
        "",
        f"- **Action:** {_plain(item.action)}",
        f"- **Why:** {_plain(item.basis)}",
        f"- **Owner:** {_plain(item.decision_owner)}",
        f"- **Approval:** {_plain(item.approval_required or CATEGORY_LABELS[category])}",
    ]
    if item.target:
        lines.append(f"- **Exact scope:** {_plain(item.target)}")
    if item.current_state:
        lines.append(f"- **Current state:** {_plain(item.current_state)}")
    if item.desired_state:
        lines.append(f"- **Desired state:** {_plain(item.desired_state)}")
    if item.implementation_steps:
        lines.extend(["- **Implementation:**"] + [f"  {index}. {_plain(step)}" for index, step in enumerate(item.implementation_steps, 1)])
    lines.append(f"- **Expected result:** {_plain(item.expected_outcome)}")
    if item.success_measure:
        lines.append(f"- **Success measure:** {_plain(item.success_measure)}")
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


def _html_link(path: str, label: str) -> str:
    return f'<a href="{html.escape(path.replace(" ", "%20"), quote=True)}">{html.escape(label)}</a>'


def _asset_html(asset_type: str, label: Any) -> str:
    return (
        '<strong class="hubspot-asset">HubSpot '
        f'{html.escape(asset_type)}: {_html_text(label)}</strong>'
    )


def _record_asset_html(asset_type: str, label: Any, url: Any) -> str:
    content = _asset_html(asset_type, label)
    if not url:
        return content
    return (
        f'<a class="hubspot-record" href="{html.escape(str(url), quote=True)}" '
        f'target="_blank" rel="noopener noreferrer">{content}</a>'
    )


def _property_asset_html(
    object_type: str,
    field: str,
    property_labels: Dict[Tuple[str, str], str],
) -> str:
    label = property_labels.get((object_type, field), field)
    display = f"{label} ({field})" if label != field else field
    return _asset_html("property", display)


def _record_line_html(row: Dict[str, str]) -> str:
    assets: List[str] = []
    if row.get("company_name"):
        assets.append(
            _record_asset_html("Company", row["company_name"], row.get("company_url"))
        )
    if row.get("deal_name"):
        assets.append(_record_asset_html("Deal", row["deal_name"], row.get("deal_url")))
    if row.get("pipeline_label"):
        assets.append(_asset_html("pipeline", row["pipeline_label"]))
    if row.get("deal_stage_label"):
        assets.append(_asset_html("deal stage", row["deal_stage_label"]))
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
        '<div class="record-samples"><strong>Representative HubSpot records</strong>'
        f"<ul>{items}</ul>{remainder}</div>"
    )


def _html_bar(value: float, label_html: str, tone: str = "primary") -> str:
    width = max(0.0, min(float(value), 100.0))
    return (
        f'<div class="metric-row"><div class="metric-label">{label_html}</div>'
        f'<div class="bar"><span class="{tone}" style="width:{width:.1f}%"></span></div>'
        f'<div class="metric-value">{width:.1f}%</div></div>'
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
    major: List[Finding],
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
    completeness = "".join(
        _html_bar(
            fill,
            f"{html.escape(obj.title())} · {_property_asset_html(obj, field, property_labels)}",
            "accent" if fill >= 90 else "warm",
        )
        for obj, field, fill, _total, _present in _completeness_rows(summary, limit=18)
    ) or "<p>Field completeness was not available.</p>"
    validity = "".join(
        _html_bar(
            float(stats.get("valid_format_rate_among_present", 0)),
            _property_asset_html("contacts", field, property_labels),
            "primary",
        )
        for field, stats in (identity.get("fields", {}) or {}).items()
    ) or "<p>Identity format checks were not available.</p>"
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
    findings_html = ""
    for finding in major:
        impacts = ", ".join(_finding_impacts(finding))
        property_context = (
            f'<p class="field-context">{_property_asset_html(finding.object_type, finding.field_name, property_labels)}</p>'
            if finding.field_name
            else ""
        )
        record_context = _representative_record_html(finding, record_groups)
        findings_html += f"""
        <article class="finding severity-{html.escape(finding.severity)}">
          <div class="finding-head"><span class="badge">{html.escape(finding.severity.title())}</span><span>{html.escape(finding.confidence.title())} confidence</span></div>
          <h3>{html.escape(_finding_title(finding))}</h3>
          {property_context}
          <p class="sample">{html.escape(_sample(finding))}</p>
          <p><strong>Decision impact:</strong> {html.escape(impacts)}</p>
          <p>{_html_text(finding.business_impact)}</p>
          {record_context}
          <p>{_html_link(finding.evidence_file, "Evidence CSV")} · {_html_link('processed/measurements/' + finding.module + '.json', "Measurement")}</p>
        </article>"""
    if not findings_html:
        findings_html = '<p class="empty">No major finding was validated.</p>'
    roots_html = "".join(
        f'<tr><td>{_html_text(root.hypothesis)}</td><td>{html.escape(", ".join(root.finding_ids))}</td><td>{html.escape(root.confidence.title())}</td><td>{_html_text(root.confirmation_question)}</td></tr>'
        for root in narrative.root_causes
    ) or '<tr><td colspan="4">No root cause can be stated confidently from the available evidence.</td></tr>'
    recs_html = ""
    for category, item in recommendation_items:
        recs_html += f"""
        <article class="recommendation">
          <div class="eyebrow">{html.escape(item.finding_id)}</div>
          <h3>{_html_text(item.action)}</h3>
          <div class="rec-grid">
            <p><strong>Why</strong><br>{_html_text(item.basis)}</p>
            <p><strong>Owner</strong><br>{_html_text(item.decision_owner)}</p>
            <p><strong>Approval</strong><br>{_html_text(item.approval_required or CATEGORY_LABELS[category])}</p>
            <p><strong>Expected result</strong><br>{_html_text(item.expected_outcome)}</p>
          </div>
          <p>{_html_link(item.evidence_file, "Evidence CSV")} · {_html_link('operator_appendix.md', "Implementation detail")}</p>
        </article>"""
    if not recs_html:
        recs_html = '<p class="empty">No recommendation was recorded.</p>'
    evidence_html = "".join(
        f'<li><strong>{html.escape(module.replace("_", " ").title())}</strong>: {_html_link("evidence/" + module + ".csv", "CSV")} · {_html_link("processed/measurements/" + module + ".json", "measurement")}</li>'
        for module in MODULES
    )
    limitation_html = "".join(f"<li>{_html_text(item)}</li>" for item in limitations)
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
    a{{color:var(--primary);font-weight:700;text-decoration-color:rgba(150,73,0,.28);text-underline-offset:3px}} a:hover{{color:var(--accent);text-decoration-color:rgba(254,129,14,.42)}} a:focus-visible{{outline:3px solid var(--accent);outline-offset:3px}} .page{{max-width:1200px;margin:0 auto;background:var(--canvas);box-shadow:0 20px 60px rgba(31,27,24,.07)}}
    header{{padding:64px 72px 52px;background:radial-gradient(110% 150% at 82% 20%,rgba(150,73,0,.48),transparent 55%),var(--dark);color:var(--dark-text)}} .brand{{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:800}}
    h1,h2,h3{{font-family:"Newsreader",Georgia,"Times New Roman",serif}} h1{{font-size:44px;line-height:1.04;max-width:850px;margin:16px 0 20px;letter-spacing:-.025em}} .subtitle{{max-width:780px;color:#fffaf5;font-size:18px}} .meta{{display:flex;gap:24px;flex-wrap:wrap;margin-top:28px;color:#eadfd6;font-size:13px}}
    main{{padding:0 72px 72px}} section{{padding:50px 0;border-bottom:1px solid var(--line)}} section:last-child{{border:0}} h2{{font-size:32px;line-height:1.15;letter-spacing:-.02em;margin:0 0 12px}} h3{{font-size:20px;line-height:1.25}} .lede{{max-width:850px;color:var(--muted);font-size:17px}}
    .kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:26px 0}} .kpi{{background:rgba(255,255,255,.78);padding:18px;border-radius:14px;border:1px solid rgba(31,27,24,.08);box-shadow:0 16px 34px rgba(31,27,24,.035)}} .kpi span{{display:block;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}} .kpi strong{{display:block;font-family:"Newsreader",Georgia,serif;font-size:29px;margin-top:7px}}
    .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:40px}} .panel{{background:rgba(247,240,234,.8);border:1px solid rgba(31,27,24,.08);border-radius:20px;padding:24px}} .panel h3{{margin-top:0}}
    .metric-row{{display:grid;grid-template-columns:minmax(140px,1.35fr) 2fr 58px;gap:12px;align-items:center;margin:10px 0}} .metric-label{{font-size:13px;overflow-wrap:anywhere}} .metric-value{{font-variant-numeric:tabular-nums;text-align:right;font-size:13px;font-weight:700}} .hubspot-asset{{font-weight:800;color:var(--ink)}} .hubspot-record{{font-weight:inherit;text-decoration-thickness:1px}}
    .bar,.stack{{height:10px;background:#e8ded5;border-radius:999px;overflow:hidden;display:flex}} .bar span,.stack span{{display:block;height:100%}} .primary{{background:var(--primary)}} .accent{{background:var(--accent)}} .warm{{background:var(--warm)}} .error{{background:var(--error)}}
    .stack-row{{margin:18px 0}} .stack-row strong{{display:block;margin-bottom:7px}} .stack-row small{{display:block;color:var(--muted);margin-top:6px}}
    table{{width:100%;border-collapse:collapse;margin-top:20px}} th,td{{text-align:left;padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:top}} th{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em}}
    .findings{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-top:24px}} .finding{{background:rgba(255,255,255,.62);border:1px solid var(--line);border-left:5px solid var(--accent);border-radius:14px;padding:22px;min-width:0}} .finding.severity-critical,.finding.severity-high{{border-left-color:var(--error)}} .finding h3{{margin:12px 0 6px}} .finding p{{margin:8px 0}} .finding-head{{display:flex;justify-content:space-between;color:var(--muted);font-size:12px}} .badge{{font-weight:800;color:var(--ink);text-transform:uppercase;letter-spacing:.05em}} .sample{{font-size:20px;font-weight:800;color:var(--primary)}} .field-context{{font-size:13px;color:var(--muted)}} .record-samples{{margin:15px 0;padding:14px 15px;background:var(--wash);border-radius:10px;border:1px solid var(--line)}} .record-samples>strong{{display:block;margin-bottom:7px}} .record-samples ul{{margin:0;padding-left:19px}} .record-samples li{{margin:7px 0;overflow-wrap:anywhere}} .record-more{{color:var(--muted);font-size:13px}}
    .recommendation{{border-top:3px solid var(--primary);background:rgba(247,240,234,.8);padding:24px;border-radius:8px 8px 20px 20px;margin:18px 0}} .recommendation h3{{font-size:20px;margin:7px 0 18px}} .eyebrow{{font-size:12px;color:var(--primary);font-weight:800;text-transform:uppercase;letter-spacing:.06em}} .rec-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:2px 28px}} .rec-grid p{{margin:8px 0}}
    .note{{background:var(--blush);border-left:4px solid var(--primary);padding:16px 18px;border-radius:10px}} .footer-note{{color:var(--muted);font-size:13px}} ul{{padding-left:20px}} .report-footer{{padding:34px 72px;background:var(--dark);color:var(--dark-text);display:flex;justify-content:space-between;gap:24px;align-items:center}} .report-footer p{{margin:0}} .report-footer a{{color:var(--accent);text-decoration-color:rgba(254,129,14,.45)}}
    @media(max-width:820px){{header,main,.report-footer{{padding-left:28px;padding-right:28px}} h1{{font-size:34px}} .kpis{{grid-template-columns:repeat(2,1fr)}} .two-col,.findings,.rec-grid{{grid-template-columns:1fr}} .report-footer{{align-items:flex-start;flex-direction:column}}}}
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
    <section id="summary"><h2>Executive Summary</h2><p class="lede">{_html_text(narrative.executive_summary)}</p><p><strong>CRM trust score: {html.escape(str(score.get('total', '—')))}/{html.escape(str(score.get('max_total', 100)))}.</strong> The score summarizes reviewed data-quality findings; it does not measure revenue performance or return on investment.</p><p>{_html_link('crm_trust_report.md', 'Text version')} · {_html_link('operator_appendix.md', 'Operator appendix')}</p></section>
    <section id="snapshot"><h2>CRM Snapshot</h2><p class="lede">{html.escape(mode)} extract completed {html.escape(generated)}. Counts and extraction coverage are taken from the completed snapshot manifest.</p><div class="kpis">{card_html}</div></section>
    <section id="quality"><h2>Data Quality and Usability</h2><p class="lede">{_html_text(narrative.data_quality_summary)}</p><div class="two-col"><div class="panel"><h3>Field completeness</h3>{completeness}</div><div class="panel"><h3>Contact identity validity</h3>{validity}</div></div></section>
    <section id="activity"><h2>Activity and Data Age</h2><p class="lede">Updated within 30 days, active within 31–90 days, aging within 91–180 days, and stale after 180 days. These bands use record modification dates.</p>{activity_rows}</section>
    <section id="funnel"><h2>Funnel and Association Coverage</h2><div class="two-col"><div class="panel"><h3>Contact lifecycle distribution</h3>{funnel_rows or '<p>Lifecycle distribution was not available.</p>'}</div><div class="panel"><h3>Association coverage</h3>{association_rows}</div></div><h3>Deal pipelines</h3><table><thead><tr><th>Pipeline</th><th>Stages</th><th>Deals</th></tr></thead><tbody>{pipeline_rows}</tbody></table></section>
    <section id="findings"><h2>Key Findings</h2><p class="lede">Every finding below has passed review and links to its record-level evidence and measurement file.</p><div class="findings">{findings_html}</div></section>
    <section id="causes"><h2>Root Cause Hypotheses</h2><p class="lede">These are evidence-based hypotheses, not confirmed facts. Confidence and the question needed for confirmation are shown explicitly.</p><table><thead><tr><th>Hypothesis</th><th>Findings</th><th>Confidence</th><th>What to confirm</th></tr></thead><tbody>{roots_html}</tbody></table></section>
    <section id="actions"><h2>Recommended Actions</h2><p class="lede">Each action states why it is needed, who should own it, what approval is required, and the expected result. Exact implementation detail is in the appendix.</p>{recs_html}</section>
    <section id="limits"><h2>What This Audit Cannot Determine</h2><ul>{limitation_html}</ul></section>
    <section id="evidence"><h2>Evidence and Supporting Files</h2><p class="note">The main report shows decision-relevant evidence. The operator appendix contains every validated finding, detailed actions, and links to supporting artifacts.</p><ul>{evidence_html}<li>{_html_link('report_record_evidence.csv', 'Mapped Company and Deal evidence')}</li><li>{_html_link('findings.json', 'Validated findings')}</li><li>{_html_link('operator_appendix.md', 'Operator appendix')}</li><li>{_html_link('schema_discovery_report.md', 'Schema discovery report')}</li></ul></section>
    <section id="next"><h2>Next Review</h2><p class="lede">{_html_text(narrative.suggested_next_review)}</p></section>
    <section id="sharing"><h2>Sharing the Report</h2><p class="lede">This HTML file is generated locally. It is not a public URL, and its supporting-file links work only when the related output folder stays together.</p><p>For a fixed copy, open the HTML in a browser and choose <strong>Print → Save as PDF</strong>. Share the PDF through an approved channel. If you share HTML instead, share the complete sanitized output package through approved hosting or file sharing; do not share the raw data folder.</p><p class="footer-note">The HTML and Markdown versions are generated from the same validated artifacts.</p></section>
  </main>
  <footer class="report-footer"><p><strong>Smartify Marketing</strong><br>Your Strategic B2B Marketing Partner</p><p>For more marketing systems insights and updates: <a href="https://smartifymarketing.com">smartifymarketing.com</a> · <a href="https://github.com/AliceEinstein">GitHub</a></p></footer>
</div></body></html>"""
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
    major = _major_findings(findings)
    record_rows, property_labels = build_report_record_evidence(run_dir, accepted)
    record_groups = _records_by_finding(record_rows)
    identity_info = report_identity(run_dir)
    business_name = str(identity_info.get("business_name") or "")
    report_title = (
        f"{business_name} CRM Trust Audit"
        if business_name
        else "HubSpot Marketing-to-Pipeline Trust Audit"
    )
    recommendation_items = _all_recommendations(recommendations)
    record_counts = {**counts, **summary.get("record_counts", {})}
    limitations = _automatic_limitations(manifest) + narrative.limitations

    lines: List[str] = [
        f"# {report_title}",
        "",
        "*HubSpot Marketing-to-Pipeline Trust Audit*",
        "",
        "## Executive Summary",
        "",
        _plain(narrative.executive_summary),
        "",
        f"**CRM trust score: {score.get('total', '—')}/{score.get('max_total', 100)}.** ",
        "The score summarizes the reviewed data-quality findings. It is not a measure of revenue performance or return on investment.",
        "",
        "No CRM records were changed during this audit.",
        "",
        "## CRM Snapshot",
        "",
    ]
    lines.extend(_snapshot_table(manifest, record_counts))
    lines.extend(
        [
            "",
            f"- Snapshot completed: {_plain(manifest.get('snapshot_completed_at'))}",
            f"- Coverage: {'Full history' if manifest.get('full_history') else 'Selected time window'}",
            "",
            "## Data Quality and Usability",
            "",
            _plain(narrative.data_quality_summary),
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
    lines.extend(["", "## Key Findings", "", "The following findings are material to management decisions and have passed the audit review gates.", ""])
    lines.extend(_finding_table(major, property_labels))
    representative_sections = _representative_record_sections(major, record_groups)
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
    lines.extend(["", "## Recommended Actions", "", "Actions are linked to the finding and evidence that justify them. Detailed implementation steps are in the operator appendix.", ""])
    lines.extend(_recommendation_summary(recommendation_items))
    lines.extend(["", "## What This Audit Cannot Determine", "", _list(limitations), "", "## Evidence and Supporting Files", ""])
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
            _plain(narrative.suggested_next_review),
            "",
            "## Sharing the Report",
            "",
            "This HTML file is generated locally. It is not a public URL, and its supporting-file links work only when the related output folder stays together.",
            "",
            "For a fixed copy, open the HTML in a browser and choose **Print → Save as PDF**. Share the PDF through an approved channel. If you share HTML instead, share the complete sanitized output package through approved hosting or file sharing; do not share the raw data folder.",
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
            _list(limitations),
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
            "2. Review the linked evidence queues with the CRM owner.",
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
        major,
        recommendation_items,
        limitations,
        business_name,
        property_labels,
        record_groups,
    )
    return report_path, html_path, appendix_path, handoff_path
