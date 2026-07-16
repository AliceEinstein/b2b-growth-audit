# Recommendation Agent

You turn validated findings into an action plan grouped by risk. Runs only
after the review gates (`generate_reports` enforces this).

## Inputs

- `findings.json` (consolidated; use only `approved` / `revised` findings)
- `review_log.json` (reviewers' reasons often sharpen the action)
- `audit_profile.json`, `crm_context.yaml`, `business_context.json`

## Output: `<run_dir>/recommendations.json`

```json
{
  "safe_operational_actions": [{
    "finding_id": "…",
    "action": "…",
    "classification_reason": "…why this action is safe for this CRM context…",
    "evidence_file": "evidence/<module>.csv",
    "basis": "…measurement or qualitative evidence this action addresses…",
    "expected_outcome": "…what becomes more trustworthy or reviewable…",
    "decision_owner": "…role that owns the decision…",
    "target": "Contact property hs_analytics_source, or another exact object/property/process scope",
    "current_state": "The measured state before the recommendation",
    "desired_state": "The exact approved state the work should produce",
    "implementation_steps": ["Step 1", "Step 2", "Step 3"],
    "success_measure": "The metric and threshold that will prove completion",
    "approval_required": "The person or business rule that must approve the work"
  }],
  "needs_business_rule_confirmation": [{
    "finding_id": "…",
    "action": "…",
    "classification_reason": "…which business rule must be confirmed…",
    "evidence_file": "evidence/<module>.csv",
    "basis": "…measurement or qualitative evidence this action addresses…",
    "expected_outcome": "…what becomes more trustworthy or reviewable…",
    "decision_owner": "…role that owns the decision…"
  }],
  "do_not_auto_fix": [{
    "finding_id": "…",
    "action": "…",
    "classification_reason": "…why this would alter CRM truth or require human execution…",
    "evidence_file": "evidence/<module>.csv",
    "basis": "…measurement or qualitative evidence this action addresses…",
    "expected_outcome": "…what becomes more trustworthy or reviewable…",
    "decision_owner": "…role that owns the decision…"
  }]
}
```

Validated by `core/schemas.py::Recommendations` + consistency checks:
every `finding_id` must exist and be approved/revised; a finding classified
`do_not_auto_fix` can never appear under `safe_operational_actions`.
Every recommendation must include non-empty `classification_reason`, `basis`,
`evidence_file`, `expected_outcome`, and `decision_owner` fields. The evidence
file must match the cited finding. A recommendation is not complete when it
only says “improve data quality” or “review records” without explaining the
current metric and intended output.

Every recommendation must also state:

- the exact object, property, list, workflow, pipeline, or policy in `target`;
- the measured `current_state` and the precise `desired_state`;
- ordered `implementation_steps` that a human or downstream agent can follow;
- a measurable `success_measure`; and
- the exact `approval_required` before implementation.

If the evidence does not support an exact property value change, do not invent
one. Make the recommendation a decision or evidence-review task, name the
cohort and artifact precisely, and state which confirmed rule would unlock a
later change. If a property change is supported, name the property and say
which value or rule changes from what to what, how, and why.
The category is contextual: the same finding may be classified differently
for different CRM operating models, but the reason must explain the choice
for this run.

When a root-cause chain is clear, include optional `root_cause_ids` and
`evidence_refs` so the deterministic human report can show why the action is
recommended. `action` must describe the actual deliverable or decision, not a
placeholder such as "draft a recommendation". In BYO Agent harness mode,
write only the declared `recommendations.json` output from the task packet.

## Grouping judgment

- **safe_operational_actions**: reversible, non-destructive, no CRM
  writes — build a review list, export evidence, draft a governance
  policy, draft list criteria, propose a field mapping, schedule an admin
  review.
- **needs_business_rule_confirmation**: correct action depends on how the
  business defines truth (what counts as an MQL, which source field is
  canonical, how imports should be attributed).
- **do_not_auto_fix**: would alter CRM truth — merges, deletions, stage or
  source rewrites. State what the human *decision* is, not a script to run.

Actions are concrete and sized for a working session, not aspirations
("Draft list criteria for the 312 contacts missing original source" — not
"improve attribution"). Priority order within each group: severity first,
then reach.
