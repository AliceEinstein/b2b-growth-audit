"""Build the sanitized Journey Evidence Store from one local snapshot."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from connectors.hubspot.normalize import write_json

from .client_config import (
    JourneyMapping,
    canonical_field,
    load_journey_mapping,
    normalize_value,
    resolve_canonical_fields,
)
from .journey_confidence import build_registry
from .metrics import (
    is_empty,
    load_association_map,
    parse_created_ms,
    pct,
    read_json,
    read_jsonl,
    stage_flags,
)
from .profiler import profile_run
from .sanitizer import hash_record_id, load_or_create_salt, sanitize_untrusted_value
from .stage_transitions import build_stage_transition_summary
from .validators import validate_snapshot_completed

INTENT_PATTERNS = {
    "lifecycle": re.compile(r"lifecycle|lead.?status|stage", re.I),
    "source": re.compile(r"source|attribution|campaign|channel|utm|medium", re.I),
    "deal_type": re.compile(r"deal.?type|motion|new.?business", re.I),
    "account_tier": re.compile(r"account.?tier|target.?account|named.?account|\babm\b", re.I),
    "partner": re.compile(r"partner|referr|reseller|channel", re.I),
    "expansion": re.compile(r"renew|expansion|upsell|cross.?sell", re.I),
    "high_intent": re.compile(
        r"intent|hand.?rais|demo|contact.?sales|sales.?request|meeting|book|"
        r"positive.?reply|response|conversion|form|inquir|qualif|mql|sql",
        re.I,
    ),
}

JOURNEY_KEYWORDS = {
    "inbound_new_business": (
        "inbound", "organic", "paid", "direct", "social", "email", "demo", "form",
        "contact sales", "hand raiser", "webinar", "trade show", "conference", "event",
    ),
    "outbound_sales_led": ("outbound", "sdr", "prospect", "import", "outreach"),
    "abm_account_based": ("abm", "target account", "account tier", "named account", "executive briefing"),
    # A bare "referral" is ambiguous (customer, executive or partner), so it
    # maps to no journey unless config/journey_mapping.yaml says otherwise.
    "partner_led": ("partner", "reseller", "channel partner"),
    "expansion_renewal": (
        "expansion", "renewal", "renew", "upsell", "up sell", "cross sell",
        "customer success", "account review",
    ),
}
# Portal-level evidence that a motion exists is broader than the terms that
# assign one record: referral fields and values suggest a referral or partner
# program even though a single "referral" value can't say which.
JOURNEY_EVIDENCE_KEYWORDS = {
    **JOURNEY_KEYWORDS,
    "partner_led": JOURNEY_KEYWORDS["partner_led"] + ("referral",),
}
JOURNEY_CHECK_ORDER = (
    "expansion_renewal",
    "partner_led",
    "abm_account_based",
    "outbound_sales_led",
    "inbound_new_business",
)
# A deal's own pipeline or deal type naming new business outranks expansion
# hints on its linked company or contacts.
NEW_BUSINESS_MARKERS = ("new business", "newbusiness", "new logo")
TRUTHY_FLAG_VALUES = {"true", "yes", "1"}

IDENTITY_FIELDS = {"email", "firstname", "lastname", "phone", "mobilephone", "name", "dealname"}
MQL_PLUS = {"marketingqualifiedlead", "salesqualifiedlead", "opportunity", "customer", "evangelist"}
QUALIFIED_PRE_DEAL_STAGES = {
    "marketingqualifiedlead",
    "salesqualifiedlead",
    "opportunity",
}
POSITIVE_INTENT_VALUE = re.compile(
    r"(^true$|^yes$|requested|request|submitted|booked|qualified|high.?intent|"
    r"hand.?rais|demo|contact.?sales|positive.?reply|meeting|mql|sql)",
    re.I,
)


def _props(record: Dict[str, Any]) -> Dict[str, Any]:
    return record.get("properties") or {}


def _safe_text(values: Iterable[Any]) -> str:
    return " ".join(str(v).lower().replace("_", " ") for v in values if v not in (None, ""))


def _matched_keywords(text: str, keywords: Iterable[str]) -> List[str]:
    """Whole-word matches, allowing a plural "s"; "paid" no longer hits "unpaid"."""
    return [
        keyword
        for keyword in keywords
        if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}s?(?![a-z0-9])", text)
    ]


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return bool(_matched_keywords(text, keywords))


def _candidate_fields(
    prop_defs: Dict[str, List[Dict[str, Any]]],
    usage: Dict[str, Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    result: Dict[str, List[Dict[str, Any]]] = {intent: [] for intent in INTENT_PATTERNS}
    for object_type, definitions in prop_defs.items():
        for definition in definitions:
            field = str(definition.get("name") or "")
            label = str(definition.get("label") or "")
            text = f"{field} {label}"
            for intent, pattern in INTENT_PATTERNS.items():
                if not pattern.search(text):
                    continue
                stats = usage.get(object_type, {}).get(field, {})
                result[intent].append(
                    {
                        "object_type": object_type,
                        "field": field,
                        "label": sanitize_untrusted_value(label),
                        "hubspot_defined": bool(definition.get("hubspotDefined")),
                        "fill_rate": stats.get("fill_rate"),
                        "fill_rate_recent_half": stats.get("fill_rate_recent_half"),
                        "distinct_count": stats.get("distinct_count"),
                        "top_values": stats.get("top_values"),
                    }
                )
    return result


def _field_signal_text(fields: Dict[str, List[Dict[str, Any]]]) -> str:
    values: List[Any] = []
    for entries in fields.values():
        for entry in entries:
            values.extend([entry.get("field"), entry.get("label")])
            for top in entry.get("top_values") or []:
                values.append(top.get("value"))
    return _safe_text(values)


def _invert(mapping: Optional[Dict[str, List[str]]]) -> Dict[str, List[str]]:
    inverse: Dict[str, List[str]] = defaultdict(list)
    for source, targets in (mapping or {}).items():
        for target in targets:
            inverse[str(target)].append(str(source))
    return dict(inverse)


def _owner_summary(records: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    result = {}
    for object_type, rows in records.items():
        owned = sum(1 for row in rows if not is_empty(_props(row).get("hubspot_owner_id")))
        result[object_type] = {
            "total": len(rows),
            "with_owner": owned,
            "coverage_pct": pct(owned, len(rows)),
        }
    return result


def _activity_summary(raw: Path) -> Dict[str, Any]:
    result: Dict[str, Any] = {"available": False, "metadata_only": True, "objects": {}}
    for object_type in ("tasks", "meetings", "notes", "calls", "emails", "communications"):
        path = raw / f"{object_type}.jsonl"
        if not path.exists():
            continue
        rows = read_jsonl(path)
        with_owner = sum(1 for row in rows if not is_empty(_props(row).get("hubspot_owner_id")))
        result["objects"][object_type] = {
            "count": len(rows),
            "owner_coverage_pct": pct(with_owner, len(rows)),
        }
        result["available"] = True
    if not result["available"]:
        result["limitation"] = "Activity metadata was not requested or unavailable."
    return result


def _intent_contact_signals(index: Dict[str, Any], contact_hash: str) -> List[str]:
    """Translate sanitized event evidence into journey-classification hints."""
    rows = index.get(contact_hash) or []
    signals: List[str] = []
    for row in rows:
        strength = str(row.get("signal_strength") or "").lower()
        if strength not in {"high", "medium"}:
            continue
        source = str(row.get("source") or "intent")
        signal_type = str(row.get("signal_type") or "signal")
        signals.append(f"observed {strength}-strength {source} {signal_type} signal")
    return list(dict.fromkeys(signals))


SIGNAL_FIELDS = {
    "hs_analytics_source",
    "hs_latest_source",
    "hs_object_source",
    "dealtype",
    "pipeline",
    "lifecyclestage",
}


def _record_values(record: Dict[str, Any], candidate_names: set[str]) -> List[Tuple[str, Any]]:
    props = _props(record)
    return [
        (field, value)
        for field, value in props.items()
        if field not in IDENTITY_FIELDS
        and (field in candidate_names or field in SIGNAL_FIELDS)
        and not is_empty(value)
    ]


NON_TEXT_VALUE = re.compile(
    r"^\d{4}-\d{2}-\d{2}"          # dates and timestamps
    r"|^[\d.,:\s+-]+$"              # numbers
    r"|@|://|^www\."                # emails and URLs
    r"|^(?=\S*\d)[a-z0-9_-]{8,}$",  # opaque keys and IDs
    re.I,
)


def _name_counts(value: Any) -> bool:
    """Whether a property name is evidence alongside this value.

    A name says something when the property is a set flag (is_partner = true)
    or holds free text (partner_source = "Acme"). It says nothing beside a
    date, number, email, URL or ID: ns_renewal_date on a company, or
    ns_source_email on a contact, must not label the record expansion or
    inbound. Empty properties never count.
    """
    text = str(value).strip()
    return text.lower() in TRUTHY_FLAG_VALUES or not NON_TEXT_VALUE.search(text)


def _record_signal_text(record: Dict[str, Any], candidate_names: set[str]) -> str:
    values: List[Any] = []
    for field, value in _record_values(record, candidate_names):
        if _name_counts(value):
            values.append(field)
        values.append(value)
    return _safe_text(values)


def _tier_evidence(
    records: List[Dict[str, Any]],
    candidate_names: set[str],
    mapping: Optional[JourneyMapping],
) -> Tuple[List[Tuple[str, str]], str]:
    """Owner-mapped journeys and keyword text for one group of records.

    A value the owner mapped (to a journey or to "unassigned") is decided by
    the mapping and left out of keyword matching.
    """
    mapped: List[Tuple[str, str]] = []
    values: List[Any] = []
    for record in records:
        for field, value in _record_values(record, candidate_names):
            journey = mapping.lookup(field, value) if mapping else None
            if journey is None:
                if _name_counts(value):
                    values.append(field)
                values.append(value)
            elif journey != "unassigned":
                mapped.append((journey, f"{field}={normalize_value(value)}"))
    return mapped, _safe_text(values)


def _classify_tiers(
    tiers: List[Tuple[str, List[Tuple[str, str]], str, str]],
    *,
    skip_expansion: bool,
    base_confidence: int,
    cap: int,
    term_label: str,
) -> Optional[tuple[str, int, List[str]]]:
    """First tier with a mapped journey or a keyword match decides."""
    for source, mapped, text, text_without_pipeline in tiers:
        candidates = [
            (journey, evidence)
            for journey, evidence in mapped
            if not (journey == "expansion_renewal" and skip_expansion)
        ]
        if candidates:
            candidates.sort(key=lambda item: JOURNEY_CHECK_ORDER.index(item[0]))
            journey = candidates[0][0]
            evidence = [item for j, item in candidates if j == journey]
            return (
                journey,
                90,
                [f"mapped in config/journey_mapping.yaml: {', '.join(evidence[:3])} (on {source})"],
            )
        for journey in JOURNEY_CHECK_ORDER:
            if journey == "expansion_renewal" and skip_expansion:
                continue
            # Inbound terms such as "direct" are not read from pipeline labels.
            haystack = text_without_pipeline if journey == "inbound_new_business" else text
            matched = _matched_keywords(haystack, JOURNEY_KEYWORDS[journey])
            if matched:
                return (
                    journey,
                    min(cap, base_confidence + len(matched) * 10),
                    [f"{term_label}: {', '.join(matched[:3])} (on {source})"],
                )
    return None


def classify_deal(
    deal: Dict[str, Any],
    *,
    linked_contacts: List[Dict[str, Any]],
    linked_companies: List[Dict[str, Any]],
    pipeline_label: str,
    candidate_names: set[str],
    journey_mapping: Optional[JourneyMapping] = None,
) -> tuple[str, int, List[str]]:
    pipeline_text = pipeline_label.lower().replace("_", " ")
    full_own_text = _record_signal_text(deal, candidate_names) + " " + pipeline_text
    deal_mapped, deal_text = _tier_evidence([deal], candidate_names, journey_mapping)
    # A deal's own pipeline or deal type naming new business outranks
    # expansion hints on its linked company or contacts.
    explicit_new_business = (
        _contains_any(full_own_text, NEW_BUSINESS_MARKERS)
        and not _contains_any(full_own_text, JOURNEY_KEYWORDS["expansion_renewal"])
        and not any(journey == "expansion_renewal" for journey, _ in deal_mapped)
    )
    # The deal's own fields and pipeline decide first. Linked contacts, then
    # linked companies, only fill in when the deal itself carries no signal,
    # so one referral contact can't relabel a deal with its own source.
    contact_mapped, contact_text = _tier_evidence(linked_contacts, candidate_names, journey_mapping)
    company_mapped, company_text = _tier_evidence(linked_companies, candidate_names, journey_mapping)
    result = _classify_tiers(
        [
            ("deal", deal_mapped, deal_text + " " + pipeline_text, deal_text),
            ("linked contacts", contact_mapped, contact_text, contact_text),
            ("linked companies", company_mapped, company_text, company_text),
        ],
        skip_expansion=explicit_new_business,
        base_confidence=55,
        cap=95,
        term_label="matched journey terms",
    )
    return result or ("unassigned", 20, ["no journey-specific source, pipeline, or field signal"])


def contact_intent_signals(
    contact: Dict[str, Any],
    fields: Dict[str, List[Dict[str, Any]]],
    lifecycle_field: str = "lifecyclestage",
) -> List[str]:
    """Return structural HubSpot signals that place a contact in a potential
    recoverable-pipeline cohort. Values never leave the deterministic layer."""
    props = _props(contact)
    signals: List[str] = []
    stage = normalize_value(props.get(lifecycle_field)).replace(" ", "")
    if stage in QUALIFIED_PRE_DEAL_STAGES:
        signals.append(f"lifecycle stage {stage}")
    for entry in fields.get("high_intent", []):
        if entry.get("object_type") != "contacts":
            continue
        field = str(entry.get("field") or "")
        value = props.get(field)
        if is_empty(value) or not POSITIVE_INTENT_VALUE.search(str(value)):
            continue
        signals.append(f"positive signal in {field}")
    return list(dict.fromkeys(signals))


def classify_contact(
    contact: Dict[str, Any],
    *,
    linked_companies: List[Dict[str, Any]],
    candidate_names: set[str],
    intent_signals: List[str],
    journey_mapping: Optional[JourneyMapping] = None,
) -> tuple[str, int, List[str]]:
    # The contact's own fields and signals decide first; linked companies only
    # fill in when the contact carries no journey signal. "positive signal in
    # <property>" entries are left out: they would match on property names.
    contact_mapped, contact_text = _tier_evidence([contact], candidate_names, journey_mapping)
    signal_text = _safe_text(s for s in intent_signals if not s.startswith("positive signal in "))
    company_mapped, company_text = _tier_evidence(linked_companies, candidate_names, journey_mapping)
    own_text = " ".join([contact_text, signal_text])
    result = _classify_tiers(
        [
            ("contact", contact_mapped, own_text, own_text),
            ("linked companies", company_mapped, company_text, company_text),
        ],
        skip_expansion=False,
        base_confidence=50,
        cap=90,
        term_label="matched contact journey terms",
    )
    return result or ("unassigned", 25, ["high-intent signal present but journey type is unclassified"])


def build_journey_evidence_store(run_dir: Path) -> Dict[str, Any]:
    run_dir = Path(run_dir)
    problems = validate_snapshot_completed(run_dir)
    if problems:
        raise ValueError("cannot build journey evidence: " + problems[0])
    processed = run_dir / "processed"
    if not (processed / "property_usage_summary.json").exists():
        profile_run(run_dir)
    raw = run_dir / "raw"
    records = {
        obj: read_jsonl(raw / f"{obj}.jsonl") if (raw / f"{obj}.jsonl").exists() else []
        for obj in ("contacts", "companies", "deals")
    }
    by_id = {obj: {str(row.get("id")): row for row in rows} for obj, rows in records.items()}
    prop_defs = {
        obj: read_json(raw / f"properties_{obj}.json", [])
        for obj in records
    }
    usage = read_json(processed / "property_usage_summary.json", {})
    fields = _candidate_fields(prop_defs, usage)
    canonical, canonical_notes = resolve_canonical_fields(run_dir, prop_defs, fields)
    journey_mapping = load_journey_mapping(run_dir)
    contact_lifecycle_field = canonical_field(canonical, "lifecycle_stage")
    intent_summary = read_json(processed / "intent_signal_summary.json", {})
    intent_index = read_json(processed / "intent_record_index.json", {}).get("contacts", {})
    candidate_names = {
        entry["field"] for entries in fields.values() for entry in entries
    }
    pipeline_summary = read_json(processed / "pipeline_summary.json", {"pipelines": []})
    pipeline_labels = {
        str(p.get("pipeline_id")): str(p.get("label") or "")
        for p in pipeline_summary.get("pipelines", [])
    }
    pipeline_text = _safe_text(
        [
            p.get("label")
            for p in pipeline_summary.get("pipelines", [])
        ]
        + [
            stage.get("label")
            for p in pipeline_summary.get("pipelines", [])
            for stage in p.get("stages", [])
        ]
    )
    contact_company = load_association_map(raw, "associations_contact_company.jsonl")
    deal_company = load_association_map(raw, "associations_deal_company.jsonl")
    deal_contact = load_association_map(raw, "associations_deal_contact.jsonl")
    company_contacts = _invert(contact_company)
    company_deals = _invert(deal_company)
    contact_deals = _invert(deal_contact)

    chronological_total = chronological_before = 0
    deals_without_mql = 0
    for deal in records["deals"]:
        deal_id = str(deal.get("id"))
        deal_ms = parse_created_ms(deal)
        linked = [by_id["contacts"].get(i) for i in (deal_contact or {}).get(deal_id, [])]
        linked = [row for row in linked if row]
        if not any(
            normalize_value(_props(row).get(contact_lifecycle_field)).replace(" ", "") in MQL_PLUS
            for row in linked
        ):
            deals_without_mql += 1
        for contact in linked:
            contact_ms = parse_created_ms(contact)
            if deal_ms is not None and contact_ms is not None:
                chronological_total += 1
                chronological_before += int(contact_ms <= deal_ms)

    pipelines = read_json(raw / "pipelines.json", [])
    flags = stage_flags(pipelines)
    won_deal_ids = {
        str(deal.get("id"))
        for deal in records["deals"]
        if flags.get(
            (str(_props(deal).get("pipeline")), str(_props(deal).get("dealstage"))),
            {},
        ).get("won")
    }
    prior_won_and_new = sum(
        1
        for deal_ids in company_deals.values()
        if any(i in won_deal_ids for i in deal_ids)
        and any(i not in won_deal_ids for i in deal_ids)
    )
    multi_contact_companies = sum(1 for ids in company_contacts.values() if len(ids) >= 2)
    owners = _owner_summary(records)
    association_summary = read_json(processed / "association_summary.json", {})
    available_coverages = [
        float(item.get("coverage_pct") or 0)
        for item in association_summary.values()
        if item.get("available")
    ]
    association_pct = round(sum(available_coverages) / len(available_coverages), 1) if available_coverages else 0
    dated_records = [row for rows in records.values() for row in rows if parse_created_ms(row) is not None]
    total_records = sum(len(rows) for rows in records.values())
    temporal_pct = pct(len(dated_records), total_records) or 0
    field_text = _field_signal_text(fields)
    manifest = read_json(run_dir / "manifest.json", {})
    truncated_objects = sorted(
        name for name, limited in (manifest.get("truncated") or {}).items() if limited
    )

    # Assign records before scoring portal-level patterns. This lets the
    # confidence engine distinguish a journey-specific object path from generic
    # facts such as "records have dates" or "associations exist".
    salt = load_or_create_salt(run_dir)
    assignments = []
    assignment_counts: Counter[str] = Counter()
    contact_assignment_counts: Counter[str] = Counter()
    high_intent_rows: List[Dict[str, Any]] = []
    for deal in records["deals"]:
        deal_id = str(deal.get("id"))
        linked_contacts = [
            by_id["contacts"][i]
            for i in (deal_contact or {}).get(deal_id, [])
            if i in by_id["contacts"]
        ]
        linked_companies = [
            by_id["companies"][i]
            for i in (deal_company or {}).get(deal_id, [])
            if i in by_id["companies"]
        ]
        journey, confidence, evidence = classify_deal(
            deal,
            linked_contacts=linked_contacts,
            linked_companies=linked_companies,
            pipeline_label=pipeline_labels.get(str(_props(deal).get("pipeline")), ""),
            candidate_names=candidate_names,
            journey_mapping=journey_mapping,
        )
        assignment_counts[journey] += 1
        assignments.append(
            {
                "record_id_hash": hash_record_id("deals", deal_id, salt),
                "object_type": "deals",
                "assigned_journey": journey,
                "assignment_confidence": confidence,
                "evidence": evidence,
            }
        )

    for contact in records["contacts"]:
        contact_id = str(contact.get("id"))
        contact_hash = hash_record_id("contacts", contact_id, salt)
        intent_signals = contact_intent_signals(contact, fields, contact_lifecycle_field)
        intent_signals.extend(_intent_contact_signals(intent_index, contact_hash))
        intent_signals = list(dict.fromkeys(intent_signals))
        if not intent_signals:
            continue
        linked_companies = [
            by_id["companies"][company_id]
            for company_id in (contact_company or {}).get(contact_id, [])
            if company_id in by_id["companies"]
        ]
        journey, confidence, evidence = classify_contact(
            contact,
            linked_companies=linked_companies,
            candidate_names=candidate_names,
            intent_signals=intent_signals,
            journey_mapping=journey_mapping,
        )
        has_owner = not is_empty(_props(contact).get("hubspot_owner_id"))
        has_deal = bool(contact_deals.get(contact_id)) if deal_contact is not None else None
        contact_assignment_counts[journey] += 1
        assignment = {
            "record_id_hash": contact_hash,
            "object_type": "contacts",
            "assigned_journey": journey,
            "assignment_confidence": confidence,
            "evidence": evidence + intent_signals,
            "high_intent": True,
            "has_owner": has_owner,
            "has_associated_deal": has_deal,
            "intent_signal_count": len(_intent_contact_signals(intent_index, contact_hash)),
        }
        assignments.append(assignment)
        high_intent_rows.append(assignment)

    inbound_source_records = sum(
        1
        for contact in records["contacts"]
        if _contains_any(
            _safe_text(
                [
                    _props(contact).get("hs_analytics_source"),
                    _props(contact).get("hs_latest_source"),
                ]
            ),
            JOURNEY_KEYWORDS["inbound_new_business"],
        )
    )
    stage_transitions = build_stage_transition_summary(
        records["contacts"], records["companies"], records["deals"]
    )
    # A timestamped passage through MQL is direct funnel evidence — much
    # stronger than "contact was created before deal".
    mql_progressions = stage_transitions["contacts"]["mql_progressions"]
    deal_count = len(records["deals"])
    assigned_path_strengths = {
        journey: pct(assignment_counts.get(journey, 0), deal_count) or 0
        for journey in JOURNEY_KEYWORDS
    }
    high_intent_count = len(high_intent_rows)
    contact_path_strengths = {
        journey: pct(contact_assignment_counts.get(journey, 0), high_intent_count) or 0
        for journey in JOURNEY_KEYWORDS
    }
    path_strengths = {
        "inbound_new_business": max(
            pct(chronological_before, chronological_total) or 0,
            pct(inbound_source_records, len(records["contacts"])) or 0,
            pct(mql_progressions, len(records["contacts"])) or 0,
            assigned_path_strengths["inbound_new_business"],
            contact_path_strengths["inbound_new_business"],
        ),
        "outbound_sales_led": max(
            pct(deals_without_mql, deal_count) or 0,
            assigned_path_strengths["outbound_sales_led"],
            contact_path_strengths["outbound_sales_led"],
        ),
        "abm_account_based": max(
            pct(multi_contact_companies, len(records["companies"])) or 0,
            assigned_path_strengths["abm_account_based"],
            contact_path_strengths["abm_account_based"],
        ),
        "partner_led": max(
            assigned_path_strengths["partner_led"],
            contact_path_strengths["partner_led"],
        ),
        "expansion_renewal": max(
            pct(prior_won_and_new, len(records["companies"])) or 0,
            assigned_path_strengths["expansion_renewal"],
            contact_path_strengths["expansion_renewal"],
        ),
    }
    material = {
        "inbound_new_business": max(
            chronological_before,
            inbound_source_records,
            mql_progressions,
            assignment_counts.get("inbound_new_business", 0),
            contact_assignment_counts.get("inbound_new_business", 0),
        ),
        "outbound_sales_led": max(
            deals_without_mql,
            assignment_counts.get("outbound_sales_led", 0),
            contact_assignment_counts.get("outbound_sales_led", 0),
        ),
        "abm_account_based": max(
            multi_contact_companies,
            assignment_counts.get("abm_account_based", 0),
            contact_assignment_counts.get("abm_account_based", 0),
        ),
        "partner_led": max(
            assignment_counts.get("partner_led", 0),
            contact_assignment_counts.get("partner_led", 0),
        ),
        "expansion_renewal": max(
            prior_won_and_new,
            assignment_counts.get("expansion_renewal", 0),
            contact_assignment_counts.get("expansion_renewal", 0),
        ),
    }
    journey_signals: Dict[str, Any] = {}
    for journey, keywords in JOURNEY_EVIDENCE_KEYWORDS.items():
        field_hits = sum(1 for keyword in keywords if keyword in field_text)
        pipeline_hits = sum(1 for keyword in keywords if keyword in pipeline_text)
        path_strength = path_strengths[journey]
        material_records = material[journey]
        has_specific_signal = bool(field_hits or pipeline_hits)
        strong_relationship_signal = (
            journey == "expansion_renewal" and prior_won_and_new > 0
        ) or (journey == "inbound_new_business" and mql_progressions > 0)
        if not has_specific_signal and not strong_relationship_signal:
            # Generic chronology, association coverage, missing MQL, and
            # multi-contact accounts do not independently prove a business
            # motion. They become supporting evidence only after a journey-
            # specific field/value/pipeline signal exists.
            path_strength = 0
            material_records = 0
            scored_temporal_pct = 0
            scored_association_pct = 0
        else:
            scored_temporal_pct = temporal_pct
            scored_association_pct = association_pct
        evidence = []
        contradictions = []
        confirmations = []
        if field_hits:
            evidence.append(f"{field_hits} journey keyword signal(s) in active fields/values")
        if pipeline_hits:
            evidence.append(f"{pipeline_hits} journey keyword signal(s) in pipeline/stage labels")
        if path_strength:
            evidence.append(f"object-path strength {path_strength}%")
        if journey == "inbound_new_business" and mql_progressions:
            evidence.append(
                f"{mql_progressions} contact(s) with a timestamped funnel "
                "progression through MQL"
            )
        if not available_coverages:
            contradictions.append("association endpoints unavailable")
        if truncated_objects:
            contradictions.append(
                "snapshot truncated for " + ", ".join(truncated_objects)
            )
        if not field_hits and not pipeline_hits:
            confirmations.append(f"Confirm whether {journey} is represented by an unmapped custom field")
        journey_signals[journey] = {
            "field_keyword_hits": field_hits,
            "pipeline_keyword_hits": pipeline_hits,
            "path_strength_pct": path_strength,
            "material_records": material_records,
            "temporal_coverage_pct": scored_temporal_pct,
            "association_coverage_pct": scored_association_pct,
            "contradiction_count": len(contradictions),
            "supporting_evidence": evidence,
            "contradicting_evidence": contradictions,
            "human_confirmation_needed": confirmations,
        }

    activity = _activity_summary(raw)
    high_intent_by_journey: Dict[str, Any] = {}
    for journey in sorted(set(contact_assignment_counts) | {"unassigned"}):
        rows = [row for row in high_intent_rows if row["assigned_journey"] == journey]
        if not rows:
            continue
        high_intent_by_journey[journey] = {
            "total": len(rows),
            "with_owner": sum(bool(row["has_owner"]) for row in rows),
            "without_owner": sum(not row["has_owner"] for row in rows),
            "with_associated_deal": sum(row["has_associated_deal"] is True for row in rows),
            "without_associated_deal": sum(row["has_associated_deal"] is False for row in rows),
            "deal_association_available": deal_contact is not None,
        }
    high_intent_summary = {
        "definition": "Contacts with a qualified pre-deal lifecycle stage or a positive high-intent HubSpot property signal. This identifies a review population, not guaranteed pipeline.",
        "total": high_intent_count,
        "with_owner": sum(bool(row["has_owner"]) for row in high_intent_rows),
        "without_owner": sum(not row["has_owner"] for row in high_intent_rows),
        "with_associated_deal": sum(row["has_associated_deal"] is True for row in high_intent_rows),
        "without_associated_deal": sum(row["has_associated_deal"] is False for row in high_intent_rows),
        "deal_association_available": deal_contact is not None,
        "by_journey": high_intent_by_journey,
        "currency_amount_available": False,
        "contains_raw_values": False,
    }
    store = {
        "run_id": run_dir.name,
        "date_window_days": manifest.get("days"),
        "full_history": manifest.get("full_history"),
        "object_counts": {obj: len(rows) for obj, rows in records.items()},
        "candidate_fields": fields,
        "pipeline_structure": pipeline_summary,
        "association_summary": association_summary,
        "owner_coverage": owners,
        "activity_summary": activity,
        "intent_signal_summary": intent_summary,
        "intent_signal_coverage": intent_summary.get("coverage", {}),
        "relationship_signals": {
            "contact_before_deal": chronological_before,
            "contact_deal_pairs_with_dates": chronological_total,
            "deals_without_mql_plus_contact": deals_without_mql,
            "companies_with_multiple_contacts": multi_contact_companies,
            "companies_with_prior_won_and_new_deal": prior_won_and_new,
        },
        "stage_transition_summary": stage_transitions,
        "journey_signals": journey_signals,
        "assignment_counts": dict(assignment_counts),
        "assignment_counts_by_object": {
            "deals": dict(assignment_counts),
            "high_intent_contacts": dict(contact_assignment_counts),
        },
        "high_intent_summary": high_intent_summary,
        "ambiguous_areas": [
            message
            for message in (
                "Deal-contact associations unavailable" if deal_contact is None else None,
                "Deal-company associations unavailable" if deal_company is None else None,
                "Activity-level handoff evidence unavailable" if not activity["available"] else None,
                (
                    "Record-linked intent signals unavailable; journey classification uses CRM properties only"
                    if intent_summary.get("coverage", {}).get("status") in {"not_requested", "unavailable"}
                    else None
                ),
                (
                    "Stage-entry timestamps unavailable; journey paths are "
                    "inferred from record creation order only"
                    if not stage_transitions["available"]
                    else None
                ),
                (
                    "Recent-only snapshot may omit earlier records needed to prove "
                    "journey history"
                    if not manifest.get("full_history", manifest.get("days") is None)
                    else None
                ),
                (
                    "Snapshot truncated for " + ", ".join(truncated_objects)
                    if truncated_objects
                    else None
                ),
                *canonical_notes,
                (
                    f"{assignment_counts.get('unassigned', 0)} deals carry no journey signal; "
                    "map their source values in config/journey_mapping.yaml and re-run"
                    if assignment_counts.get("unassigned") and not journey_mapping
                    else None
                ),
            )
            if message
        ],
        "warnings": manifest.get("warnings", []),
        "contains_raw_pii": False,
    }
    registry = build_registry(store)
    write_json(processed / "journey_evidence_store.json", store)
    write_json(processed / "journey_record_assignments.json", assignments)
    write_json(processed / "high_intent_cohort_summary.json", high_intent_summary)
    write_json(processed / "owner_distribution.json", owners)
    write_json(processed / "activity_summary.json", activity)
    write_json(processed / "intent_signal_summary.json", intent_summary)
    write_json(
        processed / "journey_transition_candidates.json",
        store["relationship_signals"],
    )
    write_json(processed / "stage_transition_summary.json", stage_transitions)
    write_json(run_dir / "journey_pattern_registry.json", registry.model_dump())

    crm_context = {
        "audit_focus": "lifecycle_integrity",
        "primary_journey_model": registry.primary_model,
        "mapping_confidence": registry.overall_confidence,
        "canonical_fields": canonical,
        "client_config": {
            "field_overrides": bool(canonical) and any(
                "field_overrides" in str(entry.get("evidence")) for entry in canonical.values()
            ),
            "journey_mapping": bool(journey_mapping),
        },
        "candidate_fields": fields,
        "suspected_legacy_fields": sorted(
            {
                entry["field"]
                for entries in fields.values()
                for entry in entries
                if re.search(r"old|legacy|backup|20\d{2}", entry["field"], re.I)
            }
        ),
        "manual_confirmation_needed": registry.human_confirmation_needed,
    }
    (run_dir / "crm_context.yaml").write_text(
        yaml.safe_dump(crm_context, sort_keys=False), encoding="utf-8"
    )
    report_lines = [
        "# Schema Discovery Report",
        "",
        f"Primary journey model: {registry.primary_model}",
        f"Mapping confidence: {registry.overall_confidence}/100",
        "",
        "## Candidate fields",
    ]
    for intent, entries in fields.items():
        report_lines.append(f"- {intent}: {', '.join(e['field'] for e in entries) or 'none'}")
    report_lines.extend(["", "## Human confirmation needed"])
    report_lines.extend(
        [f"- {item}" for item in registry.human_confirmation_needed]
        or ["- None identified by deterministic discovery."]
    )
    (run_dir / "schema_discovery_report.md").write_text(
        "\n".join(report_lines) + "\n", encoding="utf-8"
    )
    return store
