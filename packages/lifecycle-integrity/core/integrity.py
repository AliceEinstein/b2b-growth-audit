"""Content-integrity helpers for safety-gated local artifacts."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file without loading it all in memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_files(run_dir: Path, names: Iterable[str]) -> dict[str, str | None]:
    """Hash named run artifacts; missing files are represented by ``None``."""
    root = Path(run_dir)
    return {
        name: sha256_file(root / name) if (root / name).is_file() else None
        for name in names
    }


def hashes_match(
    run_dir: Path, expected: dict[str, str | None]
) -> tuple[bool, list[str]]:
    """Compare current named-file hashes with a previously recorded map."""
    current = hash_files(run_dir, expected)
    mismatches = [name for name, digest in expected.items() if current[name] != digest]
    return not mismatches, mismatches
