# Safety Policy (v1)

## Non-negotiable boundaries

1. HubSpot-only. Read-only only. Local-first.
2. No CRM writes of any kind: no updates, merges, deletions, lifecycle or
   deal stage changes, owner changes, workflow changes.
3. Raw snapshots do not leave the machine. No Smartify backend, login, or
   tokens are used. The user-selected host agent may receive bounded,
   sanitized CRM values that are necessary for deep analysis.
4. Raw records are not shown to the LLM by default. Agent tasks use processed
   artifacts, aggregates, untrusted-value markers, and salted hashes; identity
   fields, note bodies, and tokens remain excluded.
5. Every scored finding must have evidence. Every recommendation must be
   classified by action risk.

## How the read-only guarantee is enforced

- `connectors/hubspot/client.py` refuses any request not on an explicit
  read-endpoint allowlist (`ReadOnlyViolation`).
- `tests/test_connector_contract.py` asserts write methods are blocked and
  the allowlist contains only read operations.
- The private app token should be created with read scopes only; preflight
  warns if write scopes are detected.

## Final gate: two layers

**Primary judge — LLM (Privacy + Safety Reviewer).** Decides whether report
content recommends unsafe automatic execution. Wording variants are infinite;
pattern matching cannot enumerate them, and rigid rules would misjudge
legitimate business cases.

**Backstop — deterministic leak net (`core/safety.py`).**
- Email / phone / token **format** hits: fail the run unconditionally, even
  if the LLM review passed.
- Blocked-phrase hits (e.g. "delete properties", "reset lifecycle stage"):
  flagged for the LLM reviewer, who must clear or reject each in context —
  these phrases can legitimately appear inside a "Blocked Actions" section.

## Blocked recommendations (never as automatic actions)

- overwrite original source
- merge duplicate companies
- delete unused properties
- move stale deals to closed-lost
- reset lifecycle stage
- bulk update owner
- change closed-won / closed-lost

## Allowed recommendation types

- create a human review list
- export evidence CSV
- draft a governance policy
- create a proposed field mapping
- draft HubSpot list criteria
- draft a task creation plan
- recommend admin review
