# Evaluation: prepared corpus, human labels pending

V-1's first corpus contains **150 real extracted candidate sentences from all seven
preserved Georgia instrument PDFs**. It uses the same `pypdf==7.0.0` extraction as
R-1, preserving the original file SHA-256, PDF page, exact zero-based page/source
character spans and neighboring context. Originals remain untouched. Segmentation
is explicitly unreviewed; a person must approve each unit against the PDF before
it can enter scored results.

[Corpus](../tests/evaluation/corpus.json) selection is deterministic, stratified by
source, provisional instrument tier and modal-wording bucket. These selection
buckets are not gold labels. They deliberately represent rare prohibition forms;
metrics will describe this stratified set, not the prevalence of errors in all
policy text. Sources with no verified current status/dates retain `unknown`/null.
The SS-25-001 filename has a PS-25-001 header, so its policy sampling tier is
provisional and does not establish binding force.

The [protocol](../tests/evaluation/protocol.json) defines the labels and four severe
misses **before labeling**: missed prohibition, missed scope-changing exception,
future rule reported as current, and nonbinding source reported as binding. A review
candidate with unknown applicability is not itself a current or binding claim.

## Agency work required before scoring

Each participating agency appoints two independent labelers and a distinct third
adjudicator. None is currently recorded. Give the first two people the corpus,
original PDFs, context and their own blank template. Keep model predictions and
the other person's work hidden until both independent submissions are complete.

1. Fill [labeler A](../tests/evaluation/labeler-a.json) and
   [labeler B](../tests/evaluation/labeler-b.json) independently. Record actual
   person IDs and timezone-bearing completion timestamps. Set the independence
   attestation only if the work was independent.
2. Approve segmentation against the original PDF. A false segmentation flag blocks
   scoring until a new versioned corpus corrects the unit; do not discard difficult
   cases or silently change labels' corpus hashes.
3. Label obligation wording, exact actor, prohibition/permission/advice, condition,
   exception and whether an exception changes scope. Use `actor: ""` for no stated
   actor; null means pending. Keep surface wording separate from legal force.
4. Label temporal/binding status only to the extent actually supported by scoped
   primary material; `unknown` is valid. Record supporting checks and uncertainties
   in notes. The tool does not appoint counsel or make that determination.
5. The third person compares both completed submissions and fills
   [adjudication](../tests/evaluation/adjudication.json) for every case, recording
   their own ID and actual completion timestamp. All three IDs must be distinct.

## Run and interpret results

```sh
.venv/bin/python scripts/evaluate_rules.py \
  --baseline tests/evaluation/baseline.json \
  --output /tmp/compass-evaluation.json
```

Currently the report says `awaiting_independent_labels`; metrics, agreement and
severe-miss totals are **null**, not zero or 100% accurate. The normal command
validates provenance, creates predictions in memory and makes the pending state
visible in CI without inventing a passing accuracy claim. The stricter command
refuses to pass until genuine independent work is complete:

```sh
.venv/bin/python scripts/evaluate_rules.py --require-adjudication
```

Predictions analyze the full extracted source, preserving the engine’s actual
neighboring-context handling; character overlap maps each result to its sampled
sentence. The reproducible review-as-of date is 2026-07-27. This does not establish
current law.

Once adjudication is complete, the report contains per-check precision/recall for
obligation, prohibition, permission, advice, condition and exception; actor token
precision/recall/F1 and exact token match; categorical agreement and Cohen's kappa
between independent labelers; and a **separate** severe-miss count with case IDs. Condition/exception metrics
measure presence; they do not certify correct legal interpretation of every
qualifier or exact extraction of its full scope.
Severe occurrences and distinct affected cases are both reported. Unknown temporal
and binding cases are counted separately, so missing legal context cannot become
successful legal-status detection. Undefined metric denominators remain null.

The [committed baseline](../tests/evaluation/baseline.json) records the engine
version and the current pending state. After actual adjudication, review and
commit an evaluated report as the baseline. The gate requires identical corpus and
label-set fingerprints and fails if any severe category or distinct severe-case
count increases. Engine changes rerun this command in CI. A changed corpus or
label set requires explicit, reviewed versioned rebaselining; an evaluated baseline
cannot be compared to missing labels.

Synthetic toy annotations in `tests/test_evaluation.py` test the scorer and refusal
paths. They are clearly marked test-only and supply no accuracy evidence for the
real Georgia corpus.

## Regenerate without overwriting human work

```sh
.venv/bin/python scripts/prepare_evaluation.py \
  --output-directory /tmp/compass-evaluation-next-version
```

Preparation refuses an output directory that already contains a corpus or label
file. Retain the previous version and its human work. Regeneration uses R-1's
existing dependency and adds no table or runtime dependency.

V-1's completed labels, V-2's real precision/recall/agreement, and its numerical
severe-miss baseline remain pending the three agency-appointed people. The trigger
is receipt of their independent submissions and adjudication, including needed
source-status context. The scaffolding and CI gate do not fulfill that human work.
