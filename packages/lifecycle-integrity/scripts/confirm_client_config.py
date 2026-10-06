"""Confirm a run's client config drafts and rebuild the audit with them.

Run this only after the CRM owner has answered the questions in the report
(section 2, "Questions to Confirm") and the drafts in
``<run_dir>/client_config_draft/`` reflect those answers:

    python -m scripts.confirm_client_config --run <run_dir> --confirmed-by "Jane Doe, RevOps"

The command stamps who confirmed and when, saves the files outside the run
(default ``<output_root>/client_config/``) so later audits can reuse them,
and rebuilds the run from its existing snapshot without calling HubSpot.
CRM Trust can read the same field_overrides.yaml.
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import yaml
from rich.console import Console

from core.client_config import (
    CONFIG_DIR,
    DRAFT_DIR,
    FIELD_OVERRIDES_FILE,
    JOURNEY_MAPPING_FILE,
    ClientConfigError,
    check_against_snapshot,
    parse_field_overrides,
    parse_journey_mapping,
    stamp_confirmation,
)
from scripts import run_lifecycle_integrity_audit

console = Console()
PARSERS = {
    FIELD_OVERRIDES_FILE: parse_field_overrides,
    JOURNEY_MAPPING_FILE: parse_journey_mapping,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, required=True, help="Run whose client_config_draft/ was answered")
    parser.add_argument("--confirmed-by", required=True, help="Name and role of the owner who answered")
    parser.add_argument(
        "--save-to",
        type=Path,
        default=None,
        help="Where to keep the confirmed files (default: <output_root>/client_config/)",
    )
    parser.add_argument(
        "--only",
        choices=[FIELD_OVERRIDES_FILE, JOURNEY_MAPPING_FILE],
        action="append",
        default=None,
        help="Confirm only this draft (repeatable); by default both are confirmed",
    )
    parser.add_argument("--no-rebuild", action="store_true", help="Save the confirmed files without rebuilding")
    return parser.parse_args(argv)


def confirm(run_dir: Path, confirmed_by: str, save_to: Path, names: list[str]) -> dict[str, Path]:
    """Validate, stamp and save the chosen drafts. Returns file name → saved path."""
    if not confirmed_by.strip():
        raise ClientConfigError("--confirmed-by must name the owner who answered")
    today = date.today().isoformat()
    staged: dict[str, str] = {}
    for name in names:
        draft = run_dir / DRAFT_DIR / name
        if not draft.exists():
            raise ClientConfigError(f"{draft} not found — finalize the audit to generate drafts")
        text = stamp_confirmation(draft.read_text(encoding="utf-8"), confirmed_by.strip(), today)
        try:
            data = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            raise ClientConfigError(f"{name}: cannot read YAML: {exc}") from exc
        parsed = PARSERS[name](data, name)
        if name == FIELD_OVERRIDES_FILE:
            problems = check_against_snapshot(run_dir, parsed)
            if problems:
                raise ClientConfigError(f"{name}: " + "; ".join(problems))
        staged[name] = text
    save_to.mkdir(parents=True, exist_ok=True)
    saved = {}
    for name, text in staged.items():
        (save_to / name).write_text(text, encoding="utf-8")
        saved[name] = save_to / name
    return saved


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_dir = args.run.resolve()
    save_to = (args.save_to or run_dir.parent / "client_config").resolve()
    names = args.only or [FIELD_OVERRIDES_FILE, JOURNEY_MAPPING_FILE]
    try:
        saved = confirm(run_dir, args.confirmed_by, save_to, names)
    except ClientConfigError as exc:
        console.print(f"[red]❌ Not confirmed: {exc}[/red]")
        return 1
    for name, path in saved.items():
        console.print(f"✅ Confirmed {name} → {path}")
    if FIELD_OVERRIDES_FILE in saved:
        console.print(
            "CRM Trust can use the same fields: python -m scripts.run_audit_harness init "
            f"--run <crm_trust_run> --field-overrides {saved[FIELD_OVERRIDES_FILE]}"
        )
    if args.no_rebuild:
        return 0
    # A file confirmed in an earlier round stays in force for the rebuild.
    files = {
        name: saved.get(name, run_dir / CONFIG_DIR / name)
        for name in (FIELD_OVERRIDES_FILE, JOURNEY_MAPPING_FILE)
    }
    rebuild = ["--rebuild-from", str(run_dir), "--output-root", str(run_dir.parent)]
    for flag, name in (("--field-overrides", FIELD_OVERRIDES_FILE), ("--journey-mapping", JOURNEY_MAPPING_FILE)):
        if files[name].exists():
            rebuild += [flag, str(files[name])]
    return run_lifecycle_integrity_audit.main(rebuild)


if __name__ == "__main__":
    raise SystemExit(main())
