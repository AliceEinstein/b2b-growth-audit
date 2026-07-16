"""Persistent state and content hashes for the BYO Agent workflow."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from core.integrity import sha256_file
from core.validators import validate_snapshot_completed

from .workflow import STAGES, StageSpec, get_stage

TERMINAL_OK = {"passed", "skipped"}
STATUSES = {"pending", "ready", "running", "passed", "failed", "skipped"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_path(run_dir: Path) -> Path:
    return Path(run_dir) / "harness" / "run_state.json"


def task_dir(run_dir: Path) -> Path:
    return Path(run_dir) / "harness" / "tasks"


def _safe_run_path(run_dir: Path, relative: str) -> Path:
    root = Path(run_dir).resolve()
    path = (root / relative).resolve()
    if root != path and root not in path.parents:
        raise ValueError("path escapes run directory: " + relative)
    if "raw" in path.relative_to(root).parts:
        raise ValueError("raw snapshot is never an allowed harness input")
    return path


def expand_input_patterns(run_dir: Path, patterns: Iterable[str]) -> List[str]:
    """Expand run-relative patterns into safe, sorted relative paths.

    Missing files are represented by the pattern itself so an input hash
    changes when a required artifact appears later.  Raw paths are rejected
    even if a future role specification accidentally includes one.
    """
    run_dir = Path(run_dir)
    found: List[str] = []
    for pattern in patterns:
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise ValueError("harness input patterns must stay inside run dir")
        if pattern.startswith("raw/") or pattern == "raw":
            raise ValueError("raw snapshot is never an allowed harness input")
        matches = sorted(run_dir.glob(pattern))
        if matches:
            for match in matches:
                relative = match.relative_to(run_dir).as_posix()
                _safe_run_path(run_dir, relative)
                if match.is_file():
                    found.append(relative)
        else:
            found.append("<missing>" + pattern)
    return sorted(set(found))


def content_hash(run_dir: Path, relative_paths: Iterable[str]) -> str:
    """Hash path names and bytes without storing CRM content in state."""
    digest = hashlib.sha256()
    root = Path(run_dir)
    for relative in sorted(relative_paths):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if relative.startswith("<missing>"):
            continue
        path = _safe_run_path(root, relative)
        if not path.is_file():
            digest.update(b"<missing>")
            continue
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def _findings_content_hash(run_dir: Path, relative_paths: Iterable[str]) -> str:
    """Hash findings while excluding the code-owned review_status field."""
    digest = hashlib.sha256()
    root = Path(run_dir)
    for relative in sorted(relative_paths):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if relative.startswith("<missing>"):
            continue
        path = _safe_run_path(root, relative)
        if path.suffix == ".json" and "findings" in path.parts:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for finding in data.get("findings", []):
                        if isinstance(finding, dict):
                            finding.pop("review_status", None)
                digest.update(json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8"))
                continue
            except (OSError, json.JSONDecodeError):
                pass
        if path.is_file():
            digest.update(bytes.fromhex(sha256_file(path)))
        else:
            digest.update(b"<missing>")
    return digest.hexdigest()


def stage_input_hash(run_dir: Path, stage: StageSpec) -> str:
    paths = expand_input_patterns(run_dir, stage.input_patterns)
    # Review agents consume finding content, but the deterministic review
    # aggregation later changes only each finding's review_status. That status
    # is the output of the review stage, not an input to it; ignoring it here
    # prevents a completed review from invalidating itself on the next resume.
    if stage.id.startswith("review_") or stage.id == "findings_validation":
        return _findings_content_hash(run_dir, paths)
    return content_hash(run_dir, paths)


def stage_output_hash(run_dir: Path, stage: StageSpec) -> str:
    paths: List[str] = []
    for relative in stage.output_paths:
        path = _safe_run_path(run_dir, relative)
        paths.append(relative if path.is_file() else "<missing>" + relative)
    if stage.id.startswith("audit_"):
        return _findings_content_hash(run_dir, paths)
    return content_hash(run_dir, paths)


@dataclass
class StageState:
    status: str = "pending"
    attempts: int = 0
    input_hash: Optional[str] = None
    output_hash: Optional[str] = None
    last_error: Optional[str] = None
    task_file: Optional[str] = None
    updated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError("unknown stage status: " + self.status)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "attempts": self.attempts,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "last_error": self.last_error,
            "task_file": self.task_file,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StageState":
        return cls(
            status=str(data.get("status", "pending")),
            attempts=int(data.get("attempts", 0)),
            input_hash=data.get("input_hash"),
            output_hash=data.get("output_hash"),
            last_error=data.get("last_error"),
            task_file=data.get("task_file"),
            updated_at=str(data.get("updated_at", utc_now())),
        )


@dataclass
class RunState:
    run_id: str
    mode: str = "byo_agent"
    version: int = 1
    created_at: str = field(default_factory=utc_now)
    stages: Dict[str, StageState] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls, run_dir: Path) -> "RunState":
        path = state_path(run_dir)
        data = json.loads(path.read_text(encoding="utf-8"))
        stages = {
            name: StageState.from_dict(value)
            for name, value in dict(data.get("stages", {})).items()
        }
        for spec in STAGES:
            stages.setdefault(spec.id, StageState())
        return cls(
            run_id=str(data["run_id"]),
            mode=str(data.get("mode", "byo_agent")),
            version=int(data.get("version", 1)),
            created_at=str(data.get("created_at", utc_now())),
            stages=stages,
            history=list(data.get("history", [])),
        )

    @classmethod
    def initialize(cls, run_dir: Path) -> "RunState":
        run_dir = Path(run_dir)
        run_id = run_dir.name
        stages = {spec.id: StageState() for spec in STAGES}
        snapshot_problems = validate_snapshot_completed(run_dir)
        stages["snapshot"] = StageState(
            status="passed" if not snapshot_problems else "failed",
            input_hash=stage_input_hash(run_dir, get_stage("snapshot")),
            output_hash=stage_output_hash(run_dir, get_stage("snapshot")),
            last_error="; ".join(snapshot_problems) if snapshot_problems else None,
        )
        return cls(run_id=run_id, stages=stages)

    @classmethod
    def load_or_initialize(cls, run_dir: Path) -> "RunState":
        path = state_path(run_dir)
        if path.exists():
            return cls.load(run_dir)
        state = cls.initialize(run_dir)
        state.save(run_dir)
        return state

    def save(self, run_dir: Path) -> None:
        path = state_path(run_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": self.version,
            "mode": self.mode,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "stages": {name: state.as_dict() for name, state in self.stages.items()},
            "history": self.history[-100:],
        }
        fd, temp_name = tempfile.mkstemp(prefix="run_state.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def stage(self, stage_id: str) -> StageState:
        get_stage(stage_id)
        return self.stages[stage_id]

    def record(self, stage_id: str, status: str, **extra: Any) -> None:
        if status not in STATUSES:
            raise ValueError("unknown stage status: " + status)
        current = self.stage(stage_id)
        current.status = status
        current.updated_at = utc_now()
        for key, value in extra.items():
            if not hasattr(current, key):
                raise AttributeError("unknown stage state field: " + key)
            setattr(current, key, value)
        self.history.append({
            "stage": stage_id,
            "status": status,
            "at": current.updated_at,
            **{key: value for key, value in extra.items() if key != "last_error"},
        })

    def dependencies_satisfied(self, stage: StageSpec) -> bool:
        return all(self.stage(dep).status in TERMINAL_OK for dep in stage.dependencies)

    def invalidate_from(self, run_dir: Path, stage_id: str) -> None:
        """Invalidate a stage and every downstream stage without deleting data."""
        pending = [stage_id]
        seen = set()
        while pending:
            current = pending.pop(0)
            if current in seen:
                continue
            seen.add(current)
            state = self.stage(current)
            if state.status != "pending":
                spec = get_stage(current)
                stale_root = (
                    Path(run_dir)
                    / "harness"
                    / "stale"
                    / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                )
                for relative in spec.output_paths:
                    output = Path(run_dir) / relative
                    if output.is_file():
                        target = stale_root / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(output), str(target))
                state.status = "pending"
                state.attempts = 0
                state.input_hash = None
                state.output_hash = None
                state.last_error = None
                state.task_file = None
                state.updated_at = utc_now()
            for spec in STAGES:
                if current in spec.dependencies:
                    pending.append(spec.id)

    def refresh_invalidated_stages(self, run_dir: Path) -> None:
        """Detect edits to an upstream artifact and invalidate descendants."""
        for spec in STAGES:
            state = self.stage(spec.id)
            if state.status not in TERMINAL_OK or state.input_hash is None:
                continue
            current = stage_input_hash(run_dir, spec)
            output_changed = bool(spec.output_paths) and state.output_hash is not None and (
                stage_output_hash(run_dir, spec) != state.output_hash
            )
            if current != state.input_hash or output_changed:
                self.invalidate_from(run_dir, spec.id)
