from __future__ import annotations

import csv

from core.lifecycle_validators import validate_outlier_registry
from core.outliers import classify_outliers
from lifecycle_test_support import build_lifecycle_run


def test_outbound_without_mql_is_a_valid_exception(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "outbound_sales_led_sample")
    rows = classify_outliers(run_dir)
    no_mql = [row for row in rows if row.outlier_type == "no_prior_mql"]
    assert len(no_mql) == 4
    assert all(row.classification == "valid_exception" for row in no_mql)
    assert not any(row.classification == "process_breakdown" for row in no_mql)


def test_missing_associations_are_missing_data_not_automatic_process_failures(
    tmp_path,
):
    run_dir, _ = build_lifecycle_run(tmp_path, "broken_association_sample")
    rows = classify_outliers(run_dir)
    missing = [row for row in rows if row.outlier_type.startswith("missing_")]
    assert len(missing) == 4
    assert all(row.classification == "missing_data" for row in missing)


def test_outlier_registry_tampering_is_detected(tmp_path):
    run_dir, _ = build_lifecycle_run(tmp_path, "outbound_sales_led_sample")
    path = run_dir / "outlier_registry.csv"
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
        fieldnames = list(rows[0])
    rows[0]["classification"] = "process_breakdown"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    assert validate_outlier_registry(run_dir) == [
        "outlier_registry.csv does not match deterministic recomputation"
    ]
