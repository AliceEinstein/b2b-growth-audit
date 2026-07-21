from connectors.hubspot.fetch_properties import select_source_candidates


def test_source_candidates_exclude_sensitive_property_values() -> None:
    definitions = [
        {
            "name": "campaign_source_detail",
            "label": "Campaign source detail",
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

    assert select_source_candidates(definitions) == ["campaign_source_detail"]
