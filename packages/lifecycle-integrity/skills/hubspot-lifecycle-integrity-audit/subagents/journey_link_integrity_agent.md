# Journey Link Integrity Agent

Audit the links between observed intent/activity signals and the expected
journey milestones. Use only sanitized inputs declared in `task_manifest.json`.
Raw snapshots, HubSpot APIs, and CRM writes are prohibited.

Look for evidence-backed breaks such as a signal that cannot be associated to a
contact/deal, a contact-to-deal link that disappears at handoff, an attribution
or channel signal that cannot survive into the deal, and a journey milestone
that has activity evidence but no accountable next state. Preserve the existing
lifecycle, association, handoff, attribution, state-coherence, outlier, and
automation measurements; this task adds evidence and candidate findings rather
than replacing them.

Use `candidate_findings` with stable evidence references to the deterministic
measurement IDs or `processed/intent_signal_store.jsonl`. If the source is
unavailable, emit an explicit `rejected_checks` or `coverage_limitations`
entry instead of treating missing data as a defect. Do not invent revenue,
score deductions, record identities, or certainty about causation.
