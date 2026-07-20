"""Persist the minimum portal identity needed by the local human report."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .client import HubSpotClient
from .normalize import write_json


def fetch(
    client: HubSpotClient,
    out_path: Path,
    *,
    business_name: str | None = None,
) -> dict[str, Any]:
    """Read portal metadata and retain only report-navigation fields.

    HubSpot officially guarantees ``portalId`` on this endpoint but does not
    guarantee an account display name.  An explicitly supplied business name
    therefore takes precedence over any optional name-like response field.
    """
    data = client.get("/account-info/v3/details")
    explicit_name = re.sub(r"[\x00-\x1f\x7f]+", " ", str(business_name or "")).strip()
    portal_id = data.get("portalId") or data.get("portal_id")
    result = {
        "status": "available" if portal_id else "unavailable",
        "portal_id": portal_id,
        "business_name": explicit_name[:120] or None,
        "business_name_source": "user_supplied" if explicit_name else "unavailable",
    }
    write_json(out_path, result)
    return result
