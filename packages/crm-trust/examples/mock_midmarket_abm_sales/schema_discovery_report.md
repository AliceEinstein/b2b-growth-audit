# Schema Discovery Report

## Snapshot Overview

The snapshot is completed, full-history, and non-truncated: 360 contacts, 60 companies, 36 deals, 8 owners, and 2 defined pipelines. Association coverage is 77.8% for contact-to-company, 88.9% for deal-to-company, and 83.3% for deal-to-contact. See [snapshot_summary.json](processed/snapshot_summary.json) and [activity_summary.json](processed/activity_summary.json).

## Canonical Field Map

| Business concept | Candidate | Confidence | Evidence |
|---|---|---|---|
| Lifecycle stage | `lifecyclestage` | High | Present for 360/360 contacts; [snapshot summary](processed/snapshot_summary.json) |
| Original source | `hs_analytics_source` | High | 88.9% overall fill, 77.8% recent-half fill; [source candidates](processed/source_field_candidates.json) |
| Latest source | `hs_latest_source` | High | 91.7% fill; [source candidates](processed/source_field_candidates.json) |
| Campaign/source field | `campaign_source` | Medium; confirm | Multiple overlapping source-like candidates; [property evidence](evidence/property_governance.csv) |
| Account ownership | `hubspot_owner_id` on companies | Medium; confirm | Company owner coverage 91.7%; [snapshot summary](processed/snapshot_summary.json) |
| Deal ownership | `hubspot_owner_id` on deals | High | Deal owner coverage 88.9%; [snapshot summary](processed/snapshot_summary.json) |
| Deal pipeline | `pipeline` | High | Two definitions plus 2 unknown references; [pipeline summary](processed/pipeline_summary.json) |

## Legacy Candidates

Three source-like fields show older-half usage with no recent-half usage. `old_lead_source_2021` is the clearest naming candidate, but the measurement is intentionally a candidate signal rather than a deletion decision. See [property governance measurement](processed/measurements/property_governance.json).

## Duplicate/Overlap Candidates

Eleven of 17 source-like fields are name-collision candidates. The groups include campaign/source, lead/source, and UTM/source variants. Shared names and overlapping usage do not prove that fields are interchangeable; the owner must confirm the canonical map before workflow changes.

## Open Questions for the Human Owner

- Does customer lifecycle stage require a closed-won deal?
- Which lifecycle stages require a deal association?
- Which source property is authoritative for each report and workflow?
- Are shared company domains subsidiaries, regional entities, or duplicates?
- Which deal stages require amount, owner, and a defined pipeline?

## Confidence Notes

All CRM-derived values in processed artifacts are marked as untrusted data. Identity completeness is aggregate-only. Operational recency is a last-modified proxy and should not be interpreted as proof of human, marketing, or sales activity. The LLM agents must read processed artifacts and evidence only, never `raw/`.
