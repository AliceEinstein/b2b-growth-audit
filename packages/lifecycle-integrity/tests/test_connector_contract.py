"""Connector contract tests: read-only enforcement, pagination, retry."""
from __future__ import annotations

import json

import httpx
import pytest

from connectors.hubspot.client import (
    READ_ONLY_ALLOWLIST,
    HubSpotClient,
    HubSpotError,
    ReadOnlyViolation,
)
from connectors.hubspot.fetch_account_settings import fetch_company_currency, fetch_portal_identity
from connectors.hubspot.paging import fetch_object_records
from connectors.hubspot.rate_limit import RateLimitPolicy

FAKE_TOKEN = "pat-" + "na1-00000000-0000-0000-0000-000000000000"


def make_client(handler) -> HubSpotClient:
    return HubSpotClient(
        FAKE_TOKEN,
        transport=httpx.MockTransport(handler),
        policy=RateLimitPolicy(max_retries=3, base_delay=0),
        sleep=lambda s: None,
    )


# -- read-only enforcement ---------------------------------------------------


def test_write_requests_are_blocked_before_any_network_call():
    def handler(request):  # pragma: no cover - must never run
        raise AssertionError("network call escaped the read-only allowlist")

    client = make_client(handler)
    for method, path in [
        ("PATCH", "/crm/v3/objects/contacts/123"),
        ("PUT", "/crm/v3/objects/deals/9"),
        ("DELETE", "/crm/v3/objects/companies/5"),
        ("POST", "/crm/v3/objects/contacts"),  # create
        ("POST", "/crm/v3/objects/contacts/merge"),
        ("POST", "/crm/v3/lists"),
        ("DELETE", "/crm/v3/properties/contacts/foo"),
        ("POST", "/automation/v4/flows"),
        ("PATCH", "/automation/v4/flows/123"),
        ("DELETE", "/automation/v4/flows/123"),
        ("POST", "/automation/v4/flows/123/enrollments"),
        ("POST", "/automation/v4/actions"),
        ("PUT", "/settings/currencies/2026-03/company-currency"),
        ("POST", "/settings/currencies/2026-03/company-currency"),
    ]:
        with pytest.raises(ReadOnlyViolation):
            client.request(method, path)


def test_credentialed_client_cannot_be_redirected_to_another_host():
    with pytest.raises(ValueError, match="base_url is fixed"):
        HubSpotClient(FAKE_TOKEN, base_url="https://collector.invalid")


def test_currency_read_is_allowlisted_and_only_code_is_persisted(tmp_path):
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/settings/currencies/2026-03/company-currency"
        return httpx.Response(200, json={"currencyCode": "eur", "sensitive": "discard"})

    result = fetch_company_currency(
        make_client(handler), tmp_path / "account_info.json"
    )
    assert result == {"status": "available", "currency": "EUR"}
    assert json.loads((tmp_path / "account_info.json").read_text()) == result


def test_portal_identity_keeps_only_report_navigation_fields():
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/account-info/v3/details"
        return httpx.Response(
            200,
            json={
                "portalId": 123456,
                "companyName": "Smartify",
                "billingAddress": "must not persist",
                "sensitive": "discard",
            },
        )

    result = fetch_portal_identity(make_client(handler))
    assert result == {
        "identity_status": "available",
        "portal_id": 123456,
        "business_name": "Smartify",
    }


def test_allowlist_contains_only_read_operations():
    assert all(method in {"GET", "POST"} for method, _ in READ_ONLY_ALLOWLIST)
    for method, pattern in READ_ONLY_ALLOWLIST:
        if method == "POST":
            assert (
                "search" in pattern.pattern
                or "batch/read" in pattern.pattern
                or "access-token-info" in pattern.pattern
            ), f"non-read POST in allowlist: {pattern.pattern}"


# -- pagination ---------------------------------------------------------------


def test_list_pagination_follows_after_cursor(tmp_path):
    calls = []

    def handler(request):
        calls.append(dict(request.url.params))
        if "after" not in request.url.params:
            return httpx.Response(
                200,
                json={
                    "results": [{"id": "1"}, {"id": "2"}],
                    "paging": {"next": {"after": "2"}},
                },
            )
        return httpx.Response(200, json={"results": [{"id": "3"}]})

    client = make_client(handler)
    summary = fetch_object_records(
        client, "contacts", ["createdate"], tmp_path / "c.jsonl", days=None
    )
    assert summary["count"] == 3
    assert summary["ids"] == ["1", "2", "3"]
    assert summary["truncated"] is False
    assert len(calls) == 2 and calls[1]["after"] == "2"
    lines = (tmp_path / "c.jsonl").read_text().strip().splitlines()
    assert len(lines) == 3


def test_failed_page_can_resume_from_last_checkpoint(tmp_path):
    first_attempt = {"failed": False}

    def failing_handler(request):
        if request.url.params.get("after") == "2":
            first_attempt["failed"] = True
            return httpx.Response(504)
        return httpx.Response(
            200,
            json={
                "results": [{"id": "1"}, {"id": "2"}],
                "paging": {"next": {"after": "2"}},
            },
        )

    out_path = tmp_path / "contacts.jsonl"
    with pytest.raises(HubSpotError):
        fetch_object_records(
            make_client(failing_handler),
            "contacts",
            ["createdate"],
            out_path,
            days=None,
        )
    assert first_attempt["failed"] is True
    checkpoint = tmp_path / ".checkpoints" / "contacts.json"
    failed_state = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert failed_state["status"] == "failed"
    assert failed_state["count"] == 2
    assert "ids" not in failed_state
    assert failed_state["id_count"] == 2
    assert failed_state["ids_digest"]

    def resume_handler(request):
        assert request.url.params.get("after") == "2"
        return httpx.Response(200, json={"results": [{"id": "3"}]})

    summary = fetch_object_records(
        make_client(resume_handler),
        "contacts",
        ["createdate"],
        out_path,
        days=None,
        resume=True,
    )
    assert summary["count"] == 3
    assert summary["ids"] == ["1", "2", "3"]
    completed_state = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert completed_state["status"] == "completed"
    assert len(out_path.read_text(encoding="utf-8").splitlines()) == 3


def test_search_mode_sends_date_filter(tmp_path):
    payloads = []

    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"results": [{"id": "7"}]})

    client = make_client(handler)
    summary = fetch_object_records(
        client, "deals", ["createdate"], tmp_path / "d.jsonl", days=90
    )
    assert summary["count"] == 1
    flt = payloads[0]["filterGroups"][0]["filters"][0]
    assert flt["propertyName"] == "createdate"
    assert flt["operator"] == "GTE"
    assert int(flt["value"]) > 0
    assert payloads[0]["sorts"] == [
        {"propertyName": "createdate", "direction": "DESCENDING"}
    ]


# -- retry / rate limit --------------------------------------------------------


def test_retries_on_429_then_succeeds():
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"results": []})

    client = make_client(handler)
    assert client.get("/crm/v3/objects/contacts", params={"limit": 1}) == {"results": []}
    assert attempts["n"] == 2


def test_gives_up_after_max_retries():
    def handler(request):
        return httpx.Response(429)

    client = make_client(handler)
    with pytest.raises(HubSpotError) as exc_info:
        client.get("/crm/v3/objects/contacts")
    assert "429" in str(exc_info.value)


# -- secrets ------------------------------------------------------------------


def test_token_never_appears_in_error_messages():
    def handler(request):
        return httpx.Response(
            403,
            json={
                "message": "forbidden jane.doe@example.com",
                "context": "pat-" + "na1-11111111-1111-1111-1111-111111111111",
            },
        )

    client = make_client(handler)
    with pytest.raises(HubSpotError) as exc_info:
        client.get("/crm/v3/objects/contacts")
    assert FAKE_TOKEN not in str(exc_info.value)
    assert "jane.doe@example.com" not in str(exc_info.value)
    assert "11111111-1111-1111-1111-111111111111" not in str(exc_info.value)
    assert FAKE_TOKEN not in client.token_masked
