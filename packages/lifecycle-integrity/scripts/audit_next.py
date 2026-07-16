"""Report the next pending judgment-phase tasks for a lifecycle audit run.

A state-machine view over agent_workspace/task_manifest.json: completed
outputs are schema-checked, and the earliest phase with pending work is
printed with each role's instruction file, declared inputs, and output path.
Roles within one phase may run in parallel.

Usage:
    python -m scripts.audit_next --run outputs/run_x
"""
from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from core.config import default_output_root, latest_run
from core.lifecycle_workspace import PHASE_PREREQUISITES, next_tasks, task_status

console = Console()

CONSOLIDATION_HINTS = {
    "findings.json": "python -m scripts.consolidate_findings --run {run} --candidates",
    "review_trace.json": "python -m scripts.consolidate_findings --run {run} --reviews",
}


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
    phase, pending, problems = next_tasks(run_dir)
    for problem in problems:
        console.print(f"[red]❌ {problem}[/red]")
    if phase is None:
        if problems:
            return 1
        console.print("✅ All judgment-phase tasks are complete. Next:")
        console.print(f"   python -m scripts.validate_findings --lifecycle --run {run_dir}")
        console.print(f"   python -m scripts.generate_lifecycle_reports --run {run_dir}")
        console.print(f"   python -m scripts.generate_lifecycle_reports --run {run_dir} --finalize")
        return 0
    console.print(f"[bold]Next phase: {phase}[/bold] ({len(pending)} pending task(s))")
    blocked_prerequisites = [
        prerequisite
        for prerequisite in PHASE_PREREQUISITES.get(phase, [])
        if not (run_dir / prerequisite).exists()
    ]
    for prerequisite in blocked_prerequisites:
        hint = CONSOLIDATION_HINTS.get(prerequisite, "").format(run=run_dir)
        console.print(
            f"[yellow]⚠️ blocked: {prerequisite} missing — run: {hint}[/yellow]"
        )
    for task in pending:
        status = task_status(run_dir, task)
        marker = "🛑 invalid output" if status == "invalid" else "▶"
        console.print(f"\n{marker} [bold]{task['role']}[/bold]")
        console.print(f"   instruction: {task['instruction']}")
        console.print(f"   inputs: {', '.join(task['inputs'])}")
        console.print(f"   output: {task['output']} (schema: {task['output_schema']})")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
