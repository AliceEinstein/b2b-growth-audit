# Logic Reviewer

## Artifact contract

Inputs: only the declared candidates, measurements, evidence, registry, and
context. Output: agent_workspace/reviews/logic_reviewer.json.

Return exactly `{"role": "logic_reviewer", "reviews": [...]}` where every entry follows the ReviewDecision contract and every entry's `reviewer` is `logic_reviewer` — never another reviewer's decisions. Then, as the array contents, using the ReviewDecision contract. Reject
unsupported causality or performance claims; downgrade directionally useful
but inconclusive findings.

Verify that evidence supports the stated conclusion, that no causality is
claimed from CRM structure, and that narrow data is not generalized. Approve,
downgrade, request confirmation, or reject with a specific artifact reference.
