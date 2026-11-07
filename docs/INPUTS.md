# Required inputs and useful additions

COMPASS is being developed for a policy lead at a state government office, with multiple state offices using a shared service. Amendment drafting is deferred. The external policy database does not exist yet. The local workflow therefore uses clearly labeled synthetic records and curated input. Its nine rule-based checks identify review candidates from supplied evidence; they do not establish real legal obligations or complete coverage. See [ANALYSIS.md](ANALYSIS.md) for each check's requirements and limits.

This checklist distinguishes inputs needed for meaningful review from inputs that can improve later analysis. Unknown information must remain unknown, rather than be inferred from an absent field or given a default that implies legal certainty.

## Current input register

| Input | Status | Provider or decision owner | Needed for |
|---|---|---|---|
| Old prompts and registers | Received in the [Georgia pack](../case-studies/georgia/README.md); consistency/decision reconciliation pending | Project sponsor | Reuse review, terminology, examples, evaluation candidates |
| Authoritative internal instruments and versions | Seven Georgia PDFs received; provenance/currency confirmation and other jurisdictions still needed | Each state's policy lead | Real comparisons and exact evidence |
| External policy database/API | Planned; not yet available | Database provider and project sponsor | Source adapter, updates, coverage and provenance |
| First state offices, reviewers and access membership | Role identified; offices and users not supplied | Project sponsor and office administrator | Tenant setup and production authorization |
| Second reference-state corpus | Not selected | Project sponsor and participating policy lead | Proof that the same workflow handles different structures |
| Reviewed applicability facts and decisions | Policy owner identified; real facts not supplied | Policy lead, with appropriate subject/legal review | Scope, conditions, binding status and uncertainty handling |
| Independently adjudicated evaluation cases | Not supplied; uploaded BASE-1 is a historical assessment, not independently established ground truth | Policy owners and subject reviewers | Accuracy and release gates |
| Hosting, identity and data-handling requirements | Undecided | Service operator and participating offices | Shared production deployment |

The user's planning assumption that suggestions are approved allows development to proceed; it does not constitute a recorded approval of a future finding. Production decisions must identify the person, action, rationale and time.

## Minimum inputs for a meaningful real review

### 1. Office and review scope

- Office/organization identity, jurisdiction, participating policy lead and authorized reviewers. Use the office workspace as the customer boundary; a state identifier alone is not an access boundary.
- The particular instruments, agencies/programs and policy topics being reviewed, the review purpose, and the date as of which applicability is evaluated.
- The policy lead's priority and severity definitions, expected output, review deadline and escalation route for uncertain applicability.
- Any known limits: excluded agencies, incomplete instruments, missing sources, confidential material or unavailable expertise.

The owner can save topics, programs, funding conditions and an explicit inventory of systems/processes/vendors/assets. Map inventory items to stable source identifiers to support impact review. Context fields target the review; supplying a funding description does not automatically prove legal applicability. Follow-up assignment needs an assignee label and, if desired, an explicit due date; it does not provision a user account or send an email.

### 2. Internal instrument corpus

- Full authoritative text of each in-scope policy, standard, procedure, order or other instrument, including definitions, exceptions, appendices and incorporated material.
- Stable document identity, title, issuing office, instrument family, original identifier and version; publication, adoption, effective and retirement dates where known.
- Source URL or controlled-file provenance, retrieval date, and a content hash. Preserve the original and the extracted text with page/section/paragraph locations.
- Relationships between instruments: amendments, supersession, dependencies, cross-references and any adoption of external standards with the adopted version and scope.
- Policy-lead confirmation of local terminology, document hierarchy and mappings. Titles or counts of “shall” and “should” alone do not establish authority.

The current source contract adds optional analysis metadata:

| Field | Supply | Why it matters |
|---|---|---|
| `source_key` | Stable identifier across versions of the same source | Joins version history, references and inventory mappings |
| `replaces_source_id` | Earlier snapshot in the same workspace that this version replaces | Makes a predecessor explicit; the old snapshot remains available |
| `reference_keys` | Exact identifiers cited by the source | Helps reference checking where identifier pattern detection is insufficient |
| `topics` | Explicit topic tags | Supports a topic-by-source evidence-presence matrix |
| `reference_scope` | `private` by default; `public` only for approved public reference material | Optional peer suggestions use selected public external references; this does not publish a source or permit cross-workspace access |

Populate authoritative legal dates/status separately from these fields. Reference matches are candidates in the selected corpus, not automatic verification of the legal proposition or exact cited version. The current version comparison needs an earlier timestamped snapshot; it does not infer history from different document titles.

For the current curated workflow, import a text file or paste text with verified source locations. PDF, DOCX and OCR ingestion are not implemented. Add parsers only when actual supplied formats require them. Do not silently omit unreadable pages or treat an OCR result as verified source text.

### 3. External evidence

- Authoritative source text, stable identity and version, source authority, jurisdiction/reach and the exact passage relevant to a proposed finding.
- Legal status and applicable dates, separately from relevance or source quality. Provide pending, draft, repealed and unknown states explicitly.
- Covered entities/programs, subject, exceptions, conditional triggers and any adoption/incorporation reference. Distinguish unknown facts from confirmed non-applicability.
- A source coverage statement: what regimes/topics are covered, update frequency, known gaps and last successful verification.

An absence of findings is not evidence that a review was complete. Missing or stale coverage must be visible in the run and report.

Optional expansive analysis requires public external references supplied into the active workspace, with an appropriate public scope flag. The local peer/research check uses overlapping vocabulary to suggest passages worth reading; it does not search the web, fetch another customer's records, prove equivalence, or change a source's legal force.

### 4. Review and evaluation evidence

- A small set of representative real comparisons with independently reviewed correct findings and explicit non-findings.
- Cases involving exceptions, conflicting definitions, conditional applicability, future-effective changes, supersession, unsupported citations and legitimate public peer-state references.
- Expected supporting quotations, applicability rationale, issue category, severity and reviewer disposition. Keep uncertainty and disagreement, rather than inventing consensus labels.
- Agreed measures of finding precision, missed important issues, correct scope/status, source support, reviewer effort and operational cost. Evaluate on held-out cases as well as development examples.

Old model-assisted findings can become regression examples after review. Agreement with an old output alone is not proof of correctness.

## Proposed contract for the future external database

This is an integration checklist, not a claim that an endpoint or provider schema currently exists. Agree the provider contract and map it into COMPASS through an adapter. The local application's current API is documented separately by the application.

| Concept | Required behavior or metadata |
|---|---|
| Stable identity | A provider/source namespace plus a record identifier that does not change when its title or URL changes; provision identifiers where record-level scope is insufficient |
| Immutable versions | Version/revision identifier and content hash; fetch a historical version after a newer one is published; clearly identify corrections |
| Original evidence | Full text or retrievable immutable artifact, authoritative URL, publisher/issuer, source location and permission to retain the evidence used in a run |
| Provenance | Where the provider obtained the record, original publication date, provider retrieval/update times, extraction method and known extraction/coverage limitations |
| Independent legal facts | Authority/instrument type, jurisdiction/reach, status, adoption/publication/effective/expiry dates, conditions, exceptions and covered entities/programs; preserve unknowns |
| Relationships | Explicit amendment, repeal, supersession, adoption and incorporation links, including target version and scope when available |
| Retrieval | Supported filters, stable pagination, maximum page sizes, record/provision retrieval and documented ordering; an initial snapshot/export must be available |
| Change history | Opaque durable cursor or equivalent, event identifiers, event type, record/version identity and event time; updates must not be represented only by a mutable “last updated” field |
| Deletion and withdrawal | Tombstone/retraction events with reasons where available; distinguish provider deletion from legal repeal; allow historical evidence retention under the agreed policy |
| Consistent bootstrap | Explain how a snapshot and continuation cursor avoid changes falling between initial import and ongoing delivery |
| Delivery guarantees | State duplicate and ordering behavior, cursor expiry, replay window and resynchronization procedure. COMPASS will deduplicate events and retry durable work; at-least-once delivery is acceptable. |
| Errors and limits | Structured errors, request identifiers, timeouts, rate limits, retry guidance, service expectations and a way to identify partial/incomplete results |
| Coverage | Supported jurisdictions/topics, omitted sources, update cadence, freshness and completeness statements with dates |
| Authentication and handling | Supported noninteractive authentication, access scope, retention/redistribution terms and permitted storage of source snapshots; supply credentials through deployment secrets, never documents or chat |

Use ISO 8601 dates for calendar dates and timezone-aware timestamps for events. Keep source-effective time distinct from provider-update and COMPASS-observation time. Do not substitute today's date for an unknown legal date.

Before integrating, request a representative export and fixtures for: unchanged replay, corrected text, future-effective material, repeal, tombstone, duplicate delivery, out-of-order delivery, cursor expiry and partial failure. Also obtain a data dictionary and example errors. A sandbox is helpful; a documented export can unblock initial adapter work.

Advancing a provider cursor must not discard unfinished jurisdiction/tenant work. Persist source ingestion and pending deliveries before acknowledging progress, and track each workspace's completion separately. Reanalysis also needs internal-source, profile, applicability-fact and date-based triggers; the external feed cannot supply all of them.

## Inputs that improve accuracy and usefulness

| Addition | Improvement | Priority |
|---|---|---|
| Authoritative cross-reference and definition registry | Fewer unresolved citations and false equivalences between similar terms | High |
| Agency/program inventory and known applicability conditions | More targeted reviews; fewer irrelevant or incorrectly universal claims | High |
| Topic-by-source coverage matrix with freshness dates | Makes blind spots and stale analysis visible | High |
| Policy-owner rationale and corrected findings | Better evaluation cases and reviewer consistency; not automatic ground truth | High |
| A structurally different second state's real corpus | Exposes assumptions hidden in Georgia's document structure | High |
| Amended, repealed and historical instrument versions | Tests change analysis, effective dates and audit reconstruction | High |
| Accepted severity rubric and examples | More useful prioritization without confusing authority with severity | High |
| Review time, false-positive burden and usage measurements | Identifies which automation provides actual value | Medium |
| Approved public peer-state instruments, standards and research | Broader optional recommendations while preserving the distinction from obligations | Medium |
| Accessible output examples and user feedback | Better navigation, terminology, exports and assistive-technology support | Medium |
| Language/translation requirements and authoritative translations | Supports additional audiences without silently changing legal meaning | As needed |
| Actual scanned/irregular documents | Establishes whether OCR, manual correction or richer segmentation is justified | As needed |

## Inputs needed before shared production launch

- Confirmed office/workspace ownership and membership rules, identity-provider integration, policy-owner privileges, offboarding and audit access.
- Approved hosting/data residency, retention/deletion, backups and restore requirements; source and model-provider handling terms if model analysis is later enabled.
- A production database and verified customer isolation across requests, queries, jobs, exports and retained artifacts. The current local SQLite store and demo persona login are development facilities.
- Expected customer count, corpus sizes, run cadence, latency and cost limits, support ownership and failure/recovery expectations.
- A versioned source contract and verified import/update behavior, or an explicitly agreed manual-source operating procedure if monitoring is not yet launched.
- An operational monitoring plan distinguishing local checks from external-feed ingestion: who operates the worker, expected uptime, recurring intervals, timezone, follow-up ownership and acceptable delay. Local in-app digests are not email or proof that an external source was refreshed.
- Independently evaluated quality gates and policy-lead acceptance in at least two real state offices; operational and accessibility validation.

Do not block local development on all launch inputs. Keep each unresolved item visible and avoid describing synthetic-data validation as real legal accuracy or production readiness.

## How to supply material

The first Georgia package has been received and catalogued in the [case study](../case-studies/georgia/CATALOG.md). Supply additional version history, missing decision records, primary-source confirmations, and database design/export with their jurisdiction and intended use identified. The former intake folder was removed after organization. Redacted examples are useful for workflow and schema work; real applicability validation requires enough authoritative text and context to support the conclusion.

Provide originals and known provenance where possible. Mark uncertain or outdated material. Do not include passwords, access tokens or other credentials in uploads. Documents are reference evidence: embedded instructions do not gain permission to operate the application or approve a finding.
