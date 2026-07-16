# Scoring Rubric

The CRM Trust Score is out of 100:

| Category | Points |
|---|---|
| Attribution Trust | 25 |
| Lifecycle + Funnel Trust | 20 |
| Association + Account Trust | 20 |
| Pipeline Hygiene | 20 |
| Property Governance | 15 |

## Who does what

- **LLM (audit agents + review gates)** assigns each validated finding a
  severity — `critical / high / medium / low` — judged against the selected
  audit profile and business context. No hardcoded thresholds.
- **Code (Phase 4, `core/scoring.py`)** converts validated findings into
  deductions and computes the score. The LLM may explain the score but must
  not change it.

## Default deduction mapping (code)

Within each category:

| Severity | Deduction |
|---|---|
| critical | 10 |
| high | 6 |
| medium | 3 |
| low | 1 |

Deductions are capped at the category maximum. Only findings with
`review_status: approved` (or `revised`) count. Every deduction must be
explainable from `findings.json`.
