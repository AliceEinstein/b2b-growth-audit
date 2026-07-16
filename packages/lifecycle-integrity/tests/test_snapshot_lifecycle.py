"""Snapshot completion gates and local raw-data retention."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from core.retention import prune_raw_snapshots
from core.validators import validate_snapshot_completed


def _write_manifest(run_dir, *, status: str, created_at: str) -> None:
    (run_dir / "raw").mkdir(parents=True)
    (run_dir / "raw" / "contacts.jsonl").write_text("{}\n", encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "created_at": created_at,
                "status": status,
                "days": None,
                "full_history": True,
            }
        ),
        encoding="utf-8",
    )


def test_downstream_gate_rejects_incomplete_snapshot(tmp_path):
    run_dir = tmp_path / "run_incomplete"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(
        json.dumps({"status": "in_progress"}), encoding="utf-8"
    )
    problems = validate_snapshot_completed(run_dir)
    assert problems and "in_progress" in problems[0]


def test_retention_removes_expired_raw_but_keeps_current_and_resumable(tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    current = tmp_path / "run_current"
    expired = tmp_path / "run_expired"
    resumable = tmp_path / "run_resumable"
    _write_manifest(current, status="completed", created_at=old)
    _write_manifest(expired, status="completed", created_at=old)
    _write_manifest(resumable, status="in_progress", created_at=old)

    removed = prune_raw_snapshots(
        tmp_path, retention_days=365, keep_run_dir=current
    )

    assert removed == [expired]
    assert (current / "raw").exists()
    assert not (expired / "raw").exists()
    assert (resumable / "raw").exists()


def test_retention_dry_run_reports_candidates_without_deleting(tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    current = tmp_path / "run_current"
    expired = tmp_path / "run_expired"
    _write_manifest(current, status="completed", created_at=old)
    _write_manifest(expired, status="completed", created_at=old)

    candidates = prune_raw_snapshots(
        tmp_path,
        retention_days=365,
        keep_run_dir=current,
        dry_run=True,
    )

    assert candidates == [expired]
    assert (expired / "raw").exists()
