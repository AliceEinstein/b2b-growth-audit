"""Deal pipeline + stage definitions fetch."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .client import HubSpotClient
from .normalize import write_json


def fetch(client: HubSpotClient, out_path: Path) -> dict[str, Any]:
    data = client.get("/crm/v3/pipelines/deals")
    results = data.get("results", [])
    write_json(out_path, results)
    return {"count": len(results)}
