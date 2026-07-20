from __future__ import annotations

import re
import json
from pathlib import Path

from core.lifecycle_agent_tasks import expected_manifest_contract
from core.lifecycle_synthetic_datasets import LIFECYCLE_DATASETS


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
TOKEN_RE = re.compile(r"\b(?:pat|pat-na|hs_pat)-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE)
RESERVED_DOMAINS = {
    "example.com",
    "example.net",
    "example.org",
}


def test_checked_in_examples_contain_only_reserved_email_domains_and_no_tokens():
    """Keep public fixtures synthetic even when a new sample is added."""
    repo_root = Path(__file__).resolve().parents[3]
    example_roots = sorted((repo_root / "packages").glob("*/examples"))
    assert example_roots, "expected package examples to exist"

    checked_files = 0
    for examples_root in example_roots:
        for path in examples_root.rglob("*"):
            if not path.is_file() or path.name == ".gitkeep":
                continue
            checked_files += 1
            content = path.read_text(encoding="utf-8", errors="ignore")
            for match in EMAIL_RE.finditer(content):
                domain = match.group(1).lower()
                assert domain.endswith(".test") or domain.endswith(".invalid") or domain in RESERVED_DOMAINS, (
                    f"public fixture contains a non-reserved email domain: {path}"
                )
            assert not TOKEN_RE.search(content), (
                f"public fixture contains a HubSpot-looking token: {path}"
            )

    assert checked_files > 0


def test_checked_in_lifecycle_fixtures_match_the_current_task_contract():
    """A public sample must be runnable by the current judgment harness."""
    repo_root = Path(__file__).resolve().parents[3]
    lifecycle_root = repo_root / "packages" / "lifecycle-integrity" / "examples" / "lifecycle"
    sample_dirs = {path.name for path in lifecycle_root.iterdir() if path.is_dir()}
    assert sample_dirs == set(LIFECYCLE_DATASETS)

    contract = expected_manifest_contract()
    for sample in sorted(sample_dirs):
        manifest_path = lifecycle_root / sample / "agent_workspace" / "task_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for key, value in contract.items():
            assert manifest.get(key) == value, f"{sample}: stale task manifest field {key}"
