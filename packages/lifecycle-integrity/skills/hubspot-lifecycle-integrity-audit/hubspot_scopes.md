# HubSpot Private App permissions

Use one dedicated Private App token for the complete Lifecycle Integrity
diagnostic. In HubSpot, open **Settings → Integrations → Private Apps**, create
the app, open **Scopes**, and use the scope search to select the IDs in the
full-diagnostic list. HubSpot can show a human-readable permission label beside
the ID; the code-formatted value below is the exact internal scope ID that the
token must report.

## Full Lifecycle Integrity diagnostic

| Exact HubSpot scope ID | HubSpot availability | Required coverage |
|---|---|---|
| `crm.objects.contacts.read` | All accounts | Contact journeys, lifecycle state, attribution and intent fields, contact associations, and optional task/meeting/note metadata. |
| `crm.objects.companies.read` | All accounts | Account journeys, ABM/partner evidence, company state, and associations. |
| `crm.objects.deals.read` | All accounts | Deal journeys, `/crm/v3/pipelines/deals` pipeline/stage definitions, amounts on existing deals, and deal associations. |
| `crm.objects.owners.read` | All accounts | Ownership and handoff coverage. |
| `settings.currencies.read` | All accounts | Portal currency metadata so existing deal amounts are labelled with an explicit unit. |
| `crm.schemas.contacts.read` | All accounts | Contact property definitions and score-like contact fields. |
| `crm.schemas.companies.read` | All accounts | Company property definitions and score-like company fields. |
| `crm.schemas.deals.read` | All accounts | Deal property definitions and score-like deal fields. |
| `forms` | All accounts | Form definitions and submission timestamps/conversion metadata; arbitrary submission field values and uploaded files are discarded before the local snapshot is written. |
| `sales-email-read` | All accounts | One-to-one sales-email timing, direction, reply/status, owner, and record-association evidence used to evaluate follow-up continuity. Email bodies, subjects, headers, and addresses are never requested or persisted. |
| `automation` | Eligible Professional or Enterprise accounts only | Workflow inventory, dependencies, aggregate performance, and workflow/scoring root-cause context. |
| `marketing.campaigns.read` | Marketing Hub Professional or Enterprise only | Campaign, asset-type, and aggregate channel context for inbound, paid, social, and content mapping. |

The unusual-looking IDs are intentional: HubSpot's Forms permission is exactly
`forms`, not `forms.read`; its one-to-one sales email permission is exactly
`sales-email-read`; and its workflow permission is exactly `automation`, not
`automation.read`. Do not invent or substitute a more conventional-looking
scope name.

HubSpot only offers plan-dependent scopes to eligible portals. If
`automation` or `marketing.campaigns.read` is absent from the scope picker,
first verify the portal subscription. If the portal is not eligible, leave the
scope unselected and run with the documented fallback; there is no substitute
scope. If an all-account scope is missing, confirm that the user configuring
the app can manage Private Apps, reload the editor, and search for the full ID.

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
`calls.read`, `tasks.read`, `meetings.read`, or `notes.read` scope used by this
connector; those activity reads use the relevant CRM object permission.
`sales-email-read` is retained for complete one-to-one email engagement access
across HubSpot account configurations and to avoid redacted email-engagement
details that would weaken follow-up analysis. The connector extracts only
timestamp, direction, status/reply, owner, and record associations. It never
requests or persists note bodies, email bodies, subjects, headers, recordings,
or addresses.

The currency endpoint is read-only and stores only the returned currency code
in `raw/account_info.json`. If the scope is unavailable, the audit continues
but withholds any deal amount whose currency cannot be established; it never
labels an amount with a guessed portal default.

The Events API is used for record-linked page/visit, conversion-style, and
sequence-email event occurrences when the portal exposes them. The current
Events API surface requires an eligible Professional or Enterprise HubSpot
subscription; it does not add another Private App scope ID to the picker. The
preflight therefore verifies the endpoint entitlement directly. If the
endpoint is unavailable, label record-linked event coverage unavailable and
continue with CRM activity, Forms, and other readable evidence; never replace
the missing event stream with zero events.

The current
adapter does not call HubSpot's separate Marketing Email Event Analytics API;
1:1 email metadata comes from CRM email activities and aggregate campaign
metrics remain channel context. Form submissions are normalized to submission
time, form alias, conversion identifier, and a coarse page class.
Campaign/social/ad metrics are aggregate context only; they cannot by
themselves create a person-level recovery opportunity. A source that is
permission-denied is reported as unavailable, never as zero intent.

## Important broad-scope warning

HubSpot's `automation`, `forms`, and `sales-email-read` scopes are broader than
their names may suggest at the platform level:

- `automation` can authorize workflow mutations and is available only to
  eligible Professional or Enterprise portals.
- `forms` covers the Forms APIs; HubSpot does not offer a narrower
  `forms.read` scope.
- `sales-email-read` grants access to read and manage one-to-one email
  engagements; it is retained to keep follow-up evidence complete.

They are included because HubSpot does not provide narrower permissions for
the required diagnostic surfaces. This package compensates structurally: its
method-sensitive endpoint allowlist permits only workflow `GET` and read-style
batch endpoints, Forms `GET` endpoints, and CRM email retrieval/search. It
rejects workflow, form, and email create, update, delete, enroll, association,
send, and action requests before any network call.

Without `automation`, the core journey and leakage audit can still run. The
preflight and report must label workflow/scoring root-cause coverage as
incomplete; the result must not be presented as a complete Automation &
Scoring Integrity Audit. This is separate from the CLI's `--core-only` option,
which explicitly skips activity and intent acquisition.

## Plan availability and fallback behavior

Not every HubSpot subscription exposes every read surface used by the full
diagnostic. A missing optional scope is a coverage limitation, not a failed
audit and not evidence that the underlying records or controls do not exist.

| Capability | When available | When the portal or token cannot provide it | Effect on the lifecycle score |
|---|---|---|---|
| Core CRM objects, schemas, pipelines, owners, associations, and currency | Core lifecycle measurements and amount-safe reporting | The run cannot produce a trustworthy core report and should stop at preflight | No score is issued without the core evidence required to assess the journey links |
| `automation` (eligible Professional/Enterprise portals) | Workflow inventory, dependencies, aggregate performance, and scoring-output root-cause context | Core lifecycle and any available intent analysis still run. Automation artifacts are marked unavailable; the report cannot claim workflow/scoring root-cause coverage | No automatic deduction. Automation is diagnostic context, not a scored lifecycle link; the score is based only on assessable lifecycle evidence |
| `marketing.campaigns.read` (Marketing Hub Professional/Enterprise) | Aggregate campaign, asset-type, and channel context | Campaign context is marked unavailable. The audit still uses record-linked Events, Forms, Calls, Emails, and HubSpot properties when those sources are available | No automatic deduction. Campaign aggregates never create person-level intent. Scored control coverage is affected only if the missing source also makes a required control denominator or evidence set unavailable |
| Events API entitlement (eligible Professional/Enterprise portals; no additional picker scope) | Record-linked page, visit, conversion-style, and sequence event occurrences | Event coverage is marked unavailable. The audit continues with Forms, CRM activities, and CRM properties; no-event claims are prohibited | No automatic deduction. A control that depends on unavailable event evidence is excluded from assessed weight; coverage falls and the score is withheld below 70% |
| Other intent sources such as `forms` or `sales-email-read` | More complete intent, escalation, and recovery evidence | The affected source is marked partial or unavailable; the audit does not substitute zero events | The affected scored control can become `not_assessable`. Scored control coverage is shown; below 70% coverage the numeric score is withheld rather than guessed |

The report must distinguish these states:

- `available` or `full`: the source was readable.
- `partial`: some requested evidence was readable, but the source is incomplete.
- `permission_or_api_unavailable`: the endpoint or scope was not available.
- `observed_no_events`: the endpoint worked and returned no rows; this is not the
  same as unavailable access.

The score is computed from nine explicit controls grouped into five lifecycle links, not from subscription tier,
pipeline amount, journey confidence, automation availability, or campaign
count. Missing scored-control evidence is excluded from the assessed denominator. At
70% or more scored control coverage, the score is normalized over the controls
that were actually assessable. Below 70%, the report says `Not scored —
insufficient evidence`; it never turns unknown into a failure. Diagnostic data
coverage for automation, campaign/channel, and record-linked activity is shown
separately, so 100% scored control coverage cannot be read as full data access.

## Write access is not required

Do not add any `.write` scope to the audit token. Lifecycle Integrity never
creates, updates, merges, deletes, enrolls, reassigns, sends, or stage-changes
HubSpot records. As described above, HubSpot's `automation`, `forms`, and
`sales-email-read` scopes are broader at the platform level even though their
IDs do not end in `.write`; this connector restricts all three to explicit
read/retrieval endpoints.

## If the token already has other read scopes

The audit uses only the scopes in the full-diagnostic table. Additional read
scopes do not expand what the connector fetches or what the report covers
because the code uses an endpoint allowlist and explicit property selection.

For clarity, the current audit does not use:

- HubSpot Projects object permissions — **Projects object** data is not used in
  the current lifecycle model, so no Projects permission belongs in this
  checklist. A project value synced into a contact, company, or deal property
  is already covered by the relevant CRM object read and can be used when it is
  a deterministic journey signal.
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

Scope IDs and account availability were rechecked against HubSpot's current
scope list on 21 July 2026. Official references: [HubSpot app scopes](https://developers.hubspot.com/docs/apps/developer-platform/build-apps/authentication/scopes),
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
