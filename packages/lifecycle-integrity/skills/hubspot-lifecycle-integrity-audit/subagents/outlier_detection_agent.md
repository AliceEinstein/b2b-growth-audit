# Outlier Detection Agent

## Artifact contract

Inputs: the declared outlier registry, measurements, evidence, registry,
context, and hypotheses. Output:
agent_workspace/candidates/outlier_detection_agent.json.

Return `candidate_findings` (required — promoted outliers as full
LifecycleFinding objects, or an explicit empty array), plus
classification_review, observations, assumptions, and coverage_limitations.
Promotions live ONLY in `candidate_findings`; any other key is ignored by the
consolidator. Preserve the code-owned outlier classifications unless cited
evidence justifies a human-review challenge. Promotion requires material
deterministic evidence.

Classify outliers as `valid_exception`, `missing_data`, `process_breakdown`,
`journey_misclassification`, or `needs_human_review`. Outlier status is not a
finding by itself. Only material, high-confidence process breakdowns or missing
data become priority findings; the rest become observations or review items.
