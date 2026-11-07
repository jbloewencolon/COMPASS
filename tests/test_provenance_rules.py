"""Rule outputs disclose supplied page provenance and limit peer comparisons."""

import unittest
from copy import deepcopy

from compass.analysis import METHOD_CATALOGUE, _evidence, analyze
from compass.monitoring import _basis


def source(identifier, kind="instrument", jurisdiction="US-GA", **extra):
    return {"id": identifier, "kind": kind, "jurisdiction_id": jurisdiction,
            "title": "Synthetic source", "text": "The office must review its annual system inventory.",
            "version": "1", "legal_status": "unknown", "authority_type": "guidance",
            "reference_scope": "public", "created_at": "2026-11-01T00:00:00+00:00", **extra}


class ProvenanceRuleTests(unittest.TestCase):
    def test_pinned_catalogue_terms_drive_the_report_and_change_its_cache_basis(self):
        snapshot = {"tenant_id": "office", "sources": [], "profile_hash": "profile", "settings": {},
                    "context": {}, "findings": [], "workflow_audit": [], "as_of": "2026-11-06",
                    "method_catalogue": deepcopy(METHOD_CATALOGUE)}
        before = _basis(snapshot)
        snapshot["method_catalogue"]["hash"] = "different-reviewed-content"
        snapshot["method_catalogue"]["vague_terms"] = ["bespoke vague phrase"]
        self.assertNotEqual(before, _basis(snapshot))
        report = analyze([source("policy", text="The office uses bespoke vague phrase.")], [],
                         {"advanced_analysis": True}, {}, "2026-11-06", [], [], "US-GA",
                         method_catalogue=snapshot["method_catalogue"])
        self.assertEqual(report["method_catalogue"], snapshot["method_catalogue"])
        self.assertTrue(report["features"]["language"]["items"])
        report["method_catalogue"]["vague_terms"].append("must not mutate the pinned input")
        self.assertEqual(snapshot["method_catalogue"]["vague_terms"], ["bespoke vague phrase"])

    def test_quotes_include_only_intersecting_supplied_pages(self):
        text = "The office must review.\nThe vendor may respond."
        record = source("policy", text=text, page_spans=[{"page": 1, "start": 0, "end": 23}, {"page": 3, "start": 24, "end": len(text)}])
        quote = _evidence(record, 24, len(text))
        self.assertEqual(quote["quote"], text[24:])
        self.assertTrue(quote["location"].startswith("Page 3;"))
        combined = _evidence(record, 0, len(text))
        self.assertTrue(combined["location"].startswith("Pages 1, 3;"))
        record.pop("page_spans")
        self.assertNotIn("Page", _evidence(record)["location"])

    def test_peer_research_keeps_foreign_and_federal_context_out_of_state_comparisons(self):
        records = [source("local"), source("peer", "external", "US-CA"), source("foreign", "external", "EU"), source("federal", "external", "US-FED"), source("territory", "external", "US-PR")]
        report = analyze(records, [], {"features": {"peer_research": True}, "advanced_analysis": True}, {}, "2026-11-06", [], [], "US-GA")
        items = report["features"]["peer_research"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source_ids"], ["local", "peer"])
        self.assertEqual(len(records), 5)
        self.assertEqual(records[2]["jurisdiction_id"], "EU")


if __name__ == "__main__":
    unittest.main()
