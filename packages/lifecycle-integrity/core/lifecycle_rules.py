"""Pattern-aware deterministic lifecycle integrity measurements."""
from __future__ import annotations

import csv
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from connectors.hubspot.normalize import write_json

from .journey_evidence import build_journey_evidence_store
from .metrics import is_empty, load_association_map, pct, read_json, read_jsonl, stage_flags
from .outliers import write_outlier_registry
from .sanitizer import hash_record_id, load_or_create_salt
from .stage_transitions import analyze_contact_stages
from .validators import validate_snapshot_completed

EVIDENCE_COLUMNS = [
    "finding_id",
    "journey_pattern",
    "object_type",
    "record_id_hash",
    "field_name",
    "issue_type",
    "current_value_redacted",
    "confidence",
    "recommended_review",
    "pipeline_label",
    "deal_stage_label",
    "amount_included_in_aggregate",
    "currency_bucket",
]
CUSTOMER_STATES = {"customer", "evangelist"}


def _props(record: Dict[str, Any]) -> Dict[str, Any]:
    return record.get("properties") or {}


def _out_of_window_note(count: int, object_type: str) -> str:
    if not count:
        return ""
    return (
        f"{count} deal(s) excluded: associated {object_type} were created "
        "before the snapshot window and are not in this snapshot. Re-run "
        "without --days for full coverage."
    )


def _amount(value: Any) -> Optional[Decimal]:
    if is_empty(value):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def measure_lifecycle_integrity(run_dir: Path) -> Dict[str, Any]:
    run_dir = Path(run_dir)
    problems = validate_snapshot_completed(run_dir)
    if problems:
        raise ValueError("cannot measure incomplete snapshot: " + problems[0])
    processed = run_dir / "processed"
    if not (processed / "journey_evidence_store.json").exists():
        build_journey_evidence_store(run_dir)
    raw = run_dir / "raw"
    contacts = read_jsonl(raw / "contacts.jsonl") if (raw / "contacts.jsonl").exists() else []
    companies = read_jsonl(raw / "companies.jsonl") if (raw / "companies.jsonl").exists() else []
    deals = read_jsonl(raw / "deals.jsonl") if (raw / "deals.jsonl").exists() else []
    contact_by_id = {str(row.get("id")): row for row in contacts}
    company_by_id = {str(row.get("id")): row for row in companies}
    deal_by_id = {str(row.get("id")): row for row in deals}
    deal_company = load_association_map(raw, "associations_deal_company.jsonl")
    deal_contact = load_association_map(raw, "associations_deal_contact.jsonl")
    contact_deals = {
        contact_id: [deal_id for deal_id, contacts_for_deal in (deal_contact or {}).items() if contact_id in contacts_for_deal]
        for contact_id in contact_by_id
    }
    pipelines = read_json(raw / "pipelines.json", [])
    flags = stage_flags(pipelines)
    pipeline_summary = read_json(processed / "pipeline_summary.json", {"pipelines": []})
    pipeline_labels = {
        str(pipeline.get("pipeline_id")): str(
            pipeline.get("label") or pipeline.get("pipeline_id") or "Unknown pipeline"
        )
        for pipeline in pipeline_summary.get("pipelines", [])
    }
    stage_labels = {
        (str(pipeline.get("pipeline_id")), str(stage.get("stage_id"))): str(
            stage.get("label") or stage.get("stage_id") or "Unknown stage"
        )
        for pipeline in pipeline_summary.get("pipelines", [])
        for stage in pipeline.get("stages", [])
    }
    manifest = read_json(run_dir / "manifest.json", {})
    # A --days window filters every object by createdate, so an in-window deal
    # can legitimately link to a contact/company created before the window.
    # Such lookups are "outside the snapshot", never "missing data" — counting
    # them as defects would fabricate attribution/state findings.
    windowed = not manifest.get("full_history", False)
    assignments = read_json(processed / "journey_record_assignments.json", [])
    assignment_by_hash = {row["record_id_hash"]: row for row in assignments}
    store = read_json(processed / "journey_evidence_store.json", {})
    salt = load_or_create_salt(run_dir)
    measurements: List[Dict[str, Any]] = []
    leakage_deal_ids: set[str] = set()
    potential_recoverable_contact_ids: set[str] = set()
    evidence_path = run_dir / "evidence.csv"

    with evidence_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=EVIDENCE_COLUMNS)
        writer.writeheader()

        def add(
            measurement_id: str,
            journey: str,
            dimension: str,
            object_type: str,
            denominator: Optional[int],
            affected: Optional[List[Tuple[str, str]]],
            *,
            field_name: Optional[str] = None,
            available: bool = True,
            note: str = "",
            confidence: str = "high",
            leakage_candidate: bool = False,
            leakage_point: str = "",
            recoverability: str = "unknown",
            potential_recoverable_pipeline_population: bool = False,
        ) -> None:
            affected_count = len(affected) if affected is not None else None
            affected_deal_ids = sorted(
                raw_id
                for row_object_type, raw_id in affected or []
                if row_object_type == "deals" and raw_id in deal_by_id
            )
            if leakage_candidate:
                leakage_deal_ids.update(affected_deal_ids)
            if potential_recoverable_pipeline_population:
                potential_recoverable_contact_ids.update(
                    raw_id
                    for row_object_type, raw_id in affected or []
                    if row_object_type == "contacts"
                )
            amount_by_currency: Dict[str, Decimal] = defaultdict(Decimal)
            pipeline_groups: Dict[str, Dict[str, Any]] = {}
            deals_with_amount = 0
            for deal_id in affected_deal_ids:
                props = _props(deal_by_id[deal_id])
                pipeline_id = str(props.get("pipeline") or "unknown")
                currency = str(props.get("hs_currency") or "portal_default")
                parsed_amount = _amount(props.get("amount"))
                group = pipeline_groups.setdefault(
                    pipeline_id,
                    {
                        "pipeline_id": pipeline_id,
                        "pipeline_label": pipeline_labels.get(pipeline_id, pipeline_id),
                        "affected_deals": 0,
                        "amount_by_currency": defaultdict(Decimal),
                    },
                )
                group["affected_deals"] += 1
                if parsed_amount is not None:
                    deals_with_amount += 1
                    amount_by_currency[currency] += parsed_amount
                    group["amount_by_currency"][currency] += parsed_amount
            pipeline_breakdown = []
            for pipeline_id in sorted(pipeline_groups):
                group = pipeline_groups[pipeline_id]
                pipeline_breakdown.append(
                    {
                        "pipeline_id": group["pipeline_id"],
                        "pipeline_label": group["pipeline_label"],
                        "affected_deals": group["affected_deals"],
                        "amount_by_currency": {
                            currency: _decimal_text(amount)
                            for currency, amount in sorted(group["amount_by_currency"].items())
                        },
                    }
                )
            measurements.append(
                {
                    "id": measurement_id,
                    "journey_pattern": journey,
                    "integrity_dimension": dimension,
                    "object_type": object_type,
                    "field_name": field_name,
                    "available": available,
                    "denominator": denominator,
                    "affected_records": affected_count,
                    "affected_percentage": (
                        pct(affected_count, denominator)
                        if affected_count is not None and denominator is not None
                        else None
                    ),
                    "evidence_file": "evidence.csv",
                    "note": note,
                    "leakage_candidate": leakage_candidate,
                    "leakage_point": leakage_point,
                    "recoverability": recoverability,
                    "potential_recoverable_pipeline_population": (
                        affected_count
                        if potential_recoverable_pipeline_population and affected_count is not None
                        else 0
                    ),
                    "affected_deals_with_amount": deals_with_amount,
                    "affected_deals_without_amount": len(affected_deal_ids) - deals_with_amount,
                    "affected_deal_amount_by_currency": {
                        currency: _decimal_text(amount)
                        for currency, amount in sorted(amount_by_currency.items())
                    },
                    "pipeline_breakdown": pipeline_breakdown,
                }
            )
            for row_object_type, raw_id in affected or []:
                row = deal_by_id.get(raw_id) if row_object_type == "deals" else None
                props = _props(row) if row else {}
                pipeline_id = str(props.get("pipeline") or "")
                stage_id = str(props.get("dealstage") or "")
                parsed_amount = _amount(props.get("amount"))
                writer.writerow(
                    {
                        "finding_id": measurement_id,
                        "journey_pattern": journey,
                        "object_type": row_object_type,
                        "record_id_hash": hash_record_id(row_object_type, raw_id, salt),
                        "field_name": field_name or "",
                        "issue_type": measurement_id,
                        "current_value_redacted": "",
                        "confidence": confidence,
                        "recommended_review": "review against journey-specific business rules",
                        "pipeline_label": pipeline_labels.get(pipeline_id, "") if row else "",
                        "deal_stage_label": stage_labels.get((pipeline_id, stage_id), stage_id) if row else "",
                        "amount_included_in_aggregate": "yes" if parsed_amount is not None else "no" if row else "",
                        "currency_bucket": str(props.get("hs_currency") or "portal_default") if row else "",
                    }
                )

        missing_lifecycle = [
            ("contacts", str(row.get("id")))
            for row in contacts
            if is_empty(_props(row).get("lifecyclestage"))
        ]
        add(
            "contacts_missing_lifecycle",
            "all_detected_journeys",
            "lifecycle_integrity",
            "contacts",
            len(contacts),
            missing_lifecycle,
            field_name="lifecyclestage",
        )

        stage_paths = analyze_contact_stages(contacts)
        stage_history_available = stage_paths["with_stage_timestamps"] > 0
        no_history_note = (
            ""
            if stage_history_available
            else "No hs_v2_date_entered_* timestamps in this snapshot; re-run "
            "the acquisition pass with the current connector."
        )
        add(
            "customers_without_stage_history",
            "all_detected_journeys",
            "lifecycle_integrity",
            "contacts",
            stage_paths["customers_total"] if stage_history_available else None,
            (
                [("contacts", rid) for rid in stage_paths["customers_without_timestamped_path_ids"]]
                if stage_history_available
                else None
            ),
            field_name="hs_v2_date_entered_*",
            available=stage_history_available,
            note=no_history_note
            or "Customer contacts with no timestamped pre-customer stage: "
            "possibly imported or set to customer in one step. Confirm the "
            "intended entry rule before judging.",
            confidence="medium",
        )
        add(
            "contacts_stage_regression",
            "all_detected_journeys",
            "state_coherence",
            "contacts",
            stage_paths["ranked_multi_stage_paths"] if stage_history_available else None,
            (
                [("contacts", rid) for rid in stage_paths["stage_regression_ids"]]
                if stage_history_available
                else None
            ),
            field_name="hs_v2_date_entered_*",
            available=stage_history_available,
            note=no_history_note
            or "Contacts whose stage-entry timestamps run backwards through "
            "the funnel: recycling, manual resets, or import artifacts. "
            "Classify per journey rules, not as defects by default.",
            confidence="medium",
            leakage_candidate=True,
            leakage_point="Lifecycle path regression",
            recoverability="requires_business_confirmation",
        )

        add(
            "deals_without_company",
            "all_detected_journeys",
            "association_integrity",
            "deals",
            len(deals) if deal_company is not None else None,
            (
                [("deals", str(row.get("id"))) for row in deals if not deal_company.get(str(row.get("id")))]
                if deal_company is not None
                else None
            ),
            available=deal_company is not None,
            note="deal-company associations unavailable" if deal_company is None else "",
            leakage_candidate=True,
            leakage_point="Deal to company association break",
            recoverability="open_deal_review",
        )
        add(
            "deals_without_contact",
            "all_detected_journeys",
            "association_integrity",
            "deals",
            len(deals) if deal_contact is not None else None,
            (
                [("deals", str(row.get("id"))) for row in deals if not deal_contact.get(str(row.get("id")))]
                if deal_contact is not None
                else None
            ),
            available=deal_contact is not None,
            note="deal-contact associations unavailable" if deal_contact is None else "",
            leakage_candidate=True,
            leakage_point="Deal to buying-contact association break",
            recoverability="open_deal_review",
        )

        won_state_gaps: List[Tuple[str, str]] = []
        won_out_of_window = 0
        if deal_company is not None:
            for deal in deals:
                props = _props(deal)
                is_won = flags.get(
                    (str(props.get("pipeline")), str(props.get("dealstage"))), {}
                ).get("won", False)
                if not is_won:
                    continue
                associated = deal_company.get(str(deal.get("id")), [])
                linked = [company_by_id[i] for i in associated if i in company_by_id]
                if windowed and associated and not linked:
                    won_out_of_window += 1
                    continue
                if linked and not any(
                    str(_props(company).get("lifecyclestage") or "").lower() in CUSTOMER_STATES
                    for company in linked
                ):
                    won_state_gaps.append(("deals", str(deal.get("id"))))
        won_total = sum(
            1
            for deal in deals
            if flags.get(
                (str(_props(deal).get("pipeline")), str(_props(deal).get("dealstage"))), {}
            ).get("won", False)
        )
        add(
            "closed_won_company_not_customer",
            "all_detected_journeys",
            "state_coherence",
            "deals",
            won_total if deal_company is not None else None,
            won_state_gaps if deal_company is not None else None,
            field_name="lifecyclestage",
            available=deal_company is not None,
            note=_out_of_window_note(won_out_of_window, "companies"),
        )

        deals_by_journey: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for deal in deals:
            deal_hash = hash_record_id("deals", str(deal.get("id")), salt)
            journey = assignment_by_hash.get(deal_hash, {}).get("assigned_journey", "unassigned")
            deals_by_journey[str(journey)].append(deal)
        for journey, journey_deals in sorted(deals_by_journey.items()):
            if journey == "unassigned":
                continue
            missing_owner = [
                ("deals", str(deal.get("id")))
                for deal in journey_deals
                if is_empty(_props(deal).get("hubspot_owner_id"))
            ]
            add(
                f"{journey}_deals_without_owner",
                journey,
                "handoff_integrity",
                "deals",
                len(journey_deals),
                missing_owner,
                field_name="hubspot_owner_id",
                leakage_candidate=True,
                leakage_point="Journey deal without accountable owner",
                recoverability="open_deal_review",
            )
            if deal_company is not None:
                missing_company = [
                    ("deals", str(deal.get("id")))
                    for deal in journey_deals
                    if not deal_company.get(str(deal.get("id")))
                ]
                add(
                    f"{journey}_deals_without_company",
                    journey,
                    "association_integrity",
                    "deals",
                    len(journey_deals),
                    missing_company,
                    leakage_candidate=True,
                    leakage_point="Journey deal without account association",
                    recoverability="open_deal_review",
                )

        inbound_deals = deals_by_journey.get("inbound_new_business", [])
        if deal_contact is not None:
            no_source_trace = []
            inbound_out_of_window = 0
            for deal in inbound_deals:
                associated = deal_contact.get(str(deal.get("id")), [])
                linked = [contact_by_id[i] for i in associated if i in contact_by_id]
                if windowed and associated and not linked:
                    inbound_out_of_window += 1
                    continue
                if not linked or not any(
                    not is_empty(_props(contact).get("hs_analytics_source"))
                    for contact in linked
                ):
                    no_source_trace.append(("deals", str(deal.get("id"))))
            add(
                "inbound_deals_without_source_trace",
                "inbound_new_business",
                "attribution_continuity",
                "deals",
                len(inbound_deals),
                no_source_trace,
                field_name="hs_analytics_source",
                note=_out_of_window_note(inbound_out_of_window, "contacts"),
                leakage_candidate=True,
                leakage_point="Inbound deal without source continuity",
                recoverability="system_repair",
            )
        else:
            add(
                "inbound_deals_without_source_trace",
                "inbound_new_business",
                "attribution_continuity",
                "deals",
                None,
                None,
                field_name="hs_analytics_source",
                available=False,
                note="deal-contact associations unavailable",
            )

        expansion_deals = deals_by_journey.get("expansion_renewal", [])
        if deal_company is not None:
            invalid_expansion = []
            expansion_out_of_window = 0
            for deal in expansion_deals:
                associated = deal_company.get(str(deal.get("id")), [])
                linked = [company_by_id[i] for i in associated if i in company_by_id]
                if windowed and associated and not linked:
                    # Renewal customers are almost always older than any
                    # creation window; treating them as state gaps would make
                    # this check meaningless on windowed runs.
                    expansion_out_of_window += 1
                    continue
                if not linked or not any(
                    str(_props(company).get("lifecyclestage") or "").lower() in CUSTOMER_STATES
                    for company in linked
                ):
                    invalid_expansion.append(("deals", str(deal.get("id"))))
            add(
                "expansion_deals_without_customer_company",
                "expansion_renewal",
                "state_coherence",
                "deals",
                len(expansion_deals),
                invalid_expansion,
                field_name="lifecyclestage",
                note=_out_of_window_note(expansion_out_of_window, "companies"),
                leakage_candidate=True,
                leakage_point="Expansion deal disconnected from customer state",
                recoverability="requires_business_confirmation",
            )

        high_intent_by_journey: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for contact in contacts:
            contact_id = str(contact.get("id"))
            contact_hash = hash_record_id("contacts", contact_id, salt)
            assignment = assignment_by_hash.get(contact_hash, {})
            if not assignment.get("high_intent"):
                continue
            high_intent_by_journey[
                str(assignment.get("assigned_journey") or "unassigned")
            ].append(contact)
        for journey, journey_contacts in sorted(high_intent_by_journey.items()):
            missing_owner = [
                ("contacts", str(contact.get("id")))
                for contact in journey_contacts
                if is_empty(_props(contact).get("hubspot_owner_id"))
            ]
            add(
                f"{journey}_high_intent_contacts_without_owner",
                journey,
                "handoff_integrity",
                "contacts",
                len(journey_contacts),
                missing_owner,
                field_name="hubspot_owner_id",
                note=(
                    "Potential recoverable pipeline population. No monetary "
                    "value is shown because these contacts do not necessarily "
                    "have deals."
                ),
                confidence="medium",
                leakage_candidate=True,
                leakage_point="High-intent contact without accountable owner",
                recoverability="potential_recoverable_population",
                potential_recoverable_pipeline_population=True,
            )
            no_deal = (
                [
                    ("contacts", str(contact.get("id")))
                    for contact in journey_contacts
                    if not contact_deals.get(str(contact.get("id")))
                ]
                if deal_contact is not None
                else None
            )
            add(
                f"{journey}_high_intent_contacts_without_deal",
                journey,
                "handoff_integrity",
                "contacts",
                len(journey_contacts) if deal_contact is not None else None,
                no_deal,
                available=deal_contact is not None,
                note=(
                    "Potential recoverable pipeline population, not proven "
                    "lost pipeline. Confirm when this journey is expected to "
                    "create a deal. No monetary value is shown without a deal."
                    if deal_contact is not None
                    else "Deal-contact associations unavailable."
                ),
                confidence="medium",
                leakage_candidate=True,
                leakage_point="High-intent contact without deal progression",
                recoverability="potential_recoverable_population",
                potential_recoverable_pipeline_population=True,
            )

        lifecycle_fields = store.get("candidate_fields", {}).get("lifecycle", [])
        extra_fields = [entry for entry in lifecycle_fields if entry.get("field") != "lifecyclestage"]
        add(
            "lifecycle_field_fragmentation",
            "all_detected_journeys",
            "property_governance",
            "properties",
            len(lifecycle_fields),
            [("properties", str(entry.get("field"))) for entry in extra_fields],
            field_name="lifecycle_candidates",
            note="Multiple lifecycle-like fields require canonical-field confirmation.",
            confidence="medium",
        )

        activity = store.get("activity_summary", {})
        add(
            "activity_handoff_evidence_available",
            "all_detected_journeys",
            "handoff_integrity",
            "activities",
            None,
            [] if activity.get("available") else None,
            available=bool(activity.get("available")),
            note=activity.get("limitation", "Activity metadata available at portal level."),
            confidence="medium",
        )

    open_leakage_ids = []
    open_amounts: Dict[str, Decimal] = defaultdict(Decimal)
    open_by_pipeline: Dict[str, Dict[str, Any]] = {}
    open_with_amount = 0
    for deal_id in sorted(leakage_deal_ids):
        deal = deal_by_id[deal_id]
        props = _props(deal)
        key = (str(props.get("pipeline")), str(props.get("dealstage")))
        if flags.get(key, {}).get("closed", False):
            continue
        open_leakage_ids.append(deal_id)
        pipeline_id = key[0]
        currency = str(props.get("hs_currency") or "portal_default")
        parsed_amount = _amount(props.get("amount"))
        group = open_by_pipeline.setdefault(
            pipeline_id,
            {
                "pipeline_id": pipeline_id,
                "pipeline_label": pipeline_labels.get(pipeline_id, pipeline_id),
                "open_deals_with_leakage_signals": 0,
                "amount_by_currency": defaultdict(Decimal),
            },
        )
        group["open_deals_with_leakage_signals"] += 1
        if parsed_amount is not None:
            open_with_amount += 1
            open_amounts[currency] += parsed_amount
            group["amount_by_currency"][currency] += parsed_amount
    pipeline_exposure = {
        "definition": "Actual amount on unique existing open deals with one or more deterministic leakage-candidate signals. This is exposed pipeline for review, not a forecast of loss and not proof that every signal survives reviewer adjudication.",
        "unique_open_deals_with_leakage_signals": len(open_leakage_ids),
        "open_deals_with_amount": open_with_amount,
        "open_deals_without_amount": len(open_leakage_ids) - open_with_amount,
        "actual_open_deal_amount_by_currency": {
            currency: _decimal_text(amount)
            for currency, amount in sorted(open_amounts.items())
        },
        "by_pipeline": [
            {
                "pipeline_id": group["pipeline_id"],
                "pipeline_label": group["pipeline_label"],
                "open_deals_with_leakage_signals": group[
                    "open_deals_with_leakage_signals"
                ],
                "amount_by_currency": {
                    currency: _decimal_text(amount)
                    for currency, amount in sorted(group["amount_by_currency"].items())
                },
            }
            for _, group in sorted(open_by_pipeline.items())
        ],
        "potential_recoverable_pipeline_population": len(
            potential_recoverable_contact_ids
        ),
        "potential_population_amount": None,
        "potential_population_amount_rule": "Never assign monetary value when no deal exists.",
        "deal_trace_file": "evidence.csv",
    }
    doc = {
        "run_id": run_dir.name,
        "measurements": measurements,
        "pipeline_exposure": pipeline_exposure,
        "evidence_file": "evidence.csv",
        "evidence_columns": EVIDENCE_COLUMNS,
    }
    write_json(processed / "lifecycle_integrity_measurements.json", doc)
    write_outlier_registry(run_dir)
    return doc
