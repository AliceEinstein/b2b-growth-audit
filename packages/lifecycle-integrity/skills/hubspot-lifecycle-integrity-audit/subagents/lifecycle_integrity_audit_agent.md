# Lifecycle Integrity Audit Agent

## Artifact contract

Inputs: only the audit artifacts declared in task_manifest.json plus completed
hypothesis outputs. Output:
agent_workspace/candidates/lifecycle_integrity_audit_agent.json.

Return a candidate_findings array using the full LifecycleFinding contract,
including recommended_action and auto_fix_allowed: false, plus rejected_checks
and coverage_limitations. Every scored candidate cites an existing
deterministic measurement and evidence row.

For each eligible journey, test lifecycle-state alignment, field consistency,
state contradictions, customer/lead mismatch, SQL without a required deal, and
lifecycle fragmentation. A high-intent contact without a deal is not proven
lost pipeline until the journey-specific deal-creation timing is confirmed;
report it as a potential recoverable population and never attach an amount.
Respect journey-specific rules and cite measurements and evidence rows for
every finding.
