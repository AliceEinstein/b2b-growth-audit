# Attribution Trust Agent

Question: **can marketing credibly report which channels, campaigns, or
sources create qualified pipeline?**

Follow `_audit_agent_conventions.md`. Module: `attribution_trust`.

## What to weigh

- Missing original source — weigh the recent-half measurement over the
  overall one: decaying capture on *new* contacts is what breaks next
  quarter's reporting.
- Closed-won deals without source traceability hit hardest: they make
  revenue attribution impossible, not just lead attribution.
- Competing source fields (see `processed/source_field_candidates.json`):
  multiple fields active at once with conflicting values is a trust
  problem even when each field looks healthy alone.
- Imported records without source governance.

## Scope guards

- Never conclude a channel is or isn't working — paid media data is not
  connected. Valid: "campaign-level attribution is unreliable because the
  CRM lacks consistent source capture."
- Overwriting or backfilling source values is always
  `do_not_auto_fix` — original source is historical truth.
