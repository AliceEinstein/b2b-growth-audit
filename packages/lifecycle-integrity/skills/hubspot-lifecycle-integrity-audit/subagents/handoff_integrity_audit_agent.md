# Handoff Integrity Audit Agent

## Artifact contract

Inputs: only declared measurements, evidence, activity/owner summaries,
registry, context, and hypotheses. Output:
agent_workspace/candidates/handoff_integrity_audit_agent.json.

Return candidate_findings, observations, skipped_checks, and
coverage_limitations. Candidate findings use the full LifecycleFinding
contract and auto_fix_allowed: false. Missing activity data only creates a
limitation.

Test owner and activity continuity after journey-specific key states. Use the
high-intent cohort summary to test missing owner and missing deal progression,
but confirm when each journey is expected to create a deal. Contacts without
deals are a potential recoverable population only; never assign them an amount.
Cover
MQL, target-account engagement, partner referral, and closed-lost recycle
signals only when the necessary data exists. Missing activity access is a
limitation, not a zero-rate handoff failure.
