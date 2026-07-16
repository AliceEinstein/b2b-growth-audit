"""Agent-driven harness CLI for the lifecycle audit judgment phase.

The host coding agent loops three verbs — no LLM provider is built in:

    python -m scripts.harness next     --run <dir>
    python -m scripts.harness submit   --run <dir> --role <role> [--resubmit]
    python -m scripts.harness status   --run <dir>
    python -m scripts.harness finalize --run <dir>

`next` materializes the declared inputs of exactly one pending task into
agent_workspace/inbox/<role>/ (inputs/, instruction.md, contract.json) and
tells the agent where to write output.json. `submit` validates before
committing and journals the artifact hash. Phase consolidations run
automatically. `finalize` runs validators, deterministic reports, and the
final gate.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from core.config import default_output_root, latest_run
from core.harness import claim_next, submit_task
from core.lifecycle_final_gate import run_lifecycle_final_gate
from core.lifecycle_reports import generate_lifecycle_reports
from core.lifecycle_workspace import PHASE_ORDER, next_tasks
from core.lifecycle_validators import validate_lifecycle_run

console = Console()


def _resolve_run(args: argparse.Namespace) -> Path | None:
    run_dir = args.run or latest_run(args.output_root)
    if run_dir is None or not Path(run_dir).exists():
        console.print("[red]❌ No run directory found.[/red]")
        return None
    return Path(run_dir)


def cmd_next(args: argparse.Namespace) -> int:
    run_dir = _resolve_run(args)
    if run_dir is None:
        return 1
    task, inbox, problems = claim_next(run_dir)
    for problem in problems:
        console.print(f"[red]❌ {problem}[/red]")
    if task is None:
        if problems:
            return 1
        console.print(
            "✅ All judgment tasks are complete. Run: "
            f"python -m scripts.harness finalize --run {run_dir}"
        )
        return 0
    console.print(
        f"[bold]Task: {task['role']}[/bold] "
        f"(phase: {task['phase']}, model tier: {task['model_tier']})"
    )
    console.print(
        f"  model tier '{task['model_tier']}' is advisory — tasks run on the "
        "session model unless the user configured tier mapping "
        "(see contract.json model_routing_hint)"
    )
    console.print(f"  workspace: {inbox}")
    console.print(f"  instruction: {inbox}/instruction.md")
    console.print(f"  contract: {inbox}/contract.json")
    console.print(f"  inputs: {inbox}/inputs/  (read nothing outside this directory)")
    console.print(f"  write: {inbox}/output.json")
    console.print(
        f"  then: python -m scripts.harness submit --run {run_dir} --role {task['role']}"
    )
    return 0


def cmd_submit(args: argparse.Namespace) -> int:
    run_dir = _resolve_run(args)
    if run_dir is None:
        return 1
    ok, problems = submit_task(run_dir, args.role, resubmit=args.resubmit)
    if not ok:
        for problem in problems:
            console.print(f"[red]❌ rejected: {problem}[/red]")
        return 1
    console.print(f"✅ {args.role} committed")
    for problem in problems:
        console.print(f"[yellow]⚠️ phase transition: {problem}[/yellow]")
    phase, pending, _ = next_tasks(run_dir)
    if phase is None:
        console.print(
            "✅ All judgment tasks complete. Next: "
            f"python -m scripts.harness finalize --run {run_dir}"
        )
    else:
        console.print(f"Next phase: {phase} ({len(pending)} task(s) pending)")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    run_dir = _resolve_run(args)
    if run_dir is None:
        return 1
    from core.lifecycle_workspace import task_status
    from core.lifecycle_agent_tasks import TASKS

    for phase in PHASE_ORDER:
        rows = [t for t in TASKS if t["phase"] == phase]
        if not rows:
            continue
        console.print(f"[bold]{phase}[/bold]")
        for task in rows:
            status = task_status(run_dir, task)
            marker = {"done": "✅", "ready": "▶", "blocked": "⏸", "invalid": "🛑"}.get(
                status, "•"
            )
            console.print(
                f"  {marker} {task['role']} [{status}] ({task['model_tier']})"
            )
    return 0


def cmd_finalize(args: argparse.Namespace) -> int:
    run_dir = _resolve_run(args)
    if run_dir is None:
        return 1
    problems = validate_lifecycle_run(run_dir, final=False)
    failed = [f"{cat}: {row}" for cat, rows in problems.items() for row in rows]
    if failed:
        for row in failed:
            console.print(f"[red]❌ {row}[/red]")
        return 1
    try:
        generate_lifecycle_reports(run_dir)
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]❌ report generation failed: {exc}[/red]")
        return 1
    doc = run_lifecycle_final_gate(run_dir)
    if doc["passed"]:
        console.print(f"[green]✅ Final gate PASSED[/green]: {run_dir}")
        return 0
    for category, rows in doc["problems"].items():
        for row in rows:
            console.print(f"[red]❌ {category}: {row}[/red]")
    for row in doc["hard_leaks"]:
        console.print(f"[red]❌ hard leak: {row}[/red]")
    for row in doc["uncleared_phrases"]:
        console.print(
            f"[yellow]⚠️ uncleared blocked phrase: {row} — the Privacy + Safety "
            "Reviewer must write a hash-bound safety_clearance.json entry, then "
            "rerun finalize[/yellow]"
        )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verb", choices=["next", "submit", "status", "finalize"])
    parser.add_argument("--run", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument("--role", type=str, default=None)
    parser.add_argument("--resubmit", action="store_true")
    args = parser.parse_args()
    if args.verb == "submit" and not args.role:
        console.print("[red]❌ submit requires --role[/red]")
        return 1
    return {
        "next": cmd_next,
        "submit": cmd_submit,
        "status": cmd_status,
        "finalize": cmd_finalize,
    }[args.verb](args)


if __name__ == "__main__":
    raise SystemExit(main())
