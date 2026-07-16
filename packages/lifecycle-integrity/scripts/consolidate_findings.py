"""Deterministically consolidate workspace outputs into judgment artifacts.

Merges agent_workspace/candidates/*.json into findings.json and
agent_workspace/reviews/*.json into review_trace.json. Duplicate finding IDs
must carry identical payloads; conflicts are reported, never silently merged.

Usage:
    python -m scripts.consolidate_findings --run outputs/run_x --candidates
    python -m scripts.consolidate_findings --run outputs/run_x --reviews
    python -m scripts.consolidate_findings --run outputs/run_x   # both
"""
from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from core.config import default_output_root, latest_run
from core.lifecycle_consolidation import consolidate_candidates, consolidate_reviews

console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument("--candidates", action="store_true")
    parser.add_argument("--reviews", action="store_true")
    args = parser.parse_args()
    run_dir = args.run or latest_run(args.output_root)
    if run_dir is None or not Path(run_dir).exists():
        console.print("[red]❌ No run directory found.[/red]")
        return 1
    run_dir = Path(run_dir)
    do_candidates = args.candidates or not (args.candidates or args.reviews)
    do_reviews = args.reviews or not (args.candidates or args.reviews)
    failed = False
    if do_candidates:
        count, problems = consolidate_candidates(run_dir)
        if problems:
            failed = True
            for problem in problems:
                console.print(f"[red]❌ candidates: {problem}[/red]")
        else:
            console.print(f"✅ findings.json written ({count} candidate finding(s))")
    if do_reviews:
        count, problems = consolidate_reviews(run_dir)
        if problems:
            failed = True
            for problem in problems:
                console.print(f"[red]❌ reviews: {problem}[/red]")
        else:
            console.print(f"✅ review_trace.json written ({count} review decision(s))")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
