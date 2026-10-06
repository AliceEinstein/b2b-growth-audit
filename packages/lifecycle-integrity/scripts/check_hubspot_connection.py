"""Preflight: verify HubSpot connectivity and read access. Writes nothing.

Usage:
    python -m scripts.check_hubspot_connection
"""
from __future__ import annotations

from rich.console import Console

from connectors.hubspot.auth import (
    TokenError,
    load_token,
    mask_token,
    token_looks_valid,
)
from connectors.hubspot.client import HubSpotClient, HubSpotError

console = Console()

CORE_REQUIRED_SCOPES = (
    "crm.objects.contacts.read",
    "crm.objects.companies.read",
    "crm.objects.deals.read",
    "crm.objects.owners.read",
    "crm.schemas.contacts.read",
    "crm.schemas.companies.read",
    "crm.schemas.deals.read",
    "settings.currencies.read",
)
FULL_DIAGNOSTIC_SCOPE = "automation"
INTENT_SCOPES = (
    "forms",
    "marketing.campaigns.read",
    "sales-email-read",
)

SCOPE_PROBES = [
    ("contacts", "crm.objects.contacts.read", "/crm/v3/objects/contacts", {"limit": 1}),
    ("companies", "crm.objects.companies.read", "/crm/v3/objects/companies", {"limit": 1}),
    ("deals", "crm.objects.deals.read", "/crm/v3/objects/deals", {"limit": 1}),
    ("owners", "crm.objects.owners.read", "/crm/v3/owners/", {"limit": 1}),
    ("deal pipelines", "crm.objects.deals.read", "/crm/v3/pipelines/deals", None),
    ("contact properties and score fields", "crm.schemas.contacts.read", "/crm/v3/properties/contacts", None),
    ("company properties and score fields", "crm.schemas.companies.read", "/crm/v3/properties/companies", None),
    ("deal properties and score fields", "crm.schemas.deals.read", "/crm/v3/properties/deals", None),
    ("portal currency", "settings.currencies.read", "/settings/currencies/2026-03/company-currency", None),
]
FULL_DIAGNOSTIC_PROBES = [
    ("workflow/scoring root-cause coverage", FULL_DIAGNOSTIC_SCOPE, "/automation/v4/flows", {"limit": 1}),
]
INTENT_PROBES = [
    ("call activity metadata", "crm.objects.contacts.read", "/crm/v3/objects/calls", {"limit": 1}),
    (
        "one-to-one email engagement metadata",
        "sales-email-read",
        "/crm/v3/objects/emails",
        {
            "limit": 1,
            "properties": "createdate,hs_timestamp,hubspot_owner_id,hs_email_status,hs_email_direction,hs_email_type",
        },
    ),
    ("task activity metadata", "crm.objects.contacts.read", "/crm/v3/objects/tasks", {"limit": 1}),
    ("meeting activity metadata", "crm.objects.contacts.read", "/crm/v3/objects/meetings", {"limit": 1}),
    ("note activity metadata", "crm.objects.contacts.read", "/crm/v3/objects/notes", {"limit": 1}),
    ("communication activity metadata", "crm.objects.contacts.read", "/crm/v3/objects/communications", {"limit": 1}),
    ("forms and submission metadata", "forms", "/forms/v2/forms", None),
    ("campaign/channel context", "marketing.campaigns.read", "/marketing/campaigns/2026-03", {"limit": 1}),
    ("record-linked event occurrences", "Professional+ Events API entitlement", "/events/event-occurrences/2026-03/event-types", None),
]


def main() -> int:
    try:
        token = load_token()
    except TokenError as exc:
        console.print(f"[red]❌ {exc}[/red]")
        return 1

    if not token_looks_valid(token):
        console.print(
            "[yellow]⚠️ Token does not look like a HubSpot private app token "
            "(expected pat-…). Continuing anyway.[/yellow]"
        )
    console.print(
        f"Token loaded ({mask_token(token)}) — the full token is never printed or logged."
    )

    with HubSpotClient(token) as client:
        try:
            details = client.get("/account-info/v3/details")
        except HubSpotError as exc:
            console.print(f"[red]❌ Could not reach HubSpot: {exc}[/red]")
            return 1

        console.print("✅ HubSpot connection successful")
        if details.get("portalId"):
            console.print(f"✅ Portal ID detected: {details['portalId']}")
        console.print(
            "✅ Structurally read-only audit mode enforced (endpoint allowlist active)"
        )

        # Token introspection availability varies by portal; fall back to
        # endpoint-level probes if unavailable.
        missing_core_scopes: list[str] = []
        automation_reported = False
        scopes_verified = False
        missing_intent_scopes: list[str] = list(INTENT_SCOPES)
        try:
            info = client.post(
                "/oauth/v2/private-apps/get/access-token-info",
                json={"tokenKey": token},
            )
            scopes = {str(scope) for scope in (info.get("scopes") or [])}
            scopes_verified = True
            console.print(f"✅ Token reports {len(scopes)} scope(s)")
            missing_core_scopes = [
                scope for scope in CORE_REQUIRED_SCOPES if scope not in scopes
            ]
            if missing_core_scopes:
                console.print("[red]❌ Missing required core HubSpot scope(s):[/red]")
                for scope in missing_core_scopes:
                    console.print(f"  [red]- {scope}[/red]")
            else:
                console.print("✅ All required core scopes detected")
            automation_reported = FULL_DIAGNOSTIC_SCOPE in scopes
            if not automation_reported:
                console.print(
                    "[yellow]⚠️ Missing automation: the portal plan or token does "
                    "not expose workflow configuration. The core journey audit "
                    "can still run, but workflow/scoring root causes will not be "
                    "assessed. automation is available only to eligible "
                    "Professional/Enterprise portals.[/yellow]"
                )
            write_scopes = sorted(s for s in scopes if ".write" in s)
            if write_scopes:
                console.print(
                    "[yellow]⚠️ Token has write scopes "
                    f"({', '.join(write_scopes)}). The audit will never use "
                    "them, but a read-only token is recommended.[/yellow]"
                )
            if automation_reported:
                console.print(
                    "[yellow]⚠️ automation scope detected: HubSpot permits workflow "
                    "mutations under this scope, but this audit connector only "
                    "allows workflow reads.[/yellow]"
                )
            if "forms" in scopes:
                console.print(
                    "[yellow]⚠️ forms scope detected: HubSpot does not offer a "
                    "narrower forms.read scope, but this audit connector only "
                    "allows form and submission retrieval.[/yellow]"
                )
            if "sales-email-read" in scopes:
                console.print(
                    "[yellow]⚠️ sales-email-read scope detected: HubSpot describes "
                    "this as read/manage access to one-to-one email engagements. "
                    "This audit connector only retrieves metadata and associations; "
                    "email writes and message content access are not allowlisted.[/yellow]"
                )
            missing_intent_scopes = [scope for scope in INTENT_SCOPES if scope not in scopes]
            if missing_intent_scopes:
                campaign_missing = "marketing.campaigns.read" in missing_intent_scopes
                suffix = (
                    " Campaign/channel context will be unavailable; this scope is "
                    "only available to Marketing Hub Professional/Enterprise "
                    "portals. Other readable record-linked intent sources can "
                    "still be used, and the missing source does not create an "
                    "automatic score deduction."
                    if campaign_missing
                    else ""
                )
                console.print(
                    "[yellow]⚠️ Missing intent source scope(s): "
                    + ", ".join(missing_intent_scopes)
                    + ". The run will disclose those source limitations."
                    + suffix
                    + "[/yellow]"
                )
        except HubSpotError:
            console.print(
                "⚠️ Scope verification partially available. "
                "Continuing with endpoint-level checks."
            )

        failures: list[str] = []
        for label, scope, path, params in SCOPE_PROBES:
            try:
                client.get(path, params=params)
                console.print(f"  ✅ {label} [{scope}]")
            except HubSpotError:
                # Some portals 404 the currencies endpoint; the audit falls
                # back to the company currency in account info.
                if label == "portal currency" and details.get("companyCurrency"):
                    console.print(
                        f"  ✅ {label} [account info fallback; currencies endpoint unavailable]"
                    )
                    continue
                failures.append(f"{label} [{scope}]")
                console.print(
                    f"  [red]❌ {label}: no access — verify {scope}[/red]"
                )

        automation_reachable = False
        for label, scope, path, params in FULL_DIAGNOSTIC_PROBES:
            try:
                client.get(path, params=params)
                automation_reachable = True
                console.print(f"  ✅ {label} [{scope}]")
            except HubSpotError:
                console.print(
                    f"  [yellow]⚠️ {label}: unavailable — verify {scope}. The "
                    "core Lifecycle audit can continue, but the result must be "
                    "labeled core-only.[/yellow]"
                )

        intent_reachable: list[str] = []
        for label, scope, path, params in INTENT_PROBES:
            try:
                # These are real endpoint probes, not scope-name checks. A
                # token can report a scope while an endpoint is unavailable or
                # the portal exposes a different API contract.
                result = client.get(path, params=params)
                if label == "forms and submission metadata":
                    if isinstance(result, list):
                        forms = result
                    elif isinstance(result, dict):
                        forms = result.get("forms", result.get("results", []))
                    else:
                        forms = []
                    if forms and isinstance(forms[0], dict):
                        form_id = forms[0].get("guid") or forms[0].get("id")
                        if form_id:
                            client.get(
                                f"/form-integrations/v1/submissions/forms/{form_id}",
                                params={"limit": 50},
                            )
                intent_reachable.append(label)
                console.print(f"  ✅ {label} [{scope}]")
            except HubSpotError:
                console.print(
                    f"  [yellow]⚠️ {label}: unavailable — verify {scope}. "
                    "The report will disclose this source gap.[/yellow]"
                )

    if missing_core_scopes or failures:
        console.print(
            "[red]❌ Lifecycle core preflight failed. Grant every core scope in "
            "skills/hubspot-lifecycle-integrity-audit/hubspot_scopes.md before "
            "running the audit.[/red]"
        )
        return 1
    if automation_reachable:
        if (
            len(intent_reachable) == len(INTENT_PROBES)
            and scopes_verified
            and not missing_intent_scopes
        ):
            console.print("✅ Full Lifecycle + Intent + Automation & Scoring diagnostic ready")
        else:
            scope_note = (
                " token intent scopes are incomplete"
                if scopes_verified and missing_intent_scopes
                else " token scopes could not be verified"
                if not scopes_verified
                else ""
            )
            console.print(
                "⚠️ Lifecycle + Automation ready; intent source probes are partial "
                f"({len(intent_reachable)}/{len(INTENT_PROBES)});{scope_note or ' source coverage is incomplete'} "
                "and the limitation will be disclosed"
            )
    else:
        console.print(
            "[yellow]⚠️ Core-only preflight passed; full automation/scoring "
            f"coverage is not ready. Intent probes passed {len(intent_reachable)}/"
            f"{len(INTENT_PROBES)}.[/yellow]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
