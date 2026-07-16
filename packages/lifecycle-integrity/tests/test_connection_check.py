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
    ]
    monkeypatch.setattr(check_hubspot_connection, "load_token", lambda: "pat-na1-test")
    monkeypatch.setattr(check_hubspot_connection, "HubSpotClient", FakeClient)
    assert check_hubspot_connection.main() == 0


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
    assert "Core-only" in capsys.readouterr().out
