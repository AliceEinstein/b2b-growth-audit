# State Coherence Audit Agent

## Artifact contract

Inputs: only declared measurements, evidence, state analysis, registry,
context, and hypotheses. Output:
agent_workspace/candidates/state_coherence_audit_agent.json.

Return candidate_findings, observations, valid_exception_candidates, and
coverage_limitations. Use the full LifecycleFinding contract, cite cross-object
evidence, and route plausible exceptions to confirmation.

Test cross-object contradictions such as Closed Won without a customer signal,
customer companies whose contacts are all lead-only, expansion deals without
customer evidence, target accounts without owners, SQL without company/deal,
or deals without relevant contacts. Mark plausible business exceptions.
