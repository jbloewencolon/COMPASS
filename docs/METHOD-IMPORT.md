# Import BASE-1 as suggestions

Ticket I-1 supports the one supplied Georgia method producer. The source is the
`1 Active Findings` sheet of the preserved governance register, checked against
the BASE-1 baseline and both original SHA-256 values. The converter reads XLSX ZIP
and XML with the Python standard library; it installs no spreadsheet dependency.
It never reads the workbook's worked acceptance/decision examples as decisions.

```sh
python3 scripts/import_method_findings.py
```

This regenerates
[`data/method-import/georgia-base-1-suggestions.json`](../data/method-import/georgia-base-1-suggestions.json).
All 35 original IDs (`BASE-2026-01-F01` through `F35`) are retained. App IDs remain
separate. Each finding carries `origin: method_run`, the method run `BASE-1`, and
workbook/baseline paths and hashes through the import envelope. The workspace run
receiving the suggestions is a separate run; this does not pretend that an app
review occurred on the baseline's historical date.

The original row number, source fields, cached scoring values and formula text
remain under `method_record`. Historical evidence tier E1 is source data, not
verification. Historical owners are not app assignments; historical scores are not
recomputed or adopted as the new priority rubric.

## Evidence and acceptance

The workbook gives finding descriptions and instrument locators, not the exact
quotations and complete current search scope needed by D-1. **All 35 imports are
pending suggestions with explicit evidence gaps.** No quotation, applicability,
current-law verification, corpus-completeness confirmation, reviewer or decision
is invented. The imported text may repeat historical legal premises affected by
[Georgia errata](../case-studies/georgia/ERRATA.md); preservation is not endorsement.

The provisional mapping records F01 as `absence`, F02 as `internal_conflict`, and
F04 as `external_gap`. Other mappings are review aids. The JSON import report lists
every incomplete or potentially mixed finding and explains what evidence remains
to be supplied. This report does not claim that three evidence types are proven
sufficient or that a fourth type is needed; real evidence must answer that.

Use the app's ordinary finding workflow to create an evidenced finding from a
suggestion, retaining its original reference. A suggestion with gaps cannot be
accepted merely by changing an applicability label. Preserve the imported record
and later recorded decisions; never rewrite the original workbook or baseline.

## Authenticated workspace import

After signing into the local app and creating a review with the actual pinned
instrument sources, import the generated bundle through
`POST /api/runs/{run_id}/method-findings`. The route uses the current workspace and
must reject another workspace's run. A repeat import preserves existing records
instead of duplicating IDs or overwriting later work.

The helper can submit to that route using an explicitly supplied Netscape/Mozilla
cookie jar from the signed-in development session:

```sh
python3 scripts/import_method_findings.py --post-run WORKSPACE-RUN-ID \
  --cookie-file /private/path/local-session.cookies
```

Session values are not command-line arguments and are never printed. The script
does not create a session or bypass app authentication. Keep session files outside
version control. Without `--post-run`, the helper only generates validated JSON.

The validator refuses forged acceptance/applicability, duplicate or omitted IDs,
unknown source paths, wrong hashes, changed source rows and invented quotations.
It returns the canonical original bundle rather than trusting an input report.

## Boundary and trigger

There is no generic exchange protocol, producer registry or new table. A second
real finding producer is the trigger to revisit this adapter. Replacing BASE-1
with a later original requires an explicit reviewed adapter/baseline update;
silently changing the source bytes is refused. Completing agency evidence and
review is the trigger for replacing pending suggestions with evidenced findings.
