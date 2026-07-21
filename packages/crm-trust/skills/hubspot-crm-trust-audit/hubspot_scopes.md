# HubSpot Private App permissions

Use one dedicated Private App token for this audit. In HubSpot, open
**Settings → Integrations → Private Apps**, create the app, open **Scopes**, and
use the scope search to select every scope ID below. HubSpot can show a
human-readable permission label beside the ID; the code-formatted value in this
table is the exact internal scope ID that the token must report.

## Required scopes

| Exact HubSpot scope ID | HubSpot availability | Why the audit needs it |
|---|---|---|
| `crm.objects.contacts.read` | All accounts | Contact records, contact properties, contact-side associations, and task/meeting/note metadata access used by HubSpot's CRM activity APIs. |
| `crm.objects.companies.read` | All accounts | Company records and company-side associations. |
| `crm.objects.deals.read` | All accounts | Deal records, `/crm/v3/pipelines/deals` pipeline/stage definitions, and deal-side associations. |
| `crm.objects.owners.read` | All accounts | Owner identity and assignment coverage. |
| `crm.schemas.contacts.read` | All accounts | Contact property definitions, types, options, and governance signals. |
| `crm.schemas.companies.read` | All accounts | Company property definitions, types, options, and governance signals. |
| `crm.schemas.deals.read` | All accounts | Deal property definitions, types, options, and governance signals. |

Do not enter a wildcard such as `crm.schemas.*.read`; the three exact schema
scopes must be selected separately.

There is no `crm.pipelines.deals.read` scope in HubSpot's current scope list.
Deal pipeline and stage reads are covered by `crm.objects.deals.read` and are
also tested as a separate endpoint probe. `crm.pipelines.orders.read` is only
for **Order** pipelines and is not needed here.

If one of these seven IDs does not appear in the Private App scope search, do
not choose a similarly named permission. Confirm that the user configuring the
app can manage Private Apps, reload the scope editor, and search for the full
ID. All seven are listed by HubSpot as available to all accounts. The audit
must stop at preflight if an exact required scope or its endpoint is still
unavailable.

## Write access is not required

Do not add any `.write` scope to the audit token. CRM Trust never creates,
updates, merges, deletes, reassigns, or stage-changes HubSpot records. The
connector also rejects write requests before any network call.

## If the token already has other read scopes

The audit uses only the seven read scopes listed above. Additional read scopes
do not expand what the connector fetches or what the report covers because the
code uses an endpoint allowlist and an explicit property selection.

For clarity, the current audit does not use:

- `.sensitive.read` or `.highly_sensitive.read` scopes. These unlock values in
  HubSpot Sensitive Data properties, such as personal identification,
  financial, health/medical, or government-identifier data. CRM Trust can read
  the property definitions through its schema scopes but deliberately excludes
  protected property values from snapshot candidates.
- `automation`: CRM Trust does not inspect workflows or scoring automation.
- HubSpot Projects object permissions: the current audit does not call the
  Projects API, so no Projects permission belongs in this checklist.
- `crm.objects.leads.read`, `crm.lists.read`, custom-object, campaign, form, or
  email scopes: the current connector does not call those APIs.

Granting unused scopes does not add report coverage. The connector also has an
endpoint allowlist, so a broader token cannot make this audit write to HubSpot
or silently inspect an unsupported object.

No additional scope is required for report identity. The connector reads the
portal ID from HubSpot's account-info endpoint to construct local navigation
links. Because that endpoint does not guarantee a business display name, pass
the exact name with `--business-name` or `CRM_AUDIT_BUSINESS_NAME`; never use a
customer Company record as the portal's identity.

## Verify before running

1. Copy the token into a local `.env` as `HUBSPOT_PRIVATE_APP_TOKEN`.
2. Never paste the token into a prompt, report, issue, or commit.
3. Run `python -m scripts.check_hubspot_connection`.
4. Do not start the audit until all seven required scopes and endpoint probes
   pass.

Scope IDs and account availability were rechecked against HubSpot's current
scope list on 21 July 2026. Official references: [HubSpot app scopes](https://developers.hubspot.com/docs/apps/developer-platform/build-apps/authentication/scopes),
[HubSpot Sensitive Data API](https://developers.hubspot.com/docs/api-reference/latest/crm/properties/sensitive-data),
[CRM properties](https://developers.hubspot.com/docs/api-reference/latest/crm/properties/guide),
and [CRM owners](https://developers.hubspot.com/docs/api-reference/latest/crm/owners/guide).
