"""Validate audit findings: schema + verbatim number traceability.

Usage:
    python -m scripts.validate_findings [--run outputs/run_x]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from core.config import default_output_root
from core.validators import validate_findings, validate_snapshot_completed
from scripts.generate_schema_discovery import latest_run

console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    args = parser.parse_args()

    run_dir = args.run or latest_run(args.output_root)
    if run_dir is None or not Path(run_dir).exists():
        console.print("[red]❌ No run directory found.[/red]")
        return 1
    snapshot_problems = validate_snapshot_completed(Path(run_dir))
    if snapshot_problems:
        for problem in snapshot_problems:
            console.print(f"[red]❌ {problem}[/red]")
        return 1

    failed = False
    for module, problems in validate_findings(Path(run_dir)).items():
        if not problems:
            console.print(f"✅ {module}: findings valid")
        else:
            failed = True
            for problem in problems:
                console.print(f"[red]❌ {module}: {problem}[/red]")
    if failed:
        console.print(
            "[red]Fix the findings artifacts — never weaken the validator.[/red]"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
