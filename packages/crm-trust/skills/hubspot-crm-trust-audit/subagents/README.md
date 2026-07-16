# Subagent Roles

Subagents are markdown instruction files executed by the host coding agent
(Claude Code, Codex). Communication happens through artifacts on disk, never
a shared conversation. Each role: run a script → read its artifacts → write a
judgment artifact → the next script validates the schema.

| Role | Type | Arrives in |
|---|---|---|
| orchestrator | LLM | Phase 2 ✅ |
| schema_discovery_agent | LLM | Phase 3 ✅ |
| business_context_agent | LLM | Phase 3 ✅ |
| audit_model_selector | LLM | Phase 3 ✅ |
| attribution_trust_agent | LLM | Phase 4 ✅ |
| lifecycle_funnel_agent | LLM | Phase 4 ✅ |
| association_architecture_agent | LLM | Phase 4 ✅ |
| pipeline_hygiene_agent | LLM | Phase 4 ✅ |
| property_governance_agent | LLM | Phase 4 ✅ |
| data_fidelity_reviewer | LLM | Phase 5 ✅ |
| logic_reviewer | LLM | Phase 5 ✅ |
| privacy_safety_reviewer | LLM (+ code leak net) | Phase 5 ✅ |
| audit_scope_reviewer | LLM | Phase 5 ✅ |
| recommendation_agent | LLM | Phase 6 ✅ |
| final_report_agent | LLM | Phase 6 ✅ |
