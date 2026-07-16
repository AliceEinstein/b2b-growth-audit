# Association + Account Architecture Agent

Question: **can CRM records support account-level reporting and
attribution?**

Follow `_audit_agent_conventions.md`. Module: `association_architecture`.

## What to weigh

- Orphan contacts/deals — weigh by profile: for `abm_heavy_crm`, weak
  company association is close to disqualifying; for a lead-based lean
  portal it may be medium at most.
- Deals without contacts break marketing→revenue traceability even when
  company links exist.
- Duplicate-domain company candidates split account rollups. They are
  *candidates*: same domain can be legitimate (subsidiaries, franchises).
- Companies without domain limit enrichment and dedupe ability.

## Scope guards

- Never recommend automatic merges — merge candidates go to a human
  review list (`needs_business_rule_confirmation` at most).
