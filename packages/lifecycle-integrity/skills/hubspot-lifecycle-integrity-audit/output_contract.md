# Output contract

## Run directory

```text
outputs/run_<timestamp>/
  raw/                         # local-only, gitignored, never read by agents
  processed/                   # sanitized aggregates and evidence store
  evidence/                    # redacted evidence rows
  lifecycle_integrity_report.md
  lifecycle_integrity_report.html
  operator_appendix.md
  journey_map.md
  journey_pattern_registry.json
  findings.json
  recommendations.md
  agent_handoff.md
  outlier_registry.csv
  evidence.csv
  crm_context.yaml
  schema_discovery_report.md
  review_trace.json
  audit_log.json
  lifecycle_score.json
  safety_clearance.json         # only when soft phrase hits require clearance
  final_gate_report.json
  manifest.json
  processed/automation_coverage.json
  processed/workflow_inventory.json
  processed/workflow_dependency_graph.json
  processed/workflow_performance_summary.json
  processed/scoring_activation_summary.json
  processed/automation_scoring_measurements.json
  automation_evidence.csv
```

The raw snapshot also contains contacts, companies, deals, owners, pipelines,
property definitions, and contact/company/deal association files. It must have
a completed manifest before downstream work starts.

## Machine-readable contracts

Journey registry must include `primary_model`, `overall_confidence`, `patterns`,
`ambiguous_areas`, and `human_confirmation_needed`. Each pattern contains its
type, existence, score, label, supporting/contradicting evidence, and allowed
audit level.

Each scored finding must include `finding_id`, `journey_pattern`,
`integrity_dimension`, `severity`, `confidence`, `evidence_refs`, a denominator
or materiality explanation, `affected_records` or a qualitative explanation,
`business_impact`, `recommended_action`, `recommendation_type`,
`auto_fix_allowed: false`,
`assumptions`, and `limitations`.

`evidence.csv` columns:

```text
finding_id,journey_pattern,object_type,record_id_hash,field_name,issue_type,
current_value_redacted,confidence,recommended_review,pipeline_label,
deal_stage_label,amount_included_in_aggregate,currency_bucket
```

`outlier_registry.csv` columns:

```text
outlier_id,journey_pattern,object_type,record_id_hash,outlier_type,
classification,confidence,reason,recommended_review
```

## Report headings

`lifecycle_integrity_report.md` and the HTML report must use the same nine
journey-first decision sections:

1. Executive Decision Summary
2. Detected Selling Journey Model
3. Journey Evidence and Operating Paths
4. Journey Leakage Map
5. Pipeline Exposure and Recoverable Population
6. Leakage Findings and Root Causes
7. Recovery and System Repair Plan
8. Monitoring and Next Review
9. Evidence, Assumptions, and Limits

The HTML report is self-contained, responsive, print-ready, and contains
directly labelled visuals for journey confidence, operating paths, leakage
hotspots, existing-deal exposure, and high-intent pre-deal recovery
populations. General CRM completeness, identity, association, lifecycle
distribution, and data-age diagnostics belong in `operator_appendix.md`.

The overall lifecycle integrity score must be visually prominent and explain
its deterministic interpretation: the score starts at 100, deductions come
only from approved/revised findings, each deducted dimension is named, mapping
confidence remains separate, candidate leakage does not affect the score until
adjudicated, and the score is not a healthy-record percentage, conversion
rate, or estimate of revenue loss.

Every deal and pipeline claim must trace to `evidence.csv` by salted record
hash plus sanitised pipeline/stage labels. Commercial amounts may be aggregated
only from existing HubSpot deal `amount` values and must retain a currency
bucket or say portal default currency. Contacts without deals can be counted
as a potential recoverable pipeline population, but their amount must be null
in machine artifacts and shown as "No amount assigned" in human reports.

`operator_appendix.md` contains every validated finding plus exact target,
current state, desired state, implementation steps, owner, approval gate,
expected result, evidence basis, measurable success condition, deterministic
measurement detail, and the supporting technical CRM profile.
When full-diagnostic automation coverage is available, it also contains
workflow coverage, dependency, performance, score-output activation, and
limitations. Without `automation`, the report must label this layer core-only
and must not claim a complete Automation & Scoring Integrity Audit.
automation_evidence.csv is the sanitized configuration evidence file; it must
never contain raw workflow payloads, action bodies, URLs, or record lists.

Automation root-cause assessments are subordinate to lifecycle findings. They
may explain a finding's configuration context, but cannot create a new scored
finding, change the deterministic lifecycle score, infer a deal amount, or
authorize a HubSpot write.

The automation analysis output is a closed contract containing `summary`,
`available_signals`, `control_gaps`, `evidence_refs`, `limitations`, and
`human_confirmation_needed`. Root-cause assessments must reference an existing
finding, existing workflow aliases or score fields, and an existing sanitized
evidence path. Invalid cross-references fail the final gate. When a validated
automation root cause exists, the recommendation plan must make its workflow
alias or score field the explicit system-repair target rather than producing a
generic lifecycle recommendation.

`agent_handoff.md` must state that the audit was read-only and that no CRM
write is allowed without explicit user authorization and an approved plan.

## Review routing

Low-risk deterministic findings need code validation and a safety scan.
Interpretive findings need data-fidelity and logic review. High-risk strategic
findings also need journey-mapping, false-positive, and privacy/safety review.
`needs_revision` may loop once only; then adjudicate as approved, observation,
human confirmation, or rejected.
