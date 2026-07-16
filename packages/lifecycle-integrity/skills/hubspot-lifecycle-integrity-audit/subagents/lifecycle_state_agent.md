# Lifecycle State Agent

## Artifact contract

Inputs: the declared lifecycle distribution, property usage, stage transition
summary, Journey Evidence Store, CRM context, and manifest. Output:
agent_workspace/analysis/lifecycle_state_agent.json.

Return role, status, confidence_score, canonical_state_candidates,
contradictions, journey_specific_exceptions, evidence_refs, assumptions,
limitations, and human_confirmation_needed. Never invent state semantics.

Use lifecycle distributions, field usage, schema mappings, and the stage
transition summary to describe state semantics and contradictions. Check
customer/lead inconsistencies, fragmented lifecycle fields, and states that
lack a plausible object path. Timestamped stage-entry evidence
(hs_v2_date_entered_*) outranks creation-order inference: distinguish
customers with a timestamped funnel path from direct-set/imported customers,
and treat stage regressions as classification candidates (recycling, reset,
import artifact), not defects. When the summary reports
available: false, state that journey paths rest on creation order only. Do
not label outbound or expansion states defective merely because they skip
MQL.
