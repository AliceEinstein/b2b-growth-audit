"""Validate agent workspace artifacts against the task manifest.

Usage:
    python -m scripts.validate_agent_workspace --run outputs/run_x
    python -m scripts.validate_agent_workspace --run outputs/run_x --require-complete
"""
from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from core.config import default_output_root, latest_run
from core.lifecycle_workspace import validate_agent_workspace

console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="also fail when any declared task output is missing (final-gate mode)",
    )
    args = parser.parse_args()
    run_dir = args.run or latest_run(args.output_root)
    if run_dir is None or not Path(run_dir).exists():
        console.print("[red]❌ No run directory found.[/red]")
        return 1
    problems = validate_agent_workspace(
        Path(run_dir), require_complete=args.require_complete
    )
    if problems:
        for problem in problems:
            console.print(f"[red]❌ workspace: {problem}[/red]")
        return 1
    console.print("✅ agent workspace artifacts satisfy their declared contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
