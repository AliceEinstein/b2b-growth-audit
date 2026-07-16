"""Retention helpers for local raw CRM snapshots."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _snapshot_time(run_dir: Path) -> datetime:
    """Return the manifest creation time, with filesystem mtime as fallback."""
    manifest = run_dir / "manifest.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        value = data.get("created_at")
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return datetime.fromtimestamp(run_dir.stat().st_mtime, tz=timezone.utc)


def prune_raw_snapshots(
    output_root: Path,
    *,
    retention_days: int,
    keep_run_dir: Path,
    dry_run: bool = False,
) -> list[Path]:
    """Delete (or preview) expired ``raw/`` trees while preserving resumable runs.

    The processed/audit artifacts remain available for diff and reporting. A
    run is eligible only when it is not the current run, has a manifest, is
    not in progress, and is older than the configured raw-data retention. With
    ``dry_run=True`` it returns the same candidates without deleting them.
    """
    if retention_days <= 0:
        raise ValueError("retention_days must be greater than zero")

    root = Path(output_root)
    keep = Path(keep_run_dir).resolve()
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    removed: list[Path] = []
    for run_dir in sorted(root.glob("run_*")):
        if not run_dir.is_dir() or run_dir.resolve() == keep:
            continue
        raw = run_dir / "raw"
        manifest = run_dir / "manifest.json"
        if not raw.is_dir() or not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("status") == "in_progress":
            continue
        if _snapshot_time(run_dir) >= cutoff:
            continue
        if not dry_run:
            shutil.rmtree(raw)
        removed.append(run_dir)
    return removed
