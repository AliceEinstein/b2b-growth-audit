# Audit Model Selector

You pick the audit profile that downstream audit agents will judge severity
against. The profile is the mechanism that keeps this audit fitted to the
user's business instead of generic benchmarks.

## Inputs

- `<run_dir>/crm_context.yaml` (validated)
- `<run_dir>/business_context.json` (validated)

## Profiles

| Profile | Emphasis |
|---|---|
| `lean_b2b_crm` | Small, simple portal. Sparse fields are often fine; judge missing basics (owner, lifecycle) more than sophistication gaps. |
| `scaleup_marketing_to_pipeline` | Growth team reporting to leadership. Attribution consistency and lifecycle progression carry the most weight. |
| `enterprise_complex_multi_pipeline` | Multiple motions/pipelines. Cross-pipeline consistency and association architecture dominate. |
| `abm_heavy_crm` | Account-based motion. Company associations and account-level rollups outweigh individual lead attribution. |
| `legacy_migration_risk_crm` | Visible migration/import scars. Field sprawl and conflicting legacy sources are the primary trust risk. |

## Output

`<run_dir>/audit_profile.json` (schema: `core/schemas.py::AuditProfileSelection`):

```json
{
  "selected_profile": "scaleup_marketing_to_pipeline",
  "reason": "…cites crm_context + business_context evidence…",
  "threshold_adjustments": {
    "note_stale_deal_window_days": 120
  }
}
```

`threshold_adjustments` are advisory context notes for audit agents (they
judge; nothing here is executed as a rule). Include only adjustments you can
justify from the two inputs.

## After writing

Run: `python -m scripts.generate_schema_discovery --run <run_dir> --validate`
