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

Explain the trust score next to the headline number. Show starting points,
total deductions, the remaining score for each trust category, and the fixed
severity deduction mapping. Link to `score.json` for the complete counted
finding list. Never show an unexplained score.

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

Group findings into visible Priority 1, Priority 2, and Priority 3 sections. Priority 1 is
for critical/high findings that can materially distort current management
decisions; Priority 2 is for medium findings that weaken confidence or
operating consistency; Priority 3 is for low-severity maintenance and hygiene
debt. The distinction must use headings, labels, layout, and explanation —
never color alone. Recommendations follow the same global priority order;
their safety/approval category is metadata and must not override severity.

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
ordered implementation steps, evidence basis, recommended accountable role,
human decision required, completion condition, and a measurable success
condition. The accountable role is a recommendation, not a verified person,
unless the allowed evidence explicitly identifies a real person as accountable
for that exact decision.

The audit prepares the affected cohort, measurements, record links, and local
evidence files. Do not present creation of a review queue/list as human work or
as a successful outcome. The human action begins with reviewing the records,
approving or declining proposed resolutions, documenting valid exceptions,
confirming the governing rule, or authorizing a controlled CRM change.

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
- Use Arabic numerals for quantities (`8`, not `eight`). Enforce this in the
  finding/recommendation artifacts; never run a global number-word replacement
  over final prose or a user-configured HubSpot asset name.
- Never claim that CRM data quality proves revenue performance, return on
  investment, or business effectiveness.
- Visually distinguish values that originate from the portal so report
  language is not confused with configured CRM language. Bold the configured
  property, lifecycle stage, pipeline, deal stage, Company, Deal, Workflow, or
  other HubSpot asset name. Keep surrounding prose, evidence links, and generic
  record-link text at normal weight; repeated bold must not flatten the visual
  hierarchy.

## Data graphic principles

Every graphic must answer one decision question and retain its exact value in
text or an accessible label. Use charts for comparisons and distributions,
not decoration.

- KPI cards: CRM scale and trust score.
- Horizontal bars: field completeness grouped by Contact, Company, and Deal;
  compact identity validity; lifecycle stage distribution; and association
  coverage. Do not force unrelated panels into equal-height columns that leave
  large empty areas. Show every configured key field, or explicitly state the
  displayed and total field counts; never silently truncate completeness data.
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

Treat every generated report as confidential CRM data: it can contain
identifiable Company/Deal names and direct record links. For authorized
sharing, open the validated HTML in a browser and use **Print → Save as PDF**,
then use the customer's approved channel. If interactive HTML is required,
share the complete report package only with authorized recipients through
access-controlled hosting or file sharing. Never expose `raw/`, `.env`,
secrets, or the unfiltered run directory. Sharing only the HTML file will break
links to the evidence CSV and supporting artifacts.

## Evidence boundary

The main report shows enough representative evidence to evaluate each claim
and links to the supporting artifact. It does not reproduce the full row-level
dataset or schema detail. The appendix carries full audit detail for an
operator or a later authorized agent. Display-safe Company and Deal names may
appear as identifiable evidence; Contact identity values, raw IDs, portal IDs
outside link targets, and tokens never enter either report.
