"""Agency review aids preserve foreign context and historical source/profile inputs."""

import json
import unittest

import test_workflow as fixtures
from compass.demo import seed
from compass.store import canonical, digest


class MilestoneOneAPITests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    login = fixtures.WorkflowTests.login
    source = fixtures.WorkflowTests.source
    review_run = fixtures.WorkflowTests.review_run
    finding_payload = fixtures.WorkflowTests.finding_payload
    finding = fixtures.WorkflowTests.finding
    determination = fixtures.WorkflowTests.determination

    def test_foreign_source_keeps_its_type_but_cannot_establish_a_us_duty(self):
        internal = self.source()
        foreign = self.source("external", jurisdiction_id="EU", authority_type="regulation")
        run = self.review_run(internal, foreign)
        finding = self.finding(run, internal, foreign)
        for determination in ("binding", "conditional"):
            with self.subTest(determination=determination):
                response = self.determination(finding, determination)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn("Non-US context", response.json()["detail"])
        self.assertEqual(self.determination(finding, "persuasive").status_code, 200)
        saved = self.client.get(f"/api/sources/{foreign['id']}").json()
        self.assertEqual(saved, foreign)
        self.assertEqual(saved["authority_type"], "regulation")
        self.assertEqual(saved["jurisdiction_id"], "EU")
        report = self.client.post(f"/api/runs/{run['id']}/analyze", json={})
        self.assertEqual(report.status_code, 200, report.text)
        self.assertIn(foreign["id"], report.json()["source_ids"])
        related = [item for feature in report.json()["features"].values() for item in feature["items"] if foreign["id"] in item["source_ids"]]
        self.assertTrue(related)
        for item in related:
            self.assertIn("Non-US or unrecognized jurisdiction context (EU)", item["detail"])
            self.assertIn(foreign["id"], item["data"]["context_only_source_ids"])

    def test_monitoring_passes_pinned_georgia_citation_patterns_to_the_engine(self):
        internal = self.source(text="The office shall follow SS-23-002.")
        external = self.source("external", title="Synthetic standard SS-23-002", source_key="SS-23-002")
        run = self.review_run(internal, external)
        report = self.client.post(f"/api/runs/{run['id']}/analyze", json={})
        self.assertEqual(report.status_code, 200, report.text)
        data = report.json()
        self.assertTrue(data["profile_snapshot"]["citation_patterns"])
        matches = data["features"]["citations"]["items"]
        self.assertTrue(any(external["id"] in item["data"]["matched_source_ids"] for item in matches))

    def test_synthetic_profile_upgrade_does_not_rewrite_pinned_review_inputs(self):
        tenant = self.session["workspace"]["id"]
        store = self.app.state.store
        with store.connect(write=True) as db:
            row = db.execute("SELECT profile FROM tenants WHERE id=?", (tenant,)).fetchone()
            old = json.loads(row["profile"])
            old["version"] = "demo-1"
            old.pop("citation_patterns", None)
            old["sentence_abbreviations"] = ["Dept."]
            db.execute("UPDATE tenants SET profile=?,profile_hash=? WHERE id=?", (canonical(old), digest(old), tenant))
        run = self.review_run(self.source(), self.source("external"))
        self.assertEqual(run["profile_hash"], digest(old))
        seed(store)
        seed(store)
        with store.connect() as db:
            current = json.loads(db.execute("SELECT profile FROM tenants WHERE id=?", (tenant,)).fetchone()["profile"])
            updates = db.execute("SELECT COUNT(*) FROM audit WHERE tenant_id=? AND action='profile.updated'", (tenant,)).fetchone()[0]
        self.assertEqual(current["version"], "demo-2")
        self.assertTrue(current["citation_patterns"])
        self.assertEqual(current["sentence_abbreviations"], ["Dept."])
        self.assertEqual(updates, 1)
        bundle = self.client.get(f"/api/runs/{run['id']}/export").json()
        self.assertEqual(bundle["run"]["profile"], old)
        self.assertEqual(bundle["run"]["profile_hash"], digest(old))


if __name__ == "__main__":
    unittest.main()
