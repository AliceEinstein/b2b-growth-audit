"""Generate or validate lifecycle schema and journey-discovery artifacts."""
from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from core.config import default_output_root, latest_run
from core.journey_evidence import build_journey_evidence_store
from core.lifecycle_validators import load_registry
from core.profiler import PROCESSED_FILES, profile_run
from core.validators import validate_snapshot_completed

console = Console()
SUBAGENT_DIR = "skills/hubspot-lifecycle-integrity-audit/subagents"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument("--reprofile", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    run_dir = args.run or latest_run(args.output_root)
    if run_dir is None or not Path(run_dir).exists():
        console.print(
            "[red]❌ No run directory found. Run "
            "python -m scripts.run_lifecycle_integrity_audit first.[/red]"
        )
        return 1
    run_dir = Path(run_dir)
    problems = validate_snapshot_completed(run_dir)
    if args.validate:
        _, registry_problems = load_registry(run_dir)
        problems.extend(registry_problems)
        for name in (
            "crm_context.yaml",
            "schema_discovery_report.md",
            "journey_pattern_registry.json",
            "processed/journey_evidence_store.json",
        ):
            if not (run_dir / name).exists():
                problems.append(f"{name} not found")
        if problems:
            for problem in problems:
                console.print(f"[red]❌ {problem}[/red]")
            return 1
        console.print("✅ Lifecycle schema and journey discovery artifacts valid")
        return 0
    if problems:
        for problem in problems:
            console.print(f"[red]❌ {problem}[/red]")
        return 1
    missing = [
        name for name in PROCESSED_FILES if not (run_dir / "processed" / name).exists()
    ]
    try:
        if missing or args.reprofile:
            profile_run(run_dir)
        build_journey_evidence_store(run_dir)
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]❌ Schema discovery failed: {exc}[/red]")
        return 1
    console.print("✅ Schema discovery and Journey Pattern Registry generated")
    console.print(
        f"Review processed artifacts using {SUBAGENT_DIR}/schema_discovery_agent.md"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
