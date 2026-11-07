# Correctness-cycle validation

Validation date: 2026-11-07 (America/New_York). Engine: `rules-v4`.
These results check implementation behavior; they do not establish current law,
policy approval, measured analytical accuracy or WCAG conformance.

| Check | Result |
|---|---|
| Python unit/API/migration suite | 172 tests passed, including permission, legacy-upgrade, unsupported-evidence, duplicate-passage and cross-workspace refusal cases |
| Original Georgia snapshots | All 39 unique originals match the pinned preservation manifest; original bytes unchanged |
| PDF extraction and API import | Seven actual Georgia PDFs, 64 pages, zero failed pages; original hashes and page-aware quotations retained |
| Method-register import | All 35 BASE-1 rows retained as pending suggestions; identity/provenance preserved; tampering and acceptance with unresolved gaps refused |
| Evaluation preparation | 150 actual PDF passages and blind templates; zero completed independent labels, metrics/agreement/severe-miss counts null |
| Method data | Catalogue 0.1.0-draft schema, provenance and refusal tests pass; no agency review invented |
| Automated accessibility | Nine core page states, zero axe violations/JavaScript errors; deliberately missing image alt text detected in the negative probe |
| Import browser regression | Eight checks, zero JavaScript errors: stale-response isolation, pending locks, failure disclosure, provenance and unsupported-format refusals |
| Decision workflow browser regression | Seven checks: audited self-grant, verified revision with preserved original, all three finding types, unconfirmed absence refusal, attributed acceptance and pinned export |
| Static/document checks | JavaScript syntax, local Markdown file links, lockfile consistency and patch whitespace checked |

The CI workflow runs the suite, preservation checks, evaluation status and all
three browser helpers against a throwaway demo. Development-only Playwright/axe
versions and official CI actions are pinned. Local checks do not claim that a
GitHub-hosted run has already executed.

This cycle adds **zero permanent tables**. SQLite rebuilds the existing finding
table transactionally to make legacy source-pair columns nullable, and membership
gains one permission column. Historical source/run/report payloads remain intact.
The only new runtime dependency is the named R-1 exception, `pypdf==7.0.0`.

Reproduction commands and detailed limits are in [ACCESSIBILITY.md](ACCESSIBILITY.md),
[PDF-IMPORT.md](PDF-IMPORT.md), [EVALUATION.md](EVALUATION.md) and the README.

## Requirements still dependent on people or supplied inputs

- **Legal errata:** current primary-source verification and each agency's actual
  disposition remain pending. The earlier primary retrieval attempt was blocked
  by outbound policy; none of the legal corrections is marked verified.
- **V-1/V-2:** two independent labelers and a distinct adjudicator must complete
  real submissions. The runner reports pending normally and refuses strict scoring;
  real precision/recall/agreement and the severe-miss baseline are not available.
- **A-7:** catalogue-driven semantic coverage waits for agency review stabilizing
  M-1. The existing topic-mention check is not that feature.
- **Manual accessibility:** axe incomplete color/name checks, screen-reader use,
  full keyboard/zoom and agency-specific workflows still need human review.
- **Production and other deferred work:** retain the explicit triggers in the
  [implementation plan](IMPLEMENTATION-PLAN.md); no pilot or production approval is
  inferred from local development tests.

## Earlier checkpoint: Milestones 0–1

Run date: 2026-11-07. Engine: `rules-v3`. These are regression results, not a
measurement of legal accuracy or an accessibility conformance certification.

| Check | Result |
|---|---|
| Python unit/API suite | 103 tests passed, including negative modal, citation, foreign-context, snapshot-migration, truncated-manifest and damaged-evidence cases |
| Original Georgia snapshots | All 39 unique originals match the preservation manifest; 18 errata keys match their actual files |
| Browser regression | Import notice visible and described in Simple/Advanced views; Escape dismisses the dialog; mobile import has no horizontal overflow; no JavaScript exceptions |
| axe-core 4.14.0, WCAG 2.1 A/AA tags | Zero automated violations across nine states: import, Home, Reviews and Settings in each view, plus mobile import |
| JavaScript syntax / patch whitespace | Passed |

The axe report retained incomplete checks for color contrast and, on import,
label/name comparison. These require human review. Screen-reader operation and
full keyboard coverage are not established by this result. Q-1's CI integration
remains deferred to its own ticket; no browser runtime dependency was added.

Reproduce the Python/preservation/syntax checks using the README commands. For the
optional browser check, use existing development Playwright/Chromium tooling and
an independently integrity-checked local axe script against a **throwaway** demo
database:

```sh
python3 scripts/check_ui.py --axe-script /path/to/axe.min.js
```

The helper refuses missing notices, broken descriptions, dialog/mobile regressions,
JavaScript errors and automated violations. It switches the demo owner's view
preference while exercising the app. It does not download or install tooling.
The audit used the npm `axe-core@4.14.0` archive, checked against its published
SHA-512 integrity value, with test-only script injection; the app CSP is unchanged.

The citation fixture distinguishes 20 designed syntax contexts from eight exact
uploaded-PDF citation lines and two actual Georgia prohibition passages. It is not
V-1's independently double-labeled, adjudicated corpus. Precision, recall, agreement
and severe-miss trend gates remain pending that corpus.

Legal errata are unverified drafts for each agency's appointed reviewers. Primary
source retrieval was blocked by the environment's outbound policy. No reviewer,
approval, current-law conclusion or completed verification is inferred from these
tests. See the [implementation plan](IMPLEMENTATION-PLAN.md) for dependency and
deferral triggers.
