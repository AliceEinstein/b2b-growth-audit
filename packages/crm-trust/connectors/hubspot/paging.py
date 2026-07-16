"""Shared pagination for CRM object fetches.

Two modes:
- list mode  (GET /crm/v3/objects/{type})        — full history
- search mode (POST /crm/v3/objects/{type}/search) — date-windowed (--days N)

HubSpot's search API hard-caps results at 10,000 per query; we stop
proactively and mark the snapshot as truncated so downstream findings can be
flagged accordingly.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Iterator

from .client import HubSpotClient
from .normalize import JsonlWriter

LIST_PAGE_LIMIT = 100
SEARCH_PAGE_LIMIT = 100
SEARCH_HARD_CAP = 10_000
CHECKPOINT_DIR = ".checkpoints"


def _checkpoint_path(out_path: Path) -> Path:
    return Path(out_path).parent / CHECKPOINT_DIR / f"{Path(out_path).stem}.json"


def _read_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid pagination checkpoint: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"invalid pagination checkpoint: {path}")
    return data


def _write_checkpoint(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _truncate_to_checkpoint(path: Path, offset: int) -> None:
    if not path.exists():
        if offset:
            raise ValueError(f"snapshot file missing for checkpoint resume: {path}")
        return
    with path.open("r+", encoding="utf-8") as fh:
        fh.seek(offset)
        fh.truncate()


def _read_snapshot_ids(
    path: Path, expected_count: int
) -> tuple[list[str], str]:
    """Rebuild ids once from the flushed JSONL prefix, not per checkpoint."""
    if not path.exists():
        if expected_count == 0:
            return [], hashlib.sha256().hexdigest()
        raise ValueError(f"snapshot file missing for checkpoint resume: {path}")
    ids: list[str] = []
    digest = hashlib.sha256()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            record = json.loads(line)
            record_id = str(record.get("id"))
            ids.append(record_id)
            digest.update((record_id + "\n").encode("utf-8"))
    if len(ids) != expected_count:
        raise ValueError(
            f"checkpoint count does not match snapshot file: expected "
            f"{expected_count}, found {len(ids)}"
        )
    return ids, digest.hexdigest()


def _legacy_checkpoint_ids(state: dict[str, Any]) -> list[str] | None:
    """Read the pre-optimization id list for one safe migration step."""
    ids = state.get("ids")
    if not isinstance(ids, list):
        return None
    return [str(i) for i in ids]


def _page_state(
    *,
    object_type: str,
    mode: str,
    days: int | None,
    cutoff_ms: int | None,
    properties: list[str],
    after: str | None,
    count: int,
    ids_digest: str,
    last_id: str | None,
    file_offset: int,
    status: str,
    truncated: bool = False,
) -> dict[str, Any]:
    return {
        "object_type": object_type,
        "mode": mode,
        "days": days,
        "cutoff_ms": cutoff_ms,
        "properties": properties,
        "after": after,
        "count": count,
        "id_count": count,
        "ids_digest": ids_digest,
        "last_id": last_id,
        "file_offset": file_offset,
        "status": status,
        "truncated": truncated,
    }


def _validate_checkpoint(
    state: dict[str, Any], object_type: str, properties: list[str], days: int | None
) -> None:
    expected_mode = "full_history" if days is None else "search"
    if state.get("object_type") != object_type or state.get("mode") != expected_mode:
        raise ValueError("checkpoint does not match object type or snapshot mode")
    if state.get("properties") != properties or state.get("days") != days:
        raise ValueError(
            f"checkpoint for {object_type} does not match the requested properties/window"
        )


def fetch_object_records(
    client: HubSpotClient,
    object_type: str,
    default_properties: list[str],
    out_path: Path,
    *,
    days: int | None = None,
    extra_properties: tuple[str, ...] | list[str] = (),
    log: Any = None,
    resume: bool = False,
) -> dict[str, Any]:
    """Fetch records to a local JSONL snapshot. Returns a summary dict."""
    properties = list(dict.fromkeys([*default_properties, *extra_properties]))
    out_path = Path(out_path)
    checkpoint = _checkpoint_path(out_path)
    state = _read_checkpoint(checkpoint) if resume else None
    if resume and state is None:
        raise ValueError(f"cannot resume {object_type}: checkpoint is missing")
    if state is not None:
        _validate_checkpoint(state, object_type, properties, days)
        if state.get("status") == "completed":
            if not out_path.exists():
                raise ValueError(f"completed checkpoint has no snapshot file: {out_path}")
            legacy_ids = _legacy_checkpoint_ids(state)
            ids = (
                legacy_ids
                if legacy_ids is not None
                else _read_snapshot_ids(out_path, int(state.get("count", 0)))[0]
            )
            return {
                "object_type": object_type,
                "count": int(state.get("count", 0)),
                "ids": ids,
                "truncated": bool(state.get("truncated", False)),
                "properties": properties,
                "resumed": True,
            }

    cutoff_ms = (
        int(state["cutoff_ms"])
        if state is not None and state.get("cutoff_ms") is not None
        else int((time.time() - days * 86_400) * 1000) if days is not None else None
    )
    initial_count = int(state.get("count", 0)) if state else 0
    start_after = state.get("after") if state else None
    initial_offset = int(state.get("file_offset", 0)) if state else 0
    if state is not None:
        _truncate_to_checkpoint(out_path, initial_offset)

    legacy_ids = _legacy_checkpoint_ids(state) if state else None
    if legacy_ids is not None:
        ids = legacy_ids
        id_digest = hashlib.sha256()
        for record_id in ids:
            id_digest.update((record_id + "\n").encode("utf-8"))
        if len(ids) != initial_count:
            raise ValueError("legacy checkpoint ids do not match its record count")
    else:
        ids, digest = (
            _read_snapshot_ids(out_path, initial_count)
            if state
            else ([], hashlib.sha256().hexdigest())
        )
        id_digest = hashlib.sha256()
        if ids:
            for record_id in ids:
                id_digest.update((record_id + "\n").encode("utf-8"))
        if state is not None and state.get("ids_digest") not in (None, digest):
            raise ValueError("checkpoint id digest does not match the snapshot file")

    mode = "full_history" if days is None else "search"
    truncated = False
    with JsonlWriter(
        out_path,
        append=state is not None,
        initial_count=initial_count,
    ) as writer:
        last_state = _page_state(
            object_type=object_type,
            mode=mode,
            days=days,
            cutoff_ms=cutoff_ms,
            properties=properties,
            after=start_after,
            count=writer.count,
            ids_digest=id_digest.hexdigest(),
            last_id=ids[-1] if ids else None,
            file_offset=initial_offset,
            status="in_progress",
        )
        _write_checkpoint(checkpoint, last_state)
        try:
            pages = (
                _iter_list_pages(client, object_type, properties, start_after)
                if days is None
                else _iter_search_pages(
                    client, object_type, properties, cutoff_ms, start_after
                )
            )
            saw_page = False
            for records, next_after in pages:
                saw_page = True
                for rec in records:
                    writer.write(rec)
                    record_id = str(rec.get("id"))
                    ids.append(record_id)
                    id_digest.update((record_id + "\n").encode("utf-8"))
                file_offset = writer.flush()
                truncated = (
                    days is not None
                    and next_after is not None
                    and writer.count >= SEARCH_HARD_CAP
                )
                last_state = _page_state(
                    object_type=object_type,
                    mode=mode,
                    days=days,
                    cutoff_ms=cutoff_ms,
                    properties=properties,
                    after=next_after,
                    count=writer.count,
                    ids_digest=id_digest.hexdigest(),
                    last_id=ids[-1] if ids else None,
                    file_offset=file_offset,
                    status="completed" if truncated or next_after is None else "in_progress",
                    truncated=truncated,
                )
                _write_checkpoint(checkpoint, last_state)
                if truncated:
                    if log is not None:
                        log.warn(
                            f"{object_type}: hit HubSpot search 10k cap; snapshot is "
                            "truncated and prioritizes newest records. Use full-history "
                            "or a shorter --days window for complete window coverage."
                        )
                    break
            if not saw_page:
                last_state["status"] = "completed"
                _write_checkpoint(checkpoint, last_state)
        except Exception:
            failed_state = dict(last_state)
            failed_state["status"] = "failed"
            _write_checkpoint(checkpoint, failed_state)
            raise

    return {
        "object_type": object_type,
        "count": writer.count,
            "ids": ids,
        "truncated": truncated,
        "properties": properties,
        "resumed": state is not None,
    }


def _iter_list_pages(
    client: HubSpotClient,
    object_type: str,
    properties: list[str],
    after: str | None = None,
) -> Iterator[tuple[list[dict[str, Any]], str | None]]:
    while True:
        params: dict[str, Any] = {
            "limit": LIST_PAGE_LIMIT,
            "properties": ",".join(properties),
            "archived": "false",
        }
        if after:
            params["after"] = after
        data = client.get(f"/crm/v3/objects/{object_type}", params=params)
        next_after = ((data.get("paging") or {}).get("next") or {}).get("after")
        yield data.get("results", []), next_after
        if not next_after:
            return
        after = next_after


def _iter_search_pages(
    client: HubSpotClient,
    object_type: str,
    properties: list[str],
    cutoff_ms: int,
    after: str | None = None,
) -> Iterator[tuple[list[dict[str, Any]], str | None]]:
    while True:
        payload: dict[str, Any] = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "createdate",
                            "operator": "GTE",
                            "value": str(cutoff_ms),
                        }
                    ]
                }
            ],
            # If a caller explicitly chooses a window that exceeds Search's
            # hard cap, retain the newest records first. Older records are
            # still marked as omitted through the truncated manifest flag.
            "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
            "properties": properties,
            "limit": SEARCH_PAGE_LIMIT,
        }
        if after:
            payload["after"] = after
        data = client.post(f"/crm/v3/objects/{object_type}/search", json=payload)
        next_after = ((data.get("paging") or {}).get("next") or {}).get("after")
        yield data.get("results", []), next_after
        if not next_after:
            return
        after = next_after
