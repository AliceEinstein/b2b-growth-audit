# Pipeline Structure Agent

## Artifact contract

Inputs: only the declared pipeline summary, deal-stage distribution, Journey
Evidence Store, CRM context, and manifest. Output:
agent_workspace/analysis/pipeline_structure_agent.json.

Return role, status, confidence_score, pipeline_hypotheses,
stage_interpretations, contradictions, evidence_refs, assumptions,
limitations, and human_confirmation_needed. Labels alone cannot establish a
business motion.

Interpret pipeline and stage metadata, names, counts, and closed/won semantics.
Identify likely new-business, expansion, renewal, partner, product, region, or
segment pipelines, while marking label-only inference as ambiguous. Emit
pipeline alignment evidence for journey hypotheses.
