# HubSpot Private App permissions

Use one dedicated Private App token for this audit. In HubSpot, open
**Settings → Integrations → Private Apps**, create the app, open **Scopes**, and
select every scope below exactly as written.

## Required scopes

| HubSpot scope | Why the audit needs it |
|---|---|
| `crm.objects.contacts.read` | Contact records, contact properties, contact-side associations, and task/meeting/note metadata access used by HubSpot's CRM activity APIs. |
| `crm.objects.companies.read` | Company records and company-side associations. |
| `crm.objects.deals.read` | Deal records, `/crm/v3/pipelines/deals` pipeline/stage definitions, and deal-side associations. |
| `crm.objects.owners.read` | Owner identity and assignment coverage. |
| `crm.schemas.contacts.read` | Contact property definitions, types, options, and governance signals. |
| `crm.schemas.companies.read` | Company property definitions, types, options, and governance signals. |
| `crm.schemas.deals.read` | Deal property definitions, types, options, and governance signals. |

Do not enter a wildcard such as `crm.schemas.*.read`; the three exact schema
scopes must be selected separately.

There is no `crm.pipelines.deals.read` scope in HubSpot's current scope list.
Deal pipeline and stage reads are covered by `crm.objects.deals.read` and are
also tested as a separate endpoint probe. `crm.pipelines.orders.read` is only
for **Order** pipelines and is not needed here.

## Do not grant for this skill

- Any `.write`, `.sensitive.read`, or `.highly_sensitive.read` scope.
- `automation`: CRM Trust does not inspect workflows or scoring automation.
- `crm.objects.projects.read` or `crm.schemas.projects.read`: the current audit
  does not call the HubSpot Projects API.
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

Official references: [HubSpot app scopes](https://developers.hubspot.com/docs/apps/developer-platform/build-apps/authentication/scopes),
[CRM properties](https://developers.hubspot.com/docs/api-reference/latest/crm/properties/guide),
and [CRM owners](https://developers.hubspot.com/docs/api-reference/latest/crm/owners/guide).
