"""Build or rebuild lifecycle journey evidence for a completed snapshot."""
from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from core.config import default_output_root, latest_run
from core.journey_evidence import build_journey_evidence_store
from core.lifecycle_rules import measure_lifecycle_integrity

console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    args = parser.parse_args()
    run_dir = args.run or latest_run(args.output_root)
    if run_dir is None or not Path(run_dir).exists():
        console.print("[red]❌ No completed run directory found.[/red]")
        return 1
    try:
        build_journey_evidence_store(Path(run_dir))
        doc = measure_lifecycle_integrity(Path(run_dir))
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[red]❌ {exc}[/red]")
        return 1
    console.print(f"✅ Journey evidence and {len(doc['measurements'])} measurements generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
