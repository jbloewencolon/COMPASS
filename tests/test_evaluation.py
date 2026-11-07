"""Evaluation tests use synthetic toy labels; they are not real accuracy results."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from compass.analysis import ENGINE_VERSION
from compass.pdf_import import extract_pdf
from scripts.evaluate_rules import check_baseline, evaluate, fingerprint, predict, validate_corpus, validate_labels
from scripts.prepare_evaluation import label_template, select_cases, write_new

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests/evaluation"


def toy_corpus():
    return {"schema_version": 1, "corpus_id": "synthetic-test-only", "corpus_kind": "synthetic_test", "cases": [
        {"case_id": "toy-a", "text": "The office must not publish records unless the owner approves."},
        {"case_id": "toy-b", "text": "The office may publish a summary if the owner approves."},
    ]}


def completed_documents(corpus):
    documents = [label_template(corpus, role) for role in ("labeler_a", "labeler_b", "adjudicator")]
    for index, document in enumerate(documents):
        document.update(person_id=f"toy-reviewer-{index}", completed_at="2026-11-06T12:00:00-05:00", independently_completed=index != 2)
        for row in document["labels"]:
            first = row["case_id"] == "toy-a"
            row.update(segmentation_approved=True, obligation_present=first, actor="The office", modality="prohibition" if first else "permission", condition_present=not first, exception_present=first, scope_changing_exception=first, temporal_status="unknown", binding_status="unknown")
    return documents


class EvaluationTests(unittest.TestCase):
    def test_real_corpus_has_150_exact_pdf_excerpts_and_no_human_labels(self):
        corpus = json.loads((DATA / "corpus.json").read_text())
        validate_corpus(corpus, ROOT)
        self.assertEqual(len(corpus["cases"]), 150)
        self.assertEqual(len(corpus["sources"]), 7)
        by_source = {source["source"]: extract_pdf((ROOT / source["source"]).read_bytes()) for source in corpus["sources"]}
        for case in corpus["cases"]:
            extracted = by_source[case["source"]]
            self.assertEqual(extracted["text"][case["source_char_start"]:case["source_char_end"]], case["text"])
            span = next(span for span in extracted["page_spans"] if span["page"] == case["page"])
            self.assertEqual(case["source_char_start"], span["start"] + case["page_char_start"])
            self.assertEqual(case["legal_status"], "unknown")
            self.assertEqual(case["segmentation_status"], "unreviewed")
        documents = [json.loads((DATA / name).read_text()) for name in ("labeler-a.json", "labeler-b.json", "adjudication.json")]
        report = evaluate(corpus, documents)
        self.assertEqual(report["status"], "awaiting_independent_labels")
        self.assertEqual(report["prediction_count"], 150)
        self.assertIsNone(report["metrics"])
        self.assertIsNone(report["severe_misses"])
        self.assertEqual(report["engine_version"], ENGINE_VERSION)

    def test_pending_labels_cannot_be_promoted_to_an_evaluated_baseline(self):
        corpus = toy_corpus()
        documents = [label_template(corpus, role) for role in ("labeler_a", "labeler_b", "adjudicator")]
        with self.assertRaisesRegex(ValueError, "pending"):
            evaluate(corpus, documents, require_adjudication=True)
        evaluated = evaluate(corpus, completed_documents(corpus))
        with self.assertRaisesRegex(ValueError, "same completed"):
            check_baseline(evaluate(corpus, documents), evaluated)

    def test_toy_precision_recall_actor_agreement_and_zero_severe_misses(self):
        corpus = toy_corpus()
        report = evaluate(corpus, completed_documents(corpus), require_adjudication=True)
        self.assertEqual(report["status"], "evaluated")
        self.assertEqual(report["metrics"]["prohibition"]["recall"], 1)
        self.assertEqual(report["metrics"]["permission"]["precision"], 1)
        self.assertEqual(report["metrics"]["actor"]["token_f1"], 1)
        self.assertEqual(report["interrater_agreement"]["modality"]["cohen_kappa"], 1)
        self.assertEqual(report["severe_misses"]["distinct_cases"], 0)
        self.assertEqual(report["severe_misses"]["binding_unknown_cases"], 2)
        self.assertEqual(check_baseline(report, report), "no_severe_increase")

    def test_severe_miss_increase_fails_the_baseline_gate(self):
        corpus = toy_corpus()
        documents = completed_documents(corpus)
        baseline = evaluate(corpus, documents)
        predictions = predict(corpus)
        predictions["toy-a"].update(modality="obligation", exception_present=False)
        result = evaluate(corpus, documents, predictions=predictions)
        self.assertEqual(result["severe_misses"]["distinct_cases"], 1)
        self.assertEqual(result["severe_misses"]["occurrences"], 2)
        self.assertEqual(result["metrics"]["prohibition"]["recall"], 0)
        with self.assertRaisesRegex(ValueError, "Severe misses increased"):
            check_baseline(result, baseline)

    def test_future_and_nonbinding_claims_are_separate_severe_categories(self):
        corpus = toy_corpus()
        documents = completed_documents(corpus)
        for document in documents:
            document["labels"][0].update(temporal_status="future", binding_status="nonbinding")
        predictions = predict(corpus)
        predictions["toy-a"].update(current_rule_claim=True, binding_claim=True)
        report = evaluate(corpus, documents, predictions=predictions)
        self.assertEqual(report["severe_misses"]["by_category"]["future_reported_current"], 1)
        self.assertEqual(report["severe_misses"]["by_category"]["nonbinding_reported_binding"], 1)
        self.assertEqual(report["severe_misses"]["distinct_cases"], 1)

    def test_same_person_cannot_label_and_adjudicate(self):
        corpus = toy_corpus()
        documents = completed_documents(corpus)
        documents[2]["person_id"] = documents[0]["person_id"]
        with self.assertRaisesRegex(ValueError, "three distinct people"):
            evaluate(corpus, documents)
        documents = completed_documents(corpus)
        documents[0]["independently_completed"] = False
        with self.assertRaisesRegex(ValueError, "pending"):
            evaluate(corpus, documents, require_adjudication=True)

    def test_bad_label_ids_values_or_corpus_identity_are_refused(self):
        corpus = toy_corpus()
        valid = completed_documents(corpus)[0]
        for mutate in (
            lambda document: document.update(corpus_sha256="0" * 64),
            lambda document: document["labels"].pop(),
            lambda document: document["labels"][0].update(modality="binding"),
            lambda document: document["labels"][0].update(modality=["prohibition"]),
            lambda document: document.update(completed_at=True),
            lambda document: document["labels"][0].update(exception_present=False),
            lambda document: document["labels"][0].update(condition_present="false"),
        ):
            document = deepcopy(valid)
            mutate(document)
            with self.subTest(document=document), self.assertRaises(ValueError):
                validate_labels(document, corpus, "labeler_a")

    def test_segmentation_or_missing_adjudication_blocks_scoring(self):
        corpus = toy_corpus()
        documents = completed_documents(corpus)
        documents[2]["labels"][0]["segmentation_approved"] = False
        report = evaluate(corpus, documents)
        self.assertIsNone(report["metrics"])
        self.assertEqual(report["completed_labels"]["adjudicator"], 1)
        with self.assertRaisesRegex(ValueError, "Two label files"):
            evaluate(corpus, documents[:2])

    def test_changed_corpus_or_labels_cannot_reuse_an_old_baseline(self):
        corpus = toy_corpus()
        documents = completed_documents(corpus)
        baseline = evaluate(corpus, documents)
        result = deepcopy(baseline)
        result["corpus_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "corpus differs"):
            check_baseline(result, baseline)
        result = deepcopy(baseline)
        result["label_set_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "same completed"):
            check_baseline(result, baseline)

    def test_unknown_baseline_status_cannot_disable_the_gate(self):
        corpus = toy_corpus()
        result = evaluate(corpus, completed_documents(corpus))
        baseline = deepcopy(result)
        baseline["status"] = "ignored"
        with self.assertRaisesRegex(ValueError, "Unknown baseline status"):
            check_baseline(result, baseline)

    def test_preparation_refuses_to_overwrite_existing_human_work(self):
        corpus = toy_corpus()
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            write_new(corpus, directory)
            before = (directory / "labeler-a.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
                write_new(corpus, directory)
            self.assertEqual((directory / "labeler-a.json").read_bytes(), before)
        with self.assertRaisesRegex(ValueError, "Only 0 eligible"):
            select_cases([], 150)

    def test_corrupt_provenance_and_duplicate_cases_are_refused(self):
        corpus = json.loads((DATA / "corpus.json").read_text())
        corpus["cases"][0]["original_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "provenance"):
            validate_corpus(corpus)
        corpus = toy_corpus()
        corpus["cases"][1]["case_id"] = corpus["cases"][0]["case_id"]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_corpus(corpus)


if __name__ == "__main__":
    unittest.main()
