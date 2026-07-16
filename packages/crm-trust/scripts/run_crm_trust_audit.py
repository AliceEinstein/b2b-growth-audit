"""Fetch a read-only HubSpot CRM snapshot (audit pipeline, Phases 1–2).

Usage:
    python -m scripts.run_crm_trust_audit                 # full history
    python -m scripts.run_crm_trust_audit --days 90       # recent-only view

Later phases (profiling, schema discovery, audit modules, reports) consume
the snapshot this script produces.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from connectors.hubspot import (
    fetch_associations,
    fetch_companies,
    fetch_contacts,
    fetch_deals,
    fetch_owners,
    fetch_pipelines,
    fetch_properties,
)
from connectors.hubspot.auth import TokenError, load_token
from connectors.hubspot.client import HubSpotClient, HubSpotError
from connectors.hubspot.normalize import write_json
from core.audit_logger import AuditLog
from core.config import (
    create_run_dir,
    default_output_root,
    ensure_output_root_guard,
    ensure_raw_guard,
)
from core.profiler import profile_run
from core.retention import prune_raw_snapshots
from core.schemas import RunManifest

console = Console()
_ACTIVE_RUN_DIR: Path | None = None

ASSOCIATION_PAIRS = [
    ("contacts", "companies", "associations_contact_company.jsonl"),
    ("deals", "companies", "associations_deal_company.jsonl"),
    ("deals", "contacts", "associations_deal_contact.jsonl"),
]


def positive_days(value: str) -> int:
    try:
        days = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("days must be an integer") from exc
    if days <= 0:
        raise argparse.ArgumentTypeError("days must be greater than zero")
    return days


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days",
        type=positive_days,
        default=None,
        help="Optional recent-only snapshot window; default is full history",
    )
    parser.add_argument(
        "--full-history", action="store_true", help="Fetch all records, no date filter"
    )
    parser.add_argument(
        "--resume",
        type=Path,
        default=None,
        help="Resume an in-progress or failed snapshot from its checkpoints",
    )
    parser.add_argument(
        "--raw-retention-days",
        type=positive_days,
        default=365,
        help="Delete raw snapshots older than this many days (default 365)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview raw retention deletions; the audit itself still runs",
    )
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    return parser.parse_args()


def _write_manifest(
    run_dir: Path,
    *,
    created_at: str,
    snapshot_started_at: str | None = None,
    snapshot_completed_at: str | None = None,
    resumed: bool = False,
    status: str,
    days: int | None,
    counts: dict[str, int] | None = None,
    truncated: dict[str, bool] | None = None,
    source_candidates: dict[str, list[str]] | None = None,
    warnings: list[str] | None = None,
) -> None:
    manifest = RunManifest(
        run_id=run_dir.name,
        created_at=created_at,
        snapshot_started_at=snapshot_started_at or created_at,
        snapshot_completed_at=snapshot_completed_at,
        resumed=resumed,
        status=status,
        days=days,
        full_history=days is None,
        counts=counts or {},
        truncated=truncated or {},
        source_candidates=source_candidates or {},
        warnings=warnings or [],
    )
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )


def _set_manifest_status(run_dir: Path, status: str) -> None:
    path = Path(run_dir) / "manifest.json"
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    data["status"] = status
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_resume_manifest(run_dir: Path) -> dict[str, object]:
    path = Path(run_dir) / "manifest.json"
    if not path.exists():
        raise ValueError("cannot resume: manifest.json is missing")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("cannot resume: manifest.json is invalid") from exc
    if data.get("status") == "completed":
        raise ValueError("cannot resume a completed snapshot; start a new run")
    if data.get("status") not in {"in_progress", "failed"}:
        raise ValueError(
            "cannot resume: manifest status must be 'in_progress' or 'failed'"
        )
    return data


def _run_audit() -> int:
    global _ACTIVE_RUN_DIR
    args = parse_args()
    days: int | None = None if args.full_history else args.days
    if days is None:
        console.print(
            "[yellow]⚠️ Full-history mode can be slow for large portals and "
            "may hit API limits.[/yellow]"
        )

    try:
        token = load_token()
    except TokenError as exc:
        console.print(f"[red]❌ {exc}[/red]")
        return 1

    if args.resume is not None:
        run_dir = args.resume
        previous_manifest = _load_resume_manifest(run_dir)
        expected_days = None if args.full_history else args.days
        if previous_manifest.get("days") != expected_days:
            raise ValueError("resume options do not match the original snapshot")
        created_at = str(previous_manifest.get("created_at"))
        snapshot_started_at = str(
            previous_manifest.get("snapshot_started_at") or created_at
        )
        resumed = True
        _set_manifest_status(run_dir, "in_progress")
    else:
        run_dir = create_run_dir(args.output_root)
        created_at = datetime.now(timezone.utc).isoformat()
        snapshot_started_at = created_at
        resumed = False
        _write_manifest(
            run_dir,
            created_at=created_at,
            snapshot_started_at=snapshot_started_at,
            resumed=resumed,
            status="in_progress",
            days=days,
        )
    _ACTIVE_RUN_DIR = run_dir
    ensure_output_root_guard(run_dir.parent)
    raw = run_dir / "raw"
    ensure_raw_guard(raw)
    log = AuditLog(run_config={"days": days, "full_history": days is None})
    counts: dict[str, int] = {}
    truncated: dict[str, bool] = {}
    candidates: dict[str, list[str]] = {}

    with HubSpotClient(token) as client:
        # 1. Property definitions first — they scope what we snapshot.
        for obj in ("contacts", "companies", "deals"):
            defs = fetch_properties.fetch_property_definitions(client, obj)
            write_json(raw / f"properties_{obj}.json", defs)
            candidates[obj] = fetch_properties.select_source_candidates(
                defs, log=log, object_type=obj
            )
            log.event("properties_fetched", object_type=obj, count=len(defs))
        console.print("✅ Property definitions fetched")

        # 2. Object records.
        fetchers = [
            ("contacts", fetch_contacts, raw / "contacts.jsonl"),
            ("companies", fetch_companies, raw / "companies.jsonl"),
            ("deals", fetch_deals, raw / "deals.jsonl"),
        ]
        ids: dict[str, list[str]] = {}
        for name, module, out_path in fetchers:
            summary = module.fetch(
                client,
                out_path,
                days=days,
                extra_properties=candidates.get(name, []),
                log=log,
                resume=args.resume is not None,
            )
            counts[name] = summary["count"]
            truncated[name] = summary["truncated"]
            ids[name] = summary["ids"]
            log.event("records_fetched", object_type=name, count=summary["count"])
            console.print(f"✅ {name}: {summary['count']} records")

        # 3. Owners and pipelines.
        counts["owners"] = fetch_owners.fetch(client, raw / "owners.json")["count"]
        counts["pipelines"] = fetch_pipelines.fetch(client, raw / "pipelines.json")["count"]
        console.print(
            f"✅ owners: {counts['owners']}, deal pipelines: {counts['pipelines']}"
        )

        # 4. Associations — degrade gracefully per PRD error-handling policy.
        for from_type, to_type, filename in ASSOCIATION_PAIRS:
            try:
                summary = fetch_associations.fetch(
                    client,
                    from_type,
                    to_type,
                    ids[from_type],
                    raw / filename,
                    resume=args.resume is not None,
                )
                counts[f"assoc_{from_type}_{to_type}"] = summary["rows"]
                log.event(
                    "associations_fetched",
                    pair=f"{from_type}->{to_type}",
                    rows=summary["rows"],
                )
            except HubSpotError:
                log.warn(
                    f"Could not fetch {from_type}->{to_type} associations "
                    "(insufficient access or API error). Association-related "
                    "findings will be low confidence or skipped."
                )
                console.print(
                    f"[yellow]⚠️ {from_type}->{to_type} associations "
                    "unavailable — continuing.[/yellow]"
                )

    # 5. Manifest + audit log.
    _write_manifest(
        run_dir,
        created_at=created_at,
        snapshot_started_at=snapshot_started_at,
        snapshot_completed_at=datetime.now(timezone.utc).isoformat(),
        resumed=resumed,
        status="completed",
        days=days,
        counts=counts,
        truncated=truncated,
        source_candidates=candidates,
        warnings=log.warnings,
    )

    # 6. Profile: sanitized measurement artifacts for the LLM judgment roles.
    profile_summary = profile_run(run_dir)
    log.event("profiled", files=profile_summary["files"])
    console.print(f"✅ Sanitized profiles written to {profile_summary['processed_dir']}")

    retention_root = args.output_root if args.resume is None else run_dir.parent
    pruned = prune_raw_snapshots(
        retention_root,
        retention_days=args.raw_retention_days,
        keep_run_dir=run_dir,
        dry_run=args.dry_run,
    )
    if pruned:
        action = "raw_retention_preview" if args.dry_run else "raw_retention_applied"
        log.event(action, removed_runs=[p.name for p in pruned])
        verb = "Would remove" if args.dry_run else "Removed"
        for old_run in pruned:
            console.print(
                f"[yellow]🧹 {verb} expired raw snapshot: "
                f"{old_run / 'raw'}[/yellow]"
            )
    log.write(run_dir / "audit_log.json")

    table = Table(title=f"Snapshot complete: {run_dir}")
    table.add_column("Object")
    table.add_column("Count", justify="right")
    for key, value in counts.items():
        table.add_row(key, str(value))
    console.print(table)
    if any(truncated.values()):
        console.print(
            "[yellow]⚠️ Some objects hit the 10k search cap and are "
            "truncated (see manifest.json).[/yellow]"
        )
    console.print(
        "Next: python -m scripts.generate_schema_discovery "
        f"--run {run_dir}"
    )
    return 0


def main() -> int:
    """Run the snapshot without exposing raw API error bodies or tracebacks."""
    global _ACTIVE_RUN_DIR
    try:
        return _run_audit()
    except (HubSpotError, OSError, RuntimeError, ValueError) as exc:
        if _ACTIVE_RUN_DIR is not None:
            _set_manifest_status(_ACTIVE_RUN_DIR, "failed")
        console.print(f"[red]❌ CRM snapshot failed: {exc}[/red]")
        return 1
    finally:
        _ACTIVE_RUN_DIR = None


if __name__ == "__main__":
    raise SystemExit(main())
