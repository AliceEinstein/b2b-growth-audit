# Security and data handling

This project is local-first and structurally read-only. The HubSpot connector
uses a read endpoint allowlist and fixed API origin; it does not create,
update, merge, delete, reassign, or stage-change CRM records.

The automation scope required for the full workflow/scoring diagnostic is
mutation-capable at the HubSpot platform level. This repository narrows it to
method-sensitive workflow GET, batch-read, and aggregate performance
endpoints; workflow create, update, delete, enroll, and action endpoints are
not allowlisted. Runs without it are core-only and must disclose the coverage
limitation.

Raw snapshots, including full local workflow responses under
`raw/automation/`, and private app tokens must stay local and untracked. The
deterministic parser reads those responses locally and emits only sanitized
configuration signals. The audit may pass bounded processed CRM values to the
host LLM selected by the user for deep analysis. Contact identity fields, note
bodies, tokens, and raw snapshot trees are excluded from agent task inputs and
final reports. Users must have authorization to process the connected portal
data with their chosen host.

Please do not report credentials or private CRM records in a public issue.
For a security report, contact contact@smartifymarketing.com privately with
reproduction steps that do not include secrets.
