"""Verify that a previously stored final-gate PASS is still current."""
from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from core.lifecycle_final_gate import verify_lifecycle_final_gate_report

console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    problems = verify_lifecycle_final_gate_report(args.run)
    if problems:
        for problem in problems:
            console.print(f"[red]❌ {problem}[/red]")
        return 1
    console.print("[green]✅ Stored final-gate PASS matches current files.[/green]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
