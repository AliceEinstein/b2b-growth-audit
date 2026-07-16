"""Agent-driven harness: code owns the control flow, the host agent owns
judgment.

No LLM provider is built in. The host coding agent (Claude Code, Codex, …)
drives three verbs:

- ``next``     — the harness picks the next pending task, materializes ONLY
                 that role's declared inputs into an isolated inbox directory,
                 and hands over the instruction plus a JSON-Schema contract.
- ``submit``   — the harness validates the role's output (schema, role
                 identity, reviewer isolation, plan/adjudication agreement)
                 BEFORE committing it to its canonical path, records its
                 SHA-256 in a journal, and auto-runs deterministic phase
                 transitions (candidate/review consolidation).
- ``finalize`` — validators, deterministic reports, and the final gate.

The journal (`agent_workspace/harness_journal.json`) makes side-door writes
and post-commit edits detectable: the final gate requires every task artifact
to be journaled with a matching hash. This is tamper-evidence for agents and
accidents, not cryptography — nothing local can stop a determined human
editor, and it does not try to.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .integrity import sha256_file
from .lifecycle_agent_tasks import REPO_ROOT, TASKS
from .lifecycle_consolidation import consolidate_candidates, consolidate_reviews
from .lifecycle_validators import validate_recommendation_plan
from .lifecycle_workspace import (
    GATE_OWNED_SCHEMAS,
    SCHEMA_MODELS,
    _validate_task_output,
    next_tasks,
)

JOURNAL_NAME = "harness_journal.json"
INBOX_DIR = "agent_workspace/inbox"


def _journal_path(run_dir: Path) -> Path:
    return Path(run_dir) / "agent_workspace" / JOURNAL_NAME


def load_journal(run_dir: Path) -> Dict[str, Any]:
    path = _journal_path(run_dir)
    if not path.exists():
        return {"version": 1, "tasks": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_journal(run_dir: Path, journal: Dict[str, Any]) -> None:
    path = _journal_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def task_by_role(role: str) -> Optional[Dict[str, Any]]:
    return next((task for task in TASKS if task["role"] == role), None)


def materialize_task(run_dir: Path, task: Dict[str, Any]) -> Path:
    """Copy exactly the declared inputs + instruction into the role's inbox.

    Isolation is structural: the inbox contains only what the role may read.
    ``raw/`` can never appear here — the task writer rejects it at manifest
    build time, and nothing else copies it.
    """
    run_dir = Path(run_dir)
    inbox = run_dir / INBOX_DIR / task["role"]
    if inbox.exists():
        shutil.rmtree(inbox)
    inputs_dir = inbox / "inputs"
    inputs_dir.mkdir(parents=True)
    for rel in task["inputs"]:
        source = run_dir / rel
        target = inputs_dir / rel
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        elif source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    instruction = REPO_ROOT / task["instruction"]
    if instruction.exists():
        shutil.copy2(instruction, inbox / "instruction.md")
    model = SCHEMA_MODELS.get(task["output_schema"])
    contract = {
        "role": task["role"],
        "phase": task["phase"],
        "output_schema": task["output_schema"],
        "model_tier": task["model_tier"],
        "model_routing_hint": (
            "model_tier is advisory cost metadata; by default every task "
            "follows the user's session model and the harness never selects "
            "a model. Users who want to save quota can map tiers to smaller "
            "models themselves (Claude Code: edit the model: field of the "
            "bundled .claude/agents/audit-role-<tier> subagents; other CLIs: "
            "profile/model flags). Never map reviewer or safety roles below "
            "their tier. Validation gates are model-independent."
        ),
        "write_your_output_to": str(inbox / "output.json"),
        "then_run": f"python -m scripts.harness submit --run {run_dir} --role {task['role']}",
        "json_schema": model.model_json_schema() if model else None,
    }
    (inbox / "contract.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return inbox


def claim_next(run_dir: Path) -> Tuple[Optional[Dict[str, Any]], Optional[Path], List[str]]:
    """Advance deterministic state, then hand out the first pending task."""
    run_dir = Path(run_dir)
    problems = advance_phases(run_dir)
    phase, pending, next_problems = next_tasks(run_dir)
    problems += next_problems
    if phase is None or not pending:
        return None, None, problems
    task = pending[0]
    inbox = materialize_task(run_dir, task)
    return task, inbox, problems


def submit_task(
    run_dir: Path,
    role: str,
    document: Optional[Dict[str, Any]] = None,
    *,
    resubmit: bool = False,
) -> Tuple[bool, List[str]]:
    """Validate and commit one role's output; reject invalid work untouched.

    ``document`` defaults to the role's inbox ``output.json``. On success the
    artifact lands on its canonical path and is journaled; on failure nothing
    is committed and the problems are returned.
    """
    run_dir = Path(run_dir)
    task = task_by_role(role)
    if task is None:
        return False, [f"unknown role: {role}"]
    if task["output_schema"] in GATE_OWNED_SCHEMAS:
        return False, [f"{role} output is gate-owned; run finalize instead"]
    journal = load_journal(run_dir)
    entry = journal["tasks"].get(role, {"attempts": 0})
    output_path = run_dir / task["output"]
    if output_path.exists() and entry.get("status") == "committed" and not resubmit:
        return False, [
            f"{task['output']} is already committed; pass resubmit to replace it"
        ]
    if document is None:
        source = run_dir / INBOX_DIR / role / "output.json"
        if not source.exists():
            return False, [f"no output found at {source}"]
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return False, [f"output.json is not valid JSON: {exc}"]

    # Validate against the committed location semantics without committing:
    # write, validate, roll back on failure.
    previous = output_path.read_text(encoding="utf-8") if output_path.exists() else None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    problems = _validate_task_output(run_dir, task)
    if not problems and task["output_schema"] == "recommendation_lanes":
        problems = validate_recommendation_plan(run_dir)
    entry["attempts"] = int(entry.get("attempts", 0)) + 1
    if problems:
        if previous is None:
            output_path.unlink()
        else:
            output_path.write_text(previous, encoding="utf-8")
        entry["status"] = "rejected"
        entry["last_error"] = problems[0]
        journal["tasks"][role] = entry
        _save_journal(run_dir, journal)
        return False, problems
    entry.update(
        {
            "status": "committed",
            "sha256": sha256_file(output_path),
            "committed_at": datetime.now(timezone.utc).isoformat(),
            "last_error": None,
        }
    )
    journal["tasks"][role] = entry
    _save_journal(run_dir, journal)
    problems = advance_phases(run_dir)
    return True, problems


def _phase_done(run_dir: Path, phase: str) -> bool:
    return all(
        (Path(run_dir) / task["output"]).exists()
        for task in TASKS
        if task["phase"] == phase and task["output_schema"] not in GATE_OWNED_SCHEMAS
    )


def advance_phases(run_dir: Path) -> List[str]:
    """Run code-owned transitions the moment their phase is complete."""
    run_dir = Path(run_dir)
    problems: List[str] = []
    if _phase_done(run_dir, "audit"):
        count, consolidation_problems = consolidate_candidates(run_dir)
        problems += consolidation_problems
    if _phase_done(run_dir, "review") and (run_dir / "findings.json").exists():
        count, consolidation_problems = consolidate_reviews(run_dir)
        problems += consolidation_problems
    return problems


def verify_journal(run_dir: Path, *, require_complete: bool = False) -> List[str]:
    """Tamper-evidence: every task artifact must be journaled with its hash."""
    run_dir = Path(run_dir)
    journal_exists = _journal_path(run_dir).exists()
    if not journal_exists and not require_complete:
        return []
    journal = load_journal(run_dir)
    problems: List[str] = []
    if not journal_exists:
        return [
            "agent_workspace/harness_journal.json not found — judgment "
            "artifacts must be committed through `python -m scripts.harness "
            "submit`, not written directly"
        ]
    for task in TASKS:
        if task["output_schema"] in GATE_OWNED_SCHEMAS:
            continue
        path = run_dir / task["output"]
        entry = journal["tasks"].get(task["role"])
        if not path.exists():
            continue  # completeness is the workspace validator's job
        if entry is None or entry.get("status") != "committed":
            problems.append(
                f"{task['output']} exists but was never committed through the "
                "harness (side-door write)"
            )
        elif entry.get("sha256") != sha256_file(path):
            problems.append(
                f"{task['output']} was modified after harness commit "
                "(hash mismatch); resubmit it through the harness"
            )
    return problems
