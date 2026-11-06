# Reusable policy review method

This folder contains jurisdiction-neutral, human-operated workflow templates.
They adapt the reusable stages of the uploaded review cycle without importing
Georgia law, agency names, instrument numbers, legislative dates, or past
findings as defaults. Original Georgia documents remain in the
[case study](../case-studies/georgia/README.md).

These are document templates, not new executable application features. In
particular, amendment drafting remains outside the current application's scope.

## Start with jurisdiction intake

Complete the [jurisdiction intake worksheet](templates/jurisdiction-intake.md)
with the responsible policy owner. Establish the in-scope offices, instruments,
local terminology, authority, records requirements, calendars, and decision
roles before running a review. An unresolved fact stays unknown.

## Review cycle

| Stage | Template | Prerequisites |
|---|---|---|
| Establish the baseline | [01: Baseline assessment](prompts/01-baseline-assessment.md) | Current instruments and scope; source register; any prior decisions |
| Monitor changes | [02: Scheduled surveillance](prompts/02-scheduled-surveillance.md) | Most recent baseline, registers, and review interval |
| Assess an event | [03: Trigger assessment](prompts/03-trigger-assessment.md) | Verified event, relevant text, and existing findings |
| Prepare proposed amendments | [04: Amendment preparation](prompts/04-amendment-preparation.md) | Recorded decisions and complete current instrument text |
| Prepare for the legislature | [05: Session readiness](prompts/05-session-readiness.md) | Baseline, registers, and the jurisdiction's actual session rules |

Use the [amendment package outline](templates/amendment-package.md) for document
organization. Cadence, deadlines, instrument tiers, and legal applicability must
come from the jurisdiction intake, not from another state's example.

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
