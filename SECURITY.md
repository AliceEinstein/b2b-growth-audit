# Security and privacy

This project is designed for local-first, read-only HubSpot analysis.

- Never commit `.env`, tokens, raw snapshots, or generated `outputs/`.
- The connector must remain restricted to its explicit read endpoint allowlist.
- Host agents must use only generated processed artifacts and evidence; they
  must not read `outputs/*/raw/` or call HubSpot directly.
- Bounded sanitized CRM values may be passed to the host LLM when the user
  has authorized that processing. Raw snapshots, contact email/phone, note
  bodies, and credentials remain outside agent tasks. Local reports may show
  minimum sanitized account/contact/deal and owner labels needed for action;
  keep those reports confidential.
- No recommendation may directly mutate HubSpot. Changes require a human
  approval and a separate operator workflow.
- Existing deal amounts may be reported only when the corresponding HubSpot
  deal exists and the evidence artifact supports the claim. No-deal leads may
  be counted as recoverable population only; they must not receive an
  estimated amount.

Please do not publish real CRM exports, credentials, private customer records,
or report artifacts containing sensitive information in an issue or pull
request. Report a reproducible security problem privately to
contact@smartifymarketing.com before public disclosure.
