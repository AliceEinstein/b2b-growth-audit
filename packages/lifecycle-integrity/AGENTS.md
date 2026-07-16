# Security red line: never read `outputs/*/raw/` as an agent or LLM role.
# Raw contains owner-authorized CRM PII used only by deterministic fetch and
# profiling code. Agents use `processed/`, `evidence/`, and validated registries.

# Agent Instructions

You are working on a local-first, read-only HubSpot Lifecycle Integrity Audit
skill. Discover the portal's actual revenue journeys before auditing them. Do
not assume one linear funnel.

Do not add HubSpot write functions in v1. Do not add scripts that update,
merge, delete, overwrite, stage-change, or reassign HubSpot records. The client
in `connectors/hubspot/client.py` enforces a read-endpoint allowlist; do not
weaken or bypass it.

Do not print API tokens or include raw PII in processed artifacts or final
reports. Identity values may exist only in the local raw snapshot. Use
aggregates, redaction, and per-run salted record hashes downstream.

Use deterministic code for data fetching, sanitization, profiling, metrics,
journey confidence arithmetic, scoring, adjudication, and safety validation.
Use agent reasoning for custom-property intent, journey interpretation,
ambiguity, outlier classification, severity, review, and recommendation
phrasing—always from structured artifacts, never raw records.

Every scored finding must cite evidence. Missing or ambiguous evidence becomes
an observation or `requires_human_confirmation`. Missing MQL is not a defect
for outbound or expansion journeys by default. An outlier is not an issue until
classified.

If a recommendation requires business judgment, route it to human
confirmation. If it could alter CRM truth, route it to `do_not_auto_fix`.

The audit scope is lifecycle integrity and marketing-to-pipeline journey trust,
not full CRM cleanup, migration, sales forecasting, or channel performance.
