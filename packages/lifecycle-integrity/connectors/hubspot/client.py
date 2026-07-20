"""Read-only HubSpot client.

The read-only guarantee is structural: every request is checked against an
explicit allowlist of read endpoints. There is no code path in this repository
that can write to HubSpot, and this client refuses to send anything not on
the allowlist — including future code that might try.
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable

import httpx

from .auth import mask_token
from .rate_limit import RETRYABLE_STATUS, RateLimitPolicy

BASE_URL = "https://api.hubapi.com"

# Every entry is a read operation. POST entries are HubSpot read APIs that
# happen to use POST (search, batch association read, token introspection).
READ_ONLY_ALLOWLIST: list[tuple[str, re.Pattern[str]]] = [
    ("GET", re.compile(r"^/crm/v3/objects/(contacts|companies|deals|tasks|meetings|notes|calls|emails|communications|marketing_events)$")),
    ("POST", re.compile(r"^/crm/v3/objects/(contacts|companies|deals|tasks|meetings|notes|calls|emails|communications|marketing_events)/search$")),
    ("GET", re.compile(r"^/crm/v3/owners/?$")),
    ("GET", re.compile(r"^/crm/v3/pipelines/(deals|tickets)$")),
    ("GET", re.compile(r"^/crm/v3/properties/(contacts|companies|deals|tasks|meetings|notes|calls|emails|communications|marketing_events)$")),
    ("POST", re.compile(r"^/crm/v4/associations/[a-z0-9_]+/[a-z0-9_]+/batch/read$")),
    # Workflow endpoints are deliberately method-sensitive.  GET retrieves
    # configuration; POST on the same collection path creates a workflow and
    # is therefore not allowlisted.  Batch read is a read API despite using
    # POST, so it is listed explicitly rather than by a broad prefix.
    ("GET", re.compile(r"^/automation/v4/flows$")),
    ("GET", re.compile(r"^/automation/v4/flows/[0-9]+$")),
    ("POST", re.compile(r"^/automation/v4/flows/batch/read$")),
    ("GET", re.compile(r"^/automation/v3/performance/workflow/[0-9]+$")),
    ("GET", re.compile(r"^/account-info/v3/details$")),
    ("GET", re.compile(r"^/settings/currencies/2026-03/company-currency$")),
    ("POST", re.compile(r"^/oauth/v2/private-apps/get/access-token-info$")),
    # Marketing read APIs.  These paths are intentionally explicit: the
    # allowlist must never become a broad prefix that could reach write APIs.
    ("GET", re.compile(r"^/events/event-occurrences/2026-03/?$")),
    ("GET", re.compile(r"^/events/event-occurrences/2026-03/event-types/?$")),
    ("GET", re.compile(r"^/forms/v2/forms/?$")),
    ("GET", re.compile(r"^/form-integrations/v1/submissions/forms/[A-Za-z0-9_-]+$")),
    ("GET", re.compile(r"^/marketing/campaigns/2026-03/?$")),
    ("GET", re.compile(r"^/marketing/campaigns/2026-03/[A-Za-z0-9-]+$")),
    ("GET", re.compile(r"^/marketing/campaigns/2026-03/[A-Za-z0-9-]+/assets/[A-Z_]+$")),
    ("GET", re.compile(r"^/marketing/campaigns/2026-03/[A-Za-z0-9-]+/reports/metrics$")),
]


class ReadOnlyViolation(RuntimeError):
    """Raised when code attempts a request outside the read-only allowlist."""


class HubSpotError(RuntimeError):
    """HubSpot API returned an error or was unreachable."""


class HubSpotClient:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = BASE_URL,
        policy: RateLimitPolicy | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        # The bearer token is a portal credential.  Endpoint read-only
        # enforcement is not sufficient if a caller can redirect the client
        # to an arbitrary host, so production traffic is pinned to HubSpot.
        if base_url.rstrip("/") != BASE_URL:
            raise ValueError(
                "base_url is fixed to the HubSpot API origin; inject a test "
                "transport instead of redirecting credentialed traffic."
            )
        self.token_masked = mask_token(token)
        self.policy = policy or RateLimitPolicy()
        self._sleep = sleep
        self._last_request_at: float | None = None
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
            transport=transport,
        )

    # -- context manager ----------------------------------------------------
    def __enter__(self) -> "HubSpotClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # -- request core -------------------------------------------------------
    def _throttle(self, path: str) -> None:
        interval = self.policy.search_min_interval if "/search" in path else self.policy.min_interval
        now = time.monotonic()
        if self._last_request_at is not None:
            wait = interval - (now - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = time.monotonic()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        method = method.upper()
        if not any(m == method and p.match(path) for m, p in READ_ONLY_ALLOWLIST):
            raise ReadOnlyViolation(
                f"Blocked non-allowlisted request: {method} {path}. "
                "This audit is read-only by design (see safety_policy.md)."
            )

        attempt = 0
        while True:
            try:
                self._throttle(path)
                resp = self._http.request(method, path, params=params, json=json)
            except httpx.TransportError as exc:
                if attempt >= self.policy.max_retries:
                    raise HubSpotError(
                        f"Network failure calling {method} {path} after "
                        f"{attempt + 1} attempts: {exc.__class__.__name__}"
                    ) from exc
                self._sleep(self.policy.delay(attempt))
                attempt += 1
                continue

            if resp.status_code in RETRYABLE_STATUS and attempt < self.policy.max_retries:
                self._sleep(self.policy.delay(attempt, resp.headers.get("Retry-After")))
                attempt += 1
                continue

            if resp.status_code >= 400:
                # Do not echo HubSpot's response body. Error bodies can contain
                # user-entered CRM text or sensitive request context, and an
                # API error must never become a secret/data exfiltration path.
                raise HubSpotError(
                    f"HubSpot returned {resp.status_code} for {method} {path}"
                )
            return resp.json()

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("GET", path, params=params)

    def post(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("POST", path, json=json)
