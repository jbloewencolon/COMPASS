# Milestones 0–1 validation

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
