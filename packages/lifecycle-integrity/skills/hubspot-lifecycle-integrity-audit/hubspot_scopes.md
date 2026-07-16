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
| `crm.schemas.contacts.read` | Contact property definitions and score-like contact fields. |
| `crm.schemas.companies.read` | Company property definitions and score-like company fields. |
| `crm.schemas.deals.read` | Deal property definitions and score-like deal fields. |
| `automation` | Workflow inventory, dependencies, aggregate performance, and workflow/scoring root-cause context. |

HubSpot does not support `crm.schemas.*.read`; select all three schema scopes.
There is no separate HubSpot `scoring.read` scope used by this implementation.
Scoring coverage comes from score-like contact/company/deal properties plus
workflow configuration, so it requires the object reads, the three schema
reads, and `automation` together.

There is also no `crm.pipelines.deals.read` scope. Deal pipelines and stages
are covered by `crm.objects.deals.read` and receive their own preflight
endpoint probe. Do not substitute `crm.pipelines.orders.read`; that scope is
only for Order pipelines.

The optional `--include-activities` mode does not require invented
`tasks.read`, `meetings.read`, or `notes.read` scopes. HubSpot's activity read
APIs use the contact read authorization already listed above. The connector
fetches activity metadata only and deliberately excludes note bodies.

## Important automation warning

HubSpot's `automation` scope is mutation-capable at the platform level and is
available only to eligible Professional or Enterprise portals. It is included
because HubSpot does not provide a narrower workflow-read scope for the v4
workflow APIs. This package compensates structurally: its connector permits
only workflow `GET` and read-style batch endpoints and rejects workflow create,
update, delete, enroll, and action requests before any network call.

Without `automation`, the core journey and leakage audit can still run. The
preflight and report must label it **core-only**: workflow and scoring
root-cause coverage is unavailable, and the result must not be presented as a
complete Automation & Scoring Integrity Audit.

## Scopes that are not current coverage

These are real HubSpot read scopes, but granting them does not change the
current report because the connector does not call their APIs:

- `crm.objects.projects.read` and `crm.schemas.projects.read` — HubSpot
  **Projects object** data is not used in the current lifecycle model.
- `crm.objects.leads.read` — the current no-deal recovery population is built
  from high-intent contacts, not HubSpot Lead object records.
- `crm.lists.read`, custom-object, campaign, form, sequence, and sensitive-data
  scopes.

If Projects, the HubSpot Lead object, lists, or another object becomes a
supported journey signal later, add its read endpoints, sanitization,
evidence contract, tests, and exact read scopes together. Never request a
scope now and imply unsupported report coverage.

## Verify before running

1. Copy the token into local `.env` as `HUBSPOT_PRIVATE_APP_TOKEN`.
2. Never paste the token into a prompt, report, issue, or commit.
3. Run `python -m scripts.check_hubspot_connection`.
4. Confirm all seven core scopes pass and that `automation` is reported as
   available for the full diagnostic.

Official references: [HubSpot app scopes](https://developers.hubspot.com/docs/apps/developer-platform/build-apps/authentication/scopes),
[workflow v4 API](https://developers.hubspot.com/docs/api-reference/legacy/automation/workflows/guide),
[CRM properties](https://developers.hubspot.com/docs/api-reference/latest/crm/properties/guide),
and [Projects API](https://developers.hubspot.com/docs/api-reference/latest/crm/objects/projects/guide).
