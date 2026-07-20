# Client Reporting Standard

This standard separates decision communication from operator evidence. All
formats must be generated from the same validated artifacts; a format export
must never trigger a second interpretation or rewrite.

## Output layers and formats

### Decision-maker report

- `crm_trust_report.html` is the default visual report. It is self-contained,
  responsive, print-ready, and includes compact data graphics.
- `crm_trust_report.md` is the accessible text equivalent and the canonical
  linkable record when HTML is not convenient.
- PDF is for fixed distribution. Export it from the validated HTML so the
  content, data, ordering, and evidence links remain identical.
- Word is for explicitly requested editable delivery. Generate it from the
  same report model; do not ask a model to rewrite the report for Word.

### Operator evidence

- `operator_appendix.md` contains every validated finding, detailed
  implementation instructions, evidence and measurement links, schema and
  context references, and method constraints.
- `agent_handoff.md` contains safety boundaries and an implementation sequence
  for a later authorized workflow.
- CSV, JSON, YAML, and schema artifacts remain supporting evidence. They are
  not substitutes for the decision-maker report.

## Required decision-maker structure

1. Executive Summary
2. CRM Snapshot
3. Data Quality and Usability
4. Activity and Data Age
5. Funnel and Association Coverage
6. Key Findings
7. Root Cause Hypotheses
8. Recommended Actions
9. What This Audit Cannot Determine
10. Evidence and Supporting Files
11. Next Review
12. Sharing the Report

The first screen or printed page must make CRM scale, trust score, and the
most exposed decisions immediately visible. The report must include contacts,
companies, deals, and pipeline totals; key-field completeness and identity
validity; recent, active, aging, and stale record distribution; lifecycle,
pipeline, and association coverage; and every material validated finding.
Use the exact user-supplied business name in the report title. If no name was
supplied, use the generic HubSpot audit title; never infer the audited business
from a Company record.

## Finding presentation

Each material finding states:

- a human-readable title and stable finding ID;
- severity and confidence;
- affected records, denominator, and percentage when measured;
- the management decisions it may distort, such as attribution reporting,
  budget allocation, lead quality, sales handoff, account coverage, or
  forecast confidence;
- the business impact in plain language; and
- direct links to the evidence CSV and measurement file.

Where record-level evidence maps to a HubSpot Company or Deal, show up to
three representative named records per finding and link each name directly to
its HubSpot record page. Keep the complete mapped set in
`report_record_evidence.csv` so large portals remain readable. Do not expose
Contact names.

Root causes are hypotheses, never facts unless independently verified. Show
the confidence, linked finding IDs, supporting artifacts, and the question
that would confirm or reject the hypothesis.

## Recommendation presentation

Every recommendation states the exact target, current state, desired state,
ordered implementation steps, evidence basis, decision owner, approval
required, expected result, and a measurable success condition.

Do not write `change the property in CRM`. Name the object and property, say
what rule or value changes from what to what, explain how, and state why the
evidence supports it. If the evidence cannot support a value change, specify
the exact decision or evidence-review task that must happen first.

Internal risk categories remain in `recommendations.json`. In the client
report, express them as the approval needed: owner review, business-rule
confirmation, or explicit approval before a CRM change.

## Language rules

- Write concise, factual English. Put the conclusion before its explanation.
- Use ordinary business language. Define acronyms on first use.
- Do not identify an assumed reader. Phrases such as `for the CMO` or
  `CMO-facing` do not belong in a report that may be forwarded.
- Do not expose implementation language such as `LLM`, `agent`, `harness`,
  `code-owned`, `machine-readable`, `non-autofix`, or `do-not-auto-fix` in the
  decision-maker report.
- Avoid decorative prose, rhetorical openings, vague claims, and unexplained
  technical terms.
- Never claim that CRM data quality proves revenue performance, return on
  investment, or business effectiveness.
- Prefix and bold values that originate from the portal so report language is
  not confused with configured CRM language: `HubSpot property:`, `HubSpot
  lifecycle stage:`, `HubSpot pipeline:`, `HubSpot deal stage:`, `HubSpot
  Company:`, and `HubSpot Deal:`.

## Data graphic principles

Every graphic must answer one decision question and retain its exact value in
text or an accessible label. Use charts for comparisons and distributions,
not decoration.

- KPI cards: CRM scale and trust score.
- Horizontal bars: field completeness, identity validity, lifecycle stage
  distribution, and association coverage.
- Stacked bars: recent, active, aging, and stale record mix.
- Tables: exact values, evidence links, and findings where multiple fields
  must be compared.
- No 3D charts, gauges, unlabeled axes, arbitrary gradients, or charts that
  hide denominators.
- Do not use color as the only signal. Keep labels and values visible and
  preserve contrast in print.

Use the Smartify visual tokens:

- canvas `#fcf9f6`, paper `#f5efe9`, ink `#1b1714`, blush `#f3dfd2`;
- primary `#964900`, accent `#fe810e`, accent ink `#5f2b00`;
- primary text `#1f1b18`, secondary text `#5d544d`, error `#c1121f`;
- Newsreader-style editorial headings and Manrope-style body text with safe
  local fallbacks;
- consistent 10–20px radii, generous whitespace, and thin low-contrast rules.

The HTML footer links to `https://smartifymarketing.com` and
`https://github.com/AliceEinstein` for additional marketing systems insights
and updates. The brand name shown in the report is **Smartify Marketing** and
the slogan is **Your Strategic B2B Marketing Partner**.

## Sharing and distribution

The generated HTML is a local artifact. It is not automatically hosted at a
public URL. When served from `localhost`, it is normally reachable only from
the same machine (or from a deliberately configured network), and its relative
links require the supporting output files to stay with it.

For ordinary external sharing, open the validated HTML in a browser and use
**Print → Save as PDF**. Share the PDF through the customer's approved
channel. If an interactive HTML package is required, share the complete
sanitized output package through approved hosting or file sharing; do not
expose `raw/`, `.env`, secrets, or the unfiltered run directory. Sharing only
the HTML file will break links to the evidence CSV and supporting artifacts.

## Evidence boundary

The main report shows enough representative evidence to evaluate each claim
and links to the supporting artifact. It does not reproduce the full row-level
dataset or schema detail. The appendix carries full audit detail for an
operator or a later authorized agent. Sanitized Company and Deal names may
appear as evidence; Contact identity values, raw IDs, portal IDs outside link
targets, and tokens never enter either report.
