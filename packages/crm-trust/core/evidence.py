"""Evidence CSV writer. Hashed record ids only — never raw ids or PII."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

EVIDENCE_COLUMNS = [
    "finding_id",
    "object_type",
    "record_id_hash",
    "field_name",
    "issue_type",
    "current_value_redacted",
    "confidence",
    "recommended_review",
]


class ModuleEvidence:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.count = 0
        self._fh = None
        self._writer = None

    def __enter__(self) -> "ModuleEvidence":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8", newline="")
        self._writer = csv.writer(self._fh, lineterminator="\n")
        self._writer.writerow(EVIDENCE_COLUMNS)
        return self

    def add(
        self,
        finding_id: str,
        object_type: str,
        record_id_hash: str,
        field_name: Optional[str],
        issue_type: str,
        current_value_redacted: Optional[str],
        recommended_review: str,
        confidence: str = "high",
    ) -> None:
        assert self._writer is not None
        self._writer.writerow(
            [
                finding_id,
                object_type,
                record_id_hash,
                field_name or "",
                issue_type,
                current_value_redacted or "",
                confidence,
                recommended_review,
            ]
        )
        self.count += 1

    def __exit__(self, *exc: object) -> None:
        if self._fh is not None:
            self._fh.close()
