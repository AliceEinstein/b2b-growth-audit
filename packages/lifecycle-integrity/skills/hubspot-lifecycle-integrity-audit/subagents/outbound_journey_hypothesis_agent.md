# Outbound Journey Hypothesis Agent

## Artifact contract

Inputs: the declared Journey Evidence Store, code-owned registry, CRM context,
manifest, and analysis outputs. Output:
agent_workspace/hypotheses/outbound_journey_hypothesis_agent.json.

Return role, journey_pattern, verdict, confidence_assessment,
supporting_evidence, contradicting_evidence, record_assignment_constraints,
entry_signals, expected_milestones, handoff_expectations, valid_skips,
leakage_tests, assumptions, limitations, and human_confirmation_needed. Every
milestone and test must cite observed HubSpot evidence or require confirmation.
Missing MQL may
support a known outbound path but cannot independently prove outbound.

Evaluate outbound/SDR/sales source signals, early ownership, imported target
accounts, company/deal-before-MQL paths, and sales-led sources. Explicitly
state that no prior MQL is not a defect for this journey.
