"""Build the confidential human-report bridge from hashes to CRM records.

Agents and processed artifacts remain hash-only.  This deterministic local
layer uses the run salt and raw snapshot to attach safe Company and Deal
labels to validated evidence.  Direct HubSpot URLs are returned to the
renderer only; the CSV intentionally excludes portal IDs, raw IDs, and URLs.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from .metrics import load_association_map, read_json, read_jsonl
from .sanitizer import UNTRUSTED_VALUE_MARKER, hash_record_id, sanitize_untrusted_value


REPORT_RECORD_COLUMNS = [
    "finding_id",
    "measurement_id",
    "object_type",
    "record_id_hash",
    "company_name",
    "deal_name",
    "pipeline_label",
    "deal_stage_label",
]


def _safe_label(value: Any, fallback: str) -> str:
    sanitized = sanitize_untrusted_value(value)
    text = str(sanitized or "").replace(UNTRUSTED_VALUE_MARKER, "").strip()
    if not text or text.startswith("[REDACTED:"):
        return fallback
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:120] or fallback


def _csv_safe(value: Any) -> str:
    """Prevent spreadsheet formula execution in the local evidence export."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def report_identity(run_dir: Path) -> dict[str, str | None]:
    account = read_json(Path(run_dir) / "raw" / "account_info.json", {})
    portal = str(account.get("portal_id") or account.get("portalId") or "").strip()
    if not re.fullmatch(r"\d+", portal):
        portal = ""
    business = _safe_label(account.get("business_name"), "")
    return {
        "business_name": business or None,
        "portal_id": portal or None,
    }


def _record_url(portal_id: str | None, object_type_id: str, record_id: Any) -> str:
    record = str(record_id or "").strip()
    if not portal_id or not record:
        return ""
    return (
        "https://app.hubspot.com/contacts/"
        f"{quote(portal_id, safe='')}/record/{object_type_id}/{quote(record, safe='')}"
    )


def _inverse(mapping: dict[str, list[str]] | None) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for source, targets in (mapping or {}).items():
        for target in targets:
            result.setdefault(str(target), []).append(str(source))
    return result


def _record_index(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("id")): row for row in rows if row.get("id") not in (None, "")}


def _property_labels(raw: Path) -> dict[tuple[str, str], str]:
    labels: dict[tuple[str, str], str] = {}
    for object_type in ("contacts", "companies", "deals"):
        for definition in read_json(raw / f"properties_{object_type}.json", []):
            if not isinstance(definition, dict) or not definition.get("name"):
                continue
            name = str(definition["name"])
            labels[(object_type, name)] = _safe_label(definition.get("label"), name)
    return labels


def _pipeline_labels(raw: Path) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    pipelines: dict[str, str] = {}
    stages: dict[tuple[str, str], str] = {}
    for pipeline in read_json(raw / "pipelines.json", []):
        if not isinstance(pipeline, dict) or pipeline.get("id") in (None, ""):
            continue
        pipeline_id = str(pipeline["id"])
        pipelines[pipeline_id] = _safe_label(pipeline.get("label"), pipeline_id)
        for stage in pipeline.get("stages") or []:
            if not isinstance(stage, dict) or stage.get("id") in (None, ""):
                continue
            stage_id = str(stage["id"])
            stages[(pipeline_id, stage_id)] = _safe_label(stage.get("label"), stage_id)
    return pipelines, stages


def build_report_record_evidence(
    run_dir: Path,
    findings: Iterable[Any],
) -> tuple[list[dict[str, str]], dict[tuple[str, str], str]]:
    run_dir = Path(run_dir)
    raw = run_dir / "raw"
    output = run_dir / "report_record_evidence.csv"
    property_labels = _property_labels(raw)
    pipeline_labels, stage_labels = _pipeline_labels(raw)
    identity = report_identity(run_dir)
    portal_id = identity.get("portal_id")

    salt_path = raw / "run_salt.txt"
    evidence_path = run_dir / "evidence.csv"
    if not salt_path.exists() or not evidence_path.exists():
        with output.open("w", encoding="utf-8", newline="") as fh:
            csv.DictWriter(fh, fieldnames=REPORT_RECORD_COLUMNS, lineterminator="\n").writeheader()
        return [], property_labels

    salt = salt_path.read_text(encoding="utf-8").strip()
    records = {
        object_type: _record_index(read_jsonl(raw / f"{object_type}.jsonl"))
        for object_type in ("contacts", "companies", "deals")
        if (raw / f"{object_type}.jsonl").exists()
    }
    hash_index: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
    for object_type, rows in records.items():
        for record_id, record in rows.items():
            hash_index[(object_type, hash_record_id(object_type, record_id, salt))] = (
                record_id,
                record,
            )

    contact_companies = load_association_map(raw, "associations_contact_company.jsonl") or {}
    deal_companies = load_association_map(raw, "associations_deal_company.jsonl") or {}
    deal_contacts = load_association_map(raw, "associations_deal_contact.jsonl") or {}
    contact_deals = _inverse(deal_contacts)
    company_deals = _inverse(deal_companies)

    finding_map = {
        str(getattr(finding, "measurement_id", "")): str(getattr(finding, "id", ""))
        for finding in findings
        if getattr(finding, "measurement_id", None)
    }
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    with evidence_path.open(encoding="utf-8", newline="") as fh:
        for evidence in csv.DictReader(fh):
            measurement_id = str(evidence.get("finding_id") or "")
            finding_id = finding_map.get(measurement_id)
            object_type = str(evidence.get("object_type") or "")
            record_hash = str(evidence.get("record_id_hash") or "")
            indexed = hash_index.get((object_type, record_hash))
            if not finding_id or not indexed:
                continue
            record_id, record = indexed
            company_id = ""
            deal_id = ""
            if object_type == "companies":
                company_id = record_id
                deal_id = (company_deals.get(record_id) or [""])[0]
            elif object_type == "deals":
                deal_id = record_id
                company_id = (deal_companies.get(record_id) or [""])[0]
            elif object_type == "contacts":
                company_id = (contact_companies.get(record_id) or [""])[0]
                deal_id = (contact_deals.get(record_id) or [""])[0]

            company = records.get("companies", {}).get(company_id, {})
            deal = records.get("deals", {}).get(deal_id, {})
            company_props = company.get("properties") or {}
            deal_props = deal.get("properties") or {}
            company_name = (
                _safe_label(company_props.get("name"), "Unnamed Company") if company else ""
            )
            deal_name = _safe_label(deal_props.get("dealname"), "Unnamed Deal") if deal else ""
            pipeline_id = str(deal_props.get("pipeline") or "")
            stage_id = str(deal_props.get("dealstage") or "")
            row = {
                    "finding_id": finding_id,
                    "measurement_id": measurement_id,
                    "object_type": object_type,
                    "record_id_hash": record_hash,
                    "company_name": company_name,
                    "company_url": _record_url(portal_id, "0-2", company_id),
                    "deal_name": deal_name,
                    "deal_url": _record_url(portal_id, "0-3", deal_id),
                    "pipeline_label": pipeline_labels.get(pipeline_id, _safe_label(pipeline_id, "")) if deal else "",
                    "deal_stage_label": stage_labels.get(
                        (pipeline_id, stage_id), _safe_label(stage_id, "")
                    ) if deal else "",
                }
            key = (
                finding_id,
                record_hash,
                row["company_name"],
                row["deal_name"],
            )
            if key not in seen:
                seen.add(key)
                rows.append(row)

    rows.sort(
        key=lambda row: (
            row["finding_id"],
            row["company_name"],
            row["deal_name"],
            row["record_id_hash"],
        )
    )

    with output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REPORT_RECORD_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {column: _csv_safe(row.get(column, "")) for column in REPORT_RECORD_COLUMNS}
            )
    return rows, property_labels
