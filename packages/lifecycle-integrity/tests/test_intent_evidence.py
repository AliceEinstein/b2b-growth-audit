from __future__ import annotations

import json

import httpx

from connectors.hubspot.client import HubSpotClient, ReadOnlyViolation
from connectors.hubspot.fetch_intent_sources import (
    fetch_event_occurrences,
    fetch_event_types,
    fetch_forms_and_submissions,
    select_event_types,
)
from connectors.hubspot.rate_limit import RateLimitPolicy
from core.intent_evidence import build_intent_evidence
from core.journey_evidence import build_journey_evidence_store
from core.lifecycle_rules import measure_lifecycle_integrity
from core.profiler import profile_run
from core.synthetic_datasets import _company, _contact, _deal, make_run


TOKEN = "pat-na1-00000000-0000-0000-000000000000"


def make_client(handler):
    return HubSpotClient(
        TOKEN,
        transport=httpx.MockTransport(handler),
        policy=RateLimitPolicy(max_retries=0, base_delay=0),
        sleep=lambda _seconds: None,
    )


def test_event_selection_prefers_relevant_catalog_and_has_page_fallback():
    selected = select_event_types(
        [
            {"name": "custom_internal_debug"},
            {"fullyQualifiedName": "pricing_page_view"},
            {"name": "form_demo_request"},
        ],
        cap=3,
    )
    assert selected[0] == "e_visited_page"
    assert "pricing_page_view" in selected
    assert "form_demo_request" in selected


def test_event_type_catalog_normalizes_current_event_types_shape(tmp_path):
    def handler(request):
        assert request.url.path == "/events/event-occurrences/2026-03/event-types"
        return httpx.Response(
            200,
            json={"eventTypes": ["e_visited_page", "demo_request_submitted"]},
        )

    out = tmp_path / "event_types.json"
    with make_client(handler) as client:
        rows = fetch_event_types(client, out)

    assert rows == [
        {"fullyQualifiedName": "e_visited_page", "name": "e_visited_page"},
        {"fullyQualifiedName": "demo_request_submitted", "name": "demo_request_submitted"},
    ]
    assert select_event_types(rows) == ["e_visited_page", "demo_request_submitted"]


def test_event_occurrence_fetch_is_paginated_and_metadata_bounded(tmp_path):
    calls = []

    def handler(request):
        calls.append(dict(request.url.params))
        if "after" not in request.url.params:
            return httpx.Response(
                200,
                json={
                    "results": [{"objectId": "c1", "eventType": "pricing_page_view"}],
                    "paging": {"next": {"after": "1"}},
                },
            )
        return httpx.Response(
            200,
            json={"results": [{"objectId": "c2", "eventType": "form_demo_request"}]},
        )

    out = tmp_path / "events.jsonl"
    with make_client(handler) as client:
        summary = fetch_event_occurrences(client, out, ["pricing_page_view"])
    assert summary["count"] == 2
    assert calls[1]["after"] == "1"
    assert all(call["objectType"] == "contact" for call in calls)
    assert "email" not in out.read_text(encoding="utf-8").lower()


def test_forms_fetch_uses_official_submission_limit_and_keeps_local_link_hint(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path == "/forms/v2/forms":
            return httpx.Response(200, json=[{"guid": "form-1", "name": "Demo request"}])
        assert request.url.path == "/form-integrations/v1/submissions/forms/form-1"
        assert request.url.params["limit"] == "50"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "submittedAt": "2026-07-03T10:00:00Z",
                        "conversionId": "conversion-1",
                        "pageUrl": "https://example.test/demo?email=buyer@example.test",
                        "values": [{"name": "email", "value": "buyer@example.test"}],
                    }
                ]
            },
        )

    with make_client(handler) as client:
        summary = fetch_forms_and_submissions(client, tmp_path)

    assert summary == {"form_count": 1, "submission_count": 1, "truncated": False}
    raw = json.loads((tmp_path / "form_submissions.jsonl").read_text().splitlines()[0])
    assert raw["contact_email"] == "buyer@example.test"
    assert len(calls) == 2


def test_unsupported_event_type_does_not_erase_other_event_types(tmp_path):
    def handler(request):
        event_type = request.url.params.get("eventType")
        if event_type == "unsupported_portal_event":
            return httpx.Response(403)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "objectId": "c1",
                        "eventType": event_type,
                    }
                ]
            },
        )

    out = tmp_path / "events.jsonl"
    with make_client(handler) as client:
        summary = fetch_event_occurrences(
            client,
            out,
            ["unsupported_portal_event", "e_visited_page"],
        )

    assert summary["count"] == 1
    assert summary["failed_event_type_count"] == 1


def test_new_marketing_endpoints_remain_read_only():
    with make_client(lambda _request: (_ for _ in ()).throw(AssertionError("network"))) as client:
        for method, path in (
            ("POST", "/forms/v2/forms"),
            ("PATCH", "/marketing/campaigns/2026-03/1"),
            ("POST", "/form-integrations/v1/submissions/forms/a"),
        ):
            try:
                client.request(method, path)
            except ReadOnlyViolation:
                pass
            else:  # pragma: no cover - defensive assertion
                raise AssertionError(f"write escaped allowlist: {method} {path}")


def test_intent_evidence_links_activity_events_and_forms_without_raw_identity(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "calls.jsonl").write_text(
        json.dumps(
            {
                "id": "call-1",
                "properties": {
                    "hs_timestamp": "2026-07-01T10:00:00Z",
                    "hs_call_status": "COMPLETED",
                    "hs_call_direction": "INBOUND",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (raw / "associations_calls_contacts.jsonl").write_text(
        '{"from_id":"call-1","to_ids":["c1"]}\n', encoding="utf-8"
    )
    (raw / "associations_deal_contact.jsonl").write_text(
        '{"from_id":"d1","to_ids":["c1"]}\n', encoding="utf-8"
    )
    (raw / "contacts.jsonl").write_text(
        json.dumps({"id": "c1", "properties": {"email": "buyer@example.test"}})
        + "\n",
        encoding="utf-8",
    )
    (raw / "event_occurrences.jsonl").write_text(
        json.dumps(
            {
                "objectId": "c1",
                "objectType": "contact",
                "eventType": "pricing_page_view",
                "occurredAt": "2026-07-02T10:00:00Z",
                "pageUrl": "https://example.test/pricing?email=alice@example.test",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (raw / "forms.json").write_text(
        json.dumps([{"guid": "form-1", "name": "Demo request"}]), encoding="utf-8"
    )
    (raw / "form_submissions.jsonl").write_text(
        json.dumps(
            {
                "form_guid": "form-1",
                "submittedAt": "2026-07-03T10:00:00Z",
                "contact_email": "buyer@example.test",
                "pageUrl": "https://example.test/demo",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    summary = build_intent_evidence(tmp_path)
    assert summary["event_count"] == 3
    assert summary["counts_by_strength"]["high"] >= 2
    assert summary["contains_raw_values"] is False
    store_text = (tmp_path / "processed/intent_signal_store.jsonl").read_text(encoding="utf-8")
    assert "alice@example.test" not in store_text
    assert "example.test/pricing" not in store_text
    index = json.loads((tmp_path / "processed/intent_record_index.json").read_text(encoding="utf-8"))
    assert index["contacts"]
    assert '"c1"' not in json.dumps(index)


def test_standard_event_page_url_is_read_from_nested_properties(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "event_occurrences.jsonl").write_text(
        json.dumps(
            {
                "objectId": "c1",
                "objectType": "contact",
                "eventType": "e_visited_page",
                "occurredAt": "2026-07-03T10:00:00Z",
                "properties": {
                    "hs_url": "https://example.test/pricing?email=buyer@example.test"
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    summary = build_intent_evidence(tmp_path)
    store = (tmp_path / "processed/intent_signal_store.jsonl").read_text(encoding="utf-8")
    assert summary["event_count"] == 1
    assert '"signal_strength": "medium"' in store
    assert "example.test/pricing" not in store


def test_successful_empty_source_is_marked_observed_no_events_in_manifest(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    for name, value in (
        ("event_occurrences.jsonl", ""),
        ("form_submissions.jsonl", ""),
        ("forms.json", "[]"),
        ("campaigns.json", "[]"),
        ("campaign_assets.json", "[]"),
        ("campaign_metrics.json", "[]"),
    ):
        (raw / name).write_text(value, encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "intent": {
                    "sources": {
                        "events": {"status": "available"},
                        "forms": {"status": "available"},
                        "campaigns": {"status": "available"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    summary = build_intent_evidence(tmp_path)

    assert summary["coverage"]["sources"]["events"]["status"] == "observed_no_events"
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["intent"]["sources"]["events"]["status"] == "observed_no_events"


def test_unavailable_intent_sources_make_overall_coverage_partial(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "event_occurrences.jsonl").write_text(
        json.dumps(
            {
                "objectId": "c1",
                "objectType": "contact",
                "eventType": "form_demo_request",
                "occurredAt": "2026-07-03T10:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "intent": {
                    "sources": {
                        "events": {"status": "available"},
                        "forms": {"status": "permission_or_api_unavailable"},
                        "campaigns": {"status": "permission_or_api_unavailable"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    summary = build_intent_evidence(tmp_path)
    assert summary["coverage"]["status"] == "partial"


def test_campaign_context_exposes_channel_breakdown_without_person_level_claims(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    for name, value in (
        ("campaigns.json", [{"id": "cmp-1"}]),
        (
            "campaign_assets.json",
            [
                {"campaign_id": "cmp-1", "asset_type": "AD_CAMPAIGN"},
                {"campaign_id": "cmp-1", "asset_type": "SOCIAL_BROADCAST"},
            ],
        ),
        ("campaign_metrics.json", [{"campaign_id": "cmp-1", "metrics": {"clicks": 4}}]),
    ):
        (raw / name).write_text(json.dumps(value), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"intent": {"sources": {"campaigns": {"status": "available"}}}}),
        encoding="utf-8",
    )
    summary = build_intent_evidence(tmp_path)
    context = summary["campaign_context"]
    assert context["channel_counts"] == {"paid_ad": 1, "social": 1}
    assert context["evidence_scope"].startswith("aggregate_channel_context_only")


def test_manifest_unavailable_source_overrides_partial_raw_prefix(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "event_occurrences.jsonl").write_text(
        json.dumps(
            {
                "objectId": "c1",
                "objectType": "contact",
                "eventType": "form_demo_request",
                "occurredAt": "2026-07-03T10:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "intent": {
                    "status": "permission_denied",
                    "sources": {
                        "events": {
                            "status": "permission_or_api_unavailable"
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    summary = build_intent_evidence(tmp_path)

    assert summary["event_count"] == 0
    assert (
        summary["coverage"]["sources"]["events"]["status"]
        == "permission_or_api_unavailable"
    )


def test_closed_lost_recovery_is_separate_from_open_pipeline_and_score(tmp_path):
    run_dir = make_run(
        tmp_path,
        "closed_lost_intent_sample",
        contacts=[_contact(1, 1, source="ORGANIC_SEARCH")],
        companies=[_company(1, "recovery.test", "Recovery")],
        deals=[
            _deal(
                1,
                3,
                pipeline="sales",
                stage="lost",
                amount="12000",
                closedate="2026-07-01T00:00:00Z",
            )
        ],
        pipelines=[
            {
                "id": "sales",
                "label": "Sales",
                "stages": [
                    {
                        "id": "lost",
                        "label": "Closed Lost",
                        "metadata": {"isClosed": "true", "probability": "0"},
                    }
                ],
            }
        ],
        assoc_contact_company=[{"from_id": "c1", "to_ids": ["co1"]}],
        assoc_deal_company=[{"from_id": "d1", "to_ids": ["co1"]}],
        assoc_deal_contact=[{"from_id": "d1", "to_ids": ["c1"]}],
    )
    raw = run_dir / "raw"
    (raw / "forms.json").write_text(json.dumps([{"guid": "demo", "name": "Demo request"}]), encoding="utf-8")
    (raw / "form_submissions.jsonl").write_text(
        json.dumps(
            {
                "form_guid": "demo",
                "submittedAt": "2026-07-05T00:00:00Z",
                "contact": {"vid": "c1"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    profile_run(run_dir)
    build_intent_evidence(run_dir)
    build_journey_evidence_store(run_dir)
    doc = measure_lifecycle_integrity(run_dir)

    recovery = next(
        row for row in doc["measurements"] if row["id"] == "closed_lost_recovery_opportunity"
    )
    assert recovery["affected_records"] == 1
    assert recovery["leakage_candidate"] is False
    assert recovery["affected_deal_amount_by_currency"] == {}
    assert doc["pipeline_exposure"]["unique_open_deals_with_leakage_signals"] == 0
    lane = doc["recovery_routing"]["lanes"]["closed_lost_recovery"]
    assert lane["count"] == 1
    assert lane["historical_closed_lost_amount_by_currency"] == {"USD": "12000.00"}


def test_closed_lost_recovery_requires_successor_association_coverage(tmp_path):
    run_dir = make_run(
        tmp_path,
        "closed_lost_without_associations",
        contacts=[_contact(1, 1, source="ORGANIC_SEARCH")],
        companies=[_company(1, "recovery.test", "Recovery")],
        deals=[
            _deal(
                1,
                3,
                pipeline="sales",
                stage="lost",
                amount="12000",
                closedate="2026-07-01T00:00:00Z",
            )
        ],
        pipelines=[
            {
                "id": "sales",
                "label": "Sales",
                "stages": [
                    {
                        "id": "lost",
                        "label": "Closed Lost",
                        "metadata": {"isClosed": "true", "probability": "0"},
                    }
                ],
            }
        ],
    )
    raw = run_dir / "raw"
    (raw / "forms.json").write_text(
        json.dumps([{"guid": "demo", "name": "Demo request"}]),
        encoding="utf-8",
    )
    (raw / "form_submissions.jsonl").write_text(
        json.dumps(
            {
                "form_guid": "demo",
                "submittedAt": "2026-07-05T00:00:00Z",
                "contact": {"vid": "c1"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    profile_run(run_dir)
    build_intent_evidence(run_dir)
    build_journey_evidence_store(run_dir)
    doc = measure_lifecycle_integrity(run_dir)

    recovery = next(
        row
        for row in doc["measurements"]
        if row["id"] == "closed_lost_recovery_opportunity"
    )
    assert recovery["available"] is False
    assert recovery["affected_records"] == 0
    assert doc["recovery_routing"]["lanes"]["closed_lost_recovery"]["count"] == 0
