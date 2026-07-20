from __future__ import annotations

from core.safety import csv_safe
from core.lifecycle_record_evidence import write_report_record_evidence


def test_csv_safe_neutralizes_spreadsheet_formula_leaders():
    for value in ("=HYPERLINK(\"https://attacker.invalid\")", "+1", "-1", "@cmd"):
        assert csv_safe(value).startswith("'")


def test_csv_safe_preserves_normal_hubspot_labels():
    assert csv_safe("Smartify Marketing") == "Smartify Marketing"
    assert csv_safe(0) == "0"


def test_record_evidence_export_neutralizes_untrusted_hubspot_name(tmp_path):
    write_report_record_evidence(
        tmp_path,
        [{"account_name": '=HYPERLINK("https://attacker.invalid","Open")'}],
    )
    text = (tmp_path / "report_record_evidence.csv").read_text(encoding="utf-8")
    assert "'=HYPERLINK" in text
