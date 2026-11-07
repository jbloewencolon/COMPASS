# Correctness milestones and agreed decisions

This is the delivery order for the next development cycle. Milestones 0–1 form
the first reviewable change; subsequent milestones follow in order. A policy
review dependency is not completed by generating plausible labels or approvals.

## Decisions carried forward

- `finding_type` will describe evidence structure; existing issue categories stay.
- Absence/internal-conflict review must fit its actual evidence structure rather
  than invent an external legal citation. Completeness is scoped to the declared
  review corpus, not every potentially applicable law.
- Owners may grant applicability-review permission to either existing role,
  including themselves, with attribution and audit. The flag defaults off;
  finding acceptance remains owner-controlled. This is Milestone 2 work.
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
| A-4 | Added specified vague phrases to the existing advisory check | Use a simple constant until the policy catalogue exists and is reviewed |
| A-5 | Added `will`, responsibility and `is/are to` drafting forms, explicitly marked weaker candidates | No resulting change in legal force |
| A-6 | Visible, described source-import notice; foreign source context labels; keyboard/browser and axe check | A warning is not data-classification enforcement or a full accessibility certification |

This delivery adds **zero tables and zero runtime dependencies**. `rules-v3`
creates new report bases while preserving saved `rules-v2` outputs. Synthetic
demo profiles move to `demo-2` with explicit state pattern configuration; stored
run/report profile copies remain unchanged. Real agency profiles are not replaced.

The syntax fixture deliberately distinguishes 20 designed US notation examples
with synthetic surrounding prose from eight exact uploaded-PDF citation lines
with page and SHA-256 provenance. It is a regression fixture, not the independently
adjudicated evaluation set promised by V-1.

## Next: Milestone 2 — minimal data changes

Implement D-0–D-4 together with a migration for existing local data:

1. Validate US office/authority identifiers against the 50 states, DC and US-FED
   while preserving explicitly labeled foreign external context. Do not force a
   foreign instrument into a false US jurisdiction or source type.
2. Add `external_gap`, `internal_conflict` and `absence` evidence structures;
   preserve category, search scope and provenance. Gate an absence conclusion on
   an authorized completeness review of the declared corpus.
3. Add source verification and audited membership permissions. Only an explicitly
   permitted reviewer verifies or determines binding/conditional applicability.
   Record authority relied on and a useful rationale; unknown evidence stays
   unknown. Verification identity/time come from the recorded action.
4. Add funding-condition and agreement pathways with their program/contract
   attachment. Court/AG items are review flags, not an automatic binding route.
5. Add original/extracted/transcribed provenance and original file hashes.

No new decision-role system or normalized decisions table is planned. Preserve
old source revisions and pinned evidence when verification or status changes.

## Milestone 3 — real data and evaluation

- **R-1:** import the seven PDFs with page locations and original hashes; list
  failed pages. No OCR/DOCX feature. If a library is needed, this ticket is the
  explicit exception for **one** maintained PDF runtime dependency because the
  Python standard library does not extract PDF text; choose after inspecting
  available supported tools, not by adding a general ingestion framework.
- **V-1:** prepare about 150 stratified sentences with original document/page,
  context and relevant source metadata. Each agency supplies two independent
  labelers and an adjudicator. Unlabeled material is not scored as gold truth.
- **V-2:** record rules-v3 precision/recall, agreement, and severe-miss counts only
  after adjudication. Define severe categories before labeling. Gate future engine
  versions on the recorded cases; do not report invented passing accuracy.
- **I-1:** import the 35 BASE-1 findings as pending suggestions, preserve original
  IDs/run/provenance, and report evidence types that do not fit D-1.

## Milestone 4 — policy content as data

- **M-1:** one versioned method catalogue, structured/validated by developers and
  reviewed by each responsible agency. No plugin system or new rules language.
- **M-2:** extend intake for local legislative calendars, tribal consultation/
  NAGPRA/cultural-resource confidentiality, funding programs, and retention of the
  tool's own records. No tribal code branch or universal records schedule.
- **M-3:** agency-reviewed one-page rubric; optional concentration/irreversibility
  fields. Keep authority/certainty separate and avoid a combined score.
- **M-4:** add resident-language/readability and adversarial-reader passes to the
  amendment outline. No automated amendment generator is authorized by a template.
- **A-7:** extend the existing coverage check only after M-1 is stable. Expected
  Georgia outcomes must be independently supported, not merely match BASE-1.

**Ticket correction:** coverage is A-7; A-5 concerns modal forms. The earlier
reference to coverage as A-5 is not a second analytical feature.

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

**Q-1:** add one pinned axe/Pa11y run on core pages to CI, using development-only
tooling. The Milestone 1 local axe check is not yet a CI workflow. Keep manual
keyboard/screen-reader checks separate from automated findings.

| Deferred item | Trigger to revisit |
|---|---|
| New analytical check or LLM | Adjudicated V-1 or a later explicitly scoped evaluation such as S-2 demonstrates material misses the current rules cannot reasonably address |
| External database adapter | Provider contract and usable sandbox/export exist |
| Production identity, encryption, distributed workers and availability | Signed pilot and real hosting/security requirements; revisit immediately before any restricted data is introduced |
| Retention automation | Agency records schedule and pilot requirements are supplied |
| Hash-chained audit / normalized decisions | Pilot/records requirement or concrete cross-decision reporting need |
| DOCX/OCR | A supplied real task cannot be handled by PDF/text import |
| Territories | A territory partner is identified |
| Amendment drafting in the app | Existing roadmap adoption/drafting gates are satisfied; unchanged this cycle |
| Cross-state dashboards/benchmarking | At least two states have completed reviews with the same catalogue version |
| Additional abstractions | A supplied real use case differs from the current Georgia/second-state proof |

Every subsequent milestone keeps the one-table/zero-runtime-dependency budget
unless its ticket names the exception and its reason. Existing fixtures and
workflow paths should be reused before new architecture is considered.
