# Prompt 03 — Horizon Scan and Anchor Maintenance

**Cycle:** GTA AI Policy Review Cycle
**Version:** 1.0 (draft for Office of AI ratification)
**Cadence:** Quarterly, run *before* Prompt 02 in the same quarter
**Run ID format:** `SCAN-n`, sequential and never reused
**Writes to:** Anchor Register only
**Does not write to:** Governance Register

---

## PART 0 — WHAT THIS PROMPT IS FOR, AND WHAT IT IS NOT

This prompt exists because the cycle has no inward flow of external evidence. The Anchor Register grows only when an assessment run trips over something while verifying an existing anchor, or when a watch trigger fires. Of the watch items live at SCAN-0 baseline, two point outward at external practice and both wait on an event rather than a scheduled sweep. For an instrument family whose central defect is a principle dropped from a withdrawn federal framework, that is a structural weakness.

**This prompt is a research programme, not a news feed.** The distinction is operative, not rhetorical, and it is enforced by Part 2. A scan optimised for novelty floods the register with speculative material and destroys the thing that makes the register useful — the ability to filter for what is load-bearing. The register already carries roughly sixty entries. Forty speculative additions a quarter would make the `KEY` filter worthless within a year.

The target is therefore **not** "the most cutting-edge Responsible AI research." The target is:

1. Evidence that changes what GTA must do.
2. Drafting precedent for a provision the instrument family lacks.
3. Resolution of a question the register has already recorded as open.

Novelty is not a qualification. An item that is new, interesting, widely discussed, and bears on nothing GTA does is **rejected and logged as rejected**.

### Authority boundaries

| Block | Authority | Reason |
|---|---|---|
| `ADD` | Emit directly | Additive; a new anchor changes nothing that already rests on the register |
| `WATCH` | Emit directly | Additive; a trigger creates an obligation to look, not a finding |
| `CHECK-RESOLVED` | Emit directly | Closes an open question; the register is better for it |
| `AMEND-PROPOSED` | **Propose only** | Findings rest on anchor content. Changing an anchor silently changes what a finding means |
| `RETIRE-PROPOSED` | **Propose only** | Retiring an anchor can remove the evidentiary basis of an adopted provision |
| `FINDING` | **Prohibited** | Findings are Prompt 01 and Prompt 02 territory. This prompt has no authority to open, score, close, or re-score one |

Proposals are dispositioned by the next Prompt 01 or Prompt 02 run, which has the instrument text in front of it. **A scan proposes; an assessment disposes.**

---

## PART 1 — INPUTS, READ IN THIS ORDER

Read all four before searching. A scan run without them duplicates work already done and re-litigates questions already settled.

1. **Anchor Register**, current version. Extract three things:
   - Every existing entry, so nothing already present is proposed as an `ADD`.
   - Every `CHECK`-marked item. These are the standing questions of Part 2.1.
   - Every entry whose `Staleness` column reads stale, or whose verified date is more than 180 days old. These are the re-verification queue of Part 4.4.
2. **The Watch List**, and specifically **the highest watch-item number in use.** New watch items continue that sequence. They are never numbered from a fresh sequence, and never renumbered.
   > *This instruction exists because it was got wrong once. The BASE-1 run issued W-11 through W-22 without reading the existing W-01 through W-10, and eight of the twelve duplicated items already present. Eight citations in the assessment now resolve only through a crosswalk table that should never have been needed.*
3. **The Reject Log** (Appendix B of this prompt, maintained across runs). Anything on it stays rejected unless its tier has changed. Do not re-argue a settled rejection.
4. **The Standing Briefs** (Part 2.1), which carry forward until answered or withdrawn.

---

## PART 2 — ADMISSION CRITERIA

An item enters the register only if it clears **both** gates.

### Gate 1 — Relevance, stated as a locator

Every proposed entry must name, in the entry itself, **either**:

- a GTA instrument and provision it bears on (`SS-23-002 §4`, `PS-23-001 Definitions`), **or**
- a governance-register finding it supplies evidence or precedent for, **or**
- a standing brief from 2.1 it answers, **or**
- an existing `CHECK` item it resolves.

An item that cannot name one of the four is out of scope regardless of merit. "Relevant to responsible AI generally" is not a locator, and neither is "useful context."

### Gate 2 — Tier and ceiling

| Tier | Admission |
|---|---|
| E1 — binding, final, replicated | Admit if Gate 1 passes |
| E2 — adopted-not-effective, official draft, corroborated practice | Admit if Gate 1 passes |
| E3 — single study, preprint, vendor report | Admit **only** if it answers a standing brief, and only with the tier stated and the limitation named |
| F1 — forward-looking, timetabled | Admit as `WATCH`, not as `ADD`, unless it also carries present drafting value |
| F2 — forward-looking, speculative | **Do not admit as an `ADD` under any circumstances.** `WATCH` only, with a specific observable trigger |

**Per-run ceilings:** maximum **12** `ADD` entries and **6** new `WATCH` items. At least **half** of the `ADD` entries must bear on a standing brief or resolve a `CHECK` item.

The ceiling is a forcing function, not an administrative limit. If a run finds thirty qualifying items, it has found that the register was badly incomplete, and it should say so in the run note and rank the thirty rather than admitting all of them. A register that grows by thirty entries a quarter is not being maintained; it is being buried.

### 2.1 Standing briefs

These are the questions the cycle needs answered from outside Georgia. Each carries forward until answered or formally withdrawn by the Office of AI. The list is seeded from the BASE-1 findings; add and retire briefs deliberately, and record both.

| Brief | Question | Serves |
|---|---|---|
| SB-01 | **Contestability.** How have other jurisdictions drafted a resident's right to contest, appeal, or obtain human re-determination of an automated decision — as binding text, not principle? Include the operative language, the trigger threshold, and the remedy | F01, the highest-priority finding in the register, and the role vacated when the fifth OSTP Blueprint principle was dropped in adaptation |
| SB-02 | **Notice and explanation.** Binding drafting precedent for notice that an automated system is in use, and for explanation of an adverse outcome calibrated to risk | F05 |
| SB-03 | **Agentic governance.** Any published control set, overlay, authorization framework, or procurement term for agents that hold enterprise credentials and take autonomous action | F03, F26; SS-23-002 proposed §14 |
| SB-04 | **Disparity testing methodology.** Named methods, cadences, protected-class disaggregation, and disparity thresholds that a state can actually require and verify | F08 |
| SB-05 | **AI incident definition.** A severity taxonomy and definitional threshold that makes a reporting clock operable | F09 |
| SB-06 | **Inventory schema.** Published government AI inventory schemas, with field lists and validation rules | F15 |
| SB-07 | **Human oversight specification.** How to specify information set, override authority, competence standard, and time budget so that "human review" is a control rather than a formality | F06, F33 |
| SB-08 | **Vendor evidence.** What documentation vendors can in fact supply, and what state solicitations are successfully obtaining. Bounds what a procurement clause can demand | F07 |
| SB-09 | **Non-retaliation.** Design precedent for protecting a person who reports AI misuse or failure | F19 |
| SB-10 | **Accessibility of AI output.** Conformance approaches for AI-generated content and AI-mediated interfaces under an ADA Title II obligation | F04; hard date 26 April 2027 |

---

## PART 3 — SOURCE DOMAINS

### 3.1 Where to look

Search these. The list is deliberately narrow: a scan that searches broadly returns commentary, and commentary is not evidence.

**Category A — law and regulation, outside Georgia**
Federal Register; eCFR; DOJ Civil Rights Division and ADA.gov; Congressional bill trackers for AI preemption vehicles; state legislature bill trackers for enacted AI statutes; NCSL AI legislation database; official texts of comparator statutes; EU Official Journal.

**Category B — standards and government guidance**
NIST — AI publications, CSRC, COSAiS project pages, CAISI outputs, NCCoE concept papers; CISA and NSA advisories, including joint international guidance; ISO/IEC JTC 1/SC 42 published-standards catalogue; OECD.AI; NASCIO; GovAI Coalition; GovRAMP/StateRAMP; peer-state CIO and AI office publications, executive orders, and enterprise policies.

**Category C — research and documented practice**
ACM FAccT and AIES proceedings; recognised venues for evaluation and alignment work; AI Incident Database; OECD AI Incidents Monitor; state and federal enforcement actions and litigation dockets; audit and inspector-general reports on public-sector automation; the annual AI Agent Index or its successor.

### 3.2 Where not to look, and what not to cite

- Vendor marketing, product blogs, and self-published capability claims — except as **evidence of what a vendor will document**, which serves SB-08 and must be labelled E3.
- Consultancy thought-leadership, newsletters, Substack and LinkedIn commentary, podcast transcripts.
- Aggregators and secondary trackers as a *citation*. Use them to find the primary source, then cite the primary source.
- Any page without a date, version, or status.
- Any preprint presented as though final.

### 3.3 Georgia is out of scope

Georgia enacted and proposed law stays with Prompt 01 and Prompt 02, because the legislative calendar drives it and those prompts run against the session. This prompt covers external comparative law, federal law binding on Georgia state entities, standards, and research.

**One exception.** If a scan finds that a Georgia instrument outside the AI family has changed in a way that reaches AI use — a records schedule, a purchasing rule, a cross-referenced PSG — record it as an `ADD` and flag it in the run note. That is precisely the sort of thing an assessment reading only the AI topic tag will miss.

---

## PART 4 — SCAN PROTOCOL

### 4.1 Standing briefs first
Work Part 2.1 in order. These are the searches with a known consumer. Do them before any open-ended sweep, and record against each brief either an answer, partial progress, or "nothing new this run" — the last of which is a result and should be written down.

### 4.2 Open `CHECK` items second
Every `CHECK` in the register is a citation the cycle cannot currently make. Resolving one is worth more than adding a new anchor, because it unblocks work already scoped. Carry each until resolved.

### 4.3 Hard dates and commencements third
Any register entry with a date certain inside the next four quarters: confirm status, confirm the date has not moved, confirm whether a draft has been finalised. Interim and proposed rules are the priority — an interim final rule can be finalised, extended, or withdrawn, and each has a different consequence.

### 4.4 Staleness queue fourth
Re-verify entries the register flags as stale. Re-verification is maintenance: update the verified date even when nothing changed, and say that nothing changed. An entry confirmed unchanged is a stronger record than an entry nobody looked at.

### 4.5 Open sweep last, and only against the ceiling
Whatever ceiling capacity remains after 4.1–4.4. Search the Part 3.1 domains for material that clears both gates. Rank by whether it changes an obligation, then by whether it supplies drafting text, then by tier.

### 4.6 Verification standard
Every item, in every block:

- Name the **primary source**, with the locator a reader can check: statute and section, Federal Register volume and page, CFR section, standard number and edition, DOI or proceedings citation.
- State **status** and **effective or publication date**, distinguishing published from adopted from effective from in force.
- Assign exactly one **evidence tier**.
- If the item is a draft, say what would finalise it and whether a date is announced. "In development, no announced publication date" is a complete and useful answer.
- If a figure could not be confirmed, **do not carry the figure.** Record the item and mark it `CHECK`.
  > *Precedent: the register carried an unverified claim about NIST agent red-team success rates for a full cycle before a run flagged it. A number nobody has checked is worse than no number, because it will be cited.*

---

## PART 5 — OUTPUT

Six blocks, in this order. Columns match the Anchor Register exactly so each block pastes without reshaping.

### 5.1 Run metadata
Run ID, date, run by, quarter, register version read, number of entries and watch items read, ceiling used of ceiling available.

### 5.2 `ADD` — new anchors
`Category | Marker | Entry | Status | Key dates | Relevance | Verified`

`Relevance` must satisfy Gate 1 explicitly: name the instrument, provision, finding, brief, or `CHECK` item. Set `Marker` to `KEY` only where a GTA rule would actually depend on the entry.

### 5.3 `WATCH` — new watch items
`# | Item | Current tier | Trigger that makes it actionable | Expected | Owner`

Numbering continues the existing sequence. The trigger must be an observable event with a subject and a verb — "either overlay published as an initial public draft," not "monitor developments in agent security."

### 5.4 `CHECK-RESOLVED`
`Item | Question that was open | Resolution | Primary source | New marker`

State plainly whether the resolution makes the entry citable, and if the answer changes what a finding rests on, say which finding.

### 5.5 `AMEND-PROPOSED` and `RETIRE-PROPOSED`
`Entry | Current register text at issue | Proposed change | Why | Findings affected | Disposition (blank — for Prompt 01/02)`

Leave the disposition column blank. Filling it is the assessment's act, not the scan's.

### 5.6 Standing brief report
`Brief | Searched | Result | Carried forward?`

And the reject log additions: `Item | Why rejected | Would reconsider if`.

A rejection with no reconsideration condition is not a rejection; it is a permanent exclusion nobody decided to make.

---

## PART 6 — RUN LOG

Append one line to the Anchor Register run record, or to the Governance Register run log if the Office of AI prefers a single run history:

`Run ID | Prompt | Date | Run by | ADD / WATCH / CHECK-RESOLVED / PROPOSED | Ceiling used | Output filed at`

Then a short run note, no more than 200 words, covering only: what changed in the external environment that GTA should know about this quarter; whether any hard date moved; and whether the ceiling bound.

---

## PART 7 — SELF-VERIFICATION BEFORE OUTPUT

Confirm each. Correct any failure before responding. Do not print the checklist.

1. Every `ADD` names a GTA instrument, provision, finding, standing brief, or `CHECK` item in its relevance text.
2. No `ADD` is at tier F2. No `ADD` at E3 lacks a standing-brief justification and a stated limitation.
3. No `ADD` duplicates an existing register entry. Every existing entry was read before proposing.
4. New watch numbers continue the existing sequence and no existing number is reused or renumbered.
5. Ceilings respected: 12 `ADD`, 6 `WATCH`. At least half the `ADD` entries serve a brief or a `CHECK`.
6. Every item carries a primary-source locator a reader can check, a status, a date, and exactly one tier.
7. No unverified figure is asserted. Anything unconfirmed is marked `CHECK` and stated as unconfirmed.
8. No block opens, closes, scores, or re-scores a governance finding.
9. Every `AMEND-PROPOSED` and `RETIRE-PROPOSED` names the findings affected and leaves disposition blank.
10. Every standing brief has a recorded result, including "nothing new this run."
11. Every rejection carries a reconsideration condition.
12. Georgia enacted and proposed law is untouched, except any out-of-family instrument change flagged under 3.3.

---

## APPENDIX A — SEED CONTEXT AT SCAN-1

Carried from Run BASE-1, 27 July 2026, so the first scan does not start blind.

**Seven open `CHECK` items.** SB 540 subsection locators against the enrolled act; the O.C.G.A. § 50-25-4 subsection divergence; currency and titling of SS-15-002 and SS-08-045; the NIST SP 800-63B revision in force; the June 2026 federal executive action on AI security; the NIST agent red-team success-rate figures; and the finalisation status of the ADA Title II interim final rule — the last being a status question rather than a citation block.

**Hard dates inside four quarters of SCAN-1.** SB 444 commencement, 1 January 2027. The 2027 Georgia legislative session convening January 2027. Then, one quarter beyond: ADA Title II compliance for Georgia state agencies, 26 April 2027, under an interim rule whose comment period closed June 2026.

**Highest watch number in use: W-22.** New items begin at W-23.

**Known-empty spaces**, where the register holds a question rather than an answer. NIST COSAiS single-agent and multi-agent overlays do not exist in any published draft and no publication date is announced. No jurisdiction has been identified with binding text on contestability that GTA could adapt — SB-01 is the highest-value unanswered brief in the set. The three 2025 GTA instruments were absent from the BASE-1 review set entirely, which is why W-19 exists.

---

## APPENDIX B — REJECT LOG

Maintained across runs. Empty at SCAN-1.

`Item | Run rejected | Why rejected | Would reconsider if`

---

## OPEN QUESTIONS FOR THE OFFICE OF AI

Four choices this draft made that the Office of AI should confirm or overturn before SCAN-1.

1. **Prompt number and collision with Prompt 02.** Numbered 03 on the assumption that Prompt 02 is the quarterly assessment run. If Prompt 02 already contains a research or environment-scanning section, that section and this prompt must be reconciled rather than run in parallel — two prompts writing `ADD` blocks to one register will duplicate entries, which is the failure this prompt is written to prevent.
2. **Cadence and sequencing.** Quarterly, running before Prompt 02 in the same quarter, so the assessment reads a freshly verified register. The alternative — running after — means each assessment works from a register three months stale.
3. **Propose-only authority for `AMEND` and `RETIRE`.** The Anchor Register's maintenance rule 2 contemplates runs emitting all four block types directly. This draft deliberately narrows that for a scan: additive blocks direct, subtractive blocks proposed. If the Office of AI would rather a scan amend directly, delete the Part 0 authority table and Part 5.5's disposition column.
4. **Ceilings.** Twelve `ADD` and six `WATCH` are set from the observed size of the register, not from a rule. If the register is intended to grow faster, raise them — but raise them explicitly, and watch what happens to the `KEY` filter.

---

*GTA AI Policy Review Cycle — Prompt 03 v1.0 draft, prepared 7 August 2026, seeded from Run BASE-1*
