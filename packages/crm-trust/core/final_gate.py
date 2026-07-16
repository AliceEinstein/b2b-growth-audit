"""Final safety gate — the deterministic layer.

The Privacy + Safety Reviewer (LLM) is the primary judge of report safety.
This gate is the code backstop: it re-runs every fidelity validator, checks
the score is stated verbatim, and scans the final deliverables for leaks.

- Hard leaks (email / phone / token formats): fail unconditionally.
- Blocked-phrase hits: each must be explicitly cleared in
  safety_clearance.json by the Privacy + Safety Reviewer, with a reason and
  the SHA-256 of the exact reviewed deliverable.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .metrics import read_json
from .integrity import hash_files, hashes_match, sha256_file
from .safety import FINAL_DELIVERABLES, scan_deliverables, scan_final_outputs
from .scoring import compute_score
from .validators import (
    load_all_findings,
    validate_findings,
    validate_recommendations,
    validate_report_structure,
    validate_reviews,
    validate_snapshot_completed,
)

REQUIRED_DELIVERABLES = [
    "crm_trust_report.md",
    "crm_trust_report.html",
    "operator_appendix.md",
    "agent_handoff.md",
    "findings.json",
    "evidence.csv",
    "score.json",
    "recommendations.json",
    "crm_context.yaml",
    "schema_discovery_report.md",
    "audit_log.json",
    "manifest.json",
]

CLEARABLE_SOFT_SECTIONS = {
    "## Blocked Actions",
    "## Do Not Auto-Fix",
    "## Actions That Should Not Be Automated",
    "### Actions That Should Not Be Automated",
}


def _soft_phrase_only_in_blocked_section(path: Path, phrase: str) -> bool:
    """Allow a soft safety clearance only in explicit negative-safety prose."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".html":
        lowered = text.lower()
        parts = lowered.split("<!-- blocked-actions:start -->")
        if len(parts) != 2:
            return False
        blocked, marker, after = parts[1].partition("<!-- blocked-actions:end -->")
        return bool(marker) and phrase in blocked and phrase not in parts[0] and phrase not in after
    if path.suffix != ".md":
        return False
    current_heading = ""
    found = False
    for line in text.splitlines():
        if line.startswith(("## ", "### ")):
            current_heading = line.strip()
        if phrase in line.lower():
            found = True
            if current_heading not in CLEARABLE_SOFT_SECTIONS:
                return False
    return found


def _score_problems(run_dir: Path) -> List[str]:
    problems: List[str] = []
    score_path = run_dir / "score.json"
    if not score_path.exists():
        return problems  # covered by the deliverables check
    try:
        stored = json.loads(score_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"score.json is invalid JSON — {exc}"]
    findings, finding_problems = load_all_findings(run_dir)
    if finding_problems:
        return problems  # covered by the findings check
    try:
        recomputed = compute_score(findings)
    except ValueError as exc:
        return [str(exc)]
    if stored != recomputed:
        problems.append(
            f"score.json does not match the recomputed score ({recomputed['total']}/100) "
            "— the score is "
            "code-owned and may not be edited."
        )
    report_path = run_dir / "crm_trust_report.md"
    if report_path.exists():
        text = report_path.read_text(encoding="utf-8")
        if f"{recomputed['total']}/100" not in text:
            problems.append(
                "crm_trust_report.md must state the computed score verbatim "
                f"('{recomputed['total']}/100')."
            )
    return problems


def run_final_gate(run_dir: Path) -> Dict[str, Any]:
    """Run every deterministic check. Writes final_gate_report.json."""
    run_dir = Path(run_dir)

    problems: Dict[str, List[str]] = {
        "snapshot": validate_snapshot_completed(run_dir),
        "findings": [
            p for ps in validate_findings(run_dir).values() for p in ps
        ],
        "reviews": validate_reviews(run_dir),
        "recommendations": validate_recommendations(run_dir),
        "reports": validate_report_structure(run_dir),
        "deliverables": [
            f"missing final deliverable: {name}"
            for name in REQUIRED_DELIVERABLES
            if not (run_dir / name).exists()
        ],
    }
    problems["score"] = _score_problems(run_dir)

    # Hard leak formats are never legitimate anywhere outside raw/. Scan the
    # entire run tree so an agent workspace or intermediate artifact cannot
    # hide PII or a token behind the narrower shareable-deliverable contract.
    all_output_hits = scan_final_outputs(run_dir)
    # Soft blocked phrases may legitimately appear in explicit safety prose;
    # preserve the contextual clearance workflow for final deliverables only.
    deliverable_hits = scan_deliverables(run_dir)
    deliverable_hashes = hash_files(run_dir, FINAL_DELIVERABLES)
    clearance_path = run_dir / "safety_clearance.json"
    clearance_hash = sha256_file(clearance_path) if clearance_path.is_file() else None
    hard_leaks = [
        {"kind": h.kind, "file": Path(h.source).name, "excerpt": h.excerpt}
        for h in all_output_hits
        if h.hard
    ]
    clearances = read_json(clearance_path, [])
    if not isinstance(clearances, list):
        problems.setdefault("safety_clearance", []).append(
            "safety_clearance.json must contain a JSON array."
        )
        clearances = []
    soft_hits = [h for h in deliverable_hits if h.kind == "blocked_phrase"]

    def is_cleared(hit) -> bool:
        return any(
            c.get("phrase") == hit.excerpt
            and c.get("file") == Path(hit.source).name
            and c.get("file_sha256") == deliverable_hashes.get(Path(hit.source).name)
            and c.get("reason")
            for c in clearances
        )

    uncleared = [
        {"phrase": h.excerpt, "file": Path(h.source).name}
        for h in soft_hits
        if not is_cleared(h)
        or not _soft_phrase_only_in_blocked_section(Path(h.source), h.excerpt)
    ]

    passed = (
        all(not v for v in problems.values())
        and not hard_leaks
        and not uncleared
    )
    doc = {
        "passed": passed,
        "problems": {k: v for k, v in problems.items() if v},
        "hard_leaks": hard_leaks,
        "uncleared_phrases": uncleared,
        "cleared_phrases": len(soft_hits) - len(uncleared),
        "deliverable_hashes": deliverable_hashes,
        "safety_clearance_sha256": clearance_hash,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (run_dir / "final_gate_report.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return doc


def verify_final_gate_report(run_dir: Path) -> list[str]:
    """Verify that a stored PASSED report still describes current files."""
    path = Path(run_dir) / "final_gate_report.json"
    if not path.exists():
        return ["final_gate_report.json not found."]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"final_gate_report.json is invalid JSON — {exc}"]
    problems: list[str] = []
    if doc.get("passed") is not True:
        problems.append("final_gate_report.json does not state passed: true.")
    expected = doc.get("deliverable_hashes")
    if not isinstance(expected, dict):
        problems.append("final_gate_report.json has no deliverable hash map.")
    else:
        if set(expected) != set(FINAL_DELIVERABLES):
            problems.append(
                "final_gate_report.json hash map does not cover exactly all "
                "final deliverables."
            )
        matches, mismatches = hashes_match(Path(run_dir), expected)
        if not matches:
            problems.append(
                "final deliverables changed after the gate: "
                + ", ".join(mismatches)
            )
    clearance_path = Path(run_dir) / "safety_clearance.json"
    expected_clearance = doc.get("safety_clearance_sha256")
    current_clearance = (
        sha256_file(clearance_path) if clearance_path.is_file() else None
    )
    if expected_clearance != current_clearance:
        problems.append("safety_clearance.json changed after the gate.")
    return problems
