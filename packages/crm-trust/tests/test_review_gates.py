"""Review gate validation: four reviewers, deterministic aggregation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.rules import MODULES
from core.validators import REVIEWERS, aggregate_verdicts, validate_reviews

from test_findings_validation import BASE_FINDING, write_findings


@pytest.fixture
def reviewed_run(measured_run: Path) -> Path:
    """One approved finding in attribution, empty findings elsewhere."""
    write_findings(measured_run, [dict(BASE_FINDING, review_status="approved")])
    for module in MODULES:
        if module != "attribution_trust":
            write_findings(measured_run, [], module=module)
    return measured_run


def write_log(run: Path, entries: list) -> None:
    (run / "review_log.json").write_text(json.dumps(entries), encoding="utf-8")


def entries_for(finding_id: str, verdicts: dict) -> list:
    return [
        {"finding_id": finding_id, "reviewer": r, "verdict": v, "reason": "checked"}
        for r, v in verdicts.items()
    ]


def test_aggregation_rule():
    assert aggregate_verdicts(["approve"] * 4) == "approved"
    assert aggregate_verdicts(["approve", "revise", "approve", "approve"]) == "revised"
    assert aggregate_verdicts(["approve", "revise", "reject", "approve"]) == "rejected"


def test_complete_reviews_pass(reviewed_run):
    write_log(
        reviewed_run,
        entries_for(BASE_FINDING["id"], {r: "approve" for r in REVIEWERS}),
    )
    assert validate_reviews(reviewed_run) == []


def test_missing_reviewer_is_reported(reviewed_run):
    write_log(
        reviewed_run,
        entries_for(BASE_FINDING["id"], {r: "approve" for r in REVIEWERS[:3]}),
    )
    problems = validate_reviews(reviewed_run)
    assert any("missing review from audit_scope_reviewer" in p for p in problems)


def test_status_must_match_aggregate(reviewed_run):
    verdicts = {r: "approve" for r in REVIEWERS}
    verdicts["logic_reviewer"] = "reject"
    write_log(reviewed_run, entries_for(BASE_FINDING["id"], verdicts))
    problems = validate_reviews(reviewed_run)
    # finding says approved, verdicts aggregate to rejected
    assert any("aggregate to 'rejected'" in p for p in problems)


def test_unknown_finding_in_log_is_reported(reviewed_run):
    entries = entries_for(BASE_FINDING["id"], {r: "approve" for r in REVIEWERS})
    entries += entries_for("ghost_finding", {"logic_reviewer": "approve"})
    write_log(reviewed_run, entries)
    problems = validate_reviews(reviewed_run)
    assert any("unknown finding 'ghost_finding'" in p for p in problems)


def test_duplicate_verdict_is_reported(reviewed_run):
    entries = entries_for(BASE_FINDING["id"], {r: "approve" for r in REVIEWERS})
    entries += entries_for(BASE_FINDING["id"], {"logic_reviewer": "reject"})
    write_log(reviewed_run, entries)
    problems = validate_reviews(reviewed_run)
    assert any("duplicate verdict" in p for p in problems)


def test_missing_log_is_reported(reviewed_run):
    problems = validate_reviews(reviewed_run)
    assert problems and "review_log.json not found" in problems[0]
