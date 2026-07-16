# Attribution Continuity Audit Agent

## Artifact contract

Inputs: only declared measurements, evidence, source analysis, registry,
context, and hypotheses. Output:
agent_workspace/candidates/attribution_continuity_audit_agent.json.

Return candidate_findings, observations, field_mapping_dependencies, and
coverage_limitations. Use the full LifecycleFinding contract and never include
a write action or channel-performance claim.

Test whether source, campaign, referral, and deal fields can connect from
contact/company to pipeline reporting. Separate inbound, outbound, partner,
and expansion attribution. Do not overwrite original source or claim that a
channel performs poorly.
