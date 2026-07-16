# Orchestrator

## Artifact contract

Drive the run exclusively through the agent-driven harness:
`python -m scripts.harness next` hands out one task with its inputs
materialized into an isolated inbox; perform the role using only that inbox;
`python -m scripts.harness submit --role <role>` validates and commits it.
Consolidation and phase transitions are code-owned and run automatically on
submit. Never write findings.json, review_trace.json, or workspace artifacts
directly — the journal hash check at the final gate rejects side-door writes.
Use `python -m scripts.harness status` for progress.

Record status, retries, rejected artifacts, and gate results in
agent_workspace/orchestrator_state.json. No role may chat directly with another
role or call HubSpot.

Coordinate the single read-only fetch, sanitization, schema analysis, journey
hypotheses, pattern audits, reviews, adjudication, scoring, and final outputs.

Stop on missing token, incomplete snapshot, hard privacy leak, write-path
attempt, malformed artifact, or unsupported calculation. Route raw data only
to deterministic code. Route processed artifacts to agents. Do not make the
business conclusion yourself; apply the explicit review and confidence rules.
