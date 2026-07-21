# CRM Audit Operator Appendix

## How to Use This Appendix

Use this file to verify findings, inspect sample sizes, and plan approved implementation work. Record identifiers in evidence files are hashed.

## All Validated Findings

### Attribution Trust

| Finding | Severity | Evidence sample | Decisions affected | What it can distort | Evidence |
|---|---|---:|---|---|---|
| **Recent Original Source Capture Gap**<br>**HubSpot property: Original Source (hs_analytics_source)**<br><small>recent_original_source_capture_gap</small> | High | 40 of 180 records (22.2%) | Attribution reporting; Budget allocation | Recent contact cohorts have materially weaker original-source coverage, so marketing cannot reliably compare newer acquisition cohorts or explain source mix into pipeline. | [CSV](evidence/attribution_trust.csv) · [measurement](processed/measurements/attribution_trust.json) |

### Lifecycle Funnel

| Finding | Severity | Evidence sample | Decisions affected | What it can distort | Evidence |
|---|---|---:|---|---|---|
| **Customers Without Closed Won Deal Trace**<br>**HubSpot property: Lifecycle Stage (lifecyclestage)**<br><small>customers_without_closedwon_deal_trace</small> | High | 15 of 15 records (100.0%) | Marketing Qualified Lead (MQL) quality; Sales handoff; Funnel conversion | The customer-stage population cannot be reconciled to closed-won revenue through the captured deal relationships, weakening lifecycle-to-pipeline reporting for a sales-led motion. | [CSV](evidence/lifecycle_funnel.csv) · [measurement](processed/measurements/lifecycle_funnel.json) |
| **MQL Plus Contacts Without Deal Trace**<br>**HubSpot property: Lifecycle Stage (lifecyclestage)**<br><small>mql_plus_contacts_without_deal_trace</small> | High | 155 of 160 records (96.9%) | Marketing Qualified Lead (MQL) quality; Sales handoff; Funnel conversion | Most contacts at MQL, SQL, or opportunity stages have no associated deal in this snapshot, so funnel conversion and marketing-sourced pipeline coverage cannot be read confidently without confirming the intended handoff model. | [CSV](evidence/lifecycle_funnel.csv) · [measurement](processed/measurements/lifecycle_funnel.json) |
#### MQL Plus Contacts Without Deal Trace

- Company: [**Synthetic Account 001**](https://app.hubspot.com/contacts/123456/record/0-2/co001)
- Company: [**Synthetic Account 002**](https://app.hubspot.com/contacts/123456/record/0-2/co002)
- Company: [**Synthetic Account 003**](https://app.hubspot.com/contacts/123456/record/0-2/co003)
- Showing 3 of 50 mapped records; open [the local record evidence CSV](report_record_evidence.csv) for the full set.


### Association Architecture

| Finding | Severity | Evidence sample | Decisions affected | What it can distort | Evidence |
|---|---|---:|---|---|---|
| **Contacts Without Company Association**<br><small>contacts_without_company_association</small> | High | 80 of 360 records (22.2%) | Account coverage; Sales handoff; Account attribution | In an ABM-heavy CRM, contacts without a company association cannot participate reliably in account rollups, account-level attribution, or account ownership reporting. | [CSV](evidence/association_architecture.csv) · [measurement](processed/measurements/association_architecture.json) |
| **Deals Without Contact Association**<br><small>deals_without_contact_association</small> | Medium | 6 of 36 records (16.7%) | Account coverage; Sales handoff; Account attribution | Deals without an associated contact break the contact-to-revenue path used to connect marketing engagement with pipeline outcomes. | [CSV](evidence/association_architecture.csv) · [measurement](processed/measurements/association_architecture.json) |
| **Duplicate Company Domain Candidates**<br>**HubSpot property: Domain (domain)**<br><small>duplicate_company_domain_candidates</small> | Medium | 8 of 55 records (14.5%) | Account coverage; Sales handoff; Account attribution | 8 companies share a domain with another company and are duplicate candidates; if they are not intentional subsidiaries or regional entities, account rollups and attribution may be split. | [CSV](evidence/association_architecture.csv) · [measurement](processed/measurements/association_architecture.json) |
| **Deals Without Company Association**<br><small>deals_without_company_association</small> | Medium | 4 of 36 records (11.1%) | Account coverage; Sales handoff; Account attribution | Deals without a company association can be omitted from account-level pipeline reporting and make ABM influence harder to reconcile. | [CSV](evidence/association_architecture.csv) · [measurement](processed/measurements/association_architecture.json) |
| **Companies Without Domain**<br>**HubSpot property: Domain (domain)**<br><small>companies_without_domain</small> | Low | 5 of 60 records (8.3%) | Account coverage; Sales handoff; Account attribution | Companies without a domain are harder to deduplicate, enrich, and reconcile with account-level reporting keys. | [CSV](evidence/association_architecture.csv) · [measurement](processed/measurements/association_architecture.json) |
#### Deals Without Contact Association

- Deal: [**Synthetic Opportunity 033**](https://app.hubspot.com/contacts/123456/record/0-3/d033) · Pipeline: **Expansion** · Deal stage: **Closed Lost**
- Deal: [**Synthetic Opportunity 034**](https://app.hubspot.com/contacts/123456/record/0-3/d034) · Pipeline: **Expansion** · Deal stage: **Closed Lost**
- Deal: [**Synthetic Opportunity 035**](https://app.hubspot.com/contacts/123456/record/0-3/d035) · Pipeline: **legacy_pipeline** · Deal stage: **closedlost**
- Showing 3 of 6 mapped records; open [the local record evidence CSV](report_record_evidence.csv) for the full set.

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

#### Companies Without Domain

- Company: [**Synthetic Account 056**](https://app.hubspot.com/contacts/123456/record/0-2/co056)
- Company: [**Synthetic Account 057**](https://app.hubspot.com/contacts/123456/record/0-2/co057)
- Company: [**Synthetic Account 059**](https://app.hubspot.com/contacts/123456/record/0-2/co059)
- Showing 3 of 5 mapped records; open [the local record evidence CSV](report_record_evidence.csv) for the full set.


### Pipeline Hygiene

| Finding | Severity | Evidence sample | Decisions affected | What it can distort | Evidence |
|---|---|---:|---|---|---|
| **Deals Without Amount**<br>**HubSpot property: Amount (amount)**<br><small>deals_without_amount</small> | Medium | 6 of 36 records (16.7%) | Forecast confidence; Pipeline reporting | Deals without amount cannot contribute a complete value-weighted view of marketing-sourced pipeline. | [CSV](evidence/pipeline_hygiene.csv) · [measurement](processed/measurements/pipeline_hygiene.json) |
| **Open Deals Past Close Date**<br>**HubSpot property: Close Date (closedate)**<br><small>open_deals_past_close_date</small> | Medium | 3 of 20 records (15.0%) | Forecast confidence; Pipeline reporting | Open deals whose close date is already past can make the pipeline used for marketing-to-revenue reporting appear more current or more attainable than the CRM supports. | [CSV](evidence/pipeline_hygiene.csv) · [measurement](processed/measurements/pipeline_hygiene.json) |
| **Deals Without Owner**<br>**HubSpot property: Deal owner (hubspot_owner_id)**<br><small>deals_without_owner</small> | Medium | 4 of 36 records (11.1%) | Forecast confidence; Pipeline reporting | Unowned deals weaken accountability and make pipeline segmentation by sales owner incomplete. | [CSV](evidence/pipeline_hygiene.csv) · [measurement](processed/measurements/pipeline_hygiene.json) |
| **Deals In Unknown Pipeline**<br>**HubSpot property: Pipeline (pipeline)**<br><small>deals_in_unknown_pipeline</small> | Medium | 2 of 36 records (5.6%) | Forecast confidence; Pipeline reporting | Deals referencing an undefined pipeline can fall outside standard pipeline rollups and distort marketing-to-revenue reporting. | [CSV](evidence/pipeline_hygiene.csv) · [measurement](processed/measurements/pipeline_hygiene.json) |
#### Deals Without Amount

- Deal: [**Synthetic Opportunity 033**](https://app.hubspot.com/contacts/123456/record/0-3/d033) · Pipeline: **Expansion** · Deal stage: **Closed Lost**
- Deal: [**Synthetic Opportunity 036**](https://app.hubspot.com/contacts/123456/record/0-3/d036) · Pipeline: **legacy_pipeline** · Deal stage: **closedlost**
- Company: [**Synthetic Account 007**](https://app.hubspot.com/contacts/123456/record/0-2/co007) · Deal: [**Synthetic Opportunity 007**](https://app.hubspot.com/contacts/123456/record/0-3/d007) · Pipeline: **New Business** · Deal stage: **Negotiation**
- Showing 3 of 6 mapped records; open [the local record evidence CSV](report_record_evidence.csv) for the full set.

#### Open Deals Past Close Date

- Company: [**Synthetic Account 003**](https://app.hubspot.com/contacts/123456/record/0-2/co003) · Deal: [**Synthetic Opportunity 003**](https://app.hubspot.com/contacts/123456/record/0-3/d003) · Pipeline: **New Business** · Deal stage: **Negotiation**
- Company: [**Synthetic Account 009**](https://app.hubspot.com/contacts/123456/record/0-2/co009) · Deal: [**Synthetic Opportunity 009**](https://app.hubspot.com/contacts/123456/record/0-3/d009) · Pipeline: **New Business** · Deal stage: **Discovery**
- Company: [**Synthetic Account 017**](https://app.hubspot.com/contacts/123456/record/0-2/co017) · Deal: [**Synthetic Opportunity 017**](https://app.hubspot.com/contacts/123456/record/0-3/d017) · Pipeline: **New Business** · Deal stage: **Discovery**

#### Deals Without Owner

- Deal: [**Synthetic Opportunity 034**](https://app.hubspot.com/contacts/123456/record/0-3/d034) · Pipeline: **Expansion** · Deal stage: **Closed Lost**
- Company: [**Synthetic Account 011**](https://app.hubspot.com/contacts/123456/record/0-2/co011) · Deal: [**Synthetic Opportunity 011**](https://app.hubspot.com/contacts/123456/record/0-3/d011) · Pipeline: **New Business** · Deal stage: **Negotiation**
- Company: [**Synthetic Account 019**](https://app.hubspot.com/contacts/123456/record/0-2/co019) · Deal: [**Synthetic Opportunity 019**](https://app.hubspot.com/contacts/123456/record/0-3/d019) · Pipeline: **New Business** · Deal stage: **Closed Won**
- Showing 3 of 4 mapped records; open [the local record evidence CSV](report_record_evidence.csv) for the full set.

#### Deals In Unknown Pipeline

- Deal: [**Synthetic Opportunity 035**](https://app.hubspot.com/contacts/123456/record/0-3/d035) · Pipeline: **legacy_pipeline** · Deal stage: **closedlost**
- Deal: [**Synthetic Opportunity 036**](https://app.hubspot.com/contacts/123456/record/0-3/d036) · Pipeline: **legacy_pipeline** · Deal stage: **closedlost**


### Property Governance

| Finding | Severity | Evidence sample | Decisions affected | What it can distort | Evidence |
|---|---|---:|---|---|---|
| **Similar Source Field Name Candidates**<br><small>similar_source_field_name_candidates</small> | Medium | 11 of 17 records (64.7%) | Reporting consistency; Data governance | Eleven source-like property name groups are collision candidates; without a confirmed canonical mapping, workflows and reports may read different fields for the same business concept. | [CSV](evidence/property_governance.csv) · [measurement](processed/measurements/property_governance.json) |
| **Decayed Source Field Candidates**<br><small>decayed_source_field_candidates</small> | Medium | 3 of 17 records (17.6%) | Reporting consistency; Data governance | Three source-like properties are populated historically but not in the recent half, which creates a legacy-field risk and can fragment attribution logic over time. | [CSV](evidence/property_governance.csv) · [measurement](processed/measurements/property_governance.json) |

## Detailed Recommendations

## Human review and disposition

### contacts_without_company_association

- **Human action:** Review the 80 contacts without a Company association and approve an account match or valid no-account exception for each record.
- **Why:** 80 of 360 Contacts (22.2%) have no Company association.
- **Recommended accountable role:** CRM owner
- **Human decision required:** The CRM owner must approve or decline each proposed account match before any association is written
- **Exact scope:** 80 contacts in evidence/association_architecture.csv without a Company association
- **Current state:** contacts_without_company: 80 of 360 contacts (22.2%).
- **Desired state:** Each affected contact has an approved account-match decision or documented no-account exception.
- **Implementation:**
  1. Open the audit-prepared evidence cohort.
  2. Review the available Company evidence for each contact.
  3. Approve an account match or document a valid no-account exception; authorize any later CRM association separately.
- **Completion condition:** All 80 contacts have an approved account-match decision or documented no-account exception.
- **Success measure:** 80 of 80 contacts have a recorded match decision or exception.
- **Evidence:** [evidence CSV](evidence/association_architecture.csv)

### deals_without_company_association

- **Human action:** Review the 4 Deals without a Company association and approve the correct account or a valid no-account exception for each Deal.
- **Why:** 4 of 36 Deals (11.1%) have no Company association.
- **Recommended accountable role:** Revenue operations owner
- **Human decision required:** Revenue operations must approve or decline each proposed Company association before any CRM write
- **Exact scope:** 4 Deals in evidence/association_architecture.csv without a Company association
- **Current state:** deals_without_company: 4 of 36 deals (11.1%).
- **Desired state:** Each affected Deal has an approved Company-association decision or documented exception.
- **Implementation:**
  1. Open the audit-prepared evidence cohort.
  2. Review the available Company evidence for each Deal.
  3. Approve the correct Company or document an exception; authorize any later association write separately.
- **Completion condition:** All 4 Deals have an approved Company-association decision or documented exception.
- **Success measure:** 4 of 4 Deals have a recorded Company-association decision or exception.
- **Evidence:** [evidence CSV](evidence/association_architecture.csv)

### deals_without_contact_association

- **Human action:** Review the 6 Deals without a Contact association and approve the correct buying contact or a valid no-contact exception for each Deal.
- **Why:** 6 of 36 Deals (16.7%) have no Contact association.
- **Recommended accountable role:** Revenue operations owner
- **Human decision required:** Revenue operations must approve or decline each proposed Contact association before any CRM write
- **Exact scope:** 6 Deals in evidence/association_architecture.csv without a Contact association
- **Current state:** deals_without_contact: 6 of 36 deals (16.7%).
- **Desired state:** Each affected Deal has an approved Contact-association decision or documented exception.
- **Implementation:**
  1. Open the audit-prepared evidence cohort.
  2. Review the buying-contact evidence for each Deal.
  3. Approve a Contact association or document a valid exception; authorize any later CRM association separately.
- **Completion condition:** All 6 Deals have an approved Contact-association decision or documented exception.
- **Success measure:** 6 of 6 Deals have a recorded Contact-association decision or exception.
- **Evidence:** [evidence CSV](evidence/association_architecture.csv)

### companies_without_domain

- **Human action:** Review the 5 Companies without a domain and approve a verified domain or a valid no-domain exception for each Company.
- **Why:** 5 of 60 Companies (8.3%) have no domain.
- **Recommended accountable role:** CRM owner
- **Human decision required:** The CRM owner must approve or decline each proposed domain before any CRM write
- **Exact scope:** 5 Companies in evidence/association_architecture.csv without a domain
- **Current state:** companies_without_domain: 5 of 60 companies (8.3%).
- **Desired state:** Each affected Company has a verified domain decision or documented exception.
- **Implementation:**
  1. Open the audit-prepared evidence cohort.
  2. Verify a domain from an approved source or document why no domain applies.
  3. Approve or decline the proposed value before any CRM write.
- **Completion condition:** All 5 Companies have an approved verified domain or documented no-domain exception.
- **Success measure:** 5 of 5 Companies have a recorded verified-domain decision or exception.
- **Evidence:** [evidence CSV](evidence/association_architecture.csv)

### deals_without_owner

- **Human action:** Review the 4 unowned Deals and approve the accountable owner or a valid unassigned exception for each Deal.
- **Why:** 4 of 36 Deals (11.1%) have no Deal owner.
- **Recommended accountable role:** Sales operations owner
- **Human decision required:** Sales operations must approve or decline each proposed Deal owner before any CRM write
- **Exact scope:** 4 Deals in evidence/pipeline_hygiene.csv without a Deal owner
- **Current state:** deals_without_owner: 4 of 36 deals (11.1%).
- **Desired state:** Each affected Deal has an approved owner decision or documented unassigned exception.
- **Implementation:**
  1. Open the audit-prepared evidence cohort.
  2. Review territory, account, and pipeline ownership evidence for each Deal.
  3. Approve an owner or document an unassigned exception; authorize any later owner write separately.
- **Completion condition:** All 4 Deals have an approved owner decision or documented unassigned exception.
- **Success measure:** 4 of 4 Deals have a recorded owner decision or exception.
- **Evidence:** [evidence CSV](evidence/pipeline_hygiene.csv)

## Business rule confirmation

### recent_original_source_capture_gap

- **Human action:** Approve the canonical Original Source capture rule, then review the 40 recent Contacts missing that property and record a remediation decision or exception.
- **Why:** 40 of 180 recent Contacts (22.2%) are missing Original Source.
- **Recommended accountable role:** Marketing operations owner
- **Human decision required:** Marketing operations must approve the canonical rule and each historical remediation decision
- **Exact scope:** Original Source governance and 40 Contacts in evidence/attribution_trust.csv missing that property
- **Current state:** recent_half_contacts_missing_original_source: 40 of 180 recent contacts (22.2%).
- **Desired state:** The canonical rule is approved and every affected Contact has a remediation decision or exception.
- **Implementation:**
  1. Review the audit-prepared evidence cohort and proposed source-capture rule.
  2. Approve or revise the canonical rule.
  3. Review all 40 Contacts and record a remediation decision or exception before any backfill.
- **Completion condition:** An approved source-capture rule and a recorded remediation decision or exception for all 40 Contacts.
- **Success measure:** The rule is approved and 40 of 40 Contacts have a recorded disposition.
- **Evidence:** [evidence CSV](evidence/attribution_trust.csv)

### customers_without_closedwon_deal_trace

- **Human action:** Approve the Customer-to-Closed Won traceability rule, then review all 15 Customer-stage Contacts and classify each as traceable, valid exception, or lifecycle error.
- **Why:** 15 of 15 Customer-stage Contacts (100.0%) have no visible Closed Won Deal trace.
- **Recommended accountable role:** Marketing and revenue operations owner
- **Human decision required:** Marketing and revenue operations must jointly approve the traceability rule and any correction path
- **Exact scope:** Customer lifecycle-stage policy and 15 Customer-stage Contacts in evidence/lifecycle_funnel.csv
- **Current state:** customers_without_closedwon_deal: 15 of 15 customer-stage contacts (100.0%).
- **Desired state:** The traceability rule is approved and each affected Contact is classified with evidence.
- **Implementation:**
  1. Review the audit-prepared Contact and Deal evidence.
  2. Approve the Customer-to-Closed Won traceability rule and valid exception criteria.
  3. Classify all 15 Contacts before authorizing any lifecycle-stage or association correction.
- **Completion condition:** An approved lifecycle-to-revenue rule and a recorded classification for all 15 Customer-stage Contacts.
- **Success measure:** The rule is approved and 15 of 15 Contacts have a recorded classification.
- **Evidence:** [evidence CSV](evidence/lifecycle_funnel.csv)

### mql_plus_contacts_without_deal_trace

- **Human action:** Confirm the sales handoff rule for MQL, SQL, and opportunity contacts, then review the 155 contacts without an associated deal.
- **Why:** 155 of 160 MQL, SQL, or Opportunity Contacts (96.9%) have no visible Deal trace.
- **Recommended accountable role:** Marketing and sales operations owner
- **Human decision required:** Marketing and sales operations must jointly approve the handoff rule and exception criteria
- **Exact scope:** MQL/SQL/opportunity handoff policy and 155 Contacts in evidence/lifecycle_funnel.csv without a Deal trace
- **Current state:** mql_plus_contacts_without_deal: 155 of 160 MQL+ contacts (96.9%).
- **Desired state:** The handoff rule is approved and every affected Contact has a documented Deal-path decision.
- **Implementation:**
  1. Review the audit-prepared cohort by lifecycle stage and owner status.
  2. Approve the sales handoff rule and valid pre-Deal exceptions.
  3. Classify all 155 Contacts as intentional pre-Deal, create-Deal candidate, or valid exception.
- **Completion condition:** An approved handoff rule and a recorded intentional-pre-deal, create-Deal, or valid-exception decision for all 155 Contacts.
- **Success measure:** The handoff rule is approved and 155 of 155 Contacts have a recorded Deal-path decision.
- **Evidence:** [evidence CSV](evidence/lifecycle_funnel.csv)

### duplicate_company_domain_candidates

- **Human action:** Have the account owner review the 8 shared-domain company candidates and record whether each is intentional or duplicate-like.
- **Why:** 8 of 55 domain-populated Companies (14.5%) share a domain with another Company.
- **Recommended accountable role:** Account operations owner
- **Human decision required:** Account operations must approve the duplicate, related-account, or valid shared-domain classification for each candidate
- **Exact scope:** Review scope in evidence/association_architecture.csv
- **Current state:** duplicate_company_domain_candidates: 8 of 55 domain-populated companies (14.5%).
- **Desired state:** A documented decision for each shared-domain candidate and a reliable account-rollup rule.
- **Implementation:**
  1. Have the account owner review the 8 shared-domain company candidates and record whether each is intentional or duplicate-like.
- **Completion condition:** A documented decision for each shared-domain candidate and a reliable account-rollup rule.
- **Success measure:** A documented decision for each shared-domain candidate and a reliable account-rollup rule.
- **Evidence:** [evidence CSV](evidence/association_architecture.csv)

### deals_without_amount

- **Human action:** Confirm which deal stages require an amount and review the 6 missing-amount deals against that policy.
- **Why:** 6 of 36 Deals (16.7%) have no Amount.
- **Recommended accountable role:** Sales operations owner
- **Human decision required:** Sales operations must approve the stage-aware amount rule and each exception before any CRM write
- **Exact scope:** Deal amount policy and 6 Deals in evidence/pipeline_hygiene.csv without an amount
- **Current state:** deals_without_amount: 6 of 36 deals (16.7%).
- **Desired state:** The amount rule is approved and every affected Deal has a documented decision.
- **Implementation:**
  1. Review the audit-prepared cohort by Pipeline and Deal stage.
  2. Approve the stages that require an amount and valid exception criteria.
  3. Review all 6 Deals and record whether an amount is required or an exception applies.
- **Completion condition:** An approved stage-aware amount rule and a recorded amount-required or valid-exception decision for all 6 Deals.
- **Success measure:** The amount rule is approved and 6 of 6 Deals have a recorded decision.
- **Evidence:** [evidence CSV](evidence/pipeline_hygiene.csv)

### decayed_source_field_candidates

- **Human action:** Confirm a canonical-versus-legacy source field map for the 3 decayed source-like property candidates.
- **Why:** 3 of 17 source-like properties (17.6%) show historical usage but no recent usage.
- **Recommended accountable role:** Marketing operations owner
- **Human decision required:** Marketing operations must approve each property's canonical, legacy, migrate, or retain classification
- **Exact scope:** Review scope in evidence/property_governance.csv
- **Current state:** decayed_source_fields: 3 of 17 source-like fields (17.6%) show older-half usage with no recent-half usage.
- **Desired state:** A business-approved canonical/legacy map that can guide future workflow governance.
- **Implementation:**
  1. Confirm a canonical-versus-legacy source field map for the 3 decayed source-like property candidates.
- **Completion condition:** A business-approved canonical/legacy map that can guide future workflow governance.
- **Success measure:** A business-approved canonical/legacy map that can guide future workflow governance.
- **Evidence:** [evidence CSV](evidence/property_governance.csv)

### similar_source_field_name_candidates

- **Human action:** Review the 11 source-like property name collision candidates and approve a canonical field map before changing workflows.
- **Why:** 11 of 17 source-like properties (64.7%) are name-collision candidates.
- **Recommended accountable role:** CRM governance owner
- **Human decision required:** CRM governance must approve or decline each proposed canonical-field classification before workflows change
- **Exact scope:** Review scope in evidence/property_governance.csv
- **Current state:** similar_name_field_groups: 11 of 17 source-like fields (64.7%) are name-collision candidates.
- **Desired state:** Each candidate has an approved canonical, alias, or distinct-purpose classification.
- **Implementation:**
  1. Review the 11 source-like property name collision candidates and approve a canonical field map before changing workflows.
- **Completion condition:** An approved canonical property map with a recorded canonical, alias, or distinct-purpose decision for all 11 candidates.
- **Success measure:** 11 of 11 candidates have an approved classification in the canonical property map.
- **Evidence:** [evidence CSV](evidence/property_governance.csv)

## Explicit approval before a CRM change

### open_deals_past_close_date

- **Human action:** Review the 3 open Deals with past close dates and approve a revised close date, stage decision, or documented exception for each Deal.
- **Why:** 3 of 20 open Deals (15.0%) have a past Close Date.
- **Recommended accountable role:** Sales operations owner
- **Human decision required:** Sales operations must approve each close-date or stage decision before any CRM write
- **Exact scope:** Review scope in evidence/pipeline_hygiene.csv
- **Current state:** open_deals_past_close_date: 3 of 20 open deals (15.0%).
- **Desired state:** A human disposition for each past-date deal and a clearer pipeline reporting baseline.
- **Implementation:**
  1. Open the audit-prepared evidence cohort.
  2. Ask the accountable Deal owner to confirm the current next step and timing.
  3. Approve a revised close date, stage decision, or exception before any CRM write.
- **Completion condition:** A human disposition for each past-date deal and a clearer pipeline reporting baseline.
- **Success measure:** A human disposition for each past-date deal and a clearer pipeline reporting baseline.
- **Evidence:** [evidence CSV](evidence/pipeline_hygiene.csv)

### deals_in_unknown_pipeline

- **Human action:** Ask a CRM administrator to determine the intended pipeline for the 2 affected deals before any manual correction.
- **Why:** 2 of 36 Deals (5.6%) reference a Pipeline not present in the captured definitions.
- **Recommended accountable role:** CRM administrator
- **Human decision required:** The CRM administrator must approve the intended Pipeline for each Deal before any CRM write
- **Exact scope:** Review scope in evidence/pipeline_hygiene.csv
- **Current state:** deals_in_unknown_pipeline: 2 of 36 deals (5.6%) reference an undefined pipeline.
- **Desired state:** A documented pipeline decision for the affected deals and a consistent pipeline rollup.
- **Implementation:**
  1. Ask a CRM administrator to determine the intended pipeline for the 2 affected deals before any manual correction.
- **Completion condition:** A documented pipeline decision for the affected deals and a consistent pipeline rollup.
- **Success measure:** A documented pipeline decision for the affected deals and a consistent pipeline rollup.
- **Evidence:** [evidence CSV](evidence/pipeline_hygiene.csv)

## Evidence Index

- Attribution Trust: [evidence CSV](evidence/attribution_trust.csv) · [measurement file](processed/measurements/attribution_trust.json)
- Lifecycle Funnel: [evidence CSV](evidence/lifecycle_funnel.csv) · [measurement file](processed/measurements/lifecycle_funnel.json)
- Association Architecture: [evidence CSV](evidence/association_architecture.csv) · [measurement file](processed/measurements/association_architecture.json)
- Pipeline Hygiene: [evidence CSV](evidence/pipeline_hygiene.csv) · [measurement file](processed/measurements/pipeline_hygiene.json)
- Property Governance: [evidence CSV](evidence/property_governance.csv) · [measurement file](processed/measurements/property_governance.json)
- [Consolidated evidence CSV](evidence.csv)
- [Mapped Company and Deal evidence](report_record_evidence.csv)
- [Validated findings JSON](findings.json)
- [Score calculation](score.json)

## Schema and Context Files

- [CRM context map](crm_context.yaml)
- [Schema discovery report](schema_discovery_report.md)
- [Business context](business_context.json)
- [Audit profile](audit_profile.json)

## Method and Audit Constraints

- Record age is based on the last-modified timestamp. It does not prove that a person, marketing program, or sales representative actively engaged with the record.
- A long or resumed full-history extract is a close operational snapshot, not a database transaction taken at one instant.
- This synthetic demonstration measures CRM reporting trust, not business performance.
