"""Snapshot-mode defaults and CLI validation."""
from __future__ import annotations

import sys

from scripts.run_crm_trust_audit import (
    LARGE_OBJECT_WARNING,
    parse_args,
    record_volume_warning,
)


def test_snapshot_defaults_to_full_history(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_crm_trust_audit"])
    args = parse_args()
    assert args.days is None
    assert args.full_history is False
    assert args.resume is None
    assert args.raw_retention_days == 365
    assert args.dry_run is False


def test_recent_window_remains_explicit(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_crm_trust_audit", "--days", "90"])
    args = parse_args()
    assert args.days == 90


def test_large_snapshot_gets_a_memory_warning():
    assert record_volume_warning("contacts", LARGE_OBJECT_WARNING - 1) is None
    warning = record_volume_warning("contacts", LARGE_OBJECT_WARNING)
    assert warning and "shorter --days window" in warning
