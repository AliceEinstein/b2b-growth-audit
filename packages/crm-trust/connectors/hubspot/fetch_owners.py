"""Owner list fetch."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .client import HubSpotClient
from .normalize import write_json

PAGE_LIMIT = 100


def fetch(client: HubSpotClient, out_path: Path) -> dict[str, Any]:
    owners: list[dict[str, Any]] = []
    after: str | None = None
    while True:
        params: dict[str, Any] = {"limit": PAGE_LIMIT}
        if after:
            params["after"] = after
        data = client.get("/crm/v3/owners/", params=params)
        owners.extend(data.get("results", []))
        after = ((data.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            break
    write_json(out_path, owners)
    return {"count": len(owners)}
