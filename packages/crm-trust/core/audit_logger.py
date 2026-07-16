"""Audit log for every run. Contains no secrets — enforced at write time."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .safety import TOKEN_PATTERNS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditLog:
    def __init__(self, run_config: dict[str, Any] | None = None) -> None:
        self.started_at = _now()
        self.run_config = run_config or {}
        self.events: list[dict[str, Any]] = []
        self.warnings: list[str] = []

    def event(self, name: str, **details: Any) -> None:
        self.events.append({"event": name, "at": _now(), **details})

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        self.events.append({"event": "warning", "at": _now(), "message": message})

    def write(self, path: Path) -> None:
        doc = {
            "started_at": self.started_at,
            "finished_at": _now(),
            "run_config": self.run_config,
            "events": self.events,
            "warnings": self.warnings,
        }
        text = json.dumps(doc, ensure_ascii=False, indent=2)
        # Hard guarantee: a token can never be written into the audit log.
        for pattern in TOKEN_PATTERNS:
            if pattern.search(text):
                raise RuntimeError(
                    "Refusing to write audit log: content matches an API "
                    "token pattern. This is a bug — report it."
                )
        Path(path).write_text(text, encoding="utf-8")
