"""Schema, source derivation and pending-review guards for the draft method."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from xml.etree import ElementTree
from zipfile import ZipFile

from compass.catalogue import catalogue_hash, load_catalogue, validate_catalogue, vague_terms


ROOT = Path(__file__).resolve().parents[1]


def word_text(path):
    with ZipFile(path) as archive:
        document = ElementTree.fromstring(archive.read("word/document.xml"))
    return "\n".join("".join(paragraph.itertext()) for paragraph in document.iter(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"))


class MethodCatalogueTests(unittest.TestCase):
    def setUp(self):
        self.catalogue = load_catalogue()

    def refuse_change(self, change, message):
        value = deepcopy(self.catalogue)
        change(value)
        with self.assertRaisesRegex(ValueError, message):
            validate_catalogue(value)

    def test_one_versioned_draft_has_explicit_manual_coverage_boundary(self):
        value = self.catalogue
        self.assertEqual(value["catalogue_version"], "0.1.0-draft")
        self.assertEqual(value["policy_review_status"], "draft")
        self.assertEqual(value["agency_reviews"], [])
        self.assertEqual(value["coverage_review"]["execution"], "manual_only_pending_agency_review")
        self.assertIs(value["coverage_review"]["automatic_semantic_classification"], False)
        self.assertEqual(value["coverage_review"]["absence_scope"], "declared_corpus_only")
        self.assertIs(value["priority_rubric"]["numeric_product"], False)
        self.assertIs(value["audience_review"]["estimate_is_advisory"], True)

    def test_diagnostics_coverage_and_patterns_derive_from_actual_word_snapshot(self):
        source = self.catalogue["provenance"][0]
        text = word_text(ROOT / source["path"])
        defect_section = text.split("4.1 Defect classes.", 1)[1].split("PART 4A", 1)[0]
        coherence_section = text.split("PART 4A", 1)[1].split("PART 4.2", 1)[0]
        coverage_section = text.split("PART 4.2", 1)[1].split("4.3 Prioritization.", 1)[0]
        pattern_section = text.split("APPENDIX B — RECURRING", 1)[1].split("END OF PROMPT", 1)[0]
        self.assertEqual(set(re.findall(r"\bD[1-9]\b", defect_section)), {r["id"] for r in self.catalogue["defect_classes"]})
        self.assertEqual(set(re.findall(r"\bC[1-7]\b", coherence_section)), {r["id"] for r in self.catalogue["coherence_checks"]})
        original_elements = set(re.findall(r"\s{2,}([a-z]{1,2}\d?)\.\s", coverage_section))
        adapted_elements = [element["id"] for domain in self.catalogue["coverage_domains"] for element in domain["elements"]]
        self.assertEqual(original_elements, set(adapted_elements))
        self.assertEqual(len(adapted_elements), 50)
        self.assertEqual(len(self.catalogue["coverage_domains"]), 7)
        self.assertIn("k2", adapted_elements)
        self.assertEqual({int(n) for n in re.findall(r"\s(\d{1,2})\.\s", pattern_section)}, set(range(1, 23)))
        self.assertEqual(len(self.catalogue["recurring_patterns"]), 22)

    def test_every_coverage_element_has_explicit_topic_description_and_hints(self):
        for domain in self.catalogue["coverage_domains"]:
            for element in domain["elements"]:
                with self.subTest(element=element["id"]):
                    self.assertTrue(element["topic"])
                    self.assertTrue(element["description"])
                    self.assertIn(len(element["indicative_phrasings"]), (2, 3))
                    self.assertTrue(element["evidence_required"])
        self.refuse_change(lambda v: v["coverage_domains"][0]["elements"][0]["indicative_phrasings"].pop(), "two or three")
        self.refuse_change(lambda v: v["coverage_domains"][0]["elements"][0].update(indicative_phrasings=["same", "same"]), "duplicates")

    def test_provenance_keys_match_originals_without_modifying_them(self):
        for source in self.catalogue["provenance"]:
            with self.subTest(path=source["path"]):
                self.assertEqual(hashlib.sha256((ROOT / source["path"]).read_bytes()).hexdigest(), source["sha256"])
                self.assertTrue(source["sections"])

    def test_all_six_prompt_versions_match_their_catalogue_entries(self):
        for prompt in self.catalogue["prompts"]:
            with self.subTest(prompt=prompt["id"]):
                path = ROOT / "method" / prompt["path"]
                self.assertEqual(path.name.split("-", 1)[0], prompt["id"])
                text = path.read_text()
                version = re.search(r"^\*\*Method version:\*\* `([^`]+)`$", text, re.M)
                review = re.search(r"^\*\*Policy review status:\*\* ([^\n]+)$", text, re.M)
                self.assertIsNotNone(version)
                self.assertEqual(version.group(1), prompt["version"])
                self.assertIsNotNone(review)
                self.assertTrue(review.group(1).startswith("draft — agency review pending"))

    def test_language_rules_are_versioned_and_refuse_unsupported_duty_wording(self):
        rules = {rule["id"]: rule for rule in self.catalogue["language_rules"]}
        self.assertEqual(set(rules), {"LR1", "LR2"})
        self.assertTrue(all(rule["version"] == "0.1.0-draft" for rule in rules.values()))
        self.assertIs(rules["LR1"]["valid_local_instruments_may_bind"], True)
        self.assertIs(rules["LR2"]["bill_creates_duty"], False)
        self.refuse_change(lambda v: v["language_rules"][0]["required_basis"].remove("in_force"), "mandatory wording requires")
        self.refuse_change(lambda v: v["language_rules"][0].update(valid_local_instruments_may_bind=False), "valid local binding instruments")
        self.refuse_change(lambda v: v["language_rules"][1].update(bill_creates_duty=True), "bill never")
        self.refuse_change(lambda v: v["language_rules"].pop(), "preserve LR1 and LR2")

    def test_rubric_uses_requested_method_root_path(self):
        self.assertEqual(self.catalogue["priority_rubric"]["path"], "priority-rubric.md")
        self.assertTrue((ROOT / "method" / self.catalogue["priority_rubric"]["path"]).is_file())
        self.assertFalse((ROOT / "method/templates/priority-rubric.md").exists())

    def test_no_template_supplies_an_actual_agency_or_adversarial_approval(self):
        intake = (ROOT / "method/templates/jurisdiction-intake.md").read_text()
        outline = (ROOT / "method/templates/amendment-package.md").read_text()
        confirmation = re.search(r"Policy-owner confirmation: \*\*([^*]+)\*\*", intake)
        adversarial = re.search(r"Adversarial-review outcome: \*\*([^*]+)\*\*", outline)
        self.assertEqual(confirmation.group(1), "not recorded")
        self.assertEqual(adversarial.group(1), "not performed / pending")
        self.assertIs(self.catalogue["audience_review"]["adversarial_reader_required"], True)

    def test_vague_terms_are_validated_literal_advisory_phrases(self):
        terms = vague_terms(self.catalogue)
        self.assertIsInstance(terms, tuple)
        self.assertIn("robust", terms)
        self.assertIn("to the extent practicable", terms)
        changed = deepcopy(self.catalogue)
        changed["vague_terms"].append("a+b")
        literal = re.compile("|".join(re.escape(term) for term in vague_terms(changed)))
        self.assertIsNotNone(literal.search("a+b"))
        self.assertIsNone(literal.fullmatch("aaab"))
        self.refuse_change(lambda v: v["vague_terms"].append("ROBUST"), "duplicates")
        self.refuse_change(lambda v: v["vague_terms"].append(""), "nonempty text")
        self.refuse_change(lambda v: v["vague_terms"].append("line\nbreak"), "short literal phrases")

    def test_missing_duplicate_or_unknown_doctrine_ids_are_refused(self):
        self.refuse_change(lambda v: v["defect_classes"].pop(), "missing, duplicate or unknown IDs")
        self.refuse_change(lambda v: v["coherence_checks"].append(deepcopy(v["coherence_checks"][0])), "missing, duplicate or unknown IDs")
        self.refuse_change(lambda v: v["recurring_patterns"][0]["defect_class_ids"].append("D99"), "unknown defect class")
        self.refuse_change(lambda v: v["coverage_domains"][1]["elements"].pop(3), "coverage elements must preserve")
        self.refuse_change(lambda v: v["coverage_domains"][0]["elements"].append(deepcopy(v["coverage_domains"][1]["elements"][0])), "duplicate coverage element")

    def test_review_claim_needs_actual_attribution_and_valid_date(self):
        self.refuse_change(lambda v: v.update(policy_review_status="approved"), "policy_review_status")
        self.refuse_change(lambda v: v.update(policy_review_status=[]), "policy_review_status")
        self.refuse_change(lambda v: v.update(policy_review_status="agency_reviewed"), "attributed agency reviews")
        value = deepcopy(self.catalogue)
        value["agency_reviews"] = [{"agency_id": "synthetic-agency", "reviewer": "Synthetic test reviewer", "reviewed_on": "2026-11-07", "rationale": "Synthetic test record, not a real approval"}]
        value["policy_review_status"] = "agency_reviewed"
        self.assertIs(validate_catalogue(value), value)
        value["agency_reviews"][0]["reviewed_on"] = "not checked"
        with self.assertRaisesRegex(ValueError, "ISO 8601"):
            validate_catalogue(value)

    def test_schema_cannot_activate_semantic_coverage_or_erase_unknown(self):
        self.refuse_change(lambda v: v["coverage_review"].update(automatic_semantic_classification=True), "scoped, evidenced and manual")
        self.refuse_change(lambda v: v["coverage_review"].update(require_evidence=False), "scoped, evidenced and manual")
        self.refuse_change(lambda v: v["coverage_review"].update(absence_scope="all_law"), "scoped, evidenced and manual")
        self.refuse_change(lambda v: v["coverage_review"]["statuses"].remove("unknown"), "preserve unknown")
        self.refuse_change(lambda v: v["priority_rubric"].update(numeric_product=True), "does not multiply")
        self.refuse_change(lambda v: v["audience_review"].update(estimate_is_advisory=False), "advisory estimates")

    def test_scope_and_example_status_do_not_manufacture_authority(self):
        self.assertEqual(set(self.catalogue["scope"]["primary"]), {"US-FED", "US-STATES", "US-DC"})
        self.assertEqual({example["verification_status"] for example in self.catalogue["illustrative_federal_examples"]}, {"unverified"})
        self.refuse_change(lambda v: v["scope"].update(foreign_context="presumed_binding"), "foreign context")
        self.refuse_change(lambda v: v["illustrative_federal_examples"][0].update(verification_status="verified"), "pretend verification")

    def test_unknown_schema_fields_versions_and_unsafe_paths_are_refused(self):
        self.refuse_change(lambda v: v.update(schema_version=2), "unsupported schema_version")
        self.refuse_change(lambda v: v.update(schema_version=True), "unsupported schema_version")
        self.refuse_change(lambda v: v.update(catalogue_verison="typo"), "unknown fields")
        self.refuse_change(lambda v: v["prompts"][0].update(version=""), "nonempty text")
        self.refuse_change(lambda v: v["prompts"][0].update(path="../outside.md"), "parent traversal")
        self.refuse_change(lambda v: v["prompts"][0].update(id="06"), "unique 01-06")

    def test_json_subset_reader_refuses_duplicate_keys_and_missing_files(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "catalogue.yaml"
            path.write_text('{"schema_version":1,"schema_version":1}')
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                load_catalogue(path)
            path.write_text("schema_version: 1\n")
            with self.assertRaises(ValueError):
                load_catalogue(path)
            path.unlink()
            with self.assertRaises(FileNotFoundError):
                load_catalogue(path)

    def test_content_hash_ignores_formatting_but_tracks_method_content(self):
        serialized = json.dumps(self.catalogue, sort_keys=False, indent=4)
        self.assertEqual(catalogue_hash(json.loads(serialized)), catalogue_hash(self.catalogue))
        changed = deepcopy(self.catalogue)
        changed["vague_terms"].append("suitably")
        self.assertNotEqual(catalogue_hash(changed), catalogue_hash(self.catalogue))


if __name__ == "__main__":
    unittest.main()
