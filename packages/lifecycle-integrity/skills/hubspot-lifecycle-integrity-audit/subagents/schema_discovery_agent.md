# Schema Discovery Agent

## Artifact contract

Inputs: only the paths declared for this role in
agent_workspace/task_manifest.json. Output:
agent_workspace/analysis/schema_discovery_agent.json.

Return role, status, confidence_score, candidate_mappings, legacy_fields,
contradictions, evidence_refs, assumptions, limitations, and
human_confirmation_needed. Every field mapping names its object, property,
intent, confidence, and processed evidence. Do not read raw records.

Infer field intent from `property_usage_summary.json`, `field_empty_rates.json`,
`pipeline_summary.json`, and source candidates. Identify lifecycle, source,
latest-source, campaign, deal-type, account-tier, partner/referral, and
expansion/renewal candidates; flag legacy, duplicate, and ambiguous fields.

Write ONLY your declared output file. `crm_context.yaml` and
`schema_discovery_report.md` are code-owned artifacts generated
deterministically — never write or edit them; when your analysis disagrees
with them, record the disagreement in `contradictions` or
`human_confirmation_needed`. Every mapping has a confidence and evidence;
anything below high confidence requires confirmation.
