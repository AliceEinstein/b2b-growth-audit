# Revision Agent

Question: **does each finding a reviewer sent back hold up once the
reviewer's objection is answered?**

You act as the module's audit role for one revision round. The harness opens
this task only when a reviewer's round-0 verdict was `revise`; the task
packet lists each request under **Revision requests** (finding, reviewer,
reason). Follow `_audit_agent_conventions.md` for how to judge.

## Inputs

- `findings/<module>_findings.json` — the findings as first written
- `harness/agent_outputs/reviews/*.json` — the round-0 verdicts and reasons
- `processed/measurements/<module>.json`, `processed/snapshot_summary.json`
- `audit_profile.json`, `crm_context.yaml`, `business_context.json`
- Never `raw/`.

## Output: `<run_dir>/harness/agent_outputs/revisions/<module>.json`

```json
{
  "module": "<module>",
  "findings": [
    {
      "id": "deals_without_amount",
      "severity": "low",
      "confidence": "high",
      "business_impact": "…the reworded impact…",
      "recommendation_type": "needs_business_rule_confirmation",
      "revision_note": "Logic reviewer: amount is optional before proposal stage. Lowered severity to low and narrowed the impact to late-stage deals."
    }
  ]
}
```

- Include exactly the findings listed under revision requests: one entry
  each, no others.
- You may change `title`, `severity`, `confidence`, `business_impact`,
  `decision_impacts` and `recommendation_type`. Copy the original for any
  of these you leave as is.
- `id`, `measurement_id`, `field_name`, the numbers, `evidence_file`,
  `object_type`, `module` and `auto_fix_allowed` are locked. Leave them out,
  or copy them verbatim. If the numbers themselves are wrong, the finding
  cannot be fixed by revision; say so in the note and let the reviewer
  reject it.
- `revision_note` answers each reviewer's reason: what changed, or why the
  original stands. A revision that changes nothing must say why.
- Do not edit `findings/`. The original stays as the audit trail; reports
  use your revised copy once the reviewer approves it.
- Write numbers as Arabic numerals in prose ("3 owners", not "three owners").

## What happens next

Each reviewer who asked for the revision re-reviews it once and can only
approve or reject. There is no second revision round, so answer the
objection fully now.

Validate with:

```bash
python -m scripts.run_audit_harness validate --run <run_dir> --stage revise_<module>
```
