from __future__ import annotations

from connectors.hubspot.client import HubSpotError
from scripts import check_hubspot_connection


class FakeClient:
    failed_path = None
    scopes = [
        *check_hubspot_connection.CORE_REQUIRED_SCOPES,
        check_hubspot_connection.FULL_DIAGNOSTIC_SCOPE,
    ]

    def __init__(self, token):
        self.token = token

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def get(self, path, params=None):
        if path == self.failed_path:
            raise HubSpotError("missing scope")
        if path == "/account-info/v3/details":
            return {"portalId": 123}
        return {"results": []}

    def post(self, path, json=None):
        return {"scopes": self.scopes}


def test_connection_check_passes_when_all_required_reads_work(monkeypatch):
    FakeClient.failed_path = None
    FakeClient.scopes = [
        *check_hubspot_connection.CORE_REQUIRED_SCOPES,
        check_hubspot_connection.FULL_DIAGNOSTIC_SCOPE,
        *check_hubspot_connection.INTENT_SCOPES,
    ]
    monkeypatch.setattr(check_hubspot_connection, "load_token", lambda: "pat-na1-test")
    monkeypatch.setattr(check_hubspot_connection, "HubSpotClient", FakeClient)
    assert check_hubspot_connection.main() == 0


def test_connection_check_discloses_broad_platform_scopes(monkeypatch, capsys):
    FakeClient.failed_path = None
    FakeClient.scopes = [
        *check_hubspot_connection.CORE_REQUIRED_SCOPES,
        check_hubspot_connection.FULL_DIAGNOSTIC_SCOPE,
        *check_hubspot_connection.INTENT_SCOPES,
    ]
    monkeypatch.setattr(check_hubspot_connection, "load_token", lambda: "pat-na1-test")
    monkeypatch.setattr(check_hubspot_connection, "HubSpotClient", FakeClient)

    assert check_hubspot_connection.main() == 0
    output = " ".join(capsys.readouterr().out.split())
    assert "forms scope detected" in output
    assert "does not offer a narrower forms.read scope" in output
    assert "sales-email-read scope detected" in output
    assert "only retrieves metadata and associations" in output


def test_connection_check_uses_endpoint_probes_for_intent_readiness(monkeypatch, capsys):
    FakeClient.failed_path = "/forms/v2/forms"
    FakeClient.scopes = [
        *check_hubspot_connection.CORE_REQUIRED_SCOPES,
        check_hubspot_connection.FULL_DIAGNOSTIC_SCOPE,
        *check_hubspot_connection.INTENT_SCOPES,
    ]
    monkeypatch.setattr(check_hubspot_connection, "load_token", lambda: "pat-na1-test")
    monkeypatch.setattr(check_hubspot_connection, "HubSpotClient", FakeClient)
    assert check_hubspot_connection.main() == 0
    output = capsys.readouterr().out
    assert "intent source probes are partial" in output


def test_connection_check_does_not_claim_full_intent_when_email_scope_is_missing(
    monkeypatch, capsys
):
    FakeClient.failed_path = None
    FakeClient.scopes = [
        *check_hubspot_connection.CORE_REQUIRED_SCOPES,
        check_hubspot_connection.FULL_DIAGNOSTIC_SCOPE,
        "forms",
        "marketing.campaigns.read",
    ]
    monkeypatch.setattr(check_hubspot_connection, "load_token", lambda: "pat-na1-test")
    monkeypatch.setattr(check_hubspot_connection, "HubSpotClient", FakeClient)
    assert check_hubspot_connection.main() == 0
    output = " ".join(capsys.readouterr().out.split())
    assert "sales-email-read" in output
    assert "Full Lifecycle + Intent" not in output
    assert "token intent scopes are incomplete" in output


def test_connection_check_fails_when_required_read_scope_is_missing(monkeypatch):
    FakeClient.failed_path = "/crm/v3/objects/deals"
    FakeClient.scopes = [
        *check_hubspot_connection.CORE_REQUIRED_SCOPES,
        check_hubspot_connection.FULL_DIAGNOSTIC_SCOPE,
    ]
    monkeypatch.setattr(check_hubspot_connection, "load_token", lambda: "pat-na1-test")
    monkeypatch.setattr(check_hubspot_connection, "HubSpotClient", FakeClient)
    assert check_hubspot_connection.main() == 1


def test_connection_check_fails_when_schema_scope_is_missing(monkeypatch):
    FakeClient.failed_path = None
    FakeClient.scopes = [
        scope
        for scope in check_hubspot_connection.CORE_REQUIRED_SCOPES
        if scope != "crm.schemas.deals.read"
    ] + [check_hubspot_connection.FULL_DIAGNOSTIC_SCOPE]
    monkeypatch.setattr(check_hubspot_connection, "load_token", lambda: "pat-na1-test")
    monkeypatch.setattr(check_hubspot_connection, "HubSpotClient", FakeClient)
    assert check_hubspot_connection.main() == 1


def test_connection_check_allows_but_labels_core_only_without_automation(
    monkeypatch, capsys
):
    FakeClient.failed_path = "/automation/v4/flows"
    FakeClient.scopes = list(check_hubspot_connection.CORE_REQUIRED_SCOPES)
    monkeypatch.setattr(check_hubspot_connection, "load_token", lambda: "pat-na1-test")
    monkeypatch.setattr(check_hubspot_connection, "HubSpotClient", FakeClient)
    assert check_hubspot_connection.main() == 0
    output = capsys.readouterr().out
    normalized = " ".join(output.split())
    assert "Core-only" in normalized
    assert "Professional/Enterprise portals" in normalized
    assert "workflow/scoring root causes will not be assessed" in normalized


def test_connection_check_explains_campaign_fallback_when_scope_is_missing(
    monkeypatch, capsys
):
    FakeClient.failed_path = None
    FakeClient.scopes = [
        *check_hubspot_connection.CORE_REQUIRED_SCOPES,
        check_hubspot_connection.FULL_DIAGNOSTIC_SCOPE,
        "forms",
        "sales-email-read",
    ]
    monkeypatch.setattr(check_hubspot_connection, "load_token", lambda: "pat-na1-test")
    monkeypatch.setattr(check_hubspot_connection, "HubSpotClient", FakeClient)
    assert check_hubspot_connection.main() == 0
    output = capsys.readouterr().out
    assert "marketing.campaigns.read" in output
    assert "Campaign/channel context will be unavailable" in output
    assert "Marketing Hub Professional/Enterprise" in output
    assert "record-linked intent sources can still be used" in output
    assert "does not create an automatic score deduction" in output
