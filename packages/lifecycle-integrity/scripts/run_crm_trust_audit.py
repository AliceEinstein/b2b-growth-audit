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
    fetch_activities,
    fetch_account_settings,
    fetch_associations,
    fetch_companies,
    fetch_contacts,
    fetch_deals,
    fetch_owners,
    fetch_pipelines,
    fetch_properties,
)
from connectors.hubspot import fetch_automation
from connectors.hubspot import fetch_intent_sources
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
ACTIVITY_ASSOCIATION_OBJECTS = (
    "tasks",
    "meetings",
    "notes",
    "calls",
    "emails",
    "communications",
)
ACTIVITY_ASSOCIATION_TARGETS = ("contacts", "companies", "deals")
LARGE_OBJECT_WARNING = 100_000


def record_volume_warning(object_type: str, count: int) -> str | None:
    if count < LARGE_OBJECT_WARNING:
        return None
    return (
        f"{object_type}: {count} records fetched. Local profiling loads this "
        "object into memory; ensure sufficient RAM or use a shorter --days window."
    )


def positive_days(value: str) -> int:
    try:
        days = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("days must be an integer") from exc
    if days <= 0:
        raise argparse.ArgumentTypeError("days must be greater than zero")
    return days


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
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
    parser.add_argument(
        "--include-activities",
        action="store_true",
        help="Fetch activity metadata (compatibility option; never content)",
    )
    parser.add_argument(
        "--include-intent-signals",
        action="store_true",
        help=(
            "Fetch read-only activity, event, form-submission, and campaign "
            "metadata for lifecycle intent and recovery analysis"
        ),
    )
    parser.add_argument(
        "--business-name",
        default=None,
        help=(
            "Business name to use in reports. Recommended when the HubSpot "
            "account-info endpoint does not expose a display name."
        ),
    )
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional exact directory for a new run",
    )
    return parser.parse_args(argv)


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
    automation: dict[str, object] | None = None,
    intent: dict[str, object] | None = None,
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
        automation=automation or {},
        intent=intent or {},
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


def _run_audit(argv: list[str] | None = None) -> int:
    global _ACTIVE_RUN_DIR
    args = parse_args(argv)
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
        run_dir = create_run_dir(args.output_root, args.output_dir)
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
    automation_coverage: dict[str, object] = {
        "status": "unavailable",
        "limitations": ["Automation acquisition has not run."],
    }
    intent_coverage: dict[str, object] = {
        "status": "not_requested",
        "sources": {},
        "metadata_only": True,
        "limitations": ["Intent acquisition was not requested."],
    }

    with HubSpotClient(token) as client:
        # 1. Property definitions first — they scope what we snapshot.
        for obj in ("contacts", "companies", "deals"):
            defs = fetch_properties.fetch_property_definitions(client, obj)
            write_json(raw / f"properties_{obj}.json", defs)
            candidates[obj] = fetch_properties.select_journey_candidates(
                defs, log=log, object_type=obj
            ) + fetch_properties.select_stage_timestamp_candidates(
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
            volume_warning = record_volume_warning(name, int(summary["count"]))
            if volume_warning:
                log.warn(volume_warning)
                console.print(f"[yellow]⚠️ {volume_warning}[/yellow]")

        # 3. Owners and pipelines.
        counts["owners"] = fetch_owners.fetch(client, raw / "owners.json")["count"]
        counts["pipelines"] = fetch_pipelines.fetch(client, raw / "pipelines.json")["count"]
        account_settings = {"status": "permission_or_api_unavailable", "currency": None}
        try:
            account_settings = fetch_account_settings.fetch_company_currency(
                client, raw / "account_info.json"
            )
            if account_settings.get("currency"):
                console.print(f"✅ portal currency: {account_settings['currency']}")
            else:
                log.warn("Portal currency was not returned; deal amounts will be withheld when unlabeled.")
        except HubSpotError:
            # Currency is a display-quality dependency, not a reason to fail
            # the audit. The report must withhold unlabeled amounts rather than
            # inventing a unit.
            log.warn("Portal currency unavailable; unlabeled deal amounts will be withheld.")
        try:
            # Portal identity is independent of currency. Preserve the business
            # name and portal ID for report naming and authenticated record
            # links even when the optional currency endpoint is unavailable.
            account_settings.update(fetch_account_settings.fetch_portal_identity(client))
        except HubSpotError:
            log.warn("Portal identity unavailable; the report will use generic labels and omit direct record links.")
        if args.business_name:
            account_settings["business_name"] = str(args.business_name).strip()[:120]
            account_settings["business_name_source"] = "user_supplied"
        write_json(raw / "account_info.json", account_settings)
        console.print(
            f"✅ owners: {counts['owners']}, deal pipelines: {counts['pipelines']}"
        )

        # 3b. Workflow configuration and aggregate performance. The
        # connector is structurally read-only even though HubSpot's
        # `automation` scope is mutation-capable. Missing access is an
        # explicit coverage limitation, never a core snapshot failure.
        automation_coverage = fetch_automation.fetch_snapshot(
            client,
            raw,
            days=days,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        if automation_coverage.get("status") == "full":
            console.print(
                f"✅ workflows: {automation_coverage.get('workflow_inventory_count', 0)}"
            )
        else:
            warning = "Automation coverage: " + str(automation_coverage.get("status"))
            log.warn(warning)
            console.print(f"[yellow]⚠️ {warning} — continuing with core audit.[/yellow]")

        if args.include_activities or args.include_intent_signals:
            try:
                activity_summaries = fetch_activities.fetch_all(
                    client,
                    raw,
                    days=days,
                    log=log,
                    resume=args.resume is not None,
                )
                for object_type, summary in activity_summaries.items():
                    counts[object_type] = int(summary["count"])
                    truncated[object_type] = bool(summary["truncated"])
                    ids[object_type] = summary["ids"]
                log.event(
                    "activity_metadata_fetched",
                    counts={name: value["count"] for name, value in activity_summaries.items()},
                )
                console.print("✅ activity metadata fetched (metadata-only)")
                if args.include_intent_signals:
                    available_objects = [
                        name for name, value in activity_summaries.items()
                        if value.get("available")
                    ]
                    unavailable_objects = [
                        name for name, value in activity_summaries.items()
                        if not value.get("available")
                    ]
                    intent_coverage["sources"]["activities"] = {
                        "status": (
                            "full"
                            if not unavailable_objects
                            else "partial"
                            if available_objects
                            else "permission_or_api_unavailable"
                        ),
                        "objects": available_objects,
                        "unavailable_objects": unavailable_objects,
                        "metadata_only": True,
                    }
            except HubSpotError:
                log.warn(
                    "Activity metadata was unavailable. Handoff checks will use "
                    "owner and object-state signals only."
                )
                intent_coverage["sources"]["activities"] = {
                    "status": "permission_or_api_unavailable",
                    "metadata_only": True,
                }
                console.print(
                    "[yellow]⚠️ Activity metadata unavailable — continuing with reduced handoff confidence.[/yellow]"
                )

        if args.include_intent_signals:
            # Sources degrade independently. Missing Events, Forms, or
            # Campaign access is a coverage limitation, not a zero-signal
            # conclusion and never prevents the core audit from completing.
            try:
                event_types = fetch_intent_sources.fetch_event_types(
                    client, raw / "event_types.json"
                )
                selected = fetch_intent_sources.select_event_types(event_types)
                event_summary = fetch_intent_sources.fetch_event_occurrences(
                    client,
                    raw / "event_occurrences.jsonl",
                    selected,
                    days=days,
                )
                intent_coverage["sources"]["events"] = {
                    "status": (
                        "permission_or_api_unavailable"
                        if event_summary.get("failed_event_type_count", 0)
                        >= len(selected)
                        else (
                            "partial"
                            if event_summary.get("failed_event_type_count", 0) > 0
                            or event_summary.get("truncated")
                            else "available"
                        )
                    ),
                    "event_type_count": len(event_types),
                    "selected_event_type_count": len(selected),
                    **event_summary,
                }
            except HubSpotError:
                intent_coverage["sources"]["events"] = {
                    "status": "permission_or_api_unavailable",
                    "metadata_only": True,
                }
                log.warn("HubSpot Events API unavailable; event intent is uncovered.")

            try:
                form_summary = fetch_intent_sources.fetch_forms_and_submissions(
                    client, raw
                )
                intent_coverage["sources"]["forms"] = {
                    "status": "partial" if form_summary.get("truncated") else "available",
                    "metadata_only": True,
                    **form_summary,
                }
            except HubSpotError:
                intent_coverage["sources"]["forms"] = {
                    "status": "permission_or_api_unavailable",
                    "metadata_only": True,
                }
                log.warn("HubSpot Forms API unavailable; form intent is uncovered.")

            try:
                campaign_summary = fetch_intent_sources.fetch_campaign_context(
                    client, raw, days=days
                )
                intent_coverage["sources"]["campaigns"] = {
                    "status": "partial" if campaign_summary.get("truncated") else "available",
                    "metadata_only": True,
                    **campaign_summary,
                }
            except HubSpotError:
                intent_coverage["sources"]["campaigns"] = {
                    "status": "permission_or_api_unavailable",
                    "metadata_only": True,
                }
                log.warn("HubSpot Campaigns API unavailable; campaign context is uncovered.")

            # Associations are fetched separately so a record-linked timeline
            # can distinguish no activity from missing association coverage.
            for activity_type in ACTIVITY_ASSOCIATION_OBJECTS:
                activity_summary = activity_summaries.get(activity_type, {})
                if not activity_summary.get("available"):
                    intent_coverage.setdefault("association_sources", {})[
                        f"{activity_type}->record"
                    ] = {"status": "permission_or_api_unavailable"}
                    continue
                activity_ids = ids.get(activity_type, [])
                for target_type in ACTIVITY_ASSOCIATION_TARGETS:
                    filename = f"associations_{activity_type}_{target_type}.jsonl"
                    try:
                        summary = fetch_associations.fetch(
                            client,
                            activity_type,
                            target_type,
                            activity_ids,
                            raw / filename,
                            resume=args.resume is not None,
                        )
                        counts[f"assoc_{activity_type}_{target_type}"] = summary["rows"]
                        intent_coverage.setdefault("association_sources", {})[
                            f"{activity_type}->{target_type}"
                        ] = {"status": "available", "rows": summary["rows"]}
                    except HubSpotError:
                        intent_coverage.setdefault("association_sources", {})[
                            f"{activity_type}->{target_type}"
                        ] = {"status": "permission_or_api_unavailable"}

            source_statuses = [
                value.get("status")
                for value in (intent_coverage.get("sources") or {}).values()
                if isinstance(value, dict)
            ]
            if source_statuses and all(
                status == "permission_or_api_unavailable" for status in source_statuses
            ):
                intent_coverage["status"] = "permission_denied"
            elif any(status in {"available", "full"} for status in source_statuses):
                intent_coverage["status"] = (
                    "full"
                    if all(status in {"available", "full"} for status in source_statuses)
                    else "partial"
                )
            else:
                intent_coverage["status"] = "unavailable"

        # 4. Associations — degrade gracefully per the connector error-handling policy.
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
        automation=automation_coverage,
        intent=intent_coverage,
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
        "Next: python -m scripts.generate_journey_evidence_store "
        f"--run {run_dir}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the snapshot without exposing raw API error bodies or tracebacks."""
    global _ACTIVE_RUN_DIR
    try:
        return _run_audit(argv)
    except (HubSpotError, OSError, RuntimeError, ValueError) as exc:
        if _ACTIVE_RUN_DIR is not None:
            _set_manifest_status(_ACTIVE_RUN_DIR, "failed")
        console.print(f"[red]❌ CRM snapshot failed: {exc}[/red]")
        return 1
    finally:
        _ACTIVE_RUN_DIR = None


if __name__ == "__main__":
    raise SystemExit(main())
