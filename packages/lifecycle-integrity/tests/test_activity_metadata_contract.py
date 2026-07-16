from __future__ import annotations

from connectors.hubspot.fetch_activities import ACTIVITY_PROPERTIES


def test_note_snapshot_excludes_body_and_free_text():
    assert ACTIVITY_PROPERTIES["notes"] == [
        "createdate",
        "hs_timestamp",
        "hubspot_owner_id",
    ]
    blocked = {"hs_note_body", "hs_task_body", "hs_meeting_body", "body", "description"}
    assert all(
        blocked.isdisjoint(properties)
        for properties in ACTIVITY_PROPERTIES.values()
    )
