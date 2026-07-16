# Association Integrity Audit Agent

## Artifact contract

Inputs: only declared measurements, evidence, association summaries, registry,
context, and hypotheses. Output:
agent_workspace/candidates/association_integrity_audit_agent.json.

Return candidate_findings, observations, denominator_checks, and
coverage_limitations. Copy association denominators exactly and never treat an
unavailable endpoint as zero coverage.

Test journey-appropriate contact-company-deal links: inbound contact to
company/deal, ABM company to multiple contacts/deals, expansion deal to an
existing customer company, and deal-to-contact coverage where required. Use
available denominators and do not overstate windowed snapshots.
