"""Compatibility entrypoint for lifecycle report generation.

Kept for the historical generate_reports command name. The explicit
generate_lifecycle_reports module remains the canonical implementation.
"""
from __future__ import annotations

from pathlib import Path

from core.rules import MODULES
from scripts.generate_lifecycle_reports import main


def consolidate_evidence(run_dir: Path) -> int:
    """Legacy helper retained for old synthetic fixtures and migration tests."""
    lines: list[str] = []
    for module in MODULES:
        path = run_dir / "evidence" / f"{module}.csv"
        if not path.exists():
            continue
        rows = path.read_text(encoding="utf-8").splitlines()
        if not rows:
            continue
        if not lines:
            lines.append(rows[0])
        lines.extend(rows[1:])
    (run_dir / "evidence.csv").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return max(len(lines) - 1, 0)


if __name__ == "__main__":
    raise SystemExit(main())
