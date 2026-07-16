"""Run the deterministic audit measurement layer (Phase 4).

Requires validated Phase 3 judgment artifacts (crm_context.yaml,
business_context.json, audit_profile.json). Writes:

    <run_dir>/processed/measurements/<module>.json
    <run_dir>/evidence/<module>.csv

Usage:
    python -m scripts.run_audit_measurements [--run outputs/run_x]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml
from rich.console import Console

from connectors.hubspot.normalize import write_json
from core.config import default_output_root
from core.rules import measure_all
from core.schemas import CrmContext
from core.validators import validate_phase3_artifacts, validate_snapshot_completed
from scripts.generate_schema_discovery import latest_run

console = Console()

SUBAGENT_DIR = "skills/hubspot-crm-trust-audit/subagents"

AUDIT_ROLES = [
    ("attribution_trust", "attribution_trust_agent.md"),
    ("lifecycle_funnel", "lifecycle_funnel_agent.md"),
    ("association_architecture", "association_architecture_agent.md"),
    ("pipeline_hygiene", "pipeline_hygiene_agent.md"),
    ("property_governance", "property_governance_agent.md"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    args = parser.parse_args()

    run_dir = args.run or latest_run(args.output_root)
    if run_dir is None or not Path(run_dir).exists():
        console.print("[red]❌ No run directory found.[/red]")
        return 1
    run_dir = Path(run_dir)

    snapshot_problems = validate_snapshot_completed(run_dir)
    if snapshot_problems:
        for problem in snapshot_problems:
            console.print(f"[red]❌ {problem}[/red]")
        return 1

    # Gate: Phase 3 judgment artifacts must be valid before measuring.
    failed = False
    for artifact, problems in validate_phase3_artifacts(run_dir).items():
        for problem in problems:
            failed = True
            console.print(f"[red]❌ {problem}[/red]")
    if failed:
        console.print(
            "[red]Fix Phase 3 artifacts first "
            "(scripts.generate_schema_discovery --validate).[/red]"
        )
        return 1

    context = CrmContext.model_validate(
        yaml.safe_load((run_dir / "crm_context.yaml").read_text(encoding="utf-8"))
    )
    results = measure_all(run_dir, context)

    measurements_dir = run_dir / "processed" / "measurements"
    for module, doc in results.items():
        write_json(measurements_dir / f"{module}.json", doc)
        available = sum(1 for m in doc["measurements"] if m["available"])
        console.print(
            f"✅ {module}: {available}/{len(doc['measurements'])} measurements "
            f"available, {doc['evidence_rows']} evidence rows"
        )

    (run_dir / "findings").mkdir(exist_ok=True)
    console.print(
        f"""
[bold]Audit judgment task brief (for the host agent)[/bold]

For each module below, follow its instruction file: read the module's
measurements + {run_dir}/audit_profile.json + {run_dir}/crm_context.yaml,
judge severity against the selected profile, and write
{run_dir}/findings/<module>_findings.json.
"""
    )
    for module, role_file in AUDIT_ROLES:
        console.print(f"  - {module}: {SUBAGENT_DIR}/{role_file}")
    console.print(
        f"\nThen validate:\n  python -m scripts.validate_findings --run {run_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
