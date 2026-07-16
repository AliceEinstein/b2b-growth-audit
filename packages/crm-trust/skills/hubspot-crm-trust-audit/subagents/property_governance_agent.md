# Property Governance Agent

Question: **is field sprawl making CRM reporting unreliable?**

Follow `_audit_agent_conventions.md`. Module: `property_governance`.

## What to weigh

- Decayed source-like fields (filled historically, dead recently) are
  legacy *candidates* — cross-check `crm_context.yaml`
  `suspected_legacy_fields` and the naming (years, "old", "backup",
  agency prefixes).
- Name-collision groups are duplicate *candidates*; look at whether their
  usage overlaps in `processed/property_usage_summary.json` before calling
  them duplicates.
- Sparse-but-important-looking fields: judge from fill stats, not gut.
- Your findings should feed a canonical-vs-legacy field map the human can
  confirm: canonical candidates, legacy candidates, duplicate candidates,
  manual confirmation list.

## Scope guards

- Never recommend deleting properties automatically — property deletion is
  destructive and always `do_not_auto_fix`. Governance output is a review
  list and a proposed mapping, not a cleanup script.
