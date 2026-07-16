"""Snapshot-mode defaults and CLI validation."""
from __future__ import annotations

import sys

from scripts.run_crm_trust_audit import parse_args


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
