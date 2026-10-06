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


# -- revision round ------------------------------------------------------------------

from pydantic import ValidationError

from core.revisions import (
    REREVIEWS_DIR,
    REVIEWS_DIR,
    REVISIONS_DIR,
    final_review_status,
    load_revisions,
    revise_requests,
    validate_rereview,
    validate_revision,
)
from core.schemas import ReviewEntry
from core.validators import load_all_findings


def write_round0(run: Path, verdicts: dict, finding_id: str = BASE_FINDING["id"]) -> None:
    directory = run / REVIEWS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    for reviewer, verdict in verdicts.items():
        (directory / f"{reviewer}.json").write_text(
            json.dumps(entries_for(finding_id, {reviewer: verdict})), encoding="utf-8"
        )


def write_revision(run: Path, findings: list, module: str = "attribution_trust") -> None:
    directory = run / REVISIONS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{module}.json").write_text(
        json.dumps({"module": module, "findings": findings}), encoding="utf-8"
    )


def write_rereview(run: Path, reviewer: str, entries: list) -> None:
    directory = run / REREVIEWS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{reviewer}.json").write_text(json.dumps(entries), encoding="utf-8")


def revised(**changes) -> dict:
    finding = {k: v for k, v in BASE_FINDING.items() if k != "review_status"}
    finding.update({"revision_note": "Lowered severity: 3 contacts is a narrow sample."})
    finding.update(changes)
    return finding


@pytest.fixture
def sent_back_run(reviewed_run: Path) -> Path:
    verdicts = {r: "approve" for r in REVIEWERS}
    verdicts["logic_reviewer"] = "revise"
    write_round0(reviewed_run, verdicts)
    return reviewed_run


def test_rereview_cannot_ask_for_a_second_revision():
    with pytest.raises(ValidationError, match="1 revision round"):
        ReviewEntry(
            finding_id="f", reviewer="logic_reviewer", verdict="revise",
            reason="still wrong", revision_round=1,
        )
    with pytest.raises(ValidationError):
        ReviewEntry(
            finding_id="f", reviewer="logic_reviewer", verdict="approve",
            reason="ok", revision_round=2,
        )


def test_final_status_reject_wins_and_revised_needs_round0_revise():
    round0 = {r: "approve" for r in REVIEWERS}
    assert final_review_status(round0) == "approved"
    round0["logic_reviewer"] = "revise"
    assert final_review_status(round0) == "revised"
    assert final_review_status(round0, {"logic_reviewer": "approve"}) == "revised"
    assert final_review_status(round0, {"logic_reviewer": "reject"}) == "rejected"


def test_rejected_finding_is_not_sent_back(reviewed_run):
    verdicts = {r: "approve" for r in REVIEWERS}
    verdicts["logic_reviewer"] = "revise"
    verdicts["data_fidelity_reviewer"] = "reject"
    write_round0(reviewed_run, verdicts)
    assert revise_requests(reviewed_run) == {}


def test_revision_may_change_judgment_but_not_numbers(sent_back_run):
    write_revision(sent_back_run, [revised(severity="medium")])
    assert validate_revision(sent_back_run, "attribution_trust") == []

    write_revision(sent_back_run, [revised(affected_records=2)])
    problems = validate_revision(sent_back_run, "attribution_trust")
    assert any("locked field 'affected_records'" in p for p in problems)


def test_revision_needs_a_note_and_covers_exactly_the_requests(sent_back_run):
    write_revision(sent_back_run, [revised(revision_note="")])
    assert any("revision_note" in p for p in validate_revision(sent_back_run, "attribution_trust"))

    write_revision(sent_back_run, [])
    assert any("missing revision" in p for p in validate_revision(sent_back_run, "attribution_trust"))

    write_revision(sent_back_run, [revised(), revised(id="other_finding")])
    assert any("not sent back" in p for p in validate_revision(sent_back_run, "attribution_trust"))


def test_rereview_covers_only_the_reviewers_own_requests(sent_back_run):
    ok = {"finding_id": BASE_FINDING["id"], "reviewer": "logic_reviewer",
          "verdict": "approve", "reason": "Severity now fits.", "revision_round": 1}
    write_rereview(sent_back_run, "logic_reviewer", [ok])
    assert validate_rereview(sent_back_run, "logic_reviewer") == []

    write_rereview(sent_back_run, "logic_reviewer", [])
    assert any("missing re-review" in p for p in validate_rereview(sent_back_run, "logic_reviewer"))

    write_rereview(sent_back_run, "data_fidelity_reviewer", [dict(ok, reviewer="data_fidelity_reviewer")])
    assert any("wasn't sent back" in p for p in validate_rereview(sent_back_run, "data_fidelity_reviewer"))


def test_reports_use_the_revised_finding(sent_back_run):
    write_revision(sent_back_run, [revised(severity="medium", business_impact="Narrow gap.")])
    findings, problems = load_all_findings(sent_back_run)
    assert problems == []
    finding = findings[0]
    assert (finding.severity, finding.business_impact) == ("medium", "Narrow gap.")
    assert finding.affected_records == BASE_FINDING["affected_records"]


def test_stale_revision_is_ignored_once_nothing_is_sent_back(reviewed_run):
    write_round0(reviewed_run, {r: "approve" for r in REVIEWERS})
    write_revision(reviewed_run, [revised(severity="low")])
    assert load_revisions(reviewed_run) == {}
    findings, _ = load_all_findings(reviewed_run)
    assert findings[0].severity == BASE_FINDING["severity"]


def _two_round_log(verdict_round1: str) -> list:
    verdicts = {r: "approve" for r in REVIEWERS}
    verdicts["logic_reviewer"] = "revise"
    entries = entries_for(BASE_FINDING["id"], verdicts)
    if verdict_round1:
        entries.append({"finding_id": BASE_FINDING["id"], "reviewer": "logic_reviewer",
                        "verdict": verdict_round1, "reason": "rechecked", "revision_round": 1})
    return entries


def _set_status(run: Path, status: str) -> None:
    write_findings(run, [dict(BASE_FINDING, review_status=status)])


def test_harness_run_requires_the_rereview(sent_back_run):
    (sent_back_run / "harness" / "run_state.json").write_text("{}", encoding="utf-8")
    _set_status(sent_back_run, "revised")
    write_log(sent_back_run, _two_round_log(""))
    problems = validate_reviews(sent_back_run)
    assert any("no revision was recorded" in p for p in problems)
    assert any("not yet re-reviewed by logic_reviewer" in p for p in problems)
    assert validate_reviews(sent_back_run, require_rereview=False) == []

    write_revision(sent_back_run, [revised()])
    write_log(sent_back_run, _two_round_log("approve"))
    assert validate_reviews(sent_back_run) == []

    write_log(sent_back_run, _two_round_log("reject"))
    assert any("aggregate to 'rejected'" in p for p in validate_reviews(sent_back_run))
    _set_status(sent_back_run, "rejected")
    assert validate_reviews(sent_back_run) == []


def test_legacy_manual_run_keeps_in_place_revisions(reviewed_run):
    _set_status(reviewed_run, "revised")
    write_log(reviewed_run, _two_round_log(""))
    assert validate_reviews(reviewed_run) == []


def test_rereview_from_a_reviewer_who_did_not_send_it_back(reviewed_run):
    entries = entries_for(BASE_FINDING["id"], {r: "approve" for r in REVIEWERS})
    entries.append({"finding_id": BASE_FINDING["id"], "reviewer": "logic_reviewer",
                    "verdict": "reject", "reason": "late objection", "revision_round": 1})
    write_log(reviewed_run, entries)
    problems = validate_reviews(reviewed_run, require_rereview=False)
    assert any("did not send it back" in p for p in problems)
