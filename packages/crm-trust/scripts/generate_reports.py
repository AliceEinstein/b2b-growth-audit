"""Consolidate validated findings, compute the score, run the final gate.

Two stages:

    python -m scripts.generate_reports [--run X]
        Gates on findings + reviews, then writes findings.json, score.json,
        evidence.csv and prints the brief for the recommendation and bounded
        report-narrative roles.

    python -m scripts.generate_reports [--run X] --finalize
        Runs the deterministic final safety gate. Must pass for the audit
        to be considered complete.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from connectors.hubspot.normalize import write_json
from core.config import default_output_root
from core.final_gate import run_final_gate
from core.rules import MODULES
from core.scoring import compute_score
from core.validators import (
    load_all_findings,
    validate_findings,
    validate_reviews,
    validate_snapshot_completed,
)
from scripts.generate_schema_discovery import latest_run

console = Console()

SUBAGENT_DIR = "skills/hubspot-crm-trust-audit/subagents"


def consolidate_evidence(run_dir: Path) -> int:
    lines: list = []
    for module in MODULES:
        path = run_dir / "evidence" / f"{module}.csv"
        if not path.exists():
            continue
        rows = path.read_text(encoding="utf-8").splitlines()
        if not rows:
            continue
        if not lines:
            lines.append(rows[0])  # header once
        lines.extend(rows[1:])
    (run_dir / "evidence.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return max(len(lines) - 1, 0)


def finalize(run_dir: Path) -> int:
    doc = run_final_gate(run_dir)
    for check, problems in doc["problems"].items():
        for problem in problems:
            console.print(f"[red]❌ {check}: {problem}[/red]")
    for leak in doc["hard_leaks"]:
        console.print(
            f"[red]❌ HARD LEAK in {leak['file']}: {leak['kind']} "
            f"({leak['excerpt']})[/red]"
        )
    for phrase in doc["uncleared_phrases"]:
        console.print(
            f"[yellow]⚠️ uncleared blocked phrase in {phrase['file']}: "
            f"'{phrase['phrase']}' — the Privacy + Safety Reviewer must clear "
            "it in safety_clearance.json or the report must be fixed.[/yellow]"
        )
    if doc["passed"]:
        console.print(
            f"[green]✅ Final gate PASSED[/green] "
            f"({doc['cleared_phrases']} phrase(s) explicitly cleared). "
            f"Deliverables in {run_dir}."
        )
        return 0
    console.print("[red]Final gate FAILED — see final_gate_report.json.[/red]")
    return 1


def prepare(run_dir: Path) -> int:
    failed = False
    for module, problems in validate_findings(run_dir).items():
        for problem in problems:
            failed = True
            console.print(f"[red]❌ {module}: {problem}[/red]")
    for problem in validate_reviews(run_dir):
        failed = True
        console.print(f"[red]❌ reviews: {problem}[/red]")
    if failed:
        console.print(
            "[red]Findings and review gates must be clean before reports.[/red]"
        )
        return 1

    findings, _ = load_all_findings(run_dir)
    write_json(
        run_dir / "findings.json",
        {"findings": [f.model_dump() for f in findings]},
    )
    score = compute_score(findings)
    write_json(run_dir / "score.json", score)
    evidence_rows = consolidate_evidence(run_dir)

    console.print(
        f"✅ findings.json ({len(findings)} findings), score.json "
        f"(total {score['total']}/100), evidence.csv ({evidence_rows} rows)"
    )
    console.print(
        f"""
[bold]Report task brief (for the host agent)[/bold]

1. {SUBAGENT_DIR}/recommendation_agent.md
   write: {run_dir}/recommendations.json
2. {SUBAGENT_DIR}/report_narrative_agent.md
   write: {run_dir}/report_narrative.json
3. Run the harness advance command so the deterministic renderer writes:
   {run_dir}/crm_trust_report.html
   {run_dir}/crm_trust_report.md
   {run_dir}/operator_appendix.md
   {run_dir}/agent_handoff.md
4. {SUBAGENT_DIR}/privacy_safety_reviewer.md (clearance duty)
   write: {run_dir}/safety_clearance.json for any flagged phrase

Then finalize:
   python -m scripts.run_audit_harness advance --run {run_dir}
   python -m scripts.generate_reports --run {run_dir} --finalize
"""
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()

    run_dir = args.run or latest_run(args.output_root)
    if run_dir is None or not Path(run_dir).exists():
        console.print("[red]❌ No run directory found.[/red]")
        return 1
    run_dir = Path(run_dir)
    snapshot_problems = validate_snapshot_completed(run_dir)
    if snapshot_problems:
        for problem in snapshot_problems:
            console.print(f"[red]❌ {problem}[/red]")
        return 1

    return finalize(run_dir) if args.finalize else prepare(run_dir)


if __name__ == "__main__":
    raise SystemExit(main())
