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
