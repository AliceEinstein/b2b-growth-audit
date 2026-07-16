"""Generate lifecycle reports or run the final safety gate."""
from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from core.config import default_output_root, latest_run
from core.lifecycle_final_gate import run_lifecycle_final_gate
from core.lifecycle_reports import generate_lifecycle_reports
from core.lifecycle_validators import validate_lifecycle_run

console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    run_dir = args.run or latest_run(args.output_root)
    if run_dir is None or not Path(run_dir).exists():
        console.print("[red]❌ No run directory found.[/red]")
        return 1
    run_dir = Path(run_dir)
    if args.finalize:
        try:
            doc = run_lifecycle_final_gate(run_dir)
        except (OSError, RuntimeError, ValueError) as exc:
            console.print(f"[red]❌ Final gate could not run: {exc}[/red]")
            return 1
        if doc["passed"]:
            console.print(f"[green]✅ Lifecycle final gate PASSED[/green]: {run_dir}")
            return 0
        for category, rows in doc["problems"].items():
            for row in rows:
                console.print(f"[red]❌ {category}: {row}[/red]")
        for row in doc["hard_leaks"]:
            console.print(f"[red]❌ hard leak: {row}[/red]")
        for row in doc["uncleared_phrases"]:
            console.print(f"[yellow]⚠️ uncleared blocked phrase: {row}[/yellow]")
        return 1
    problems = validate_lifecycle_run(run_dir, final=False)
    failed = False
    for category, rows in problems.items():
        for row in rows:
            failed = True
            console.print(f"[red]❌ {category}: {row}[/red]")
    if failed:
        return 1
    try:
        result = generate_lifecycle_reports(run_dir)
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]❌ {exc}[/red]")
        return 1
    console.print(
        f"✅ Reports generated; lifecycle score "
        f"{result['score']['overall_lifecycle_integrity_score']}/100"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
