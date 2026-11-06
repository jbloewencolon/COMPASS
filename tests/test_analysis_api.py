"""Workspace analysis switches, saved evidence, and monitoring boundaries.

These checks use synthetic evidence and the API's real configuration paths.
Changing the display mode must never silently change the review's analysis.
"""

import copy
import unittest

import test_workflow as fixtures
from compass.analysis import ENGINE_VERSION


class AnalysisAPITests(unittest.TestCase):
    # Reuse the existing temporary-database/API fixtures without inheriting and
    # rerunning its full test suite under a second test class.
    setUp = fixtures.WorkflowTests.setUp
    login = fixtures.WorkflowTests.login
    dashboard = fixtures.WorkflowTests.dashboard
    source = fixtures.WorkflowTests.source
    review_run = fixtures.WorkflowTests.review_run
    finding_payload = fixtures.WorkflowTests.finding_payload
    finding = fixtures.WorkflowTests.finding
    fixture = fixtures.WorkflowTests.fixture

    def get_json(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def put_json(self, path, payload):
        response = self.client.put(path, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def analyze(self, run):
        response = self.client.post(f"/api/runs/{run['id']}/analyze", json={})
        self.assertIn(response.status_code, (200, 201), response.text)
        return response.json()

    def monitored_check(self):
        response = self.client.post("/api/monitoring/check", json={})
        self.assertIn(response.status_code, (200, 201), response.text)
        return response.json()

    def test_display_mode_is_personal_and_does_not_change_analysis(self):
        _, _, run, _ = self.fixture()
        self.assertEqual(self.get_json("/api/preferences")["view_mode"], "simple")
        settings = self.get_json("/api/settings")
        first = self.analyze(run)
        self.put_json("/api/preferences", {"view_mode": "advanced"})
        second = self.analyze(run)
        self.assertEqual(first["features"], second["features"])
        self.assertEqual(settings, self.get_json("/api/settings"))
        self.login("ga-reviewer")
        self.assertEqual(self.get_json("/api/preferences")["view_mode"], "simple")
        self.put_json("/api/preferences", {"view_mode": "advanced"})
        self.login("ga-owner")
        self.assertEqual(self.get_json("/api/preferences")["view_mode"], "advanced")
        self.login("ga-peer-owner")
        self.assertEqual(self.get_json("/api/preferences")["view_mode"], "simple")

    def test_reviewer_can_analyze_but_cannot_change_shared_configuration(self):
        _, _, run, _ = self.fixture()
        settings = self.get_json("/api/settings")
        context = self.get_json("/api/context")
        self.login("ga-reviewer")
        self.assertEqual(self.client.put("/api/settings", json=settings).status_code, 403)
        self.assertEqual(self.client.put("/api/context", json=context).status_code, 403)
        self.assertEqual(self.put_json("/api/preferences", {"view_mode": "advanced"})["view_mode"], "advanced")
        self.assertEqual(self.analyze(run)["method"], ENGINE_VERSION)

    def test_feature_switch_disables_work_not_just_presentation(self):
        instrument = self.source(text="The policy lead reviews the inventory when requested.")
        external = self.source("external", text="The office shall maintain an annual inventory.")
        run = self.review_run(instrument, external)
        enabled = self.analyze(run)
        self.assertTrue(enabled["features"]["obligations"]["enabled"])
        self.assertTrue(enabled["features"]["obligations"]["items"])
        selected_sources = {source["id"]: source for source in (instrument, external)}
        for item in enabled["features"]["obligations"]["items"]:
            self.assertTrue(item["evidence"])
            for evidence in item["evidence"]:
                self.assertIn(evidence["source_id"], selected_sources)
                self.assertIn(evidence["quote"], selected_sources[evidence["source_id"]]["text"])
        settings = self.get_json("/api/settings")
        settings["features"]["obligations"] = False
        self.put_json("/api/settings", settings)
        disabled = self.analyze(run)
        feature = disabled["features"]["obligations"]
        self.assertFalse(feature["enabled"])
        self.assertEqual(feature["status"], "disabled")
        self.assertEqual(feature["items"], [])
        self.assertFalse(disabled["settings_snapshot"]["features"]["obligations"])

    def test_master_switch_disables_every_advanced_feature(self):
        _, _, run, _ = self.fixture()
        settings = self.get_json("/api/settings")
        settings["advanced_analysis"] = False
        self.put_json("/api/settings", settings)
        report = self.analyze(run)
        self.assertTrue(report["features"], "Disabled modules must be visible as disabled.")
        for name in ("terminology", "impact", "language", "peer_research"):
            with self.subTest(feature=name):
                feature = report["features"][name]
                self.assertFalse(feature["enabled"])
                self.assertEqual(feature["status"], "disabled")
                self.assertEqual(feature["items"], [])
        self.assertTrue(report["features"]["obligations"]["enabled"])
        self.assertFalse(report["settings_snapshot"]["advanced_analysis"])

    def test_saved_reports_keep_prior_settings_and_context_in_export(self):
        _, _, run, _ = self.fixture()
        original_settings = self.get_json("/api/settings")
        original_context = self.get_json("/api/context")
        first = self.analyze(run)
        settings = copy.deepcopy(original_settings)
        settings["features"]["coverage"] = not settings["features"]["coverage"]
        self.put_json("/api/settings", settings)
        context = copy.deepcopy(original_context)
        context["topics"] = ["Procurement"]
        context["programs"] = ["Synthetic purchasing office"]
        self.put_json("/api/context", context)
        second = self.analyze(run)
        self.assertNotEqual(first["id"], second["id"])
        bundle = self.get_json(f"/api/runs/{run['id']}/export")
        reports = {report["id"]: report for report in bundle["analyses"]}
        self.assertIn(first["id"], reports)
        self.assertIn(second["id"], reports)
        self.assertEqual(reports[first["id"]]["settings_snapshot"], original_settings)
        self.assertEqual(reports[first["id"]]["context_snapshot"], original_context)
        self.assertEqual(reports[second["id"]]["settings_snapshot"], settings)
        self.assertEqual(reports[second["id"]]["context_snapshot"], context)
        self.assertEqual(reports[first["id"]]["features"], first["features"])

    def test_settings_context_and_analysis_are_scoped_to_office_not_state(self):
        _, _, run, _ = self.fixture()
        settings = self.get_json("/api/settings")
        settings["features"]["terminology"] = False
        self.put_json("/api/settings", settings)
        context = self.get_json("/api/context")
        context["programs"] = ["Private office-specific program"]
        self.put_json("/api/context", context)
        self.login("ga-peer-owner")
        self.assertTrue(self.get_json("/api/settings")["features"]["terminology"])
        self.assertNotIn("Private office-specific program", self.get_json("/api/context")["programs"])
        response = self.client.post(f"/api/runs/{run['id']}/analyze", json={})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get(f"/api/runs/{run['id']}/brief").status_code, 404)

    def test_equivalent_monitoring_checks_reuse_completed_work(self):
        self.fixture()
        first = self.monitored_check()
        second = self.monitored_check()
        self.assertEqual(first["job"]["id"], second["job"]["id"])
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(first["analysis"]["id"], second["analysis"]["id"])
        monitoring = self.get_json("/api/monitoring")
        self.assertEqual(
            len([job for job in monitoring["jobs"] if job["id"] == first["job"]["id"]]),
            1,
        )

    def test_source_change_trigger_honors_workspace_settings_without_worker(self):
        settings = self.get_json("/api/settings")
        settings["monitoring"]["enabled"] = True
        settings["monitoring"]["source_changes"] = True
        self.put_json("/api/settings", settings)
        before = {job["id"] for job in self.get_json("/api/monitoring")["jobs"]}
        self.source("external", source_key="source-trigger-fixture")
        after = self.get_json("/api/monitoring")["jobs"]
        created = [job for job in after if job["id"] not in before]
        self.assertTrue(created, "A source change should enqueue work when enabled.")
        self.assertTrue(all(job.get("analysis_id") is None for job in created))
        settings["monitoring"]["source_changes"] = False
        self.put_json("/api/settings", settings)
        before_disabled = {job["id"] for job in self.get_json("/api/monitoring")["jobs"]}
        self.source("external", source_key="disabled-source-trigger-fixture")
        self.assertEqual(
            {job["id"] for job in self.get_json("/api/monitoring")["jobs"]},
            before_disabled,
        )

    def test_insights_marks_old_report_stale_until_new_configuration_is_analyzed(self):
        first = self.monitored_check()
        before = self.get_json("/api/insights")
        self.assertEqual(before["latest"]["id"], first["analysis"]["id"])
        self.assertFalse(before["stale"])
        settings = self.get_json("/api/settings")
        settings["features"]["coverage"] = False
        self.put_json("/api/settings", settings)
        changed = self.get_json("/api/insights")
        self.assertEqual(changed["latest"]["id"], first["analysis"]["id"])
        self.assertTrue(changed["stale"])
        second = self.monitored_check()
        refreshed = self.get_json("/api/insights")
        self.assertNotEqual(first["analysis"]["id"], second["analysis"]["id"])
        self.assertEqual(refreshed["latest"]["id"], second["analysis"]["id"])
        self.assertFalse(refreshed["stale"])

    def test_jobs_and_notices_cannot_cross_same_state_tenant_boundary(self):
        self.fixture()
        check = self.monitored_check()
        own_monitoring = self.get_json("/api/monitoring")
        notice_ids = {notice["id"] for notice in own_monitoring["notices"]}
        self.assertTrue(notice_ids, "A finished check must create a review-ready notice.")
        self.login("ga-peer-owner")
        response = self.client.post(f"/api/jobs/{check['job']['id']}/retry", json={})
        self.assertEqual(response.status_code, 404)
        peer = self.get_json("/api/monitoring")
        self.assertNotIn(check["job"]["id"], [job["id"] for job in peer["jobs"]])
        self.assertFalse(notice_ids.intersection(notice["id"] for notice in peer["notices"]))
        for notice_id in notice_ids:
            with self.subTest(notice=notice_id):
                self.assertEqual(
                    self.client.post(f"/api/notices/{notice_id}/read", json={}).status_code,
                    404,
                )

    def test_assignment_is_owner_controlled_and_tenant_scoped(self):
        _, _, _, finding = self.fixture()
        assignment = {"assignee": "Synthetic procurement lead", "due_date": "2026-12-01"}
        response = self.put_json(f"/api/findings/{finding['id']}/assignment", assignment)
        self.assertEqual(response["assignment"]["assignee"], assignment["assignee"])
        self.assertEqual(response["assignment"]["due_date"], assignment["due_date"])
        self.login("ga-reviewer")
        self.assertEqual(
            self.client.put(f"/api/findings/{finding['id']}/assignment", json=assignment).status_code,
            403,
        )
        self.login("ga-peer-owner")
        self.assertEqual(
            self.client.put(f"/api/findings/{finding['id']}/assignment", json=assignment).status_code,
            404,
        )

    def test_brief_is_plain_text_and_preserves_source_links(self):
        instrument = self.source(source_url="https://example.org/synthetic-instrument")
        external = self.source("external", source_url="https://example.org/synthetic-reference")
        run = self.review_run(instrument, external)
        finding = self.finding(run, instrument, external)
        self.analyze(run)
        response = self.client.get(f"/api/runs/{run['id']}/brief")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.headers["content-type"].startswith("text/plain"))
        self.assertIn(run["title"], response.text)
        self.assertIn(finding["summary"], response.text)
        self.assertIn(instrument["source_url"], response.text)
        self.assertIn(external["source_url"], response.text)

    def test_capabilities_do_not_claim_an_llm_or_live_external_database(self):
        health = self.get_json("/api/health")
        self.assertFalse(health["language_model_connected"])
        self.assertFalse(health["external_database_connected"])
        self.assertEqual(health["analysis_method"], ENGINE_VERSION)
        self.assertFalse(health["production_ready"])

    def test_replacement_predecessor_must_be_same_tenant_kind_and_jurisdiction(self):
        original = self.source("external", source_key="replacement-contract")
        payload = {
            key: value for key, value in original.items()
            if key not in {"id", "hash", "created_at"}
        }
        payload.update(version="fixture-v2", replaces_source_id=original["id"])
        wrong_kind = {**payload, "kind": "instrument", "jurisdiction_id": "US-GA"}
        self.assertEqual(self.client.post("/api/sources", json=wrong_kind).status_code, 422)
        wrong_jurisdiction = {**payload, "jurisdiction_id": "US-CA"}
        self.assertEqual(self.client.post("/api/sources", json=wrong_jurisdiction).status_code, 422)
        self.login("ga-peer-owner")
        self.assertEqual(self.client.post("/api/sources", json=payload).status_code, 404)


if __name__ == "__main__":
    unittest.main()
