# Security red line: never read `outputs/*/raw/` as an agent or LLM role.
# Raw contains owner-authorized CRM PII and credentials used only by the
# deterministic fetch/profile code. Use `processed/` and `evidence/` instead.

# Agent Instructions

You are working on a local-first, read-only HubSpot CRM Trust Audit skill.

Do not add CRM write functions in v1.

Do not add scripts that update, merge, delete, or overwrite HubSpot records.
The client in `connectors/hubspot/client.py` enforces a read-endpoint
allowlist — do not weaken or bypass it.

Do not print API tokens.

Do not include raw PII in final reports. Email, name, and phone fields may be
fetched into the local, owner-authorized raw snapshot because identity
completeness is part of this audit. Contact names, emails, and phones must
never be copied into processed LLM artifacts or final reports; sanitized
Company/Deal names and owner labels may appear in the confidential local
report as actionable evidence. Use aggregate completeness/format counts for
contact identity.

Use deterministic code for data fetching, measurement, score arithmetic, and
leak-format detection.

Use LLM/agent reasoning for interpretation, severity judgment,
business-context classification, review gates, recommendation phrasing, and
bounded narrative — always based on the generated harness task packet and
structured artifacts, never raw records. Let the harness render the final
report and handoff so snapshot data and evidence links cannot be omitted.
The decision-maker HTML/Markdown report and operator appendix must follow
`skills/hubspot-crm-trust-audit/reporting_standard.md`, including its plain-
language, evidence, recommendation-detail, and Smartify data-graphic rules.

For new runs, use:

```bash
python -m scripts.run_audit_harness init --run <run_dir>
python -m scripts.run_audit_harness advance --run <run_dir>
```

The harness is BYO Agent in v1: it does not call an LLM provider and does not
require an OpenAI or Anthropic API key. Write only the artifact declared by
the current task packet, then resume the harness.

Do not hardcode severity thresholds in code. Code measures; the LLM judges
severity against the audit profile.

Every scored finding must have evidence.

If a finding lacks evidence, mark it as an observation, not a scored finding.

If a recommendation requires business judgment, classify it as
`needs_business_rule_confirmation`.

If a recommendation could alter CRM truth, classify it as `do_not_auto_fix`.

The v1 audit scope is marketing-to-pipeline trust, not full RevOps cleanup.
