# COMPASS

An evidence-linked review workspace for policy leads at state government offices.
The release goal is a shared service for multiple states. The local development
application combines an attributed review workflow with nine rule-based review
aids, personal Simple/Advanced views, and local monitoring. It uses **synthetic
demo data**; amendment drafting is deferred.

## Run locally

Requires Python 3.12 or newer and [uv](https://docs.astral.sh/uv/). From the repository root:

```sh
uv sync --frozen --extra test --cache-dir .compass/uv-cache
.venv/bin/python -m compass --demo
```

The server listens only on `127.0.0.1:8000`. Open that address in your local browser
when running on your own machine. The cloud task uses internal requests for validation.
If dependencies are already installed, `python3 -m compass --demo` is sufficient.
Use `--port` or `--db` to change the local port or database path.

Choose a synthetic policy owner or reviewer. Two Georgia offices and a California
office demonstrate that the workspace/customer boundary is separate from the
jurisdiction. Seeding is repeatable and does not replace existing demo work.

The CLI also starts the local monitoring worker. Keep the application running for
queued and scheduled checks to execute. Calling `create_app()` directly does not
start a worker unless explicitly requested; tests do not start one by default.

Without `--demo`, persona login is disabled and no data/users are seeded. Production
identity provisioning has not been implemented; this mode is deliberately not a
deployable production service.

## Try the workflow

1. Open a demo workspace. Use **Simple** for guided review or **Advanced** to inspect
   the analysis sections and technical metadata. Source evidence remains accessible
   in both views. Your view preference does not enable checks or change anyone's role.
2. Import a text file or paste source text in **Sources**. Imports create immutable
   snapshots; repeating the same payload reuses it. Internal instruments must match
   the office's jurisdiction. External references can describe other jurisdictions.
3. For useful analysis, supply stable source identifiers and predecessor links,
   reference keys, topics, legal dates/status, and appropriate public/private reference
   metadata. See [the input checklist](docs/INPUTS.md).
4. As the owner, use **Settings** to choose checks and enter office topics, programs,
   funding context, and explicit system/process/vendor mappings. Personal view mode
   and workspace analysis controls are separate.
5. Choose **Check now**, or create a review with at least one internal instrument and
   one external reference and analyze its pinned inputs. Read the source excerpts,
   data gaps and warnings. The suggestions are review aids, not approved findings.
6. Add a finding with exact quotations and source locations. As the policy owner,
   determine applicability with a scope/exception rationale and record a separate
   accept/reject/request-information decision. Unknown applicability blocks acceptance.
   Assign follow-up work and an optional due date when needed.
7. Export a plain-language review brief or, in Advanced view, the full JSON evidence
   bundle with profile, source snapshots, findings, decisions, audit events and saved
   analysis reports.
8. Use **Monitoring** in Advanced view to inspect local jobs and notices. Scheduled
   checks and in-app digests are opt-in. Source/context event triggers are controlled
   separately from the recurring schedule.
9. Switch to another office and confirm its records are separate. A reviewer can
   propose findings, but only an owner changes workspace settings/context,
   determines applicability, records decisions or assigns follow-up work.

The demo statutes and policies are invented examples, not real laws. The two
jurisdiction fixtures do not establish real-world accuracy or second-state validation.

## What works now

- Cookie-based local demo sessions with server-derived workspace membership/roles.
- Explicit tenant scoping, composite database ownership constraints, and transactional
  writes. Source text is preserved verbatim and hashed with its metadata.
- Pinned source/profile versions, exact-quotation checks, and inspectable exports.
- Nine deterministic analysis sections: version differences, candidate obligations,
  references, definitions/terminology, topic evidence presence, mapped impact,
  advisory language flags, dates/workload, and optional public peer/research passage
  suggestions. No model or external database is contacted.
- Personal Simple/Advanced views; owner-controlled individual analysis switches and
  a separate complex-analysis control for terminology, impact, language and peer
  research. Turning it off leaves the five core checks subject to their own switches.
- Saved report settings/context, input hashes, source evidence and rule-engine version.
  Changing current settings does not erase previous reports.
- Local source/context/date monitoring, durable database jobs, opt-in recurring
  checks and in-app digests. These operate on supplied workspace snapshots, not a
  remote source feed. No email is sent.
- Finding assignment with an optional owner-entered due date, and a plain-text brief.
- Owner-reviewed applicability, independently recorded issue severity, and no numeric
  weight that can create or remove legal force.
- Conservative binding guards: eligible source type, in-force status, known effective
  date, and an as-of date within its effective period. `effective_to` is exclusive.
  Adopted standards additionally need an adoption reference. These checks do not
  establish actual legal applicability; the owner must confirm scope and exceptions.
- Decision attribution and history. Changing applicability invalidates the current
  decision and preserves the earlier action in the audit trail.
- Native, responsive forms and navigation with labels, keyboard focus, and status/error
  announcements. Full accessibility conformance has not been certified.

## Development checks

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check compass/static/app.js
```

Tests use temporary databases and synthetic text. Relevant behaviors include tenant
isolation, roles, source pinning, quotation support, date/authority guards, decisions,
analysis heuristics and local job behavior. Passing these checks does not measure
real-world legal-analysis accuracy; use independently reviewed cases for that.

In the managed execution sandbox, the test client's thread/event-loop wakeup may
require running the command outside that sandbox. This is a runner restriction,
not a requirement to disable application security.

API documentation is served at `/api/docs`; `/api/health` reports the
demo/unconfigured mode, local rule engine, background-worker state, and unavailable
external database/language-model connections.
No credentials, model accounts, or external services are needed for this milestone.

## Structure and decisions

`compass/app.py` implements one FastAPI application; `models.py` contains validated
request contracts; `store.py` uses Python's SQLite facilities; `analysis.py` implements
pure standard-library rules; `configuration.py` loads workspace controls/context;
`monitoring.py` manages local checks and jobs; `demo.py` holds synthetic fixtures;
`static/` contains native HTML, CSS and JavaScript. There is no frontend build,
document-parser stack, external broker, vector database, or model framework.

The repository was empty. Existing environment FastAPI/Uvicorn tools and standard
library dates, hashing, transactions, and JSON cover this milestone. Additional
dependencies or services should follow the five checks in [the roadmap](docs/ROADMAP.md).

## Required inputs and next work

[INPUTS.md](docs/INPUTS.md) records required and helpful data, owners/status, and the
proposed contract for the future external database. Highest-value next inputs are:

- The old prompts and registers, for review as reference material.
- Authoritative instruments with versions, full definitions/exceptions, and provenance.
- A database design/sample export covering source text, history, legal dates/status,
  relationships, coverage, and consistent snapshot/change delivery.
- A second-state partner/corpus and independently reviewed evaluation cases.

[ROADMAP.md](docs/ROADMAP.md) defines the phased delivery and production gates.
[ANALYSIS.md](docs/ANALYSIS.md) explains each check's evidence requirements, controls,
monitoring behavior, and limits.

This is **not ready for public deployment**. The local demo persona endpoint grants
access without real authentication. Do not put real confidential inputs into the demo
or expose it publicly. Before shared production, integrate an identity provider,
production database/isolation controls, tenant provisioning, TLS/deployment policy,
retention, backup/restore, operational limits, and evaluated real-source ingestion.
SQLite's local ownership checks are not a substitute for production database RLS.

There is no live external database/feed, PDF/DOCX/OCR importer, LLM/embedding analysis,
email connection, policy onboarding/sign-off UI, or amendment generation. Local rules
do not establish semantic contradiction, legal applicability, compliance percentages,
or complete coverage. Owner-authored findings still require evidence and review;
turning analysis off does not bypass approval controls. Exact text matching does not
verify a claimed legal conclusion. Application-level audit records support history
inspection; they are not a tamper-proof audit ledger.
