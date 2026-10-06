"""One revision round for findings a reviewer asked to revise.

Round 0: the four reviewers judge every finding. A ``revise`` verdict sends the
finding back to its module's audit role, which writes a revised copy to
``harness/agent_outputs/revisions/<module>.json``: same id and numbers, new
wording, severity, confidence or recommendation type. Round 1: each reviewer
who asked for a revision re-reviews only those findings and may approve or
reject, never revise again. Reports use the revised text.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from pydantic import ValidationError

from .schemas import Finding, ReviewEntry

REVIEWS_DIR = Path("harness") / "agent_outputs" / "reviews"
REVISIONS_DIR = Path("harness") / "agent_outputs" / "revisions"
REREVIEWS_DIR = Path("harness") / "agent_outputs" / "rereviews"

# Numbers, identity and traceability come from code; a revision may change
# only how the finding is judged and worded. Locked fields may be omitted from
# a revision; when present they must equal the original.
LOCKED_FIELDS = (
    "id",
    "module",
    "object_type",
    "measurement_id",
    "field_name",
    "denominator",
    "affected_records",
    "affected_percentage",
    "evidence_file",
    "auto_fix_allowed",
)
EDITABLE_FIELDS = (
    "title",
    "severity",
    "confidence",
    "business_impact",
    "decision_impacts",
    "recommendation_type",
)


def _read_list(path: Path) -> List[Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path.name} must contain a JSON array")
    return data


def raw_entries(directory: Path, revision_round: int) -> List[Dict[str, Any]]:
    """Verdict dicts from one round's per-reviewer files, round number filled in."""
    entries: List[Dict[str, Any]] = []
    if not directory.is_dir():
        return entries
    for path in sorted(directory.glob("*.json")):
        for raw in _read_list(path):
            data = dict(raw) if isinstance(raw, dict) else {"_invalid": raw}
            data.setdefault("revision_round", revision_round)
            entries.append(data)
    return entries


def round0_raw(run_dir: Path) -> List[Dict[str, Any]]:
    return raw_entries(Path(run_dir) / REVIEWS_DIR, 0)


def round1_raw(run_dir: Path) -> List[Dict[str, Any]]:
    return raw_entries(Path(run_dir) / REREVIEWS_DIR, 1)


def round0_entries(run_dir: Path) -> List[ReviewEntry]:
    return [ReviewEntry.model_validate(raw) for raw in round0_raw(run_dir)]


def round1_entries(run_dir: Path) -> List[ReviewEntry]:
    return [ReviewEntry.model_validate(raw) for raw in round1_raw(run_dir)]


def original_findings(run_dir: Path) -> Dict[str, Tuple[str, Dict[str, Any]]]:
    """Finding id → (module, raw finding) from the audit roles' files."""
    result: Dict[str, Tuple[str, Dict[str, Any]]] = {}
    for path in sorted((Path(run_dir) / "findings").glob("*_findings.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        module = str(doc.get("module") or path.name.removesuffix("_findings.json"))
        for raw in doc.get("findings", []):
            if isinstance(raw, dict) and raw.get("id"):
                result[str(raw["id"])] = (module, raw)
    return result


def revise_requests(run_dir: Path) -> Dict[str, List[ReviewEntry]]:
    """Finding id → the round-0 entries that asked for a revision.

    A finding another reviewer already rejected stays rejected, so it is not
    sent back.
    """
    try:
        entries = round0_entries(run_dir)
    except ValueError:  # malformed round-0 files; the round-0 gate reports them
        return {}
    rejected = {entry.finding_id for entry in entries if entry.verdict == "reject"}
    requests: Dict[str, List[ReviewEntry]] = {}
    for entry in entries:
        if entry.verdict == "revise" and entry.finding_id not in rejected:
            requests.setdefault(entry.finding_id, []).append(entry)
    return requests


def modules_needing_revision(run_dir: Path) -> Set[str]:
    originals = original_findings(run_dir)
    return {originals[fid][0] for fid in revise_requests(run_dir) if fid in originals}


def reviewers_needing_rereview(run_dir: Path) -> Set[str]:
    return {entry.reviewer for entries in revise_requests(run_dir).values() for entry in entries}


def load_revisions(run_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Finding id → revised raw finding, for findings currently sent back.

    A revision left over from an earlier review round is ignored.
    """
    directory = Path(run_dir) / REVISIONS_DIR
    if not directory.is_dir():
        return {}
    requested = set(revise_requests(run_dir))
    revisions: Dict[str, Dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for raw in doc.get("findings", []) if isinstance(doc, dict) else []:
            if isinstance(raw, dict) and str(raw.get("id")) in requested:
                revisions[str(raw["id"])] = raw
    return revisions


def overlay(raw: Dict[str, Any], revisions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """The finding as reviewers last approved it: revised wording where present."""
    revised = revisions.get(str(raw.get("id")))
    if revised is None:
        return raw
    merged = dict(raw)
    for field in EDITABLE_FIELDS:
        if field in revised:
            merged[field] = revised[field]
    return merged


def validate_revision(run_dir: Path, module: str) -> List[str]:
    """Check one module's revision file against the round-0 revise requests."""
    from .validators import NUMBER_WORD_QUANTITY_RE  # avoid an import cycle

    run_dir = Path(run_dir)
    path = run_dir / REVISIONS_DIR / f"{module}.json"
    label = str(REVISIONS_DIR / f"{module}.json")
    if not path.exists():
        return [f"{label} not found"]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{label}: invalid JSON — {exc}"]
    if not isinstance(doc, dict) or doc.get("module") != module:
        return [f"{label}: must be an object with module {module!r}"]
    originals = original_findings(run_dir)
    requests = revise_requests(run_dir)
    requested = {fid for fid in requests if originals.get(fid, (None,))[0] == module}
    problems: List[str] = []
    given: Set[str] = set()
    for raw in doc.get("findings", []):
        if not isinstance(raw, dict):
            problems.append(f"{label}: every finding must be an object")
            continue
        fid = str(raw.get("id") or "")
        given.add(fid)
        if fid not in requested:
            problems.append(f"{label}: finding '{fid}' was not sent back for revision")
            continue
        original = originals[fid][1]
        if not str(raw.get("revision_note") or "").strip():
            problems.append(
                f"{label}: finding '{fid}' needs a revision_note saying what changed "
                "in answer to each reviewer, or why the original stands"
            )
        for field in LOCKED_FIELDS:
            if field in raw and raw[field] != original.get(field):
                problems.append(
                    f"{label}: finding '{fid}' changes locked field {field!r}; "
                    "a revision may change only wording, severity, confidence and recommendation type"
                )
        try:
            finding = Finding.model_validate(overlay(original, {fid: raw}))
        except ValidationError as exc:
            problems.append(f"{label}: finding '{fid}' is invalid — {exc}")
            continue
        if NUMBER_WORD_QUANTITY_RE.search(finding.business_impact):
            problems.append(
                f"{label}: finding '{fid}' business_impact spells out a measurable quantity. "
                "Use Arabic numerals in audit prose."
            )
    for fid in sorted(requested - given):
        problems.append(f"{label}: missing revision for finding '{fid}'")
    return problems


def validate_rereview(run_dir: Path, reviewer: str) -> List[str]:
    """Check one reviewer's round-1 file: exactly the findings it sent back."""
    run_dir = Path(run_dir)
    path = run_dir / REREVIEWS_DIR / f"{reviewer}.json"
    label = str(REREVIEWS_DIR / f"{reviewer}.json")
    if not path.exists():
        return [f"{label} not found"]
    try:
        raw_entries = _read_list(path)
    except (ValueError, json.JSONDecodeError) as exc:
        return [f"{label}: {exc}"]
    expected = {
        fid
        for fid, entries in revise_requests(run_dir).items()
        if any(entry.reviewer == reviewer for entry in entries)
    }
    problems: List[str] = []
    seen: Set[str] = set()
    for index, raw in enumerate(raw_entries):
        data = dict(raw) if isinstance(raw, dict) else {}
        data.setdefault("revision_round", 1)
        try:
            entry = ReviewEntry.model_validate(data)
        except ValidationError as exc:
            problems.append(f"{label} entry {index}: {exc}")
            continue
        if entry.reviewer != reviewer:
            problems.append(f"{label} entry {index}: reviewer {entry.reviewer!r}, expected {reviewer!r}")
        if entry.revision_round != 1:
            problems.append(f"{label} entry {index}: re-review entries are revision_round 1")
        if entry.finding_id not in expected:
            problems.append(f"{label}: '{entry.finding_id}' wasn't sent back by {reviewer}")
        if entry.finding_id in seen:
            problems.append(f"{label}: duplicate re-review of '{entry.finding_id}'")
        seen.add(entry.finding_id)
    for fid in sorted(expected - seen):
        problems.append(f"{label}: missing re-review of '{fid}'")
    return problems


def final_review_status(round0: Dict[str, str], round1: Optional[Dict[str, str]] = None) -> str:
    """Reject wins; a finding sent back and then approved is ``revised``."""
    round1 = round1 or {}
    effective = {reviewer: round1.get(reviewer, verdict) for reviewer, verdict in round0.items()}
    if "reject" in effective.values():
        return "rejected"
    if "revise" in round0.values():
        return "revised"
    return "approved"


def is_harness_run(run_dir: Path) -> bool:
    """Harness runs get a revision round; legacy manual runs edit findings in place."""
    return (Path(run_dir) / "harness" / "run_state.json").is_file()


def stray_files(run_dir: Path, directory: Path, expected: Iterable[str]) -> List[str]:
    """Revision or re-review files for a module or reviewer nobody sent anything back to."""
    folder = Path(run_dir) / directory
    if not folder.is_dir():
        return []
    allowed = set(expected)
    return [
        f"{directory / path.name}: nothing was sent back to '{path.stem}' in this review round"
        for path in sorted(folder.glob("*.json"))
        if path.stem not in allowed
    ]
