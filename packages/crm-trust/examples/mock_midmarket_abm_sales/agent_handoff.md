# Agent Handoff: CRM Trust Audit Follow-up

## Safety Boundary

This audit was generated in read-only mode. No CRM write actions are allowed unless the user explicitly provides write access and approves a concrete implementation plan. The current run used synthetic local data and performed no CRM writes.

Agents consuming this handoff must use the linked findings, recommendations, measurement files, and hashed evidence only. Do not read `raw/` or attempt to reconstruct identity values.

## Approved Low-Risk Follow-ups

These are actual deliverables an implementation or operations agent may prepare without changing CRM truth:

| Deliverable | Direct basis | Why it is safe | Output to produce |
|---|---|---|---|
| Account-association review queue | 80/360 contacts lack company; 4/36 deals lack company; 6/36 deals lack contact | The queue contains hashed evidence and a decision column; it does not choose an association | A CSV or task-list draft linked to [association evidence](evidence/association_architecture.csv) |
| Missing-domain and owner review queues | 5/60 companies lack domain; 4/36 deals lack owner | It surfaces records for an administrator without guessing domains or assignees | Two review lists linked to [association evidence](evidence/association_architecture.csv) and [pipeline evidence](evidence/pipeline_hygiene.csv) |
| Source-capture review-list specification | 40/180 recent contacts lack original source | The artifact defines the cohort and review fields; it does not backfill source history | List criteria and owner instructions linked to [attribution evidence](evidence/attribution_trust.csv) |
| Canonical source-property map | 3/17 source-like fields are decayed candidates; 11/17 collide by name | A mapping document records decisions before workflows are changed | Proposed map with confirmation status linked to [property evidence](evidence/property_governance.csv) |
| Pipeline exception review queue | 3/20 open deals have past close dates; 6/36 lack amount; 2/36 reference an unknown pipeline | The queue preserves current values and asks for a human disposition | Review artifact linked to [pipeline evidence](evidence/pipeline_hygiene.csv) |

The exact recommendation objects, including expected outcomes and decision owners, are in [recommendations.json](recommendations.json). “Draft a list” and “draft a field map” are intentionally treated as concrete safe deliverables, not as vague implementation steps.

## Manual Confirmation Required

| Decision | Evidence | Why the audit cannot decide it |
|---|---|---|
| Does customer lifecycle stage require a closed-won deal? | 15/15 customer-stage contacts lack closed-won trace; [lifecycle evidence](evidence/lifecycle_funnel.csv) | Lifecycle semantics are a business rule, not a universal CRM invariant |
| Which lifecycle stages require a deal? | 155/160 MQL+ contacts lack deal trace; [lifecycle evidence](evidence/lifecycle_funnel.csv) | Some sales motions intentionally keep pre-deal contacts contact-led |
| Which source field is canonical? | Original source 88.9% overall and 77.8% in the recent half; 17 source-like candidates; [attribution evidence](evidence/attribution_trust.csv) and [property evidence](evidence/property_governance.csv) | Backfilling or rewriting historical source changes attribution truth |
| Are shared domains legitimate account structures? | 8/55 domain-populated companies are shared-domain candidates; [association evidence](evidence/association_architecture.csv) | Subsidiaries and regional entities can legitimately share a domain |
| Which deal stages require amount and owner? | 6/36 deals lack amount and 4/36 lack owner; [pipeline evidence](evidence/pipeline_hygiene.csv) | Requiredness depends on the sales process and stage policy |
| What should happen to undefined-pipeline deals? | 2/36 deals reference an undefined pipeline; [pipeline evidence](evidence/pipeline_hygiene.csv) | Moving them changes reporting semantics |

## Blocked Actions

The following actions are prohibited for this read-only audit and require separate human approval and an implementation plan:

- overwrite original source
- merge companies automatically
- delete properties
- move all stale deals
- reset lifecycle stage
- bulk update owner
- change a deal's pipeline, close date, or stage based only on this report

These are guardrails, not instructions to execute any CRM change. The reviewed phrase clearances are hash-bound in [safety_clearance.json](safety_clearance.json).

## Suggested Implementation Sequence

1. Confirm the six business rules above and record the owner for each decision.
2. Use [findings.json](findings.json) to create the review queues, preserving each finding ID and evidence link.
3. Produce the source-property map and mark each candidate as canonical, legacy, intentional parallel field, or unresolved.
4. Have CRM and revenue-operations owners review the association, lifecycle, and pipeline queues.
5. Obtain explicit approval for any write plan through the CRM administrator’s change-management process.
6. Apply approved changes outside this audit skill.
7. Run a new full-history snapshot, compare [snapshot_summary.json](processed/snapshot_summary.json), and re-run the same evidence-backed findings.

## Evidence Files

The evidence files are local, sanitized, and use per-run hashed record identifiers:

- [Consolidated evidence](evidence.csv)
- [Attribution evidence](evidence/attribution_trust.csv)
- [Lifecycle evidence](evidence/lifecycle_funnel.csv)
- [Association evidence](evidence/association_architecture.csv)
- [Pipeline evidence](evidence/pipeline_hygiene.csv)
- [Property governance evidence](evidence/property_governance.csv)
- [Deterministic measurements](processed/measurements/)
- [Snapshot and completeness summary](processed/snapshot_summary.json)
- [Operational recency summary](processed/activity_summary.json)

To verify a recommendation, start with its `finding_id` in [recommendations.json](recommendations.json), open the linked finding in [findings.json](findings.json), open the cited measurement JSON, and then inspect the corresponding rows in the evidence CSV. No raw identity field is needed for this chain.

## Questions to Ask Human Owner Before Any Write Action

- Which source property is authoritative for each report and workflow?
- What business event makes a contact a customer?
- When is a deal required for a lifecycle stage?
- What is the account model for subsidiaries and regional entities?
- Which pipeline, stage, amount, and owner rules are mandatory?
- Which proposed changes are approved, by whom, and how will the post-change audit be verified?
