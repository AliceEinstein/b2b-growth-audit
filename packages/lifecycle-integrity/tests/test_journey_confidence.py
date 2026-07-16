from __future__ import annotations

import pytest

from core.journey_confidence import audit_level, confidence_label, score_components


@pytest.mark.parametrize(
    ("score", "label", "level"),
    [
        (0, "insufficient", "not_detected"),
        (29, "insufficient", "not_detected"),
        (30, "low", "observation_only"),
        (49, "low", "observation_only"),
        (50, "medium", "confidence_capped"),
        (69, "medium", "confidence_capped"),
        (70, "high", "full"),
        (84, "high", "full"),
        (85, "very_high", "full"),
        (100, "very_high", "full"),
    ],
)
def test_confidence_boundaries(score, label, level):
    assert confidence_label(score) == label
    assert audit_level(score) == level


def test_confidence_arithmetic_is_deterministic():
    components = {
        "field_signal": 20,
        "object_path_evidence": 15,
        "volume_materiality": 12,
        "temporal_consistency": 8,
        "pipeline_alignment": 10,
        "association_coherence": 7,
        "reviewer_adjustment": 4,
        "contradiction_penalty": 11,
    }
    assert score_components(components) == 65


def test_confidence_rejects_unknown_or_out_of_range_components():
    with pytest.raises(ValueError, match="unknown confidence"):
        score_components({"invented_signal": 1})
    with pytest.raises(ValueError, match="field_signal"):
        score_components({"field_signal": 21})
