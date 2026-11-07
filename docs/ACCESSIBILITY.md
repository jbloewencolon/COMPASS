# Accessibility regression checks

Pull requests and pushes to `main` run one axe-core audit of nine core page states:
the source import dialog, Home, Reviews and Settings in Simple and Advanced views,
plus mobile source import. The workflow also runs the full Python suite, verifies
the preservation manifest and checks JavaScript syntax. GitHub Actions are pinned
to immutable commits; development packages are exact versions with lockfile
integrity records.

A separate eight-check import browser regression follows the accessibility audit.
It checks stale file-selection responses, provenance after manual editing, failed
page disclosures, rejection of unsupported DOCX/invalid UTF-8/image-only PDFs,
plain-text byte hashes, and the non-absence applicability form. It uses the real
local UI/login but controls preview timing and captures source submission in the
browser, so it does not claim to test the PDF extraction backend. Backend extraction
and stored evidence are covered by the Python/API suite.

The audit fails for any reported WCAG 2.1 A/AA violation, JavaScript exception,
missing import notice or missing notice description, broken Escape dismissal, or
horizontal overflow in the mobile import dialog. A separate deliberately broken
page must produce the known `image-alt` violation before the app is audited. This
negative probe checks that the detector is active; it does not add a finding to
the app or alter source evidence.

`axe-core` and Playwright are **development-only** npm dependencies. The Python
application imports neither, and their installation adds no database table or
runtime dependency. Browser checks run against a throwaway local synthetic demo;
the helper refuses other hosts and non-demo instances. It changes the demo
owner's view preference while exercising the UI.

## Run locally

```sh
npm ci --ignore-scripts
npx --no-install playwright install chromium
.venv/bin/python -m compass --demo --db /tmp/compass-a11y.sqlite3 --port 8765
# In another terminal:
npm run check:ui -- --url http://127.0.0.1:8765
npm run check:import-ui -- --url http://127.0.0.1:8765
npm run check:review-ui -- --url http://127.0.0.1:8765
```

For a system-installed browser, append `--chromium /usr/bin/chromium`. The existing
`python3 scripts/check_ui.py` entry point forwards the same options to Node; it
does not require Python Playwright. An alternate local `--axe-script` is allowed
for development, but CI uses the locked package. The script injects axe only into
its test browser context; the application's Content Security Policy is unchanged.

The JSON report is written to `test-results/accessibility.json`, including failures
and axe `incomplete` checks. CI retains that report for 14 days. Incomplete checks
remain visible for human review and are not counted as passes.
The separate import report is `test-results/import-ui.json` and has the same
retention. Nine accessibility states and eight import regressions are different
checks; neither count is a claim about overall legal or accessibility correctness.

The seven-check review workflow uses a separate synthetic demo office and real
UI actions: an audited permission grant, immutable source verification, creation
of external-gap/internal-conflict/absence findings, refusal of an unconfirmed
absence, attributed decisions and pinned exports. It writes throwaway synthetic
records and retains `test-results/review-ui.json`. These are implementation tests,
not real agency appointments, verified law or policy approvals.

CI also records the [evaluation](EVALUATION.md) runner's status. Until independent
labels and adjudication exist, its baseline gate is explicitly pending and its
accuracy metrics are null. Once a valid adjudicated baseline is supplied, the
same command enforces its severe-miss regression gate. A pending evaluation is not
reported as a measured accuracy pass.

## What still needs human review

Zero automated violations is not WCAG conformance. Review incomplete color/name
checks, keyboard access and focus order, screen-reader announcements, reading and
zoom behavior, meaningful content/labels, and the full working review flow with
each agency. A real accessibility issue in those checks triggers a targeted fix
and regression case. The nine-state audit is deliberately small; expand it when
a supplied task introduces another critical interaction, rather than building a
generic page-testing framework.
