"""Audit measurement layer: facts + evidence, never verdicts.

Each module emits measurements — countable facts with evidence rows keyed
by measurement id. Whether a measurement becomes a finding, and at what
severity, is decided by the audit agents (LLM) against the selected audit
profile. No severity thresholds live in this file, by design.

Measurements that cannot be computed (missing association snapshot, no
canonical field confirmed) are emitted with available: false and a note,
so the LLM knows the gap exists instead of inventing numbers around it.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .evidence import ModuleEvidence
from .metrics import (
    is_empty,
    load_association_map,
    median_created_ms,
    parse_created_ms,
    parse_ms,
    pct,
    read_json,
    read_jsonl,
    stage_flags,
)
from .sanitizer import (
    hash_record_id,
    load_or_create_salt,
    sanitize_evidence_value,
)
from .schemas import CrmContext

MODULES = [
    "attribution_trust",
    "lifecycle_funnel",
    "association_architecture",
    "pipeline_hygiene",
    "property_governance",
]

EVIDENCE_MAX = 50

# HubSpot standard lifecycle values considered "MQL or later" for funnel
# progression measurements. Documented fact, not a judgment.
MQL_PLUS_STAGES = {"marketingqualifiedlead", "salesqualifiedlead", "opportunity"}

# Tokens ignored when grouping similar property names (legacy markers).
_NAME_NOISE_TOKENS = {"old", "new", "legacy", "backup", "import", "imported", "hs"}


def _props(record: Dict[str, Any]) -> Dict[str, Any]:
    return record.get("properties") or {}


class Snapshot:
    """Everything the measurement functions need, loaded once."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = Path(run_dir)
        raw = self.run_dir / "raw"
        self.contacts = (
            read_jsonl(raw / "contacts.jsonl") if (raw / "contacts.jsonl").exists() else []
        )
        self.companies = (
            read_jsonl(raw / "companies.jsonl") if (raw / "companies.jsonl").exists() else []
        )
        self.deals = (
            read_jsonl(raw / "deals.jsonl") if (raw / "deals.jsonl").exists() else []
        )
        self.manifest = read_json(self.run_dir / "manifest.json", {})
        self.days = self.manifest.get("days")
        self.full_history = bool(self.manifest.get("full_history", self.days is None))
        self.truncated = self.manifest.get("truncated", {})
        self.pipelines = read_json(raw / "pipelines.json", [])
        self.stage_flags = stage_flags(self.pipelines)
        self.assoc_contact_company = load_association_map(
            raw, "associations_contact_company.jsonl"
        )
        self.assoc_deal_company = load_association_map(
            raw, "associations_deal_company.jsonl"
        )
        self.assoc_deal_contact = load_association_map(
            raw, "associations_deal_contact.jsonl"
        )
        self.source_candidates = read_json(
            self.run_dir / "processed" / "source_field_candidates.json", {}
        )
        self._salt = load_or_create_salt(self.run_dir)

    def hash(self, object_type: str, record_id: Any) -> str:
        return hash_record_id(object_type, record_id, self._salt)

    def deal_stage_is(self, deal: Dict[str, Any], flag: str) -> bool:
        props = _props(deal)
        pipeline = str(props.get("pipeline"))
        stage = str(_props(deal).get("dealstage"))
        return self.stage_flags.get((pipeline, stage), {"closed": False, "won": False})[flag]

    @property
    def relationship_measurements_complete(self) -> bool:
        """Whether cross-object absence claims can cover the full history."""
        return self.full_history and not any(self.truncated.values())

    @property
    def relationship_coverage_note(self) -> str:
        objects = ", ".join(
            sorted(name for name, limited in self.truncated.items() if limited)
        )
        cap = f"; 10k cap reached for {objects}" if objects else ""
        window = f" ({self.days}-day window)" if self.days is not None else ""
        return (
            "cross-object absence measurement is unavailable because the "
            f"snapshot is not full history{window}{cap}"
        )


def _measurement(
    mid: str,
    object_type: str,
    field_name: Optional[str],
    denominator: Optional[int],
    affected: Optional[int],
    description: str,
    *,
    available: bool = True,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": mid,
        "object_type": object_type,
        "field_name": field_name,
        "denominator": denominator,
        "affected_records": affected,
        "affected_percentage": (
            pct(affected, denominator)
            if available and denominator and affected is not None
            else None
        ),
        "available": available,
        "note": note,
        "description": description,
    }


def _unavailable(mid: str, object_type: str, description: str, note: str) -> Dict[str, Any]:
    return _measurement(
        mid, object_type, None, None, None, description, available=False, note=note
    )


def _record_evidence(
    ev: ModuleEvidence,
    snap: Snapshot,
    object_type: str,
    mid: str,
    field: Optional[str],
    records: List[Dict[str, Any]],
    issue_type: str,
    review: str,
) -> None:
    for record in records[:EVIDENCE_MAX]:
        value = _props(record).get(field) if field else None
        ev.add(
            mid,
            object_type,
            snap.hash(object_type, record.get("id")),
            field,
            issue_type,
            sanitize_evidence_value(object_type, field, value),
            review,
        )


def _canonical_contact_field(context: CrmContext, name: str) -> Optional[str]:
    mapping = context.canonical_fields.get(name)
    if mapping is not None and mapping.object == "contact":
        return mapping.field
    return None


# -- modules --------------------------------------------------------------------


def _measure_attribution(
    snap: Snapshot, context: CrmContext, ev: ModuleEvidence
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    source = _canonical_contact_field(context, "original_source")
    if source is None:
        out.append(
            _unavailable(
                "contacts_missing_original_source",
                "contacts",
                "contacts with empty canonical original source",
                "no canonical original_source confirmed in crm_context.yaml",
            )
        )
        return out

    missing = [c for c in snap.contacts if is_empty(_props(c).get(source))]
    out.append(
        _measurement(
            "contacts_missing_original_source",
            "contacts",
            source,
            len(snap.contacts),
            len(missing),
            f"contacts with empty {source}",
        )
    )
    _record_evidence(
        ev, snap, "contacts", "contacts_missing_original_source", source, missing,
        "missing_value", "confirm how source should be captured for these contacts",
    )

    median = median_created_ms(snap.contacts)
    if median is not None:
        recent = [c for c in snap.contacts if (parse_created_ms(c) or 0) > median]
        recent_missing = [c for c in recent if is_empty(_props(c).get(source))]
        out.append(
            _measurement(
                "recent_half_contacts_missing_original_source",
                "contacts",
                source,
                len(recent),
                len(recent_missing),
                f"contacts in the recent half (created after median createdate) with empty {source}",
            )
        )
        _record_evidence(
            ev,
            snap,
            "contacts",
            "recent_half_contacts_missing_original_source",
            source,
            recent_missing,
            "missing_value",
            "confirm how source should be captured for these recent contacts",
        )

    won_deals = [d for d in snap.deals if snap.deal_stage_is(d, "won")]
    if snap.assoc_deal_contact is None:
        out.append(
            _unavailable(
                "closedwon_deals_without_source_trace",
                "deals",
                "closed-won deals with no associated contact having a non-empty canonical source",
                "deal->contact associations unavailable in this snapshot",
            )
        )
    elif not snap.relationship_measurements_complete:
        out.append(
            _unavailable(
                "closedwon_deals_without_source_trace",
                "deals",
                "closed-won deals with no associated contact having a non-empty canonical source",
                snap.relationship_coverage_note,
            )
        )
    else:
        contacts_by_id = {str(c.get("id")): c for c in snap.contacts}

        def has_trace(deal: Dict[str, Any]) -> bool:
            for contact_id in snap.assoc_deal_contact.get(str(deal.get("id")), []):
                contact = contacts_by_id.get(contact_id)
                if contact is not None and not is_empty(_props(contact).get(source)):
                    return True
            return False

        untraced = [d for d in won_deals if not has_trace(d)]
        out.append(
            _measurement(
                "closedwon_deals_without_source_trace",
                "deals",
                source,
                len(won_deals),
                len(untraced),
                f"closed-won deals with no associated contact having non-empty {source}",
            )
        )
        _record_evidence(
            ev, snap, "deals", "closedwon_deals_without_source_trace", None, untraced,
            "no_source_trace", "review how this won deal should be attributed",
        )

    imported = [
        c
        for c in snap.contacts
        if str(_props(c).get("hs_object_source") or "").upper() == "IMPORT"
    ]
    imported_missing = [c for c in imported if is_empty(_props(c).get(source))]
    out.append(
        _measurement(
            "imported_contacts_missing_source",
            "contacts",
            source,
            len(imported),
            len(imported_missing),
            f"contacts created via IMPORT with empty {source}",
        )
    )
    _record_evidence(
        ev,
        snap,
        "contacts",
        "imported_contacts_missing_source",
        source,
        imported_missing,
        "missing_value",
        "confirm source governance for imported contacts",
    )
    return out


def _measure_lifecycle(
    snap: Snapshot, context: CrmContext, ev: ModuleEvidence
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    lifecycle = _canonical_contact_field(context, "lifecycle_stage")
    if lifecycle is None:
        out.append(
            _unavailable(
                "contacts_missing_lifecycle",
                "contacts",
                "contacts with empty canonical lifecycle stage",
                "no canonical lifecycle_stage confirmed in crm_context.yaml",
            )
        )
        return out

    missing = [c for c in snap.contacts if is_empty(_props(c).get(lifecycle))]
    out.append(
        _measurement(
            "contacts_missing_lifecycle",
            "contacts",
            lifecycle,
            len(snap.contacts),
            len(missing),
            f"contacts with empty {lifecycle}",
        )
    )
    _record_evidence(
        ev, snap, "contacts", "contacts_missing_lifecycle", lifecycle, missing,
        "missing_value", "confirm lifecycle handling for these contacts",
    )

    customers = [
        c for c in snap.contacts if str(_props(c).get(lifecycle)) == "customer"
    ]
    mql_plus = [
        c for c in snap.contacts if str(_props(c).get(lifecycle)) in MQL_PLUS_STAGES
    ]
    if snap.assoc_deal_contact is None:
        note = "deal->contact associations unavailable in this snapshot"
        out.append(
            _unavailable(
                "customers_without_closedwon_deal",
                "contacts",
                "customer-stage contacts with no associated closed-won deal",
                note,
            )
        )
        out.append(
            _unavailable(
                "mql_plus_contacts_without_deal",
                "contacts",
                "MQL-or-later contacts with no associated deal",
                note,
            )
        )
    elif not snap.relationship_measurements_complete:
        note = snap.relationship_coverage_note
        out.append(
            _unavailable(
                "customers_without_closedwon_deal",
                "contacts",
                "customer-stage contacts with no associated closed-won deal",
                note,
            )
        )
        out.append(
            _unavailable(
                "mql_plus_contacts_without_deal",
                "contacts",
                "MQL-or-later contacts with no associated deal",
                note,
            )
        )
    else:
        contacts_with_won: Set[str] = set()
        contacts_with_deal: Set[str] = set()
        for deal in snap.deals:
            contact_ids = snap.assoc_deal_contact.get(str(deal.get("id")), [])
            contacts_with_deal.update(contact_ids)
            if snap.deal_stage_is(deal, "won"):
                contacts_with_won.update(contact_ids)

        cust_missing = [
            c for c in customers if str(c.get("id")) not in contacts_with_won
        ]
        out.append(
            _measurement(
                "customers_without_closedwon_deal",
                "contacts",
                lifecycle,
                len(customers),
                len(cust_missing),
                "customer-stage contacts with no associated closed-won deal",
            )
        )
        _record_evidence(
            ev, snap, "contacts", "customers_without_closedwon_deal", lifecycle,
            cust_missing, "funnel_inconsistency",
            "confirm whether this customer should have a won deal on record",
        )

        mql_missing = [
            c for c in mql_plus if str(c.get("id")) not in contacts_with_deal
        ]
        out.append(
            _measurement(
                "mql_plus_contacts_without_deal",
                "contacts",
                lifecycle,
                len(mql_plus),
                len(mql_missing),
                f"contacts in {sorted(MQL_PLUS_STAGES)} with no associated deal",
            )
        )
        _record_evidence(
            ev,
            snap,
            "contacts",
            "mql_plus_contacts_without_deal",
            lifecycle,
            mql_missing,
            "funnel_inconsistency",
            "confirm whether these contacts should have an associated deal",
        )
    return out


def _measure_associations(
    snap: Snapshot, context: CrmContext, ev: ModuleEvidence
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    specs = [
        (
            "contacts_without_company",
            "contacts",
            snap.contacts,
            snap.assoc_contact_company,
            "contacts with no associated company",
        ),
        (
            "deals_without_company",
            "deals",
            snap.deals,
            snap.assoc_deal_company,
            "deals with no associated company",
        ),
        (
            "deals_without_contact",
            "deals",
            snap.deals,
            snap.assoc_deal_contact,
            "deals with no associated contact",
        ),
    ]
    for mid, object_type, records, assoc, description in specs:
        if assoc is None:
            out.append(
                _unavailable(
                    mid, object_type, description,
                    "association snapshot unavailable",
                )
            )
            continue
        orphans = [r for r in records if not assoc.get(str(r.get("id")))]
        out.append(
            _measurement(mid, object_type, None, len(records), len(orphans), description)
        )
        _record_evidence(
            ev, snap, object_type, mid, None, orphans, "missing_association",
            "review whether this record should be linked",
        )

    with_domain = [
        c for c in snap.companies if not is_empty(_props(c).get("domain"))
    ]
    domain_counts: Dict[str, int] = {}
    for company in with_domain:
        domain = str(_props(company).get("domain")).strip().lower()
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
    dupes = [
        c
        for c in with_domain
        if domain_counts[str(_props(c).get("domain")).strip().lower()] > 1
    ]
    out.append(
        _measurement(
            "duplicate_company_domain_candidates",
            "companies",
            "domain",
            len(with_domain),
            len(dupes),
            "companies sharing a domain with at least one other company",
        )
    )
    _record_evidence(
        ev, snap, "companies", "duplicate_company_domain_candidates", "domain",
        dupes, "duplicate_domain_candidate",
        "human review — never merge automatically",
    )

    no_domain = [c for c in snap.companies if is_empty(_props(c).get("domain"))]
    out.append(
        _measurement(
            "companies_without_domain",
            "companies",
            "domain",
            len(snap.companies),
            len(no_domain),
            "companies with empty domain",
        )
    )
    _record_evidence(
        ev,
        snap,
        "companies",
        "companies_without_domain",
        "domain",
        no_domain,
        "missing_value",
        "review whether this company should have a domain",
    )
    return out


def _measure_pipeline_hygiene(
    snap: Snapshot, context: CrmContext, ev: ModuleEvidence
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    now_ms = time.time() * 1000

    open_deals = [d for d in snap.deals if not snap.deal_stage_is(d, "closed")]
    past_due = [
        d
        for d in open_deals
        if (parse_ms(_props(d).get("closedate")) or now_ms) < now_ms
    ]
    out.append(
        _measurement(
            "open_deals_past_close_date",
            "deals",
            "closedate",
            len(open_deals),
            len(past_due),
            "open deals whose close date is in the past",
        )
    )
    _record_evidence(
        ev, snap, "deals", "open_deals_past_close_date", "closedate", past_due,
        "past_due_close_date", "review close date or stage with the deal owner",
    )

    for mid, field in [
        ("deals_without_owner", "hubspot_owner_id"),
        ("deals_without_amount", "amount"),
    ]:
        affected = [d for d in snap.deals if is_empty(_props(d).get(field))]
        out.append(
            _measurement(
                mid, "deals", field, len(snap.deals), len(affected),
                f"deals with empty {field}",
            )
        )
        _record_evidence(
            ev, snap, "deals", mid, field, affected, "missing_value",
            "confirm with the deal owner",
        )

    known = {str(p.get("id")) for p in snap.pipelines}
    unknown = [
        d for d in snap.deals if str(_props(d).get("pipeline")) not in known
    ]
    out.append(
        _measurement(
            "deals_in_unknown_pipeline",
            "deals",
            "pipeline",
            len(snap.deals),
            len(unknown),
            "deals referencing a pipeline not present in pipeline definitions",
        )
    )
    _record_evidence(
        ev,
        snap,
        "deals",
        "deals_in_unknown_pipeline",
        "pipeline",
        unknown,
        "unknown_reference",
        "confirm the pipeline definition and deal assignment",
    )

    out.append(
        _unavailable(
            "deals_stuck_in_stage",
            "deals",
            "deals stuck in a stage beyond a normal cycle",
            "stage-entry timestamps are not fetched in v1; do not infer this",
        )
    )
    return out


def _measure_property_governance(
    snap: Snapshot, context: CrmContext, ev: ModuleEvidence
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    all_candidates = []
    for object_type, entries in snap.source_candidates.items():
        for entry in entries:
            all_candidates.append((object_type, entry))

    decayed = []
    for object_type, entry in all_candidates:
        stats = entry.get("stats") or {}
        older = stats.get("fill_rate_older_half")
        recent = stats.get("fill_rate_recent_half")
        if older is not None and recent is not None and older > 0 and recent == 0:
            decayed.append((object_type, entry))
    out.append(
        _measurement(
            "decayed_source_fields",
            "properties",
            None,
            len(all_candidates),
            len(decayed),
            "source-like fields filled in the older half of records but never in the recent half",
        )
    )
    for object_type, entry in decayed[:EVIDENCE_MAX]:
        stats = entry.get("stats") or {}
        ev.add(
            "decayed_source_fields",
            object_type,
            "-",
            entry.get("field"),
            "usage_decay",
            f"older_half {stats.get('fill_rate_older_half')}% recent_half {stats.get('fill_rate_recent_half')}%",
            "confirm whether this field is legacy before any governance action",
        )

    def name_key(field: str) -> str:
        tokens = [
            t
            for t in re.split(r"[^a-z]+", field.lower())
            if t and t not in _NAME_NOISE_TOKENS and not t.isdigit()
        ]
        return "_".join(sorted(tokens))

    groups: Dict[str, List[str]] = {}
    for object_type, entry in all_candidates:
        groups.setdefault(
            f"{object_type}:{name_key(entry.get('field', ''))}", []
        ).append(entry.get("field"))
    collisions = {k: v for k, v in groups.items() if len(v) > 1}
    collided_fields = [f for fields in collisions.values() for f in fields]
    out.append(
        _measurement(
            "similar_name_field_groups",
            "properties",
            None,
            len(all_candidates),
            len(collided_fields),
            "source-like fields whose normalized names collide (duplicate candidates)",
        )
    )
    for key, fields in list(collisions.items())[:EVIDENCE_MAX]:
        ev.add(
            "similar_name_field_groups",
            key.split(":", 1)[0],
            "-",
            ", ".join(sorted(fields)),
            "name_collision",
            None,
            "human review — potential duplicate properties",
        )
    return out


# -- entry point ------------------------------------------------------------------


def measure_all(run_dir: Path, context: CrmContext) -> Dict[str, Dict[str, Any]]:
    """Run all module measurements. Returns {module: module_document}."""
    run_dir = Path(run_dir)
    snap = Snapshot(run_dir)
    evidence_dir = run_dir / "evidence"

    module_fns = [
        ("attribution_trust", _measure_attribution),
        ("lifecycle_funnel", _measure_lifecycle),
        ("association_architecture", _measure_associations),
        ("pipeline_hygiene", _measure_pipeline_hygiene),
        ("property_governance", _measure_property_governance),
    ]
    out: Dict[str, Dict[str, Any]] = {}
    for module, fn in module_fns:
        with ModuleEvidence(evidence_dir / f"{module}.csv") as ev:
            measurements = fn(snap, context, ev)
        out[module] = {
            "module": module,
            "evidence_file": f"evidence/{module}.csv",
            "evidence_rows": ev.count,
            "snapshot_coverage": {
                "days": snap.days,
                "full_history": snap.full_history,
                "truncated": snap.truncated,
                "relationship_measurements_complete": snap.relationship_measurements_complete,
            },
            "measurements": measurements,
        }
    return out
