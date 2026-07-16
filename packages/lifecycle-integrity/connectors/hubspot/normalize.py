"""Local snapshot writers: JSONL streams and JSON documents."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonlWriter:
    """Streaming JSONL writer that counts rows."""

    def __init__(
        self, path: Path, *, append: bool = False, initial_count: int = 0
    ) -> None:
        self.path = Path(path)
        self.append = append
        self.count = initial_count
        self._fh = None

    def __enter__(self) -> "JsonlWriter":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a" if self.append else "w", encoding="utf-8")
        return self

    def write(self, obj: dict[str, Any]) -> None:
        assert self._fh is not None, "JsonlWriter used outside context manager"
        self._fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.count += 1

    def flush(self) -> int:
        """Flush and return a text-stream position for checkpointing."""
        assert self._fh is not None, "JsonlWriter used outside context manager"
        self._fh.flush()
        return self._fh.tell()

    def __exit__(self, *exc: object) -> None:
        if self._fh is not None:
            self._fh.close()


def write_json(path: Path, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
