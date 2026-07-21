# Security red line: never read outputs/*/raw/ as an agent or LLM role.
# Raw contains CRM PII; use processed/ and evidence files only.

# Gemini CLI context

This repository implements the local-first, read-only HubSpot Lifecycle
Integrity Audit.

Canonical working rules live in AGENTS.md. The skill entry point is
skills/hubspot-lifecycle-integrity-audit/SKILL.md; isolated role contracts are
under skills/hubspot-lifecycle-integrity-audit/subagents/.

Non-negotiables: read-only toward HubSpot; never print tokens; never read raw
snapshots as a judgment agent; numbers come from code-owned artifacts; do not
assume a linear funnel; missing MQL is not an outbound or expansion defect by
default. The automation scope is required for the complete workflow/scoring
diagnostic and is used only for workflow reads and aggregate performance; the
client structurally blocks workflow mutations. Without it, label the
automation/scoring layer incomplete. `--core-only` separately skips intent and
activity acquisition. `marketing.campaigns.read` is available only to Marketing
Hub Professional/Enterprise portals; when it is unavailable, label aggregate
campaign/channel context unavailable, continue with other readable
record-linked sources, and never interpret the gap as zero campaigns or zero
intent. Neither missing automation nor missing campaign context creates an
automatic score deduction; unavailable lifecycle-link evidence reduces stated
coverage and can withhold the score below the reportable threshold.
The Events API adds no picker scope but requires an eligible
Professional/Enterprise portal. If its endpoint probe fails, disclose event
coverage as unavailable and continue with other readable evidence.
