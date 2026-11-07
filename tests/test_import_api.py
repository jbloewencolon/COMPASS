"""Method suggestions remain scoped, pending and idempotent through the API."""

from copy import deepcopy
import unittest

from compass.method_import import convert_georgia_register
import test_workflow as fixtures


class MethodImportAPITests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    login = fixtures.WorkflowTests.login
    source = fixtures.WorkflowTests.source
    review_run = fixtures.WorkflowTests.review_run

    def create_run(self):
        return self.review_run(self.source(legal_status="unknown"), self.source("external", legal_status="unknown"))

    def import_into(self, run, bundle=None):
        return self.client.post(f"/api/runs/{run['id']}/method-findings", json=bundle if bundle is not None else convert_georgia_register())

    def test_all_35_imported_suggestions_keep_method_identity_and_provenance(self):
        run = self.create_run()
        bundle = convert_georgia_register()
        response = self.import_into(run, bundle)
        self.assertEqual(response.status_code, 201, response.text)
        result = response.json()
        self.assertEqual(result["imported_count"], 35)
        self.assertEqual(result["skipped_count"], 0)
        self.assertEqual(result["import_report"], bundle["import_report"])
        expected = {item["original_finding_id"] for item in bundle["findings"]}
        self.assertEqual({item["original_finding_id"] for item in result["imported"]}, expected)
        for finding in result["imported"]:
            self.assertNotEqual(finding["id"], finding["original_finding_id"])
            self.assertEqual(finding["run_id"], run["id"])
            self.assertEqual(finding["origin"], "method_run")
            self.assertEqual(finding["method_run_id"], "BASE-1")
            self.assertEqual(finding["provenance"], bundle["provenance"])
            self.assertEqual(finding["status"], "pending")
            self.assertEqual(finding["applicability"]["determination"], "unknown")
            self.assertIsNone(finding["applicability"]["reviewed_by"])
            self.assertTrue(finding["evidence_gaps"])
            self.assertEqual(finding["evidence"], [])
            self.assertFalse(finding["scope_complete"])
            self.assertNotIn("decision", finding)
        exported = self.client.get(f"/api/runs/{run['id']}/export")
        self.assertEqual(exported.status_code, 200, exported.text)
        data = exported.json()
        self.assertEqual(len(data["findings"]), 35)
        imports = [event for event in data["audit"] if event["action"] == "finding.imported"]
        self.assertEqual(len(imports), 35)
        self.assertTrue(all(event["details"]["status"] == "pending" for event in imports))
        analysis = self.client.post(f"/api/runs/{run['id']}/analyze", json={})
        self.assertEqual(analysis.status_code, 200, analysis.text)
        self.assertTrue(all(item["status"] == "pending" for item in self.client.get(f"/api/runs/{run['id']}").json()["findings"]))

    def test_repeat_import_preserves_records_and_does_not_duplicate_audit(self):
        run = self.create_run()
        first = self.import_into(run)
        self.assertEqual(first.status_code, 201, first.text)
        original = {item["id"]: item for item in first.json()["imported"]}
        second = self.import_into(run)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(second.json()["imported"], [])
        self.assertEqual(second.json()["imported_count"], 0)
        self.assertEqual(second.json()["skipped_count"], 35)
        run_after = self.client.get(f"/api/runs/{run['id']}").json()
        self.assertEqual({item["id"]: item for item in run_after["findings"]}, original)
        export = self.client.get(f"/api/runs/{run['id']}/export").json()
        self.assertEqual(len([event for event in export["audit"] if event["action"] == "finding.imported"]), 35)

    def test_tampered_decision_or_identity_is_refused_without_partial_import(self):
        run = self.create_run()
        original = convert_georgia_register()
        cases = []
        accepted = deepcopy(original)
        accepted["findings"][-1]["status"] = "accepted"
        cases.append(accepted)
        duplicate = deepcopy(original)
        duplicate["findings"][-1] = deepcopy(duplicate["findings"][0])
        cases.append(duplicate)
        provenance = deepcopy(original)
        provenance["provenance"]["workbook"]["sha256"] = "0" * 64
        cases.append(provenance)
        for bundle in cases:
            response = self.import_into(run, bundle)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(self.client.get(f"/api/runs/{run['id']}").json()["findings"], [])
        export = self.client.get(f"/api/runs/{run['id']}/export").json()
        self.assertFalse(any(event["action"] == "finding.imported" for event in export["audit"]))

    def test_applicability_label_cannot_accept_a_suggestion_with_evidence_gaps(self):
        run = self.create_run()
        response = self.import_into(run)
        self.assertEqual(response.status_code, 201, response.text)
        finding = next(item for item in response.json()["imported"] if item["original_finding_id"].endswith("F04"))
        reviewed = self.client.post(f"/api/findings/{finding['id']}/applicability", json={
            "determination": "persuasive",
            "rationale": "This is an optional policy proposal; its supporting passages and current legal status remain unverified.",
            "authority_relied_on": "Agency policy preference only; historical BASE-1 suggestion, not a verified legal requirement.",
        })
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        decision = self.client.post(f"/api/findings/{finding['id']}/decisions", json={
            "outcome": "accept", "rationale": "Attempt to accept before supplying the missing evidence.",
        })
        self.assertEqual(decision.status_code, 409, decision.text)
        current = self.client.get(f"/api/findings/{finding['id']}").json()
        self.assertEqual(current["status"], "pending")
        self.assertTrue(current["evidence_gaps"])
        self.assertNotIn("decision", current)

    def test_other_workspace_run_is_hidden_and_non_georgia_target_is_refused(self):
        georgia_run = self.create_run()
        self.login("ga-peer-owner")
        hidden = self.import_into(georgia_run)
        self.assertEqual(hidden.status_code, 404, hidden.text)
        self.login("ca-owner")
        california_run = self.review_run(self.source(jurisdiction_id="US-CA", legal_status="unknown"), self.source("external", legal_status="unknown"))
        refused = self.import_into(california_run)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertIn("Georgia", refused.json()["detail"])
        self.assertEqual(self.client.get(f"/api/runs/{california_run['id']}").json()["findings"], [])


if __name__ == "__main__":
    unittest.main()
