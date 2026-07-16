# B2B Growth Audit

Read-only HubSpot audits for B2B marketing-to-pipeline decisions, created by
Alice Ren, Founder of Smartify Marketing.

This distribution contains two complementary skills:

- `packages/crm-trust/` — **CRM Trust Audit**: can HubSpot be trusted as the
  single source of truth for attribution, lifecycle, associations, pipeline
  hygiene, and reporting?
- `packages/lifecycle-integrity/` — **Lifecycle Integrity Audit**: what
  selling journeys are actually represented, where do those journeys leak,
  and which existing deals or no-deal high-intent populations need repair?

Start with the package you need:

- [CRM Trust Audit quickstart](packages/crm-trust/README.md)
- [Lifecycle Integrity Audit quickstart](packages/lifecycle-integrity/README.md)

They answer different questions and their scores must not be averaged. Read
the outputs in this order:

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

The scores are decision inputs, not a blended score: CRM Trust establishes the
evidence reliability boundary; Journey Mapping Confidence describes how well
the lifecycle model was identified; Lifecycle Integrity describes validated
breaks inside that model. Existing deal exposure and no-deal recoverable
populations remain in the Lifecycle Integrity report only.

## Safety boundary

Raw snapshots, tokens, contact identity, note bodies, and local outputs stay
outside the open-source distribution and are protected by `.gitignore`. The
user may authorize a host LLM to process bounded, sanitized CRM values needed
for deep journey and finding analysis. The agent contracts still prohibit raw
snapshot access, direct HubSpot API calls, token output, and CRM writes.

## Development

Each package is independently runnable and tested from its own directory:

```bash
cd packages/crm-trust && pytest
cd ../lifecycle-integrity && pytest
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

MIT — see [LICENSE](LICENSE). Smartify Marketing names, logos, and brand
presentation remain Smartify Marketing brand assets.
