"""Deterministic validation of LLM judgment artifacts.

Fidelity checks only — never judgment. We verify that a judgment artifact
is well-formed and that every field it cites actually exists in the portal
(an LLM cannot invent a property and have it survive this gate). Whether
the judgment itself is *right* is reviewed by other LLM roles in Phase 5.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml
from pydantic import ValidationError

from .schemas import (
    AuditProfileSelection,
    BusinessContext,
    CrmContext,
    Finding,
    Recommendations,
    ReportNarrative,
    ReviewEntry,
)

SINGULAR_TO_PLURAL = {"contact": "contacts", "company": "companies", "deal": "deals"}


def _property_names(run_dir: Path, plural: str) -> Optional[Set[str]]:
    path = Path(run_dir) / "raw" / f"properties_{plural}.json"
    if not path.exists():
        return None
    definitions = json.loads(path.read_text(encoding="utf-8"))
    return {d.get("name") for d in definitions}


def _all_property_names(run_dir: Path) -> Optional[Set[str]]:
    combined: Set[str] = set()
    found_any = False
    for plural in SINGULAR_TO_PLURAL.values():
        names = _property_names(run_dir, plural)
        if names is not None:
            combined |= names
            found_any = True
    return combined if found_any else None


def validate_snapshot_completed(run_dir: Path) -> List[str]:
    """Downstream phases may consume only a completed fetch snapshot."""
    path = Path(run_dir) / "manifest.json"
    if not path.exists():
        return ["manifest.json not found — the snapshot fetch is incomplete."]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"manifest.json: invalid JSON — {exc}"]
    if data.get("status") != "completed":
        return [
            "manifest.json: snapshot status is "
            f"{data.get('status')!r}; resume or complete the fetch before "
            "running downstream phases."
        ]
    return []


def validate_crm_context(run_dir: Path) -> List[str]:
    run_dir = Path(run_dir)
    path = run_dir / "crm_context.yaml"
    if not path.exists():
        return [f"{path.name} not found — the schema discovery role has not run."]

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [f"{path.name}: invalid YAML — {exc}"]

    try:
        context = CrmContext.model_validate(data)
    except ValidationError as exc:
        return [f"{path.name}: schema validation failed — {exc}"]

    problems: List[str] = []

    # Anti-hallucination: every cited field must exist in the portal.
    for name, mapping in context.canonical_fields.items():
        plural = SINGULAR_TO_PLURAL[mapping.object]
        names = _property_names(run_dir, plural)
        if names is not None and mapping.field not in names:
            problems.append(
                f"canonical_fields.{name}: field '{mapping.field}' does not "
                f"exist on {plural} — fields must come from the snapshot, "
                "never invented."
            )

    all_names = _all_property_names(run_dir)
    if all_names is not None:
        for field in context.suspected_legacy_fields:
            if field not in all_names:
                problems.append(
                    f"suspected_legacy_fields: '{field}' does not exist on any "
                    "snapshotted object."
                )
        for group in context.suspected_duplicate_groups:
            for field in group:
                if field not in all_names:
                    problems.append(
                        f"suspected_duplicate_groups: '{field}' does not exist "
                        "on any snapshotted object."
                    )

    return problems


def validate_business_context(run_dir: Path) -> List[str]:
    path = Path(run_dir) / "business_context.json"
    if not path.exists():
        return [f"{path.name} not found — the business context role has not run."]
    try:
        BusinessContext.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValidationError) as exc:
        return [f"{path.name}: validation failed — {exc}"]
    return []


def validate_report_narrative(run_dir: Path) -> List[str]:
    """Validate the bounded narrative used by the deterministic renderer."""
    path = Path(run_dir) / "report_narrative.json"
    if not path.exists():
        return ["report_narrative.json not found — the narrative role has not run."]
    try:
        narrative = ReportNarrative.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        return [f"report_narrative.json: validation failed — {exc}"]

    findings, finding_problems = load_all_findings(Path(run_dir))
    known_ids = {finding.id for finding in findings}
    problems = list(finding_problems)
    for root_cause in narrative.root_causes:
        unknown = sorted(set(root_cause.finding_ids) - known_ids)
        if unknown:
            problems.append(
                f"report_narrative.json/root_causes/{root_cause.id}: unknown "
                f"finding ids: {', '.join(unknown)}"
            )
    return problems


def validate_audit_profile(run_dir: Path) -> List[str]:
    path = Path(run_dir) / "audit_profile.json"
    if not path.exists():
        return [f"{path.name} not found — the audit model selector has not run."]
    try:
        AuditProfileSelection.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        return [f"{path.name}: validation failed — {exc}"]
    return []


def validate_phase3_artifacts(run_dir: Path) -> Dict[str, List[str]]:
    """Validate whichever Phase 3 judgment artifacts exist or are expected."""
    return {
        "crm_context.yaml": validate_crm_context(run_dir),
        "business_context.json": validate_business_context(run_dir),
        "audit_profile.json": validate_audit_profile(run_dir),
    }


# -- findings (Phase 4) -----------------------------------------------------------


def _numbers_match(finding: Finding, measurement: Dict[str, Any]) -> List[str]:
    problems = []
    pairs = [
        ("denominator", finding.denominator, measurement.get("denominator")),
        ("affected_records", finding.affected_records, measurement.get("affected_records")),
        (
            "affected_percentage",
            finding.affected_percentage,
            measurement.get("affected_percentage"),
        ),
    ]
    for name, finding_value, measured_value in pairs:
        if finding_value is None and measured_value is None:
            continue
        if finding_value is None or measured_value is None:
            problems.append(
                f"finding '{finding.id}': {name} is {finding_value!r} but the "
                f"measurement says {measured_value!r} — copy measurement "
                "numbers verbatim."
            )
            continue
        if abs(float(finding_value) - float(measured_value)) > 1e-9:
            problems.append(
                f"finding '{finding.id}': {name}={finding_value} does not match "
                f"measurement {measurement['id']} ({measured_value}). Numbers "
                "come from measurements, never from the LLM."
            )
    return problems


def _validate_evidence_reference(
    run_dir: Path, module: str, finding: Finding
) -> List[str]:
    """Keep evidence references inside the deterministic module evidence file."""
    expected = Path("evidence") / f"{module}.csv"
    reference = Path(finding.evidence_file)
    if reference.is_absolute() or ".." in reference.parts or reference != expected:
        return [
            f"finding '{finding.id}': evidence_file must be exactly "
            f"'{expected.as_posix()}', never raw/ or an outside path."
        ]

    path = run_dir / expected
    if not path.exists():
        return [
            f"finding '{finding.id}': evidence_file "
            f"'{expected.as_posix()}' does not exist."
        ]

    # Deterministic evidence rows are keyed by measurement id.  A scored
    # finding must point to a measurement that actually has evidence rows.
    if finding.measurement_id is not None:
        try:
            with path.open(encoding="utf-8", newline="") as fh:
                rows = csv.DictReader(fh)
                if not any(
                    row.get("finding_id") == finding.measurement_id for row in rows
                ):
                    return [
                        f"finding '{finding.id}': evidence file does not contain "
                        f"a row for measurement '{finding.measurement_id}'."
                    ]
        except (OSError, csv.Error) as exc:
            return [
                f"finding '{finding.id}': evidence file could not be read — {exc}"
            ]
    return []


def validate_findings(run_dir: Path, modules: Optional[List[str]] = None) -> Dict[str, List[str]]:
    """Validate findings files against schema + measurement traceability."""
    from .rules import MODULES  # local import to avoid a cycle

    run_dir = Path(run_dir)
    results: Dict[str, List[str]] = {}
    seen_finding_ids: Dict[str, str] = {}
    for module in modules or MODULES:
        problems: List[str] = []
        results[module] = problems

        measurements_path = run_dir / "processed" / "measurements" / f"{module}.json"
        if not measurements_path.exists():
            problems.append(
                f"measurements missing for {module} — run "
                "`python -m scripts.run_audit_measurements` first."
            )
            continue
        module_doc = json.loads(measurements_path.read_text(encoding="utf-8"))
        measurements = {m["id"]: m for m in module_doc.get("measurements", [])}

        findings_path = run_dir / "findings" / f"{module}_findings.json"
        if not findings_path.exists():
            problems.append(
                f"findings/{module}_findings.json not found — the {module} "
                "audit role has not run."
            )
            continue
        try:
            doc = json.loads(findings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{findings_path.name}: invalid JSON — {exc}")
            continue
        if doc.get("module") != module:
            problems.append(
                f"{findings_path.name}: module is {doc.get('module')!r}, expected {module!r}"
            )

        for raw_finding in doc.get("findings", []):
            try:
                finding = Finding.model_validate(raw_finding)
            except ValidationError as exc:
                problems.append(f"{findings_path.name}: invalid finding — {exc}")
                continue

            if finding.module != module:
                problems.append(
                    f"finding '{finding.id}': module {finding.module!r} does not "
                    f"match file module {module!r}"
                )
            if finding.auto_fix_allowed:
                problems.append(
                    f"finding '{finding.id}': auto_fix_allowed must be false in v1."
                )
            previous_module = seen_finding_ids.get(finding.id)
            if previous_module is not None:
                problems.append(
                    f"finding '{finding.id}': duplicate finding id; already used "
                    f"in module '{previous_module}'."
                )
            else:
                seen_finding_ids[finding.id] = module
            problems.extend(_validate_evidence_reference(run_dir, module, finding))

            if finding.measurement_id is not None:
                measurement = measurements.get(finding.measurement_id)
                if measurement is None:
                    problems.append(
                        f"finding '{finding.id}': measurement_id "
                        f"'{finding.measurement_id}' does not exist in "
                        f"{module} measurements — never invent measurements."
                    )
                    continue
                if not measurement.get("available", True):
                    problems.append(
                        f"finding '{finding.id}': cites unavailable measurement "
                        f"'{finding.measurement_id}' — a gap is not a number."
                    )
                    continue
                problems.extend(_numbers_match(finding, measurement))
            else:
                if any(
                    v is not None
                    for v in (
                        finding.denominator,
                        finding.affected_records,
                        finding.affected_percentage,
                    )
                ):
                    problems.append(
                        f"finding '{finding.id}': carries structured numbers "
                        "without a measurement_id — qualitative findings must "
                        "leave numeric fields null."
                    )
    return results


# -- review gates (Phase 5) --------------------------------------------------------

REVIEWERS = [
    "data_fidelity_reviewer",
    "logic_reviewer",
    "privacy_safety_reviewer",
    "audit_scope_reviewer",
]


def load_all_findings(run_dir: Path):
    """Load every finding across module files. Returns (findings, problems)."""
    from .rules import MODULES

    run_dir = Path(run_dir)
    findings: List[Finding] = []
    problems: List[str] = []
    seen_ids: Dict[str, str] = {}
    for module in MODULES:
        path = run_dir / "findings" / f"{module}_findings.json"
        if not path.exists():
            problems.append(f"findings/{module}_findings.json not found.")
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{path.name}: invalid JSON — {exc}")
            continue
        for raw in doc.get("findings", []):
            try:
                finding = Finding.model_validate(raw)
            except ValidationError as exc:
                problems.append(f"{path.name}: invalid finding — {exc}")
                continue
            previous_module = seen_ids.get(finding.id)
            if previous_module is not None:
                problems.append(
                    f"finding '{finding.id}': duplicate finding id; already used "
                    f"in module '{previous_module}'."
                )
                continue
            seen_ids[finding.id] = module
            findings.append(finding)
    return findings, problems


def aggregate_verdicts(verdicts: List[str]) -> str:
    if "reject" in verdicts:
        return "rejected"
    if "revise" in verdicts:
        return "revised"
    return "approved"


def validate_reviews(run_dir: Path) -> List[str]:
    """Every finding must be reviewed by all four gates, and review_status
    must equal the deterministic aggregate of the recorded verdicts."""
    run_dir = Path(run_dir)
    path = run_dir / "review_log.json"
    if not path.exists():
        return ["review_log.json not found — the review gates have not run."]

    try:
        raw_entries = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"review_log.json: invalid JSON — {exc}"]

    problems: List[str] = []
    entries: List[ReviewEntry] = []
    for raw in raw_entries:
        try:
            entries.append(ReviewEntry.model_validate(raw))
        except ValidationError as exc:
            problems.append(f"review_log.json: invalid entry — {exc}")
    if problems:
        return problems

    findings, finding_problems = load_all_findings(run_dir)
    problems.extend(finding_problems)
    known_ids = {f.id for f in findings}

    by_finding: Dict[str, Dict[str, str]] = {}
    for entry in entries:
        if entry.finding_id not in known_ids:
            problems.append(
                f"review_log.json: entry for unknown finding "
                f"'{entry.finding_id}'."
            )
            continue
        reviewer_map = by_finding.setdefault(entry.finding_id, {})
        if entry.reviewer in reviewer_map:
            problems.append(
                f"review_log.json: duplicate verdict from {entry.reviewer} "
                f"on '{entry.finding_id}'."
            )
        reviewer_map[entry.reviewer] = entry.verdict

    for finding in findings:
        verdicts = by_finding.get(finding.id, {})
        missing = [r for r in REVIEWERS if r not in verdicts]
        if missing:
            problems.append(
                f"finding '{finding.id}': missing review from {', '.join(missing)}."
            )
            continue
        expected = aggregate_verdicts(list(verdicts.values()))
        if finding.review_status != expected:
            problems.append(
                f"finding '{finding.id}': review_status is "
                f"'{finding.review_status}' but recorded verdicts aggregate to "
                f"'{expected}' (reject > revise > approve)."
            )
    return problems


# -- recommendations + reports (Phase 6) --------------------------------------------


def validate_recommendations(run_dir: Path) -> List[str]:
    run_dir = Path(run_dir)
    path = run_dir / "recommendations.json"
    if not path.exists():
        return ["recommendations.json not found — the recommendation role has not run."]
    try:
        recs = Recommendations.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        return [f"recommendations.json: validation failed — {exc}"]

    findings, _ = load_all_findings(run_dir)
    by_id = {f.id: f for f in findings}
    problems: List[str] = []
    groups = [
        ("safe_operational_actions", recs.safe_operational_actions),
        ("needs_business_rule_confirmation", recs.needs_business_rule_confirmation),
        ("do_not_auto_fix", recs.do_not_auto_fix),
    ]
    for group_name, items in groups:
        for item in items:
            finding = by_id.get(item.finding_id)
            if finding is None:
                problems.append(
                    f"recommendations.json/{group_name}: unknown finding "
                    f"'{item.finding_id}'."
                )
                continue
            if finding.review_status not in {"approved", "revised"}:
                problems.append(
                    f"recommendations.json/{group_name}: finding "
                    f"'{item.finding_id}' is {finding.review_status} — only "
                    "approved/revised findings get recommendations."
                )
            if item.evidence_file != finding.evidence_file:
                problems.append(
                    f"recommendations.json/{group_name}: recommendation for "
                    f"'{item.finding_id}' cites '{item.evidence_file}', but "
                    f"the finding cites '{finding.evidence_file}'."
                )
            if not (run_dir / item.evidence_file).is_file():
                problems.append(
                    f"recommendations.json/{group_name}: evidence file "
                    f"'{item.evidence_file}' does not exist."
                )
            if (
                group_name == "safe_operational_actions"
                and finding.recommendation_type == "do_not_auto_fix"
            ):
                problems.append(
                    f"recommendations.json: '{item.finding_id}' is classified "
                    "do_not_auto_fix and cannot appear under "
                    "safe_operational_actions."
                )
    return problems


REQUIRED_REPORT_SECTIONS = [
    "# HubSpot Marketing-to-Pipeline Trust Audit",
    "## Executive Summary",
    "## CRM Snapshot",
    "## Data Quality and Usability",
    "## Activity and Data Age",
    "## Funnel and Association Coverage",
    "## Key Findings",
    "## Root Cause Hypotheses",
    "## Recommended Actions",
    "## What This Audit Cannot Determine",
    "## Evidence and Supporting Files",
    "## Next Review",
    "## Sharing the Report",
]

REQUIRED_HTML_SECTIONS = [
    "HubSpot Marketing-to-Pipeline Trust Audit",
    "Executive Summary",
    "CRM Snapshot",
    "Data Quality and Usability",
    "Activity and Data Age",
    "Funnel and Association Coverage",
    "Key Findings",
    "Root Cause Hypotheses",
    "Recommended Actions",
    "What This Audit Cannot Determine",
    "Evidence and Supporting Files",
    "Next Review",
    "Sharing the Report",
    "https://smartifymarketing.com",
]

REQUIRED_APPENDIX_SECTIONS = [
    "# CRM Audit Operator Appendix",
    "## How to Use This Appendix",
    "## All Validated Findings",
    "## Detailed Recommendations",
    "## Evidence Index",
    "## Schema and Context Files",
    "## Method and Audit Constraints",
]

REQUIRED_HANDOFF_SECTIONS = [
    "# Agent Handoff: CRM Trust Audit Follow-up",
    "## Safety Boundary",
    "## Approved Low-Risk Follow-ups",
    "## Manual Confirmation Required",
    "## Blocked Actions",
    "## Suggested Implementation Sequence",
    "## Evidence Files",
    "## Questions to Ask Human Owner Before Any Write Action",
]

# These terms expose internal implementation concepts or audience labels that
# do not belong in a client report. Internal operator and handoff artifacts may
# still use them where they are necessary for safe execution.
MAIN_REPORT_BANNED_TERMS = [
    "for cmo",
    "cmo-facing",
    "non-autofix",
    "non auto fix",
    "do not auto-fix",
    "machine-readable",
    "code-owned",
    "narrative agent",
    "deterministic renderer",
    "llm",
    "harness",
]


def validate_report_structure(run_dir: Path) -> List[str]:
    run_dir = Path(run_dir)
    problems: List[str] = []
    for filename, sections in [
        ("crm_trust_report.md", REQUIRED_REPORT_SECTIONS),
        ("crm_trust_report.html", REQUIRED_HTML_SECTIONS),
        ("operator_appendix.md", REQUIRED_APPENDIX_SECTIONS),
        ("agent_handoff.md", REQUIRED_HANDOFF_SECTIONS),
    ]:
        path = run_dir / filename
        if not path.exists():
            problems.append(f"{filename} not found — the report role has not run.")
            continue
        text = path.read_text(encoding="utf-8")
        for section in sections:
            if section not in text:
                problems.append(f"{filename}: missing required section '{section}'.")
        if filename in {"crm_trust_report.md", "crm_trust_report.html"}:
            lowered = text.lower()
            for term in MAIN_REPORT_BANNED_TERMS:
                if term in lowered:
                    problems.append(
                        f"{filename}: internal or audience-specific term "
                        f"'{term}' must not appear in the client report."
                    )
    return problems
