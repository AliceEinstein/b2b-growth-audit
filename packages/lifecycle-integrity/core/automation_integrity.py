"""Deterministic workflow and scoring integrity measurements.

This module is deliberately code-owned. It reads the local raw automation
snapshot after acquisition, emits sanitized structural artifacts, and links
configuration evidence to existing lifecycle measurements. It does not call
HubSpot and it does not turn workflow presence or absence into a finding by
itself.
"""
from __future__ import annotations

import csv
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from connectors.hubspot.normalize import write_json

from .metrics import is_empty, pct, read_json, read_jsonl
from .sanitizer import sanitize_untrusted_value
from .validators import validate_snapshot_completed

AUTOMATION_EVIDENCE_COLUMNS = [
    "evidence_id",
    "measurement_id",
    "workflow_alias",
    "workflow_id",
    "workflow_name_redacted",
    "issue_type",
    "field_name",
    "configuration_status",
    "causal_status",
    "confidence",
    "limitation",
]

RELEVANT_FIELD_PATTERN = re.compile(
    r"(lifecycle|lead.?status|deal.?stage|pipeline|owner|source|attribution|"
    r"campaign|channel|utm|partner|referr|renew|expansion|account.?tier|"
    r"target.?account|abm|intent|handoff|routing|route|score|fit|engagement|"
    r"likelihood|priority)",
    re.IGNORECASE,
)
SCORE_FIELD_PATTERN = re.compile(
    r"(score|fit|engagement|likelihood|priority|qualification)", re.IGNORECASE
)
FIELD_KEY_PATTERN = re.compile(
    r"(property|field|pipeline|stage|owner|source|lifecycle|score)", re.IGNORECASE
)
SIMPLE_VALUE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{1,120}$")
ACTION_TYPE_KEYS = {"actiontypeid", "action_type_id"}
ACTION_FIELD_CONTAINERS = {
    "fields",
    "inputfields",
    "input_fields",
    "propertyvalues",
    "property_values",
    "propertychanges",
    "property_changes",
}
SKIP_UNKNOWN_VALUES = {
    "property_name",
    "propertyname",
    "field_name",
    "fieldname",
    "pipeline_id",
    "pipelineid",
    "stage_id",
    "stageid",
    "owner_id",
    "ownerid",
    "list_id",
    "listid",
}


def _walk(node: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key), value
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _as_strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, (str, int, float))]
    if isinstance(value, (str, int, float)):
        return [str(value)]
    return []


def _property_definitions(run_dir: Path) -> tuple[dict[str, list[dict[str, Any]]], set[str], set[str]]:
    raw = Path(run_dir) / "raw"
    definitions: dict[str, list[dict[str, Any]]] = {}
    property_names: set[str] = set()
    safe_values: set[str] = set()
    for object_type in ("contacts", "companies", "deals"):
        rows = read_json(raw / f"properties_{object_type}.json", [])
        definitions[object_type] = rows if isinstance(rows, list) else []
        for definition in definitions[object_type]:
            name = str(definition.get("name") or "")
            if name:
                property_names.add(name)
            for option in definition.get("options") or []:
                if isinstance(option, dict) and option.get("value") is not None:
                    safe_values.add(str(option["value"]))
    pipelines = read_json(raw / "pipelines.json", [])
    for pipeline in pipelines if isinstance(pipelines, list) else []:
        if pipeline.get("id") is not None:
            safe_values.add(str(pipeline["id"]))
        for stage in pipeline.get("stages") or []:
            if stage.get("id") is not None:
                safe_values.add(str(stage["id"]))
    owners = read_json(raw / "owners.json", [])
    for owner in owners if isinstance(owners, list) else []:
        if owner.get("id") is not None:
            safe_values.add(str(owner["id"]))
    return definitions, property_names, safe_values


def _all_known_references(
    detail: dict[str, Any], property_names: set[str], safe_values: set[str]
) -> tuple[set[str], set[str]]:
    """Return known references and suspicious unknown field-like values."""
    references: set[str] = set()
    unknown: set[str] = set()
    for key, value in _walk(detail):
        key_lower = key.casefold()
        values = _as_strings(value)
        for item in values:
            if item in property_names:
                references.add(item)
            if FIELD_KEY_PATTERN.search(key) and SIMPLE_VALUE_PATTERN.match(item):
                if item in SKIP_UNKNOWN_VALUES or item.isdigit():
                    continue
                if item not in property_names and item not in safe_values:
                    # Names such as actionTypeId and internal operator values
                    # are not useful dependency references.
                    if key_lower not in {"actiontypeid", "action_type_id", "type", "operator"}:
                        unknown.add(item)
    return references, unknown


def _extract_action_writes(
    detail: dict[str, Any], property_names: set[str], safe_values: set[str]
) -> list[dict[str, str]]:
    writes: list[dict[str, str]] = []
    for key, node in _walk(detail):
        if key.casefold() not in ACTION_FIELD_CONTAINERS or not isinstance(node, dict):
            continue
        for field_key, field_value in node.items():
            field_key_text = str(field_key)
            values = _as_strings(field_value)
            field_name = None
            for value in values:
                if value in property_names:
                    field_name = value
                    break
            if field_name is None and field_key_text in property_names:
                field_name = field_key_text
            if field_name is None and not FIELD_KEY_PATTERN.search(field_key_text):
                continue
            if field_name is None:
                continue
            safe_value = ""
            for value in values:
                if value == field_name:
                    continue
                if value in safe_values or value.isdigit() or value.casefold() in {"true", "false"}:
                    safe_value = value
                    break
            writes.append({"field": field_name, "value": safe_value})
    deduped: dict[tuple[str, str], dict[str, str]] = {}
    for row in writes:
        deduped[(row["field"], row["value"])] = row
    return list(deduped.values())


def _workflow_performance(raw_rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in raw_rows:
        workflow_id = str(row.get("workflow_id") or "")
        series = str(row.get("series") or "").upper()
        frequency = row.get("frequency")
        try:
            count = int(frequency)
        except (TypeError, ValueError):
            continue
        if workflow_id and series in {"ENROLLED", "COMPLETED", "UNENROLLED"}:
            output[workflow_id][series] += count
    return {workflow_id: dict(values) for workflow_id, values in output.items()}


def _safe_name(value: Any) -> str:
    safe = sanitize_untrusted_value(value) or "Unnamed workflow"
    # Keep processed artifacts safe even when a workflow name contains markup;
    # the human HTML renderer still escapes the final display value.
    return safe.replace("<", "‹").replace(">", "›")[:120]


def _relevant_workflow(workflow: dict[str, Any]) -> bool:
    refs = workflow.get("references") or []
    writes = workflow.get("action_writes") or []
    text = " ".join(
        [str(value) for value in refs]
        + [str(row.get("field")) for row in writes if isinstance(row, dict)]
        + [str(row.get("value")) for row in writes if isinstance(row, dict)]
    )
    return bool(RELEVANT_FIELD_PATTERN.search(text))


def _score_candidates(
    run_dir: Path,
    definitions: dict[str, list[dict[str, Any]]],
    workflow_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    raw = Path(run_dir) / "raw"
    candidates: list[dict[str, Any]] = []
    workflow_refs = {
        field
        for workflow in workflow_rows
        for field in workflow.get("references") or []
        if isinstance(field, str)
    }
    for object_type, defs in definitions.items():
        records = read_jsonl(raw / f"{object_type}.jsonl") if (raw / f"{object_type}.jsonl").exists() else []
        for definition in defs:
            name = str(definition.get("name") or "")
            label = str(definition.get("label") or "")
            description = str(definition.get("description") or "")
            if not SCORE_FIELD_PATTERN.search(f"{name} {label} {description}"):
                continue
            values: list[float] = []
            non_empty = 0
            for record in records:
                value = (record.get("properties") or {}).get(name)
                if is_empty(value):
                    continue
                try:
                    values.append(float(value))
                    non_empty += 1
                except (TypeError, ValueError):
                    # A threshold category is useful evidence, but it is not
                    # a numeric score output for distribution calculations.
                    non_empty += 1
            numeric = values
            signals = []
            if definition.get("hubspotDefined"):
                signals.append("hubspot_defined")
            if definition.get("calculated") or definition.get("calculationFormula"):
                signals.append("calculated_property")
            if name in workflow_refs:
                signals.append("referenced_by_workflow")
            if SCORE_FIELD_PATTERN.search(label):
                signals.append("score_like_label")
            classification = (
                "confirmed_score_output"
                if len(signals) >= 2 and ("referenced_by_workflow" in signals or "hubspot_defined" in signals)
                else "probable_score_output"
                if len(signals) >= 2
                else "possible_score_output"
            )
            candidates.append(
                {
                    "object_type": object_type,
                    "field": name,
                    "label": _safe_name(label or name),
                    "classification": classification,
                    "signals": signals,
                    "record_count": len(records),
                    "non_empty": non_empty,
                    "coverage_pct": pct(non_empty, len(records)),
                    "numeric_count": len(numeric),
                    "distinct_numeric": len(set(numeric)),
                    "minimum": min(numeric) if numeric else None,
                    "maximum": max(numeric) if numeric else None,
                    "median": statistics.median(numeric) if numeric else None,
                    "zero_count": sum(1 for value in numeric if value == 0),
                    "workflow_activation_visible": name in workflow_refs,
                }
            )
    return candidates


def _build_workflow_rows(
    details: list[dict[str, Any]],
    property_names: set[str],
    safe_values: set[str],
    performance: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, detail in enumerate(sorted(details, key=lambda row: str(row.get("id") or "")), 1):
        workflow_id = str(detail.get("id") or "")
        refs, unknown = _all_known_references(detail, property_names, safe_values)
        writes = _extract_action_writes(detail, property_names, safe_values)
        sanitized_writes = [
            {
                "field": str(write.get("field") or ""),
                "value": _safe_name(write.get("value"))
                if write.get("value")
                else "",
            }
            for write in writes
        ]
        perf = performance.get(workflow_id, {})
        row = {
            "workflow_alias": f"WF-{index:03d}",
            "workflow_id": workflow_id,
            "workflow_name_redacted": _safe_name(detail.get("name")),
            "object_type_id": str(detail.get("objectTypeId") or ""),
            "is_enabled": bool(detail.get("isEnabled", detail.get("enabled", False))),
            "revision_id": str(detail.get("revisionId") or ""),
            "created_at": detail.get("createdAt"),
            "updated_at": detail.get("updatedAt"),
            "enrollment_type": str((detail.get("enrollmentCriteria") or {}).get("type") or "unknown"),
            "should_re_enroll": (detail.get("enrollmentCriteria") or {}).get("shouldReEnroll"),
            "references": sorted(refs),
            "unknown_references": sorted(_safe_name(value) for value in unknown),
            "action_type_ids": sorted(
                {
                    str(value)
                    for key, value in _walk(detail)
                    if key.casefold() in ACTION_TYPE_KEYS
                    for value in _as_strings(value)
                }
            ),
            "action_writes": sanitized_writes,
            "relevant": False,
            "performance": {
                "enrolled": perf.get("ENROLLED", 0),
                "completed": perf.get("COMPLETED", 0),
                "unenrolled": perf.get("UNENROLLED", 0),
            },
        }
        row["relevant"] = _relevant_workflow(row)
        rows.append(row)
    return rows


def _checks(
    workflows: list[dict[str, Any]],
    score_candidates: list[dict[str, Any]],
    coverage_status: str,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    for workflow in workflows:
        workflow_fields = sorted(
            {
                *[str(value) for value in workflow.get("references") or []],
                *[
                    str(write.get("field"))
                    for write in workflow.get("action_writes") or []
                    if isinstance(write, dict) and write.get("field")
                ],
            }
        )
        if workflow["relevant"] and not workflow["is_enabled"]:
            checks.append(
                {
                    "check_id": "AUTO-001",
                    "issue_type": "relevant_workflow_disabled",
                    "workflow_aliases": [workflow["workflow_alias"]],
                    "fields": workflow_fields,
                    "configuration_status": "defect_confirmed",
                    "causal_status": "possible",
                    "confidence": 60,
                    "limitation": "Configuration does not prove a specific record entered this workflow.",
                }
            )
        if workflow["unknown_references"]:
            checks.append(
                {
                    "check_id": "AUTO-003",
                    "issue_type": "workflow_reference_not_in_snapshot_schema",
                    "workflow_aliases": [workflow["workflow_alias"]],
                    "fields": workflow["unknown_references"],
                    "configuration_status": "opaque_dependency",
                    "causal_status": "unverified",
                    "confidence": 35,
                    "limitation": "The referenced field or dependency was not present in the local schema snapshot.",
                }
            )
        if workflow["relevant"] and workflow["is_enabled"] and not any(workflow["performance"].values()):
            checks.append(
                {
                    "check_id": "AUTO-005",
                    "issue_type": "relevant_workflow_no_aggregate_activity",
                    "workflow_aliases": [workflow["workflow_alias"]],
                    "fields": workflow_fields,
                    "configuration_status": "control_present",
                    "causal_status": "possible",
                    "confidence": 35,
                    "limitation": "No eligible-cohort denominator or per-record execution log is available.",
                }
            )

    writers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for workflow in workflows:
        if not workflow["is_enabled"]:
            continue
        for write in workflow.get("action_writes") or []:
            if write.get("field"):
                writers[str(write["field"])].append(
                    {"workflow": workflow, "value": str(write.get("value") or "")}
                )
    for field, entries in sorted(writers.items()):
        aliases = sorted({entry["workflow"]["workflow_alias"] for entry in entries})
        values = {entry["value"] for entry in entries if entry["value"]}
        if len(aliases) >= 2 and len(values) >= 2:
            checks.append(
                {
                    "check_id": "AUTO-002",
                    "issue_type": "conflicting_active_writers",
                    "workflow_aliases": aliases,
                    "fields": [field],
                    "configuration_status": "defect_confirmed",
                    "causal_status": "probable",
                    "confidence": 70,
                    "limitation": "The conflict is configuration evidence; record-level execution order is not available.",
                }
            )

    for candidate in score_candidates:
        if (
            coverage_status not in {"unavailable", "permission_denied"}
            and candidate["classification"] in {"confirmed_score_output", "probable_score_output"}
            and not candidate["workflow_activation_visible"]
        ):
            checks.append(
                {
                    "check_id": "SCORE-006",
                    "issue_type": "score_output_not_referenced_by_workflow",
                    "workflow_aliases": [],
                    "fields": [candidate["field"]],
                    "configuration_status": "control_absent",
                    "causal_status": "unverified",
                    "confidence": 30,
                    "limitation": "Manual routing or non-workflow activation may exist.",
                }
            )
    return checks


def _measurement_links(
    run_dir: Path,
    workflows: list[dict[str, Any]],
    score_candidates: list[dict[str, Any]],
    checks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    measurement_doc = read_json(Path(run_dir) / "processed" / "lifecycle_integrity_measurements.json", {})
    measurements = measurement_doc.get("measurements") or []
    evidence: list[dict[str, str]] = []
    links: list[dict[str, Any]] = []
    coverage = read_json(Path(run_dir) / "processed" / "automation_coverage.json", {"status": "unavailable"})
    for measurement in measurements:
        measurement_id = str(measurement.get("id") or "")
        field = str(measurement.get("field_name") or "")
        candidates = []
        for check in checks:
            check_fields = {str(value) for value in check.get("fields") or []}
            check_aliases = set(check.get("workflow_aliases") or [])
            matching = field and field in check_fields
            measurement_text = f"{measurement_id} {field}".casefold()
            check_text = " ".join(
                [str(value) for value in check.get("fields") or []]
                + [str(check.get("issue_type") or "")]
            ).casefold()
            keyword_groups = (
                ("owner", "handoff", "routing", "route"),
                ("source", "attribution", "utm", "campaign", "partner", "referr"),
                ("lifecycle", "stage", "deal"),
                ("score", "fit", "engagement", "likelihood", "priority"),
            )
            keyword_matching = bool(check_aliases) and any(
                any(token in measurement_text for token in group)
                and any(token in check_text for token in group)
                for group in keyword_groups
            )
            if matching or keyword_matching:
                candidates.append(check)
        score_fields = [
            candidate["field"]
            for candidate in score_candidates
            if candidate["field"] == field
        ]
        aliases = sorted({alias for check in candidates for alias in check.get("workflow_aliases") or []})
        issue_types = sorted({str(check.get("issue_type")) for check in candidates})
        if candidates:
            best = max(candidates, key=lambda check: int(check.get("confidence", 0)))
            configuration_status = str(best.get("configuration_status"))
            causal_status = str(best.get("causal_status"))
            confidence = int(best.get("confidence", 0))
            limitations = sorted({str(check.get("limitation")) for check in candidates if check.get("limitation")})
        elif score_fields and coverage.get("status") not in {"unavailable", "permission_denied"}:
            configuration_status = "control_absent"
            causal_status = "unverified"
            confidence = 30
            limitations = ["Score output was observed, but no workflow activation reference was found."]
            issue_types = ["score_output_not_referenced_by_workflow"]
        elif coverage.get("status") == "unavailable":
            configuration_status = "unknown"
            causal_status = "unverified"
            confidence = 0
            limitations = ["Automation coverage was unavailable; workflow root cause was not inspected."]
        else:
            configuration_status = "unknown"
            causal_status = "unverified"
            confidence = 0
            limitations = ["No relevant workflow or score link was established for this measurement."]
        links.append(
            {
                "measurement_id": measurement_id,
                "workflow_aliases": aliases,
                "score_fields": score_fields,
                "issue_types": issue_types,
                "configuration_status": configuration_status,
                "causal_status": causal_status,
                "confidence": confidence,
                "limitations": limitations,
                "evidence_refs": [f"automation_evidence.csv#measurement_id={measurement_id}"] if candidates or score_fields else [],
            }
        )
        for index, check in enumerate(candidates, 1):
            for alias in check.get("workflow_aliases") or [""]:
                workflow = next((row for row in workflows if row["workflow_alias"] == alias), {})
                evidence.append(
                    {
                        "evidence_id": f"{measurement_id}:automation:{index}:{alias or 'score'}",
                        "measurement_id": measurement_id,
                        "workflow_alias": alias,
                        "workflow_id": str(workflow.get("workflow_id") or ""),
                        "workflow_name_redacted": str(workflow.get("workflow_name_redacted") or ""),
                        "issue_type": str(check.get("issue_type") or ""),
                        "field_name": ",".join(str(value) for value in check.get("fields") or []),
                        "configuration_status": str(check.get("configuration_status") or ""),
                        "causal_status": str(check.get("causal_status") or ""),
                        "confidence": str(check.get("confidence") or ""),
                        "limitation": str(check.get("limitation") or ""),
                    }
                )
    return links, evidence


def _write_evidence(run_dir: Path, rows: list[dict[str, str]]) -> None:
    path = Path(run_dir) / "automation_evidence.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUTOMATION_EVIDENCE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def build_automation_integrity_artifacts(run_dir: Path) -> dict[str, Any]:
    """Build processed workflow/scoring artifacts; safe when automation is absent."""
    run_dir = Path(run_dir)
    processed = run_dir / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    problems = validate_snapshot_completed(run_dir)
    if problems:
        raise ValueError("cannot build automation artifacts: " + problems[0])
    manifest = read_json(run_dir / "manifest.json", {})
    coverage = manifest.get("automation") or {"status": "unavailable"}
    write_json(processed / "automation_coverage.json", coverage)
    raw_automation = run_dir / "raw" / "automation"
    details = read_json(raw_automation / "workflows.json", [])
    performance_rows = read_json(raw_automation / "workflow_performance.json", [])
    if not isinstance(details, list):
        details = []
    if not isinstance(performance_rows, list):
        performance_rows = []
    definitions, property_names, safe_values = _property_definitions(run_dir)
    performance = _workflow_performance(performance_rows)
    workflows = _build_workflow_rows(details, property_names, safe_values, performance)
    score_candidates = _score_candidates(run_dir, definitions, workflows)
    checks = _checks(
        workflows,
        score_candidates,
        str(coverage.get("status") or "unavailable"),
    )
    links, evidence = _measurement_links(run_dir, workflows, score_candidates, checks)

    write_json(processed / "workflow_inventory.json", workflows)
    write_json(
        processed / "workflow_dependency_graph.json",
        {
            "workflow_count": len(workflows),
            "relevant_workflow_count": sum(1 for row in workflows if row.get("relevant")),
            "workflows": workflows,
        },
    )
    write_json(
        processed / "workflow_performance_summary.json",
        {
            "window": coverage.get("performance_window"),
            "by_workflow": performance,
        },
    )
    write_json(
        processed / "scoring_activation_summary.json",
        {
            "definition_visibility": "output_and_activation_only",
            "score_candidates": score_candidates,
            "limitations": [
                "Full score-model criteria, weights, status, and version history are not read from the public API.",
                "A single snapshot cannot prove that an unchanged score property is active or stale.",
            ],
        },
    )
    artifact = {
        "coverage": coverage,
        "checks": checks,
        "root_cause_links": links,
        "workflow_count": len(workflows),
        "relevant_workflow_count": sum(1 for row in workflows if row.get("relevant")),
        "score_candidate_count": len(score_candidates),
        "limitations": list(coverage.get("limitations") or [])
        + [
            "Workflow configuration does not prove per-record execution.",
            "Missing workflow controls are not defects by default; manual controls may exist.",
        ],
    }
    write_json(processed / "automation_scoring_measurements.json", artifact)
    _write_evidence(run_dir, evidence)
    return artifact
