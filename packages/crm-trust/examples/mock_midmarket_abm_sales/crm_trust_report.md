# Northstar Systems CRM Trust Audit

*HubSpot Marketing-to-Pipeline Trust Audit*

## Executive Summary

Northstar Systems has enough structured HubSpot data to support regular management reporting, but material attribution, relationship, and pipeline gaps prevent the CRM from functioning as a dependable single source of truth.

**CRM trust score: 48/100.**
The score summarizes the reviewed data-quality findings. It is not a measure of revenue performance or return on investment.

### How the score is calculated

**100 starting points − 52 deducted points = 48.** Only approved or revised findings count. Critical findings deduct 10 points, high 6, medium 3, and low 1, capped at each category maximum.

| Trust category | Starting points | Deducted | Remaining |
|---|---:|---:|---:|
| Attribution Trust | 25 | −6 | 19 |
| Lifecycle + Funnel Trust | 20 | −12 | 8 |
| Association + Account Trust | 20 | −16 | 4 |
| Pipeline Hygiene | 20 | −12 | 8 |
| Property Governance | 15 | −6 | 9 |

- [Complete score calculation](score.json)

No CRM records were changed during this audit.

## CRM Snapshot

| CRM object | Records | Coverage | Complete extract |
|---|---:|---|---|
| Contacts | 360 | Full history | Yes |
| Companies | 60 | Full history | Yes |
| Deals | 36 | Full history | Yes |
| Pipelines | 2 | Full history | Yes |

- Snapshot completed: 2026-07-14T00:00:00+00:00
- Coverage: Full history

## Data Quality and Usability

Core contact identity is broadly usable. Trust falls where acquisition source capture, Contact-to-Company-to-Deal traceability, Deal amount coverage, and legacy property governance affect management reporting.

### Key field completeness

| Object | Field | Present | Total | Complete |
|---|---|---:|---:|---:|
| Companies | **HubSpot property: Domain (domain)** | 55 | 60 | 91.7% |
| Companies | **HubSpot property: Company owner (hubspot_owner_id)** | 55 | 60 | 91.7% |
| Companies | **HubSpot property: Name (name)** | 59 | 60 | 98.3% |
| Companies | **HubSpot property: Lifecycle Stage (lifecyclestage)** | 60 | 60 | 100.0% |
| Contacts | **HubSpot property: Phone (phone)** | 270 | 360 | 75.0% |
| Contacts | **HubSpot property: Original Source (hs_analytics_source)** | 320 | 360 | 88.9% |
| Contacts | **HubSpot property: Contact owner (hubspot_owner_id)** | 324 | 360 | 90.0% |
| Contacts | **HubSpot property: Latest Source (hs_latest_source)** | 330 | 360 | 91.7% |
| Contacts | **HubSpot property: Last Name (lastname)** | 339 | 360 | 94.2% |
| Contacts | **HubSpot property: Email (email)** | 360 | 360 | 100.0% |
| Contacts | **HubSpot property: First Name (firstname)** | 360 | 360 | 100.0% |
| Contacts | **HubSpot property: Lifecycle Stage (lifecyclestage)** | 360 | 360 | 100.0% |
| Deals | **HubSpot property: Amount (amount)** | 30 | 36 | 83.3% |
| Deals | **HubSpot property: Deal owner (hubspot_owner_id)** | 32 | 36 | 88.9% |
| Deals | **HubSpot property: Close Date (closedate)** | 36 | 36 | 100.0% |
| Deals | **HubSpot property: Deal name (dealname)** | 36 | 36 | 100.0% |
| Deals | **HubSpot property: Deal Stage (dealstage)** | 36 | 36 | 100.0% |
| Deals | **HubSpot property: Pipeline (pipeline)** | 36 | 36 | 100.0% |

### Contact identity completeness and validity

| Contact field | Complete | Valid format when present |
|---|---:|---:|
| **HubSpot property: Email (email)** | 100.0% | 100.0% |
| **HubSpot property: First Name (firstname)** | 100.0% | 100.0% |
| **HubSpot property: Last Name (lastname)** | 94.2% | 100.0% |
| **HubSpot property: Phone (phone)** | 75.0% | 100.0% |

## Activity and Data Age

The table uses each record's last-modified date. It shows recency, not confirmed human engagement.

| Object | Updated ≤30 days | 31–90 days | 91–180 days | Over 180 days |
|---|---:|---:|---:|---:|
| Contacts | 90 | 90 | 90 | 90 |
| Companies | 15 | 30 | 0 | 15 |
| Deals | 9 | 9 | 9 | 9 |

## Funnel and Association Coverage

### Lifecycle distribution

| Object | Lifecycle stage | Records |
|---|---|---:|
| Contacts | **HubSpot lifecycle stage: Lead** | 180 |
| Contacts | **HubSpot lifecycle stage: Marketing Qualified Lead (MQL)** | 80 |
| Contacts | **HubSpot lifecycle stage: Sales Qualified Lead (SQL)** | 50 |
| Contacts | **HubSpot lifecycle stage: Opportunity** | 30 |
| Contacts | **HubSpot lifecycle stage: Customer** | 15 |
| Contacts | **HubSpot lifecycle stage: Closed Lost** | 5 |
| Companies | **HubSpot lifecycle stage: Lead** | 48 |
| Companies | **HubSpot lifecycle stage: Customer** | 12 |

### Association coverage

| Relationship | Associated records | Total | Coverage |
|---|---:|---:|---:|
| Contacts To Companies | 280 | 360 | 77.8% |
| Deals To Companies | 32 | 36 | 88.9% |
| Deals To Contacts | 30 | 36 | 83.3% |

### Deal pipelines

| Pipeline | Stages | Deals |
|---|---:|---:|
| **HubSpot pipeline: New Business** | 6 | 26 |
| **HubSpot pipeline: Expansion** | 4 | 8 |
| Unknown pipeline | — | 2 |

## Key Findings

Validated findings are ordered by decision priority: P1 first, then structural P2 gaps, followed by P3 maintenance debt.

### Priority 1 — Decisions at immediate risk

| Finding | Severity | Evidence sample | Decisions affected | What it can distort | Evidence |
|---|---|---:|---|---|---|
| **Customers Without Closed Won Deal Trace**<br>**HubSpot property: Lifecycle Stage (lifecyclestage)**<br><small>customers_without_closedwon_deal_trace</small> | High | 15 of 15 records (100.0%) | Marketing Qualified Lead (MQL) quality; Sales handoff; Funnel conversion | The customer-stage population cannot be reconciled to closed-won revenue through the captured deal relationships, weakening lifecycle-to-pipeline reporting for a sales-led motion. | [CSV](evidence/lifecycle_funnel.csv) · [measurement](processed/measurements/lifecycle_funnel.json) |
| **MQL Plus Contacts Without Deal Trace**<br>**HubSpot property: Lifecycle Stage (lifecyclestage)**<br><small>mql_plus_contacts_without_deal_trace</small> | High | 155 of 160 records (96.9%) | Marketing Qualified Lead (MQL) quality; Sales handoff; Funnel conversion | Most contacts at MQL, SQL, or opportunity stages have no associated deal in this snapshot, so funnel conversion and marketing-sourced pipeline coverage cannot be read confidently without confirming the intended handoff model. | [CSV](evidence/lifecycle_funnel.csv) · [measurement](processed/measurements/lifecycle_funnel.json) |
| **Contacts Without Company Association**<br><small>contacts_without_company_association</small> | High | 80 of 360 records (22.2%) | Account coverage; Sales handoff; Account attribution | In an ABM-heavy CRM, contacts without a company association cannot participate reliably in account rollups, account-level attribution, or account ownership reporting. | [CSV](evidence/association_architecture.csv) · [measurement](processed/measurements/association_architecture.json) |
| **Recent Original Source Capture Gap**<br>**HubSpot property: Original Source (hs_analytics_source)**<br><small>recent_original_source_capture_gap</small> | High | 40 of 180 records (22.2%) | Attribution reporting; Budget allocation | Recent contact cohorts have materially weaker original-source coverage, so marketing cannot reliably compare newer acquisition cohorts or explain source mix into pipeline. | [CSV](evidence/attribution_trust.csv) · [measurement](processed/measurements/attribution_trust.json) |

### Priority 2 — Structural trust gaps

| Finding | Severity | Evidence sample | Decisions affected | What it can distort | Evidence |
|---|---|---:|---|---|---|
| **Similar Source Field Name Candidates**<br><small>similar_source_field_name_candidates</small> | Medium | 11 of 17 records (64.7%) | Reporting consistency; Data governance | Eleven source-like property name groups are collision candidates; without a confirmed canonical mapping, workflows and reports may read different fields for the same business concept. | [CSV](evidence/property_governance.csv) · [measurement](processed/measurements/property_governance.json) |
| **Decayed Source Field Candidates**<br><small>decayed_source_field_candidates</small> | Medium | 3 of 17 records (17.6%) | Reporting consistency; Data governance | Three source-like properties are populated historically but not in the recent half, which creates a legacy-field risk and can fragment attribution logic over time. | [CSV](evidence/property_governance.csv) · [measurement](processed/measurements/property_governance.json) |
| **Deals Without Amount**<br>**HubSpot property: Amount (amount)**<br><small>deals_without_amount</small> | Medium | 6 of 36 records (16.7%) | Forecast confidence; Pipeline reporting | Deals without amount cannot contribute a complete value-weighted view of marketing-sourced pipeline. | [CSV](evidence/pipeline_hygiene.csv) · [measurement](processed/measurements/pipeline_hygiene.json) |
| **Deals Without Contact Association**<br><small>deals_without_contact_association</small> | Medium | 6 of 36 records (16.7%) | Account coverage; Sales handoff; Account attribution | Deals without an associated contact break the contact-to-revenue path used to connect marketing engagement with pipeline outcomes. | [CSV](evidence/association_architecture.csv) · [measurement](processed/measurements/association_architecture.json) |
| **Open Deals Past Close Date**<br>**HubSpot property: Close Date (closedate)**<br><small>open_deals_past_close_date</small> | Medium | 3 of 20 records (15.0%) | Forecast confidence; Pipeline reporting | Open deals whose close date is already past can make the pipeline used for marketing-to-revenue reporting appear more current or more attainable than the CRM supports. | [CSV](evidence/pipeline_hygiene.csv) · [measurement](processed/measurements/pipeline_hygiene.json) |
| **Duplicate Company Domain Candidates**<br>**HubSpot property: Domain (domain)**<br><small>duplicate_company_domain_candidates</small> | Medium | 8 of 55 records (14.5%) | Account coverage; Sales handoff; Account attribution | 8 companies share a domain with another company and are duplicate candidates; if they are not intentional subsidiaries or regional entities, account rollups and attribution may be split. | [CSV](evidence/association_architecture.csv) · [measurement](processed/measurements/association_architecture.json) |
| **Deals Without Company Association**<br><small>deals_without_company_association</small> | Medium | 4 of 36 records (11.1%) | Account coverage; Sales handoff; Account attribution | Deals without a company association can be omitted from account-level pipeline reporting and make ABM influence harder to reconcile. | [CSV](evidence/association_architecture.csv) · [measurement](processed/measurements/association_architecture.json) |
| **Deals Without Owner**<br>**HubSpot property: Deal owner (hubspot_owner_id)**<br><small>deals_without_owner</small> | Medium | 4 of 36 records (11.1%) | Forecast confidence; Pipeline reporting | Unowned deals weaken accountability and make pipeline segmentation by sales owner incomplete. | [CSV](evidence/pipeline_hygiene.csv) · [measurement](processed/measurements/pipeline_hygiene.json) |
| **Deals In Unknown Pipeline**<br>**HubSpot property: Pipeline (pipeline)**<br><small>deals_in_unknown_pipeline</small> | Medium | 2 of 36 records (5.6%) | Forecast confidence; Pipeline reporting | Deals referencing an undefined pipeline can fall outside standard pipeline rollups and distort marketing-to-revenue reporting. | [CSV](evidence/pipeline_hygiene.csv) · [measurement](processed/measurements/pipeline_hygiene.json) |

### Priority 3 — Maintenance and hygiene debt

| Finding | Severity | Evidence sample | Decisions affected | What it can distort | Evidence |
|---|---|---:|---|---|---|
| **Companies Without Domain**<br>**HubSpot property: Domain (domain)**<br><small>companies_without_domain</small> | Low | 5 of 60 records (8.3%) | Account coverage; Sales handoff; Account attribution | Companies without a domain are harder to deduplicate, enrich, and reconcile with account-level reporting keys. | [CSV](evidence/association_architecture.csv) · [measurement](processed/measurements/association_architecture.json) |


### Representative HubSpot Companies and Deals

These named records connect material findings to the CRM. Up to three records are shown per finding; the local CSV contains the full mapped set.

#### MQL Plus Contacts Without Deal Trace

- Company: [**Synthetic Account 001**](https://app.hubspot.com/contacts/123456/record/0-2/co001)
- Company: [**Synthetic Account 002**](https://app.hubspot.com/contacts/123456/record/0-2/co002)
- Company: [**Synthetic Account 003**](https://app.hubspot.com/contacts/123456/record/0-2/co003)
- Showing 3 of 50 mapped records; open [the local record evidence CSV](report_record_evidence.csv) for the full set.

#### Deals Without Amount

- Deal: [**Synthetic Opportunity 033**](https://app.hubspot.com/contacts/123456/record/0-3/d033) · Pipeline: **Expansion** · Deal stage: **Closed Lost**
- Deal: [**Synthetic Opportunity 036**](https://app.hubspot.com/contacts/123456/record/0-3/d036) · Pipeline: **legacy_pipeline** · Deal stage: **closedlost**
- Company: [**Synthetic Account 007**](https://app.hubspot.com/contacts/123456/record/0-2/co007) · Deal: [**Synthetic Opportunity 007**](https://app.hubspot.com/contacts/123456/record/0-3/d007) · Pipeline: **New Business** · Deal stage: **Negotiation**
- Showing 3 of 6 mapped records; open [the local record evidence CSV](report_record_evidence.csv) for the full set.

#### Deals Without Contact Association

- Deal: [**Synthetic Opportunity 033**](https://app.hubspot.com/contacts/123456/record/0-3/d033) · Pipeline: **Expansion** · Deal stage: **Closed Lost**
- Deal: [**Synthetic Opportunity 034**](https://app.hubspot.com/contacts/123456/record/0-3/d034) · Pipeline: **Expansion** · Deal stage: **Closed Lost**
- Deal: [**Synthetic Opportunity 035**](https://app.hubspot.com/contacts/123456/record/0-3/d035) · Pipeline: **legacy_pipeline** · Deal stage: **closedlost**
- Showing 3 of 6 mapped records; open [the local record evidence CSV](report_record_evidence.csv) for the full set.

#### Open Deals Past Close Date

- Company: [**Synthetic Account 003**](https://app.hubspot.com/contacts/123456/record/0-2/co003) · Deal: [**Synthetic Opportunity 003**](https://app.hubspot.com/contacts/123456/record/0-3/d003) · Pipeline: **New Business** · Deal stage: **Negotiation**
- Company: [**Synthetic Account 009**](https://app.hubspot.com/contacts/123456/record/0-2/co009) · Deal: [**Synthetic Opportunity 009**](https://app.hubspot.com/contacts/123456/record/0-3/d009) · Pipeline: **New Business** · Deal stage: **Discovery**
- Company: [**Synthetic Account 017**](https://app.hubspot.com/contacts/123456/record/0-2/co017) · Deal: [**Synthetic Opportunity 017**](https://app.hubspot.com/contacts/123456/record/0-3/d017) · Pipeline: **New Business** · Deal stage: **Discovery**

#### Duplicate Company Domain Candidates

- Company: [**Synthetic Account 001**](https://app.hubspot.com/contacts/123456/record/0-2/co001) · Deal: [**Synthetic Opportunity 001**](https://app.hubspot.com/contacts/123456/record/0-3/d001) · Pipeline: **New Business** · Deal stage: **Discovery**
- Company: [**Synthetic Account 002**](https://app.hubspot.com/contacts/123456/record/0-2/co002) · Deal: [**Synthetic Opportunity 002**](https://app.hubspot.com/contacts/123456/record/0-3/d002) · Pipeline: **New Business** · Deal stage: **Proposal**
- Company: [**Synthetic Account 003**](https://app.hubspot.com/contacts/123456/record/0-2/co003) · Deal: [**Synthetic Opportunity 003**](https://app.hubspot.com/contacts/123456/record/0-3/d003) · Pipeline: **New Business** · Deal stage: **Negotiation**
- Showing 3 of 8 mapped records; open [the local record evidence CSV](report_record_evidence.csv) for the full set.

#### Deals Without Company Association

- Deal: [**Synthetic Opportunity 033**](https://app.hubspot.com/contacts/123456/record/0-3/d033) · Pipeline: **Expansion** · Deal stage: **Closed Lost**
- Deal: [**Synthetic Opportunity 034**](https://app.hubspot.com/contacts/123456/record/0-3/d034) · Pipeline: **Expansion** · Deal stage: **Closed Lost**
- Deal: [**Synthetic Opportunity 035**](https://app.hubspot.com/contacts/123456/record/0-3/d035) · Pipeline: **legacy_pipeline** · Deal stage: **closedlost**
- Showing 3 of 4 mapped records; open [the local record evidence CSV](report_record_evidence.csv) for the full set.

#### Deals Without Owner

- Deal: [**Synthetic Opportunity 034**](https://app.hubspot.com/contacts/123456/record/0-3/d034) · Pipeline: **Expansion** · Deal stage: **Closed Lost**
- Company: [**Synthetic Account 011**](https://app.hubspot.com/contacts/123456/record/0-2/co011) · Deal: [**Synthetic Opportunity 011**](https://app.hubspot.com/contacts/123456/record/0-3/d011) · Pipeline: **New Business** · Deal stage: **Negotiation**
- Company: [**Synthetic Account 019**](https://app.hubspot.com/contacts/123456/record/0-2/co019) · Deal: [**Synthetic Opportunity 019**](https://app.hubspot.com/contacts/123456/record/0-3/d019) · Pipeline: **New Business** · Deal stage: **Closed Won**
- Showing 3 of 4 mapped records; open [the local record evidence CSV](report_record_evidence.csv) for the full set.

#### Deals In Unknown Pipeline

- Deal: [**Synthetic Opportunity 035**](https://app.hubspot.com/contacts/123456/record/0-3/d035) · Pipeline: **legacy_pipeline** · Deal stage: **closedlost**
- Deal: [**Synthetic Opportunity 036**](https://app.hubspot.com/contacts/123456/record/0-3/d036) · Pipeline: **legacy_pipeline** · Deal stage: **closedlost**

#### Companies Without Domain

- Company: [**Synthetic Account 056**](https://app.hubspot.com/contacts/123456/record/0-2/co056)
- Company: [**Synthetic Account 057**](https://app.hubspot.com/contacts/123456/record/0-2/co057)
- Company: [**Synthetic Account 059**](https://app.hubspot.com/contacts/123456/record/0-2/co059)
- Showing 3 of 5 mapped records; open [the local record evidence CSV](report_record_evidence.csv) for the full set.


## Root Cause Hypotheses

These are evidence-based hypotheses. Confidence and the question needed for confirmation are shown explicitly.

| Hypothesis | Linked findings | Confidence | Evidence and confirmation |
|---|---|---|---|
| No root cause can be stated confidently from the available evidence | — | — | Confirm operating rules with the CRM owner. |

## Recommended Actions

The audit has already prepared each affected cohort and its evidence. The recommended accountable role reviews the records, makes or authorizes the decision, and records the disposition. It is a recommended business role, not a verified HubSpot owner name.

| Priority | Finding | Human action | Recommended accountable role | Human decision required | Completion condition | Evidence |
|---:|---|---|---|---|---|---|
| P1 | customers_without_closedwon_deal_trace | Approve the Customer-to-Closed Won traceability rule, then review all 15 Customer-stage Contacts and classify each as traceable, valid exception, or lifecycle error. | Marketing and revenue operations owner | Marketing and revenue operations must jointly approve the traceability rule and any correction path | An approved lifecycle-to-revenue rule and a recorded classification for all 15 Customer-stage Contacts. | [CSV](evidence/lifecycle_funnel.csv) |
| P1 | mql_plus_contacts_without_deal_trace | Confirm the sales handoff rule for MQL, SQL, and opportunity contacts, then review the 155 contacts without an associated deal. | Marketing and sales operations owner | Marketing and sales operations must jointly approve the handoff rule and exception criteria | An approved handoff rule and a recorded intentional-pre-deal, create-Deal, or valid-exception decision for all 155 Contacts. | [CSV](evidence/lifecycle_funnel.csv) |
| P1 | contacts_without_company_association | Review the 80 contacts without a Company association and approve an account match or valid no-account exception for each record. | CRM owner | The CRM owner must approve or decline each proposed account match before any association is written | All 80 contacts have an approved account-match decision or documented no-account exception. | [CSV](evidence/association_architecture.csv) |
| P1 | recent_original_source_capture_gap | Approve the canonical Original Source capture rule, then review the 40 recent Contacts missing that property and record a remediation decision or exception. | Marketing operations owner | Marketing operations must approve the canonical rule and each historical remediation decision | An approved source-capture rule and a recorded remediation decision or exception for all 40 Contacts. | [CSV](evidence/attribution_trust.csv) |
| P2 | similar_source_field_name_candidates | Review the 11 source-like property name collision candidates and approve a canonical field map before changing workflows. | CRM governance owner | CRM governance must approve or decline each proposed canonical-field classification before workflows change | An approved canonical property map with a recorded canonical, alias, or distinct-purpose decision for all 11 candidates. | [CSV](evidence/property_governance.csv) |
| P2 | decayed_source_field_candidates | Confirm a canonical-versus-legacy source field map for the 3 decayed source-like property candidates. | Marketing operations owner | Marketing operations must approve each property's canonical, legacy, migrate, or retain classification | A business-approved canonical/legacy map that can guide future workflow governance. | [CSV](evidence/property_governance.csv) |
| P2 | deals_without_amount | Confirm which deal stages require an amount and review the 6 missing-amount deals against that policy. | Sales operations owner | Sales operations must approve the stage-aware amount rule and each exception before any CRM write | An approved stage-aware amount rule and a recorded amount-required or valid-exception decision for all 6 Deals. | [CSV](evidence/pipeline_hygiene.csv) |
| P2 | deals_without_contact_association | Review the 6 Deals without a Contact association and approve the correct buying contact or a valid no-contact exception for each Deal. | Revenue operations owner | Revenue operations must approve or decline each proposed Contact association before any CRM write | All 6 Deals have an approved Contact-association decision or documented exception. | [CSV](evidence/association_architecture.csv) |
| P2 | open_deals_past_close_date | Review the 3 open Deals with past close dates and approve a revised close date, stage decision, or documented exception for each Deal. | Sales operations owner | Sales operations must approve each close-date or stage decision before any CRM write | A human disposition for each past-date deal and a clearer pipeline reporting baseline. | [CSV](evidence/pipeline_hygiene.csv) |
| P2 | duplicate_company_domain_candidates | Have the account owner review the 8 shared-domain company candidates and record whether each is intentional or duplicate-like. | Account operations owner | Account operations must approve the duplicate, related-account, or valid shared-domain classification for each candidate | A documented decision for each shared-domain candidate and a reliable account-rollup rule. | [CSV](evidence/association_architecture.csv) |
| P2 | deals_without_company_association | Review the 4 Deals without a Company association and approve the correct account or a valid no-account exception for each Deal. | Revenue operations owner | Revenue operations must approve or decline each proposed Company association before any CRM write | All 4 Deals have an approved Company-association decision or documented exception. | [CSV](evidence/association_architecture.csv) |
| P2 | deals_without_owner | Review the 4 unowned Deals and approve the accountable owner or a valid unassigned exception for each Deal. | Sales operations owner | Sales operations must approve or decline each proposed Deal owner before any CRM write | All 4 Deals have an approved owner decision or documented unassigned exception. | [CSV](evidence/pipeline_hygiene.csv) |
| P2 | deals_in_unknown_pipeline | Ask a CRM administrator to determine the intended pipeline for the 2 affected deals before any manual correction. | CRM administrator | The CRM administrator must approve the intended Pipeline for each Deal before any CRM write | A documented pipeline decision for the affected deals and a consistent pipeline rollup. | [CSV](evidence/pipeline_hygiene.csv) |
| P3 | companies_without_domain | Review the 5 Companies without a domain and approve a verified domain or a valid no-domain exception for each Company. | CRM owner | The CRM owner must approve or decline each proposed domain before any CRM write | All 5 Companies have an approved verified domain or documented no-domain exception. | [CSV](evidence/association_architecture.csv) |

## What This Audit Cannot Determine

- Record age is based on the last-modified timestamp. It does not prove that a person, marketing program, or sales representative actively engaged with the record.
- A long or resumed full-history extract is a close operational snapshot, not a database transaction taken at one instant.
- This synthetic demonstration measures CRM reporting trust, not business performance.

## Evidence and Supporting Files

- Attribution Trust: [evidence CSV](evidence/attribution_trust.csv) · [measurement file](processed/measurements/attribution_trust.json)
- Lifecycle Funnel: [evidence CSV](evidence/lifecycle_funnel.csv) · [measurement file](processed/measurements/lifecycle_funnel.json)
- Association Architecture: [evidence CSV](evidence/association_architecture.csv) · [measurement file](processed/measurements/association_architecture.json)
- Pipeline Hygiene: [evidence CSV](evidence/pipeline_hygiene.csv) · [measurement file](processed/measurements/pipeline_hygiene.json)
- Property Governance: [evidence CSV](evidence/property_governance.csv) · [measurement file](processed/measurements/property_governance.json)
- [Validated findings](findings.json)
- [Mapped Company and Deal evidence](report_record_evidence.csv)
- [Operator appendix](operator_appendix.md)
- [Schema discovery report](schema_discovery_report.md)

## Next Review

Re-run after the approved source-capture, association, and Deal governance changes have operated for one complete reporting cycle.

## Sharing the Report

This HTML file is generated locally. It is not a public URL, and its supporting-file links work only when the related output folder stays together.

**Treat this as a confidential CRM report.** It can contain identifiable HubSpot Company and Deal names plus direct record links. For a fixed copy, choose **Print → Save as PDF**, then share the PDF only with authorized recipients through an approved channel. If you share interactive HTML, keep the complete report package together, use approved access-controlled hosting or file sharing, and never include the raw data folder, environment files, or secrets.

---

Smartify Marketing · For more marketing systems insights and updates: [smartifymarketing.com](https://smartifymarketing.com) · [GitHub](https://github.com/AliceEinstein)
