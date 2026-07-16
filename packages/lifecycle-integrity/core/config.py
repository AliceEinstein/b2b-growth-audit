"""Run configuration and output directory layout."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4


def default_output_root() -> Path:
    """Use the skill repository's absolute, local output directory by default."""
    return Path(__file__).resolve().parents[1] / "outputs"


@dataclass
class RunConfig:
    days: int | None = None  # None = full history; set for a recent-only audit
    output_root: Path = default_output_root()

    @property
    def full_history(self) -> bool:
        return self.days is None


def create_run_dir(output_root: Path, explicit_dir: Path | None = None) -> Path:
    root = Path(output_root).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    ensure_output_root_guard(root)
    if explicit_dir is not None:
        run_dir = Path(explicit_dir).expanduser()
        if run_dir.exists() and any(run_dir.iterdir()):
            raise ValueError(f"output directory is not empty: {run_dir}")
        (run_dir / "raw").mkdir(parents=True, exist_ok=True)
        (run_dir / "processed").mkdir(parents=True, exist_ok=True)
        ensure_output_root_guard(run_dir.parent)
        ensure_explicit_run_guard(run_dir)
        ensure_raw_guard(run_dir / "raw")
        return run_dir
    for _ in range(5):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        run_dir = root / f"run_{stamp}_{uuid4().hex[:8]}"
        try:
            (run_dir / "raw").mkdir(parents=True, exist_ok=False)
            (run_dir / "processed").mkdir(parents=True, exist_ok=False)
            ensure_raw_guard(run_dir / "raw")
            return run_dir
        except FileExistsError:
            continue
    raise RuntimeError("could not allocate a unique CRM audit run directory")


def ensure_output_root_guard(root: Path) -> None:
    """Make accidental ``git add .`` ignore every local snapshot artifact."""
    path = root / ".gitignore"
    marker = "# CRM Audit local snapshot guard"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker in existing:
        lines = existing.splitlines()
        marker_index = lines.index(marker)
        if marker_index + 1 < len(lines) and lines[marker_index + 1].strip() == "*":
            lines[marker_index + 1] = "run_*/"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    addition = f"{marker}\nrun_*/\n"
    separator = "\n" if existing and not existing.endswith("\n") else ""
    path.write_text(existing + separator + addition, encoding="utf-8")


def ensure_raw_guard(raw_dir: Path) -> None:
    """Add the human-visible raw-data warning to new and resumed runs."""
    raw = Path(raw_dir)
    raw.mkdir(parents=True, exist_ok=True)
    path = raw / "README.md"
    if not path.exists():
        path.write_text(
            "# Restricted raw snapshot\n\n"
            "Agents and LLM judgment roles must never read this directory.\n"
            "Use processed/ and evidence/ artifacts instead.\n",
            encoding="utf-8",
        )


def ensure_explicit_run_guard(run_dir: Path) -> None:
    """Deny git tracking inside an arbitrarily named explicit run directory."""
    path = Path(run_dir) / ".gitignore"
    if path.exists():
        return
    path.write_text(
        "# Lifecycle audit local run guard\n"
        "*\n"
        "!.gitignore\n",
        encoding="utf-8",
    )


def latest_run(output_root: Path) -> Path | None:
    runs = sorted(Path(output_root).glob("run_*"))
    return runs[-1] if runs else None
