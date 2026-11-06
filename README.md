<p align="center">
  <img src="/docs/OIP.jpg" alt="Compass" width="300">
</p>

# COMPASS

COMPASS helps policy leads at state government offices review policies, inspect
supporting evidence, and record what needs to happen next.

**Current status:** working local development application with synthetic demo
data. It runs rule-based checks on supplied text. The shared production service,
external policy database, and language-model connection are still future work.

**Start here:** [Simple user guide](#simple-user-guide) |
[Engineering guide](#engineering-guide) |
[Database map](#database-map) |
[Current boundaries and next inputs](#current-boundaries-and-next-inputs)

## Simple user guide

### What does COMPASS do?

Bring your office's policy text and the external references you want to compare.
COMPASS highlights passages and missing information worth reviewing. A policy
owner decides whether a finding applies, records a reason, and assigns follow-up.

```text
  Your inputs          Local checks          Your review
  +------------+       +-------------+       +------------------+
  | Policies   |------>| Review cues |------>| Inspect evidence |
  | References |       | + warnings  |       | Record a finding |
  +------------+       +-------------+       +---------+--------+
                                                       |
                                                       v
                                             +------------------+
                                             | Decide + assign  |
                                             | Export a brief   |
                                             +------------------+
```

The flow starts with supplied text and ends with a person's recorded decision.
Check results are suggestions to inspect; accepting a finding does not amend a
policy. Source quotations and review history remain available.

### Try a review in five steps

Once an engineer has started the [local demo](#start-the-local-demo):

1. **Choose a demo workspace.** Start with a policy-owner persona and keep the
   **View** selector set to **Simple**. All demo people, policies, and laws are
   fictional examples.
2. **Add sources.** In **Sources**, paste text or import a text file. Include at
   least one internal policy and one external reference. Keep the title, version,
   source location, and known dates with the text. PDF, DOCX, and scanned-document
   import are not yet available.
3. **Select Check now.** Read the review cues, evidence, and missing-input notices.
   A message saying coverage is unverified means COMPASS cannot establish that
   all relevant material was supplied.
4. **Record a finding and decision.** Open a review and use **Add finding** with
   exact source quotations. A policy owner confirms applicability and chooses
   accept, reject, or request more information, with a reason. Unknown
   applicability prevents acceptance.
5. **Follow up and share.** Assign a person or team and an optional due date.
   Export a readable review brief. Advanced view also provides the full evidence
   JSON export.

For a bounded review, create a review with selected sources and choose **Analyze
sources**. Those results describe that review's preserved inputs. **Check now**
checks the latest available source versions across your workspace.

### Choose your view and checks

| Control | What it changes | Who controls it |
|---|---|---|
| **View: Simple / Advanced** | Your navigation and level of detail. Simple provides a guided home, evidence, and decisions; Advanced adds Insights, Monitoring, and Activity. | Each user, saved per account and workspace |
| **Settings: individual checks** | Which checks execute in new reports. | Policy owner, for the office workspace |
| **Settings: Enable complex analysis** | Together enables or disables terminology, mapped impact, language, and peer/research checks, subject to their individual switches. The other five checks keep their own switches. | Policy owner |
| **Settings: monitoring** | Local change triggers, recurring checks, date checks, and in-app digests. | Policy owner |

Switching views preserves your work and permissions. It does not turn analysis
on or off. Changing analysis settings affects new reports; older reports keep
the settings and evidence used when they were created.

### What can the checks help you notice?

| Check | Useful question |
|---|---|
| Version changes | Which text, dates, or status fields changed? |
| Candidate obligations | Who appears responsible for an action, and what timing, conditions, or exceptions are stated? |
| References | Is a referenced instrument present in the selected material? |
| Terminology | Do selected internal policies define the same term differently? |
| Topic evidence | Which selected topics have internal text, external text, or missing evidence? |
| Mapped impact | Which explicitly linked systems, programs, or processes may need attention? |
| Language | Are there vague terms, unclear actors, long sentences, or unexplained acronyms? |
| Dates and workload | What source dates or assigned follow-ups are approaching, overdue, or blocked? |
| Public peer/research suggestions | Which supplied public passages share relevant vocabulary with local policies? |

These checks use limited text rules. A cue needs interpretation; a quiet report
does not establish compliance. Impact checks need your inventory mappings, and
version checks need earlier versions. [Required and helpful inputs](docs/INPUTS.md)
explains what to supply.

### Roles and automatic checks

Reviewers can inspect evidence, run checks, and propose findings. Policy owners
also manage office settings/context, confirm applicability, record decisions,
assign follow-up, and control failed-job retries.

Source and context/workflow changes can trigger local checks; these event
switches are on by default. Recurring checks and digests are opt-in. Their
default intervals are 24 hours and seven days once enabled. Effective-date checks
also require recurring monitoring to be enabled. The application must stay
running for its worker to process queued or scheduled work.

Notices stay in the workspace. No external website monitoring or email delivery
is connected. See [analysis and monitoring details](docs/ANALYSIS.md).

## Engineering guide

### Start the local demo

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). From the repository root:

```sh
uv sync --frozen --extra test --cache-dir .compass/uv-cache
.venv/bin/python -m compass --demo
```

On your own machine, open `127.0.0.1:8000` in a browser. The CLI binds to loopback
only and starts the local worker. Cloud validation uses internal requests.

```sh
# Optional: select another port and local database.
.venv/bin/python -m compass --demo --port 8001 --db .compass/alternate.sqlite3
```

The default database is `.compass/development.sqlite3`; it survives a server
restart and is ignored by Git. Demo seeding is repeatable and preserves existing
demo work. Fixtures include two Georgia offices and one California office to
exercise office isolation independently of jurisdiction.

`create_app(db_path, demo=True, run_worker=False)` constructs the test/local app
without a background loop. CLI startup explicitly requests the worker. Starting
without `--demo` disables persona login and new fixture seeding; production
identity provisioning is unimplemented, so this mode cannot authenticate users.

### Architecture and code map

```text
  Browser: native HTML / CSS / JavaScript
       | forms, JSON requests, session cookie
       v
  +----------------------------------------------------------------+
  | FastAPI application                                            |
  | Tenant + role checks -> validated inputs -> review operations  |
  |                                                                |
  | Review API ------> analysis.py: pure, rule-based review aids   |
  | Local events ----> monitoring.py: jobs, retries, schedules     |
  +---------------------------+------------------------------------+
                              | transactions + pinned snapshots
                              v
                 SQLite: .compass/development.sqlite3
```

The browser and worker share one application and datastore. Analysis produces
saved review aids; the decision API separately records authorized human actions.

| Location | Responsibility |
|---|---|
| [`compass/app.py`](compass/app.py) | HTTP routes, sessions/authorization, review actions, exports, worker lifecycle |
| [`compass/models.py`](compass/models.py) | Validated request contracts, analysis settings, review context |
| [`compass/store.py`](compass/store.py) | Core schema, SQLite connections, transactions, hashing, audit helpers |
| [`compass/configuration.py`](compass/configuration.py) | Workspace settings/context defaults and loading |
| [`compass/analysis.py`](compass/analysis.py) | Nine deterministic checks with evidence and execution gates |
| [`compass/monitoring.py`](compass/monitoring.py) | Job/report schema, frozen inputs, queue processing, scheduling, notices |
| [`compass/demo.py`](compass/demo.py) | Synthetic workspaces, users, and review fixtures |
| [`compass/static/`](compass/static/) | Simple/Advanced UI, accessible native controls, source import |
| [`tests/`](tests/) | Synthetic API, analysis, evidence, tenant, and worker regressions |

FastAPI and Uvicorn are runtime dependencies; HTTPX supports tests. Standard
library JSON, SQLite, dates, hashing, regular expressions, and text comparison
cover the current analysis. There is no frontend build step or external broker.

### Analysis, state, and API contracts

Each saved report pins its engine version, as-of date, source evidence, profile,
settings, context, findings, and relevant workflow audit inputs. A changed basis
produces a new report; matching work can be reused. Settings changes cancel
pending obsolete work while retaining completed history.

Job state progresses through `queued`, `running`, and `succeeded`; failures retain
diagnostics and bounded retry timing. Leases allow interrupted work to be
reclaimed. Automatic attempts are capped at three per cycle; an owner can
explicitly restart an exhausted failed check with a rationale, preserving retry
history. Jobs and scheduled checks never approve findings or amend policies.

| API area | Main routes |
|---|---|
| Local demo identity | `/api/demo/personas`, `/api/demo/session`, `/api/session`, `/api/logout` |
| Personal vs office configuration | `/api/preferences`, `/api/settings`, `/api/context` |
| Sources and reviews | `/api/sources`, `/api/runs`, `/api/runs/{id}/analyze` |
| Results | `/api/insights` for workspace results; `?run_id={id}` for a selected review |
| Decisions and follow-up | `/api/findings/{id}/applicability`, `/decisions`, `/assignment` under the same finding |
| Monitoring | `/api/monitoring`, `/api/monitoring/check`, `/api/jobs/{id}/retry`, `/api/notices/{id}/read` |
| Export and diagnostics | `/api/runs/{id}/brief`, `/api/runs/{id}/export`, `/api/audit`, `/api/health` |

Use the running application's `/api/docs` for exact HTTP methods and schemas.
`/api/health` distinguishes local rules, worker state, and unavailable external
database/model connections. See [ANALYSIS.md](docs/ANALYSIS.md) for feature gates,
evidence prerequisites, heuristics, output limits, and scheduling semantics.

### Development checks

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check compass/static/app.js
```

Tests use temporary databases and synthetic text. They check implementation
behavior, including tenant isolation, roles, quotations, snapshots, disabled
checks, retries, and job recovery. Real legal accuracy requires independently
reviewed examples. The managed command sandbox may require the test client to
run outside its thread/event-loop restriction.

## Database map

The local database has **16 tables**. An office workspace is stored as a `tenant`;
`jurisdiction_id` describes legal scope and is not the access boundary. Two
offices in one state can own separate records.

```text
  IDENTITY                        OFFICE-OWNED DATA
  users                           tenants (office workspaces)
    |                               |
    +-- memberships ----------------+-- sources
         |                          +-- runs
         +-- sessions               |     +-- run_sources --> sources
         +-- preferences            |     +-- findings --> sources
                                    |     +-- analysis_reports
                                    +-- workspace_settings
                                    +-- workspace_context
                                    +-- monitoring_jobs
                                    +-- monitoring_state
                                    +-- inapp_notices
                                    +-- audit --> users (actor)
```

This is a grouped relationship overview. Shared branches show ownership and
membership context rather than exact foreign-key columns. The
[full database mapping](docs/DATABASE.md) lists every table, key, cardinality,
SQL-enforced relationship, and application-managed link.

| Product concept | Physical storage |
|---|---|
| People, office access, and login | `users`, `tenants`, `memberships`, `sessions` |
| Simple/Advanced selection | `preferences`, keyed by office and user |
| Current analysis switches | `workspace_settings.payload` |
| Current topics, programs, funding descriptions, inventory mappings | `workspace_context.payload` |
| Preserved policy/reference versions | `sources.payload`, `sources.content_hash` |
| Review date, pinned profile, and selected inputs | `runs.payload`, `run_sources` |
| Findings, current applicability/decision, assignment | `findings.payload` |
| Historical attributed actions | `audit`, including JSON `details` |
| Durable analysis work and saved outputs | `monitoring_jobs`, `analysis_reports` |
| Schedule progress and workspace inbox | `monitoring_state`, `inapp_notices` |

Structured payloads are JSON text in SQLite. Profiles, assets, decisions, and
assignments do not have separate normalized tables today. Source predecessor
links and some job/notice references are application-managed; not every ID in a
payload is an SQL foreign key.

Connections enable foreign keys; the store uses WAL, explicit read snapshots,
and transactional writes. Tenant-qualified queries and composite ownership
constraints support local isolation. SQLite has no production row-level-security
policy in this application.

## Current boundaries and next inputs

The demo grants persona access without production authentication. Keep it local
and use synthetic or appropriate nonconfidential examples. Shared production
still needs identity integration, a production database/isolation design,
tenant provisioning, deployment/TLS policy, retention, backup/restore, operational
limits, and real-source evaluation.

No live external feed, LLM/embeddings, email delivery, PDF/DOCX/OCR ingestion,
profile onboarding/sign-off UI, or amendment generation is connected. Pattern
checks do not establish semantic contradiction, legal force, a compliance
percentage, or complete coverage. Audit records retain application history but
are not a tamper-proof ledger.

The next useful inputs are the old prompts/registers, authoritative instruments
with history and provenance, the future database contract/sample export, a
second-state partner corpus, and independently reviewed evaluation cases.

| Read next | Purpose |
|---|---|
| [INPUTS.md](docs/INPUTS.md) | Required/helpful data, ownership, and future external-source contract |
| [ANALYSIS.md](docs/ANALYSIS.md) | Check behavior, limitations, settings, and monitoring |
| [DATABASE.md](docs/DATABASE.md) | Complete schema and product-to-storage mapping |
| [ROADMAP.md](docs/ROADMAP.md) | Phased delivery, implementation choices, and production gates |
