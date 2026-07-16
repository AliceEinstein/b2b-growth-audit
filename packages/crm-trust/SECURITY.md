# Security and privacy

This package is designed for local-first, read-only HubSpot analysis.

- Never commit `.env`, tokens, raw snapshots, or generated `outputs/`.
- Keep the connector's explicit read-endpoint allowlist intact.
- Host agents must use generated processed artifacts and evidence only; they
  must not read `outputs/*/raw/` or call HubSpot directly.
- Bounded sanitized CRM values may be passed to the host LLM when the user
  authorizes that processing. Raw snapshots, contact identity, note bodies,
  and credentials remain outside agent tasks and final reports.
- No recommendation may directly mutate HubSpot. Changes require human
  approval and a separate operator workflow.
- Deal amounts are valid only for existing HubSpot deals supported by the
  evidence artifacts. No-deal leads may be counted as a potential recoverable
  population only; never assign them an amount.

Please do not publish real CRM exports, credentials, private customer records,
or sensitive report artifacts in an issue or pull request. Report a
reproducible security problem privately to contact@smartifymarketing.com.
