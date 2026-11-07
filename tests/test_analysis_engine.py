"""Deterministic analytical aids: evidence, scope, switches and honest limits."""

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from compass.analysis import ADVANCED, FEATURES, analyze


GA_TEST_PROFILE = {"jurisdiction_id": "US-GA", "citation_patterns": [r"\b[A-Z]{1,8}-\d{2,4}-\d{2,6}(?:-[A-Z0-9]+)?\b"]}


def source(source_id="internal", text="The office maintains an AI inventory.", **changes):
    value = {
        "id": source_id, "title": f"Synthetic source {source_id}", "kind": "instrument", "jurisdiction_id": "US-GA",
        "version": "1", "text": text, "created_at": "2026-02-01T12:00:00+00:00", "authority_type": "internal_policy",
        "legal_status": "in_force", "effective_from": "2026-01-01", "effective_to": None,
        "source_key": None, "replaces_source_id": None, "reference_keys": [], "topics": [], "reference_scope": "private",
    }
    value.update(changes)
    return value


class AnalysisEngineTests(unittest.TestCase):
    def report(self, sources=None, history=None, context=None, settings=None, findings=None, audit=None, as_of="2026-02-01"):
        return analyze(sources or [], history or [], settings if settings is not None else {"advanced_analysis": True}, context or {}, as_of, findings or [], audit or [], "US-GA", profile=GA_TEST_PROFILE)

    def items(self, report, feature):
        return report["features"][feature]["items"]

    def assert_real_evidence(self, report, sources):
        registry = {value["id"]: value for value in sources}
        for result in report["features"].values():
            for item in result["items"]:
                for evidence in item["evidence"]:
                    self.assertIn(evidence["source_id"], registry)
                    self.assertIn(evidence["quote"], registry[evidence["source_id"]]["text"])
                    self.assertTrue(evidence["location"].startswith("Line "))

    def test_each_feature_can_be_disabled_and_advanced_master_gates_execution(self):
        sources = [source(text="The office must promptly review AI inventory annually.")]
        enabled = self.report(sources)
        self.assertTrue(self.items(enabled, "obligations"))
        self.assertTrue(self.items(enabled, "language"))
        disabled = self.report(sources, settings={"advanced_analysis": True, "features": {feature: False for feature in FEATURES}})
        for value in disabled["features"].values():
            self.assertFalse(value["enabled"])
            self.assertEqual(value["status"], "disabled")
            self.assertEqual(value["items"], [])
        simple = self.report(sources, settings={"advanced_analysis": False})
        for feature in ADVANCED:
            self.assertFalse(simple["features"][feature]["enabled"])
        self.assertTrue(simple["features"]["obligations"]["enabled"])

    def test_diff_uses_verified_earlier_identity_and_never_future_history(self):
        old = source("old", "The office should review inventory.", source_key="inventory", created_at="2026-01-01T12:00:00Z")
        current = source("current", "The office must review inventory annually.", source_key="inventory")
        future = source("future", "FUTURE SECRET TEXT must never enter this review.", source_key="inventory", created_at="2026-03-01T12:00:00Z")
        report = self.report([current], [old, future])
        changes = self.items(report, "change_detection")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["data"]["previous_source_id"], "old")
        self.assertNotIn("FUTURE SECRET TEXT", json.dumps(report))
        self.assert_real_evidence(report, [old, current])

    def test_identical_text_still_reports_status_and_other_legal_metadata_changes(self):
        text = "The office shall review the inventory annually."
        old = source("old", text, source_key="inventory", created_at="2026-01-01T12:00:00Z",
                     legal_status="adopted_not_effective", effective_from="2026-03-01", effective_to="2027-01-01", authority_type="guidance")
        current = source("current", text, source_key="inventory", effective_from="2026-02-01",
                         authority_type="adopted_standard", adoption_reference="Synthetic adopting instrument, version 2, office scope")
        report = self.report([current], [old])
        changes = self.items(report, "change_detection")
        self.assertEqual(len(changes), 1)
        data = changes[0]["data"]
        self.assertFalse(data["text_changed"])
        self.assertEqual(data["changes"], [])
        self.assertEqual(changes[0]["evidence"], [])
        self.assertEqual(set(data["metadata_changes"]), {"legal_status", "effective_from", "effective_to", "authority_type", "adoption_reference"})
        self.assertEqual(data["metadata_changes"]["legal_status"], {"before": "adopted_not_effective", "after": "in_force"})
        self.assertIn("metadata", data["change_types"])
        self.assertEqual(data["substantive_status"], "unreviewed")

    def test_text_changes_identify_candidate_modal_timing_date_exception_and_definition_edits(self):
        old = source("old", '“AI system” means automated software. The office should review inventory annually by 2026-03-01, except research pilots.',
                     source_key="inventory", created_at="2026-01-01T12:00:00Z")
        current = source("current", '“AI system” means decision software. The office must review inventory monthly by 2026-04-01, except procurement pilots.', source_key="inventory")
        report = self.report([current], [old])
        data = self.items(report, "change_detection")[0]["data"]
        self.assertTrue({"text", "modal", "timing", "date", "exception", "definition"}.issubset(data["change_types"]))
        self.assertEqual(data["substantive_status"], "unreviewed")
        self.assert_real_evidence(report, [old, current])

    def test_same_words_with_formatting_changes_remain_owner_review_candidates(self):
        old = source("old", "The office shall review inventory.\n", source_key="inventory", created_at="2026-01-01T12:00:00Z")
        current = source("current", "THE office   shall review inventory!\n\n", source_key="inventory")
        report = self.report([current], [old])
        item = self.items(report, "change_detection")[0]
        self.assertEqual(item["data"]["change_types"], ["formatting_only"])
        self.assertTrue(item["data"]["text_changed"])
        self.assertEqual(item["data"]["substantive_status"], "unreviewed")
        self.assertIn("owner confirmation", item["detail"])
        self.assert_real_evidence(report, [old, current])

    def test_impact_detects_mapped_changes_when_diff_display_is_disabled(self):
        old = source("old", "The office should review inventory.", source_key="inventory", created_at="2026-01-01T12:00:00Z")
        current = source("current", "The office must review inventory annually.", source_key="inventory")
        context = {"assets": [{"id": "register", "name": "Inventory register", "source_keys": ["inventory"]}]}
        report = self.report([current], [old], context=context, settings={"advanced_analysis": True, "features": {"change_detection": False}})
        self.assertEqual(report["features"]["change_detection"]["status"], "disabled")
        self.assertEqual(self.items(report, "change_detection"), [])
        impact = self.items(report, "impact")[0]
        self.assertEqual(impact["data"]["changed_source_ids"], ["current"])
        self.assertEqual(impact["severity"], "review")
        # A changed date/status is also a mapped change even with identical text.
        current["text"] = old["text"]
        current["legal_status"] = "adopted_not_effective"
        report = self.report([current], [old], context=context, settings={"advanced_analysis": True, "features": {"change_detection": False}})
        self.assertEqual(self.items(report, "impact")[0]["data"]["changed_source_ids"], ["current"])

    def test_retrospective_selected_snapshot_cannot_compare_to_later_version(self):
        current = source("old", "Older pinned text.", source_key="inventory", created_at="2026-01-01T12:00:00Z")
        future = source("new", "Unselected later text.", source_key="inventory", created_at="2026-03-01T12:00:00Z")
        report = self.report([current], [future])
        self.assertEqual(self.items(report, "change_detection"), [])
        self.assertNotIn("Unselected later text", json.dumps(report))
        self.assertEqual(report["features"]["change_detection"]["status"], "needs_input")

    def test_title_similarity_does_not_invent_document_identity(self):
        old = source("old", "Old wording.", title="Same title", created_at="2026-01-01T12:00:00Z")
        current = source("new", "Changed wording.", title="Same title")
        self.assertEqual(self.items(self.report([current], [old]), "change_detection"), [])

    def test_explicit_predecessor_cannot_point_to_future_snapshot(self):
        current = source("old", "Older text.", replaces_source_id="future")
        future = source("future", "Future forbidden text.", created_at="2026-03-01T12:00:00Z")
        report = self.report([current], [future])
        self.assertEqual(self.items(report, "change_detection"), [])
        self.assertNotIn("Future forbidden text", json.dumps(report))

    def test_obligation_candidates_preserve_negation_conditions_and_exceptions(self):
        item = source(text="The office must not deploy an AI system unless review is complete. Except research-only pilots are excluded.")
        report = self.report([item])
        action = self.items(report, "obligations")[0]
        self.assertEqual(action["data"]["actor"], "The office")
        self.assertTrue(action["data"]["negated_or_prohibited"])
        self.assertTrue(action["data"]["exceptions"])
        self.assertEqual(action["data"]["applicability"], "unknown")
        self.assertIn("research-only", json.dumps(action))
        self.assert_real_evidence(report, [item])

    def test_permission_and_conditional_timing_are_not_asserted_as_binding(self):
        text = "The office may publish an inventory. If federal funding applies, the office must review it within 30 days."
        report = self.report([source(text=text)])
        actions = self.items(report, "obligations")
        self.assertEqual(actions[0]["data"]["candidate_type"], "permission")
        self.assertEqual(actions[0]["severity"], "info")
        self.assertTrue(actions[1]["data"]["conditions"])
        self.assertIn("within 30 days", actions[1]["data"]["timing"])

    def test_citation_resolution_distinguishes_missing_corpus_from_invalid_law(self):
        internal = source(text="See SS-23-002 and SS-99-999 for the inventory process.")
        known = source("standard", "Preserved text.", source_key="SS-23-002")
        report = self.report([internal, known])
        references = {item["data"]["reference"]: item for item in self.items(report, "citations")}
        self.assertEqual(references["SS-23-002"]["data"]["resolution"], "candidate_match")
        self.assertEqual(references["SS-99-999"]["data"]["resolution"], "unresolved_in_selected_corpus")
        self.assertEqual(report["summary"]["unresolved_references"], 1)
        self.assertIn("does not establish", references["SS-99-999"]["detail"])
        self.assert_real_evidence(report, [internal, known])

    def test_definition_conflicts_keep_internal_jurisdiction_scope(self):
        first = source("one", '“AI system” means a computational decision tool.')
        second = source("two", '“AI system” means any software system used by the office.')
        foreign = source("foreign", '“AI system” means unrelated foreign wording.', jurisdiction_id="US-CA")
        external = source("external", '“AI system” means an external concept.', kind="external")
        report = self.report([first, second, foreign, external])
        variations = self.items(report, "terminology")
        self.assertEqual(len(variations), 1)
        self.assertEqual(set(variations[0]["source_ids"]), {"one", "two"})
        self.assert_real_evidence(report, [first, second, foreign, external])

    def test_coverage_distinguishes_topic_presence_missing_and_unreviewed(self):
        internal = source("internal", "Inventory and procurement are covered topics.")
        external = source("external", "Inventory reference text.", kind="external")
        report = self.report([internal, external], context={"topics": ["inventory", "procurement", "rights"]})
        matrix = {item["data"]["topic"]: item["data"] for item in self.items(report, "coverage")}
        self.assertEqual(matrix["inventory"]["evidence_state"], "paired_evidence")
        self.assertEqual(matrix["inventory"]["review_state"], "unreviewed")
        self.assertEqual(matrix["procurement"]["evidence_state"], "missing_external_evidence")
        self.assertEqual(matrix["rights"]["evidence_state"], "no_selected_evidence")
        self.assertEqual(report["coverage_status"], "unverified")
        self.assertNotIn("compliance_percentage", json.dumps(report))

    def test_impact_uses_explicit_asset_source_mapping(self):
        item = source(source_key="AI-1")
        context = {"assets": [{"id": "register", "name": "Inventory register", "owner": "Policy lead", "program": "Governance", "source_keys": ["AI-1"]}, {"id": "other", "name": "Other asset", "program": "Governance", "source_keys": ["not-selected"]}]}
        impacts = self.items(self.report([item], context=context), "impact")
        self.assertEqual(len(impacts), 1)
        self.assertEqual(impacts[0]["data"]["asset_id"], "register")
        self.assertEqual(impacts[0]["source_ids"], ["internal"])

    def test_language_flags_are_advisory_and_respect_recognized_acronym_expansion(self):
        first = source("one", "The office must promptly review AI systems as needed.")
        second = source("two", "Artificial intelligence (AI) supports inventory review. AI records inform the office.")
        report = self.report([first, second])
        language = self.items(report, "language")
        self.assertTrue(any("AI" in item["data"]["unexpanded_acronyms"] for item in language if item["source_ids"] == ["one"]))
        self.assertFalse(any("AI" in item["data"]["unexpanded_acronyms"] for item in language if item["source_ids"] == ["two"]))
        self.assertTrue(any("vague" in reason for item in language for reason in item["data"]["flags"]))
        self.assert_real_evidence(report, [first, second])

    def test_upcoming_dates_and_workload_do_not_invent_owner_deadlines(self):
        item = source(effective_from="2026-02-04", legal_status="adopted_not_effective")
        pending = {"id": "f1", "status": "pending", "applicability": {"determination": "unknown"}, "evidence": [{"source_id": item["id"]}]}
        reopened = {"action": "applicability.reviewed", "details": {"invalidated_status": "accepted"}}
        report = self.report([item], findings=[pending], audit=[reopened])
        deadlines = self.items(report, "deadlines")
        upcoming = next(entry for entry in deadlines if entry["data"]["kind"] == "source_date")
        workload = next(entry for entry in deadlines if entry["data"]["kind"] == "review_workload")
        self.assertEqual(upcoming["data"]["days_until"], 3)
        self.assertEqual(upcoming["severity"], "urgent")
        self.assertEqual(report["summary"]["upcoming_dates"], 1)
        self.assertEqual(workload["data"]["blocked"], 1)
        self.assertEqual(workload["data"]["reopened_events"], 1)
        self.assertNotIn("overdue", workload["data"])

    def test_peer_suggestions_only_use_explicit_public_other_jurisdiction_material(self):
        internal = source(text="The office maintains an annual inventory of automated decision tools.")
        public = source("public", "Annual inventory entries list automated decision tools and reviewers.", kind="external", jurisdiction_id="US-CA", reference_scope="public")
        private = source("private", "CONFIDENTIAL annual inventory uses automated decision tools.", kind="external", jurisdiction_id="US-NY", reference_scope="private")
        report = self.report([internal, public, private])
        ideas = self.items(report, "peer_research")
        self.assertEqual(len(ideas), 1)
        self.assertEqual(ideas[0]["source_ids"], ["internal", "public"])
        self.assertIn("nonbinding", ideas[0]["detail"])
        self.assertNotIn("CONFIDENTIAL", json.dumps(ideas))
        self.assert_real_evidence(report, [internal, public])

    def test_bounded_results_disclose_omission_and_count_all_candidates(self):
        item = source(text="\n".join(f"The office must review inventory item {number}." for number in range(105)))
        report = self.report([item])
        self.assertEqual(len(self.items(report, "obligations")), 100)
        self.assertEqual(report["summary"]["obligations"], 105)
        self.assertTrue(any("obligations: 5 additional items omitted" in warning for warning in report["warnings"]))

    def test_empty_inputs_and_missing_context_remain_unknown(self):
        report = self.report([])
        self.assertEqual(report["coverage_status"], "unverified")
        self.assertEqual(report["features"]["coverage"]["status"], "needs_input")
        self.assertEqual(report["features"]["impact"]["status"], "needs_input")
        self.assertTrue(any("No source snapshots" in warning for warning in report["warnings"]))

    def test_report_is_reproducible_and_inputs_are_not_modified(self):
        values = [source(text="The office must review an inventory annually.")]
        context = {"topics": ["inventory"]}
        before = json.dumps([values, context], sort_keys=True)
        first = self.report(values, context=context)
        second = self.report(values, context=context)
        self.assertEqual(first, second)
        self.assertEqual(before, json.dumps([values, context], sort_keys=True))

    def test_report_and_item_ids_match_across_python_hash_seeds(self):
        # Multiple matched sources exercise set-derived coverage IDs; peer shared
        # terms and impact mappings exercise the other emitted set-derived lists.
        values = [source(name, "Annual inventory records track automated decision tools.", source_key=name)
                  for name in ("zeta", "alpha", "delta", "gamma", "beta", "eta", "epsilon")]
        values.append(source("public", "Annual inventory records track automated decision tools for reviewers.",
                             kind="external", jurisdiction_id="US-CA", reference_scope="public"))
        payload = {"sources": values, "history": [], "settings": {"advanced_analysis": True},
                   "context": {"topics": ["inventory"], "assets": [{"id": "register", "name": "Register", "source_keys": ["zeta", "alpha"]}]},
                   "as_of": "2026-02-01", "findings": [], "audit_events": [], "jurisdiction_id": "US-GA"}
        script = "import json,sys; from compass.analysis import analyze; print(json.dumps(analyze(**json.load(sys.stdin)), sort_keys=True))"
        outputs = [subprocess.run([sys.executable, "-c", script], input=json.dumps(payload), text=True,
                                  capture_output=True, check=True, timeout=10,
                                  cwd=Path(__file__).resolve().parents[1],
                                  env={**os.environ, "PYTHONHASHSEED": seed}).stdout
                   for seed in ("1", "2", "27")]
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0], outputs[2])
        report = json.loads(outputs[0])
        coverage = self.items(report, "coverage")[0]
        self.assertEqual(coverage["source_ids"], sorted(value["id"] for value in values))

    def test_same_source_key_needs_matching_kind_and_jurisdiction(self):
        current = source("current", "Selected version.", source_key="shared-key")
        foreign = source("foreign", "WRONG JURISDICTION", source_key="shared-key", jurisdiction_id="US-CA", created_at="2026-01-01T12:00:00Z")
        external = source("external", "WRONG KIND", source_key="shared-key", kind="external", created_at="2026-01-02T12:00:00Z")
        for history in ([foreign], [external]):
            report = self.report([current], history)
            self.assertEqual(self.items(report, "change_detection"), [])
        current["replaces_source_id"] = "foreign"
        self.assertEqual(self.items(self.report([current], [foreign]), "change_detection"), [])

    def test_nearby_exclusion_after_numbered_heading_is_preserved_as_candidate_context(self):
        item = source(text="Section 4. The office shall review inventory annually. Section 5. Research-only pilots are excluded.")
        report = self.report([item])
        action = self.items(report, "obligations")[0]
        self.assertTrue(any("excluded" in value for value in action["data"]["exceptions"]))
        self.assertTrue(any("excluded" in value["quote"] for value in action["evidence"]))
        self.assertEqual(action["data"]["applicability"], "unknown")

    def test_regularly_is_an_advisory_language_flag(self):
        item = source(text="The office reviews its inventory regularly.")
        report = self.report([item])
        self.assertTrue(any("regularly" in flag for entry in self.items(report, "language") for flag in entry["data"]["flags"]))

    def test_explicit_owner_deadlines_are_distinct_from_legal_dates(self):
        base = {"status": "pending", "applicability": {"determination": "unknown"}, "evidence": []}
        overdue = {**base, "id": "late", "assignment": {"owner": "Policy lead", "due_date": "2026-01-30"}}
        upcoming = {**base, "id": "soon", "assignment": {"owner": "Reviewer", "due_date": "2026-02-03"}}
        completed = {**base, "id": "done", "status": "accepted", "assignment": {"due_date": "2026-01-01"}}
        report = self.report([], findings=[overdue, upcoming, completed])
        tasks = [entry for entry in self.items(report, "deadlines") if entry["data"]["kind"] == "owner_task_due"]
        self.assertEqual(len(tasks), 2)
        self.assertTrue(next(entry for entry in tasks if entry["data"]["finding_id"] == "late")["data"]["overdue"])
        self.assertEqual(report["summary"]["upcoming_dates"], 1)
        self.assertTrue(all("separate from" in entry["detail"] for entry in tasks))


if __name__ == "__main__":
    unittest.main()
