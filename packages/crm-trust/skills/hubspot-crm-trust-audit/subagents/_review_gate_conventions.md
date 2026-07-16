# Review Gate Conventions (all four reviewers)

Reviews run after `scripts.validate_findings` passes. All four reviewers
examine **every finding**; a finding is final only after passing through
all gates.

## Inputs

- `findings/<module>_findings.json` (all modules)
- `processed/measurements/<module>.json`, other `processed/` artifacts
- `audit_profile.json`, `crm_context.yaml`, `business_context.json`
- Never `raw/`.

## Recording verdicts

Append entries to `<run_dir>/review_log.json` (a JSON array):

```json
{"finding_id": "…", "reviewer": "<your_role>", "verdict": "approve|revise|reject", "reason": "…specific, cites artifacts…"}
```

- **approve** — the finding stands as written.
- **revise** — fix the finding first (severity, wording, classification —
  numbers stay verbatim per the validator), then record `revise`.
- **reject** — the finding should not count. Do not delete it; set its
  fate through the verdict.

One entry per (finding, reviewer). After all four reviewers are done,
update each finding's `review_status` to the deterministic aggregate:
any reject → `rejected`; else any revise → `revised`; else `approved`.
`scripts.generate_reports` verifies exactly this rule — mismatches block
the report stage.

## BYO Agent harness mode

When the task packet says `mode: byo_agent`, write only your isolated output:

```text
<run_dir>/harness/agent_outputs/reviews/<your_reviewer_name>.json
```

It must contain the same JSON array of verdict entries, but only for your
reviewer. Do not append to `review_log.json` and do not edit any finding file;
the harness aggregates these files deterministically after all four reviewer
tasks pass validation.

## Stance

You are a gate, not a rubber stamp. Rejecting a bad finding is a success
of the system. But do not re-litigate another reviewer's domain: each gate
has one question, answer only yours.
