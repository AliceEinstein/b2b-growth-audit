"""Shared deterministic helpers: I/O, parsing, percentages, stage semantics.

Used by both the profiler and the audit measurement layer. Facts only.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_json(path: Path, default: Any) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def parse_ms(value: Any) -> Optional[float]:
    """Parse a HubSpot date value (epoch-ms string or ISO 8601) to epoch ms."""
    if value is None:
        return None
    text = str(value)
    if text.isdigit():
        return float(text)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000
    except ValueError:
        return None


def parse_created_ms(record: Dict[str, Any]) -> Optional[float]:
    raw = (record.get("properties") or {}).get("createdate") or record.get("createdAt")
    return parse_ms(raw)


def pct(part: int, whole: int) -> Optional[float]:
    if not whole:
        return None
    return round(part / whole * 100, 1)


def median_created_ms(
    records: List[Dict[str, Any]], min_dated: int = 4
) -> Optional[float]:
    dated = [ms for ms in (parse_created_ms(r) for r in records) if ms is not None]
    if len(dated) < min_dated:
        return None
    return statistics.median(dated)


def stage_flags(
    pipelines: List[Dict[str, Any]],
) -> Dict[tuple[str, str], Dict[str, bool]]:
    """Per-(pipeline, stage) {closed, won} facts from definitions.

    Uses stage metadata (isClosed / probability) when HubSpot provides it;
    falls back to the conventional closedwon/closedlost stage ids otherwise.
    """
    flags: Dict[tuple[str, str], Dict[str, bool]] = {}
    for pipeline in pipelines:
        pipeline_id = str(pipeline.get("id"))
        for stage in pipeline.get("stages", []):
            stage_id = str(stage.get("id"))
            metadata = stage.get("metadata") or {}
            if metadata:
                closed = str(metadata.get("isClosed", "")).lower() == "true"
                try:
                    probability = (
                        float(metadata["probability"])
                        if metadata.get("probability") is not None
                        else None
                    )
                except (TypeError, ValueError):
                    probability = None
                # Some portals expose isClosed but omit probability. The
                # conventional stage id is then the safest available won
                # signal. When probability is present, metadata wins.
                won = (
                    closed and probability == 1.0
                    if probability is not None
                    else closed and stage_id.lower() == "closedwon"
                )
            else:
                closed = stage_id in {"closedwon", "closedlost"}
                won = stage_id == "closedwon"
            flags[(pipeline_id, stage_id)] = {"closed": closed, "won": won}
    return flags


def load_association_map(
    raw_dir: Path, filename: str
) -> Optional[Dict[str, List[str]]]:
    """from_id -> to_ids, or None when the snapshot lacks this association."""
    path = Path(raw_dir) / filename
    if not path.exists():
        return None
    return {row["from_id"]: row.get("to_ids", []) for row in read_jsonl(path)}
