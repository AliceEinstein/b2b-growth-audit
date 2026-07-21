# B2B Growth Audit

Find where unreliable CRM data and broken lifecycle execution limit B2B
growth — and what to fix next.

Created by [Alice Ren](https://www.linkedin.com/in/b2b-marketing-alice/), founder of [Smartify Marketing](https://smartifymarketing.com).

B2B Growth Audit is an open-source package of two independent, read-only
HubSpot audit skills. Together they answer the two questions behind any
credible marketing-to-pipeline decision:

1. Is the CRM evidence reliable enough to make a decision?
2. Is the business turning demand into pipeline without preventable breaks?

Each report connects its score to the records, properties, associations,
journeys, and control failures behind the result, then turns that evidence
into a prioritized review and repair plan.

## Choose the audit that matches your question

### CRM Trust Audit — establish what the business can trust

Use **CRM Trust Audit** when teams disagree about the numbers, attribution is
uncertain, reporting depends on fragile properties, or a CMO has inherited a
HubSpot portal and needs to know whether it is fit for decision-making.

It examines data completeness, identity validity, source capture, lifecycle
coherence, Company–Contact–Deal associations, pipeline hygiene, property
governance, and record traceability. The result is a defensible CRM Trust
Score, a clear boundary around which reports can be trusted, and an
evidence-backed remediation plan.

[Run the CRM Trust Audit](packages/crm-trust/README.md)

### Lifecycle Integrity Audit — find where demand and pipeline break

Use **Lifecycle Integrity Audit** when the CRM is usable but the business
needs to understand how it actually sells, whether each journey is fully
connected, and where qualified demand or active pipeline is being missed.

It identifies inbound, outbound, ABM, partner, expansion/renewal, and
mixed-motion journeys from HubSpot evidence. It then traces contacts,
accounts, deals, activities, intent signals, workflows, and scoring controls
to find broken handoffs, ignored high intent, exposed open deals, and credible
closed-lost recovery opportunities. The result is a journey-specific
Lifecycle Integrity Score and an action plan tied to real commercial records.

[Run the Lifecycle Integrity Audit](packages/lifecycle-integrity/README.md)

### How the two audits fit together

Either skill can run independently. When using both, run **CRM Trust Audit
first**: Lifecycle Integrity relies on CRM evidence, so lifecycle conclusions
are only as dependable as the underlying data and associations. A weak CRM
Trust result limits confidence in the affected lifecycle conclusions and
identifies which evidence needs remediation or confirmation before the
business acts.

The reports remain separate and their scores must not be averaged. Read the
outputs in this order:

1. CRM Trust Score — the reliability boundary for the evidence.
2. Journey Mapping Confidence — how confidently the selling model was
   identified.
3. Lifecycle Integrity Score — validated leakage inside the identified
   journeys.
4. Existing deal exposure and recoverable populations — the action layer.

The lifecycle classifier currently evaluates inbound, outbound, ABM, partner,
expansion/renewal, and mixed-motion behavior. Mixed-motion is evaluated only
after the other motion hypotheses are available. An unclassified motion is
kept as an evidence-backed observation requiring human confirmation; it is
not silently forced into a catch-all category.

Contacts, companies, deals, owners, their properties and associations are the
shared evidence base. Lifecycle Integrity can additionally inspect sanitized
workflow configuration, aggregate workflow performance, and score-like CRM
properties when its token includes `automation`. A field synced from another
tool may be used when it exists in HubSpot and provides evidence for journey
classification or leakage detection. The audits do not write, merge, delete,
reassign, stage-change, or enroll CRM records.

Use the exact permission checklist for the selected package:

- [CRM Trust permissions](packages/crm-trust/skills/hubspot-crm-trust-audit/hubspot_scopes.md)
- [Lifecycle Integrity permissions](packages/lifecycle-integrity/skills/hubspot-lifecycle-integrity-audit/hubspot_scopes.md)

## Independent report deliverables

Each audit produces its own standalone Markdown and HTML report, evidence set,
operator appendix, score, and final-gate result. The CRM Trust report and the
Lifecycle Integrity report must remain separate files and independently
distributable. They may be read together by a CMO or CEO, but neither report
depends on, imports, or replaces the other.

The scores are separate decision inputs: CRM Trust establishes the evidence
reliability boundary; Journey Mapping Confidence describes how well the
lifecycle model was identified; Lifecycle Integrity describes validated
breaks inside that model. Existing deal exposure and no-deal recoverable
populations remain in the Lifecycle Integrity report only.

## Safety boundary

Real/customer raw snapshots, tokens, note bodies, and local outputs stay
outside the open-source distribution and are protected by `.gitignore`. A
local report may contain the minimum account, contact, deal, and owner names
needed for a CMO to act; treat it as a confidential business artifact and do
not publish it. The user may authorize a host LLM to process bounded CRM
values needed for deep journey and finding analysis. Agent contracts still
prohibit raw snapshot access, direct HubSpot API calls, token output, and CRM
writes.

The checked-in `examples/` directories are synthetic QA fixtures, not customer
exports. Their email identities use reserved non-deliverable domains, and CI
checks the fixture tree for non-reserved email domains and HubSpot-looking
tokens before a change can merge.

## Development

Each package is independently runnable and tested from its own directory. Run
the agent from the selected package directory so that Codex, Claude Code, or
Gemini CLI loads that package's instructions:

```bash
(cd packages/crm-trust && pytest)
(cd packages/lifecycle-integrity && pytest)
```

Use one virtual environment per package. The packages intentionally preserve
their agent-native top-level `connectors`, `core`, and `scripts` modules; do
not install both editable packages into the same virtual environment because
the second installation can shadow the first package's modules.

The package boundaries are intentional: the two audits share the HubSpot
read-only principle, but retain separate deterministic scoring and evidence
contracts so a CRM trust defect cannot be hidden by lifecycle scoring (or
vice versa).

## License

MIT — see [LICENSE](LICENSE). [Smartify Marketing](https://smartifymarketing.com)
names, logos, and brand presentation remain Smartify Marketing brand assets.
