"""Read-only workflow inventory and aggregate performance acquisition.

The workflow API is intentionally isolated from the CRM snapshot fetchers.
This module only calls paths that the HubSpotClient allowlist exposes.  Raw
workflow responses remain local; downstream code consumes the sanitized
artifacts written by :mod:`core.automation_integrity`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .client import HubSpotClient, HubSpotError
from .normalize import write_json

WORKFLOW_LIST_PATH = "/automation/v4/flows"
WORKFLOW_DETAIL_PATH = "/automation/v4/flows/{flow_id}"
WORKFLOW_BATCH_READ_PATH = "/automation/v4/flows/batch/read"
WORKFLOW_PERFORMANCE_PATH = "/automation/v3/performance/workflow/{flow_id}"
PAGE_SIZE = 100
BATCH_SIZE = 100
DEFAULT_PERFORMANCE_DAYS = 548  # approximately the 18-month B2B cycle window


def _paged_get(client: HubSpotClient, path: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    after: str | None = None
    while True:
        params: dict[str, Any] = {"limit": PAGE_SIZE}
        if after:
            params["after"] = after
        payload = client.get(path, params=params)
        page = payload.get("results") or []
        if not isinstance(page, list):
            raise HubSpotError(f"HubSpot returned an invalid workflow page for {path}")
        results.extend(item for item in page if isinstance(item, dict))
        paging = payload.get("paging") or {}
        next_page = paging.get("next") if isinstance(paging, dict) else None
        next_after = next_page.get("after") if isinstance(next_page, dict) else None
        if not next_after:
            break
        after = str(next_after)
    return results


def list_workflows(client: HubSpotClient) -> list[dict[str, Any]]:
    return _paged_get(client, WORKFLOW_LIST_PATH)


def _workflow_ids(rows: Iterable[dict[str, Any]]) -> list[str]:
    return [str(row["id"]) for row in rows if str(row.get("id") or "").isdigit()]


def read_workflow_details(
    client: HubSpotClient,
    workflow_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Read full specs, preserving per-workflow failures without aborting.

    Batch read is attempted first.  A failed batch falls back to individual
    GETs because one malformed workflow must not hide healthy workflow
    configuration from the audit.
    """
    ids = _workflow_ids(workflow_rows)
    details: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for start in range(0, len(ids), BATCH_SIZE):
        chunk = ids[start : start + BATCH_SIZE]
        fallback_ids = list(chunk)
        try:
            payload = client.post(
                WORKFLOW_BATCH_READ_PATH,
                json={"inputs": [{"flowId": flow_id, "type": "FLOW_ID"} for flow_id in chunk]},
            )
            rows = payload.get("results") or []
            if isinstance(rows, list) and rows:
                details.extend(row for row in rows if isinstance(row, dict))
                returned = {str(row.get("id")) for row in rows if row.get("id") is not None}
                fallback_ids = [flow_id for flow_id in chunk if flow_id not in returned]
        except HubSpotError:
            fallback_ids = list(chunk)

        for flow_id in fallback_ids:
            try:
                detail = client.get(WORKFLOW_DETAIL_PATH.format(flow_id=flow_id))
                if isinstance(detail, dict):
                    details.append(detail)
                else:
                    failures.append(
                        {"workflow_id": flow_id, "reason": "invalid_detail"}
                    )
            except HubSpotError:
                failures.append(
                    {"workflow_id": flow_id, "reason": "detail_unavailable"}
                )
    return details, failures


def _performance_window(
    *, days: int | None, completed_at: str | None
) -> tuple[int, int, str]:
    end = datetime.now(timezone.utc)
    if completed_at:
        try:
            end = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
        except ValueError:
            pass
    window_days = days if days is not None else DEFAULT_PERFORMANCE_DAYS
    start = end - timedelta(days=window_days)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000), f"{window_days} days"


def read_performance(
    client: HubSpotClient,
    workflow_ids: Iterable[str],
    *,
    days: int | None,
    completed_at: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    start_ms, end_ms, label = _performance_window(days=days, completed_at=completed_at)
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for flow_id in workflow_ids:
        if not str(flow_id).isdigit():
            continue
        try:
            payload = client.get(
                WORKFLOW_PERFORMANCE_PATH.format(flow_id=flow_id),
                params={"start": start_ms, "end": end_ms, "bucket": "MONTH"},
            )
            series = payload if isinstance(payload, list) else payload.get("results", [])
            if isinstance(series, list):
                for row in series:
                    if isinstance(row, dict):
                        rows.append({"workflow_id": str(flow_id), **row})
        except HubSpotError:
            failures.append({"workflow_id": str(flow_id), "reason": "performance_unavailable"})
    return rows, failures, {
        "start_ms": start_ms,
        "end_ms": end_ms,
        "bucket": "MONTH",
        "label": label,
    }


def fetch_snapshot(
    client: HubSpotClient,
    raw_dir: Path,
    *,
    days: int | None,
    completed_at: str | None,
) -> dict[str, Any]:
    """Fetch automation data with graceful degradation and no write path."""
    raw_dir = Path(raw_dir) / "automation"
    raw_dir.mkdir(parents=True, exist_ok=True)
    coverage: dict[str, Any] = {
        "status": "unavailable",
        "provider": "hubspot_automation_v4",
        "scope": "automation",
        "workflow_inventory_count": 0,
        "workflow_detail_count": 0,
        "workflow_detail_failures": [],
        "performance_workflow_count": 0,
        "performance_failures": [],
        "performance_window": None,
        "limitations": [],
    }
    try:
        inventory = list_workflows(client)
    except HubSpotError:
        coverage["limitations"].append("Workflow inventory was unavailable.")
        write_json(raw_dir / "workflows_index.json", [])
        write_json(raw_dir / "workflows.json", [])
        write_json(raw_dir / "workflow_performance.json", [])
        return coverage

    write_json(raw_dir / "workflows_index.json", inventory)
    coverage["workflow_inventory_count"] = len(inventory)
    details, detail_failures = read_workflow_details(client, inventory)
    write_json(raw_dir / "workflows.json", details)
    coverage["workflow_detail_count"] = len(details)
    coverage["workflow_detail_failures"] = detail_failures
    if detail_failures:
        coverage["limitations"].append("Some workflow specifications could not be read.")

    # Performance is acquired for all successfully detailed workflows in this
    # first pass; deterministic processing later narrows the report to
    # journey-relevant workflows. This keeps the acquisition pass complete and
    # avoids asking an agent to choose which APIs to call.
    performance, performance_failures, performance_window = read_performance(
        client,
        (row.get("id") for row in details),
        days=days,
        completed_at=completed_at,
    )
    write_json(raw_dir / "workflow_performance.json", performance)
    coverage["performance_workflow_count"] = len({row.get("workflow_id") for row in performance})
    coverage["performance_failures"] = performance_failures
    coverage["performance_window"] = performance_window
    if performance_failures:
        coverage["limitations"].append("Performance was unavailable for some workflows.")
    if not details:
        coverage["status"] = "configuration_only"
    elif detail_failures or performance_failures:
        coverage["status"] = "partial"
    else:
        coverage["status"] = "full"
    return coverage
