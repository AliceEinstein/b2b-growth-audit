"""Deterministic consolidation of agent workspace outputs.

Merging candidate findings into findings.json and reviewer decisions into
review_trace.json is arithmetic, not judgment, so it is owned by code: the
orchestrator role dispatches and adjudicates but never hand-assembles the
consolidated artifacts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from pydantic import ValidationError

from connectors.hubspot.normalize import write_json

from .lifecycle_schemas import CandidateFindingsDoc, ReviewDecisionsDoc


def _load_docs(directory: Path, model) -> Tuple[List[Tuple[str, Any]], List[str]]:
    docs: List[Tuple[str, Any]] = []
    problems: List[str] = []
    if not directory.exists():
        return docs, [f"{directory.name}/ directory not found"]
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            docs.append((path.name, model.model_validate(data)))
        except (json.JSONDecodeError, OSError, ValidationError) as exc:
            problems.append(f"{directory.name}/{path.name} is invalid: {exc}")
    if not docs and not problems:
        problems.append(f"{directory.name}/ contains no artifacts")
    return docs, problems


def consolidate_candidates(run_dir: Path) -> Tuple[int, List[str]]:
    """Merge agent_workspace/candidates/*.json into findings.json."""
    run_dir = Path(run_dir)
    docs, problems = _load_docs(
        run_dir / "agent_workspace" / "candidates", CandidateFindingsDoc
    )
    if problems:
        return 0, problems
    merged: Dict[str, Dict[str, Any]] = {}
    for source, doc in docs:
        for finding in doc.candidate_findings:
            row = finding.model_dump()
            existing = merged.get(finding.finding_id)
            if existing is None:
                merged[finding.finding_id] = row
            elif existing != row:
                problems.append(
                    f"conflicting candidate payloads for {finding.finding_id} "
                    f"(latest from {source}); resolve in the audit roles first"
                )
    if problems:
        return 0, problems
    rows = [merged[key] for key in sorted(merged)]
    write_json(run_dir / "findings.json", {"findings": rows})
    return len(rows), []


def consolidate_reviews(run_dir: Path) -> Tuple[int, List[str]]:
    """Merge agent_workspace/reviews/*.json into review_trace.json."""
    run_dir = Path(run_dir)
    docs, problems = _load_docs(
        run_dir / "agent_workspace" / "reviews", ReviewDecisionsDoc
    )
    if problems:
        return 0, problems
    rows: List[Dict[str, Any]] = []
    seen = set()
    for source, doc in docs:
        # Reviewer isolation is structural: the artifact filename is the
        # reviewer's identity, and a file may carry only its own decisions.
        expected_reviewer = Path(source).stem
        for review in doc.reviews:
            if review.reviewer != expected_reviewer:
                problems.append(
                    f"reviews/{source}: decision for {review.finding_id} is "
                    f"attributed to {review.reviewer!r}; this file may only "
                    f"contain {expected_reviewer!r} decisions"
                )
                continue
            key = (review.finding_id, review.reviewer, review.revision_round)
            if key in seen:
                problems.append(
                    f"duplicate review decision {key} (latest from {source})"
                )
                continue
            seen.add(key)
            rows.append(review.model_dump())
    if problems:
        return 0, problems
    rows.sort(key=lambda row: (row["finding_id"], row["reviewer"], row["revision_round"]))
    write_json(run_dir / "review_trace.json", {"reviews": rows})
    return len(rows), []
