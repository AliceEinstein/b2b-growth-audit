---
name: hubspot-lifecycle-integrity-audit
description: Run a local-first, read-only HubSpot Lifecycle Integrity Audit when a user needs to identify the selling journeys represented in HubSpot, locate journey-specific pipeline leakage, quantify exposure on existing deals, identify high-intent contacts that may be recoverable, and design evidence-backed repairs without assuming a linear funnel.
---

# HubSpot Lifecycle Integrity Audit

## Purpose

Use this skill to understand how a business actually sells, where that journey
breaks inside HubSpot, and which breakpoints can leak pipeline. It discovers
the portal's represented revenue motions before judging lifecycle integrity:
inbound new business, outbound sales-led, ABM, partner-led, expansion/renewal,
or a mixed-motion model.

This is not a general CRM health report. The primary deliverable is a
journey-specific leakage and recovery view. General field completeness,
identity, association, and data-age diagnostics belong in the operator
appendix. Use only HubSpot objects and properties. A signal from another tool
is eligible only after it has been synced into a HubSpot property and can help
identify a journey or test a leakage point.

This skill produces its own standalone report and evidence set. Do not replace
it with a combined CRM report or require the CRM Trust Audit to complete it.

The governing rule is: measure in deterministic code, interpret with isolated
agent roles, validate with reviewers, and let the orchestrator adjudicate by
rules. Never turn a missing MQL, an outlier, or a non-linear path into a defect
without journey-specific evidence.

Read these files as needed:

- `prd.md` — design contract: required behavior, outputs, and non-goals.
- `audit_scope.md` — in-scope questions and non-goals.
- `safety_policy.md` — read-only and privacy gates.
- `hubspot_scopes.md` — exact Private App scopes and permission boundaries.
- `confidence_model.md` — journey confidence, severity caps, and ambiguity.
- `scoring_rubric.md` — deterministic score ownership.
- `output_contract.md` — required artifact schemas and report headings.
- `agent_constitution.md` — rules every role must follow.
- `subagents/` — one instruction file per analysis, review, and report role.

## Run workflow

Every `python -m scripts.*` command below must run from the package root (the
directory containing `pyproject.toml` and `.env`). With the normal repository
or Claude symlink install, that is `packages/lifecycle-integrity`. If Claude
was installed with `python -m scripts.install_skill --agent claude --copy`,
the executable package snapshot is the sibling `package/` directory next to
this `SKILL.md`; run commands from that `package/` directory instead. If this
skill was installed by symlink, the run's `agent_workspace/task_manifest.json`
records the absolute `repo_root` to change into.

1. Read `hubspot_scopes.md`. Create one dedicated Private App token with all
   seven exact CRM object/schema read scopes plus `settings.currencies.read`, `automation`, `forms`,
   `marketing.campaigns.read`, and `sales-email-read` for the complete
   intent-enabled workflow/scoring root-cause diagnostic. There is no wildcard
   schema scope and no separate scoring scope used by this implementation. `automation` is
   mutation-capable at the HubSpot platform level, but this connector permits
   only workflow reads and read-style batch reads. Put the token in local
   `.env` as `HUBSPOT_PRIVATE_APP_TOKEN`; never print it.
2. Run `python -m scripts.check_hubspot_connection`. All core probes must pass.
   A missing `automation` result means workflow/scoring root-cause coverage is
   incomplete and must be disclosed; do not present the run as a complete
   Automation & Scoring Integrity Audit.
3. Run `python -m scripts.run_lifecycle_integrity_audit`. Full history is
   the default and the authoritative mode: B2B sales cycles run 6-18 months,
   so a creation-date window truncates journeys and drops the older
   contacts/companies that in-window deals link to. Offer `--days N` only as
   an explicit quick preliminary scan, and tell the user its three costs: the
   window filters on `createdate`, the search API caps each object at 10,000
   records, and cross-object checks exclude deals whose associated records
   fall outside the window (exclusions appear as measurement notes). Intent and
   activity acquisition is enabled by default and remains in this same
   single-token, read-only pass. Use `--core-only` only for an explicitly
   limited CRM-object run; it cannot support reliable activity-based recovery
   claims. This is the only data-acquisition pass.
4. Confirm the run manifest is `completed`. If fetching was interrupted, use
   the runner's resume path; do not consume a partial snapshot.
5. Read only `processed/`, `evidence/`, `manifest.json`, and the generated
   judgment artifacts. Never read `outputs/<run>/raw/` as an agent or LLM role.
6. Confirm that deterministic code generated
   `processed/journey_evidence_store.json`,
   `journey_pattern_registry.json`,
   `processed/lifecycle_integrity_measurements.json`,
   `processed/high_intent_cohort_summary.json`,
   `processed/intent_signal_summary.json`,
   `processed/intent_signal_coverage.json`,
   `processed/intent_record_index.json`,
   `processed/intent_signal_store.jsonl`,
   `processed/recovery_routing.json`,
   `processed/stage_transition_summary.json`, `evidence.csv`, and
   `outlier_registry.csv`. Do not recalculate or edit code-owned numbers.
   Also confirm `processed/automation_coverage.json`,
   `processed/workflow_inventory.json`,
   `processed/workflow_dependency_graph.json`,
   `processed/workflow_performance_summary.json`,
   `processed/scoring_activation_summary.json`,
   `processed/automation_scoring_measurements.json`, and
   `automation_evidence.csv`. If automation coverage is unavailable, these
   artifacts must say so explicitly; do not interpret missing workflow access
   as a missing control.
   Stage-entry timestamps are the primary transition evidence; when the
   stage transition summary reports `available: false`, journey paths rest
   on creation order only and conclusions must say so.
   Run schema, relationship, lifecycle, pipeline, source, activity, channel
   intent, journey-link, active-deal escalation, closed-lost recovery, and
   automation/scoring roles only against those processed artifacts.
7. Drive every judgment role through the agent-driven harness — do not
   hand-orchestrate the markdown contracts:

   ~~~bash
   python -m scripts.harness next --run <run_dir>
   ~~~

   `next` picks the task, copies ONLY that role's declared inputs into
   `agent_workspace/inbox/<role>/inputs/`, and writes `instruction.md` plus
   `contract.json` (including the output's JSON Schema). Perform the role
   using only the inbox contents, write `output.json` beside them, then:

   ~~~bash
   python -m scripts.harness submit --run <run_dir> --role <role>
   ~~~

   Each contract carries a `model_tier` (`reasoning` / `standard` /
   `light`) as advisory cost metadata. By default every task follows the
   user's session model — never select a model on the user's behalf. In
   Claude Code, delegate via the bundled project subagent
   `audit-role-<tier>` (it inherits the session model; the user may edit its
   `model:` field to map light/standard tiers to smaller models). In other
   CLIs the tier maps to user-configured profile or model flags. If the user
   opts in to tier mapping, never route reviewer or safety roles below their
   tier. The validation gates are model-independent.

   `submit` validates schema, role identity, and reviewer isolation before
   committing, journals the artifact hash, and auto-runs candidate/review
   consolidation when a phase completes. A rejected submission commits
   nothing — fix `output.json` and submit again. Use `--resubmit` to replace
   a committed artifact (for example during a revision round). Check progress
   any time with `python -m scripts.harness status --run <run_dir>`.
8. Judgment rules while performing tasks: only audit detected patterns whose
   confidence is at least 50; cap severity and downgrade low-confidence
   patterns per `confidence_model.md`; every scored candidate must cite a
   deterministic measurement and an evidence row; reviewers follow the
   intensity in `output_contract.md`, with at most one revision round.
   Workflow configuration can support a root-cause hypothesis, but never
   proves per-record execution or the full scoring formula/version. Intent
   events enrich journey classification and leakage routing; they do not
   replace the existing leakage measurements. Missing-deal recovery, active
   deal escalation, and closed-lost recovery are separate commercial lanes.
9. Never write findings.json, review_trace.json, or any workspace artifact
   directly. The final gate rejects artifacts that were not committed
   through the harness (journal hash check).
10. Compute scores in code. The LLM may explain them but must not change them.
11. Run `python -m scripts.harness finalize --run <run_dir>`. It validates
    everything (including the harness journal), generates the deterministic
    journey-first report set — `lifecycle_integrity_report.md`, a
    self-contained responsive `lifecycle_integrity_report.html` with a score
    hero, journey rail, chronological leakage lanes, record-level action
    evidence, and `operator_appendix.md` with
    technical CRM profiling and implementation detail (print the HTML to PDF
    for distribution) — and runs the final gate. The final report
    agent reviews these generated artifacts against the validated evidence and
    reports discrepancies; it never edits them.
12. The Privacy + Safety Reviewer must inspect every soft blocked-phrase hit
    and write `safety_clearance.json` entries containing the exact phrase,
    filename, current file SHA-256, and a contextual reason. Never clear a
    hard email, phone, or token leak. Then rerun finalize; do not call the
    audit complete unless it reports PASSED.

## Hard boundaries

- The workflow is local-first and read-only. Agents do not call HubSpot APIs;
  the connector fetches once and downstream roles consume artifacts.
- Do not create, update, merge, delete, reassign, or stage-change CRM records,
  properties, workflows, lists, campaigns, or owners.
- Do not expose names, emails, phone numbers, note bodies, tokens, or raw
  contact lists in processed artifacts or agent-visible outputs. The local,
  confidential human report may include sanitized account/contact/deal labels
  and owner names only when needed to make an action auditable. Its HTML and
  Markdown may attach direct HubSpot links to those sanitized record names
  when the portal and record IDs are available; treat the report as
  confidential. It must never expose contact email/phone or message bodies,
  and raw IDs/URLs must never enter CSV, processed, or agent-visible evidence.
- Type and emphasize every named HubSpot asset in the human report, such as
  `Workflow: ...`, `Pipeline: ...`, `HubSpot form: ...`, and
  `HubSpot property: ...`. A named account, contact, or deal may link to its
  HubSpot record; if a safe link cannot be constructed, show emphasized plain
  text instead.
- Make every report card prove its conclusion: name the record, show the dated
  signal chain, explain why it qualifies, state the observed break and its
  commercial consequence, and give the record-specific next action. Do not
  replace this with a generic ideal-state or "missing control" paragraph.
- Name a workflow only when that exact workflow exists in the sanitized
  inventory. State its enabled status, relevant visible action, applicability,
  and the lack of per-record execution proof. Never invent a workflow name or
  claim that a workflow failed without execution evidence.
- Do not assume `Lead → MQL → SQL → Deal → Closed Won` is the only journey.
- Do not treat an outbound or expansion journey as broken because it lacks a
  prior MQL.
- Do not treat every outlier as an issue. Classify it as a valid exception,
  missing data, process breakdown, journey misclassification, or human review.
- Every deal and pipeline claim must be traceable to hashed evidence. Show
  commercial amounts only when they exist on HubSpot deal records. High-intent
  contacts without deals may be reported as a potential recoverable pipeline
  population, but must never receive an estimated monetary value.
- If evidence is weak, emit an observation or human-confirmation item, never a
  high-severity finding.

## Final artifact set

The run must produce the files in `output_contract.md`, including:

`lifecycle_integrity_report.md`, `lifecycle_integrity_report.html`,
`operator_appendix.md`, `journey_map.md`,
`journey_pattern_registry.json`, `findings.json`, `recommendations.md`,
`agent_handoff.md`, `outlier_registry.csv`, `evidence.csv`,
`report_record_evidence.csv`, `crm_context.yaml`,
`schema_discovery_report.md`, `review_trace.json`, `audit_log.json`,
`lifecycle_score.json`, `automation_evidence.csv`, and a passing
`final_gate_report.json`.
