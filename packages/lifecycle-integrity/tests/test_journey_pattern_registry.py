from __future__ import annotations

import json

from core.lifecycle_validators import load_registry
from lifecycle_test_support import build_lifecycle_run


def _scores(run_dir):
    registry = json.loads(
        (run_dir / "journey_pattern_registry.json").read_text(encoding="utf-8")
    )
    return registry, {
        row["journey_type"]: row["confidence_score"] for row in registry["patterns"]
    }


def test_clean_inbound_does_not_invent_other_motions(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "clean_inbound_crm_sample")
    registry, scores = _scores(run_dir)
    assert registry["primary_model"] == "single_motion"
    assert scores["inbound_new_business"] >= 50
    assert all(
        scores[journey] < 30
        for journey in (
            "outbound_sales_led",
            "abm_account_based",
            "partner_led",
            "expansion_renewal",
        )
    )


def test_mixed_motion_is_kept_separate(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "mixed_motion_scaleup_sample")
    registry, scores = _scores(run_dir)
    assert registry["primary_model"] == "multi_motion"
    assert scores["inbound_new_business"] >= 50
    assert scores["outbound_sales_led"] >= 50
    assert scores["expansion_renewal"] >= 50


def test_missing_mql_alone_does_not_prove_outbound(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "clean_inbound_crm_sample")
    _, scores = _scores(run_dir)
    assert scores["outbound_sales_led"] == 0


def test_registry_cannot_be_tampered_by_balancing_adjustment_and_score(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "clean_inbound_crm_sample")
    path = run_dir / "journey_pattern_registry.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    inbound = next(
        row for row in doc["patterns"] if row["journey_type"] == "inbound_new_business"
    )
    inbound["evidence_components"]["reviewer_adjustment"] = 10
    inbound["confidence_score"] += 10
    inbound["confidence_label"] = "medium"
    path.write_text(json.dumps(doc), encoding="utf-8")
    _, problems = load_registry(run_dir)
    assert any("does not match deterministic" in row for row in problems)
