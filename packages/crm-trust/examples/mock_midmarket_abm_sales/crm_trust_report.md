# HubSpot Marketing-to-Pipeline Trust Audit

## Snapshot Overview

This report evaluates a **completed, full-history, non-truncated local snapshot** of the CRM fixture. It is a synthetic test run designed to exercise the audit workflow; it is not a conclusion about the live portal.

| Snapshot fact | Result | Source |
|---|---:|---|
| Snapshot status | `completed` | [manifest.json](manifest.json) |
| Coverage | Full history; no object truncated | [manifest.json](manifest.json) |
| Capture window | 2026-07-13 23:00–2026-07-14 00:00 UTC | [manifest.json](manifest.json) |
| Contacts | 360 | [snapshot_summary.json](processed/snapshot_summary.json) |
| Companies | 60 | [snapshot_summary.json](processed/snapshot_summary.json) |
| Deals | 36 | [snapshot_summary.json](processed/snapshot_summary.json) |
| Owners | 8 | [snapshot_summary.json](processed/snapshot_summary.json) |
| Defined deal pipelines | 2 | [snapshot_summary.json](processed/snapshot_summary.json) |

Association coverage is complete for this fixture: **280/360 contacts (77.8%)** have a company, **32/36 deals (88.9%)** have a company, and **30/36 deals (83.3%)** have a contact. The underlying distribution is available in [association_summary.json](processed/association_summary.json).

## Data Quality Dashboard

There is deliberately no single “data completeness score” here. Email, phone, source, ownership, amount, and association fields have different business meanings and requiredness rules. The dashboard shows each field so the CRM owner can judge it against the operating model.

### Key-field completeness

| Object | Field | Present | Missing | Fill rate |
|---|---|---:|---:|---:|
| Contact | Email | 360/360 | 0 | 100.0% |
| Contact | First name | 360/360 | 0 | 100.0% |
| Contact | Last name | 339/360 | 21 | 94.2% |
| Contact | Phone | 270/360 | 90 | 75.0% |
| Contact | Lifecycle stage | 360/360 | 0 | 100.0% |
| Contact | Original source | 320/360 | 40 | 88.9% |
| Contact | Latest source | 330/360 | 30 | 91.7% |
| Contact | Owner | 324/360 | 36 | 90.0% |
| Company | Name | 59/60 | 1 | 98.3% |
| Company | Domain | 55/60 | 5 | 91.7% |
| Company | Lifecycle stage | 60/60 | 0 | 100.0% |
| Company | Owner | 55/60 | 5 | 91.7% |
| Deal | Deal name | 36/36 | 0 | 100.0% |
| Deal | Pipeline | 36/36 | 0 | 100.0% |
| Deal | Deal stage | 36/36 | 0 | 100.0% |
| Deal | Amount | 30/36 | 6 | 83.3% |
| Deal | Close date | 36/36 | 0 | 100.0% |
| Deal | Owner | 32/36 | 4 | 88.9% |

Source: [snapshot_summary.json](processed/snapshot_summary.json) and [identity_completeness.json](processed/identity_completeness.json). Identity values themselves remain local-only and are not included in this report.

### Lifecycle and pipeline shape

| Contact lifecycle stage | Records |
|---|---:|
| Lead | 180 |
| Marketing qualified lead | 80 |
| Sales qualified lead | 50 |
| Opportunity | 30 |
| Customer | 15 |
| Closed lost | 5 |

The CRM contains **20 open deals, 12 closed-won deals, and 4 closed-lost deals**. Of the defined pipelines, 26 deals are in `new_business` and 8 are in `expansion`; 2 deals reference a pipeline not present in the pipeline definitions. See [lifecycle_distribution.json](processed/lifecycle_distribution.json) and [pipeline_summary.json](processed/pipeline_summary.json).

### Operational recency

The following is a **last-modified recency proxy**, not proof of human, marketing, or sales activity. It is included because a CMO needs to know whether the CRM is being maintained operationally.

| Object | ≤30 days | 31–90 days | 91–180 days | >180 days | Timestamp coverage |
|---|---:|---:|---:|---:|---:|
| Contacts | 90/360 (25.0%) | 90/360 (25.0%) | 90/360 (25.0%) | 90/360 (25.0%) | 100.0% |
| Companies | 15/60 (25.0%) | 30/60 (50.0%) | 0/60 (0.0%) | 15/60 (25.0%) | 100.0% |
| Deals | 9/36 (25.0%) | 9/36 (25.0%) | 9/36 (25.0%) | 9/36 (25.0%) | 100.0% |

Details and the exact reference timestamp are in [activity_summary.json](processed/activity_summary.json). This is a synthetic fixture, so the even distribution is intentional test data rather than a claim about a real team’s activity pattern.

### Attribution and property shape

- Original source is present for 320/360 contacts overall (88.9%), but only 140/180 in the recent half (77.8%).
- Latest source is present for 330/360 contacts (91.7%).
- The property-governance measurement examined 17 source-like fields across the snapshot: 3 show older-half usage with no recent-half usage, and 11 are name-collision candidates.
- The source field candidate detail, including older/recent fill rates, is in [source_field_candidates.json](processed/source_field_candidates.json). No raw CRM values are required to inspect the finding.

## Findings by Module

The following table includes every approved finding, not only the executive-summary items. Each number is copied from a deterministic measurement and each row links to the module evidence CSV.

| Module | Finding | Severity | Measured result | Evidence |
|---|---|---|---|---|
| Attribution | Recent original-source capture gap | High | 40/180 recent contacts; 22.2% | [attribution_trust.csv](evidence/attribution_trust.csv) |
| Lifecycle | Customer stage without closed-won trace | High | 15/15; 100.0% | [lifecycle_funnel.csv](evidence/lifecycle_funnel.csv) |
| Lifecycle | MQL+ contacts without deal trace | High | 155/160; 96.9% | [lifecycle_funnel.csv](evidence/lifecycle_funnel.csv) |
| Associations | Contacts without company | High | 80/360; 22.2% | [association_architecture.csv](evidence/association_architecture.csv) |
| Associations | Deals without company | Medium | 4/36; 11.1% | [association_architecture.csv](evidence/association_architecture.csv) |
| Associations | Deals without contact | Medium | 6/36; 16.7% | [association_architecture.csv](evidence/association_architecture.csv) |
| Associations | Shared-domain company candidates | Medium | 8/55; 14.5% | [association_architecture.csv](evidence/association_architecture.csv) |
| Associations | Companies without domain | Low | 5/60; 8.3% | [association_architecture.csv](evidence/association_architecture.csv) |
| Pipeline | Open deals past close date | Medium | 3/20 open deals; 15.0% | [pipeline_hygiene.csv](evidence/pipeline_hygiene.csv) |
| Pipeline | Deals without amount | Medium | 6/36; 16.7% | [pipeline_hygiene.csv](evidence/pipeline_hygiene.csv) |
| Pipeline | Deals without owner | Medium | 4/36; 11.1% | [pipeline_hygiene.csv](evidence/pipeline_hygiene.csv) |
| Pipeline | Deals in unknown pipeline | Medium | 2/36; 5.6% | [pipeline_hygiene.csv](evidence/pipeline_hygiene.csv) |
| Property governance | Decayed source-field candidates | Medium | 3/17; 17.6% | [property_governance.csv](evidence/property_governance.csv) |
| Property governance | Similar source-field name candidates | Medium | 11/17; 64.7% | [property_governance.csv](evidence/property_governance.csv) |

Machine-readable details are in [findings.json](findings.json), and the exact measurement documents are in [processed/measurements](processed/measurements/).

## CRM Trust Score

**48/100**

| Category | Score | Why points were deducted |
|---|---:|---|
| Attribution Trust | 19/25 | Recent original-source capture gap |
| Lifecycle + Funnel Trust | 8/20 | Customer/deal reconciliation and MQL+ deal-trace gaps |
| Association + Account Trust | 4/20 | Orphan contacts/deals, duplicate candidates, and missing domains |
| Pipeline Hygiene | 8/20 | Past close dates, missing amounts/owners, and unknown pipeline |
| Property Governance | 9/15 | Decayed and colliding source-like fields |

The score is code-owned arithmetic over the 14 approved findings. It is a measure of reporting trust for this audit profile, not revenue performance, forecast accuracy, or company performance. See [score.json](score.json).

## Executive Summary

The CRM has a healthy basic identity layer—email and first name are 100% populated, lifecycle stage is present for every contact, and all deals have names, stages, pipelines, and close dates. The weaknesses are structural rather than cosmetic: account relationships are incomplete, lifecycle stages do not reconcile to deals, source governance is fragmenting, and pipeline value/ownership is not consistently captured.

For an ABM-heavy sales-led motion, the account architecture is the largest trust constraint. Only 77.8% of contacts are linked to a company, and 83.3% of deals are linked to a contact. That makes it difficult to answer which accounts were influenced, which contacts progressed, and which marketing activity can be connected to revenue.

The biggest near-term reporting risk is the lifecycle-to-deal gap: 96.9% of MQL+ contacts have no associated deal, and all 15 customer-stage contacts lack a closed-won relationship in this snapshot. This may be a real data-quality problem, or it may reflect a business rule that the CRM is not encoding consistently; the report therefore recommends confirmation and review, not automatic stage changes.

## Business Context Detected

The detected model is a mid-market, sales-led ABM CRM with multiple pipelines, company-level ownership, and partial attribution maturity. The selected profile is `abm_heavy_crm`, which weights account rollups, association integrity, and cross-pipeline attribution more heavily than a lean lead-based CRM would. The context artifacts are [business_context.json](business_context.json), [crm_context.yaml](crm_context.yaml), and [audit_profile.json](audit_profile.json).

## Audit Scope

This audit covers attribution trust, lifecycle and funnel trust, contact-company-deal associations, pipeline hygiene relevant to marketing reporting, and property governance. It does not evaluate sales performance, forecasting, win rates, quota attainment, or business strategy, and it performs no CRM writes.

## Critical Findings

There are no findings classified as critical. The high-severity findings are the recent source-capture gap, the customer-stage/closed-won reconciliation gap, the MQL+/deal-trace gap, and the contact/company association gap. They are high because they materially impair the reporting questions this ABM profile is meant to answer; they are not proof that the underlying business process is failing.

## Evidence Summary

The deterministic measurement layer produced **241 evidence rows** across five modules. The CSVs contain hashed record identifiers and redacted values only:

- [Attribution evidence](evidence/attribution_trust.csv) · [measurement](processed/measurements/attribution_trust.json)
- [Lifecycle evidence](evidence/lifecycle_funnel.csv) · [measurement](processed/measurements/lifecycle_funnel.json)
- [Association evidence](evidence/association_architecture.csv) · [measurement](processed/measurements/association_architecture.json)
- [Pipeline evidence](evidence/pipeline_hygiene.csv) · [measurement](processed/measurements/pipeline_hygiene.json)
- [Property governance evidence](evidence/property_governance.csv) · [measurement](processed/measurements/property_governance.json)

To validate a finding, open the row whose `finding_id` equals the finding’s `measurement_id`, then compare the result to [findings.json](findings.json). The report never exposes raw contact identity values.

## Priority Recommendations

1. Confirm the lifecycle-to-closed-won and MQL+/deal handoff rules, then review the 15 customer-stage and 155 MQL+ exceptions.
2. Confirm the canonical source field and produce a review-list specification for the 40 recent contacts missing original source.
3. Produce account-association review queues for 80 orphan contacts, 4 orphan deals, and 6 deals without a contact.
4. Review the 8 shared-domain candidates and 5 companies without domains before relying on account rollups.
5. Establish stage-aware rules for amount, ownership, and pipeline membership before using value-weighted pipeline reporting.
6. Produce a canonical-versus-legacy source-property map for the 3 decayed and 11 name-collision candidates.

## Recommendation Basis

The recommendation agent’s output is not a free-standing checklist. Every item below points back to a finding, its measurement, and an evidence file. “Draft a list” and “draft a field map” are themselves concrete deliverables: they produce a reviewable artifact without changing CRM truth.

| Finding | Recommended deliverable | Why this follows | Expected outcome | Owner / risk |
|---|---|---|---|---|
| `recent_original_source_capture_gap` | Confirm source rule and draft criteria for the 40-record review list | 40/180 recent contacts lack original source | Confirmed capture rule and remediation queue | Marketing ops · business confirmation |
| `customers_without_closedwon_deal_trace` | Confirm lifecycle-to-revenue rule and prepare a 15-record exception queue | 15/15 customer-stage contacts lack closed-won trace | Documented rule and reviewed exceptions | Marketing + RevOps · business confirmation |
| `mql_plus_contacts_without_deal_trace` | Confirm handoff rule and review the 155-record exception queue | 155/160 MQL+ contacts lack deal trace | Separate intentional pre-deal stages from broken traceability | Marketing + Sales Ops · business confirmation |
| `contacts_without_company_association` | Export an 80-record account-association review list | 80/360 contacts lack company association | Human decisions on account membership | CRM owner · safe operational |
| `deals_without_company_association` | Export a 4-record deal/account review list | 4/36 deals lack company association | Restore account-rollup coverage through reviewed decisions | RevOps · safe operational |
| `deals_without_contact_association` | Export a 6-record deal/contact review list | 6/36 deals lack contact association | Restore contact-to-revenue traceability | RevOps · safe operational |
| `duplicate_company_domain_candidates` | Review 8 shared-domain candidates and record intent | 8/55 domain-populated companies are candidate collisions | Distinguish subsidiaries from duplicate-like records | Account Ops · business confirmation |
| `companies_without_domain` | Export a 5-record missing-domain review list | 5/60 companies lack domain | Better matching and deduplication inputs | CRM owner · safe operational |
| `open_deals_past_close_date` | Route 3 records to human pipeline review | 3/20 open deals have past close dates | Human disposition without rewriting sales truth | Sales Ops · do not auto-fix |
| `deals_without_amount` | Confirm stage-aware amount rule and review 6 records | 6/36 deals lack amount | A clear value-reporting policy and exception list | Sales Ops · business confirmation |
| `deals_without_owner` | Export a 4-record owner-gap review list | 4/36 deals lack owner | Reviewed ownership gaps without guessing assignees | Sales Ops · safe operational |
| `deals_in_unknown_pipeline` | Ask an administrator to determine the intended pipeline for 2 records | 2/36 deals reference undefined pipeline | A documented pipeline decision and consistent rollup | CRM Admin · do not auto-fix |
| `decayed_source_field_candidates` | Draft a canonical/legacy map for 3 candidates | 3/17 source-like fields have no recent usage | Governance artifact for workflow owners | Marketing Ops · business confirmation |
| `similar_source_field_name_candidates` | Draft a canonical map for 11 name-collision candidates | 11/17 source-like fields collide by name | Explicit mapping and confirmation backlog | CRM Governance · business confirmation |

## Safe Actions

These are safe because they create reviewable artifacts only: export hashed evidence queues, draft list criteria, draft a field map, and draft governance documentation. They do not select CRM values, create associations, assign owners, rewrite stages, or delete fields. The exact evidence rows are linked above and in [recommendations.json](recommendations.json).

## Needs Business Rule Confirmation

The audit cannot decide whether customer stage requires closed-won, which lifecycle stages require a deal, which source property is canonical, whether shared domains are subsidiaries, or which deal stages require amount and ownership. Those decisions must be made by the business owner before any CRM write plan is approved.

## Do Not Auto-Fix

- Do not overwrite original source.
- Do not merge companies automatically.
- Do not delete properties.
- Do not move all stale deals.
- Do not reset lifecycle stage.
- Do not bulk update owner.
- Do not change pipeline, close date, or deal stage based only on this report.

These phrases appear here as explicit prohibitions, not as execution instructions. The Privacy + Safety Reviewer clearance is recorded in [safety_clearance.json](safety_clearance.json).

## Limitations

- `deals_stuck_in_stage` is unavailable because stage-entry timestamps are not fetched in v1; no stuckness conclusion is made. See [pipeline_hygiene.json](processed/measurements/pipeline_hygiene.json).
- This is synthetic data designed to exercise the workflow. The measurements validate the audit mechanics, not the live portal’s truth.
- Shared domains and lifecycle/deal mismatches are candidates for review, not proof of incorrect CRM data.
- Full-history cursor traversal in the live connector is best-effort rather than a point-in-time transaction, although this fixture itself is complete and non-truncated.

## Suggested Next Review

Use this fixture as a regression case after changes to profiling, sanitization, findings validation, review aggregation, recommendations, or final-gate logic. Once the live portal has sufficient deal and association coverage, run the same full-history workflow and compare the snapshot dashboard, evidence rows, and recommendation decisions against this structure.
