# HubSpot Lifecycle Integrity Audit Skill

A local-first, structurally read-only workflow that discovers the real revenue
journeys represented in a HubSpot portal, then audits whether lifecycle state,
associations, attribution, ownership, handoffs, and deal structure can support
trustworthy marketing-to-pipeline reporting.

It does not assume one linear funnel. Inbound new business, outbound
sales-led, ABM, partner-led, expansion/renewal, and mixed-motion journeys are
detected and scored separately.

## What is implemented

- HubSpot read-only connector with an explicit endpoint allowlist
- pagination, retry/backoff, date windows, checkpointing, and resume
- one-pass local snapshots for contacts, companies, deals, owners, pipelines,
  properties, and required associations
- optional task, meeting, and note metadata without note bodies
- deterministic profiling, schema discovery, and custom-property candidates
- stage-entry timestamp capture (hs_v2_date_entered_*) with deterministic
  transition analysis: timestamped funnel progressions, direct-set customers,
  and stage regressions
- sanitized Journey Evidence Store and per-run SHA-256 record identifiers
- Journey Pattern Registry with reproducible 0–100 confidence components
- pattern-aware lifecycle, handoff, association, attribution, state-coherence,
  property-governance, and outlier measurements
- workflow inventory, aggregate workflow performance, and score-output
  activation measurements in a full diagnostic when the token includes
  `automation`
- deterministic workflow dependency checks and evidence-bounded root-cause
  context for lifecycle leakage; missing automation scope degrades to an
  explicit coverage limitation and never becomes a false defect
- evidence-backed finding validation, multi-reviewer routing, adjudication,
  deterministic scoring, report generation, and a final privacy/safety gate
- nine synthetic lifecycle portals and lifecycle-specific golden tests

## Safety model

- The client rejects every request outside its read-only allowlist.
- The single token for a full diagnostic includes HubSpot's `automation`
  scope, but the client allowlist contains only workflow GET and batch-read
  endpoints; workflow create, update, delete, enroll, and action endpoints are
  structurally blocked.
- Tokens are loaded locally and never written to artifacts or error messages.
- Raw snapshots, including full workflow responses needed for local parsing,
  stay under gitignored outputs/; AI roles must never read outputs/*/raw/ and
  the raw directory must not be shared.
- Processed artifacts contain aggregates, redacted values, and salted hashes,
  not contact identity fields or note bodies.
- Every finding has auto_fix_allowed: false.
- Hard email, phone, and token leaks fail the final gate. Dangerous phrases
  require a file-hash-bound Privacy + Safety Reviewer clearance.

## Quickstart

All commands run from the repository root (where `pyproject.toml` and your
`.env` live).

Create one dedicated HubSpot Private App and select these exact scopes:

~~~text
crm.objects.contacts.read
crm.objects.companies.read
crm.objects.deals.read
crm.objects.owners.read
crm.schemas.contacts.read
crm.schemas.companies.read
crm.schemas.deals.read
automation
~~~

HubSpot does not accept `crm.schemas.*.read`, and there is no separate scoring
scope used by this implementation. See
[`hubspot_scopes.md`](skills/hubspot-lifecycle-integrity-audit/hubspot_scopes.md)
for the scope-to-feature map, the `automation` safety boundary, activity
coverage, and why Projects/Lead-object scopes are not current report inputs.

~~~bash
cp .env.example .env
# Add HUBSPOT_PRIVATE_APP_TOKEN with all eight scopes listed above.

python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip   # older bundled pips cannot editable-install a pyproject-only package
pip install -e ".[dev]"
python -m scripts.check_hubspot_connection
python -m scripts.run_lifecycle_integrity_audit
~~~

Full history is the default and the authoritative mode. B2B sales cycles run
6-18 months, so a creation-date window truncates journeys: an in-window deal
often links to contacts and companies created long before the window, and a
windowed snapshot cannot see them. `--days N` exists only for a quick
preliminary scan — it filters on `createdate`, routes through the search API
(hard-capped at 10,000 records per object), and cross-object checks exclude
deals whose associated records fall outside the window (noted on each
affected measurement).

Useful options:

~~~bash
python -m scripts.run_lifecycle_integrity_audit --days 90    # quick preliminary scan only
python -m scripts.run_lifecycle_integrity_audit --include-activities
python -m scripts.run_lifecycle_integrity_audit --resume outputs/run_<timestamp>
python -m scripts.run_lifecycle_integrity_audit --output-dir outputs/my_run
~~~

The preparation command performs the only HubSpot acquisition pass and writes
the sanitized Journey Evidence Store, Journey Pattern Registry, deterministic
measurements, workflow/scoring artifacts, evidence rows, and outlier registry.
The local coding agent then
follows skills/hubspot-lifecycle-integrity-audit/SKILL.md and its isolated role
contracts; every role output is schema-checked against the task manifest.

The lifecycle audit can still run without `automation`, but that is a
core-only run: workflow and scoring root-cause coverage is explicitly
unavailable and must not be presented as a complete Automation & Scoring
Integrity Audit.

The judgment phase is an agent-driven harness: no LLM provider is built in —
your own coding agent (Claude Code, Codex, Gemini CLI, …) supplies the
judgment while the harness owns control flow, input isolation, validation,
and consolidation. The agent loops three verbs:

~~~bash
python -m scripts.harness next --run outputs/run_<timestamp>
#   → materializes ONE task into agent_workspace/inbox/<role>/
#     (inputs/, instruction.md, contract.json with the output JSON Schema);
#     the agent works only inside that inbox and writes output.json

python -m scripts.harness submit --run outputs/run_<timestamp> --role <role>
#   → validates schema, role identity, and reviewer isolation BEFORE
#     committing; journals the artifact hash; auto-runs candidate/review
#     consolidation when a phase completes; rejects invalid work untouched

python -m scripts.harness finalize --run outputs/run_<timestamp>
#   → validators (including the journal hash check), deterministic reports,
#     and the final privacy/safety gate
~~~

Every task contract carries a `model_tier` as advisory cost metadata:
`reasoning` for journey hypotheses, skeptical review, and everything
safety-critical; `standard` for structured findings and recommendations;
`light` for mechanical verification. **By default all tasks follow your
session model — the harness never selects a model for you.** To conserve
token quota you can opt in to tier mapping: in Claude Code, edit the
`model:` field of the bundled
`.claude/agents/audit-role-{light,standard}.md` subagents (e.g.
`model: haiku` for light); in other CLIs, map tiers to your own model or
profile flags. Keep reviewer and safety roles on your strongest model. Every
validation gate is model-independent, and a rejected submission from a
smaller model costs one retry, not audit quality.

`python -m scripts.harness status` shows per-role progress. Artifacts written
around the harness fail the final gate: every judgment artifact must carry a
matching journal hash. The lower-level tools (`scripts.audit_next`,
`scripts.consolidate_findings`, `scripts.validate_findings`,
`scripts.validate_agent_workspace`, `scripts.generate_lifecycle_reports`)
remain available for inspection and debugging.

## The report

The audit's human deliverable follows a journey-first decision structure:
detected selling journeys, evidence-backed operating paths, leakage maps,
existing-deal pipeline exposure, a separate no-deal recovery population, and
targeted repair plans. General CRM-health profiling moves to the operator
appendix. It ships in three
formats from one validated view model: `lifecycle_integrity_report.md` (the
gated canonical text), `lifecycle_integrity_report.html` (self-contained,
responsive, inline journey and leakage charts, no external assets — print it to PDF for
distribution), and `operator_appendix.md` (full finding and implementation
detail plus supporting technical CRM profile). Amounts come only from existing
HubSpot deals; high-intent contacts without deals are shown only as a potential
recoverable population. Language rules are enforced in code, not by convention:
numbers first, plain sentences, no audience meta-language, machine keys
humanized. All three files pass the same leak scan and verbatim-score checks. The footer uses the
Smartify Marketing brand, slogan, website, and GitHub credit constants at the
top of `core/lifecycle_human_report.py`.

## What a run costs

The acquisition pass is paced conservatively (~8 requests/second, stricter on
search endpoints). Full history uses plain list pagination — no search cap —
and snapshots roughly 50,000 records in about a minute per object type; even
large portals complete in tens of minutes. The judgment phase runs 27
isolated agent roles over sanitized aggregates — expect it to dominate LLM
token usage, scaling with findings volume rather than portal size.

## Try it without HubSpot

Nine generated samples live under examples/lifecycle/:

~~~text
clean_inbound_crm_sample
outbound_sales_led_sample
abm_sample
mixed_motion_scaleup_sample
partner_led_sample
expansion_renewal_sample
legacy_property_sprawl_sample
broken_association_sample
pipeline_leakage_sample
~~~

Regenerate them with:

~~~bash
python -m scripts.generate_lifecycle_examples
~~~

Each sample includes expected_lifecycle_invariants.json with confidence
ranges, expected findings or observations, and blocked recommendation classes.

## Tests

~~~bash
pytest
~~~

The suite covers the inherited connector/snapshot safety guarantees plus
lifecycle confidence, journey assignments, pattern registry integrity,
pattern-aware rules, outliers, reviewer routing, workspace contracts,
deterministic consolidation, exact evidence arithmetic, all nine golden
datasets, report contracts, and final safety blockers.

When automation coverage is available, the workflow/scoring layer appears
inside the same nine-section lifecycle report and operator appendix. It is
diagnostic only: the score, finding severity, and action lanes remain owned by
the existing deterministic lifecycle rules and reviewer gates.

## Distribution model

This is a repo-native skill by design: the executable pipeline, role
contracts, examples, and your local `.env` stay in the repository workspace,
and every command runs from the repository root. The raw snapshot remains
local; the user-selected host agent may process bounded sanitized CRM values
needed for the audit. Installing for Claude Code
(`python -m scripts.install_skill --agent claude`) only registers the skill
for discovery via a symlink — execution stays here. Codex and Gemini CLI need
no installation at all; they read AGENTS.md / GEMINI.md when working inside
the repository. Building a wheel or copying `skills/` elsewhere is not a
supported deployment: the role contracts and the deterministic gates must
stay in the same tree to keep the task-manifest paths and validators honest.

## Repository layout note

The lifecycle audit evolved from an earlier CRM trust audit and reuses its
snapshot, sanitization, and profiling layer. Modules named without the
`lifecycle_` prefix (`core/rules.py`, `core/final_gate.py`, `core/scoring.py`,
`core/synthetic_datasets.py`, and the `examples/*_sample` directories outside
`examples/lifecycle/`) belong to that legacy flow; each is marked in its
docstring. The lifecycle flow is the maintained entry point.

## License

MIT — see [LICENSE](LICENSE). Created by **Alice Ren, Founder of Smartify
Marketing**. Smartify names, logos, and brand presentation remain Smartify
Marketing brand assets.
