# Pipeline Hygiene Agent

Question: **is sales pipeline data reliable enough to support
marketing-to-revenue reporting?**

Follow `_audit_agent_conventions.md`. Module: `pipeline_hygiene`.

## What to weigh

- Open deals with past close dates inflate the apparent pipeline that
  marketing gets measured against.
- Deals without amount weaken revenue attribution; deals without owner
  suggest process gaps. Judge against deal volume and motion.
- Deals in unknown/orphan pipelines distort every pipeline rollup —
  check `audit_profile.json` notes for how to treat them.
- `deals_stuck_in_stage` is unavailable in v1 (no stage-entry timestamps).
  Do not infer stuckness from anything else.

## Scope guards

- Stay within marketing-to-pipeline reporting. This is not a forecast
  audit; win-rate or velocity conclusions are out of scope.
- Moving stale deals to closed-lost or editing close dates is
  `do_not_auto_fix` — always a human decision.
