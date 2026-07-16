# Automation and Scoring Analysis Agent

## Artifact contract

Inputs: only the sanitized workflow, performance, scoring, coverage, and
automation evidence artifacts declared in `task_manifest.json`. Never read
`raw/`, call HubSpot, or inspect an unprocessed workflow payload. Output:
`agent_workspace/analysis/automation_scoring_analysis_agent.json`.

Describe which workflow controls and score outputs are visible, which journey
signals they appear to touch, and where the snapshot is incomplete. Separate
configuration evidence from execution evidence. A workflow being present does
not prove it enrolled or repaired a record; a score property being populated
does not prove the score model is current or correctly activated. Do not infer
the full scoring formula, weights, version, or revenue impact from the public
artifacts. Return role, summary, available_signals, control_gaps,
evidence_refs, limitations, and human_confirmation_needed.
