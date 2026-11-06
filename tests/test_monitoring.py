"""Durable-worker integration checks, with a controlled clock and real store.

The worker is driven explicitly; no sleeps or background threads are needed to
exercise scheduling, retry backoff, interrupted leases, and evidence snapshots.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import unittest

from fastapi import HTTPException

import test_workflow as fixtures


class MonitoringTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    login = fixtures.WorkflowTests.login
    dashboard = fixtures.WorkflowTests.dashboard
    source = fixtures.WorkflowTests.source
    review_run = fixtures.WorkflowTests.review_run
    finding_payload = fixtures.WorkflowTests.finding_payload
    finding = fixtures.WorkflowTests.finding
    fixture = fixtures.WorkflowTests.fixture
    determination = fixtures.WorkflowTests.determination

    @property
    def service(self):
        return self.app.state.monitoring

    @property
    def store(self):
        return self.app.state.store

    @property
    def tenant(self):
        return self.session["workspace"]["id"]

    @property
    def actor(self):
        return {**self.session["user"], "tenant_id": self.tenant}

    def json_get(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def configure_monitoring(self, **controls):
        settings = self.json_get("/api/settings")
        settings["monitoring"].update(controls)
        response = self.client.put("/api/settings", json=settings)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def manual_check(self):
        response = self.client.post("/api/monitoring/check", json={})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def make_due(self, job_id):
        with self.store.connect(write=True) as db:
            db.execute(
                "UPDATE monitoring_jobs SET available_at=? WHERE tenant_id=? AND id=?",
                ("2000-01-01T00:00:00+00:00", self.tenant, job_id),
            )

    @contextmanager
    def clock(self, instant):
        with patch("compass.monitoring.datetime", wraps=datetime) as clock, patch(
            "compass.monitoring.now", return_value=instant.isoformat()
        ):
            clock.now.return_value = instant
            yield

    def test_event_flags_work_independently_of_scheduled_monitoring(self):
        self.assertFalse(self.json_get("/api/settings")["monitoring"]["enabled"])
        self.assertEqual(self.service.status(self.tenant)["jobs"], [])
        self.service.tick()
        self.assertEqual(self.service.status(self.tenant)["jobs"], [])
        self.source("external", source_key="event-driven-fixture")
        source_jobs = self.service.status(self.tenant)["jobs"]
        self.assertTrue(any(job["trigger"] == "source_changed" for job in source_jobs))
        context = self.json_get("/api/context")
        context["programs"] = ["Changed synthetic program"]
        response = self.client.put("/api/context", json=context)
        self.assertEqual(response.status_code, 200, response.text)
        jobs = self.service.status(self.tenant)["jobs"]
        self.assertTrue(any(job["trigger"] == "context_changed" for job in jobs))
        job_ids = {job["id"] for job in jobs}
        self.service.tick()
        self.assertEqual({job["id"] for job in self.service.status(self.tenant)["jobs"]}, job_ids)
        self.configure_monitoring(source_changes=False, context_changes=False)
        disabled_ids = {job["id"] for job in self.service.status(self.tenant)["jobs"]}
        self.source("external", source_key="disabled-event-fixture")
        context["programs"] = ["Another synthetic program"]
        self.assertEqual(self.client.put("/api/context", json=context).status_code, 200)
        self.assertEqual(
            {job["id"] for job in self.service.status(self.tenant)["jobs"]}, disabled_ids
        )

    def test_effective_date_catch_up_and_repeated_tick_do_not_duplicate_work(self):
        self.configure_monitoring(
            enabled=True, source_changes=False, context_changes=False,
            effective_dates=True, check_interval_hours=168, timezone="UTC",
        )
        start = datetime.now(timezone.utc).replace(microsecond=0)
        with self.clock(start):
            self.service.tick()
            initial = self.service.status(self.tenant)
            self.assertEqual(len(initial["jobs"]), 1)
            self.assertEqual(initial["jobs"][0]["state"], "succeeded")
            self.service.tick()
            self.assertEqual(len(self.service.status(self.tenant)["jobs"]), 1)
        # Catch up on the current legal date after a multi-day worker outage,
        # even though the ordinary seven-day check interval is not yet due.
        later = start + timedelta(days=3)
        with self.clock(later):
            self.service.tick()
            jobs = self.service.status(self.tenant)["jobs"]
            self.assertEqual(len(jobs), 2)
            self.assertEqual({job["as_of"] for job in jobs}, {start.date().isoformat(), later.date().isoformat()})
            self.assertTrue(all(job["state"] == "succeeded" for job in jobs))
            self.service.tick()
            self.assertEqual(len(self.service.status(self.tenant)["jobs"]), 2)

    def test_due_digest_is_in_app_scoped_and_not_duplicated_on_next_tick(self):
        self.configure_monitoring(
            enabled=True, source_changes=False, context_changes=False,
            effective_dates=False, check_interval_hours=168, digest_interval_days=7,
            timezone="UTC",
        )
        start = datetime.now(timezone.utc).replace(microsecond=0)
        with self.clock(start):
            self.service.tick()
        with self.clock(start + timedelta(days=8)):
            self.service.tick()
            status = self.service.status(self.tenant)
            digests = [notice for notice in status["notices"] if notice["kind"] == "digest"]
            self.assertEqual(len(digests), 1)
            self.assertIn("workload", digests[0])
            self.assertFalse(status["capabilities"]["email_delivery"])
            self.service.tick()
            repeated = self.service.status(self.tenant)
            self.assertEqual(
                [notice["id"] for notice in repeated["notices"] if notice["kind"] == "digest"],
                [digests[0]["id"]],
            )
        self.login("ga-peer-owner")
        self.assertNotIn(digests[0]["id"], [notice["id"] for notice in self.service.status(self.tenant)["notices"]])

    def test_failure_backoff_then_repair_reuses_run_and_saves_one_report(self):
        job = self.service.enqueue(self.tenant, self.actor, "manual")
        with patch("compass.monitoring.analyze", side_effect=RuntimeError("private diagnostic fixture")):
            failed = self.service.process(job["id"], self.tenant)
        self.assertEqual(failed["state"], "failed")
        self.assertEqual(failed["attempts"], 1)
        self.assertIsNotNone(failed["run_id"])
        self.assertIsNone(failed["analysis_id"])
        self.assertNotIn("private diagnostic fixture", failed["last_error"])
        self.assertEqual(self.service.process(job["id"], self.tenant)["attempts"], 1)
        self.make_due(job["id"])
        repaired = self.service.process(job["id"], self.tenant)
        self.assertEqual(repaired["state"], "succeeded")
        self.assertEqual(repaired["attempts"], 2)
        self.assertEqual(repaired["run_id"], failed["run_id"])
        self.assertEqual(len(self.service.analyses_for_run(self.tenant, failed["run_id"])), 1)
        again = self.service.process(job["id"], self.tenant)
        self.assertEqual(again["analysis_id"], repaired["analysis_id"])
        self.assertEqual(again["attempts"], 2)

    def test_automatic_and_explicit_retries_cannot_exceed_attempt_limit(self):
        job = self.service.enqueue(self.tenant, self.actor, "manual")
        run_id = None
        with patch("compass.monitoring.analyze", side_effect=RuntimeError("simulated failure")):
            for attempt in range(1, job["max_attempts"] + 1):
                self.make_due(job["id"])
                current = self.service.process(job["id"], self.tenant)
                self.assertEqual(current["state"], "failed")
                self.assertEqual(current["attempts"], attempt)
                if run_id is None:
                    run_id = current["run_id"]
                self.assertEqual(current["run_id"], run_id)
        self.make_due(job["id"])
        stopped = self.service.process(job["id"], self.tenant)
        self.assertEqual(stopped["state"], "failed")
        self.assertEqual(stopped["attempts"], job["max_attempts"])
        with self.assertRaises(HTTPException) as denied:
            self.service.retry(self.tenant, self.actor, job["id"])
        self.assertEqual(denied.exception.status_code, 409)
        self.assertEqual(self.service.analyses_for_run(self.tenant, run_id), [])

    def test_expired_worker_lease_recovers_without_duplicate_run(self):
        job = self.service.enqueue(self.tenant, self.actor, "manual")
        with patch("compass.monitoring.analyze", side_effect=RuntimeError("initial interruption")):
            failed = self.service.process(job["id"], self.tenant)
        with self.store.connect(write=True) as db:
            db.execute(
                "UPDATE monitoring_jobs SET state='running',lease_token='abandoned-fixture',lease_expires_at=? WHERE tenant_id=? AND id=?",
                ("2000-01-01T00:00:00+00:00", self.tenant, job["id"]),
            )
        recovered = self.service.process(job["id"], self.tenant)
        self.assertEqual(recovered["state"], "succeeded")
        self.assertEqual(recovered["run_id"], failed["run_id"])
        self.assertEqual(recovered["attempts"], 2)
        self.assertEqual(len(self.service.analyses_for_run(self.tenant, recovered["run_id"])), 1)

    def test_settings_change_cancels_old_queued_snapshot_before_processing(self):
        old = self.service.enqueue(self.tenant, self.actor, "manual")
        settings = self.json_get("/api/settings")
        settings["features"]["language"] = False
        response = self.client.put("/api/settings", json=settings)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.service.get_job(self.tenant, old["id"])["state"], "cancelled")
        self.assertEqual(self.service.process(old["id"], self.tenant)["state"], "cancelled")
        self.assertIsNone(self.service.get_job(self.tenant, old["id"])["run_id"])
        new_jobs = [job for job in self.service.status(self.tenant)["jobs"] if job["id"] != old["id"]]
        self.assertEqual(len(new_jobs), 1)
        current = self.service.process(new_jobs[0]["id"], self.tenant)
        self.assertEqual(current["state"], "succeeded")
        report = self.service.analyses_for_run(self.tenant, current["run_id"])[0]
        self.assertFalse(report["settings_snapshot"]["features"]["language"])
        self.assertFalse(report["features"]["language"]["enabled"])

    def test_workflow_changes_stale_reports_but_worker_audit_does_not(self):
        _, _, _, finding = self.fixture()
        first = self.manual_check()
        self.assertFalse(self.service.insights(self.tenant)["stale"])
        response = self.client.put(
            f"/api/findings/{finding['id']}/assignment",
            json={"assignee": "Synthetic policy lead", "due_date": "2026-12-01"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(self.service.insights(self.tenant)["stale"])
        second = self.manual_check()
        self.assertNotEqual(first["analysis"]["id"], second["analysis"]["id"])
        self.assertFalse(self.service.insights(self.tenant)["stale"])
        self.assertEqual(self.determination(finding, "persuasive").status_code, 200)
        response = self.client.post(
            f"/api/findings/{finding['id']}/decisions",
            json={"outcome": "accept", "rationale": "The owner confirmed this synthetic recommendation."},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(self.service.insights(self.tenant)["stale"])
        third = self.manual_check()
        self.assertNotEqual(second["analysis"]["id"], third["analysis"]["id"])
        self.assertFalse(self.service.insights(self.tenant)["stale"])
        original = next(item for item in first["analysis"]["findings_snapshot"] if item["id"] == finding["id"])
        current = next(item for item in third["analysis"]["findings_snapshot"] if item["id"] == finding["id"])
        self.assertEqual(original["status"], "pending")
        self.assertNotIn("assignment", original)
        self.assertEqual(current["status"], "accepted")
        self.assertEqual(current["assignment"]["assignee"], "Synthetic policy lead")

    def test_source_and_trigger_are_atomic_when_enqueue_fails(self):
        before = self.dashboard()["counts"]["sources"]
        before_jobs = self.service.status(self.tenant)["jobs"]
        with patch.object(self.service, "enqueue", side_effect=RuntimeError("enqueue unavailable")):
            with self.assertRaises(RuntimeError):
                self.source("external", title="Atomic rollback source fixture")
        self.assertEqual(self.dashboard()["counts"]["sources"], before)
        self.assertEqual(self.service.status(self.tenant)["jobs"], before_jobs)
        events = self.json_get("/api/audit")["events"]
        source_ids = {source["id"] for source in self.dashboard()["sources"]}
        self.assertTrue(all(event["entity_id"] in source_ids for event in events if event["action"] == "source.created"))

    def test_same_source_key_in_distinct_jurisdictions_keeps_both_references(self):
        state = self.source("external", source_key="shared-key", jurisdiction_id="US-GA")
        federal = self.source("external", source_key="shared-key", jurisdiction_id="US-FED")
        report = self.manual_check()["analysis"]
        self.assertIn(state["id"], report["source_ids"])
        self.assertIn(federal["id"], report["source_ids"])


if __name__ == "__main__":
    unittest.main()
