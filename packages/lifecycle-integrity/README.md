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
- metadata-only activity snapshots for calls, emails, communications, tasks,
  meetings, and notes, with separate activity-to-record associations
- record-linked Events and Forms intent evidence plus normalized aggregate
  Campaign channel context for inbound, outbound, ABM, partner, and expansion
  mapping; form submissions are linked by the official contact reference when
  present or by a local-only email match against the fetched contacts snapshot
- campaign asset acquisition has an explicit request budget; if a large portal
  exceeds it, the source is marked `partial` and the report does not present
  channel coverage as complete
- deterministic intent timelines, journey-link checks, active-deal escalation,
  and a separate closed-lost recovery lane
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
- eleven synthetic lifecycle portals and lifecycle-specific golden tests

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

Run all commands from this package directory (`packages/lifecycle-integrity`),
where its `pyproject.toml` and `.env` live. Do not install this package and
`packages/crm-trust` into the same virtual environment because both preserve
agent-native top-level Python modules.

Create one dedicated HubSpot Private App and select these exact scopes:

~~~text
crm.objects.contacts.read
crm.objects.companies.read
crm.objects.deals.read
crm.objects.owners.read
settings.currencies.read
crm.schemas.contacts.read
crm.schemas.companies.read
crm.schemas.deals.read
automation
forms
marketing.campaigns.read
sales-email-read
~~~

Do not enter the wildcard string `crm.schemas.*.read`; select each of the
three exact schema scopes above. There is no separate scoring scope used by
this implementation. Projects are not read as a separate object;
project values synced into CRM records are covered by the relevant object read.
See
[`hubspot_scopes.md`](skills/hubspot-lifecycle-integrity-audit/hubspot_scopes.md)
for the scope-to-feature map, the `automation` safety boundary, activity
coverage, and why Projects/Lead-object scopes are not current report inputs.

~~~bash
cp .env.example .env
# Add HUBSPOT_PRIVATE_APP_TOKEN with all scopes listed above.

python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip   # older bundled pips cannot editable-install a pyproject-only package
pip install -e ".[dev]"
python -m scripts.check_hubspot_connection
python -m scripts.run_lifecycle_integrity_audit --business-name "Your Business Name"
# Explicitly skip intent/activity acquisition only for a core-only scan:
python -m scripts.run_lifecycle_integrity_audit --core-only
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

The lifecycle audit can still run without `automation`; in that case the
report labels workflow/scoring root-cause coverage as unavailable and must not
present the result as a complete Automation & Scoring Integrity Audit.
`--core-only` is a separate explicit option that skips activity, Events, Forms,
and Campaign acquisition for a limited CRM-object scan.

### HubSpot API compatibility

The connector deliberately pins each route to the contract it implements. The
core CRM objects, properties, pipelines, owners, and associations use the
numeric v3/v4 routes; record-linked Events, Campaigns, and currency metadata
use HubSpot's date-versioned `2026-03` routes; Forms use the legacy v2 catalog
plus the legacy v1 submission route; and workflow configuration/performance use
the legacy v4 automation surface. HubSpot documents the numeric API family as
legacy and the workflow v4 API as beta, so these are compatibility boundaries,
not promises that the upstream APIs are stable forever.

There is no silent endpoint fallback. If HubSpot changes or withdraws one of
these contracts, the preflight probe or fetcher marks that source unavailable
or partial, and the report must disclose the limitation rather than treating
the source as zero activity. Updating an API route requires a matching
allowlist change, sanitization review, contract tests, and a new synthetic
fixture run before release. See the [HubSpot date-versioned API reference](https://developers.hubspot.com/docs/reference/api?hsLang=en),
[Events API](https://developers.hubspot.com/docs/api-reference/latest/events/guide),
[Campaigns API](https://developers.hubspot.com/docs/api-reference/latest/marketing/campaigns/guide),
[legacy Forms API reference](https://developers.hubspot.com/docs/api-reference/legacy/overview),
and [workflow v4 API](https://developers.hubspot.com/docs/api-reference/legacy/automation/workflows/guide).

The report may include account, contact, deal, and owner names plus authorized
HubSpot record links so a reviewer can act on a finding. Keep the report
confidential. Emails, phone numbers, message bodies, form values, full URLs,
tokens, and raw snapshots remain outside agent inputs and final reports.

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
large portals complete in tens of minutes. The judgment phase runs 31
isolated agent roles over sanitized aggregates — expect it to dominate LLM
token usage, scaling with findings volume rather than portal size.

## Try it without HubSpot

Eleven generated samples live under examples/lifecycle/:

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
complex_lifecycle_demo
scaled_mixed_motion_demo
~~~

The checked-in samples are public synthetic fixtures and are kept in the
current task-manifest format. If you update the package or copy the package
into a new working directory, regenerate the fixtures before running a full
report workflow so the code-owned artifact manifest is refreshed:

~~~bash
python -m scripts.generate_lifecycle_examples --overwrite
~~~

`--overwrite` is explicit because regeneration replaces only the named
synthetic sample directories under `examples/lifecycle/`; it never touches a
HubSpot portal or an audit output directory.

Each sample includes expected_lifecycle_invariants.json with confidence
ranges, expected findings or observations, and blocked recommendation classes.
All checked-in example emails use non-deliverable `.test` domains and all
example portal labels are synthetic. A CI fixture-safety test prevents a real
customer identity or credential from being added to the public examples.

## Tests

~~~bash
pytest
~~~

The suite covers the inherited connector/snapshot safety guarantees plus
lifecycle confidence, journey assignments, pattern registry integrity,
pattern-aware rules, outliers, reviewer routing, workspace contracts,
deterministic consolidation, exact evidence arithmetic, all golden datasets,
report contracts, and final safety blockers.

When automation coverage is available, the workflow/scoring layer appears
inside the same seven-section lifecycle report and operator appendix. It is
diagnostic only: the score, finding severity, and action lanes remain owned by
the existing deterministic lifecycle rules and reviewer gates. The local
report also includes a sanitized `report_record_evidence.csv` for action: it
may show local-only sanitized account/contact/deal labels, owner, stage,
amount/currency, the dated signal chain, the observed break, configuration
evidence, and next action, but never contact email/phone, message bodies, raw
HubSpot IDs, or raw URLs. The confidential HTML and Markdown reports may make
sanitized account/contact/deal names clickable when the portal and record IDs
are available; those navigation URLs never enter the CSV or processed
evidence. Named HubSpot assets are type-labeled and emphasized so readers can
distinguish a workflow, pipeline, form, or property from narrative prose.
Processed and agent-visible evidence remains hash-only. A workflow is named
only when it exists in the sanitized inventory; the report distinguishes
configuration evidence from per-record execution.
If `settings.currencies.read` is unavailable, unlabeled deal amounts are
withheld rather than shown with a guessed portal default.

## Distribution model

This is a repo-native skill by design: the executable pipeline, role
contracts, examples, and your local `.env` stay in the package workspace, and
every command runs from the package root. The raw snapshot remains local; the
user-selected host agent may process bounded sanitized CRM values needed for
the audit. Installing for Claude Code
(`python -m scripts.install_skill --agent claude`) registers the skill for
discovery via a symlink while execution stays in this package. With
`--copy`, the installer copies the skill plus a complete executable package
snapshot to
`~/.claude/skills/hubspot-lifecycle-integrity-audit/package/`; run from that
`package/` directory and provide its own local `.env` or an environment
variable. The copy is intentionally a frozen snapshot. Codex and Gemini CLI
need no installation at all; they read AGENTS.md / GEMINI.md when working
inside the repository. A wheel is not the supported agent-install surface
because the role contracts and deterministic gates must stay in the same tree
to keep task-manifest paths and validators honest.

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
