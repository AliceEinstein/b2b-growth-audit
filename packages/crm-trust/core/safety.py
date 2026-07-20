"""Deterministic leak-detection net.

This module is NOT the primary safety judge. Per the division of labor
(measure in code, judge with LLM), the Privacy + Safety Reviewer — an LLM
role — decides whether report content is safe in context. This net exists
because leaked emails, phone numbers, and API tokens have fixed FORMATS that
pattern matching catches cheaply and deterministically, and a failed LLM
review must never be the only thing standing between a token and a report.

Hit semantics:
- hard=True  (email / phone / token formats)  -> fail the run unconditionally
- hard=False (blocked-phrase matches)         -> flag for the LLM safety
  reviewer, who must clear or reject each one in context. Phrases like
  "delete properties" legitimately appear inside a "Blocked Actions" section,
  so auto-failing on phrases would cause exactly the kind of one-size-fits-all
  misjudgment this design avoids.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

TOKEN_PATTERNS = [
    # Canonical HubSpot private app token shape
    re.compile(
        r"\bpat-[a-z]{2,4}\d?-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        re.IGNORECASE,
    ),
    # Anything that looks like a long pat-… credential
    re.compile(r"\bpat-[A-Za-z0-9][A-Za-z0-9-]{18,}\b"),
]

# Requires separators and 9+ digits; date/timestamp shapes are excluded below.
PHONE_PATTERN = re.compile(
    r"(?<![\dA-Za-z.])\+?\d{1,3}[\s.-]?\(?\d{2,4}\)?[\s.-]\d{3,4}[\s.-]?\d{2,4}(?![\dA-Za-z])"
)

# Final deliverables are English by contract, so this is intentionally an
# English recommendation backstop. Multilingual CRM input is handled by the
# untrusted sanitizer and the LLM reviewer, not by this output phrase list.
# Soft hits — reviewed, not auto-failed.
BLOCKED_PHRASES = [
    "overwrite original source",
    "merge companies automatically",
    "delete properties",
    "move all stale deals",
    "reset lifecycle stage",
    "bulk update owner",
]

# File types scanned in final outputs. raw/ is never scanned (it is local and
# allowed to contain owner-authorized business data; agent access is strongly
# discouraged by workflow instructions and the raw-directory sentinel).
SCANNED_SUFFIXES = {".md", ".html", ".json", ".csv", ".yaml", ".yml", ".txt"}


@dataclass
class SafetyHit:
    kind: str  # email | phone | hubspot_token | blocked_phrase
    source: str  # file or label the hit came from
    excerpt: str  # masked — never reproduces the leaked value
    hard: bool  # True = unconditional failure


def _mask(value: str) -> str:
    return value[:2] + "…" + f"({len(value)} chars)"


def _looks_like_timestamp(value: str) -> bool:
    return bool(re.match(r"^\s*\d{4}-\d{2}-\d{2}", value))


def scan_text(text: str, source: str = "text") -> list[SafetyHit]:
    hits: list[SafetyHit] = []

    for match in EMAIL_PATTERN.finditer(text):
        hits.append(SafetyHit("email", source, _mask(match.group()), hard=True))

    for pattern in TOKEN_PATTERNS:
        for match in pattern.finditer(text):
            hits.append(
                SafetyHit("hubspot_token", source, _mask(match.group()), hard=True)
            )

    for match in PHONE_PATTERN.finditer(text):
        candidate = match.group()
        digits = re.sub(r"\D", "", candidate)
        if len(digits) >= 9 and not _looks_like_timestamp(candidate):
            hits.append(SafetyHit("phone", source, _mask(candidate), hard=True))

    lowered = text.lower()
    for phrase in BLOCKED_PHRASES:
        if phrase in lowered:
            hits.append(SafetyHit("blocked_phrase", source, phrase, hard=False))

    return hits


def scan_file(path: Path) -> list[SafetyHit]:
    return scan_text(Path(path).read_text(encoding="utf-8"), source=str(path))


def scan_final_outputs(run_dir: Path) -> list[SafetyHit]:
    """Scan every final artifact in a run directory, skipping raw/."""
    hits: list[SafetyHit] = []
    for path in sorted(Path(run_dir).rglob("*")):
        if "raw" in path.parts:
            continue
        if path.is_file() and path.suffix in SCANNED_SUFFIXES:
            hits.extend(scan_file(path))
    return hits


def has_hard_leaks(hits: list[SafetyHit]) -> bool:
    return any(h.hard for h in hits)


# The final deliverables of a run (PRD output contract). The final gate
# scans exactly these — intermediate working artifacts (review_log,
# safety_clearance, final_gate_report) may legitimately quote flagged
# phrases while discussing them.
FINAL_DELIVERABLES = [
    "crm_trust_report.md",
    "crm_trust_report.html",
    "operator_appendix.md",
    "agent_handoff.md",
    "findings.json",
    "evidence.csv",
    "report_record_evidence.csv",
    "crm_context.yaml",
    "schema_discovery_report.md",
    "audit_log.json",
    "score.json",
    "recommendations.json",
    "manifest.json",
]


def scan_deliverables(run_dir: Path) -> list:
    hits = []
    for name in FINAL_DELIVERABLES:
        path = Path(run_dir) / name
        if path.exists():
            hits.extend(scan_file(path))
    return hits
