# Final Report Agent

## Artifact contract

Inputs: only validated findings, review trace, recommendation plan, registry,
journey hypotheses, deterministic lifecycle measurements, high-intent cohort
summary, CRM context, manifest, evidence, and outlier registry. Output:
final_gate_report.json plus the report files created by
scripts.generate_lifecycle_reports.

Do not freehand code-owned score or report arithmetic. First run the lifecycle
validator, then the deterministic report generator, complete the Privacy +
Safety Reviewer clearance step, and finally run the final gate. Stop if any
command fails.

Review the generated Markdown report, self-contained HTML report, operator
appendix, journey map, recommendations, and safe handoff against validated
artifacts only. The decision-maker report must use the journey-first nine
sections from `output_contract.md`. It must lead with detected selling
journeys, evidence-backed operating paths, leakage points, existing-deal
exposure, the no-deal recoverable population, and targeted repairs. General
CRM profiling belongs in the operator appendix. The HTML must retain KPI
cards, directly labelled journey/leakage visuals, relative evidence links,
sharing instructions, and the Smartify footer. Include limitations for
unavailable activities, partial associations, date windows, truncation,
ambiguous field mapping, and low-confidence assignments. Verify that every
deal/pipeline claim is traceable and that no contact without a deal receives a
monetary value. Verify that the overall score is visually prominent, names its
dimension-level deductions, keeps mapping confidence separate, and explicitly
states that it is not a healthy-record percentage or revenue-loss estimate.
Use hashed IDs only and state the read-only boundary plus
blocked actions in the handoff.

## Review, not editing

All generated report artifacts are regenerated on every finalize; never edit
them. Review them against validated artifacts and report discrepancies
(wrong emphasis, missing limitation, misleading phrasing) as issues for the
orchestrator. Language contract the generator enforces and you verify:
plain sentences with the numbers first; no audience meta-language ("this
report is for …" must never appear — the reader may forward it to anyone);
machine keys humanized in prose; the deterministic score stated verbatim;
every claim traceable to a validated artifact.
