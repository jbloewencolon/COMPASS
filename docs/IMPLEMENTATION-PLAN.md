# Correctness milestones and agreed decisions

This is the delivery order for the next development cycle. Milestones 0–1 form
the first committed change; the remaining development follows below. A policy
review dependency is not completed by generating plausible labels or approvals.

## Decisions carried forward

- `finding_type` will describe evidence structure; existing issue categories stay.
- Absence/internal-conflict review must fit its actual evidence structure rather
  than invent an external legal citation. Completeness is scoped to the declared
  review corpus, not every potentially applicable law.
- Owners may grant applicability-review permission to either existing role,
  including themselves, with attribution and audit. The flag defaults off;
  finding acceptance remains owner-controlled. This is implemented in Milestone 2.
- Preserve source, profile, run and report snapshots. Later verification/status
  changes must not rewrite historical evidence or decisions.
- Court/AG material is flagged for review; do not automatically classify its
  effect as binding.
- US federal, state and DC authority is the primary legal scope. Retain EU and
  other sources with their true jurisdiction/type and a clear context label.
  A foreign-context source alone does not establish a US binding duty; any US
  contract/program route needs its own supporting authority.
- Each agency appoints its review lead and any counsel. No central lead counsel
  or independent evaluation labelers are currently appointed by this project.
- Evaluation will include document/page/context and source dates/status where
  needed to measure severe temporal or applicability errors.

## Milestones 0–1: first delivery

| Ticket | Implementation and verification | Remaining boundary |
|---|---|---|
| E-1 | Four-item [errata sidecar](../case-studies/georgia/ERRATA.md), including the three requested legal review items, keyed to original filenames and SHA-256; linked from catalog/README | Proposed corrections remain unverified and agency-review pending; primary retrieval was blocked by network policy |
| E-2 | SB-01 replacement research brief uses scoped US due-process/program sources | Agency must verify current primary texts, program/action coverage and exact OMB language |
| E-3 | Neutral [Prompt 06](../method/prompts/06-horizon-scan.md) added | Historical scan's Prompt 03 title and bytes retained |
| E-4 | Method scope updated, with foreign context explicitly retained | This supersedes the earlier instruction to remove foreign material |
| A-1 | Negative modals surface prohibition review candidates, including `may not` | Candidate wording is not an applicability decision |
| A-2 | Small abbreviation-aware sentence splitter, original quote offsets, profile extensions | Designed syntax fixtures are not independently verified legal quotations or V-1 ground truth |
| A-3 | Default federal/bill reference patterns; Georgia formats supplied through the profile | Matches are candidate records, not verified citations; no general legal parser |
| A-4 | Added specified vague phrases to the existing advisory check | Literal advisory terms now come from the schema-validated draft catalogue; semantic coverage still waits for review |
| A-5 | Added `will`, responsibility and `is/are to` drafting forms, explicitly marked weaker candidates | No resulting change in legal force |
| A-6 | Visible, described source-import notice; foreign source context labels; keyboard/browser and axe check | A warning is not data-classification enforcement or a full accessibility certification |

Milestones 0–1 added **zero tables and zero runtime dependencies**. `rules-v3`
creates new report bases while preserving saved `rules-v2` outputs. Synthetic
demo profiles move to `demo-2` with explicit state pattern configuration; stored
run/report profile copies remain unchanged. Real agency profiles are not replaced.

The syntax fixture deliberately distinguishes 20 designed US notation examples
with synthetic surrounding prose from eight exact uploaded-PDF citation lines
with page and SHA-256 provenance. It is a regression fixture, not the independently
adjudicated evaluation set promised by V-1.

## Milestone 2 — data and review controls

| Ticket | Delivered behavior | Verification boundary |
|---|---|---|
| D-0 | Fixed US state/DC/FED identifiers; internal sources match the workspace; foreign external context remains truthful | Bogus US identifiers are refused; historical originals are retained rather than silently relabeled |
| D-1 | Three finding structures, exact evidence lists, recorded absence searches; internal-only runs supported | Unsupported/unpinned/repeated passages and incomplete searches are refused; completeness is an attributed review of the declared corpus |
| D-2 | Default-off review permission, audited grants, server-attributed verification, immutable source review revisions, 30-character applicability rationale and authority relied on | Binding support needs a verified in-force revision pinned in the run; owners retain acceptance control; legacy records do not acquire fabricated verification |
| D-3 | Funding-condition/agreement pathways with a named program/contract for binding findings; court/AG flags | Court/AG and foreign context cannot automatically establish a binding or conditional duty |
| D-4 | Original/extracted/transcribed provenance and original file hashes; page maps and extraction failures retained | A file hash proves identity, not legal correctness; edited transcriptions lose page mappings |

The existing membership table gains one permission column. The existing findings
foreign keys become nullable so absence/conflict suggestions need no invented
external source. SQLite rebuilds that existing table transactionally; no permanent
table is added and historical payloads are not rewritten. Evidence exports use
schema version 2 for the broader evidence structures. See [DATABASE.md](DATABASE.md).

## Milestone 3 — real data and evaluation

| Ticket | Delivered | Pending requirement / trigger |
|---|---|---|
| R-1 | Bounded PDF preview/import, original hashes, exact page spans and explicit failed-page records; all seven originals extract | One named runtime dependency: pinned pypdf. No OCR/DOCX; originals are retained outside the app's binary storage |
| V-1 | 150 actual PDF passages, sampling/provenance protocol, blind independent label templates and adjudication file | Two independent agency-appointed people and a third adjudicator must supply real labels; segmentation/tier/status uncertainties are disclosed |
| V-2 | Rules-v4 predictions, scorer, pending baseline, per-check metrics/agreement and severe-regression logic, CI evaluation status | Accuracy and severe-miss values stay null until V-1 is adjudicated. Strict mode refuses missing labels; once a real baseline exists, CI refuses increased severe misses |
| I-1 | Converter and authenticated import preserve all 35 BASE-1 IDs/rows/provenance as pending suggestions; idempotent and rejects forged decisions | All 35 have unresolved evidence/review gaps. Record supported follow-up findings using actual pinned sources; this does not establish a need for a fourth finding type |

No model, provider adapter, new exchange protocol, worker system or production
service was introduced. See [PDF import](PDF-IMPORT.md), [evaluation](EVALUATION.md)
and [method import](METHOD-IMPORT.md) for exact contracts and reproduction.

## Milestone 4 — method content as data

| Ticket | Delivered | Remaining boundary |
|---|---|---|
| M-1 | One schema-validated catalogue `0.1.0-draft`: D1–D9, C1–C7, 50 expected elements with topic/description/indicative phrases, 22 recurring patterns, two language rules, advisory vague terms; all six neutral prompts cite it | Agency review remains pending. Only the literal vague-term list is used by the rules; reports/jobs pin its version/hash/actual terms |
| M-2 | Intake explicitly covers legislative calendars, tribal/NAGPRA/confidentiality/data agreements, funding programs and COMPASS records | Agencies supply actual obligations, appointments and schedules; no universal tribal or retention code |
| M-3 | One-page rubric, concentrated-harm and irreversibility fields in findings/UI/exports | Manual anchored judgments; no multiplied score, and authority/certainty stay separate |
| M-4 | Resident text/estimated reading level, audience readability notes and adversarial-reader sections | Templates require actual review; no amendment drafting feature in the app |
| A-7 | **Deferred** as required by its dependency | Build only after the responsible agency stabilizes/reviews M-1. Current topic evidence-presence checks do not claim semantic coverage or legal compliance |

**Ticket correction:** coverage is A-7; A-5 concerns modal forms. The earlier
reference to coverage as A-5 is not a second analytical feature.

## Five implementation checks applied

| Check | Decision for this cycle |
|---|---|
| Need | Actual BASE-1 absences/conflicts, unsupported legal status and seven uploaded PDFs establish the concrete tasks |
| Reuse | Extend existing finding/source JSON, membership, audit, analysis, jobs and native forms; retain the existing 16 tables |
| Standard/native | Use SQLite migration, standard-library JSON/ZIP/XML/hash tools, native file/date/select/checkbox controls and existing browser dialogs |
| Installed dependency | FastAPI/Pydantic provide request validation; no new schema, role, parser or worker framework |
| Minimum | Add fields, lists and a boolean permission. PDF text extraction is the single named library exception because the standard library cannot do it |

## Definition of Done

For every ticket, test the new behavior and at least one refusal/flagging case;
update the relevant analysis, data or method documentation; add no runtime
dependency or table without a named ticket exception; preserve every original
case-study file; and record each deferred sub-part with its trigger. Run
`python3 scripts/check_case_study.py` to refuse missing or altered originals.
Corrections belong in ERRATA.md; catalog and guide links can point to the sidecar.
The preservation check pins manifest membership as well as original-file hashes;
only reviewed future intake can trigger a baseline update retaining existing files.
See [validation results and reproduction](VALIDATION.md) for this first delivery.

## Q-1 and deferred work

**Q-1 is implemented:** one locked axe/Playwright run on core pages in CI, plus
PDF import regression checks. Official CI actions are pinned to commit hashes.
Local automated results do not substitute for GitHub execution or manual
keyboard/screen-reader review. See [ACCESSIBILITY.md](ACCESSIBILITY.md).

| Deferred item | Trigger to revisit |
|---|---|
| New analytical check or LLM | Adjudicated V-1 or a later explicitly scoped evaluation such as S-2 demonstrates material misses the current rules cannot reasonably address |
| External database adapter | Provider contract and usable sandbox/export exist |
| Production identity/shared hosting, encryption, backups, distributed workers and availability | Signed pilot and real hosting/security requirements; revisit immediately before any restricted data is introduced |
| Retention automation | Pilot state supplies its records schedule |
| Hash-chained audit / normalized decisions | Pilot agreement or a records-officer request |
| DOCX/OCR | A supplied real task cannot be handled by PDF/text import |
| Territories | A territory partner is identified |
| Amendment drafting in the app | Existing roadmap adoption/drafting gates are satisfied; unchanged this cycle |
| Cross-state dashboards/benchmarking | At least two states have completed reviews with the same catalogue version |
| Additional abstractions | A supplied real use case differs from the current Georgia/second-state proof |

Every subsequent milestone keeps the one-table/zero-runtime-dependency budget
unless its ticket names the exception and its reason. Existing fixtures and
workflow paths should be reused before new architecture is considered.
