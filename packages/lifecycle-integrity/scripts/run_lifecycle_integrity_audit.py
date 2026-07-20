"""Run the local-first HubSpot Lifecycle Integrity Audit preparation phase.

This command performs one read-only snapshot pass, writes sanitized profiles,
builds the Journey Evidence Store and Journey Pattern Registry, measures
pattern-specific integrity facts, and stops for agent judgment/review.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.console import Console

from core.config import default_output_root, latest_run
from core.automation_integrity import build_automation_integrity_artifacts
from core.intent_evidence import build_intent_evidence
from core.journey_evidence import build_journey_evidence_store
from core.lifecycle_agent_tasks import REPO_ROOT, write_agent_task_manifest
from core.lifecycle_rules import measure_lifecycle_integrity
from scripts.run_crm_trust_audit import main as run_snapshot

console = Console()
SKILL_DIR = REPO_ROOT / "skills/hubspot-lifecycle-integrity-audit/subagents"


def positive_days(value: str) -> int:
    days = int(value)
    if days <= 0:
        raise argparse.ArgumentTypeError("days must be greater than zero")
    return days


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    window = parser.add_mutually_exclusive_group()
    window.add_argument(
        "--days",
        type=positive_days,
        default=None,
        help=(
            "restrict the snapshot to records CREATED in the last N days. "
            "Full history is the default: B2B sales cycles run 6-18 months, "
            "so short creation windows truncate journeys and lose the older "
            "contacts/companies that in-window deals link to. Use --days only "
            "for a quick preliminary scan; it routes through the search API, "
            "which caps each object at 10,000 records."
        ),
    )
    window.add_argument(
        "--full-history",
        action="store_true",
        help="fetch full history explicitly (this is already the default)",
    )
    parser.add_argument(
        "--include-activities",
        action="store_true",
        help="Compatibility option; intent-enabled runs fetch activity metadata by default.",
    )
    parser.add_argument(
        "--core-only",
        action="store_true",
        help="Skip activity, event, form, and campaign acquisition for a core-only run.",
    )
    parser.add_argument("--resume", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument(
        "--business-name",
        default=None,
        help="Business name shown in the report (recommended for a branded report).",
    )
    parser.add_argument("--raw-retention-days", type=positive_days, default=365)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.days is not None and args.resume is None:
        console.print(
            f"[yellow]⚠️ --days {args.days} restricts the snapshot to records "
            "CREATED in that window. B2B journeys typically span 6-18 months, "
            "so windowed runs are quick preliminary scans: journey detection "
            "and attribution checks lose the older contacts/companies that "
            "in-window deals link to, and affected checks will carry "
            "out-of-window exclusion notes. Run without --days for the "
            "authoritative audit.[/yellow]"
        )
    snapshot_args: list[str] = []
    if args.resume is not None:
        manifest_path = args.resume / "manifest.json"
        if not manifest_path.exists():
            console.print("[red]❌ Resume directory has no manifest.json.[/red]")
            return 1
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        snapshot_args.extend(["--resume", str(args.resume)])
        if manifest.get("days"):
            snapshot_args.extend(["--days", str(manifest["days"])])
        else:
            snapshot_args.append("--full-history")
    elif args.days is not None:
        snapshot_args.extend(["--days", str(args.days)])
    else:
        snapshot_args.append("--full-history")
    snapshot_args.extend(["--output-root", str(args.output_root)])
    snapshot_args.extend(["--raw-retention-days", str(args.raw_retention_days)])
    if args.business_name:
        snapshot_args.extend(["--business-name", args.business_name])
    if args.output_dir is not None:
        snapshot_args.extend(["--output-dir", str(args.output_dir)])
    if args.include_activities:
        snapshot_args.append("--include-activities")
    if not args.core_only:
        snapshot_args.append("--include-intent-signals")
    if args.dry_run:
        snapshot_args.append("--dry-run")

    status = run_snapshot(snapshot_args)
    if status:
        return status
    run_dir = args.resume or args.output_dir or latest_run(args.output_root)
    if run_dir is None:
        console.print("[red]❌ Snapshot completed but no run directory was found.[/red]")
        return 1
    run_dir = Path(run_dir)
    try:
        intent = build_intent_evidence(run_dir)
        store = build_journey_evidence_store(run_dir)
        measurements = measure_lifecycle_integrity(run_dir)
        automation = build_automation_integrity_artifacts(run_dir)
        tasks = write_agent_task_manifest(run_dir)
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]❌ Lifecycle preparation failed: {exc}[/red]")
        return 1
    console.print(f"✅ Journey Evidence Store: {run_dir / 'processed/journey_evidence_store.json'}")
    console.print(f"✅ Journey Pattern Registry: {run_dir / 'journey_pattern_registry.json'}")
    console.print(f"✅ Lifecycle measurements: {len(measurements['measurements'])}")
    console.print(
        "✅ Automation & scoring coverage: "
        f"{automation.get('coverage', {}).get('status', 'unavailable')}"
    )
    console.print(
        "✅ Intent/activity coverage: "
        f"{intent.get('coverage', {}).get('status', 'unavailable')} · "
        f"{intent.get('event_count', 0)} normalized signal(s)"
    )
    console.print(f"✅ Isolated agent task contracts: {len(tasks['tasks'])}")
    console.print(
        f"""
[bold]Agent judgment phase[/bold] (run every command from the repository root: {REPO_ROOT})

Loop the agent-driven harness until it reports completion:

  python -m scripts.harness next --run {run_dir}
      # materializes one task into agent_workspace/inbox/<role>/
      # (inputs/, instruction.md, contract.json) — work only inside it
  python -m scripts.harness submit --run {run_dir} --role <role>
      # validates and commits output.json; consolidation runs automatically

  python -m scripts.harness status --run {run_dir}
  python -m scripts.harness finalize --run {run_dir}
"""
    )
    if not store.get("activity_summary", {}).get("available"):
        console.print(
            "[yellow]⚠️ Activity-level handoff checks are limited to owner and object-state signals.[/yellow]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
