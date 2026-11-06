# Database map

COMPASS currently uses one local SQLite database for all workspaces. A workspace
is a **tenant**: it owns its source snapshots, reviews, findings, settings, and
monitoring records. A jurisdiction identifies the state or other policy scope;
it is not the access-control boundary.

This document describes the implemented schema in [store.py](../compass/store.py)
and [monitoring.py](../compass/monitoring.py), rather than a proposed production
database. There are **16 application tables**. SQLite also creates its internal
`sqlite_sequence` table for the audit counter.

## For policy leads: where your work goes

```text
+-------------------+     +--------------------+     +-------------------+
| Sources           | --> | Review run         | --> | Findings          |
| Text + metadata   |     | Selected versions  |     | Evidence + owner  |
| New version = new |     | Date + profile     |     | review + decision |
| saved snapshot    |     | Saved input scope  |     | Current status    |
+-------------------+     +--------------------+     +-------------------+
                                  |
                                  v
                         +--------------------+
                         | Analysis report    |
                         | Saved results and  |
                         | input snapshots    |
                         +--------------------+

Sources / context / workflow changes --> Monitoring job --> In-app notice
Workspace settings -------------------> Analysis controls
Your display preference --------------> Simple or Advanced view
User actions -------------------------> Audit history
```

Switching your view changes your own display preference. Analysis settings apply
to the workspace and determine which checks run. A saved report retains its
inputs even after settings or findings change. An export includes saved reports
and the current findings and related audit history from a consistent read.

## For engineers: relationships and boundaries

The arrows below point from a child record to its referenced parent. These are
SQL foreign keys; the diagram groups related tables and is not a count of rows.

```text
IDENTITY AND WORKSPACE

 sessions ----------> memberships <---------- preferences
                        |     |
                        v     v
                     tenants users <---------- audit.actor_id
                        ^
                        |
              +---------+--------------------+
              |         |                    |
       workspace_   workspace_         monitoring_state
        settings     context

REVIEW AND ANALYSIS

 run_sources -----> runs <------------- analysis_reports
      |              ^                        (same tenant + run)
      v              |
   sources <----- findings
                  (instrument and external source roles)

 monitoring_jobs ---> runs          (nullable tenant + run FK)

 Direct tenant FKs: sources, runs, audit, monitoring_jobs, inapp_notices,
                   memberships, workspace_settings, workspace_context,
                   monitoring_state.
 Other tenant links are enforced through composite parent keys.
```

Each relationship can have multiple child rows unless a primary or unique key
limits it. `workspace_settings`, `workspace_context`, and `monitoring_state` have
at most one row per tenant. Each tenant/user membership has at most one
preference row and can have multiple sessions.

The following are **application or JSON links**, not SQL foreign keys:

```text
 sources.payload.replaces_source_id ........> sources.id
 sources.payload.reference_keys ............> sources.payload.source_key
 runs.payload.source_ids ...................> sources.id
 workspace_context.payload.assets
   [*].source_keys .........................> sources.payload.source_key
 monitoring_jobs.analysis_id ...............> analysis_reports.id
 inapp_notices.payload.run_id ...............> runs.id
 inapp_notices.payload.analysis_id ..........> analysis_reports.id
 audit.entity_type + entity_id .............> relevant application entity

 Legend:  ----> SQL FK       ....> application/JSON link or matching key
```

The run's JSON source list also has normalized `run_sources` rows. Source
replacement is checked by the application for the same tenant, source role,
jurisdiction, and compatible stable identifier. Citation and inventory mappings
use declared source keys; a title is not a stable identifier. Report payloads
embed evidence source snapshots, rather than adding a report-to-source join
table. An assignee is a text label, not a user FK or a grant of access.

Tenant isolation currently depends on application queries, authorization checks,
and tenant-qualified composite FKs. Those FKs prevent linking a finding or run
association to another tenant's source. They do not provide row-level security
for arbitrary SQL access. There is no database RLS policy, separate database per
tenant, or production provisioning flow. `jurisdiction_id` is a text field, with
no `jurisdictions` table. Public reference metadata does not make a tenant's
database rows accessible to other tenants.

## Table and key inventory

`PK` means primary key; `UQ` means unique constraint; `FK` means SQL foreign key.
Identifiers are text. New source, run, finding, job, report, and notice IDs use
UUIDs; demo offices and users use readable fixture keys. Audit IDs are integers,
and session keys are token hashes. `payload`, `profile`, and `details`
are JSON serialized into SQLite `TEXT`; their fields are validated and interpreted
by the application, not normalized into additional tables.

### Identity and configuration: 7 tables

| Table | Keys and SQL references | Other stored data |
| --- | --- | --- |
| `tenants` | PK `id`. | `name`, `jurisdiction_id`, current `profile` JSON, `profile_hash`. |
| `users` | PK `id`. | `name`. |
| `memberships` | PK `(tenant_id, user_id)`; separate FKs to `tenants.id` and `users.id`. | `role`, constrained to `owner` or `reviewer`. |
| `sessions` | PK `token_hash`; composite FK `(tenant_id, user_id)` to `memberships`. | `expires_at`. Stores a token hash rather than a raw session token. |
| `preferences` | PK `(tenant_id, user_id)`; composite FK to `memberships`. | `view_mode`, constrained to `simple` or `advanced`. |
| `workspace_settings` | PK/FK `tenant_id` to `tenants.id`. | `payload` with analysis switches, feature switches, horizon, monitoring controls; `updated_at`. |
| `workspace_context` | PK/FK `tenant_id` to `tenants.id`. | `payload` with topics, programs, funding conditions, inventory assets; `updated_at`. |

Missing settings/context rows resolve to validated application defaults. Merely
reading those defaults does not insert singleton rows. Profiles live in
`tenants.profile`; assets live inside `workspace_context.payload.assets`.

### Review and accountability: 5 tables

| Table | Keys and SQL references | Other stored data |
| --- | --- | --- |
| `sources` | PK `id`; FK `tenant_id` to `tenants.id`; UQ `(tenant_id, id)`; UQ `(tenant_id, content_hash)`. | `payload`, `content_hash`, `created_at`. Re-adding identical canonical input within a tenant returns the existing snapshot. |
| `runs` | PK `id`; FK `tenant_id` to `tenants.id`; UQ `(tenant_id, id)`. | `payload`, `created_at`. |
| `run_sources` | PK `(tenant_id, run_id, source_id)`; composite FKs `(tenant_id, run_id)` to `runs` and `(tenant_id, source_id)` to `sources`. | Association only; no JSON payload. |
| `findings` | PK `id`; UQ `(tenant_id, id)`; composite FK `(tenant_id, run_id)` to `runs`; composite FKs `(tenant_id, instrument_source_id)` and `(tenant_id, external_source_id)` to `sources`. | `payload`, `created_at`; the two evidence-source IDs are also explicit SQL columns. |
| `audit` | PK `id`, integer autoincrement; FK `tenant_id` to `tenants.id`; FK `actor_id` to `users.id`. | `actor_name`, `action`, `entity_type`, `entity_id`, `details` JSON, `created_at`. Entity references are polymorphic application links. |

### Monitoring and saved analysis: 4 tables

| Table | Keys and SQL references | Other stored data |
| --- | --- | --- |
| `monitoring_jobs` | PK `id`; FK `tenant_id` to `tenants.id`; nullable composite FK `(tenant_id, run_id)` to `runs`; UQ `(tenant_id, basis_hash)`. | `state`, `attempts`, frozen-input `payload`, `created_at`, `updated_at`, `available_at`, `lease_expires_at`, `lease_token`, `last_error`, nullable `analysis_id`. **`analysis_id` has no SQL FK.** |
| `analysis_reports` | PK `id`; composite FK `(tenant_id, run_id)` to `runs`; UQ `(tenant_id, run_id, basis_hash)`. | `payload`, `created_at`. A changed input basis creates another report rather than replacing an earlier result. |
| `monitoring_state` | PK/FK `tenant_id` to `tenants.id`. | Nullable `last_check`, `last_successful_check`, `last_scheduled_at`, `last_effective_date`, `last_digest`. |
| `inapp_notices` | PK `id`; FK `tenant_id` to `tenants.id`; UQ `(tenant_id, dedupe_key)`. | `payload`, `created_at`, nullable `read_at`. Run/report links exist only inside JSON. Read status is shared within the workspace, not per user. |

Job state is constrained to `queued`, `running`, `succeeded`, `failed`, or
`cancelled`. Attempts and leases support retry and worker recovery. An explicit
owner reset can restart an exhausted retry cycle with a rationale; prior retry
history remains in the job payload.

Named indexes supplement primary and unique keys:

| Index | Indexed columns |
| --- | --- |
| `sources_tenant` | `sources(tenant_id)` |
| `runs_tenant` | `runs(tenant_id)` |
| `findings_run` | `findings(tenant_id, run_id)` |
| `audit_tenant` | `audit(tenant_id, id)` |
| `monitoring_job_queue` | `monitoring_jobs(state, available_at)` |
| `analysis_reports_tenant` | `analysis_reports(tenant_id, created_at)` |
| `analysis_reports_basis` | `analysis_reports(tenant_id, basis_hash, created_at)` |

No cascading deletes are declared. Foreign keys use SQLite's default delete
behavior; the schema does not implement automatic workspace cleanup.

## What the JSON contains

| Location | Meaningful fields |
| --- | --- |
| `sources.payload` | `kind` (`instrument`/`external`), title, jurisdiction, version, verbatim `text`, authority type, legal status, URL, effective dates, adoption reference, `source_key`, `replaces_source_id`, `reference_keys`, topics, reference scope. `effective_to` is exclusive. |
| `runs.payload` | Title, `as_of`, selected `source_ids`, coverage note, pinned `profile`/`profile_hash`, analysis method, coverage status, code version; worker-created runs also record the trigger. |
| `findings.payload` | Run ID, summary, category, severity, rationale, current status, analysis method, exact evidence quotes and locations, applicability determination/rationale/reviewer/time; latest decision and assignment when present. |
| `workspace_settings.payload` | `advanced_analysis`, nine feature switches, `horizon_days`; monitoring opt-in, source/context/effective-date controls, check interval, digest interval, IANA timezone. |
| `workspace_context.payload` | Topics, programs, funding conditions; assets with ID, name, program, owner, and `source_keys`. |
| `monitoring_jobs.payload` | Trigger, authorized actor, frozen snapshot of sources/history, profile/hash, settings, context, findings, workflow audit, analysis date, snapshot time; retry history/reset attribution when applicable. |
| `analysis_reports.payload` | Feature results and evidence, `basis_hash`, engine version, `settings_snapshot`, `context_snapshot`, `findings_snapshot`, `audit_snapshot`, `profile_snapshot`/hash, selected source IDs, embedded `evidence_sources`, snapshot time, capabilities, coverage status, policy-approval flag. |
| `inapp_notices.payload` | Notice kind, title, severity, message, optional run/report IDs and workload/freshness information. |
| `audit.details` | Event-specific data, including decision rationale, applicability changes, assignments, configuration changes, analysis references, and monitoring outcomes. |

There are no separate decisions, assignments, profiles, inventory assets,
citations, or feature-result tables. Finding decisions and assignments update the
current finding JSON and append audit events. Changing applicability clears the
current decision and returns the finding to pending; the audit retains the prior
decision and the reason its premise changed.

`content_hash` is SHA-256 over the canonical source input JSON, including metadata
and text. It is not only a text checksum. `basis_hash` includes tenant, selected
source IDs/hashes, profile hash, settings, context, findings/workflow audit,
analysis date, and engine version. Jobs and reports use these hashes to avoid
duplicating work for the same basis within their unique-key scope.

## Lifecycle and feature mapping

| User action or service behavior | Writes | Reads / preserved context |
| --- | --- | --- |
| Switch Simple / Advanced view | `preferences` | Membership; affects that user's display. |
| Set analysis and automation controls | `workspace_settings`, `audit`; eligible pending jobs are cancelled and a new check may be queued. | Previous settings; analysis switches are independent of display mode. |
| Maintain topics and inventory | `workspace_context`, `audit`; pending jobs may be cancelled and a new check queued. | Current context and declared source-key mappings. |
| Add a source or source version | New `sources`, `audit`; optional `monitoring_jobs`. | Existing same-tenant hash or declared predecessor. Older rows remain. |
| Start a review | New `runs`, `run_sources`, `audit`. | Selected same-tenant source snapshots and current profile. |
| Record evidence and review a finding | New/current `findings`, `audit`; optional `monitoring_jobs`. | Pinned run sources; exact quotes; owner applicability/decision checks. |
| Run analysis or process a queued check | New `analysis_reports`, `audit`; worker may create `runs`/`run_sources`, update `monitoring_jobs`/`monitoring_state`, add `inapp_notices`. | Frozen analysis basis, local rules, source evidence. |
| Scheduled checks / digests | `monitoring_state`, queued jobs, `inapp_notices`, `audit` as applicable. | Workspace automation settings and local workload; no external delivery. |
| Mark a notice read | `inapp_notices.read_at` | Workspace-scoped notice. |
| Export a review | No saved export table. | Run, pinned profile/sources, current findings, related audit, saved analyses in one read transaction. |

Source snapshots, run inputs, and saved analysis reports are not updated through
the application. Findings, preferences, workspace configuration, job state,
monitoring timestamps, and notice read state are mutable. Audit events are
appended. These are application lifecycle guarantees, not database immutability
triggers or a tamper-proof audit system. A run pins inputs; its linked findings
can continue through review. A report freezes the finding and workflow snapshots
used for that analysis.

Source/configuration/workflow mutations and their triggered job enqueue use the
same write transaction when passed through the application. Scheduled monitoring
is opt-in; source and context/workflow triggers have their own controls. All of
this operates on locally supplied records. There is no external policy database,
LLM connection, email delivery, automatic policy approval, or amendment drafting
in the current storage workflow.

## Local storage and production implications

- The CLI and application default to `.compass/development.sqlite3`, relative to
  the process working directory. `python -m compass --db PATH` selects another
  file. SQLite WAL sidecar files may accompany it while active.
- Store initialization selects WAL mode. Each `Store.connect()` enables foreign
  keys, sets a 10-second connection timeout, and opens an explicit transaction.
  Reads use `BEGIN`; writes use `BEGIN IMMEDIATE`. Commit or rollback closes the
  connection. The read snapshot keeps exports coherent during concurrent edits.
- Schema creation uses `CREATE TABLE/INDEX IF NOT EXISTS`; there is no versioned
  migration framework. Adding columns or changing constraints requires an
  explicit migration strategy, not just editing the creation SQL.
- A shared production service still needs production identity/provisioning,
  database-enforced tenant isolation, migrations, and operating procedures for
  backups, retention, restore, and workers. See [the roadmap](ROADMAP.md).

Keep operational database access tenant-scoped. A database connection can read
across tenants; an application's session membership does not constrain direct
SQL access. Use the API for ordinary review work and exports.
