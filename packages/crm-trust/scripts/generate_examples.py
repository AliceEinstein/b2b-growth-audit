"""Materialize the synthetic sample datasets into examples/.

Each sample is a complete, runnable run directory (raw snapshot + valid
Phase 3 judgment artifacts — no HubSpot token needed). Try the pipeline on
one with:

    python -m scripts.run_audit_measurements --run examples/messy_scaleup_sample
"""
from __future__ import annotations

import shutil
from pathlib import Path

from rich.console import Console

from connectors.hubspot.normalize import write_json
from core.synthetic_datasets import DATASETS

console = Console()


def main() -> int:
    examples = Path("examples")
    examples.mkdir(exist_ok=True)
    for name, builder in DATASETS.items():
        target = examples / name
        if target.exists():
            shutil.rmtree(target)
        run, _context, expects = builder(examples)
        write_json(run / "expected_invariants.json", expects)
        console.print(f"✅ {name}: {len(expects)} expected invariants")
    console.print(
        "\nSamples ready. Example:\n"
        "  python -m scripts.run_audit_measurements --run examples/messy_scaleup_sample"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
