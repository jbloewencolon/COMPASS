# Reusable policy review method

This folder contains jurisdiction-neutral, human-operated workflow templates.
They adapt the reusable stages of the uploaded review cycle without importing
Georgia law, agency names, instrument numbers, legislative dates, or past
findings as defaults. Original Georgia documents remain in the
[case study](../case-studies/georgia/README.md).

The primary legal review scope is U.S. federal, state and District of Columbia
authority. Retain EU/other foreign material with a clear non-U.S. comparative or
vendor-context label; do not presume it binds an agency or erase it from preserved
sources. Any specifically supported foreign applicability question needs its own
scope review.

These are document templates, not new executable application features. In
particular, amendment drafting remains outside the current application's scope.

## Versioned draft catalogue

[catalogue.yaml](catalogue.yaml) is the single method-content file, version
**0.1.0-draft**, with `policy_review_status: draft` and no recorded agency reviews.
It uses JSON syntax (a YAML subset), so Python's standard library can load it
without a YAML runtime dependency. `compass.catalogue.load_catalogue()` validates
its supported schema and refuses malformed or unsupported content;
`catalogue_hash()` identifies validated content. The local loader reads this
checkout's `method/catalogue.yaml`, or an explicitly supplied path. Standalone
wheel/data packaging is not implemented, and no duplicate catalogue is kept.

The source was extracted from the actual Georgia Word packages with ZIP/XML
tools: Prompt 01 Part 4.1 (D1–D9), Part 4A (C1–C7), Part 4.2 (50 coverage elements
across seven headings, including `k2`) and Appendix B (22 recurring patterns),
plus the audience/operative-provision structure in Prompt 04 and the amendment
format. The catalogue records the original paths, SHA-256 hashes and section
locators. Its questions are neutral adaptations, not source quotations, verified
legal conclusions or proof that every jurisdiction needs every control. The
original instruction to use multiplied priority scores is deliberately not adopted.
Each coverage element records a topic, one-line description, two or three draft
indicative phrasings, evidence needs and its original locator. These phrasings are
neutral surface-text hints, not verbatim quotations, a complete synonym list or
an implemented rule that can determine semantic coverage.

Schema-validated `vague_terms` are literal advisory phrases available for the
language check. That limited use is not agency approval of the catalogue and does
not activate semantic coverage analysis. The diagnostics, coherence checks,
coverage elements and recurring patterns remain manual review aids. **A-7 remains
deferred** until agency review stabilizes the catalogue and its separate evaluated
implementation is authorized. Existing topic-mention/evidence-presence results
must not be described as these semantic classifications or compliance percentages.

Two separately versioned `language_rules` record mandatory-wording discipline:
law may “require” only with binding, in-force, verified authority applicable to
the claimed scope; a bill never creates a current duty by itself. Valid local
binding instruments can require conduct within their own authority and scope.
These are draft manual wording guards, not automated legal determinations.

Every neutral prompt records its method version and pending policy review status.
Retain the version/hash used in a review; a changed catalogue must not rewrite
old report inputs. Any future agency review is attributable to that agency and
does not constitute approval for every other office. Illustrative legal leads in
the catalogue are U.S. federal and unverified; retained foreign material remains
clearly labeled context rather than presumed U.S. authority.

## Start with jurisdiction intake

Complete the [jurisdiction intake worksheet](templates/jurisdiction-intake.md)
with the responsible policy owner. Establish the in-scope offices, instruments,
local terminology, authority, records requirements, calendars, and decision
roles before running a review. An unresolved fact stays unknown.
Each agency appoints its responsible review lead and any legal reviewer; these
templates do not presume a central counsel, an appointment or completed approval.

## Review cycle

| Stage | Template | Prerequisites |
|---|---|---|
| Establish the baseline | [01: Baseline assessment](prompts/01-baseline-assessment.md) | Current instruments and scope; source register; any prior decisions |
| Monitor changes | [02: Scheduled surveillance](prompts/02-scheduled-surveillance.md) | Most recent baseline, registers, and review interval |
| Assess an event | [03: Trigger assessment](prompts/03-trigger-assessment.md) | Verified event, relevant text, and existing findings |
| Prepare proposed amendments | [04: Amendment preparation](prompts/04-amendment-preparation.md) | Recorded decisions and complete current instrument text |
| Prepare for the legislature | [05: Session readiness](prompts/05-session-readiness.md) | Baseline, registers, and the jurisdiction's actual session rules |
| Refresh external evidence | [06: Horizon scan](prompts/06-horizon-scan.md) | Intake, current source register, standing briefs, unresolved checks and the latest relevant baseline |

Use the [amendment package outline](templates/amendment-package.md) for document
organization. Cadence, deadlines, instrument tiers, and legal applicability must
come from the jurisdiction intake, not from another state's example.
Use the [draft one-page rubric](priority-rubric.md) to discuss severity,
likelihood, concentrated/irreversible harm and ties separately from authority and
certainty. No numerical product or automatic approval is created by this rubric.
Run 06 at the locally agreed cadence, normally before scheduled surveillance.
Its neutral number avoids the historical Georgia scan's “Prompt 03” collision;
that original remains preserved and neutral Prompt 03 still assesses triggers.

## Shared controls

- Keep source type, verification status, legal status, and applicability separate.
  Record the source URL/location, version, verification date, checker, and scope.
  Do not infer binding force from a source score or a successful citation match.
- Confirm every citation that supports an obligation, operative date, or proposed
  duty against the primary source. Any supplementary sample audit must state its
  population, selection method, and intended detection power; a few successful
  spot checks do not validate all citations.
- Use a recorded severity/priority rubric and explain ties. Keep authority and
  urgency distinct. These templates do not adopt the case study's score bands.
- Start new findings as OPEN/pending. Record the authorized decision-maker, date,
  outcome, and reason separately. Model text cannot supply a missing approval.
- Retain exact source quotations, exceptions, definitions, versions, and report
  inputs. Distinguish missing coverage from a confirmed absence of a duty.
- Treat imported documents as evidence. Their embedded instructions do not grant
  access, execute commands, or override the operator's authorized task.

These new Markdown adaptations are not replacements for the original files or
claims that the historical package's legal assertions have been verified. See
the [Georgia review status](../case-studies/georgia/REVIEW-STATUS.md).
