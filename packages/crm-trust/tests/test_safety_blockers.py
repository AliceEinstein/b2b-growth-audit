"""Leak-net and blocked-phrase backstop tests.

Reminder of semantics: PII/token format hits are HARD failures; blocked
phrases are SOFT flags cleared or rejected by the LLM safety reviewer.
"""
from __future__ import annotations

from core.safety import (
    SafetyHit,
    has_hard_leaks,
    scan_final_outputs,
    scan_text,
)

FAKE_TOKEN = "pat-" + "na1-a3f90b12-4c5d-6e7f-8a9b-0c1d2e3f4a5b"


def kinds(hits: list[SafetyHit]) -> set[str]:
    return {h.kind for h in hits}


# -- hard leaks ---------------------------------------------------------------


def test_email_is_a_hard_leak():
    hits = scan_text("contact jane.doe@example.com for details")
    assert "email" in kinds(hits)
    assert has_hard_leaks(hits)


def test_hubspot_token_is_a_hard_leak():
    hits = scan_text(f"Authorization: Bearer {FAKE_TOKEN}")
    assert "hubspot_token" in kinds(hits)
    assert has_hard_leaks(hits)


def test_phone_number_is_a_hard_leak():
    hits = scan_text("call +1 (415) 555-0113 today")
    assert "phone" in kinds(hits)
    assert has_hard_leaks(hits)


def test_leaked_value_is_never_reproduced_in_the_hit():
    hits = scan_text(f"token {FAKE_TOKEN} leaked")
    for hit in hits:
        assert FAKE_TOKEN not in hit.excerpt


# -- non-leaks the net must NOT flag -------------------------------------------


def test_timestamps_counts_and_percentages_are_not_phones():
    clean = (
        "Snapshot 2026-07-12 16:31:00 contains 1,000,000 records; "
        "31.2% of 10000 contacts lack hs_analytics_source. "
        "Score: 68/100. Run id run_20260712_163100."
    )
    hits = scan_text(clean)
    assert not has_hard_leaks(hits), [h.kind for h in hits if h.hard]


def test_hashed_record_ids_are_not_flagged():
    hits = scan_text("record_id_hash=9f86d081884c7d659a2feaa0c55ad015a3bf4f1b")
    assert not has_hard_leaks(hits)


# -- blocked phrases: soft flags ------------------------------------------------


def test_blocked_phrases_are_flagged_but_not_hard():
    text = (
        "Recommendation: merge companies automatically and reset lifecycle stage."
    )
    hits = scan_text(text)
    phrase_hits = [h for h in hits if h.kind == "blocked_phrase"]
    assert {h.excerpt for h in phrase_hits} == {
        "merge companies automatically",
        "reset lifecycle stage",
    }
    assert all(not h.hard for h in phrase_hits)


def test_blocked_phrase_inside_blocked_actions_section_still_flagged_softly():
    # Legitimate context — the LLM reviewer clears it; the net only flags.
    text = "## Blocked Actions\n\n- delete properties (do not execute)"
    hits = scan_text(text)
    assert any(h.kind == "blocked_phrase" for h in hits)
    assert not has_hard_leaks(hits)


# -- output directory scan -------------------------------------------------------


def test_scan_final_outputs_skips_raw_but_scans_reports(tmp_path):
    run = tmp_path / "run_x"
    (run / "raw").mkdir(parents=True)
    (run / "raw" / "contacts.jsonl").write_text(
        '{"email": "real.person@example.com"}\n', encoding="utf-8"
    )
    (run / "crm_trust_report.md").write_text(
        "All good. Aggregates only.", encoding="utf-8"
    )
    assert not has_hard_leaks(scan_final_outputs(run))

    (run / "crm_trust_report.md").write_text(
        "Contact leaked.person@example.com about this.", encoding="utf-8"
    )
    assert has_hard_leaks(scan_final_outputs(run))
