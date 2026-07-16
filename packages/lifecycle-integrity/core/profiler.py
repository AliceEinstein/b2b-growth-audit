"""Deterministic profiling of a raw snapshot.

Produces the sanitized measurement artifacts that ALL LLM judgment roles
read. Measurements only — no thresholds, no severity, no conclusions.
A field's "usage decay" here is two fill rates side by side; whether that
decay is a problem is the schema discovery agent's judgment.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from connectors.hubspot.fetch_properties import SOURCE_CANDIDATE_PATTERN
from connectors.hubspot.normalize import write_json

from .metrics import (
    is_empty,
    median_created_ms,
    parse_ms,
    parse_created_ms,
    pct,
    read_json,
    read_jsonl,
)
from .sanitizer import (
    hash_record_id,
    load_or_create_salt,
    sanitize_untrusted_value,
)
from .safety import EMAIL_PATTERN, PHONE_PATTERN
from .validators import validate_snapshot_completed

OBJECT_FILES = {
    "contacts": "contacts.jsonl",
    "companies": "companies.jsonl",
    "deals": "deals.jsonl",
}

ASSOCIATION_SPECS = [
    ("contacts", "companies", "associations_contact_company.jsonl"),
    ("deals", "companies", "associations_deal_company.jsonl"),
    ("deals", "contacts", "associations_deal_contact.jsonl"),
]

# HubSpot-defined fields that are always source-relevant even though their
# names don't match the candidate regex.
KNOWN_SOURCE_FIELDS = {
    "contacts": ["hs_analytics_source", "hs_latest_source", "hs_object_source"],
    "companies": ["hs_object_source"],
    "deals": ["hs_object_source"],
}

ACTIVITY_FIELDS = {
    "contacts": "lastmodifieddate",
    "companies": "hs_lastmodifieddate",
    "deals": "hs_lastmodifieddate",
}

TOP_VALUE_MAX_DISTINCT = 25
TOP_VALUES_SHOWN = 10
SAMPLE_RECORDS = 5
IDENTITY_FIELDS = {
    "email",
    "hs_additional_emails",
    "firstname",
    "lastname",
    "phone",
    "mobilephone",
}
SENSITIVE_VALUE_FIELDS = {
    "domain",
    "hs_domain",
    "website",
    "dealname",
}
FREE_TEXT_FIELD_HINTS = (
    "note", "comment", "description", "message", "body", "text", "content",
    "name",
)

PROCESSED_FILES = [
    "object_counts.json",
    "property_usage_summary.json",
    "field_empty_rates.json",
    "association_summary.json",
    "pipeline_summary.json",
    "lifecycle_distribution.json",
    "source_field_candidates.json",
    "sanitized_samples.json",
    "identity_completeness.json",
    "data_age_summary.json",
]


def _observed_fields(records: List[Dict[str, Any]]) -> List[str]:
    fields: Dict[str, None] = {}
    for record in records:
        for key in (record.get("properties") or {}):
            fields.setdefault(key)
    return list(fields)


def _field_stats(
    records: List[Dict[str, Any]],
    field: str,
    median_ms: Optional[float],
) -> Dict[str, Any]:
    total = len(records)
    non_empty = 0
    older_total = older_filled = recent_total = recent_filled = 0
    values: Counter = Counter()

    for record in records:
        value = (record.get("properties") or {}).get(field)
        empty = is_empty(value)
        if not empty:
            non_empty += 1
            values[str(value)] += 1
        created = parse_created_ms(record)
        if created is not None and median_ms is not None:
            if created <= median_ms:
                older_total += 1
                older_filled += 0 if empty else 1
            else:
                recent_total += 1
                recent_filled += 0 if empty else 1

    top_values = None
    field_lower = field.lower()
    expose_values = (
        field not in IDENTITY_FIELDS
        and field_lower not in SENSITIVE_VALUE_FIELDS
        and not any(hint in field_lower for hint in FREE_TEXT_FIELD_HINTS)
    )
    if expose_values and 0 < len(values) <= TOP_VALUE_MAX_DISTINCT:
        top_values = [
            {"value": sanitize_untrusted_value(v), "count": c}
            for v, c in values.most_common(TOP_VALUES_SHOWN)
        ]

    return {
        "total": total,
        "non_empty": non_empty,
        "fill_rate": pct(non_empty, total),
        "empty_rate": pct(total - non_empty, total),
        "fill_rate_older_half": pct(older_filled, older_total),
        "fill_rate_recent_half": pct(recent_filled, recent_total),
        "distinct_count": len(values),
        "top_values": top_values,
    }


def _valid_identity_value(field: str, value: Any) -> bool:
    if is_empty(value):
        return False
    text = str(value).strip()
    if field == "email":
        return bool(re.fullmatch(EMAIL_PATTERN.pattern, text))
    if field == "phone":
        match = PHONE_PATTERN.search(text)
        return bool(match and len(re.sub(r"\D", "", match.group())) >= 7)
    return True


def _identity_completeness(
    records: List[Dict[str, Any]], prop_defs: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Count contact identity coverage without emitting identity values."""
    definitions = {str(item.get("name")) for item in prop_defs}
    observed = _observed_fields(records)
    fields: Dict[str, Any] = {}
    for field in sorted(IDENTITY_FIELDS):
        present = sum(
            1 for record in records if not is_empty((record.get("properties") or {}).get(field))
        )
        valid = sum(
            1
            for record in records
            if _valid_identity_value(field, (record.get("properties") or {}).get(field))
        )
        fields[field] = {
            "property_exists": field in definitions,
            "observed_in_snapshot": field in observed,
            "total": len(records),
            "present": present,
            "missing": len(records) - present,
            "fill_rate": pct(present, len(records)),
            "valid_format": valid,
            "invalid_format": present - valid,
            "valid_format_rate_among_present": pct(valid, present),
        }
    return {
        "object_type": "contacts",
        "record_count": len(records),
        "fields": fields,
        "raw_values_in_artifact": False,
    }


def _iso_from_ms(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def _date_range(records: List[Dict[str, Any]], field: str) -> Dict[str, Any]:
    values = [
        parsed
        for parsed in (
            parse_ms((record.get("properties") or {}).get(field))
            for record in records
        )
        if parsed is not None
    ]
    return {
        "available": bool(values),
        "oldest": _iso_from_ms(min(values)) if values else None,
        "newest": _iso_from_ms(max(values)) if values else None,
        "records_with_valid_timestamp": len(values),
        "records_missing_or_invalid": len(records) - len(values),
    }


def _data_age_summary(
    records_by_object: Dict[str, List[Dict[str, Any]]], manifest: Dict[str, Any]
) -> Dict[str, Any]:
    """Aggregate record freshness without treating it as human activity."""
    reference_ms = parse_ms(manifest.get("snapshot_completed_at"))
    reference_source = "manifest.snapshot_completed_at"
    if reference_ms is None:
        observed = []
        for object_type, records in records_by_object.items():
            field = ACTIVITY_FIELDS.get(object_type)
            observed.extend(
                parsed
                for parsed in (
                    parse_ms((record.get("properties") or {}).get(field))
                    for record in records
                )
                if field and parsed is not None
            )
        reference_ms = max(observed) if observed else None
        reference_source = "latest_observed_modified_timestamp"

    objects: Dict[str, Any] = {}
    for object_type, records in records_by_object.items():
        field = ACTIVITY_FIELDS.get(object_type)
        if field is None:
            continue
        valid: List[float] = []
        missing_or_invalid = 0
        future_dated = 0
        buckets = {
            "within_30_days": 0,
            "31_to_90_days": 0,
            "91_to_180_days": 0,
            "over_180_days": 0,
        }
        if reference_ms is not None:
            for record in records:
                parsed = parse_ms((record.get("properties") or {}).get(field))
                if parsed is None:
                    missing_or_invalid += 1
                    continue
                valid.append(parsed)
                age_days = (reference_ms - parsed) / 86_400_000
                if age_days < 0:
                    future_dated += 1
                elif age_days <= 30:
                    buckets["within_30_days"] += 1
                elif age_days <= 90:
                    buckets["31_to_90_days"] += 1
                elif age_days <= 180:
                    buckets["91_to_180_days"] += 1
                else:
                    buckets["over_180_days"] += 1
        else:
            missing_or_invalid = len(records)
        objects[object_type] = {
            "activity_field": field,
            "available": reference_ms is not None and bool(valid),
            "total": len(records),
            "with_valid_timestamp": len(valid),
            "missing_or_invalid": missing_or_invalid,
            "future_dated": future_dated,
            "recency_buckets": buckets,
            "last_modified_range": _date_range(records, field),
            "created_range": _date_range(records, "createdate"),
        }
    return {
        "reference_time": _iso_from_ms(reference_ms),
        "reference_time_source": reference_source,
        "definition": "Operational recency proxy based on last-modified timestamps; this is not proof of human, marketing, or sales activity.",
        "objects": objects,
    }


def profile_run(run_dir: Path) -> Dict[str, Any]:
    """Profile a snapshot run directory. Writes processed/*.json artifacts."""
    run_dir = Path(run_dir)
    problems = validate_snapshot_completed(run_dir)
    if problems:
        raise ValueError("cannot profile incomplete snapshot: " + problems[0])
    raw = run_dir / "raw"
    processed = run_dir / "processed"
    processed.mkdir(parents=True, exist_ok=True)

    salt = load_or_create_salt(run_dir)
    manifest = read_json(run_dir / "manifest.json", {})
    records = {
        obj: read_jsonl(raw / filename)
        for obj, filename in OBJECT_FILES.items()
        if (raw / filename).exists()
    }
    prop_defs = {
        obj: read_json(raw / f"properties_{obj}.json", []) for obj in OBJECT_FILES
    }
    owners = read_json(raw / "owners.json", [])
    pipelines = read_json(raw / "pipelines.json", [])

    # --- object_counts.json ---
    object_counts: Dict[str, Any] = {obj: len(recs) for obj, recs in records.items()}
    object_counts["owners"] = len(owners)
    object_counts["deal_pipelines"] = len(pipelines)
    object_counts["truncated"] = manifest.get("truncated", {})
    write_json(processed / "object_counts.json", object_counts)

    # --- property usage + empty rates ---
    usage: Dict[str, Dict[str, Any]] = {}
    empty_rates: Dict[str, Dict[str, Any]] = {}
    for obj, recs in records.items():
        median_ms = median_created_ms(recs)
        usage[obj] = {}
        empty_rates[obj] = {}
        for field in _observed_fields(recs):
            stats = _field_stats(recs, field, median_ms)
            usage[obj][field] = stats
            empty_rates[obj][field] = {
                "empty_rate": stats["empty_rate"],
                "total": stats["total"],
            }
    write_json(processed / "property_usage_summary.json", usage)
    write_json(processed / "field_empty_rates.json", empty_rates)

    # --- lifecycle_distribution.json ---
    lifecycle: Dict[str, Dict[str, int]] = {}
    for obj in ("contacts", "companies"):
        if obj not in records:
            continue
        counter: Counter = Counter()
        for record in records[obj]:
            value = (record.get("properties") or {}).get("lifecyclestage")
            counter[
                sanitize_untrusted_value(value) if not is_empty(value) else "(empty)"
            ] += 1
        lifecycle[obj] = dict(counter.most_common())
    write_json(processed / "lifecycle_distribution.json", lifecycle)

    # --- pipeline_summary.json ---
    deal_stage_counts: Counter = Counter()
    for record in records.get("deals", []):
        props = record.get("properties") or {}
        deal_stage_counts[(str(props.get("pipeline")), str(props.get("dealstage")))] += 1
    known_pipeline_ids = set()
    pipeline_entries = []
    for pipeline in pipelines:
        pipeline_id = str(pipeline.get("id"))
        known_pipeline_ids.add(pipeline_id)
        stages = []
        pipeline_total = 0
        for stage in pipeline.get("stages", []):
            stage_id = str(stage.get("id"))
            count = deal_stage_counts.get((pipeline_id, stage_id), 0)
            pipeline_total += count
            stages.append(
                {
                    "stage_id": stage_id,
                    "label": sanitize_untrusted_value(stage.get("label")),
                    "deal_count": count,
                }
            )
        pipeline_entries.append(
            {
                "pipeline_id": pipeline_id,
                "label": sanitize_untrusted_value(pipeline.get("label")),
                "stage_count": len(stages),
                "deal_count": pipeline_total,
                "stages": stages,
            }
        )
    unknown_deals = sum(
        count
        for (pipeline_id, _stage), count in deal_stage_counts.items()
        if pipeline_id not in known_pipeline_ids
    )
    write_json(
        processed / "pipeline_summary.json",
        {"pipelines": pipeline_entries, "deals_in_unknown_pipeline": unknown_deals},
    )

    # --- association_summary.json ---
    association_summary: Dict[str, Any] = {}
    for from_obj, to_obj, filename in ASSOCIATION_SPECS:
        key = f"{from_obj}_to_{to_obj}"
        path = raw / filename
        if not path.exists() or from_obj not in records:
            association_summary[key] = {"available": False}
            continue
        link_counts = {
            row["from_id"]: len(row.get("to_ids", [])) for row in read_jsonl(path)
        }
        universe = [str(r.get("id")) for r in records[from_obj]]
        with_zero = sum(1 for i in universe if link_counts.get(i, 0) == 0)
        with_one = sum(1 for i in universe if link_counts.get(i, 0) == 1)
        with_multi = sum(1 for i in universe if link_counts.get(i, 0) > 1)
        association_summary[key] = {
            "available": True,
            "total": len(universe),
            "with_association": with_one + with_multi,
            "coverage_pct": pct(with_one + with_multi, len(universe)),
            "distribution": {"0": with_zero, "1": with_one, "2+": with_multi},
        }
    write_json(processed / "association_summary.json", association_summary)

    # --- source_field_candidates.json ---
    candidates: Dict[str, List[Dict[str, Any]]] = {}
    for obj, recs in records.items():
        def_map = {d.get("name"): d for d in prop_defs.get(obj, [])}
        entries = []
        for field in _observed_fields(recs):
            if not (
                SOURCE_CANDIDATE_PATTERN.search(field)
                or field in KNOWN_SOURCE_FIELDS.get(obj, [])
            ):
                continue
            definition = def_map.get(field, {})
            entries.append(
                {
                    "field": field,
                    "label": sanitize_untrusted_value(definition.get("label")),
                    "hubspot_defined": bool(definition.get("hubspotDefined")),
                    "stats": usage[obj].get(field),
                }
            )
        candidates[obj] = entries
    write_json(processed / "source_field_candidates.json", candidates)

    # --- identity_completeness.json ---
    write_json(
        processed / "identity_completeness.json",
        _identity_completeness(records.get("contacts", []), prop_defs.get("contacts", [])),
    )

    # --- data_age_summary.json ---
    write_json(processed / "data_age_summary.json", _data_age_summary(records, manifest))

    # --- sanitized_samples.json ---
    # Samples communicate field presence and redaction behavior only. Raw CRM
    # values are unnecessary for downstream judgment and can carry identity or
    # commercially sensitive information even when they are not an email or
    # phone number.
    def sample_value(object_type: str, field: str, value: Any) -> str:
        if is_empty(value):
            return "[MISSING]"
        if (
            field in IDENTITY_FIELDS
            or field.lower() in SENSITIVE_VALUE_FIELDS
            or (object_type == "companies" and field in {"name", "domain"})
            or (object_type == "deals" and field == "dealname")
        ):
            return "[PRESENT]"
        sanitized = sanitize_untrusted_value(value)
        if sanitized and sanitized.startswith("[REDACTED:"):
            return sanitized
        return "[PRESENT]"

    samples: Dict[str, List[Dict[str, Any]]] = {}
    for obj, recs in records.items():
        samples[obj] = [
            {
                "record_id_hash": hash_record_id(obj, record.get("id"), salt),
                "properties": {
                    key: sample_value(obj, key, value)
                    for key, value in (record.get("properties") or {}).items()
                },
            }
            for record in recs[:SAMPLE_RECORDS]
        ]
    write_json(processed / "sanitized_samples.json", samples)

    return {"processed_dir": str(processed), "files": list(PROCESSED_FILES)}
