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
)
FULL_DIAGNOSTIC_SCOPE = "automation"

SCOPE_PROBES = [
    ("contacts", "crm.objects.contacts.read", "/crm/v3/objects/contacts", {"limit": 1}),
    ("companies", "crm.objects.companies.read", "/crm/v3/objects/companies", {"limit": 1}),
    ("deals", "crm.objects.deals.read", "/crm/v3/objects/deals", {"limit": 1}),
    ("owners", "crm.objects.owners.read", "/crm/v3/owners/", {"limit": 1}),
    ("deal pipelines", "crm.objects.deals.read", "/crm/v3/pipelines/deals", None),
    ("contact properties and score fields", "crm.schemas.contacts.read", "/crm/v3/properties/contacts", None),
    ("company properties and score fields", "crm.schemas.companies.read", "/crm/v3/properties/companies", None),
    ("deal properties and score fields", "crm.schemas.deals.read", "/crm/v3/properties/deals", None),
]
FULL_DIAGNOSTIC_PROBES = [
    ("workflow/scoring root-cause coverage", FULL_DIAGNOSTIC_SCOPE, "/automation/v4/flows", {"limit": 1}),
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
        try:
            info = client.post(
                "/oauth/v2/private-apps/get/access-token-info",
                json={"tokenKey": token},
            )
            scopes = {str(scope) for scope in (info.get("scopes") or [])}
            console.print(f"✅ Token reports {len(scopes)} scope(s)")
            missing_core_scopes = [
                scope for scope in CORE_REQUIRED_SCOPES if scope not in scopes
            ]
            if missing_core_scopes:
                console.print("[red]❌ Missing required core HubSpot scope(s):[/red]")
                for scope in missing_core_scopes:
                    console.print(f"  [red]- {scope}[/red]")
            else:
                console.print("✅ All seven required core scopes detected")
            automation_reported = FULL_DIAGNOSTIC_SCOPE in scopes
            if not automation_reported:
                console.print(
                    "[yellow]⚠️ Missing automation: this token can run only the "
                    "core journey audit, not the complete workflow/scoring "
                    "root-cause diagnostic.[/yellow]"
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

    if missing_core_scopes or failures:
        console.print(
            "[red]❌ Lifecycle core preflight failed. Grant every core scope in "
            "skills/hubspot-lifecycle-integrity-audit/hubspot_scopes.md before "
            "running the audit.[/red]"
        )
        return 1
    if automation_reachable:
        console.print("✅ Full Lifecycle + Automation & Scoring diagnostic ready")
    else:
        console.print(
            "[yellow]⚠️ Core-only preflight passed; full automation/scoring "
            "coverage is not ready.[/yellow]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
