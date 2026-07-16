# Safety policy

## Non-negotiable

- Local-only token loading; never print or persist the token.
- Explicit read-endpoint allowlist; no HubSpot write client methods.
- The automation scope is accepted only to diagnose workflows and score
  activation. The client allowlist is method-sensitive and excludes workflow
  create, update, delete, enroll, and action endpoints.
- The acquisition pass may store full workflow responses under the local,
  gitignored `raw/automation/` directory for deterministic parsing. Never read
  `outputs/*/raw/` in an LLM or agent role, and never share the raw directory.
- Never copy identity fields, note bodies, tokens, or raw snapshot records into
  agent tasks or final reports. Selected bounded CRM property values may be
  retained in processed artifacts when needed to identify a journey or explain
  a finding; they are marked as untrusted data and remain local to the
  user-selected host workflow.
- `auto_fix_allowed` is always `false`.
- Every scored finding needs evidence, a denominator or materiality rationale,
  confidence, and a limitations note where coverage is incomplete.
- Workflow configuration evidence must be labelled separately from causal
  evidence. No workflow presence, absence, performance aggregate, or score
  property can prove a specific record's execution or establish a complete
  scoring-model diagnosis.
- The final gate scans both shareable deliverables and sanitized
  automation/root-cause artifacts for hard email, phone, and token leaks.

## Blocked actions

Never recommend automatic overwriting of original source, merging companies,
deleting properties, resetting lifecycle stages, moving deal stages, changing
closed-won/closed-lost status, or reassigning owners.

## Allowed actions

Review lists, evidence exports, draft governance documents, proposed field
mappings, draft list criteria, proposed task plans, and questions for the
business owner are allowed. Any action that changes CRM truth belongs in
`do_not_auto_fix` or `requires_human_confirmation`.

## Final gate

Run the deterministic leak scan after the report and handoff are written. Hard
email, phone, or token-format leaks fail unconditionally. Soft blocked phrases
may legitimately appear in the explicit blocked-actions section. The Privacy
+ Safety Reviewer must record each accepted occurrence in
`safety_clearance.json` with the exact phrase, filename, current file SHA-256,
and contextual reason. A clearance never overrides a hard PII or token leak.
