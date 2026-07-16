"""Schema discovery driver: deterministic prep + validation.

The judgment itself is performed by the host LLM agent following
skills/hubspot-crm-trust-audit/subagents/schema_discovery_agent.md
(and business_context_agent.md / audit_model_selector.md).

Usage:
    python -m scripts.generate_schema_discovery [--run outputs/run_x]
        Ensure processed artifacts exist (profiling if needed) and print
        the task brief for the host agent.

    python -m scripts.generate_schema_discovery --validate [--run ...]
        Validate the LLM judgment artifacts (schema + field existence).
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from rich.console import Console

from core.config import default_output_root
from core.profiler import PROCESSED_FILES, profile_run
from core.validators import validate_phase3_artifacts, validate_snapshot_completed

console = Console()

SUBAGENT_DIR = "skills/hubspot-crm-trust-audit/subagents"


def latest_run(output_root: Path) -> Optional[Path]:
    runs = sorted(Path(output_root).glob("run_*"))
    return runs[-1] if runs else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=None, help="Run directory")
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument("--reprofile", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    run_dir = args.run or latest_run(args.output_root)
    if run_dir is None or not Path(run_dir).exists():
        console.print(
            "[red]❌ No run directory found. Run "
            "`python -m scripts.run_crm_trust_audit` first.[/red]"
        )
        return 1
    run_dir = Path(run_dir)

    snapshot_problems = validate_snapshot_completed(run_dir)
    if snapshot_problems:
        for problem in snapshot_problems:
            console.print(f"[red]❌ {problem}[/red]")
        return 1

    if args.validate:
        results = validate_phase3_artifacts(run_dir)
        failed = False
        for artifact, problems in results.items():
            if not problems:
                console.print(f"✅ {artifact} valid")
            else:
                failed = True
                for problem in problems:
                    console.print(f"[red]❌ {problem}[/red]")
        return 1 if failed else 0

    processed = run_dir / "processed"
    missing = [f for f in PROCESSED_FILES if not (processed / f).exists()]
    if missing or args.reprofile:
        console.print(f"Profiling snapshot in {run_dir}…")
        profile_run(run_dir)
        console.print("✅ Processed artifacts written")
    else:
        console.print("✅ Processed artifacts already present")

    console.print(
        f"""
[bold]Schema discovery task brief (for the host agent)[/bold]

Perform the judgment roles below IN ORDER, reading only processed
artifacts — never {run_dir}/raw/.

1. {SUBAGENT_DIR}/schema_discovery_agent.md
   read:  {processed}/source_field_candidates.json
          {processed}/property_usage_summary.json
          {processed}/field_empty_rates.json
          {processed}/lifecycle_distribution.json
          {processed}/pipeline_summary.json
          {processed}/association_summary.json
          {processed}/identity_completeness.json
          {processed}/snapshot_summary.json
          {processed}/activity_summary.json
   write: {run_dir}/crm_context.yaml
          {run_dir}/schema_discovery_report.md

2. {SUBAGENT_DIR}/business_context_agent.md
   read:  {processed}/object_counts.json + summaries above + crm_context.yaml
   write: {run_dir}/business_context.json

3. {SUBAGENT_DIR}/audit_model_selector.md
   read:  {run_dir}/crm_context.yaml, {run_dir}/business_context.json
   write: {run_dir}/audit_profile.json

Then validate:
   python -m scripts.generate_schema_discovery --run {run_dir} --validate
"""
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
