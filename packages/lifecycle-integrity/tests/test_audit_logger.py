"""Audit log tests: structure and the no-token guarantee."""
from __future__ import annotations

import json

import pytest

from core.audit_logger import AuditLog

FAKE_TOKEN = "pat-" + "na1-a3f90b12-4c5d-6e7f-8a9b-0c1d2e3f4a5b"


def test_writes_events_and_warnings(tmp_path):
    log = AuditLog(run_config={"days": 90})
    log.event("records_fetched", object_type="contacts", count=42)
    log.warn("contacts: hit search cap")
    out = tmp_path / "audit_log.json"
    log.write(out)

    doc = json.loads(out.read_text())
    assert doc["run_config"] == {"days": 90}
    assert doc["warnings"] == ["contacts: hit search cap"]
    assert any(e["event"] == "records_fetched" for e in doc["events"])
    assert doc["started_at"] <= doc["finished_at"]


def test_refuses_to_write_a_token(tmp_path):
    log = AuditLog()
    log.event("oops", detail=f"token was {FAKE_TOKEN}")
    with pytest.raises(RuntimeError, match="token"):
        log.write(tmp_path / "audit_log.json")
    assert not (tmp_path / "audit_log.json").exists()
