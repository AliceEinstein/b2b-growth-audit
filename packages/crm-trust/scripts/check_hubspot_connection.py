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

REQUIRED_SCOPES = (
    "crm.objects.contacts.read",
    "crm.objects.companies.read",
    "crm.objects.deals.read",
    "crm.objects.owners.read",
    "crm.schemas.contacts.read",
    "crm.schemas.companies.read",
    "crm.schemas.deals.read",
)

SCOPE_PROBES = [
    ("contacts", "crm.objects.contacts.read", "/crm/v3/objects/contacts", {"limit": 1}),
    ("companies", "crm.objects.companies.read", "/crm/v3/objects/companies", {"limit": 1}),
    ("deals", "crm.objects.deals.read", "/crm/v3/objects/deals", {"limit": 1}),
    ("owners", "crm.objects.owners.read", "/crm/v3/owners/", {"limit": 1}),
    ("deal pipelines", "crm.objects.deals.read", "/crm/v3/pipelines/deals", None),
    ("contact properties", "crm.schemas.contacts.read", "/crm/v3/properties/contacts", None),
    ("company properties", "crm.schemas.companies.read", "/crm/v3/properties/companies", None),
    ("deal properties", "crm.schemas.deals.read", "/crm/v3/properties/deals", None),
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
        console.print("✅ Read-only audit mode enforced (endpoint allowlist active)")

        # Token introspection availability varies by portal; fall back to
        # endpoint-level probes if unavailable.
        missing_scopes: list[str] = []
        try:
            info = client.post(
                "/oauth/v2/private-apps/get/access-token-info",
                json={"tokenKey": token},
            )
            scopes = {str(scope) for scope in (info.get("scopes") or [])}
            console.print(f"✅ Token reports {len(scopes)} scope(s)")
            missing_scopes = [scope for scope in REQUIRED_SCOPES if scope not in scopes]
            if missing_scopes:
                console.print("[red]❌ Missing required HubSpot scope(s):[/red]")
                for scope in missing_scopes:
                    console.print(f"  [red]- {scope}[/red]")
            else:
                console.print("✅ All seven required CRM Trust scopes detected")
            write_scopes = sorted(s for s in scopes if ".write" in s)
            if write_scopes:
                console.print(
                    "[yellow]⚠️ Token has write scopes "
                    f"({', '.join(write_scopes)}). The audit will never use "
                    "them, but a read-only token is recommended.[/yellow]"
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
                failures.append(f"{label} [{scope}]")
                console.print(
                    f"  [red]❌ {label}: no access — verify {scope}[/red]"
                )

    if missing_scopes or failures:
        console.print(
            "[red]❌ CRM Trust preflight failed. Grant every scope in "
            "skills/hubspot-crm-trust-audit/hubspot_scopes.md before running "
            "the audit.[/red]"
        )
        return 1
    console.print("✅ CRM Trust permission preflight passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
