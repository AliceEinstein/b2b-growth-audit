"""Deterministic journey-confidence arithmetic."""
from __future__ import annotations

from typing import Any, Dict

from .lifecycle_schemas import JourneyPattern, JourneyPatternRegistry

COMPONENT_MAX = {
    "field_signal": 20,
    "object_path_evidence": 20,
    "volume_materiality": 15,
    "temporal_consistency": 10,
    "pipeline_alignment": 15,
    "association_coherence": 10,
    "reviewer_adjustment": 10,
    "contradiction_penalty": 30,
}

JOURNEYS = [
    "inbound_new_business",
    "outbound_sales_led",
    "abm_account_based",
    "partner_led",
    "expansion_renewal",
]


def confidence_label(score: int) -> str:
    if score >= 85:
        return "very_high"
    if score >= 70:
        return "high"
    if score >= 50:
        return "medium"
    if score >= 30:
        return "low"
    return "insufficient"


def audit_level(score: int) -> str:
    if score >= 70:
        return "full"
    if score >= 50:
        return "confidence_capped"
    if score >= 30:
        return "observation_only"
    return "not_detected"


def score_components(components: Dict[str, int]) -> int:
    unknown = set(components) - set(COMPONENT_MAX)
    if unknown:
        raise ValueError(f"unknown confidence components: {sorted(unknown)}")
    normalized: Dict[str, int] = {}
    for name, maximum in COMPONENT_MAX.items():
        value = int(components.get(name, 0))
        if not 0 <= value <= maximum:
            raise ValueError(f"{name} must be between 0 and {maximum}")
        normalized[name] = value
    positive = sum(v for k, v in normalized.items() if k != "contradiction_penalty")
    return max(0, min(100, positive - normalized["contradiction_penalty"]))


def _volume_points(material_records: int) -> int:
    if material_records >= 50:
        return 15
    if material_records >= 20:
        return 12
    if material_records >= 5:
        return 9
    if material_records >= 3:
        return 7
    if material_records >= 1:
        return 4
    return 0


def derive_components(signal: Dict[str, Any]) -> Dict[str, int]:
    path_strength = float(signal.get("path_strength_pct") or 0)
    temporal = float(signal.get("temporal_coverage_pct") or 0)
    associations = float(signal.get("association_coverage_pct") or 0)
    components = {
        "field_signal": min(20, int(signal.get("field_keyword_hits", 0)) * 5),
        "object_path_evidence": min(20, round(path_strength / 5)),
        "volume_materiality": _volume_points(int(signal.get("material_records", 0))),
        "temporal_consistency": min(10, round(temporal / 10)),
        "pipeline_alignment": min(15, int(signal.get("pipeline_keyword_hits", 0)) * 8),
        "association_coherence": min(10, round(associations / 10)),
        "reviewer_adjustment": int(signal.get("reviewer_adjustment", 0)),
        "contradiction_penalty": min(
            30, int(signal.get("contradiction_count", 0)) * 5
        ),
    }
    return components


def build_registry(evidence_store: Dict[str, Any]) -> JourneyPatternRegistry:
    patterns = []
    all_confirmations = []
    all_ambiguities = list(evidence_store.get("ambiguous_areas", []))
    for journey in JOURNEYS:
        signal = evidence_store.get("journey_signals", {}).get(journey, {})
        components = derive_components(signal)
        score = score_components(components)
        confirmations = list(signal.get("human_confirmation_needed", []))
        all_confirmations.extend(confirmations)
        patterns.append(
            JourneyPattern(
                journey_type=journey,
                exists=score >= 30,
                confidence_score=score,
                confidence_label=confidence_label(score),
                evidence_components=components,
                supporting_evidence=list(signal.get("supporting_evidence", [])),
                contradicting_evidence=list(signal.get("contradicting_evidence", [])),
                human_confirmation_needed=confirmations,
                audit_level=audit_level(score),
            )
        )
    auditable = [p for p in patterns if p.confidence_score >= 50]
    detected = [p for p in patterns if p.exists]
    if len(auditable) >= 2:
        model = "multi_motion"
    elif detected:
        model = "single_motion"
    else:
        model = "insufficient_evidence"
    overall = round(sum(p.confidence_score for p in detected) / len(detected)) if detected else 0
    return JourneyPatternRegistry(
        primary_model=model,
        overall_confidence=overall,
        patterns=patterns,
        ambiguous_areas=list(dict.fromkeys(all_ambiguities)),
        human_confirmation_needed=list(dict.fromkeys(all_confirmations)),
    )
