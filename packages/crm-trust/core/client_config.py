"""Owner-confirmed canonical fields, shared with the lifecycle audit.

``field_overrides.yaml`` is the same file the lifecycle package writes when
the owner confirms its questions (``scripts.confirm_client_config``). Copied
into ``<run_dir>/config/``, it fixes the fields schema discovery must use:
each named role is canonical at high confidence, with no confirmation left
to ask.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List

import yaml

CONFIG_DIR = "config"
FIELD_OVERRIDES_FILE = "field_overrides.yaml"
FIELD_OVERRIDES_PATH = CONFIG_DIR + "/" + FIELD_OVERRIDES_FILE

# Same roles as the lifecycle package; CRM Trust measures lifecycle_stage and
# original_source, and records company_lifecycle_stage when the owner names it.
CANONICAL_ROLES: Dict[str, Dict[str, str]] = {
    "lifecycle_stage": {"object": "contact", "object_type": "contacts"},
    "company_lifecycle_stage": {"object": "company", "object_type": "companies"},
    "original_source": {"object": "contact", "object_type": "contacts"},
}


class ClientConfigError(ValueError):
    """A client configuration file is missing, malformed, or names unknown fields."""


def parse_field_overrides(data: Any, source: str = FIELD_OVERRIDES_FILE) -> Dict[str, str]:
    if not isinstance(data, dict):
        raise ClientConfigError(f"{source}: top level must be a mapping")
    overrides = data.get("canonical_fields") or {}
    if not isinstance(overrides, dict):
        raise ClientConfigError(f"{source}: canonical_fields must be a mapping")
    result: Dict[str, str] = {}
    for role, prop in overrides.items():
        if role not in CANONICAL_ROLES:
            raise ClientConfigError(
                f"{source}: unknown canonical field '{role}'; expected one of "
                + ", ".join(sorted(CANONICAL_ROLES))
            )
        if not isinstance(prop, str) or not prop.strip():
            raise ClientConfigError(f"{source}: canonical_fields.{role} must name a property")
        result[role] = prop.strip()
    return result


def _read(path: Path) -> Dict[str, str]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ClientConfigError(f"{path.name}: cannot read YAML: {exc}") from exc
    return parse_field_overrides(data, path.name)


def load_field_overrides(run_dir: Path) -> Dict[str, str]:
    path = Path(run_dir) / FIELD_OVERRIDES_PATH
    return _read(path) if path.exists() else {}


def _missing_properties(run_dir: Path, overrides: Dict[str, str]) -> List[str]:
    problems = []
    for role, prop in overrides.items():
        spec = CANONICAL_ROLES[role]
        path = Path(run_dir) / "raw" / f"properties_{spec['object_type']}.json"
        try:
            names = {str(d.get("name")) for d in json.loads(path.read_text(encoding="utf-8"))}
        except (OSError, json.JSONDecodeError):
            continue
        if prop not in names:
            problems.append(
                f"canonical_fields.{role} names '{prop}', which is not a "
                f"{spec['object']} property in this snapshot"
            )
    return problems


def install_field_overrides(run_dir: Path, source: Path) -> Dict[str, str]:
    """Validate an owner-confirmed file against the snapshot and copy it into the run."""
    source = Path(source)
    if not source.exists():
        raise ClientConfigError(f"{source}: file not found")
    overrides = _read(source)
    problems = _missing_properties(run_dir, overrides)
    if problems:
        raise ClientConfigError(f"{source.name}: " + "; ".join(problems))
    target = Path(run_dir) / FIELD_OVERRIDES_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return overrides


def override_problems(run_dir: Path, canonical_fields: Dict[str, Any]) -> List[str]:
    """crm_context.yaml must use every owner-confirmed field as given."""
    try:
        overrides = load_field_overrides(run_dir)
    except ClientConfigError as exc:
        return [str(exc)]
    problems = []
    for role, prop in overrides.items():
        mapping = canonical_fields.get(role)
        expected_object = CANONICAL_ROLES[role]["object"]
        if mapping is None:
            problems.append(
                f"canonical_fields.{role}: missing; the owner confirmed '{prop}' in {FIELD_OVERRIDES_PATH}"
            )
            continue
        if (mapping.object, mapping.field) != (expected_object, prop):
            problems.append(
                f"canonical_fields.{role}: uses {mapping.object}.{mapping.field}, but the owner "
                f"confirmed {expected_object}.{prop} in {FIELD_OVERRIDES_PATH}"
            )
        if mapping.confidence != "high" or mapping.requires_confirmation:
            problems.append(
                f"canonical_fields.{role}: an owner-confirmed field is high confidence "
                "with requires_confirmation: false"
            )
    return problems
