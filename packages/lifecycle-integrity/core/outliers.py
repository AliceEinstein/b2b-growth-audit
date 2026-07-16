"""Deterministic outlier classification with hashed identifiers only."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List

from .lifecycle_schemas import OutlierRecord
from .metrics import load_association_map, read_json, read_jsonl
from .sanitizer import hash_record_id, load_or_create_salt

OUTLIER_COLUMNS = [
    "outlier_id",
    "journey_pattern",
    "object_type",
    "record_id_hash",
    "outlier_type",
    "classification",
    "confidence",
    "reason",
    "recommended_review",
]
MQL_PLUS = {"marketingqualifiedlead", "salesqualifiedlead", "opportunity", "customer", "evangelist"}


def classify_outliers(run_dir: Path) -> List[OutlierRecord]:
    run_dir = Path(run_dir)
    raw = run_dir / "raw"
    assignments = read_json(run_dir / "processed" / "journey_record_assignments.json", [])
    by_hash = {row["record_id_hash"]: row for row in assignments}
    deals = read_jsonl(raw / "deals.jsonl") if (raw / "deals.jsonl").exists() else []
    contacts = {
        str(row.get("id")): row
        for row in (read_jsonl(raw / "contacts.jsonl") if (raw / "contacts.jsonl").exists() else [])
    }
    deal_company = load_association_map(raw, "associations_deal_company.jsonl")
    deal_contact = load_association_map(raw, "associations_deal_contact.jsonl")
    salt = load_or_create_salt(run_dir)
    result: List[OutlierRecord] = []

    def add(
        deal_hash: str,
        journey: str,
        suffix: str,
        classification: str,
        confidence: int,
        reason: str,
        review: str,
    ) -> None:
        result.append(
            OutlierRecord(
                outlier_id=f"{deal_hash}-{suffix}",
                journey_pattern=journey,
                object_type="deals",
                record_id_hash=deal_hash,
                outlier_type=suffix,
                classification=classification,
                confidence=confidence,
                reason=reason,
                recommended_review=review,
            )
        )

    for deal in deals:
        deal_id = str(deal.get("id"))
        deal_hash = hash_record_id("deals", deal_id, salt)
        assignment = by_hash.get(
            deal_hash,
            {"assigned_journey": "unassigned", "assignment_confidence": 0},
        )
        journey = str(assignment.get("assigned_journey") or "unassigned")
        confidence = int(assignment.get("assignment_confidence") or 0)
        if journey == "unassigned":
            add(
                deal_hash,
                journey,
                "unassigned_journey",
                "needs_human_review",
                max(confidence, 20),
                "No journey-specific source, pipeline, or custom-field signal.",
                "Confirm the canonical deal motion or deal-type field.",
            )
        elif confidence < 50:
            add(
                deal_hash,
                journey,
                "low_confidence_assignment",
                "journey_misclassification",
                confidence,
                "Journey assignment is below the formal audit threshold.",
                "Review the deal against the Journey Pattern Registry.",
            )
        if deal_company is not None and not deal_company.get(deal_id):
            add(
                deal_hash,
                journey,
                "missing_company_association",
                "missing_data",
                90,
                "Deal has no company association in the completed snapshot.",
                "Review the deal-company association requirement for this journey.",
            )
        if deal_contact is not None and not deal_contact.get(deal_id):
            add(
                deal_hash,
                journey,
                "missing_contact_association",
                "missing_data",
                90,
                "Deal has no contact association in the completed snapshot.",
                "Review whether this journey requires a buying-contact association.",
            )
        if journey == "outbound_sales_led" and deal_contact is not None:
            linked = [contacts[i] for i in deal_contact.get(deal_id, []) if i in contacts]
            has_mql = any(
                str((row.get("properties") or {}).get("lifecyclestage") or "").lower()
                in MQL_PLUS
                for row in linked
            )
            if linked and not has_mql:
                add(
                    deal_hash,
                    journey,
                    "no_prior_mql",
                    "valid_exception",
                    90,
                    "Outbound deal has linked contacts but no MQL-or-later contact state.",
                    "Do not treat this as a defect unless the business requires MQL for outbound.",
                )
    return result


def write_outlier_registry(run_dir: Path) -> List[OutlierRecord]:
    rows = classify_outliers(run_dir)
    path = Path(run_dir) / "outlier_registry.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTLIER_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.model_dump())
    return rows
