# Lifecycle Integrity Audit — design contract

This skill is a local-first, read-only HubSpot workflow. This document is the
authoritative statement of required behavior, required outputs, and non-goals
for the skill package.

## Required behavior

- Fetch HubSpot data once through a local Private App token and never write to
  HubSpot.
- Sanitize and profile the local snapshot before any LLM role sees it.
- Infer CRM field intent and discover multiple revenue journeys before auditing
  lifecycle integrity.
- Keep the executive report journey-first: identify the selling motion, show
  evidence for its operating path, locate journey-specific breakpoints, and
  separate immediate pipeline recovery from system repair. General CRM-health
  profiling is supporting appendix material, not the main purpose.
- Use HubSpot objects and properties only. Signals originating in another tool
  are in scope only after they are synced into a HubSpot property.
- Maintain a Journey Pattern Registry with numeric confidence and explicit
  contradictions and human-confirmation needs.
- Run pattern-specific checks for lifecycle, handoff, association, attribution,
  state coherence, and outliers.
- In the same acquisition pass, optionally read workflow configuration and
  aggregate workflow performance with one token carrying the automation scope.
  Deterministically map sanitized workflow controls and score-like property
  outputs to lifecycle measurements, so a leak can be investigated for a
  configuration root cause without changing the existing lifecycle score.
- Run an automation/scoring analysis role and a root-cause role after
  candidate findings and before reviewer adjudication. These roles may only
  classify evidence as configuration, possible cause, probable cause, or
  unverified; they may not invent full score-model logic or turn absence of
  access into absence of a control.
- Require evidence and a denominator for every scored finding.
- Route findings through data-fidelity, journey-mapping, logic,
  false-positive, and privacy/safety review as risk requires.
- Compute scores deterministically and route recommendations into priority,
  safe operational, human confirmation, observations, and do-not-auto-fix
  lanes.
- Consolidate candidate findings and reviewer decisions with deterministic
  code, and validate every agent workspace artifact against the task
  manifest's declared schema before the final gate passes.
- Keep raw snapshots local and gitignored; final artifacts contain aggregates,
  redacted values, and per-run hashed IDs only.
- Make every deal and pipeline claim traceable. Aggregate commercial amounts
  only from existing deals. Contacts without deals may form a potential
  recoverable pipeline population but never receive an estimated amount.
- Reconcile the five configured journey hypotheses in the mixed-motion role.
  Residual signals may create a human-confirmation-only unclassified motion
  observation, never a registered/scored journey or leakage audit.

## Required outputs

`lifecycle_integrity_report.md`, `lifecycle_integrity_report.html`,
`operator_appendix.md`, `journey_map.md`,
`journey_pattern_registry.json`, `findings.json`, `recommendations.md`,
`agent_handoff.md`, `outlier_registry.csv`, `evidence.csv`, `crm_context.yaml`,
`schema_discovery_report.md`, `review_trace.json`, and `audit_log.json`.
The run also emits sanitized automation/scoring artifacts and
automation_evidence.csv; the report keeps the existing nine top-level
sections and adds the new layer inside executive, root-cause, appendix, and
limits views.

## Explicit non-goals

No CRM cleanup, record merge/delete/update, lifecycle or deal-stage changes,
owner reassignment, workflow/list/campaign modification, workflow enrollment,
score-model changes, SaaS login, hosted
third-party data services, raw CRM upload, full migration audit,
ad-performance audit, or sales-forecast audit.
