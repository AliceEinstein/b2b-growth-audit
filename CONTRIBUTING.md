# Contributing

Please preserve the audit's read-only and evidence-first boundaries.

- Keep deterministic fetching, measurement, validation, and score arithmetic
  in code; keep interpretation in isolated, schema-checked agent tasks.
- Add a synthetic fixture and regression test for any new journey signal,
  leakage rule, safety rule, or report contract.
- Do not add HubSpot write endpoints, CRM mutation helpers, raw-record prompts,
  or credentials to examples and tests.
- Run both package test suites before opening a pull request:

  ```bash
  (cd packages/crm-trust && pytest)
  (cd packages/lifecycle-integrity && pytest)
  ```

- Keep reports evidence-backed and preserve the distinction between existing
  deal exposure and no-deal recoverable populations.
- Changes to the final safety gate require a negative regression test proving
  that a dangerous phrase cannot be cleared outside its designated safety
  section.
