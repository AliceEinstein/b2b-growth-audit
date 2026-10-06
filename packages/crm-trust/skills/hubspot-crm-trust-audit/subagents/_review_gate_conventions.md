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

In this mode **revise** means "send it back": say in `reason` exactly what
must change (severity, wording, confidence, recommendation type) and why. Do
not fix the finding yourself. The harness then runs one revision round:

1. A `revise_<module>` task asks the module's audit role to answer your
   reason with a revised copy in `harness/agent_outputs/revisions/`. Numbers,
   measurement and evidence stay locked.
2. A `rereview_<your_reviewer_name>` task asks you to judge the revised
   copy of each finding you sent back. Write
   `harness/agent_outputs/rereviews/<your_reviewer_name>.json` with one entry
   per finding and `"revision_round": 1`. The verdict is `approve` or
   `reject` only; there is no second revision round. If the revision
   still falls short, reject it and say why.

A finding another reviewer rejected in round 0 is not sent back; reject wins.
After the round, `review_status` is `rejected` if any standing verdict is
reject, `revised` if it went through the revision round and was approved,
and `approved` otherwise. Reports use the revised copy; the audit role's
original file stays as the audit trail.

## Stance

You are a gate, not a rubber stamp. Rejecting a bad finding is a success
of the system. But do not re-litigate another reviewer's domain: each gate
has one question, answer only yours.
