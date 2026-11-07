"""Milestone 1 surface-language regressions, with explicit fixture provenance.

Citation recognition is not verification of law. The twenty designed citation
contexts are synthetic; eight supplementary lines came from uploaded PDFs.
"""

import hashlib
import json
from pathlib import Path
import re
import unittest

from compass.analysis import _sentences, analyze


GA_PROFILE = {
    "jurisdiction_id": "US-GA",
    "citation_patterns": [r"\b[A-Z]{1,8}-\d{2,4}-\d{2,6}(?:-[A-Z0-9]+)?\b",
                          r"\bO\.C\.G\.A\.?\s*§?\s*\d+-\d+-\d+(?:\s*\([A-Za-z0-9]+\))*"],
}
FIXTURE = Path(__file__).parent / "fixtures" / "text_rules_citations.json"


def source(text, source_id="policy", **changes):
    record = {"id": source_id, "title": "Synthetic policy excerpt", "kind": "instrument", "jurisdiction_id": "US-GA",
              "version": "1", "text": text, "created_at": "2026-11-03T12:00:00+00:00", "source_key": None,
              "reference_keys": [], "authority_type": "internal_policy", "legal_status": "unknown"}
    return {**record, **changes}


class TextRuleTests(unittest.TestCase):
    def report(self, values, profile=None, jurisdiction="US-GA"):
        return analyze(values, [], {"advanced_analysis": True}, {}, "2026-11-03", [], [], jurisdiction, profile=profile)

    def items(self, report, feature):
        return report["features"][feature]["items"]

    def assert_exact_offsets(self, quote, text):
        match = re.search(r"characters (\d+)–(\d+)$", quote["location"])
        self.assertIsNotNone(match, quote["location"])
        start, end = map(int, match.groups())
        self.assertEqual(text[start - 1:end], quote["quote"])

    def test_immediate_negative_modals_are_prohibition_review_candidates(self):
        cases = ["may not", "shall not", "must not", "will not", "is prohibited from", "are prohibited from"]
        for phrase in cases:
            with self.subTest(phrase=phrase):
                item = source(f"The office {phrase} deploy an unreviewed system.")
                candidate = self.items(self.report([item]), "obligations")[0]
                self.assertEqual(candidate["data"]["candidate_type"], "prohibition_wording")
                self.assertEqual(candidate["severity"], "review")
                self.assertTrue(candidate["data"]["negated_or_prohibited"])
                self.assertEqual(candidate["data"]["applicability"], "unknown")
                self.assert_exact_offsets(candidate["evidence"][0], item["text"])

    def test_later_not_does_not_turn_permission_into_prohibition(self):
        item = source("The office may review records that are not confidential.")
        candidate = self.items(self.report([item]), "obligations")[0]
        self.assertEqual(candidate["data"]["candidate_type"], "permission")
        self.assertEqual(candidate["severity"], "info")
        self.assertFalse(candidate["data"]["negated_or_prohibited"])

    def test_actual_georgia_mixed_modal_and_pii_clauses_remain_prohibition_candidates(self):
        fixture = json.loads(FIXTURE.read_text())
        cases = fixture["uploaded_georgia_obligation_cases"]
        self.assertEqual(len(cases), 2)
        root = Path(__file__).resolve().parents[1]
        mixed = next(row for row in cases if "may consult" in row["text"])
        self.assertEqual(mixed["page"], 2)
        self.assertIn("it may not", mixed["text"])
        for row in cases:
            with self.subTest(source=row["source"]):
                self.assertEqual(hashlib.sha256((root / row["source"]).read_bytes()).hexdigest(), row["sha256"])
                candidate = self.items(self.report([source(row["text"])]), "obligations")[0]
                self.assertEqual(candidate["data"]["candidate_type"], "prohibition_wording")
                self.assertEqual(candidate["severity"], "review")
                self.assertTrue(candidate["data"]["negated_or_prohibited"])
                self.assertTrue(candidate["data"]["action"].startswith("not "))
                self.assertEqual(candidate["data"]["applicability"], "unknown")
                self.assertEqual(candidate["evidence"][0]["quote"], row["text"])
                self.assert_exact_offsets(candidate["evidence"][0], row["text"])

    def test_additional_drafting_forms_are_explicitly_weaker_evidence(self):
        cases = {"will": "commitment_wording", "is responsible for": "responsibility_wording",
                 "are responsible for": "responsibility_wording", "is to": "drafting_wording", "are to": "drafting_wording"}
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                candidate = self.items(self.report([source(f"The office {phrase} review inventory.")]), "obligations")[0]
                self.assertEqual(candidate["data"]["candidate_type"], expected)
                self.assertEqual(candidate["data"]["wording_evidence"], "weaker_candidate")
                self.assertEqual(candidate["data"]["applicability"], "unknown")
        advisory = self.items(self.report([source("The office should review inventory.")]), "obligations")[0]
        self.assertEqual(advisory["data"]["candidate_type"], "advisory_wording")

    def test_abbreviation_periods_do_not_separate_actor_and_duty(self):
        text = "  Under 42 U.S.C. § 12132 and 28 C.F.R. § 35.130, Acme, Inc. shall review an inventory. The office may publish it."
        sentences = _sentences(source(text))
        self.assertEqual(len(sentences), 2)
        self.assertIn("Acme, Inc. shall", sentences[0][2])
        self.assertEqual(sentences[1][2], "The office may publish it.")
        for start, end, sentence in sentences:
            self.assertEqual(text[start:end], sentence)
        item = self.items(self.report([source(text)]), "obligations")[0]
        self.assertIn("Under 42 U.S.C. § 12132", item["data"]["actor"])
        self.assertIn("Acme, Inc.", item["data"]["actor"])
        self.assert_exact_offsets(item["evidence"][0], text)

    def test_wrapped_citation_and_modal_phrases_preserve_original_newlines(self):
        text = "Under 42 U.S.C.\n§ 12132, the office is\nresponsible for maintaining an inventory.\n\nThe office may publish it."
        candidates = self.items(self.report([source(text)]), "obligations")
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["data"]["candidate_type"], "responsibility_wording")
        self.assertIn("U.S.C.\n§", candidates[0]["evidence"][0]["quote"])
        self.assert_exact_offsets(candidates[0]["evidence"][0], text)

    def test_profile_sentence_abbreviation_is_literal_and_extends_defaults(self):
        text = "The Dept. shall review records under 5 U.S.C. § 552. The office may respond."
        profile = {"sentence_abbreviations": ["Dept."]}
        sentences = _sentences(source(text), profile)
        self.assertEqual(len(sentences), 2)
        self.assertEqual(sentences[0][2], "The Dept. shall review records under 5 U.S.C. § 552.")
        candidate = self.items(self.report([source(text)], profile), "obligations")[0]
        self.assertEqual(candidate["data"]["actor"], "The Dept.")
        self.assert_exact_offsets(candidate["evidence"][0], text)

    def test_twenty_designed_us_citation_forms_with_synthetic_context(self):
        fixture = json.loads(FIXTURE.read_text())
        self.assertEqual(len(fixture["designed_cases"]), 20)
        self.assertIn("synthetic", fixture["designed_cases_provenance"]["context"])
        for row in fixture["designed_cases"]:
            with self.subTest(case=row["id"]):
                items = self.items(self.report([source(row["text"])]), "citations")
                match = next((item for item in items if item["data"]["reference"] == row["citation"]), None)
                self.assertIsNotNone(match, items)
                self.assertEqual(match["data"]["citation_type"], row["citation_type"])
                self.assertEqual(match["data"]["verification"], "unverified")
                self.assertIn(row["citation"], match["evidence"][0]["quote"])
                self.assert_exact_offsets(match["evidence"][0], row["text"])

    def test_uploaded_pdf_lines_have_hash_and_page_provenance_and_profile_detection(self):
        fixture = json.loads(FIXTURE.read_text())
        self.assertEqual(len(fixture["uploaded_pdf_cases"]), 8)
        root = Path(__file__).resolve().parents[1]
        for row in fixture["uploaded_pdf_cases"]:
            with self.subTest(source=row["source"], text=row["text"]):
                self.assertGreater(row["page"], 0)
                self.assertEqual(hashlib.sha256((root / row["source"]).read_bytes()).hexdigest(), row["sha256"])
                matches = self.items(self.report([source(row["text"])], GA_PROFILE), "citations")
                self.assertTrue(matches)
                self.assertTrue(any(item["data"]["reference"].startswith("O.C.G.A") for item in matches))
                for item in matches:
                    self.assert_exact_offsets(item["evidence"][0], row["text"])

    def test_georgia_shaped_identifiers_require_explicit_profile_configuration(self):
        item = source("Compare SS-23-002 with PS-23-001 and O.C.G.A. § 50-18-70.")
        self.assertEqual(self.items(self.report([item]), "citations"), [])
        self.assertEqual(len(self.items(self.report([item], GA_PROFILE), "citations")), 3)

    def test_custom_other_state_profile_pattern_detects_different_identifier_shape(self):
        profile = {"jurisdiction_id": "US-CA", "citation_patterns": [r"\bCA-GOV-\d{4}/\d{2}\b", r"\bGov\.\s+Code\s+§\s*\d+(?:\.\d+)?\b"], "sentence_abbreviations": ["Gov."]}
        item = source("Review CA-GOV-2026/07 and Gov. Code § 11546.45 before a decision.", jurisdiction_id="US-CA")
        citations = self.items(self.report([item], profile, "US-CA"), "citations")
        self.assertEqual({item["data"]["reference"] for item in citations}, {"CA-GOV-2026/07", "Gov. Code § 11546.45"})
        self.assertTrue(all(item["data"]["origin"] == "profile_pattern" for item in citations))

    def test_invalid_profile_pattern_warns_and_preserves_federal_defaults(self):
        profile = {"citation_patterns": ["[", None, ""]}
        report = self.report([source("Review 42 U.S.C. § 12132 before a decision.")], profile)
        self.assertEqual(len(self.items(report, "citations")), 1)
        self.assertEqual(len([warning for warning in report["warnings"] if "Invalid profile citation pattern" in warning]), 3)
        self.assertEqual(self.items(report, "citations")[0]["data"]["verification"], "unverified")

    def test_alias_normalization_resolves_abbreviation_and_section_mark_variants(self):
        internal = source("Review 42 USC 12132 before recording a finding.")
        external = source("Preserved external excerpt.", "ada", kind="external", jurisdiction_id="US-FED", source_key="42 U.S.C. § 12132")
        candidate = self.items(self.report([internal, external]), "citations")[0]
        self.assertEqual(candidate["data"]["matched_source_ids"], ["ada"])
        self.assertEqual(candidate["data"]["resolution"], "candidate_match")
        self.assertEqual(candidate["data"]["verification"], "unverified")
        self.assertIn("remain unverified", candidate["detail"])

    def test_decimal_section_dots_are_not_lost_by_normalization(self):
        internal = source("Review 28 CFR 35.130 before recording a finding.")
        different = source("Different section.", "other", kind="external", source_key="28 C.F.R. § 351.30", jurisdiction_id="US-FED")
        correct = source("Correct selected section.", "correct", kind="external", source_key="28 C.F.R. § 35.130", jurisdiction_id="US-FED")
        candidate = self.items(self.report([internal, different, correct]), "citations")[0]
        self.assertEqual(candidate["data"]["matched_source_ids"], ["correct"])

    def test_all_requested_bill_prefixes_are_reference_candidates_without_enactment_claim(self):
        for citation in ("HB 444", "SB 444", "AB 2013", "LB 1", "HF 2", "SF 3", "H.R. 815", "S. 686"):
            with self.subTest(citation=citation):
                item = self.items(self.report([source(f"Review {citation} before a decision.")]), "citations")[0]
                self.assertEqual(item["data"]["reference"], citation)
                self.assertEqual(item["data"]["citation_type"], "bill")
                self.assertIn("does not establish enactment", item["detail"])

    def test_declared_identifier_punctuation_does_not_merge_distinct_records(self):
        internal = source("Read the separate record.", reference_keys=["agency.policy-v1"])
        other = source("Different record.", "other", kind="external", source_key="agencypolicy-v1")
        correct = source("Exact record.", "correct", kind="external", source_key="agency.policy-v1")
        unresolved = self.items(self.report([internal, other]), "citations")[0]
        self.assertEqual(unresolved["data"]["matched_source_ids"], [])
        matched = self.items(self.report([internal, other, correct]), "citations")[0]
        self.assertEqual(matched["data"]["matched_source_ids"], ["correct"])

    def test_court_reporter_abbreviation_is_not_a_senate_bill(self):
        report = self.report([source("Compare 597 U.S. 215 (2022) with S. 686 before review.")])
        citations = self.items(report, "citations")
        self.assertEqual([item["data"]["reference"] for item in citations], ["S. 686"])

    def test_explicit_reference_keys_resolve_without_a_recognition_pattern(self):
        internal = source("Read the separate record before a decision.", reference_keys=["agency/manual-2026"])
        external = source("Preserved source.", "manual", source_key="agency/manual-2026", kind="external")
        item = self.items(self.report([internal, external]), "citations")[0]
        self.assertEqual(item["data"]["matched_source_ids"], ["manual"])
        self.assertEqual(item["data"]["origin"], "declared_metadata")

    def test_expanded_vague_wording_catalogue_produces_advisory_flags(self):
        for phrase in ("rigorous", "robust", "sufficient", "adequate", "best efforts", "as appropriate", "to the extent practicable"):
            with self.subTest(phrase=phrase):
                text = f"The office follows {phrase} review practices."
                items = self.items(self.report([source(text)]), "language")
                self.assertTrue(any(phrase in flag for item in items for flag in item["data"]["flags"]))
                self.assertTrue(all("Advisory" in item["detail"] for item in items))

    def test_foreign_source_actions_and_references_are_retained_and_labeled(self):
        item = source("The provider must review records under 42 U.S.C. § 12132.", "foreign", kind="external", jurisdiction_id="EU")
        report = self.report([item])
        for feature in ("obligations", "citations"):
            candidates = self.items(report, feature)
            self.assertTrue(candidates)
            self.assertEqual(candidates[0]["data"]["context_scope"], "foreign_or_unspecified_context")
            self.assertIn("unassessed", candidates[0]["detail"])
            self.assert_exact_offsets(candidates[0]["evidence"][0], item["text"])

    def test_unknown_us_prefixed_ids_are_context_not_recognized_us_authority(self):
        for jurisdiction in ("US-XX", "US", "US-FEDERAL"):
            with self.subTest(jurisdiction=jurisdiction):
                record = source("The office must review records.", jurisdiction_id=jurisdiction)
                candidate = self.items(self.report([record]), "obligations")[0]
                self.assertEqual(candidate["data"]["jurisdiction_id"], jurisdiction)
                self.assertEqual(candidate["data"]["context_scope"], "foreign_or_unspecified_context")
                self.assertIn("unassessed", candidate["detail"])


if __name__ == "__main__":
    unittest.main()
