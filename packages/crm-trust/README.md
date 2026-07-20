# HubSpot CRM Trust Audit

This package contains one local-first audit that runs inside Claude Code,
Codex, Gemini CLI, or another capable coding-agent environment. The separate
Lifecycle Integrity package is an independent companion, not a hidden second
report in this package.

It answers one question:

> Can marketing credibly explain how leads, sources, campaigns, lifecycle
> stages, companies, and deals connect to pipeline impact?

## Design principle

**Measure in code, judge through bounded artifacts.** Deterministic Python
fetches data, computes counts/percentages/evidence, controls stage order, and
does score arithmetic. In V1, your local coding agent (Codex, Claude Code, or
another host) reads generated task packets and writes structured judgment
artifacts. No OpenAI or Anthropic API key is required inside this repository.
The harness validates every artifact before advancing and renders the final
report from validated data. No hardcoded one-size-fits-all thresholds.

Each completed audit produces a self-contained, Smartify-styled HTML report,
an accessible Markdown equivalent, an operator appendix, and the underlying
CSV/JSON evidence. The HTML includes CRM scale cards, completeness and
validity bars, record-age distribution, funnel and association graphics, and
print styles for PDF export. Editable Word delivery is an optional conversion
of the same validated report content, never a separate model rewrite.

## Safety model

- **Structurally read-only**: the HubSpot client only sends requests matching
  an explicit read-endpoint allowlist ([client.py](connectors/hubspot/client.py)).
  There is no write code in this repository — enforced by tests.
- **Local-only identity check**: contact emails, names, and phone numbers may
  be fetched into the owner-authorized local raw snapshot to measure
  completeness. Sanitized Company/Deal names and owner labels may appear in
  the confidential local report for action; contact names, emails, and phone
  numbers do not.
- **Raw snapshots stay local**: snapshots live in `outputs/` (gitignored) and
  are never sent to a Smartify backend. The user-selected host agent may read
  bounded processed CRM values needed for analysis; contact identity fields,
  note bodies, tokens, and raw snapshot trees remain outside agent tasks.
- **Leak net**: every non-raw text artifact is scanned for email/phone/token
  formats (hard fail); final deliverables are also scanned for dangerous
  recommendation phrases that require contextual safety review.

## Quickstart

First create a dedicated HubSpot Private App with these seven exact scopes:

```text
crm.objects.contacts.read
crm.objects.companies.read
crm.objects.deals.read
crm.objects.owners.read
crm.schemas.contacts.read
crm.schemas.companies.read
crm.schemas.deals.read
```

Do not enter the wildcard string `crm.schemas.*.read`; select each of the
three exact schema scopes above. See
[`hubspot_scopes.md`](skills/hubspot-crm-trust-audit/hubspot_scopes.md) for the
click-by-click setup, scope-to-endpoint mapping, and scopes not to grant.

```bash
cp .env.example .env
# add your dedicated HubSpot Private App token to .env

pip install -e ".[dev]"

python -m scripts.check_hubspot_connection
python -m scripts.run_crm_trust_audit --business-name "Your Business Name"
# Optional recent-only view:
# python -m scripts.run_crm_trust_audit --days 90
# Resume a timed-out or failed snapshot:
# python -m scripts.run_crm_trust_audit --resume outputs/run_<timestamp>
# Keep raw PII for a different local retention period (days):
# python -m scripts.run_crm_trust_audit --raw-retention-days 730
# Preview which expired raw trees would be removed (the audit still runs):
# python -m scripts.run_crm_trust_audit --dry-run
```

Snapshot output lands in the skill repository's absolute `outputs/` directory
by default (or the path supplied with `--output-root`). The output root has a
deny-by-default `.gitignore` guard.
Each page is checkpointed under `raw/.checkpoints/`; only snapshots with
`manifest.json.status == "completed"` are accepted by later phases. Processed
aggregates remain after expired raw trees are pruned for local diffing. A
stored final-gate PASS can be checked with:

```bash
python -m scripts.verify_final_gate --run outputs/run_<timestamp>
```

Retention removes the entire expired `raw/` tree, including its local
`run_salt.txt`. This is privacy-positive but means old evidence hashes are no
longer reversible or operationally matchable to CRM records after retention.

The business name is supplied explicitly because HubSpot's account-info API
does not guarantee a display name. The portal ID is read automatically and is
used only to build direct Company/Deal links in the local report. The report
labels HubSpot-origin properties, stages, pipelines, Companies, and Deals so
configured CRM terms are not mistaken for audit prose.

## Use with your coding agent

The skill is agent-agnostic: deterministic Python scripts + markdown role
instructions that any capable coding agent can follow. Each agent picks up
its native context file at the repo root, and all three route to the same
canonical rules (AGENTS.md):

| Agent | Context file | Setup |
|---|---|---|
| Claude Code | `CLAUDE.md` | none — or register globally: `python -m scripts.install_skill --agent claude` |
| Codex | `AGENTS.md` | none — work inside this repo |
| Gemini CLI | `GEMINI.md` | none — work inside this repo |

Then just ask your agent: *"run the HubSpot CRM trust audit"*. It will run
the scripts, use `python -m scripts.run_audit_harness`, perform the generated
judgment tasks in `skills/hubspot-crm-trust-audit/subagents/`, and validate
its outputs against the deterministic gates. The harness never requires a
model API key in V1.

Claude's default global install is a symlink and keeps the executable package
in this repository. If you use `--copy`, the installer copies the skill plus a
complete package snapshot to
`~/.claude/skills/hubspot-crm-trust-audit/package/`; run the audit from that
`package/` directory and provide its own local `.env` or an environment
variable. The copied snapshot does not receive repository updates
automatically. Codex and Gemini remain repository-native and need no global
install.

For a completed snapshot, the explicit loop is:

```bash
python -m scripts.run_audit_harness init --run outputs/run_<timestamp>
# Have the host agent complete the task packet printed by the harness.
python -m scripts.run_audit_harness advance --run outputs/run_<timestamp>
python -m scripts.run_audit_harness status --run outputs/run_<timestamp>
```

## Status

| Phase | Scope | Status |
|---|---|---|
| 1 | Skeleton, safety boundary, leak net | ✅ |
| 2 | HubSpot connector, snapshot fetch | ✅ |
| 3 | Profiling + schema discovery | ✅ |
| 4 | Audit measurements + scoring arithmetic | ✅ |
| 5 | LLM review gates | ✅ |
| 6 | Reports + final safety gate | ✅ |
| 7 | Synthetic datasets + golden tests | ✅ |

## Try it without a HubSpot portal

`examples/` ships six synthetic CRM sample portals (clean, messy scaleup,
broken attribution, property sprawl, broken associations, multi-pipeline),
each a complete runnable run directory with machine-checkable
`expected_invariants.json`:

```bash
python -m scripts.run_audit_measurements --run examples/messy_scaleup_sample
```

Regenerate them anytime with `python -m scripts.generate_examples`.

## Using the two independent reports together

The CRM Trust report and Lifecycle Integrity report are separate deliverables,
with separate evidence, scores, and final gates. Do not merge them into one
report or average their scores. Read them in this order:

1. CRM Trust Score — whether the underlying CRM evidence is reliable enough
   for reporting.
2. Journey Mapping Confidence — how confidently the lifecycle audit identified
   the represented selling motions.
3. Lifecycle Integrity Score — validated breaks inside those motions.
4. Existing-deal exposure and recoverable populations — the action layer. Deal
   amounts come only from existing HubSpot deals; contacts without deals never
   receive an estimated amount.

When both audits are available, prioritize CRM trust prerequisites before
depending on lifecycle findings whose evidence relies on the affected data
structure. The common decision context is conceptual only; each report remains
independently traceable and distributable.

## Tests

```bash
pytest
```

## License and authorship

MIT — see [LICENSE](LICENSE). Created by **Alice Ren, Founder of Smartify
Marketing**. The MIT license covers the source code; Smartify names, logos, and
brand presentation remain Smartify Marketing brand assets.
