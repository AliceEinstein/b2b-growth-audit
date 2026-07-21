"""Final deterministic gate for lifecycle audit deliverables."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .integrity import hash_files, hashes_match, sha256_file
from .lifecycle_agent_tasks import TASKS
from .lifecycle_scoring import compute_lifecycle_score
from .lifecycle_validators import load_findings, load_registry, validate_lifecycle_run
from .safety import scan_file, scan_final_outputs

FINAL_DELIVERABLES = [
    "lifecycle_integrity_report.md",
    "lifecycle_integrity_report.html",
    "journey_map.md",
    "journey_pattern_registry.json",
    "findings.json",
    "recommendations.md",
    "operator_appendix.md",
    "agent_handoff.md",
    "outlier_registry.csv",
    "evidence.csv",
    "report_record_evidence.csv",
    "report_account_evidence.csv",
    "crm_context.yaml",
    "schema_discovery_report.md",
    "review_trace.json",
    "audit_log.json",
    "lifecycle_score.json",
    "manifest.json",
    "automation_evidence.csv",
]

# Final deliverables are the shareable report contract. These additional
# sanitized automation/agent artifacts are not shareable deliverables, but
# they still cross an agent boundary and must receive the hard leak scan.
AUTOMATION_SAFETY_FILES = [
    "processed/automation_coverage.json",
    "processed/workflow_inventory.json",
    "processed/workflow_dependency_graph.json",
    "processed/workflow_performance_summary.json",
    "processed/scoring_activation_summary.json",
    "processed/automation_scoring_measurements.json",
    "agent_workspace/analysis/automation_scoring_analysis_agent.json",
    "agent_workspace/root_cause/automation_root_cause_agent.json",
]
INTENT_SAFETY_FILES = [
    "processed/intent_signal_summary.json",
    "processed/intent_signal_coverage.json",
    "processed/intent_record_index.json",
    "processed/intent_signal_store.jsonl",
    "processed/recovery_routing.json",
]

# Every committed judgment artifact can influence consolidation or the final
# report. Hash all of them (except the gate report that this module owns) so a
# stored PASS is invalidated when an agent artifact changes after review.
AGENT_SAFETY_FILES = [
    task["output"]
    for task in TASKS
    if task["output"] != "final_gate_report.json"
]
SAFETY_HASH_FILES = list(
    dict.fromkeys(
        FINAL_DELIVERABLES
        + AUTOMATION_SAFETY_FILES
        + INTENT_SAFETY_FILES
        + AGENT_SAFETY_FILES
    )
)
CLEARABLE_SOFT_SECTIONS = {
    "## Blocked Actions",
    "## Do Not Auto-Fix",
    "## 11. Proposed CRM Changes Requiring Approval",
    "## 12. Actions That Should Not Be Automated",
    "### Actions That Should Not Be Automated",
}


def _soft_phrase_only_in_blocked_section(path: Path, phrase: str) -> bool:
    """Allow reviewer clearance only for explicit negative-safety sections."""
    if path.suffix == ".html":
        text = path.read_text(encoding="utf-8")
        if phrase not in text.lower():
            return False
        inside = text.lower().split("<!-- blocked-actions:start -->")
        if len(inside) != 2:
            return False
        blocked, _, after = inside[1].partition("<!-- blocked-actions:end -->")
        return phrase in blocked and phrase not in inside[0] and phrase not in after
    if path.suffix != ".md":
        return False
    current_heading = ""
    found = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(("## ", "### ")):
            current_heading = line.strip()
        if phrase in line.lower():
            found = True
            if current_heading not in CLEARABLE_SOFT_SECTIONS:
                return False
    return found


def run_lifecycle_final_gate(run_dir: Path) -> Dict[str, Any]:
    run_dir = Path(run_dir)
    problems = validate_lifecycle_run(run_dir, final=True)
    problems["deliverables"] = [
        f"missing final deliverable: {name}"
        for name in FINAL_DELIVERABLES
        if not (run_dir / name).exists()
    ]
    registry, registry_problems = load_registry(run_dir)
    findings, finding_problems = load_findings(run_dir)
    if registry is not None and not (registry_problems or finding_problems):
        measurement_path = run_dir / "processed" / "lifecycle_integrity_measurements.json"
        try:
            measurement_doc = json.loads(measurement_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            measurement_doc = {}
        try:
            recomputed = compute_lifecycle_score(
                findings,
                registry,
                measurement_doc.get("measurements", []),
            )
        except ValueError as exc:
            recomputed = None
            problems.setdefault("scoring_contract", []).append(str(exc))
        score_path = run_dir / "lifecycle_score.json"
        try:
            stored = (
                json.loads(score_path.read_text(encoding="utf-8"))
                if score_path.exists()
                else None
            )
        except (json.JSONDecodeError, OSError) as exc:
            stored = None
            problems.setdefault("score", []).append(
                f"lifecycle_score.json is invalid: {exc}"
            )
        if recomputed is not None and stored != recomputed:
            problems.setdefault("score", []).append("lifecycle_score.json does not match deterministic recomputation")
        for report_name in ("lifecycle_integrity_report.md", "lifecycle_integrity_report.html"):
            report_path = run_dir / report_name
            if report_path.exists() and recomputed is not None:
                report_text = report_path.read_text(encoding="utf-8")
                overall = recomputed["overall_lifecycle_integrity_score"]
                score_text = "Not scored" if overall is None else f"{overall}/100"
                html_score = re.search(
                    r"class=['\"][^'\"]*\bhero-number\b[^'\"]*['\"][^>]*>\s*Not scored\s*</span>"
                    if overall is None
                    else rf"class=['\"][^'\"]*\bhero-number\b[^'\"]*['\"][^>]*>\s*{re.escape(str(overall))}\s*</span>.*?class=['\"]hero-denom['\"][^>]*>\s*/100",
                    report_text,
                    flags=re.DOTALL,
                )
                if score_text not in report_text and html_score is None:
                    problems.setdefault("score", []).append(
                        f"{report_name} does not state the deterministic score verbatim"
                    )

    deliverable_hits = []
    for name in FINAL_DELIVERABLES:
        path = run_dir / name
        if path.exists():
            deliverable_hits.extend(scan_file(path))
    # Hard-form leaks are never clearable. Scan every non-raw text artifact,
    # including all general analysis, hypothesis, candidate, review, and inbox
    # outputs—not only the automation roles.
    all_output_hits = scan_final_outputs(run_dir)
    hard_leaks = [
        {"kind": hit.kind, "file": Path(hit.source).name, "excerpt": hit.excerpt}
        for hit in all_output_hits
        if hit.hard
    ]
    hashes = hash_files(run_dir, SAFETY_HASH_FILES)
    clearance_path = run_dir / "safety_clearance.json"
    try:
        clearances = json.loads(clearance_path.read_text(encoding="utf-8")) if clearance_path.exists() else []
    except json.JSONDecodeError:
        clearances = []
        problems.setdefault("safety_clearance", []).append("safety_clearance.json is invalid JSON")
    # Soft phrases in shareable reports follow the existing contextual
    # clearance workflow. Auxiliary automation artifacts are not shareable
    # reports, so any hard leak fails while their soft prose is not silently
    # promoted into a report clearance entry.
    soft_hits = [
        hit
        for hit in deliverable_hits
        if hit.kind == "blocked_phrase"
    ]
    uncleared = []
    for hit in soft_hits:
        filename = Path(hit.source).name
        cleared = any(
            row.get("phrase") == hit.excerpt
            and row.get("file") == filename
            and row.get("file_sha256") == hashes.get(filename)
            and row.get("reason")
            for row in clearances
        )
        if not cleared or not _soft_phrase_only_in_blocked_section(
            run_dir / filename, hit.excerpt
        ):
            uncleared.append({"phrase": hit.excerpt, "file": filename})
    passed = all(not rows for rows in problems.values()) and not hard_leaks and not uncleared
    doc = {
        "passed": passed,
        "problems": {name: rows for name, rows in problems.items() if rows},
        "hard_leaks": hard_leaks,
        "uncleared_phrases": uncleared,
        "deliverable_hashes": hashes,
        "safety_clearance_sha256": sha256_file(clearance_path) if clearance_path.exists() else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (run_dir / "final_gate_report.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


def verify_lifecycle_final_gate_report(run_dir: Path) -> list[str]:
    """Verify that a stored lifecycle PASS still matches protected files."""
    run_dir = Path(run_dir)
    path = run_dir / "final_gate_report.json"
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
        problems.append("final_gate_report.json has no protected artifact hash map.")
    else:
        if set(expected) != set(SAFETY_HASH_FILES):
            problems.append(
                "final_gate_report.json hash map does not cover exactly all "
                "lifecycle deliverables and committed agent artifacts."
            )
        matches, mismatches = hashes_match(run_dir, expected)
        if not matches:
            problems.append(
                "lifecycle protected artifacts changed after the gate: "
                + ", ".join(mismatches)
            )

    clearance_path = run_dir / "safety_clearance.json"
    expected_clearance = doc.get("safety_clearance_sha256")
    current_clearance = (
        sha256_file(clearance_path) if clearance_path.is_file() else None
    )
    if expected_clearance != current_clearance:
        problems.append("safety_clearance.json changed after the gate.")
    return problems
