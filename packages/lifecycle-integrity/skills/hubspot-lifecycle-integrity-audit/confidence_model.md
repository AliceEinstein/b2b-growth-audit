# Journey confidence model

## Formula

Compute, do not invent:

```text
field_signal                 0–20
object_path_evidence         0–20
volume_materiality           0–15
temporal_consistency         0–10
pipeline_alignment           0–15
association_coherence        0–10
reviewer_adjustment          0–10
minus contradiction_penalty  0–30
```

The result is clamped to 0–100. The deterministic score must retain each
component and every reviewer adjustment as evidence.

## Labels

- 85–100: `very_high`
- 70–84: `high`
- 50–69: `medium`
- 30–49: `low`
- 0–29: `insufficient`

## Downstream rules

- 85–100 and 70–84: full pattern audit allowed.
- 50–69: audit allowed, but high-severity conclusions require stronger
  evidence and reviewer support.
- 30–49: observation only.
- 0–29: do not audit as a detected pattern.

Low-confidence record assignments are routed to outlier review and cannot
support strong aggregate conclusions. Journey confidence is separate from the
integrity score; never use one as a substitute for the other.
