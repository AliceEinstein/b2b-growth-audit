"""Fetch the portal currency needed to label deal amounts safely."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .client import HubSpotClient, HubSpotError
from .normalize import write_json


def fetch_company_currency(client: HubSpotClient, out_path: Path) -> dict[str, Any]:
    """Persist only the currency code, never the full account settings response.

    Some portals answer the currencies endpoint with 404 even when the token
    holds settings.currencies.read. Account info reports the same company
    currency, so it is the fallback before the currency counts as unavailable.
    """
    error: HubSpotError | None = None
    currency = None
    try:
        data = client.get("/settings/currencies/2026-03/company-currency")
        currency = data.get("currencyCode") or data.get("currency_code") or data.get("currency")
    except HubSpotError as exc:
        error = exc
    result: dict[str, Any] = {
        "status": "available" if currency else "unavailable",
        "currency": str(currency).upper() if currency else None,
    }
    if not currency:
        try:
            fallback = client.get("/account-info/v3/details").get("companyCurrency")
        except HubSpotError:
            fallback = None
        if fallback:
            result = {
                "status": "available",
                "currency": str(fallback).upper(),
                "currency_source": "account_info",
            }
        elif error is not None:
            raise error
    write_json(out_path, result)
    return result


def fetch_portal_identity(client: HubSpotClient) -> dict[str, Any]:
    """Read portal identity fields; business name remains an optional hint.

    HubSpot guarantees portal ID but not a human-facing business display name.
    The runner therefore accepts an explicit ``--business-name`` override.
    """
    data = client.get("/account-info/v3/details")
    business_name = next(
        (
            data.get(key)
            for key in ("companyName", "company_name", "accountName", "account_name", "name")
            if data.get(key) not in (None, "")
        ),
        None,
    )
    portal_id = data.get("portalId") or data.get("portal_id")
    return {
        "identity_status": "available" if business_name or portal_id else "unavailable",
        "portal_id": portal_id,
        "business_name": str(business_name)[:120] if business_name else None,
    }
