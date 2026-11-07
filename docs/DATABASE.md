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
no `jurisdictions` table. Application validation uses the fixed 50-state/DC and
`US-FED` authority identifiers. Internal instruments must match the workspace;
external sources may retain a real foreign jurisdiction as labelled context.
Unknown `US-` identifiers are rejected rather than treated as another state.
Public reference metadata does not make a tenant's
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
| `memberships` | PK `(tenant_id, user_id)`; separate FKs to `tenants.id` and `users.id`. | `role`, constrained to `owner` or `reviewer`; `can_determine_applicability`, a boolean flag defaulting off. |
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
| `findings` | PK `id`; UQ `(tenant_id, id)`; composite FK `(tenant_id, run_id)` to `runs`; nullable composite FKs `(tenant_id, instrument_source_id)` and `(tenant_id, external_source_id)` to `sources`. | `payload`, `created_at`; the legacy paired IDs remain for external-gap compatibility. Evidence of other structures is validated and stored as a JSON list. |
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
| `sources.payload` | `kind` (`instrument`/`external`), title, jurisdiction, version, verbatim `text`, authority type, legal status, URL, effective dates, adoption reference, `source_key`, `replaces_source_id`, `reference_keys`, topics, reference scope; `verification`, `text_provenance`, `original_sha256`, `page_spans`, `page_count`, `failed_pages`. `effective_to` is exclusive. |
| `runs.payload` | Title, `as_of`, selected `source_ids`, coverage note, pinned `profile`/`profile_hash`, analysis method, coverage status, code version; worker-created runs also record the trigger. |
| `findings.payload` | Run ID, summary, category, severity, rationale, current status, analysis method, `finding_type`, exact `evidence` list, `search_source_ids`, `search_description`, `program_or_contract`, optional `concentrated_harm`/`irreversible`; applicability determination, rationale, `authority_relied_on`, reviewer/time and `scope_complete`; latest decision and assignment when present. Imported suggestions also retain their original IDs, method-run provenance and unresolved `evidence_gaps`. |
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

The downloadable evidence wrapper now uses `schema_version: 2`: findings may
have zero, two or more evidence items and an explicit `finding_type`. Clients
must not assume every finding has exactly one internal/external pair. Exporting
a historical run uses this current wrapper without rewriting its saved source,
run or analysis payloads and hashes.

### Verification, evidence structures and provenance

Source type and verification are separate dimensions. `verification.status` is
`unverified`, `verified` or `disputed`; the verification record also carries
`primary_source_location`, and server-attributed `verified_by`, `verified_by_id`
and `verified_at` for
an actual verification action. Clients cannot supply a different person's name
or an invented verification time. Source type is retained as supplied; a foreign
regulation is not silently converted into US guidance.

An owner can grant or revoke `can_determine_applicability` for an existing
same-workspace member, including the owner, through
`PATCH /api/memberships/{user_id}`. The grant is audited and starts off by default.
It does not create a new role or establish that a person is legally qualified.
Only a flagged member may verify a source, label it in force, or make a binding
or conditional applicability determination. A policy owner still records acceptance
or rejection. Each agency appoints its reviewers and decides whether one person
may combine these responsibilities.

`PATCH /api/sources/{source_id}/review` receives a verification object, reviewed
legal status and a rationale. It creates a **new source revision** with a new hash
and predecessor link, rather than editing the old source payload. Earlier reviews
continue to reference the earlier source. Use a new review pinned to the verified
revision before relying on it for a binding determination. Status changes and the
relationship between old and new revisions are recorded in the audit trail.
Repeating an identical unverified/disputed review of the same predecessor returns
the existing derived revision. Invalid legacy metadata is flagged with 422;
the original is preserved rather than silently relabelled or changed.

| `finding_type` | Required evidence | Acceptance boundary |
|---|---|---|
| `external_gap` | One or more internal and external passages; each quotation is an exact excerpt from a source pinned to the run | Resolve applicability against the actual external support, not a score |
| `internal_conflict` | Two or more distinct instrument passages; changing a location label cannot duplicate a quotation into another passage | Review the conflict and governing authority within the declared scope |
| `absence` | No quotation; record the searched source IDs and a useful search description | A flagged reviewer must confirm completeness; all sources in the run's declared pinned corpus must have been searched before confirmation |

Finding types describe evidence structure, while `category` describes the issue.
Every supplied evidence/search source is checked for tenant scope and membership
in the run's pinned inputs. Applicability requires a rationale of at least 30
characters and an `authority_relied_on` record. Binding support must be a verified,
in-force source effective on the review date. `funding_condition` and `agreement`
sources also need the finding's actual `program_or_contract` attachment.
`court_or_ag` material is flagged for human review and cannot automatically
establish a binding or conditional determination. Foreign context alone cannot
establish a US duty. Imported records with unresolved evidence gaps remain pending
suggestions and cannot be accepted.
Fresh acceptance also requires a current applicability record with identified
authority and reviewer. Binding/conditional reviews retain the server-recorded
permission at the time of review; revoking permission later does not erase that
historical action. Older owner-only determinations are preserved, but cannot be
newly accepted without the current review controls. Binding acceptance checks
the verified source revision pinned to that run again.

`text_provenance` distinguishes `original`, `extracted` and `transcribed` text.
`original_sha256` identifies the exact source-file bytes, separately from the
canonical JSON snapshot hash. PDF `page_spans` contain one-based page numbers and
zero-based, half-open character offsets into the saved text. `page_count` includes
unextractable pages, and `failed_pages` explicitly records their numbers/reasons.
Editing extracted text clears its page mapping and marks it transcribed while
retaining known extraction limitations. A hash does not mean the original binary
is retained by the app, nor does successful extraction establish legal accuracy.

The optional concentration-of-harm and irreversibility flags are exported with
the finding. They support the manual priority rubric; they do not multiply scores
or change authority, certainty or source verification.

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
| Review a source's verification or legal status | New revised `sources`, `audit`; optional `monitoring_jobs`. | Exact predecessor snapshot and delegated review permission; historical reviews remain unchanged. |
| Grant or revoke applicability permission | `memberships`, `audit`. | Owner authority and existing same-tenant membership. |
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
- Schema creation uses `CREATE TABLE/INDEX IF NOT EXISTS`. Milestone 2 includes
  an explicit local migration: add the membership flag with its default off and
  rebuild the existing findings table with nullable legacy evidence columns in
  a transaction, retaining existing rows and payload bytes. It adds no table or
  migration framework. Reopening an already migrated database is repeatable;
  future constraint changes still need an explicit strategy and tests.
- A shared production service still needs production identity/provisioning,
  database-enforced tenant isolation, migrations, and operating procedures for
  backups, retention, restore, and workers. See [the roadmap](ROADMAP.md).

Keep operational database access tenant-scoped. A database connection can read
across tenants; an application's session membership does not constrain direct
SQL access. Use the API for ordinary review work and exports.
