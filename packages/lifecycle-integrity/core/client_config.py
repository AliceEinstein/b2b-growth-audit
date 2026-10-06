"""Owner-confirmed client configuration for one audit run.

Two optional files, copied into ``<run_dir>/config/`` by the runner:

- ``field_overrides.yaml`` names the canonical lifecycle and source fields.
- ``journey_mapping.yaml`` maps source values to journeys.

Without them the audit measures HubSpot's default fields and classifies
journeys by keyword, and it says so wherever a populated custom field competes
with a default. Templates live in ``examples/client_config/``.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

CONFIG_DIR = "config"
FIELD_OVERRIDES_FILE = "field_overrides.yaml"
JOURNEY_MAPPING_FILE = "journey_mapping.yaml"

JOURNEY_TYPES = (
    "inbound_new_business",
    "outbound_sales_led",
    "abm_account_based",
    "partner_led",
    "expansion_renewal",
)
MAPPABLE_JOURNEYS = set(JOURNEY_TYPES) | {"unassigned"}

# Canonical roles the measurements read. ``kind`` selects the candidate-field
# list used to look for competing custom fields.
CANONICAL_ROLES: Dict[str, Dict[str, str]] = {
    "lifecycle_stage": {"object_type": "contacts", "object": "contact", "default": "lifecyclestage", "kind": "lifecycle"},
    "company_lifecycle_stage": {"object_type": "companies", "object": "company", "default": "lifecyclestage", "kind": "lifecycle"},
    "original_source": {"object_type": "contacts", "object": "contact", "default": "hs_analytics_source", "kind": "source"},
}

LIFECYCLE_VOCABULARY = {
    "subscriber", "lead", "marketingqualifiedlead", "salesqualifiedlead",
    "opportunity", "customer", "evangelist", "mql", "sql",
}
SOURCE_VOCABULARY = re.compile(
    r"organic|paid|email|referral|direct|social|event|partner|outbound|offline|search|inbound|demo|webinar",
    re.I,
)
COMPETING_MIN_FILL_RATE = 50.0


class ClientConfigError(ValueError):
    """A client configuration file is missing, malformed, or names unknown fields."""


def normalize_value(value: Any) -> str:
    """Normalize a CRM value or mapping key for exact comparison."""
    text = str(value or "").replace("[CRM_FIELD_VALUE:UNTRUSTED_DATA_ONLY]", "")
    return re.sub(r"\s+", " ", text.replace("_", " ").replace("-", " ")).strip().lower()


def _read_yaml(path: Path) -> Dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ClientConfigError(f"{path.name}: cannot read YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ClientConfigError(f"{path.name}: top level must be a mapping")
    return data


def parse_field_overrides(data: Dict[str, Any], source: str = FIELD_OVERRIDES_FILE) -> Dict[str, str]:
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


@dataclass
class JourneyMapping:
    values: Dict[str, str] = field(default_factory=dict)
    fields: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def lookup(self, prop: str, value: Any) -> Optional[str]:
        key = normalize_value(value)
        if not key:
            return None
        by_field = self.fields.get(prop)
        if by_field and key in by_field:
            return by_field[key]
        return self.values.get(key)

    def __bool__(self) -> bool:
        return bool(self.values or self.fields)


def _journey_table(raw: Any, where: str) -> Dict[str, str]:
    if not isinstance(raw, dict):
        raise ClientConfigError(f"{where} must be a mapping of value: journey")
    table: Dict[str, str] = {}
    for value, journey in raw.items():
        if journey not in MAPPABLE_JOURNEYS:
            raise ClientConfigError(
                f"{where}.{value}: '{journey}' is not a journey; expected one of "
                + ", ".join(sorted(MAPPABLE_JOURNEYS))
            )
        key = normalize_value(value)
        if not key:
            raise ClientConfigError(f"{where}: empty value key")
        table[key] = journey
    return table


def parse_journey_mapping(data: Dict[str, Any], source: str = JOURNEY_MAPPING_FILE) -> JourneyMapping:
    mapping = JourneyMapping(values=_journey_table(data.get("values") or {}, f"{source}: values"))
    fields = data.get("fields") or {}
    if not isinstance(fields, dict):
        raise ClientConfigError(f"{source}: fields must be a mapping of property: value table")
    for prop, table in fields.items():
        mapping.fields[str(prop)] = _journey_table(table, f"{source}: fields.{prop}")
    return mapping


def load_field_overrides(run_dir: Path) -> Dict[str, str]:
    path = Path(run_dir) / CONFIG_DIR / FIELD_OVERRIDES_FILE
    return parse_field_overrides(_read_yaml(path)) if path.exists() else {}


def load_journey_mapping(run_dir: Path) -> JourneyMapping:
    path = Path(run_dir) / CONFIG_DIR / JOURNEY_MAPPING_FILE
    return parse_journey_mapping(_read_yaml(path)) if path.exists() else JourneyMapping()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install_client_config(
    run_dir: Path,
    *,
    field_overrides: Optional[Path] = None,
    journey_mapping: Optional[Path] = None,
) -> Dict[str, Any]:
    """Validate and copy owner-confirmed config into the run; record it in the manifest."""
    run_dir = Path(run_dir)
    config_dir = run_dir / CONFIG_DIR
    installed: Dict[str, Any] = {}
    for source, name, parser in (
        (field_overrides, FIELD_OVERRIDES_FILE, parse_field_overrides),
        (journey_mapping, JOURNEY_MAPPING_FILE, parse_journey_mapping),
    ):
        if source is None:
            continue
        source = Path(source)
        if not source.exists():
            raise ClientConfigError(f"{source}: file not found")
        data = _read_yaml(source)
        parser(data, source.name)
        config_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, config_dir / name)
        installed[name] = {
            "sha256": _sha256(config_dir / name),
            "confirmed_by": data.get("confirmed_by"),
            "confirmed_on": str(data.get("confirmed_on")) if data.get("confirmed_on") else None,
        }
    manifest_path = run_dir / "manifest.json"
    if installed and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.setdefault("client_config", {}).update(installed)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return installed


def _top_value_texts(entry: Dict[str, Any]) -> List[str]:
    return [normalize_value(top.get("value")) for top in entry.get("top_values") or []]


def _competes(entry: Dict[str, Any], kind: str) -> bool:
    if entry.get("hubspot_defined"):
        return False
    fill = entry.get("fill_rate")
    if fill is None or float(fill) < COMPETING_MIN_FILL_RATE:
        return False
    values = _top_value_texts(entry)
    if kind == "lifecycle":
        return sum(value.replace(" ", "") in LIFECYCLE_VOCABULARY for value in values) >= 2
    return sum(bool(SOURCE_VOCABULARY.search(value)) for value in values) >= 2


def resolve_canonical_fields(
    run_dir: Path,
    prop_defs: Dict[str, List[Dict[str, Any]]],
    candidate_fields: Dict[str, List[Dict[str, Any]]],
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Choose the field each measurement reads and say how sure that choice is.

    An owner override wins. Otherwise the HubSpot default is used, at medium
    confidence and flagged for confirmation when a populated custom field with
    a matching vocabulary competes with it.
    """
    overrides = load_field_overrides(run_dir)
    names = {obj: {str(d.get("name")) for d in defs} for obj, defs in prop_defs.items()}
    canonical: Dict[str, Dict[str, Any]] = {}
    notes: List[str] = []
    for role, spec in CANONICAL_ROLES.items():
        object_type = spec["object_type"]
        available = names.get(object_type, set())
        competitors = [
            entry for entry in candidate_fields.get(spec["kind"], [])
            if entry.get("object_type") == object_type and _competes(entry, spec["kind"])
        ]
        if role in overrides:
            chosen = overrides[role]
            if chosen not in available:
                raise ClientConfigError(
                    f"{FIELD_OVERRIDES_FILE}: canonical_fields.{role} names '{chosen}', "
                    f"which is not a {spec['object']} property in this snapshot"
                )
            others = [e["field"] for e in competitors if e["field"] != chosen]
            canonical[role] = {
                "object": spec["object"],
                "field": chosen,
                "confidence": "high",
                "requires_confirmation": False,
                "evidence": f"Confirmed by the owner in {CONFIG_DIR}/{FIELD_OVERRIDES_FILE}",
                "competing_fields": others,
            }
            continue
        default = spec["default"]
        if default not in available:
            continue
        rivals = [e for e in competitors if e["field"] != default]
        if rivals:
            described = ", ".join(f"{e['field']} (fill {e.get('fill_rate')}%)" for e in rivals)
            canonical[role] = {
                "object": spec["object"],
                "field": default,
                "confidence": "medium",
                "requires_confirmation": True,
                "evidence": f"HubSpot-defined default; populated custom field(s) compete: {described}",
                "competing_fields": [e["field"] for e in rivals],
            }
            notes.append(
                f"{spec['object'].capitalize()} {role.replace('_', ' ')} is measured with HubSpot's "
                f"{default}, but {described} may be the field the team uses. Confirm it in "
                f"{CONFIG_DIR}/{FIELD_OVERRIDES_FILE} and re-run."
            )
        else:
            canonical[role] = {
                "object": spec["object"],
                "field": default,
                "confidence": "high",
                "requires_confirmation": False,
                "evidence": f"HubSpot-defined {role.replace('_', ' ')} field present in the snapshot",
                "competing_fields": [],
            }
    contact_lifecycle = canonical.get("lifecycle_stage", {}).get("field")
    if contact_lifecycle and contact_lifecycle != "lifecyclestage":
        notes.append(
            "Stage-entry timestamps exist only for HubSpot's lifecyclestage, so stage-path "
            f"checks still use it while other lifecycle checks use {contact_lifecycle}."
        )
    return canonical, notes


def canonical_field(canonical: Dict[str, Dict[str, Any]], role: str) -> str:
    """Field a measurement reads for ``role``; falls back to the HubSpot default."""
    return str((canonical.get(role) or {}).get("field") or CANONICAL_ROLES[role]["default"])
