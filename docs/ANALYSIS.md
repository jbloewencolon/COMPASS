# Local analysis and monitoring

COMPASS currently uses deterministic Python standard-library rules over the source snapshots and review records supplied to the active office workspace. It does not connect a language model, embeddings, the future external database, an email service, or the web. Text-file import and paste are supported; PDF, DOCX and OCR extraction are not implemented.

The result is a set of **review aids** with evidence or an explicit input need. A suggestion is not an approved finding, a legal applicability determination, proof of contradiction, or a compliance score. A policy lead still reviews the source, scope, conditions and exceptions before recording a decision.

## View mode and analysis controls

These controls serve different purposes:

| Control | Who can change it | Effect |
|---|---|---|
| Personal Simple/Advanced view | Any authenticated workspace member | Changes navigation, explanation detail and technical metadata shown to that person; it does not change executed checks, approvals or another user's view |
| Individual analysis switches | Policy owner | Enables/disables each check for new reports |
| Enable complex analysis | Policy owner | Gates terminology, impact, language and peer/research checks in addition to their individual switches; the other five checks remain subject to their own switches |
| Office review context | Policy owner | Supplies topics, programs, funding descriptions and explicit inventory/source mappings used to target new checks |
| Local monitoring controls | Policy owner | Controls event-triggered checks, recurring schedule, date checks, intervals and timezone |

The four complex checks run only when both the workspace complex-analysis control and their own feature switch are on. Peer/research suggestions are off by default. The other check switches are on by default. A user's Advanced view cannot override a disabled workspace feature, and Simple view does not disable the engine.

Simple view keeps source evidence accessible through progressive disclosure and provides a plain-language path through review. Advanced view adds analysis sections, settings snapshots, source identifiers/hashes, jobs and activity detail. Turning any analysis off does not remove requirements for authorized applicability review and decisions.

Changes affect new reports. Previously saved reports retain their settings/context and evidence snapshots; they are not rewritten to appear as though disabled checks never ran. If current inputs/settings differ from the latest saved analysis, obtain a new report rather than assume old results describe the new configuration.

## The nine checks

`rules-v3` adds a small abbreviation-aware splitter, prohibition handling,
additional candidate drafting forms, and federal/bill reference patterns.
Recognizing a form does not verify its legal status or meaning. State-specific
patterns come from the pinned profile's `citation_patterns` list; literal
`sentence_abbreviations` entries extend the default abbreviation list. Invalid
profile patterns are skipped with a warning. Georgia's patterns are in its
synthetic demo profile, not a universal state identifier rule.

Foreign source text is retained under its supplied jurisdiction and source type,
with context labels. It is not silently relabelled as US guidance. Such a source
alone cannot establish a binding or conditional US duty in the decision API.
Refer any claimed US contract/program route to its actual supporting authority.
The import form warns against importing restricted material; it does not encrypt
or automatically classify source text.

| Check | Evidence/input needed | What it returns | What it cannot establish |
|---|---|---|---|
| **1. Version changes** (`change_detection`) | Current text, an earlier timestamped snapshot, and either a stable `source_key` or explicit `replaces_source_id` | Exact line-oriented differences and links/excerpts from the old and new snapshots | Whether a change is legally substantive; history when no verified earlier snapshot exists; semantic equivalence of rewritten text |
| **2. Candidate obligations** (`obligations`) | Preserved source text containing recognized modal phrases | Candidate actor, action, modal wording, timing, conditions, negation/prohibition and recognized exceptions, with quotations | Actual legal duty, complete exception scope, correct actor resolution in complex prose, or applicability to the office |
| **3. References** (`citations`) | Selected-source stable keys/title identifiers, explicit `reference_keys`, and/or recognized instrument identifiers in text | Candidate matches, multiple matches/versions, or a reference unresolved in the selected corpus | Invalidity of an authority missing from this corpus, all legal citation formats, exact-version correctness or support for the legal proposition |
| **4. Terminology** (`terminology`) | Selected internal instruments in the active jurisdiction and recognizable definition wording | Different definitions of the same extracted term, with supporting source passages | A semantic contradiction, an instruction to merge definitions, equivalence of similar terms, or differences justified by scope |
| **5. Topic evidence presence** (`coverage`) | Owner-selected topics plus explicit topic tags or matching text mentions | Topic rows showing internal/external evidence presence and related recorded review activity | A compliance percentage, completeness of the legal corpus, sufficient policy treatment or legal compliance |
| **6. Mapped impact** (`impact`) | Owner-supplied inventory items explicitly linked to stable source keys | Mapped systems/programs/vendors/processes that may need review; whether their linked source appears in the version-change results | Inferred inventory relationships, actual operational harm/cost, legal severity, or a causal impact prediction |
| **7. Advisory language flags** (`language`) | Preserved source sentences and recognized acronym/definition wording | Flags for long sentences, potentially vague terms, unclear actors, mixed modal wording and acronyms without recognized expansions | A legal defect, grade-level certification, a duty in advisory text, or a reason to sacrifice necessary legal precision |
| **8. Dates and workload** (`deadlines`) | Explicit effective dates/status and supplied findings/audit records; owner-entered assignments for follow-up | Upcoming source dates within the configured horizon, date/status reconciliation cues and counts of pending/blocked/reopened review work | New compliance deadlines, a late task without an explicit due date, an automatic change in legal status, or proof that an old effective date makes a task overdue |
| **9. Public peer/research suggestions** (`peer_research`) | Local instruments plus selected external references from other jurisdictions explicitly marked `reference_scope: public` | Related passages suggested by overlapping nontrivial vocabulary, with supporting text | Semantic similarity, comprehensive research, peer-policy applicability, equivalence, access to another tenant's private material, or binding force |

All checks work with the active workspace's authorized inputs. Marking a reference public does not publish it globally or bypass tenant access. The optional peer check does not retrieve other offices' sources; an appropriate public reference must already be supplied to the active workspace and selected for the analysis.

### Evidence and uncertainty

- Source-derived text observations include exact excerpts and generated text locations where available. Metadata-based observations identify their source or explicit mapping; they may have no quotation because their basis is a date, tag, inventory link or review record.
- An explicit tag and a textual mention are distinguished. Neither alone establishes adequate policy coverage.
- Missing prerequisites produce an input-needed result or warning. A disabled check is labeled disabled, not passed. “No candidates identified” is not a finding of compliance.
- Obligation extraction recognizes a limited set of English patterns. It preserves recognized conditions, negation and same/adjacent-sentence exceptions, but complex syntax, long-range exceptions, quoted obligations and unfamiliar drafting styles need human review.
- Source version selection respects available prior snapshots and their recorded creation times. A retrospective comparison must not silently use later text as its predecessor.
- The current engine bounds output to 100 items per feature and excerpts long differences/text. Warnings identify omitted items or excerpted comparisons; consult the preserved full sources or narrow the review scope.

The engine does not assign legal force from a numeric weight. Existing binding-determination guards check eligible source type, in-force status, known dates and any required adoption reference; the policy owner must still confirm actual scope and exceptions.

## Running checks and preserving results

Choose **Check now** to analyze the available workspace inputs, or analyze the sources pinned to a particular review. Review suggestions remain separate from human-entered findings. They do not automatically accept findings, assign legal applicability or change an owner's decision.

Saved results include the rule-engine version, as-of date, source evidence, settings/context snapshots and input identity/hashes. These allow inspection of what was actually checked even if workspace controls or newer source versions later change. Inspect the saved report's settings rather than assume every feature was enabled.

Use the full evidence JSON export for retained source text, findings, decisions, attributed audit events and saved analysis reports. Use the plain-text brief for a readable review summary with recorded findings, evidence, applicability/decisions, follow-up work and available rule-based suggestions. The brief is not generated amendment text and is not an automated legal opinion.

## Local monitoring

Monitoring operates on snapshots already supplied to COMPASS. It does not fetch updates from the planned external database. Its purpose is to notice local changes and maintain visible follow-up work.

- **Source-change triggers:** new nonduplicate source snapshots can queue a local check when the owner has enabled this trigger.
- **Context/settings triggers:** changed review context or analysis settings can queue a fresh check when the context-change trigger is enabled. Prior results remain inspectable.
- **Effective-date checks:** when recurring monitoring and its effective-date option are enabled, check the office's local calendar date and queue a fresh review on a new day. They surface stored dates and possible status inconsistencies; they do not amend the source or determine legal effect.
- **Recurring checks:** opt-in, with a default interval of 24 hours. The interval is configurable; this is a local elapsed schedule rather than a guarantee that external sources refresh daily.
- **In-app digests:** opt-in through monitoring, with a default seven-day interval. They appear in the workspace; no email or external message is sent.

Source/context event-trigger switches are independent of the recurring-schedule enable switch. Turning off the recurring schedule alone does not disable an explicitly enabled event trigger. Set the relevant event switches off if those checks are unwanted. Effective-date daily checks and digests require the recurring-monitoring enable switch. Workspace timezone defaults to `America/New_York` and accepts IANA timezone names.

### Worker and durable work

The normal CLI starts the local worker:

```sh
.venv/bin/python -m compass --demo
```

Keep it running for queued jobs and recurring checks to execute. Job state is retained in the SQLite database so work can be inspected and failures retried rather than depending on a live browser tab. Jobs preserve their input snapshots, deduplicate an identical analysis basis, use leases to reclaim interrupted work, and bound attempts to three with persisted retry delays. The owner can request a retry of a failed job within that limit. These mechanisms do not approve findings.

The local worker is not an external distributed broker or production scheduling service. A stopped application cannot deliver a timely digest or execute a scheduled check; retained state is not an uptime guarantee. The first enabled monitoring tick initializes the digest interval rather than sending a week of invented history.

Application-factory calls default to `run_worker=False`, including test construction, so importing/creating an app does not silently start background loops. CLI operation explicitly requests the worker; it runs only in the local demo mode. Production identity and worker deployment are not configured.

Workspace members can inspect their office's local monitoring results and notices; retry controls and workspace settings remain owner-controlled. Job and report lookups are scoped to the authenticated workspace. Do not interpret another state's name in an approved public reference as a job-data leak; isolation concerns ownership and authorized access.

## Assignment and review decisions

Owners can assign a finding to a named follow-up assignee and optionally enter a due date. Assignment records retain the assigning owner and time. An assignee label is not user provisioning, an access grant, an email address lookup or a notification connection.

Applicability review, assignment and accept/reject/request-information actions remain separate from automated suggestions. Changing an applicability premise invalidates the current decision and preserves the earlier event. A reviewer cannot obtain owner privileges by switching to Advanced view or disabling complex analysis.

## Validation and next evidence

Use synthetic cases to test exact rule behavior, disabled-check handling, source links, saved snapshots, tenant/role boundaries and job recovery. Real-world accuracy needs independently reviewed positive/negative cases covering exceptions, future-effective and conditional rules, conflicting definitions, missing references, public peer material and irrelevant matches.

Provide the [required inputs](INPUTS.md) before treating these aids as evidence of value on real policies. Improve authoritative coverage, provenance and evaluation before adding larger models or broader infrastructure. The [roadmap](ROADMAP.md) separates local implementation from shared production gates and later analytical expansion.
