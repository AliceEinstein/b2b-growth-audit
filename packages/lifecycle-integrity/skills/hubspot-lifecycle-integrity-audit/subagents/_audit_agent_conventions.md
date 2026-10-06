# Audit-agent conventions

Inputs are sanitized `processed/` artifacts, the Journey Pattern Registry,
`crm_context.yaml`, and the relevant evidence CSV. Never read `raw/`.

Emit structured JSON plus a short summary. Copy numeric values verbatim from
deterministic measurements. A missing or unavailable measurement is a stated
coverage limitation, not a zero. Every candidate finding must include a
finding ID, journey pattern, integrity dimension, evidence references,
denominator/materiality, confidence, severity, business impact,
recommended_action, recommendation type, review intensity, and
`auto_fix_allowed: false`.

No causality or business-performance claim may be inferred from CRM structure
alone. Use observations or `requires_human_confirmation` when field intent,
journey assignment, activity data, or the business rule is ambiguous.

The harness checks these rules when you submit and rejects the file if one fails:

- `review_intensity` follows severity: `critical` or `high` → `high`,
  `medium` → `medium`, `low` or `observation` → `low`.
- Every finding cites at least one measurement as
  `evidence.csv#finding_id=<measurement id>`, and at most one `primary`
  measurement. A finding that is not an observation must cite a measurement
  with evidence rows. A finding with no measurement behind it is an observation.
- `denominator`, `affected_records` and `affected_percentage`, when set, equal
  the cited measurement's values.
- A journey pattern below 50 confidence can only produce observations.
- `confidence_label` matches `confidence_score` (85+ very_high, 70+ high,
  50+ medium, 30+ low, below 30 insufficient).
- `rejected_checks` entries are objects of strings, such as
  `{"check": "...", "reason": "..."}`.
