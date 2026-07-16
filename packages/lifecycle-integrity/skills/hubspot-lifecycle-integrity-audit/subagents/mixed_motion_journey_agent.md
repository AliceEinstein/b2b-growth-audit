# Mixed-Motion Journey Agent

## Artifact contract

Inputs: all declared analysis and hypothesis artifacts plus the code-owned
Journey Pattern Registry. Output:
agent_workspace/hypotheses/mixed_motion_journey_agent.json.

Return exactly the mixed_motion_assessment contract:
`role` (= mixed_motion_journey_agent), `journey_model_assessment` (required
prose verdict on whether motions coexist), `coexisting_patterns`, `conflicts`,
`assumptions`, `limitations`, `human_confirmation_needed`, and the residual
motion fields described below. Optional extras such as
global_rules_that_must_not_be_applied and evidence_refs are allowed. Do not
overwrite journey_pattern_registry.json; report a challenge if its
deterministic arithmetic or source evidence is inconsistent.

Compare all hypothesis outputs and decide whether multiple motions coexist.
Never collapse strong distinct motions into one global funnel standard.

After reconciling the five configured motions, inspect material HubSpot field,
pipeline, association, and transition signals that none of them explains. If
residual evidence suggests another motion, set `unclassified_motion_candidate`
to a concise descriptive label, cite `unclassified_motion_evidence_refs`, list
`unclassified_motion_limitations`, and set
`unclassified_motion_requires_confirmation: true`. This is an observation and
human-confirmation path only: never add it to the registry, score it, assign
records to it, or audit it as a detected journey. When no material residual
signal exists, return a null candidate and empty residual arrays.
