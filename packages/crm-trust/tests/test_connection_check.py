from __future__ import annotations

from connectors.hubspot.client import HubSpotError
from scripts import check_hubspot_connection


class FakeClient:
    failed_path = None
    scopes = list(check_hubspot_connection.REQUIRED_SCOPES)

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


def _install(monkeypatch):
    monkeypatch.setattr(check_hubspot_connection, "load_token", lambda: "pat-na1-test")
    monkeypatch.setattr(check_hubspot_connection, "HubSpotClient", FakeClient)


def test_connection_check_passes_with_all_exact_scopes(monkeypatch):
    FakeClient.failed_path = None
    FakeClient.scopes = list(check_hubspot_connection.REQUIRED_SCOPES)
    _install(monkeypatch)
    assert check_hubspot_connection.main() == 0


def test_connection_check_fails_when_exact_schema_scope_is_missing(monkeypatch):
    FakeClient.failed_path = None
    FakeClient.scopes = [
        scope
        for scope in check_hubspot_connection.REQUIRED_SCOPES
        if scope != "crm.schemas.companies.read"
    ]
    _install(monkeypatch)
    assert check_hubspot_connection.main() == 1


def test_connection_check_fails_when_pipeline_endpoint_is_unreachable(monkeypatch):
    FakeClient.failed_path = "/crm/v3/pipelines/deals"
    FakeClient.scopes = list(check_hubspot_connection.REQUIRED_SCOPES)
    _install(monkeypatch)
    assert check_hubspot_connection.main() == 1
