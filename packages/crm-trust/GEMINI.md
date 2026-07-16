# Security red line: never read `outputs/*/raw/` as an agent or LLM role.
# Raw contains CRM PII; use `processed/` and `evidence/` only.

# Gemini CLI context

This repository is a series of local-first B2B growth audit skills.
Current skill: **HubSpot Marketing-to-Pipeline Trust Audit**.

Canonical working rules live in [AGENTS.md](AGENTS.md) — follow them
exactly. The skill entry point and workflow are in
[skills/hubspot-crm-trust-audit/SKILL.md](skills/hubspot-crm-trust-audit/SKILL.md);
role instructions are in `skills/hubspot-crm-trust-audit/subagents/`.

Non-negotiables (details in AGENTS.md): read-only toward HubSpot; never
print tokens; never read `outputs/*/raw/` as the judgment agent; numbers
come from code-generated artifacts, severity judgment is yours.
