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

Also return `proposed_client_config`, your suggested answers to the owner's
config questions. The harness writes them into ready-to-confirm drafts in
`client_config_draft/` and lists them in the report; the code uses them only
after the owner confirms. Shape:

```json
"proposed_client_config": {
  "canonical_fields": {
    "lifecycle_stage": {"field": "<contact property>", "evidence": "<why>"},
    "company_lifecycle_stage": {"field": "<company property>", "evidence": "<why>"},
    "original_source": {"field": "<contact property>", "evidence": "<why>"}
  },
  "journey_mapping": [
    {"field": "<property>", "value": "<value>", "journey": "<journey or unassigned>", "evidence": "<why>"}
  ]
}
```

- Propose a field only from `crm_context.yaml` `candidate_fields` or a
  canonical field's `competing_fields`; anything else is ignored.
- Propose journeys for the values in `crm_context.yaml` `source_values`,
  the material values the classifier reads. Journeys:
  `inbound_new_business`, `outbound_sales_led`, `abm_account_based`,
  `partner_led`, `expansion_renewal`, or `unassigned` when a value says
  nothing about how the buyer arrived (for example how a record was created).
- Keep evidence to one sentence citing processed artifacts; never quote raw
  record content.
