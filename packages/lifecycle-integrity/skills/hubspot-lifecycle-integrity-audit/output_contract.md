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
  report_record_evidence.csv
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
  processed/intent_signal_summary.json
  processed/intent_signal_coverage.json
  processed/intent_record_index.json
  processed/intent_signal_store.jsonl
  processed/recovery_routing.json
  automation_evidence.csv
```

The raw snapshot also contains contacts, companies, deals, owners, pipelines,
activity metadata, event/form/campaign source responses, property definitions,
and contact/company/deal/activity association files. It must have
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

### Coverage status semantics

Every requested intent/activity source must carry one of these statuses in
`processed/intent_signal_coverage.json` and the corresponding manifest
section:

| Status | Meaning | Permitted interpretation |
|---|---|---|
| `available` / `full` | The endpoint and requested pages returned successfully and rows may exist. | Use the returned evidence. |
| `partial` | Some event types, records, pages, or campaign assets were unavailable or the explicit request budget was reached. | Use only returned evidence and disclose the blind spot. |
| `observed_no_events` | The endpoint succeeded, but the completed snapshot contained zero qualifying rows for that source. | Report “none observed in this snapshot”; do not call it permission denied, and do not infer a recovery or a leak from emptiness. |
| `permission_or_api_unavailable` / `permission_denied` / `unavailable` | The endpoint could not be read or the token/product did not expose it. | Treat the source as unknown, never as zero. |
| `not_requested` | The user explicitly selected `--core-only` or otherwise excluded the source. | Do not make activity-based conclusions. |

`observed_no_events` is intentionally different from `unavailable`: it tells a
reader that the connector reached the source and found no qualifying rows in
the selected snapshot window. The report must still show the time window and
any partial/association limitations. This status never creates a scored
finding by itself.

## Report headings

`lifecycle_integrity_report.md` and the HTML report must use the same seven
journey-first decision sections:

1. Executive Verdict
2. How {Business Name} Sells
3. Where the Journey Breaks by Account, Contact, and Deal
4. Action Queue
5. Why These Breaks Exist
6. 30-Day Recovery Plan
7. Monitor and Verify

The HTML report is self-contained, responsive, print-ready, and uses a clear
score hero, journey rail, chronological lanes, responsive evidence tables, and
record cards. It connects each business outcome to a named account, contact,
or deal and shows why the record qualified, the dated evidence timeline, the
actual break, the commercial consequence, configuration evidence, the next
action, and the evidence trace. It must not substitute a generic ideal-state
"missing control" paragraph for the observed record-level break. It also
separates missing-deal recovery, active-deal escalation, and closed-lost
recovery; closed-lost historical amounts are context only and never open
pipeline or recoverable revenue. General CRM completeness, identity,
association, lifecycle distribution, and data-age diagnostics belong in
`operator_appendix.md`.

The overall lifecycle integrity score must be visually prominent and explain
its deterministic interpretation: it is a weighted health score for five
journey links (intent→owner, owner→deal/valid skip, record continuity, deal
progression, and post-close recovery). Confirmed breaks use their affected
share; unresolved deterministic candidates are included at half weight in the
deterministic formula. The executive report explains once, in plain language,
that unresolved rule matches can move the score; the exact formula belongs in
the operator appendix. Closed-lost recovery opportunities remain visible but
do not move the score by themselves. Mapping confidence remains separate. The
score is not a healthy-record percentage, conversion rate, or estimate of
revenue loss.

Every deal and pipeline claim must trace to `evidence.csv` by salted record
hash plus sanitised pipeline/stage labels. The local-only
`report_record_evidence.csv` joins those hashes to the minimum business labels
needed for action (sanitized account/contact/deal name, owner, pipeline,
stage, amount/currency, signal timing, observed break, configuration evidence,
and next action). Contact display names may appear only in this local,
confidential human layer; processed and agent-visible evidence remains
hash-only. The file must never contain contact email/phone, message bodies,
raw HubSpot IDs, or raw URLs. The local HTML and Markdown reports may convert
sanitized account, contact, and deal names into direct HubSpot record links
when both the numeric portal ID and record ID are available. Those links are
confidential navigation aids: they must be escaped, open in a new tab with
`noopener noreferrer`, work only for authorized HubSpot users, and must never
be copied into `report_record_evidence.csv`, `evidence.csv`, processed
artifacts, or agent-visible evidence. When a safe link cannot be constructed,
render the sanitized name as emphasized plain text instead. Commercial amounts
may be aggregated only from existing HubSpot deal `amount` values with an
explicit currency; if currency is unavailable, withhold the amount. Contacts
without deals can be counted as a potential recoverable pipeline population,
but must never receive a monetary value.

`operator_appendix.md` contains every validated finding plus exact target,
current state, desired state, implementation steps, owner, approval gate,
expected result, evidence basis, measurable success condition, deterministic
measurement detail, and the supporting technical CRM profile.
When full-diagnostic automation coverage is available, it also contains
workflow coverage, dependency, performance, score-output activation, and
limitations. Without `automation`, the report must label this layer
incomplete and must not claim a complete Automation & Scoring Integrity Audit.
automation_evidence.csv is the sanitized configuration evidence file; it must
never contain raw workflow payloads, action bodies, URLs, or record lists.

Automation root-cause assessments are subordinate to lifecycle findings. They
may explain a finding's configuration context, but cannot create a new scored
finding, change the deterministic lifecycle score, infer a deal amount, or
authorize a HubSpot write.

The human report may name a workflow only when the sanitized workflow
inventory contains that exact workflow. It must state whether the workflow is
enabled, which visible action or field write is relevant, whether the record's
signal appears applicable, and whether record-level execution is unavailable.
If no matching control is visible, say so without inventing a workflow name or
claiming that a workflow failed.

Every named HubSpot asset in the human report must be visibly typed and
emphasized so it cannot be mistaken for narrative prose: for example,
`Workflow: Assign inbound owner (WF-001)`, `Pipeline: Inbound New Business`,
`HubSpot form: Demo request`, and `HubSpot property: Contact owner`. Workflow
aliases such as `WF-001` are sanitized report aliases, not raw HubSpot IDs.

Intent/activity evidence is subordinate to the same deterministic leakage
engine. The normalized store enriches journey classification and routes three
commercial lanes: missing-deal/pre-deal recovery (contacts only, no amount
without a deal), active-deal leakage/escalation (existing open deals and actual
amounts), and closed-lost recovery (a separate review population whose
historical amount is context only). Calls, 1:1 email activities, forms,
page/visit events, sequence-email events, and communications are record-linked
only when HubSpot associations and timestamps support that claim. The current
adapter does not retrieve the separate Marketing Email Event Analytics API;
aggregate campaign/social/ad metrics are channel context, not person-level
intent. Permission-unavailable sources are reported as unavailable, never as
zero.

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
