# Agent routing for this monorepo

This repository contains two independent, read-only HubSpot audit packages.
Before doing work, choose exactly one package:

- `packages/crm-trust` for CRM Trust Audit.
- `packages/lifecycle-integrity` for Lifecycle Integrity Audit.

Run commands from the selected package directory and read that package's
`AGENTS.md`, `CLAUDE.md`, or `GEMINI.md` as applicable. Do not install both
packages into the same virtual environment because they intentionally retain
top-level `connectors`, `core`, and `scripts` modules.

Never read `outputs/*/raw/` as an agent, call HubSpot directly, expose tokens,
or add HubSpot write operations. Generated reports are confidential local
business artifacts even when their code and synthetic fixtures are public.
