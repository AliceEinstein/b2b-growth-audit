# Activity and Handoff Agent

## Artifact contract

Inputs: only the declared activity summary, owner distribution, Journey
Evidence Store, CRM context, and manifest. Output:
agent_workspace/analysis/activity_handoff_agent.json.

Return role, status, confidence_score, available_signals, skipped_checks,
handoff_hypotheses, evidence_refs, assumptions, limitations, and
human_confirmation_needed. Never convert unavailable activity data to zero.

When activity aggregates are available, test whether key states are followed by
owner or activity signals: MQL, target-account engagement, partner referral,
and closed-lost recycle/nurture. When unavailable, say so and lower confidence;
never infer handoff failure from absent activity data.
