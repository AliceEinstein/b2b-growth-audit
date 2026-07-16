# Legacy Final Report Role — Retired

The BYO Agent harness no longer asks a model to write final reports directly.
Use `report_narrative_agent.md` to create the bounded interpretation in
`report_narrative.json`. The deterministic `render_reports` stage then creates:

- `crm_trust_report.html`
- `crm_trust_report.md`
- `operator_appendix.md`
- `agent_handoff.md`

This keeps every count, percentage, score, finding sample, and evidence link
bound to validated artifacts. The output structure, language, visual rules,
and format policy are defined in `../reporting_standard.md`.
