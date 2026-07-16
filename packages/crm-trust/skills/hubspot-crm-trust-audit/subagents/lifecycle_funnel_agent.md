# Lifecycle + Funnel Agent

Question: **can the CRM support a trustworthy view of lead-to-pipeline
progression?**

Follow `_audit_agent_conventions.md`. Module: `lifecycle_funnel`.

## What to weigh

- Missing lifecycle stage undermines every funnel metric downstream.
- Funnel inconsistencies (customers without a won deal, MQL+ contacts with
  no deal) — judge against the motion in `business_context.json`: in a
  PLG-ish motion, MQLs without deals may be normal; in sales-led, they
  suggest broken handoff or stale stages.
- Check `processed/lifecycle_distribution.json` for shape anomalies (e.g.
  everyone stuck at one stage, customers outnumbering leads).

## Scope guards

- Lifecycle changes always require business rule confirmation — a
  lifecycle reset is never a safe action (`do_not_auto_fix` for anything
  that rewrites stages).
- A custom lifecycle model is not itself a finding; inconsistency within
  the model is.
