# Audit scope

## In scope

- CRM schema and custom-property intent discovery.
- Contact, company, deal, owner, pipeline, stage, and required association
  coverage.
- Lifecycle state usage and contradictions.
- Journey-specific handoffs and ownership signals.
- Attribution continuity from source/campaign/referral fields into pipeline.
- Account-centric and contact-centric relationship integrity.
- Outlier classification and confidence-aware recommendations.
- High-intent contact populations with missing ownership or deal progression,
  without assigning monetary value where no deal exists.
- Actual amount on existing open deals with traceable leakage-candidate
  signals, reported as exposure for review rather than forecast loss.
- Workflow configuration and aggregate performance for controls that can
  explain lifecycle entry, stage progression, ownership/routing, attribution,
  handoff, deal creation, renewal/expansion, and journey-relevant score
  activation.
- Score-like HubSpot property outputs and their observable workflow activation
  relationships. This is an activation/output audit, not a reconstruction of
  a private scoring formula.

## Detected journey patterns

1. Inbound new business
2. Outbound sales-led
3. ABM / account-based
4. Partner-led
5. Expansion / renewal
6. Mixed-motion journeys

## Out of scope

Do not audit full RevOps cleanup, sales forecasting, ad performance, website
conversion, migration completeness, or any non-HubSpot system. Do not request
extra system artifacts. The acquisition pass may receive a full workflow
response locally so code can derive configuration signals, but agents and
reports must never read or expose raw action bodies, external URLs, enrollment
lists, per-record execution logs, or hidden score criteria beyond the declared
sanitized outputs. Do not create, edit, enroll, delete, or otherwise mutate
workflows or scoring. A field synced from another tool can be used only after
it exists as a HubSpot property. The audit explains how the represented selling
journey can leak inside HubSpot, not whether a channel or sales team performs
well.
