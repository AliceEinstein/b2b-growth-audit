from connectors.hubspot.fetch_properties import (
    select_journey_candidates,
    select_source_candidates,
    select_stage_timestamp_candidates,
)


def test_source_and_journey_candidates_exclude_sensitive_property_values() -> None:
    definitions = [
        {
            "name": "target_account_tier",
            "label": "Target account tier",
            "hubspotDefined": False,
            "dataSensitivity": "non_sensitive",
        },
        {
            "name": "lead_financial_profile",
            "label": "Lead financial profile",
            "hubspotDefined": False,
            "dataSensitivity": "sensitive",
        },
        {
            "name": "government_id_source",
            "label": "Government ID source",
            "hubspotDefined": False,
            "dataSensitivity": "highly_sensitive",
        },
    ]

    assert select_source_candidates(definitions) == []
    assert select_journey_candidates(definitions) == ["target_account_tier"]


def test_stage_timestamp_candidates_exclude_protected_values_defensively() -> None:
    definitions = [
        {
            "name": "hs_v2_date_entered_customer",
            "dataSensitivity": "non_sensitive",
        },
        {
            "name": "hs_v2_date_entered_protected_stage",
            "dataSensitivity": "sensitive",
        },
    ]

    assert select_stage_timestamp_candidates(definitions) == [
        "hs_v2_date_entered_customer"
    ]
