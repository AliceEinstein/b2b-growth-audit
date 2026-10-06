---
name: hubspot-crm-trust-audit
description: Run a local-first, read-only HubSpot CRM Trust Audit when a CMO, RevOps owner, or growth leader needs to determine whether HubSpot is reliable enough to serve as the marketing-to-pipeline single source of truth. Use it to audit attribution capture, lifecycle-to-deal traceability, contact-company-deal associations, pipeline hygiene, property governance, reporting contamination, and the evidence quality behind revenue decisions. Do not use it to write, clean, merge, reassign, or forecast from HubSpot.
---

# HubSpot Marketing-to-Pipeline Trust Audit

## Goal

Determine whether HubSpot CRM data can be trusted to explain marketing impact
on pipeline.

This skill produces its own standalone report and evidence set. It does not
replace or depend on the separate Lifecycle Integrity Audit report.

## Division of labor

Use the artifact-driven BYO Agent harness by default:

- Scripts fetch data, compute metrics, generate evidence, control stage order,
  validate artifacts, resume state, and do score arithmetic. Never recompute
  or adjust their numbers.
- The host agent executes the judgment roles in `subagents/` from generated
  task packets. Each role receives an allowlist of processed/evidence inputs
  and writes a declared structured artifact. The harness validates it before
  unlocking the next stage.
- The final report and handoff are rendered deterministically from validated
  artifacts. The narrative role supplies interpretation but cannot omit
  snapshot data, evidence links, score arithmetic, or recommendation basis.
- V1 does not call an LLM API and does not require `OPENAI_API_KEY` or
  `ANTHROPIC_API_KEY`. A future provider-driven adapter may execute the same
  task packets without changing the contracts.

## Scope

This audit focuses on:
- attribution trust
- lifecycle and funnel trust
- contact-company-deal associations
- pipeline hygiene relevant to marketing reporting
- property governance issues that affect reporting trust

This audit does not:
- clean CRM automatically
- write to HubSpot
- merge records
- update lifecycle stages
- update deal stages
- delete properties
- perform full sales forecasting

## Required local setup

- `.env` with `HUBSPOT_PRIVATE_APP_TOKEN`
- A dedicated virtual environment for this package
- Python dependencies installed (`pip install -e ".[dev]"`)
- HubSpot Private App with all seven exact read scopes in
  `hubspot_scopes.md`; wildcards are invalid

Every `python -m scripts.*` command below must run from the package root (the
directory containing `pyproject.toml` and `.env`). With a normal repository or
Claude symlink install, that is `packages/crm-trust`. If Claude was installed
with `python -m scripts.install_skill --agent claude --copy`, run from the
copied skill's sibling `package/` directory instead. Do not run commands from
an unrelated project merely because the skill is globally discoverable.

## Workflow

1. Read `hubspot_scopes.md`, grant all seven exact scopes, then run
   `python -m scripts.check_hubspot_connection`. Do not continue if a required
   scope or endpoint probe fails.
2. Ask the user for the exact business name that should appear in the report,
   then run `python -m scripts.run_crm_trust_audit --business-name "Business Name"`
   — fetches the full-history
   read-only snapshot and writes sanitized profiles. Each object page and
   association batch is checkpointed under `raw/.checkpoints/`; if the
   process times out, rerun with `--resume <run_dir>`. Only a manifest with
   `status: completed` can enter later phases. Use `--days 90` only for an
   additional recent-only view. The local raw snapshot includes contact
   identity fields only to measure completeness; contact names/emails/phones
   never enter LLM-facing artifacts or final reports. Display-safe but still
   identifiable Company/Deal names and owner labels may appear in the
   confidential local report. Do not describe that report package as
   anonymized or safe for unrestricted sharing.
   Raw trees from completed/failed runs older than 365 days are removed by
   default; change this with `--raw-retention-days N`. In-progress runs are
   retained so they remain resumable. Use `--dry-run` to preview retention
   deletions; the command still performs the audit fetch.
3. Initialize the BYO Agent harness:

   ```bash
   python -m scripts.run_audit_harness init --run <run_dir>
   ```

   This runs deterministic profiling and pauses with task packets under
   `<run_dir>/harness/tasks/`. Have Codex or Claude Code perform each task,
   writing only the declared artifact. No model API key is required.
4. After an agent task is complete, resume the harness:

   ```bash
   python -m scripts.run_audit_harness advance --run <run_dir>
   ```

   The harness validates the artifact, prepares parallel audit/reviewer tasks
   where possible, aggregates reviewer verdicts deterministically, and only
   then unlocks recommendations and the report narrative. A `revise` verdict
   opens one revision round: a `revise_<module>` task for the audit role
   (`revision_agent.md`), then a `rereview_<reviewer>` task in which the
   reviewer can only approve or reject. Both are skipped when no finding was
   sent back.
5. Inspect progress or validate one stage directly:

   ```bash
   python -m scripts.run_audit_harness status --run <run_dir>
   python -m scripts.run_audit_harness validate --run <run_dir> --stage findings_validation
   ```

   The renderer creates the human report and handoff from validated data. The
   final safety gate runs as the last deterministic stage. If a stored gate
   result is reused later, verify it with:

   ```bash
   python -m scripts.verify_final_gate --run <run_dir>
   ```

   Legacy manual scripts remain available for migration and debugging, but
   new runs should use the harness entrypoint.

## Safety

Do not perform or suggest automatic CRM writes.
Do not expose raw PII by default.
Do not include token values in logs or reports.
Require evidence for every scored finding.
See `safety_policy.md` for the full policy and gate semantics.

Snapshot safety and recovery:

- Full-history list requests use `archived=false`, active pacing, and page
  checkpoints to reduce burst traffic and avoid duplicate pages after a
  timeout.
- A checkpoint records the request mode, selected properties, cursor, row
  count, record ids, and flushed file offset. Resume rejects mismatched
  windows or property selections.
- A failed or in-progress snapshot is not valid input to schema discovery,
  measurements, or the final gate.
- The current raw snapshot is preserved for local diffing. Older raw trees
  are pruned independently of their processed aggregate artifacts.
- Retention deletes `run_salt.txt` together with expired raw data. Older
  evidence hashes are intentionally no longer reversible or matchable to CRM
  records after that point.
- Full-history cursor traversal is best-effort rather than point-in-time
  consistent; `manifest.json` records start/completion and resume metadata.

## Final outputs

- `crm_trust_report.html`
- `crm_trust_report.md`
- `operator_appendix.md`
- `agent_handoff.md`
- `findings.json`
- `evidence.csv`
- `report_record_evidence.csv`
- `score.json`
- `crm_context.yaml`
- `schema_discovery_report.md`
- `audit_log.json`
- `manifest.json`
- `recommendations.json`
- `final_gate_report.json`

The report renderer follows `reporting_standard.md`: the HTML/Markdown report
is written for decision use, while the operator appendix carries complete
finding and implementation detail. PDF or Word exports must derive from the
same validated report content rather than a separate rewrite.

The supplied business name becomes the report title. Deterministic local
rendering may show display-safe but identifiable HubSpot Company and Deal names
for representative evidence and link them to their HubSpot record pages when
the portal ID is available. Contact names, emails, phones, raw IDs, and tokens
remain excluded. Share final reports only with authorized recipients.
