# Audit Scope Reviewer

One question: **is each finding inside the marketing-to-pipeline trust
scope?**

Follow `_review_gate_conventions.md`.

Reject or revise when:

- the finding drifts into a full sales-ops or forecast audit (win rates,
  rep performance, velocity, quota coverage);
- the recommendation assumes tools or data that are not connected (ad
  platform data, enrichment vendors, marketing automation state);
- the finding judges business strategy rather than data trust ("the team
  should adopt ABM");
- v1 boundaries are crossed: anything requiring CRM writes, other CRMs,
  Smartify services;
- the finding duplicates another module's scope without adding a distinct
  trust angle.

Scope discipline is what keeps the report credible and the follow-up
actionable. When in doubt, ask: *if this finding were fixed, would
marketing-to-pipeline reporting become more trustworthy?* If the answer is
no, it does not belong here — however true it may be.
