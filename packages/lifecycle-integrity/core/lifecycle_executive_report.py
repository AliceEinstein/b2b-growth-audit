"""Render the scalable, business-facing lifecycle integrity report.

The executive report is intentionally problem-group first.  Local evidence
files retain every sanitized record; the page itself explains the size,
commercial meaning, root-cause evidence, and action for each affected group.
"""
from __future__ import annotations

import html
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from .lifecycle_cohorts import UNRESOLVED_ACCOUNT
from .lifecycle_human_report import BRAND_NAME, CREDIT_URL, DO_NOT_AUTOMATE, GITHUB_URL, SLOGAN, humanize


def _h(value: Any) -> str:
    return html.escape("—" if value in (None, "") else str(value))


def _asset_html(value: Any) -> str:
    """Escape prose and visually identify named HubSpot assets."""
    text = _h(value)
    text = re.sub(
        r"Workflow: ([^;<]*?\(WF-\d+\))",
        lambda match: f"<strong class='hubspot-asset'>Workflow: {match.group(1)}</strong>",
        text,
    )
    text = re.sub(
        r"HubSpot form: ([^;<]+?) submitted",
        lambda match: f"<strong class='hubspot-asset'>HubSpot form: {match.group(1)}</strong> submitted",
        text,
    )
    return re.sub(
        r"HubSpot property: ([^,;.]+)",
        lambda match: f"<strong class='hubspot-asset'>HubSpot property: {match.group(1)}</strong>",
        text,
    )


def _md(value: Any) -> str:
    return str("—" if value in (None, "") else value).replace("|", "\\|").replace("\n", " ")


def _asset_md(value: Any) -> str:
    text = _md(value)
    text = re.sub(r"Workflow: ([^;]*?\(WF-\d+\))", r"**Workflow: \1**", text)
    text = re.sub(r"HubSpot form: ([^;]+?) submitted", r"**HubSpot form: \1** submitted", text)
    return re.sub(r"HubSpot property: ([^,;.]+)", r"**HubSpot property: \1**", text)


def _items(value: Any) -> list[str]:
    return [row.strip() for row in str(value or "").split("||") if row.strip()]


def _first(value: Any, fallback: str = "—") -> str:
    rows = _items(value)
    return rows[0] if rows else fallback


def _count(value: Any, singular: str) -> str:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        number = 0
    return f"{number} {singular if number == 1 else singular + 's'}"


def _has(value: Any) -> str:
    try:
        return "has" if int(value or 0) == 1 else "have"
    except (TypeError, ValueError):
        return "have"


def _business(view: dict[str, Any]) -> str:
    value = str(view.get("business_name") or "").strip()
    return value or "Your business"


def _title(view: dict[str, Any]) -> str:
    name = str(view.get("business_name") or "").strip()
    return f"{name} Lifecycle Integrity Audit" if name else "Lifecycle Integrity Audit"


def _score_status(score: dict[str, Any]) -> str:
    overall = int(score.get("overall_lifecycle_integrity_score", 0) or 0)
    if overall >= 90:
        return "Strong control coverage with named gaps to close"
    if overall >= 70:
        return "Material gaps are reducing journey performance"
    return "Immediate lifecycle intervention is required"


def _score_lines(score: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for link_id, row in (score.get("journey_link_scores") or {}).items():
        retained = row.get("score")
        deducted = row.get("deducted")
        status = str(row.get("status") or "")
        if status == "confirmed break":
            reading = "Confirmed break"
        elif "review candidate" in status:
            reading = "Under review"
        elif "outside score" in status:
            reading = "Shown separately"
        elif status == "not_assessable":
            reading = "Not assessed"
        else:
            reading = "No affected population found"
        rows.append({
            "id": link_id,
            "label": row.get("label") or humanize(link_id),
            "retained": retained,
            "weight": row.get("weight"),
            "deducted": deducted,
            "reading": reading,
        })
    return rows


def _score_formula(score: dict[str, Any]) -> str:
    baseline = score.get("score_baseline", 100)
    deducted = score.get("total_deducted", 0)
    unrounded = score.get("unrounded_score", score.get("overall_lifecycle_integrity_score", 0))
    overall = score.get("overall_lifecycle_integrity_score", 0)
    return f"{baseline:g} baseline − {deducted:g} total deductions = {unrounded:g}; displayed as {overall}/100 after rounding"


def _amount_text(view: dict[str, Any]) -> str:
    exposure = view.get("pipeline_exposure", {}) or {}
    amounts = exposure.get("actual_open_deal_amount_by_currency") or {}
    values = []
    for currency, amount in sorted(amounts.items()):
        if currency in {"portal_default", "currency_unavailable", ""}:
            continue
        try:
            values.append(f"{str(currency).upper()} {Decimal(str(amount)):,.2f}")
        except (InvalidOperation, ValueError):
            continue
    return " · ".join(values) or "Amount unavailable"


def _summary(view: dict[str, Any]) -> dict[str, Any]:
    exposure = view.get("pipeline_exposure", {}) or {}
    lanes = (view.get("recovery_routing", {}) or {}).get("lanes", {}) or {}
    predeal = lanes.get("missing_deal_predeal_recovery", {}) or {}
    closed = lanes.get("closed_lost_recovery", {}) or {}
    cohorts = view.get("account_cohorts", []) or []
    return {
        "accounts": len({name for cohort in cohorts for name in cohort.get("account_names", []) if name != UNRESOLVED_ACCOUNT}),
        "predeal_contacts": predeal.get("count", exposure.get("potential_recoverable_pipeline_population", 0)),
        "open_deals": exposure.get("unique_open_deals_with_leakage_signals", 0),
        "open_amount": _amount_text(view),
        "closed_lost": closed.get("count", exposure.get("closed_lost_recovery_opportunities", 0)),
    }


def _motion_rows(view: dict[str, Any]) -> list[dict[str, Any]]:
    labels = {
        "inbound_new_business": "Inbound new business",
        "outbound_sales_led": "Outbound sales-led",
        "abm_account_based": "ABM / account-based",
        "partner_led": "Partner-led",
        "expansion_renewal": "Expansion / renewal",
    }
    rows = []
    counts = view.get("assignment_counts_by_object", {}) or {}
    for key, label in labels.items():
        pattern = view.get("patterns", {}).get(key)
        if pattern is None or not pattern.exists:
            continue
        rows.append({
            "motion": label,
            "confidence": getattr(pattern, "confidence_score", "—"),
            "contacts": counts.get("high_intent_contacts", {}).get(key, 0),
            "deals": counts.get("deals", {}).get(key, 0),
        })
    return rows


def _cohort_metrics(cohort: dict[str, Any]) -> list[tuple[str, Any]]:
    key = str(cohort.get("cohort_id") or "")
    metrics: list[tuple[str, Any]] = [
        ("Named accounts", _count(cohort.get("account_count"), "account")),
        ("Contacts affected", _count(cohort.get("contact_count"), "contact")),
    ]
    if cohort.get("unresolved_account_relationships"):
        metrics.append(("Account links to resolve", _count(cohort.get("unresolved_account_relationships"), "link")))
    if key.startswith("pre_deal"):
        metrics.extend([
            ("Contacts without an owner", _count(cohort.get("unowned_contacts"), "contact")),
            ("Affected accounts with open deals", _count(cohort.get("open_deal_accounts"), "account")),
            ("Amount shown", "No amount assigned"),
        ])
    elif key == "closed_lost_recovery":
        metrics.extend([
            ("Deals to re-qualify", _count(cohort.get("deal_count"), "deal")),
            ("Amount shown", "Historical context only"),
        ])
    else:
        metrics.extend([
            ("Deals affected", _count(cohort.get("deal_count"), "deal")),
            ("Actual deal amount", cohort.get("amount") or "Amount unavailable"),
        ])
    return metrics


def _cohort_root_cause(cohort: dict[str, Any]) -> list[str]:
    rows = cohort.get("sample_rows", []) or []
    statements: list[str] = []
    for row in rows:
        statements.extend(_items(row.get("automation_evidence")))
    return list(dict.fromkeys(statements))[:3]


def _sample_label(row: dict[str, Any]) -> str:
    account = str(row.get("account_name") or "Account unavailable")
    if row.get("record_type") == "Deal":
        return f"{account} — {row.get('deal_name') or 'Unnamed deal'}"
    return f"{account} — {row.get('contact_name') or row.get('record_reference') or 'Contact'}"


def _record_assets(row: dict[str, Any]) -> list[tuple[str, str]]:
    values = [
        (str(row.get("account_name") or ""), str(row.get("account_url") or "")),
        (str(row.get("deal_name") or ""), str(row.get("deal_url") or "")),
        (str(row.get("contact_name") or ""), str(row.get("contact_url") or "")),
    ]
    ignored = {"", "No deal created", "Account unavailable", "No company association found"}
    return sorted(
        {(label, url) for label, url in values if label not in ignored},
        key=lambda item: -len(item[0]),
    )


def _linkified_html(value: Any, rows: Iterable[dict[str, Any]]) -> str:
    result = _asset_html(value)
    seen: set[str] = set()
    for row in rows:
        for label, url in _record_assets(row):
            if label in seen:
                continue
            seen.add(label)
            escaped = _h(label)
            replacement = f"<strong class='hubspot-asset'>{escaped}</strong>"
            if url:
                replacement = (
                    f"<a class='hubspot-record' href='{_h(url)}' target='_blank' "
                    f"rel='noopener noreferrer'>{replacement}</a>"
                )
            result = result.replace(escaped, replacement)
    return result


def _linkified_md(value: Any, rows: Iterable[dict[str, Any]]) -> str:
    result = _asset_md(value)
    seen: set[str] = set()
    for row in rows:
        for label, url in _record_assets(row):
            if label in seen:
                continue
            seen.add(label)
            replacement = f"**{_md(label)}**"
            if url:
                replacement = f"[**{_md(label)}**]({url})"
            result = result.replace(_md(label), replacement)
    return result


def _sample_label_html(row: dict[str, Any]) -> str:
    account = str(row.get("account_name") or "Account unavailable")
    record = str(
        row.get("deal_name")
        if row.get("record_type") == "Deal"
        else row.get("contact_name") or row.get("record_reference") or "Record"
    )
    return f"{_linkified_html(account, [row])} — {_linkified_html(record, [row])}"


def _sample_label_md(row: dict[str, Any]) -> str:
    account = str(row.get("account_name") or "Account unavailable")
    record = str(
        row.get("deal_name")
        if row.get("record_type") == "Deal"
        else row.get("contact_name") or row.get("record_reference") or "Record"
    )
    return f"{_linkified_md(account, [row])} — {_linkified_md(record, [row])}"


def _sample_rows(cohort: dict[str, Any]) -> list[dict[str, Any]]:
    return cohort.get("sample_rows", []) or []


def _cohort_md(cohort: dict[str, Any]) -> list[str]:
    rows = _sample_rows(cohort)
    metrics = " · ".join(f"**{_md(label)}:** {_md(value)}" for label, value in _cohort_metrics(cohort))
    lines = [
        f"### {_md(cohort.get('title'))}",
        "",
        f"**{_md(cohort.get('status'))}** · {_md(metrics)}",
        "",
        f"**What we found:** {_md(cohort.get('pattern'))}",
        "",
        "**Evidence pattern:**",
    ]
    lines.extend(f"- {_linkified_md(item, rows)}" for item in cohort.get("evidence_basis", []) or ["No representative evidence was available."])
    lines.extend(["", "**Why it matters:**"])
    if str(cohort.get("cohort_id", "")).startswith("pre_deal"):
        lines.append("- These are recoverable demand signals, not booked pipeline. No amount is assigned without an existing deal.")
    elif cohort.get("cohort_id") == "closed_lost_recovery":
        lines.append("- This is a re-qualification opportunity. Historical deal amount is context only and stays outside the score and open pipeline.")
    else:
        lines.append(f"- {_md(cohort.get('amount'))} is actual deal amount exposed for review, not a loss forecast.")
    lines.extend(["", "**Account-level reading:**"])
    if cohort.get("unresolved_account_relationships"):
        lines.append(f"- {_count(cohort.get('unresolved_account_relationships'), 'affected record')} cannot be rolled up to a named account because the HubSpot company association is missing or unavailable in this snapshot.")
    else:
        lines.append(f"- {_count(cohort.get('account_count'), 'account')} affected; {_count(cohort.get('multiple_contact_accounts'), 'account')} {_has(cohort.get('multiple_contact_accounts'))} more than one associated contact in the available snapshot.")
    if str(cohort.get("cohort_id", "")).startswith("pre_deal") and cohort.get("open_deal_accounts"):
        lines.append(f"- {_count(cohort.get('open_deal_accounts'), 'affected account')} already {_has(cohort.get('open_deal_accounts'))} an open deal. Check whether the named contact belongs in an existing buying group or is a valid no-deal exception.")
    elif cohort.get("no_open_deal_accounts"):
        lines.append(f"- {_count(cohort.get('no_open_deal_accounts'), 'account')} of these accounts have no open deal visible.")
    pipelines = cohort.get("pipelines", []) or []
    if pipelines:
        pipeline_text = ", ".join(
            f"**Pipeline: {_md(item['label'])}** ({item['count']})"
            for item in pipelines[:4]
        )
        lines.append(f"- HubSpot pipelines represented: {pipeline_text}.")
    lines.extend(["", "**Root-cause evidence:**"])
    lines.extend(f"- {_linkified_md(item, rows)}" for item in (_cohort_root_cause(cohort) or ["The available workflow data does not support a specific configuration cause."]))
    lines.extend(["", f"**Recommended action:** {_md(cohort.get('action'))}", "", "**Representative cases:**", "", "| Account / record | Evidence | Actual break | First action |", "|---|---|---|---|"])
    for row in rows:
        lines.append(
            f"| {_sample_label_md(row)} | {_linkified_md(_first(row.get('why_this_record')), [row])} | {_linkified_md(_first(row.get('observed_break')), [row])} | {_linkified_md(_first(row.get('recommended_action')), [row])} |"
        )
    if not rows:
        lines.append("| — | No representative record available | — | Review the evidence file |")
    lines.extend(["", f"Full population: {_count(cohort.get('all_record_count'), 'record')} in [report_record_evidence.csv](report_record_evidence.csv); account aggregation in [report_account_evidence.csv](report_account_evidence.csv).", ""])
    return lines


def render_markdown(view: dict[str, Any]) -> str:
    score = view["score"]
    business = _business(view)
    summary = _summary(view)
    cohorts = view.get("account_cohorts", []) or []
    lines = [
        f"# {_md(_title(view))}",
        "",
        f"Audit date: {_md(view.get('generated'))} · Scope: {_md(view.get('window'))} · Based on HubSpot evidence · Read-only · **Confidential — internal use only**",
        "",
        "## 1. Executive Verdict",
        "",
        f"### Overall Lifecycle Integrity Score: {_md(score.get('overall_lifecycle_integrity_score'))}/100 — {_md(_score_status(score))}",
        "",
        "The score starts at 100 and measures whether the observed handoffs in the selling journey are protected. It is not a conversion rate, CRM hygiene score, or estimate of lost revenue.",
        "",
        f"**Score calculation:** `{_md(_score_formula(score))}`",
        "",
        "| Handoff | Points kept | Points deducted | What the result means |",
        "|---|---:|---:|---|",
    ]
    for row in _score_lines(score):
        retained = "Not assessed" if row["retained"] is None else f"{row['retained']}/{row['weight']}"
        deducted = "—" if row["deducted"] is None else f"−{row['deducted']:g}"
        lines.append(f"| {_md(row['label'])} | {_md(retained)} | {_md(deducted)} | {_md(row['reading'])} |")
    lines.extend([
        "",
        f"The current snapshot contains {_count(summary['accounts'], 'account')} represented in named leakage groups, {_count(summary['predeal_contacts'], 'high-intent contact')} with no visible deal path, {_count(summary['open_deals'], 'open deal')} representing **{_md(summary['open_amount'])}**, and {_count(summary['closed_lost'], 'closed-lost deal')} to re-qualify. Contacts and accounts without deals are never assigned an amount.",
        "",
        "## 2. How " + _md(business) + " Sells",
        "",
        f"The available evidence points to a **{_md(humanize(view['registry'].primary_model))}** selling model. The model classification is separate from the integrity score: it tells us how demand appears to move through {business}, not whether the movement is healthy.",
        "",
        "**Observed path:** Buyer signal → accountable owner → deal or documented valid skip → next sales action → won, lost, renewal, or expansion.",
        "",
        "| Selling motion | Evidence confidence | Contacts | Deals |",
        "|---|---:|---:|---:|",
    ])
    motions = _motion_rows(view)
    for row in motions:
        lines.append(f"| {_md(row['motion'])} | {_md(row['confidence'])}/100 | {_md(row['contacts'])} | {_md(row['deals'])} |")
    if not motions:
        lines.append("| No motion reached the evidence threshold | — | — | — |")
    lines.extend(["", "## 3. Where the Journey Breaks by Account, Contact, and Deal", "", "The groups below are ordered from the first missed handoff to downstream recovery. Each group shows its scale, the evidence behind the conclusion, its account-level meaning, and a small set of representative cases. The complete population remains in the linked evidence files.", ""])
    if cohorts:
        for cohort in cohorts:
            lines.extend(_cohort_md(cohort))
    else:
        lines.extend(["No named leakage group was found in the available evidence.", ""])
    lines.extend([
        "## 4. Action Queue",
        "",
        "Work the queue in journey order. The queue is grouped so a team can fix a process or control once and then re-check the full affected population.",
        "",
        "| Order | Problem group | Named accounts | Unresolved account links | Contacts | Deals / amount | First action |",
        "|---:|---|---:|---:|---:|---|---|",
    ])
    for index, cohort in enumerate(cohorts, 1):
        lines.append(f"| {index} | {_md(cohort['title'])} | {cohort['account_count']} | {cohort.get('unresolved_account_relationships', 0)} | {cohort['contact_count']} | {cohort['deal_count']} / {_md(cohort['amount'])} | {_md(cohort['action'])} |")
    if not cohorts:
        lines.append("| — | No action population | — | — | — | — | Continue monitoring |")
    lines.extend([
        "",
        "## 5. Why These Breaks Exist",
        "",
        "Automation data is used as root-cause evidence only when the workflow or scoring configuration is actually present in the local snapshot. A workflow name is never invented, and configuration presence does not prove that a specific record enrolled or failed.",
        "",
    ])
    causes = []
    for cohort in cohorts:
        for item in _cohort_root_cause(cohort):
            causes.append((cohort["title"], item))
    if causes:
        for cause_title, statement in list(dict.fromkeys(causes)):
            cohort = next((row for row in cohorts if row.get("title") == cause_title), {})
            lines.append(
                f"- **{_md(cause_title)}:** "
                f"{_linkified_md(statement, _sample_rows(cohort))}"
            )
    else:
        lines.append("- No specific workflow or scoring cause was supported by the available configuration evidence.")
    lines.extend([
        "",
        "## 6. 30-Day Recovery Plan",
        "",
        "| Timing | Owner | Action | Success measure |",
        "|---|---|---|---|",
    ])
    for cohort in cohorts:
        lines.append(f"| Days 1–5 | Sales leadership + RevOps | {_md(cohort['action'])} | All {_count(cohort['all_record_count'], 'record')} receive a documented resolution or valid exception |")
    lines.append("| Week 4 | RevOps + revenue leadership | Re-run the audit and compare the same problem groups and named evidence files. | Resolved groups shrink without new downstream breaks. |")
    lines.extend(["", "### Actions That Should Not Be Automated", "", *[f"- {item}" for item in DO_NOT_AUTOMATE], "", "## 7. Monitor and Verify", "", f"Track the same groups on the next run: {_count(summary['predeal_contacts'], 'high-intent contact')} without a deal path, {_count(summary['open_deals'], 'open deal')} representing {_md(summary['open_amount'])}, and {_count(summary['closed_lost'], 'closed-lost deal')} selected for re-qualification. Keep the actual amount boundary unchanged: no deal, no amount.", "", "Re-run after approved ownership, association, routing, workflow, scoring, or deal-creation changes. Compare [report_account_evidence.csv](report_account_evidence.csv) and [report_record_evidence.csv](report_record_evidence.csv).", "", "---", f"{BRAND_NAME} · {SLOGAN}", f"Website: {CREDIT_URL}", f"GitHub: {GITHUB_URL}"])
    return "\n".join(lines) + "\n"


def _metric_html(cohort: dict[str, Any]) -> str:
    return "".join(f"<div class='metric'><span>{_h(label)}</span><strong>{_h(value)}</strong></div>" for label, value in _cohort_metrics(cohort))


def _sample_html(row: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{_sample_label_html(row)}<br><small>{_h(row.get('record_reference'))}</small></td>"
        f"<td>{_linkified_html(_first(row.get('why_this_record')), [row])}</td>"
        f"<td>{_linkified_html(_first(row.get('observed_break')), [row])}</td>"
        f"<td>{_linkified_html(_first(row.get('recommended_action')), [row])}</td>"
        "</tr>"
    )


def _cohort_html(cohort: dict[str, Any]) -> str:
    status = "opportunity" if cohort.get("status") == "Recovery opportunity" else "break"
    rows = _sample_rows(cohort)
    evidence = "".join(f"<li>{_linkified_html(item, rows)}</li>" for item in cohort.get("evidence_basis", []) or ["No representative evidence was available."])
    root = "".join(f"<li>{_linkified_html(item, rows)}</li>" for item in (_cohort_root_cause(cohort) or ["The available workflow data does not support a specific configuration cause."]))
    if str(cohort.get("cohort_id", "")).startswith("pre_deal"):
        meaning = "Recoverable demand, not booked pipeline. No amount is assigned without an existing deal."
    elif cohort.get("cohort_id") == "closed_lost_recovery":
        meaning = "Re-qualification opportunity. Historical deal amount is context only and stays outside the score and open pipeline."
    else:
        meaning = f"{cohort.get('amount') or 'Actual deal amount unavailable'} is actual deal amount exposed for review, not a loss forecast."
    samples = "".join(_sample_html(row) for row in rows) or "<tr><td colspan='4'>No representative record available.</td></tr>"
    pipelines = ", ".join(
        f"<strong class='hubspot-asset'>Pipeline: {_h(item['label'])}</strong> ({item['count']})"
        for item in cohort.get("pipelines", [])[:4]
    ) or "No deal pipeline"
    if str(cohort.get("cohort_id", "")).startswith("pre_deal") and cohort.get("open_deal_accounts"):
        account_reading = f"{_count(cohort.get('open_deal_accounts'), 'affected account')} already {_has(cohort.get('open_deal_accounts'))} an open deal; check whether the named contact belongs in an existing buying group or is a valid no-deal exception."
    elif cohort.get("unresolved_account_relationships"):
        account_reading = f"{_count(cohort.get('unresolved_account_relationships'), 'record')} cannot be rolled up to a named account because the HubSpot company association is missing or unavailable in this snapshot."
    else:
        account_reading = f"{_count(cohort.get('account_count'), 'account')} affected; {_count(cohort.get('multiple_contact_accounts'), 'account')} {_has(cohort.get('multiple_contact_accounts'))} more than one associated contact. {_count(cohort.get('no_open_deal_accounts'), 'account')} {_has(cohort.get('no_open_deal_accounts'))} no open deal visible."
    return f"""
<article class='problem-group {status}'>
  <div class='group-header'><div><span class='status'>{_h(cohort.get('status'))}</span><h3>{_h(cohort.get('title'))}</h3></div><span class='group-count'>{_h(_count(cohort.get('all_record_count'), 'record'))}</span></div>
  <div class='metric-grid'>{_metric_html(cohort)}</div>
  <div class='diagnosis-grid'>
    <section><h4>What we found</h4><p>{_h(cohort.get('pattern'))}</p><h4>Evidence pattern</h4><ul>{evidence}</ul></section>
    <section><h4>Why it matters</h4><p>{_h(meaning)}</p><h4>Account-level reading</h4><p>{_h(account_reading)}</p><p class='muted'>HubSpot pipelines represented: {pipelines}</p></section>
    <section><h4>Root-cause evidence</h4><ul>{root}</ul></section>
    <section><h4>Recommended action</h4><p>{_h(cohort.get('action'))}</p></section>
  </div>
  <h4>Representative cases</h4>
  <div class='table-wrap'><table><thead><tr><th>Account / record</th><th>Evidence</th><th>Actual break</th><th>First action</th></tr></thead><tbody>{samples}</tbody></table></div>
  <p class='trace'>Full population: {_h(_count(cohort.get('all_record_count'), 'record'))} in <a href='report_record_evidence.csv'>record evidence</a>; account aggregation in <a href='report_account_evidence.csv'>account evidence</a>.</p>
</article>
"""


def render_html(view: dict[str, Any], markdown_text: str) -> str:
    del markdown_text
    score = view["score"]
    business = _business(view)
    title = _title(view)
    summary = _summary(view)
    cohorts = view.get("account_cohorts", []) or []
    score_rows = "".join(
        "<div class='score-line'>"
        f"<span><strong>{_h(row['label'])}</strong><small>{_h(row['reading'])}</small></span>"
        f"<b>{_h('—' if row['deducted'] is None else ('−' + format(row['deducted'], 'g')))}</b>"
        "</div>"
        for row in _score_lines(score)
    )
    motion_rows = "".join(f"<tr><td><strong>{_h(row['motion'])}</strong></td><td>{_h(row['confidence'])}/100</td><td>{_h(row['contacts'])}</td><td>{_h(row['deals'])}</td></tr>" for row in _motion_rows(view)) or "<tr><td colspan='4'>No motion reached the evidence threshold.</td></tr>"
    cohort_html = "".join(_cohort_html(cohort) for cohort in cohorts) or "<div class='empty'>No named leakage group was found in the available evidence.</div>"
    action_rows = "".join(f"<tr><td>{index}</td><td><strong>{_h(cohort['title'])}</strong></td><td>{cohort['account_count']}</td><td>{cohort.get('unresolved_account_relationships', 0)}</td><td>{cohort['contact_count']}</td><td>{cohort['deal_count']} / {_h(cohort['amount'])}</td><td>{_h(cohort['action'])}</td></tr>" for index, cohort in enumerate(cohorts, 1)) or "<tr><td colspan='7'>No action population.</td></tr>"
    forbidden_actions = "".join(f"<li>{_h(item)}</li>" for item in DO_NOT_AUTOMATE)
    score_facts = f"<div class='score-facts'><span><b>{_h(score.get('total_deducted'))}</b> points deducted</span><span><b>{_h(score.get('coverage_percentage'))}%</b> handoff coverage</span><span><b>{_h(summary['accounts'])}</b> accounts represented</span></div>"
    html_body = f"""
<header class='cover'><div class='eyebrow light'>Smartify Marketing · Lifecycle Integrity Audit</div><h1>{_h(title)}</h1><p class='lede'>How buyer intent moves through { _h(business) }, where it stops becoming accountable pipeline, and what can be recovered or repaired next.</p><p class='cover-meta'>Audit date: {_h(view.get('generated'))} · Scope: {_h(view.get('window'))} · Based on HubSpot evidence · Read-only audit</p></header>
<section id='executive'><h2>1. Executive Verdict</h2><div class='score-hero'><div class='score-number'><div class='eyebrow light'>Overall Lifecycle Integrity Score</div><div><span class='hero-number'>{_h(score.get('overall_lifecycle_integrity_score'))}</span><span class='hero-denom'>/100</span></div><div class='score-status'>{_h(_score_status(score))}</div></div><div class='score-explanation'><h3>How the score is calculated</h3><p>The score starts at 100. It measures protected journey handoffs, not conversion, CRM hygiene, or lost revenue.</p><p class='formula'>{_h(_score_formula(score))}</p><div class='score-waterfall'>{score_rows}</div>{score_facts}<p class='score-caveat'>Closed-lost recovery is shown as a commercial opportunity and does not reduce the score unless a separate scored control break is confirmed.</p></div></div><div class='summary-grid'><article><span>Pre-deal demand</span><strong>{_h(summary['predeal_contacts'])}</strong><p>high-intent contacts without a visible deal path</p></article><article><span>Open pipeline to protect</span><strong>{_h(summary['open_deals'])}</strong><p>{_h(summary['open_amount'])} actual deal amount under review</p></article><article><span>Closed-lost recovery</span><strong>{_h(summary['closed_lost'])}</strong><p>deals with renewed activity to re-qualify</p></article></div></section>
<section id='journey'><h2>2. How {_h(business)} Sells</h2><p>The available evidence points to a <strong>{_h(humanize(view['registry'].primary_model))}</strong> selling model. Confidence describes the evidence for that classification, not funnel performance.</p><div class='journey-rail'><span>Buyer signal</span><b>→</b><span>Accountable owner</span><b>→</b><span>Deal or valid skip</span><b>→</b><span>Next sales action</span><b>→</b><span>Won / lost / re-engaged</span></div><div class='table-wrap'><table><thead><tr><th>Selling motion</th><th>Evidence confidence</th><th>Contacts</th><th>Deals</th></tr></thead><tbody>{motion_rows}</tbody></table></div></section>
<section id='breaks'><h2>3. Where the Journey Breaks by Account, Contact, and Deal</h2><p>Problems are grouped by the first missed handoff and then explained at account, contact, and deal level. Each group includes its actual evidence and a small representative sample; the complete population remains in the linked files.</p><div class='problem-list'>{cohort_html}</div></section>
<section id='actions'><h2>4. Action Queue</h2><p>Work from the first missed handoff downstream. The queue is grouped so one approved process repair can be checked against the full affected population.</p><div class='table-wrap'><table><thead><tr><th>Order</th><th>Problem group</th><th>Named accounts</th><th>Unresolved account links</th><th>Contacts</th><th>Deals / amount</th><th>First action</th></tr></thead><tbody>{action_rows}</tbody></table></div><p><a href='report_account_evidence.csv'>Open account-level evidence</a> · <a href='report_record_evidence.csv'>Open full record evidence</a></p></section>
<section id='causes'><h2>5. Why These Breaks Exist</h2><p>Workflow and scoring configuration is named only when it exists in the local snapshot. Configuration presence does not prove that a particular record enrolled or failed.</p><div class='cause-list'>{''.join(f"<article><strong>{_h(cohort['title'])}</strong><ul>{''.join(f'<li>{_linkified_html(item, _sample_rows(cohort))}</li>' for item in (_cohort_root_cause(cohort) or ['No specific configuration cause was supported.']))}</ul></article>" for cohort in cohorts) or '<div class="empty">No specific workflow or scoring cause was supported by the available evidence.</div>'}</div></section>
<section id='plan'><h2>6. 30-Day Recovery Plan</h2><p>The audit is read-only. Any CRM or workflow change requires separate approval.</p><div class='table-wrap'><table><thead><tr><th>Timing</th><th>Owner</th><th>Action</th><th>Success measure</th></tr></thead><tbody>{''.join(f"<tr><td>Days 1–5</td><td>Sales leadership + RevOps</td><td>{_h(cohort['action'])}</td><td>All {_h(_count(cohort['all_record_count'], 'record'))} receive a documented resolution or valid exception.</td></tr>" for cohort in cohorts)}<tr><td>Week 4</td><td>RevOps + revenue leadership</td><td>Re-run the audit and compare the same problem groups.</td><td>Resolved groups shrink without new downstream breaks.</td></tr></tbody></table></div><!-- blocked-actions:start --><h3>Actions That Should Not Be Automated</h3><ul>{forbidden_actions}</ul><!-- blocked-actions:end --></section>
<section id='monitor'><h2>7. Monitor and Verify</h2><p>Re-run after approved ownership, association, routing, workflow, scoring, or deal-creation changes. Compare <a href='report_account_evidence.csv'>account evidence</a> and <a href='report_record_evidence.csv'>record evidence</a>.</p><div class='monitor-grid'><article><strong>{_h(summary['predeal_contacts'])}</strong><span>high-intent contacts without deal paths</span><small>Target: owner plus deal or valid-no-deal decision</small></article><article><strong>{_h(summary['open_deals'])}</strong><span>open deals representing {_h(summary['open_amount'])}</span><small>Target: next action and account continuity</small></article><article><strong>{_h(summary['closed_lost'])}</strong><span>closed-lost deals to re-qualify</span><small>Target: recover / do-not-recover decision</small></article></div><div class='support-grid'><article><h3>Evidence files</h3><ul><li><a href='report_account_evidence.csv'>Account-level evidence</a></li><li><a href='report_record_evidence.csv'>Record-level evidence</a></li><li><a href='evidence.csv'>Hashed evidence</a></li><li><a href='operator_appendix.md'>Operator appendix</a></li></ul></article><article><h3>Sharing boundary</h3><p>Keep the raw snapshot local. Direct HubSpot links contain portal and record identifiers and work only for authorized HubSpot users. Treat this report as confidential.</p></article></div></section>
"""
    css = f"""
:root{{--canvas:#fcf9f6;--paper:#f5efe9;--ink:#1f1b18;--muted:#5d544d;--primary:#964900;--accent:#fe810e;--track:#eadfd5;--dark:#1b1714;--dark-text:#fffaf5;--error:#c1121f;--blue:#0b5e72}} *{{box-sizing:border-box}} body{{margin:0;background:var(--canvas);color:var(--ink);font:15px/1.55 Manrope,system-ui,-apple-system,sans-serif}} main{{max-width:1180px;margin:0 auto;padding:0 28px 52px}} section{{min-width:0}} p,li,td,small{{overflow-wrap:anywhere;word-break:break-word}} h2,h3,h4{{font-family:Newsreader,Georgia,serif}} h2{{font-size:31px;line-height:1.15;border-bottom:1px solid var(--track);padding-bottom:11px;margin:48px 0 20px}} h3{{font-size:22px;margin:14px 0 8px}} h4{{font-size:17px;margin:15px 0 7px}} a{{color:var(--primary);text-decoration:underline;text-underline-offset:3px}} .cover{{background:var(--dark);color:var(--dark-text);margin:0 -28px;padding:58px 28px 46px;border-radius:0 0 22px 22px}} .cover h1{{font:700 48px/1.05 Newsreader,Georgia,serif;max-width:800px;margin:10px 0 18px}} .lede{{font-size:18px;max-width:850px;color:#eadfd5}} .cover-meta{{font-size:13px;color:#cfc2b8}} .eyebrow{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--primary);font-weight:800}} .eyebrow.light{{color:var(--accent)}} .score-hero{{display:grid;grid-template-columns:minmax(270px,.82fr) minmax(0,1.7fr);overflow:hidden;background:var(--dark);color:var(--dark-text);border-radius:20px;box-shadow:0 10px 28px rgba(31,27,24,.14)}} .score-number{{padding:30px 31px;background:linear-gradient(145deg,#1b1714,#2b211b);border-right:1px solid #443a33}} .hero-number{{font:700 88px/1 Newsreader,Georgia,serif;color:var(--accent)}} .hero-denom{{font:24px Newsreader,Georgia,serif;color:#d8cabf}} .score-status{{font:600 19px/1.3 Newsreader,Georgia,serif;margin-top:12px;max-width:300px}} .score-explanation{{padding:25px 29px;min-width:0}} .score-explanation h3{{color:var(--dark-text);margin-top:0}} .score-explanation p{{color:#eadfd5}} .formula{{background:#2a211c;border:1px solid #51443b;border-radius:9px;padding:11px 12px;font-weight:700;color:#fff!important}} .score-waterfall{{border-top:1px solid #443a33;margin-top:17px}} .score-line{{display:flex;justify-content:space-between;gap:16px;border-bottom:1px solid #443a33;padding:8px 0}} .score-line span{{min-width:0}} .score-line small{{display:block;color:#cfc2b8;margin-top:2px}} .score-line b{{white-space:nowrap;color:var(--accent)}} .score-facts{{display:flex;flex-wrap:wrap;gap:9px;margin-top:16px}} .score-facts span{{border:1px solid #51443b;border-radius:9px;padding:8px 10px;color:#eadfd5;font-size:12px}} .score-facts b{{display:block;color:#fff;font-size:15px}} .score-caveat{{border-left:3px solid var(--accent);padding-left:11px;font-weight:700}} .summary-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px;margin:20px 0}} .summary-grid article,.cause-list article,.support-grid article{{background:#fff;border:1px solid var(--track);border-radius:15px;padding:17px;min-width:0}} .summary-grid span,.summary-grid p,.metric span,.monitor-grid span,.monitor-grid small{{display:block;color:var(--muted)}} .summary-grid strong{{display:block;font:700 32px/1 Newsreader,Georgia,serif;color:var(--primary);margin:8px 0}} .journey-rail{{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;background:#fff;border:1px solid var(--track);border-radius:15px;padding:18px;margin:18px 0}} .journey-rail span{{background:var(--paper);border:1px solid var(--track);border-radius:999px;padding:8px 11px;font-size:12px;font-weight:800}} .journey-rail b{{color:var(--primary);font-size:20px}} .table-wrap{{overflow-x:auto;margin:16px 0 22px}} table{{border-collapse:collapse;width:100%;background:#fff;min-width:760px;font-size:13px}} th{{background:var(--paper);font-weight:800;text-align:left}} th,td{{padding:10px;border:1px solid var(--track);vertical-align:top}} .problem-list{{display:grid;gap:20px}} .problem-group{{background:#fff;border:1px solid var(--track);border-top:5px solid var(--primary);border-radius:17px;padding:21px;min-width:0;box-shadow:0 5px 18px rgba(31,27,24,.05)}} .problem-group.opportunity{{border-top-color:var(--blue)}} .group-header{{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}} .group-header h3{{font-size:26px;margin:10px 0 0}} .group-count{{color:var(--muted);white-space:nowrap}} .status{{display:inline-block;border-radius:999px;padding:4px 9px;font-size:11px;font-weight:800;background:#ffe1e3;color:#7d0a13}} .opportunity .status{{background:#dff5fb;color:var(--blue)}} .metric-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:1px;background:var(--track);border:1px solid var(--track);border-radius:11px;overflow:hidden;margin:18px 0}} .metric{{background:var(--paper);padding:11px;min-width:0}} .metric strong{{display:block;color:var(--primary);font:700 20px/1.2 Newsreader,Georgia,serif;margin-top:5px}} .diagnosis-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}} .diagnosis-grid section{{border:1px solid var(--track);border-radius:12px;padding:14px;min-width:0}} .diagnosis-grid ul{{margin:6px 0;padding-left:20px}} .muted,.trace,small{{color:var(--muted);font-size:12px}} .cause-list,.support-grid,.monitor-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px}} .monitor-grid{{grid-template-columns:repeat(3,minmax(0,1fr));margin:18px 0}} .monitor-grid article{{background:#fff;border:1px solid var(--track);border-radius:14px;padding:16px;min-width:0}} .monitor-grid strong{{display:block;font:700 30px/1 Newsreader,Georgia,serif;color:var(--primary)}} footer{{border-top:1px solid var(--track);margin-top:52px;padding-top:18px;color:var(--muted);font-size:13px}} ul,ol{{padding-left:23px}} li{{margin:5px 0}} .empty{{background:#fff;border:1px dashed var(--track);border-radius:12px;padding:17px;color:var(--muted)}} @media(max-width:850px){{main{{padding:0 17px 38px}}.cover{{margin:0 -17px;padding:42px 17px}}.cover h1{{font-size:38px}}.score-hero{{grid-template-columns:1fr}}.score-number{{border-right:0;border-bottom:1px solid #443a33}}.summary-grid,.metric-grid,.diagnosis-grid,.cause-list,.support-grid,.monitor-grid{{grid-template-columns:1fr 1fr}}.journey-rail{{justify-content:flex-start}}.journey-rail b{{display:none}}}} @media(max-width:560px){{.summary-grid,.metric-grid,.diagnosis-grid,.cause-list,.support-grid,.monitor-grid{{grid-template-columns:1fr}}}} @media print{{body{{background:#fff;font-size:11px}}main{{max-width:none;padding:0}}.cover{{border-radius:0;padding:35px 0}}h2{{break-before:page;margin-top:25px}}.score-hero,.problem-group,.summary-grid article,.cause-list article{{box-shadow:none;break-inside:avoid}}.table-wrap{{overflow:visible}}table{{min-width:0;font-size:9px}}a{{color:inherit;text-decoration:none}}}}
.hubspot-asset{{font-weight:800;color:var(--ink)}} .hubspot-record{{text-decoration-thickness:1px}}
"""
    return f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{_h(title)}</title><style>{css}</style></head><body><main>{html_body}<footer><strong>{_h(BRAND_NAME)}</strong> · {_h(SLOGAN)}<br><a href='{_h(CREDIT_URL)}'>{_h(CREDIT_URL)}</a> · <a href='{_h(GITHUB_URL)}'>GitHub</a></footer></main></body></html>"
