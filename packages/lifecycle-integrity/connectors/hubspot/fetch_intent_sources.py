"""Read-only acquisition for marketing intent sources.

Raw responses and the small local-only identity hints needed to link form
submissions stay in the gitignored snapshot.  Downstream agents never receive
these files.  The deterministic normalizer removes values, query strings,
email addresses, and campaign free text before the agent boundary.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from .client import HubSpotClient, HubSpotError
from .normalize import JsonlWriter, write_json

EVENT_TYPES_PATH = "/events/event-occurrences/2026-03/event-types"
EVENT_OCCURRENCES_PATH = "/events/event-occurrences/2026-03"
FORM_LIST_PATH = "/forms/v2/forms"
FORM_SUBMISSIONS_PATH = "/form-integrations/v1/submissions/forms/{form_guid}"
CAMPAIGN_LIST_PATH = "/marketing/campaigns/2026-03"
CAMPAIGN_ASSETS_PATH = "/marketing/campaigns/2026-03/{campaign_id}/assets/{asset_type}"
CAMPAIGN_METRICS_PATH = "/marketing/campaigns/2026-03/{campaign_id}/reports/metrics"

EVENT_TYPE_PATTERN = re.compile(
    r"page|visit|form|demo|contact.?sales|intent|score|meeting|sequence|reply|"
    r"conversion|campaign|marketing|content|email|open|click|delivered|bounce",
    re.IGNORECASE,
)
EVENT_TYPE_CAP = 60
PAGE_SIZE = 100
# The Events API uses the CRM object name for ``objectType`` (for example,
# ``contact``), not the CRM object type ID (``0-1``). Keeping this explicit
# avoids a silent empty result set on real portals.
EVENT_CONTACT_OBJECT_TYPE = "contact"
FORM_SUBMISSION_PAGE_SIZE = 50  # HubSpot's documented maximum for this endpoint.
FORM_LIST_PAGE_SIZE = 50
CAMPAIGN_ASSET_TYPES = (
    "AD_CAMPAIGN",
    "SOCIAL_BROADCAST",
    "FORM",
    "MARKETING_EMAIL",
    "SITE_PAGE",
    "LANDING_PAGE",
    "WEB_INTERACTIVE",
)


def _results(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        value = data.get("results")
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _form_results(data: Any) -> list[dict[str, Any]]:
    """Read both legacy Forms response shapes without guessing a CRM schema."""
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("forms", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _next_after(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    paging = data.get("paging") or {}
    next_page = paging.get("next") if isinstance(paging, dict) else None
    return str(next_page.get("after")) if isinstance(next_page, dict) and next_page.get("after") is not None else None


def _paginate(
    client: HubSpotClient,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    max_pages: int = 1000,
    page_size: int = PAGE_SIZE,
) -> Iterable[dict[str, Any]]:
    after: str | None = None
    for _ in range(max_pages):
        request_params = dict(params or {})
        request_params.setdefault("limit", page_size)
        if after is not None:
            request_params["after"] = after
        data = client.get(path, params=request_params)
        rows = _results(data)
        for row in rows:
            yield row
        after = _next_after(data)
        if after is None or not rows:
            break


def fetch_event_types(client: HubSpotClient, out_path: Path) -> list[dict[str, Any]]:
    """Fetch the exhaustive event type catalog for local capability mapping."""
    data = client.get(EVENT_TYPES_PATH)
    # The current Events contract returns ``{"eventTypes": ["..."]}``,
    # while older/test tenants may expose a ``results`` list of objects.
    # Normalize both into the object shape consumed by the selector.
    if isinstance(data, dict) and isinstance(data.get("eventTypes"), list):
        rows = [
            {"fullyQualifiedName": str(value), "name": str(value)}
            for value in data["eventTypes"]
            if isinstance(value, str) and value.strip()
        ]
    else:
        rows = _results(data)
    write_json(out_path, rows)
    return rows


def select_event_types(rows: list[dict[str, Any]], *, cap: int = EVENT_TYPE_CAP) -> list[str]:
    """Select intent-relevant event types without assuming a portal taxonomy."""
    names = []
    for row in rows:
        name = str(
            row.get("fullyQualifiedName")
            or row.get("fully_qualified_name")
            or row.get("name")
            or row.get("eventType")
            or ""
        )
        if name and EVENT_TYPE_PATTERN.search(name):
            names.append(name)
    if "e_visited_page" not in names:
        names.insert(0, "e_visited_page")
    return list(dict.fromkeys(names))[:cap]


def _fetch_forms(client: HubSpotClient) -> list[dict[str, Any]]:
    """Fetch the legacy Forms catalog using its list/offset contract.

    The v2 Forms endpoint returns the complete catalog when ``limit`` is not
    supplied in the documented response shape.  Some tenants expose an
    offset-paginated wrapper instead, so support that shape as well while
    never sending the cursor-based ``after`` parameter used by CRM APIs.
    """
    first = client.get(FORM_LIST_PATH, params={"formTypes": "ALL"})
    forms = _form_results(first)
    if isinstance(first, list) or not isinstance(first, dict):
        return forms
    paging = first.get("paging") or {}
    has_more = bool(first.get("hasMore") or first.get("has_more"))
    next_offset = None
    if isinstance(paging, dict):
        next_page = paging.get("next")
        if isinstance(next_page, dict):
            next_offset = next_page.get("offset")
    if next_offset is None:
        next_offset = first.get("offset") if has_more else None
    for _ in range(1000):
        if next_offset in (None, ""):
            break
        data = client.get(
            FORM_LIST_PATH,
            params={
                "formTypes": "ALL",
                "limit": FORM_LIST_PAGE_SIZE,
                "offset": next_offset,
            },
        )
        page = _form_results(data)
        if not page:
            break
        forms.extend(page)
        paging = data.get("paging") or {} if isinstance(data, dict) else {}
        next_offset = None
        if isinstance(paging, dict) and isinstance(paging.get("next"), dict):
            next_offset = paging["next"].get("offset")
        if next_offset is None and isinstance(data, dict) and (
            data.get("hasMore") or data.get("has_more")
        ):
            next_offset = data.get("offset")
    return list({str(row.get("guid") or row.get("id")): row for row in forms}.values())


def _submission_email(submission: dict[str, Any]) -> str | None:
    """Extract only an email hint into the local raw snapshot for ID linking."""
    value = submission.get("email")
    values = submission.get("values")
    if value in (None, "") and isinstance(values, dict):
        for key in ("email", "hs_email"):
            if values.get(key) not in (None, ""):
                value = values[key]
                break
    if value in (None, "") and isinstance(values, list):
        for item in values:
            if isinstance(item, dict) and str(item.get("name") or "").lower() in {"email", "hs_email"}:
                value = item.get("value")
                break
    if value in (None, ""):
        return None
    text = str(value).strip().lower()
    return text[:320] if "@" in text else None


def fetch_event_occurrences(
    client: HubSpotClient,
    out_path: Path,
    event_types: list[str],
    *,
    days: int | None = None,
    max_records: int = 100_000,
) -> dict[str, Any]:
    """Fetch record-linked intent events, bounded by time and volume."""
    count = 0
    truncated = False
    failed_event_types: list[str] = []
    with JsonlWriter(out_path) as writer:
        for event_type in event_types:
            params: dict[str, Any] = {
                "eventType": event_type,
                "objectType": EVENT_CONTACT_OBJECT_TYPE,
                "limit": PAGE_SIZE,
            }
            if days is not None:
                # Event APIs filter on occurrence time, unlike CRM object
                # search, so this does not silently confuse createdate with
                # behavioural recency.
                from datetime import datetime, timedelta, timezone

                cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                params["occurredAfter"] = cutoff.isoformat()
            try:
                for row in _paginate(client, EVENT_OCCURRENCES_PATH, params=params):
                    writer.write(row)
                    count += 1
                    if count >= max_records:
                        truncated = True
                        break
            except HubSpotError:
                # HubSpot returns an exhaustive catalog that can include event
                # types unavailable to this portal. One unsupported type must
                # not erase page-view/form evidence from other types.
                failed_event_types.append(event_type)
            if truncated:
                break
    return {
        "count": count,
        "event_type_count": len(event_types),
        "failed_event_type_count": len(failed_event_types),
        "truncated": truncated,
        "metadata_only": True,
    }


def fetch_forms_and_submissions(
    client: HubSpotClient,
    raw_dir: Path,
    *,
    max_submissions: int = 100_000,
) -> dict[str, Any]:
    """Fetch form definitions and submission metadata without persisting fields."""
    forms = _fetch_forms(client)
    # Keep definitions local for deterministic form-name/channel mapping. The
    # submission endpoint may return values as part of its response, but the
    # runner persists only the minimum timestamp/path/conversion/contact-link
    # metadata and never persists uploaded files or arbitrary field values.
    write_json(raw_dir / "forms.json", forms)
    count = 0
    truncated = False
    with JsonlWriter(raw_dir / "form_submissions.jsonl") as writer:
        for form in forms:
            form_guid = str(form.get("guid") or form.get("id") or "")
            if not form_guid:
                continue
            for submission in _paginate(
                client,
                FORM_SUBMISSIONS_PATH.format(form_guid=form_guid),
                page_size=FORM_SUBMISSION_PAGE_SIZE,
            ):
                # Form submissions may contain field values and page URLs in
                # the API response. They are discarded immediately; only the
                # selected metadata below is written to the local snapshot,
                # then deterministic normalization applies coarse path
                # classification before any agent boundary.
                writer.write({
                    "form_guid": form_guid,
                    "submittedAt": submission.get("submittedAt"),
                    "pageUrl": submission.get("pageUrl"),
                    "conversionId": submission.get("conversionId"),
                    "contact": submission.get("contact"),
                    # This stays local and is used only to match against the
                    # already-fetched contacts snapshot. It is never emitted
                    # into processed artifacts.
                    "contact_email": _submission_email(submission),
                })
                count += 1
                if count >= max_submissions:
                    truncated = True
                    break
            if truncated:
                break
    return {"form_count": len(forms), "submission_count": count, "truncated": truncated}


def fetch_campaign_context(
    client: HubSpotClient,
    raw_dir: Path,
    *,
    days: int | None = None,
    max_campaigns: int = 5000,
    max_api_calls: int = 4000,
) -> dict[str, Any]:
    """Fetch campaign, asset, and aggregate channel evidence.

    Campaign asset APIs are one-resource-per-campaign/type. A hard request
    budget prevents a large portal from hanging indefinitely; the manifest
    reports the resulting partial coverage instead of pretending it is full.
    """
    campaigns: list[dict[str, Any]] = []
    campaign_truncated = False
    for campaign in _paginate(client, CAMPAIGN_LIST_PATH, params={}):
        if len(campaigns) >= max_campaigns:
            campaign_truncated = True
            break
        campaigns.append(campaign)
    write_json(raw_dir / "campaigns.json", campaigns)
    assets: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    api_calls = 0
    api_budget_truncated = False
    date_params: dict[str, Any] = {}
    if days is not None:
        from datetime import datetime, timedelta, timezone

        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=days)
        date_params = {"startDate": start.isoformat(), "endDate": end.isoformat()}
    # Asset and metric endpoints can fail (some portals answer 500) while the
    # campaign list works. A failure skips that asset type or the metrics for
    # the rest of the run instead of discarding the campaign list.
    failed_asset_types: set[str] = set()
    asset_failures = 0
    metric_failures = 0
    for campaign in campaigns:
        campaign_id = str(campaign.get("id") or campaign.get("campaignGuid") or "")
        if not campaign_id:
            continue
        for asset_type in CAMPAIGN_ASSET_TYPES:
            if asset_type in failed_asset_types:
                continue
            if api_calls >= max_api_calls:
                api_budget_truncated = True
                break
            api_calls += 1
            params = dict(date_params)
            try:
                for asset in _paginate(
                    client,
                    CAMPAIGN_ASSETS_PATH.format(campaign_id=campaign_id, asset_type=asset_type),
                    params=params,
                ):
                    assets.append({
                        "campaign_id": campaign_id,
                        "asset_type": asset_type,
                        "asset_id": asset.get("id"),
                        "asset_name": asset.get("name"),
                        "metrics": asset.get("metrics") or {},
                    })
            except HubSpotError:
                asset_failures += 1
                failed_asset_types.add(asset_type)
        if api_budget_truncated:
            break
        if metric_failures:
            continue
        if api_calls >= max_api_calls:
            api_budget_truncated = True
            break
        api_calls += 1
        try:
            metric = client.get(
                CAMPAIGN_METRICS_PATH.format(campaign_id=campaign_id),
                params=date_params or None,
            )
        except HubSpotError:
            metric_failures += 1
            continue
        metrics.append({"campaign_id": campaign_id, "metrics": metric})
    write_json(raw_dir / "campaign_assets.json", assets)
    write_json(raw_dir / "campaign_metrics.json", metrics)
    return {
        "campaign_count": len(campaigns),
        "asset_count": len(assets),
        "metric_count": len(metrics),
        "asset_failures": asset_failures,
        "failed_asset_types": sorted(failed_asset_types),
        "metric_failures": metric_failures,
        "truncated": campaign_truncated or api_budget_truncated,
        "campaign_limit": max_campaigns,
        "api_call_count": api_calls,
        "api_call_budget": max_api_calls,
    }
