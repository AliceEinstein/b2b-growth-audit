"""Association fetch via the v4 batch read API (a read API that uses POST)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .client import HubSpotClient
from .normalize import JsonlWriter

BATCH_SIZE = 500


def _checkpoint_path(out_path: Path) -> Path:
    return Path(out_path).parent / ".checkpoints" / f"{Path(out_path).stem}.json"


def _read_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid association checkpoint: {path}")
    return data


def _write_checkpoint(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _ids_fingerprint(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def fetch(
    client: HubSpotClient,
    from_type: str,
    to_type: str,
    from_ids: list[str],
    out_path: Path,
    *,
    resume: bool = False,
) -> dict[str, Any]:
    """Fetch associations for the given source ids into a JSONL snapshot.

    Rows: {"from_id": "...", "to_ids": ["...", ...]}
    Source records with no associations simply don't appear in results;
    downstream profiling computes coverage against the full id list.
    """
    out_path = Path(out_path)
    checkpoint = _checkpoint_path(out_path)
    state = _read_checkpoint(checkpoint) if resume else None
    ids_fingerprint = _ids_fingerprint(from_ids)
    if resume and state is None:
        raise ValueError("cannot resume associations: checkpoint is missing")
    if state is not None:
        if (
            state.get("from_type") != from_type
            or state.get("to_type") != to_type
            or state.get("ids_fingerprint") != ids_fingerprint
        ):
            raise ValueError("association checkpoint does not match the requested ids")
        if state.get("status") == "completed":
            if not out_path.exists():
                raise ValueError(
                    f"completed association checkpoint has no snapshot file: {out_path}"
                )
            return {
                "rows": int(state.get("rows", 0)),
                "from_total": len(from_ids),
                "resumed": True,
            }
        with out_path.open("r+", encoding="utf-8") as fh:
            fh.seek(int(state.get("file_offset", 0)))
            fh.truncate()

    initial_index = int(state.get("next_index", 0)) if state else 0
    initial_rows = int(state.get("rows", 0)) if state else 0
    with JsonlWriter(
        out_path, append=state is not None, initial_count=initial_rows
    ) as writer:
        last_state = {
            "from_type": from_type,
            "to_type": to_type,
            "ids_fingerprint": ids_fingerprint,
            "next_index": initial_index,
            "rows": writer.count,
            "file_offset": int(state.get("file_offset", 0)) if state else 0,
            "status": "in_progress",
        }
        _write_checkpoint(checkpoint, last_state)
        try:
            for start in range(initial_index, len(from_ids), BATCH_SIZE):
                chunk = from_ids[start : start + BATCH_SIZE]
                data = client.post(
                    f"/crm/v4/associations/{from_type}/{to_type}/batch/read",
                    json={"inputs": [{"id": i} for i in chunk]},
                )
                for result in data.get("results", []):
                    writer.write(
                        {
                            "from_id": str((result.get("from") or {}).get("id")),
                            "to_ids": [
                                str(t.get("toObjectId"))
                                for t in result.get("to", [])
                            ],
                        }
                    )
                file_offset = writer.flush()
                last_state = {
                    "from_type": from_type,
                    "to_type": to_type,
                    "ids_fingerprint": ids_fingerprint,
                    "next_index": start + len(chunk),
                    "rows": writer.count,
                    "file_offset": file_offset,
                    "status": "completed"
                    if start + len(chunk) >= len(from_ids)
                    else "in_progress",
                }
                _write_checkpoint(checkpoint, last_state)
            if not from_ids:
                last_state["status"] = "completed"
                _write_checkpoint(checkpoint, last_state)
        except Exception:
            last_state["status"] = "failed"
            _write_checkpoint(checkpoint, last_state)
            raise
    return {"rows": writer.count, "from_total": len(from_ids), "resumed": state is not None}
