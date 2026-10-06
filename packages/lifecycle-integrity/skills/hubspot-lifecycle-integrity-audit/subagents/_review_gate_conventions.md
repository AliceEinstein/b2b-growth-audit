# Review-gate conventions

Each reviewer writes its declared output file as
`{"role": "<reviewer_name>", "reviews": [ReviewDecision, ...]}`. The `reviews`
key is required (write an explicit empty array when there is nothing to
review), and a file may contain only decisions whose `reviewer` equals the
file's own role — consolidation and the workspace gate reject anything else.

Review each candidate against the declared artifacts and record one of:
`approved`, `needs_revision`, `downgrade_to_observation`,
`requires_human_confirmation`, or `rejected`.

`needs_revision` may be returned once. The orchestrator then adjudicates using
the rules in `output_contract.md`; it must not improvise a new status. Review
reasons cite evidence IDs and distinguish missing data from a valid exception.
No reviewer may change deterministic counts, percentages, denominators, or
scores.

Every `rejected` decision states `rejection_basis`:

- `valid_exception`: the measurement is right, but the affected records are
  acceptable business behavior. The control is scored as healthy.
- `invalid_measurement`: the population itself is wrong, for example a
  journey misassignment or a field that doesn't mean what the measurement
  assumes. Cite the contradicting evidence in `evidence_refs`. When at least 2
  reviewers reject on this basis, the population leaves the score: the
  control is shown as not assessed instead of healthy, and coverage falls.

Never use `invalid_measurement` to avoid an unwelcome result; it lowers
coverage and is listed in the report with its reason.
