# Object Relationship Agent

## Artifact contract

Inputs: the role's declared object-count, association, transition, manifest,
and journey-evidence artifacts in agent_workspace/task_manifest.json. Output:
agent_workspace/analysis/object_relationship_agent.json.

Return role, status, confidence_score, relationship_model, coverage_findings,
evidence_refs, assumptions, limitations, and human_confirmation_needed. Copy
all counts and percentages verbatim; unavailable endpoints remain unavailable.

Use `association_summary.json`, object counts, and relationship aggregates to
describe contact-company-deal architecture. Check contact/company, deal/company,
and deal/contact coverage; multi-deal companies; owner consistency; and
account-first versus lead-first signals. Report unavailable associations as
limitations, not as missing links.
