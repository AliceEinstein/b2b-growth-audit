# HubSpot Private App permissions

Use one dedicated Private App token for the complete Lifecycle Integrity
diagnostic. In HubSpot, open **Settings → Integrations → Private Apps**, create
the app, open **Scopes**, and select every scope in the full-diagnostic list
exactly as written.

## Full Lifecycle Integrity diagnostic

| HubSpot scope | Required coverage |
|---|---|
| `crm.objects.contacts.read` | Contact journeys, lifecycle state, attribution and intent fields, contact associations, and optional task/meeting/note metadata. |
| `crm.objects.companies.read` | Account journeys, ABM/partner evidence, company state, and associations. |
| `crm.objects.deals.read` | Deal journeys, `/crm/v3/pipelines/deals` pipeline/stage definitions, amounts on existing deals, and deal associations. |
| `crm.objects.owners.read` | Ownership and handoff coverage. |
| `settings.currencies.read` | Portal currency metadata so existing deal amounts are labelled with an explicit unit. |
| `crm.schemas.contacts.read` | Contact property definitions and score-like contact fields. |
| `crm.schemas.companies.read` | Company property definitions and score-like company fields. |
| `crm.schemas.deals.read` | Deal property definitions and score-like deal fields. |
| `automation` | Workflow inventory, dependencies, aggregate performance, and workflow/scoring root-cause context. |
| `forms` | Form definitions and submission timestamps/conversion metadata; field values are not persisted downstream. |
| `marketing.campaigns.read` | Campaign, asset-type, and aggregate channel context for inbound, paid, social, and content mapping. |
| `sales-email-read` | Email activity metadata and direction/status where the portal exposes it; email bodies, subjects, and addresses are never requested. |

Do not enter the wildcard string `crm.schemas.*.read`; select all three exact
schema scopes above.
There is no separate HubSpot `scoring.read` scope used by this implementation.
Scoring coverage comes from score-like contact/company/deal properties plus
workflow configuration, so it requires the object reads, the three schema
reads, and `automation` together.

There is also no `crm.pipelines.deals.read` scope. Deal pipelines and stages
are covered by `crm.objects.deals.read` and receive their own preflight
endpoint probe. Do not substitute `crm.pipelines.orders.read`; that scope is
only for Order pipelines.

The lifecycle runner enables intent/activity acquisition by default. It reads
calls, emails, communications, tasks, meetings, and notes as metadata and
fetches record associations separately. HubSpot does not expose a separate
`tasks.read`, `meetings.read`, or `notes.read` scope used by this connector;
activity authorization is evaluated by the relevant CRM/product scopes. The
`sales-email-read` scope is included because email activity availability varies
by portal and product entitlement. The connector never requests note bodies,
email bodies, subjects, recordings, or addresses.

The currency endpoint is read-only and stores only the returned currency code
in `raw/account_info.json`. If the scope is unavailable, the audit continues
but withholds any deal amount whose currency cannot be established; it never
labels an amount with a guessed portal default.

The Events API is used for record-linked page/visit, conversion-style, and
sequence-email event occurrences when the portal exposes them. The current
adapter does not call HubSpot's separate Marketing Email Event Analytics API;
1:1 email metadata comes from CRM email activities and aggregate campaign
metrics remain channel context. Form submissions are normalized to submission
time, form alias, conversion identifier, and a coarse page class.
Campaign/social/ad metrics are aggregate context only; they cannot by
themselves create a person-level recovery opportunity. A source that is
permission-denied is reported as unavailable, never as zero intent.

## Important automation warning

HubSpot's `automation` scope is mutation-capable at the platform level and is
available only to eligible Professional or Enterprise portals. It is included
because HubSpot does not provide a narrower workflow-read scope for the v4
workflow APIs. This package compensates structurally: its connector permits
only workflow `GET` and read-style batch endpoints and rejects workflow create,
update, delete, enroll, and action requests before any network call.

Without `automation`, the core journey and leakage audit can still run. The
preflight and report must label workflow/scoring root-cause coverage as
incomplete; the result must not be presented as a complete Automation &
Scoring Integrity Audit. This is separate from the CLI's `--core-only` option,
which explicitly skips activity and intent acquisition.

## Write access is not required

Do not add any `.write` scope to the audit token. Lifecycle Integrity never
creates, updates, merges, deletes, enrolls, reassigns, or stage-changes HubSpot
records. The required `automation` scope is the one platform-level exception
described above: HubSpot makes it mutation-capable, while this connector
restricts it to allowlisted read endpoints.

## If the token already has other read scopes

The audit uses only the scopes in the full-diagnostic table. Additional read
scopes do not expand what the connector fetches or what the report covers
because the code uses an endpoint allowlist and explicit property selection.

For clarity, the current audit does not use:

- `crm.objects.projects.read` and `crm.schemas.projects.read` — HubSpot
  **Projects object** data is not used in the current lifecycle model. A
  project value synced into a contact, company, or deal property is already
  covered by the relevant CRM object read and can be used when it is a
  deterministic journey signal.
- `crm.objects.leads.read` — the current no-deal recovery population is built
  from high-intent contacts, not HubSpot Lead object records.
- `.sensitive.read` or `.highly_sensitive.read` scopes — these unlock values
  in HubSpot Sensitive Data properties, such as personal identification,
  financial, health/medical, or government-identifier data. Lifecycle
  Integrity can read the property definitions through its schema scopes but
  deliberately excludes protected property values from journey-signal
  candidates. If a business intentionally stores a journey-critical signal in
  a protected property, that requires a separate privacy and sanitization
  design; adding the scope alone does not extend this audit.
- `crm.lists.read`, custom-object, and sequence scopes.
- `crm.objects.marketing_events.read` — the current implementation uses the
  Events occurrence endpoint and does not read the Marketing Events CRM
  object; add this only if a future adapter explicitly uses that object.

If Projects, the HubSpot Lead object, lists, or another object becomes a
supported journey signal later, add its read endpoints, sanitization,
evidence contract, tests, and exact read scopes together. Never request a
scope now and imply unsupported report coverage.

## Verify before running

1. Copy the token into local `.env` as `HUBSPOT_PRIVATE_APP_TOKEN`.
2. Never paste the token into a prompt, report, issue, or commit.
3. Run `python -m scripts.check_hubspot_connection`.
4. Confirm all seven core CRM scopes plus `settings.currencies.read`,
   `automation`, `forms`,
   `marketing.campaigns.read`, and `sales-email-read` pass for the full
   intent-enabled diagnostic. A missing source is disclosed in the capability
   matrix and does not become a false zero.

Official references: [HubSpot app scopes](https://developers.hubspot.com/docs/apps/developer-platform/build-apps/authentication/scopes),
[HubSpot Sensitive Data API](https://developers.hubspot.com/docs/api-reference/latest/crm/properties/sensitive-data),
[date-versioned API reference](https://developers.hubspot.com/docs/reference/api?hsLang=en),
[Events API](https://developers.hubspot.com/docs/api-reference/latest/events/guide),
[Campaigns API](https://developers.hubspot.com/docs/api-reference/latest/marketing/campaigns/guide),
[legacy Forms/API overview](https://developers.hubspot.com/docs/api-reference/legacy/overview),
[workflow v4 API](https://developers.hubspot.com/docs/api-reference/legacy/automation/workflows/guide),
[CRM properties](https://developers.hubspot.com/docs/api-reference/latest/crm/properties/guide),
[Currencies API](https://developers.hubspot.com/docs/api-reference/latest/account/settings/multicurrency/guide),
and [Projects API](https://developers.hubspot.com/docs/api-reference/latest/crm/objects/projects/guide).

### Compatibility and upgrade rule

The current adapter is intentionally pinned to these upstream contracts:

| Feature | Implemented route family | Upstream compatibility note |
|---|---|---|
| CRM objects, properties, pipelines, owners | numeric v3 | HubSpot's legacy numeric API family; re-test before a date-versioned migration. |
| Associations | numeric v4 batch read | Read-only batch endpoint; keep method and path allowlisted separately. |
| Record-linked Events | `events/.../2026-03` | Date-versioned route; `objectType=contact` is required by the current contract. |
| Campaigns and channel context | `marketing/campaigns/2026-03` | Date-versioned route; aggregate context only. |
| Currency metadata | `settings/currencies/2026-03` | Date-versioned route; amounts are withheld if currency is unavailable. |
| Forms and submissions | `/forms/v2/forms` + `/form-integrations/v1/...` | Legacy Forms routes; no form field values are persisted downstream. |
| Workflow inventory and performance | `/automation/v4/...` + `/automation/v3/...` | Workflow v4 is documented as beta; configuration is diagnostic, never proof of execution. |

If any route is retired, changes response shape, or requires a new scope, the
preflight and fetcher must degrade to `partial` or
`permission_or_api_unavailable`. Do not add a fallback that silently converts
an API failure into zero signals. An upgrade is complete only after updating
the read-only allowlist, raw-to-processed sanitization, output contract,
connector tests, and synthetic golden fixtures. The audit does not request
legacy write endpoints or beta mutation operations.
