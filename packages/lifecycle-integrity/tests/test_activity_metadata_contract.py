from __future__ import annotations

import httpx

from connectors.hubspot.client import HubSpotClient
from connectors.hubspot.fetch_activities import ACTIVITY_PROPERTIES
from connectors.hubspot.fetch_activities import fetch_all
from connectors.hubspot.rate_limit import RateLimitPolicy


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


def test_one_unavailable_activity_does_not_hide_other_activity_sources(tmp_path):
    def handler(request):
        if request.url.path == "/crm/v3/objects/calls":
            return httpx.Response(200, json={"results": [{"id": "call-1", "properties": {}}]})
        return httpx.Response(403)

    client = HubSpotClient(
        "pat-na1-test",
        transport=httpx.MockTransport(handler),
        policy=RateLimitPolicy(max_retries=0, base_delay=0),
        sleep=lambda _seconds: None,
    )
    with client:
        summaries = fetch_all(client, tmp_path)
    assert summaries["calls"]["available"] is True
    assert summaries["calls"]["count"] == 1
    assert summaries["emails"]["available"] is False
    assert summaries["emails"]["status"] == "permission_or_api_unavailable"


def test_failed_activity_source_does_not_leave_partial_jsonl(tmp_path):
    def handler(request):
        if request.url.path == "/crm/v3/objects/calls":
            if request.url.params.get("after") is None:
                return httpx.Response(
                    200,
                    json={
                        "results": [{"id": "call-1", "properties": {}}],
                        "paging": {"next": {"after": "1"}},
                    },
                )
            return httpx.Response(403)
        return httpx.Response(403)

    client = HubSpotClient(
        "pat-na1-test",
        transport=httpx.MockTransport(handler),
        policy=RateLimitPolicy(max_retries=0, base_delay=0),
        sleep=lambda _seconds: None,
    )
    with client:
        summaries = fetch_all(client, tmp_path)

    assert summaries["calls"]["available"] is False
    assert not (tmp_path / "calls.jsonl").exists()
