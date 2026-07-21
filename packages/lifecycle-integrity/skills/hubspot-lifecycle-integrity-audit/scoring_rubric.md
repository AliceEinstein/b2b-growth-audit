# Scoring rubric

## Five journey links

The Lifecycle Integrity Score measures whether five observable commercial
handoffs are protected. The weights total 100 points.

| Journey link | Points |
|---|---:|
| Intent → accountable owner | 20 |
| Owner → deal or documented valid skip | 20 |
| Deal, account, contact, and source continuity | 20 |
| Open deal → next sales action | 25 |
| Closed-lost/customer → recovery or renewal | 15 |

Journey Mapping Confidence is reported separately. It identifies how strongly
the available HubSpot evidence supports the inferred selling motion and is
never folded into Lifecycle Integrity Score arithmetic.

## Scored control coverage and score availability

Each control is assessable only when its required source and denominator are
available. An unavailable control is labelled `not_assessable`; it is never
treated as healthy or broken. A journey link can therefore be partially
assessed when some of its independent controls are available and others are
not.

A denominator must be a positive eligible population observed in the audit
window. A missing denominator is unavailable evidence. A zero denominator
means no eligible population was observed; it is reported separately and does
not earn healthy points. Neither state is converted into a failure.

- Below 70% weighted scored control coverage, do not issue a numeric Lifecycle
  Integrity Score. Report `insufficient_evidence`, the available control and link results,
  and the missing coverage.
- At 70–94% coverage, normalize the retained points across the assessable
  controls to 100 and label the result a partial assessment.
- At 95–100% coverage, report the normalized score and the exact coverage.

For a reportable score:

```text
normalized score = retained assessed points / assessed weight × 100
normalized deductions = 100 − normalized score
```

The report must state the assessed control weight and scored control coverage next to
the formula. It must separately label diagnostic data coverage for automation,
campaign/channel context, and record-linked activity. A 100% scored control
coverage value means all nine controls across the five links were assessable; it does not mean
every optional diagnostic source was available. A missing scope, API response,
source, or denominator cannot create a lifecycle-risk verdict by itself.

## Finding treatment

- Approved or revised deterministic breaks use their full affected share.
- An unresolved deterministic candidate with an affected population uses half
  of its affected share until reviewer adjudication, and the verdict is
  provisional.
- Rejected findings and observations do not reduce the score.
- Bind reviewer status through an exact `evidence.csv#finding_id=...`
  measurement citation, never by matching a finding name or substring. One
  finding may confirm at most one `primary` population; split combined scored
  populations before adjudication.
- Closed-lost renewed-intent opportunities remain visible outside the score
  unless a separate scored control break supports a deduction.
- Require each scored or score-adjacent measurement to declare `score_link`,
  `score_control`, `score_population_key`, and `score_role` when deterministic
  code creates it. Never infer scoring ownership from a measurement ID, note,
  dimension, or keyword.
- `primary` is the only role that can make a control assessable or change its
  score. Each canonical population key can have only one primary measurement.
- `breakdown` explains a primary population by journey or cohort and never
  changes the score or unresolved-population count.
- `opportunity_only` remains visible outside the score and cannot make a link
  assessable, earn healthy points, or create a deduction.
- `supporting` identifies a deterministic leakage signal that overlaps a
  primary population. It remains actionable evidence but cannot be scored a
  second time and must explain why it stays outside the arithmetic.
- When mutually exclusive motion populations belong to one control, calculate
  `sum(affected records × review multiplier) / sum(eligible population)`.
  This makes each motion contribute in proportion to its observed population;
  a small 100%-affected motion cannot represent the entire control.
- Assess independent controls separately. Missing Deal–Contact evidence, for
  example, removes only the Deal–Contact control weight; readable Deal–Company
  evidence cannot make the missing control healthy or assessable.

Current ownership rules include:

| Control | Weight | Population treatment |
|---|---:|---|
| Intent → accountable owner | 20 | Mutually exclusive motion populations, denominator-weighted |
| Owner → deal or valid skip | 20 | Mutually exclusive motion populations, denominator-weighted; activity-derived overlap is `supporting` |
| Contact lifecycle state | 5 | Independent continuity control |
| Deal–Company association | 5 | Independent continuity control; journey slices are `breakdown` |
| Deal–Contact association | 5 | Independent continuity control |
| Inbound source continuity | 5 | Independent continuity control |
| Open-deal owner | 10 | Mutually exclusive motion populations, denominator-weighted |
| Active-deal seller follow-up | 15 | Independent progression control |
| Expansion/customer-state continuity | 15 | Independent post-close control |

Closed-lost renewed intent without a successor path remains
`opportunity_only`: it is commercially actionable but is not scored as proof
that the original closed-lost decision or lifecycle control was wrong.

Commercial deal amounts rank the action queue but never change score
arithmetic. Contacts or accounts without deals never receive an estimated
amount.

## Ownership

Deterministic code calculates control scores, rolls them up into the five link
summaries, and calculates coverage, normalization, and the overall result. The
LLM may interpret, explain, review, or recommend; it must not alter score
arithmetic.

If a journey is medium confidence, cap or downgrade high-severity conclusions
unless the finding has independent evidence. Low-confidence journeys can only
produce observations or human-confirmation items.
