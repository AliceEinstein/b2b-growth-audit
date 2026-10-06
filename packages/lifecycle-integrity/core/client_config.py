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
# A latest- or last-touch source field records a different fact from the
# original source, so it never competes for that role.
NOT_A_COMPETITOR = {"original_source": re.compile(r"latest|recent|last", re.I)}


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
        excluded = NOT_A_COMPETITOR.get(role)
        competitors = [
            entry for entry in candidate_fields.get(spec["kind"], [])
            if entry.get("object_type") == object_type
            and _competes(entry, spec["kind"])
            and not (excluded and excluded.search(str(entry.get("field"))))
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


# -- drafts and owner questions ------------------------------------------------------

DRAFT_DIR = "client_config_draft"
QUESTIONS_FILE = "questions.json"
SCHEMA_DISCOVERY_OUTPUT = Path("agent_workspace") / "analysis" / "schema_discovery_agent.json"
MAX_EVIDENCE_LEN = 400

ROLE_QUESTIONS = {
    "lifecycle_stage": "Which contact property does your team use as the lifecycle stage?",
    "company_lifecycle_stage": "Which company property does your team use as the lifecycle stage?",
    "original_source": "Which contact property records where a contact originally came from?",
}
JOURNEY_QUESTION = (
    "Which selling motion does each of these source values belong to? "
    "Use unassigned when a value says nothing about how the buyer arrived."
)


def _one_line(text: Any) -> str:
    line = re.sub(r"\s+", " ", str(text or "")).strip()
    return line if len(line) <= MAX_EVIDENCE_LEN else line[: MAX_EVIDENCE_LEN - 1] + "…"


def _agent_proposal(run_dir: Path) -> Tuple[Dict[str, Dict[str, str]], Dict[Tuple[str, str], Dict[str, str]]]:
    """Field and journey suggestions the schema discovery role proposed, if any."""
    path = Path(run_dir) / SCHEMA_DISCOVERY_OUTPUT
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, {}
    proposal = data.get("proposed_client_config") if isinstance(data, dict) else None
    if not isinstance(proposal, dict):
        return {}, {}
    fields: Dict[str, Dict[str, str]] = {}
    for role, entry in (proposal.get("canonical_fields") or {}).items():
        if role not in CANONICAL_ROLES:
            continue
        if isinstance(entry, str):
            entry = {"field": entry}
        if isinstance(entry, dict) and str(entry.get("field") or "").strip():
            fields[role] = {
                "field": str(entry["field"]).strip(),
                "evidence": _one_line(entry.get("evidence")),
            }
    journeys: Dict[Tuple[str, str], Dict[str, str]] = {}
    for entry in proposal.get("journey_mapping") or []:
        if not isinstance(entry, dict) or entry.get("journey") not in MAPPABLE_JOURNEYS:
            continue
        key = (str(entry.get("field") or ""), normalize_value(entry.get("value")))
        if all(key):
            journeys[key] = {"journey": entry["journey"], "evidence": _one_line(entry.get("evidence"))}
    return fields, journeys


def build_confirmation(run_dir: Path) -> Dict[str, Any]:
    """What the owner should confirm, with a suggested answer for each question.

    Suggestions come from, in order: the owner's installed config, the schema
    discovery role's proposal (only fields the audit saw as candidates), and the
    measured default or keyword match.
    """
    run_dir = Path(run_dir)
    try:
        context = yaml.safe_load((run_dir / "crm_context.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        context = {}
    canonical = context.get("canonical_fields") or {}
    candidates = context.get("candidate_fields") or {}
    known_fields = {
        str(entry.get("field"))
        for entries in candidates.values()
        for entry in entries or []
        if isinstance(entry, dict)
    }
    overrides = load_field_overrides(run_dir)
    mapping = load_journey_mapping(run_dir)
    agent_fields, agent_journeys = _agent_proposal(run_dir)

    field_rows: List[Dict[str, Any]] = []
    for role, spec in CANONICAL_ROLES.items():
        current = canonical.get(role) or {}
        proposed = agent_fields.get(role)
        if not current and role not in overrides and not proposed:
            continue  # the snapshot has no such field to measure or confirm
        measured = str(current.get("field") or spec["default"])
        competing = [str(f) for f in current.get("competing_fields") or []]
        suggested, basis, evidence = measured, "measured default", _one_line(current.get("evidence"))
        if role in overrides:
            suggested, basis = overrides[role], "confirmed by the owner"
        elif proposed and proposed["field"] in known_fields | set(competing) | {measured}:
            suggested, basis = proposed["field"], "schema discovery proposal"
            evidence = proposed["evidence"] or evidence
        field_rows.append(
            {
                "role": role,
                "object": spec["object"],
                "question": ROLE_QUESTIONS[role],
                "measured_with": measured,
                "suggested": suggested,
                "alternatives": [f for f in competing if f != suggested]
                + ([measured] if suggested != measured else []),
                "basis": basis,
                "evidence": evidence,
                "needs_confirmation": role not in overrides
                and (bool(current.get("requires_confirmation")) or suggested != measured),
            }
        )

    value_rows: List[Dict[str, Any]] = []
    for row in context.get("source_values") or []:
        field, value = str(row.get("field")), normalize_value(row.get("value"))
        confirmed = mapping.lookup(field, value) if mapping else None
        proposed = agent_journeys.get((field, value))
        if confirmed is not None:
            suggested, basis = confirmed, "confirmed by the owner"
        elif proposed:
            suggested = proposed["journey"]
            basis = "schema discovery proposal" + (f": {proposed['evidence']}" if proposed["evidence"] else "")
        else:
            suggested, basis = str(row.get("keyword_journey") or "unassigned"), str(row.get("keyword_basis") or "")
        value_rows.append(
            {
                "field": field,
                "value": value,
                "deal_count": int(row.get("deal_count") or 0),
                "suggested": suggested,
                "basis": basis,
                "needs_confirmation": confirmed is None,
            }
        )

    questions: List[Dict[str, Any]] = [
        {"id": "field." + row["role"], "kind": "canonical_field", **row}
        for row in field_rows
        if row["needs_confirmation"]
    ]
    open_values = [row for row in value_rows if row["needs_confirmation"]]
    if open_values:
        questions.append(
            {
                "id": "journey_mapping",
                "kind": "journey_mapping",
                "question": JOURNEY_QUESTION,
                "values": open_values,
                "unassigned_deals": int(context.get("unassigned_deals") or 0),
            }
        )
    return {
        "draft_dir": DRAFT_DIR,
        "questions": questions,
        "field_overrides": field_rows,
        "journey_values": value_rows,
        "confirmed": {
            "field_overrides": bool(overrides),
            "journey_mapping": bool(mapping),
        },
    }


def _yaml_key(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def _draft_header(run_dir: Path, what: str) -> List[str]:
    return [
        f"# Draft {what} from audit run {Path(run_dir).name}.",
        "# Check each line against how your team actually works and edit it if needed.",
        "# Lines marked CONFIRM are the open questions in the report.",
        "# Then confirm (this stamps confirmed_by/confirmed_on and rebuilds the audit):",
        f"#   python -m scripts.confirm_client_config --run {Path(run_dir)} --confirmed-by \"<name>\"",
    ]


def _field_overrides_draft(run_dir: Path, rows: List[Dict[str, Any]]) -> str:
    lines = _draft_header(run_dir, "canonical fields") + ["canonical_fields:"]
    for row in rows:
        note = f"{row['object']} {row['role'].replace('_', ' ')} · {row['basis']}"
        if row["alternatives"]:
            note += " · alternatives: " + ", ".join(row["alternatives"])
        if row["needs_confirmation"]:
            note = "CONFIRM · " + note
        lines.append(f"  {row['role']}: {row['suggested']}    # {note}")
    lines += ["confirmed_by: null", "confirmed_on: null"]
    return "\n".join(lines) + "\n"


def _journey_mapping_draft(run_dir: Path, rows: List[Dict[str, Any]]) -> str:
    installed_path = Path(run_dir) / CONFIG_DIR / JOURNEY_MAPPING_FILE
    installed = _read_yaml(installed_path) if installed_path.exists() else {}
    fields: Dict[str, Dict[str, Tuple[str, str]]] = {}
    for prop, table in (installed.get("fields") or {}).items():
        for value, journey in (table or {}).items():
            fields.setdefault(str(prop), {})[normalize_value(value)] = (journey, "confirmed")
    for row in rows:
        if not row["needs_confirmation"]:
            continue
        note = f"CONFIRM · {row['deal_count']} deals · {row['basis']}"
        fields.setdefault(row["field"], {})[row["value"]] = (row["suggested"], note)
    lines = _draft_header(run_dir, "journey mapping")
    lines.append("# Journeys: " + ", ".join(JOURNEY_TYPES) + ", unassigned.")
    lines.append("fields:" if fields else "fields: {}")
    for prop in sorted(fields):
        lines.append(f"  {_yaml_key(prop)}:")
        for value, (journey, note) in fields[prop].items():
            lines.append(f"    {_yaml_key(value)}: {journey}    # {note}")
    values = installed.get("values") or {}
    lines.append("values:" if values else "values: {}")
    for value, journey in values.items():
        lines.append(f"  {_yaml_key(normalize_value(value))}: {journey}    # confirmed")
    lines += ["confirmed_by: null", "confirmed_on: null"]
    return "\n".join(lines) + "\n"


def write_client_config_drafts(run_dir: Path) -> Dict[str, Any]:
    """Write ready-to-confirm config drafts and the owner's questions into the run."""
    run_dir = Path(run_dir)
    confirmation = build_confirmation(run_dir)
    draft_dir = run_dir / DRAFT_DIR
    draft_dir.mkdir(parents=True, exist_ok=True)
    field_text = _field_overrides_draft(run_dir, confirmation["field_overrides"])
    journey_text = _journey_mapping_draft(run_dir, confirmation["journey_values"])
    # A draft that cannot be parsed back is a bug here, never the owner's problem.
    parse_field_overrides(yaml.safe_load(field_text))
    parse_journey_mapping(yaml.safe_load(journey_text))
    (draft_dir / FIELD_OVERRIDES_FILE).write_text(field_text, encoding="utf-8")
    (draft_dir / JOURNEY_MAPPING_FILE).write_text(journey_text, encoding="utf-8")
    (draft_dir / QUESTIONS_FILE).write_text(
        json.dumps(confirmation, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return confirmation


# -- confirmation ---------------------------------------------------------------------


def stamp_confirmation(text: str, confirmed_by: str, confirmed_on: str) -> str:
    """Set confirmed_by / confirmed_on in a config file, keeping its comments."""
    for key, value in (("confirmed_by", confirmed_by), ("confirmed_on", confirmed_on)):
        line = f"{key}: {_yaml_key(value)}"
        text, count = re.subn(rf"(?m)^{key}:.*$", line, text)
        if not count:
            text = text.rstrip("\n") + "\n" + line + "\n"
    return text


def check_against_snapshot(run_dir: Path, overrides: Dict[str, str]) -> List[str]:
    """Every overridden field must be a property of its object in the snapshot."""
    problems = []
    for role, prop in overrides.items():
        object_type = CANONICAL_ROLES[role]["object_type"]
        path = Path(run_dir) / "raw" / f"properties_{object_type}.json"
        try:
            names = {str(d.get("name")) for d in json.loads(path.read_text(encoding="utf-8"))}
        except (OSError, json.JSONDecodeError):
            continue
        if prop not in names:
            problems.append(
                f"canonical_fields.{role} names '{prop}', which is not a "
                f"{CANONICAL_ROLES[role]['object']} property in this snapshot"
            )
    return problems
