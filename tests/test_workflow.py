"""Workflow and isolation checks for the local COMPASS foundation.

All legal-looking material below is synthetic. These tests exercise access,
provenance, and review controls, not the correctness of legal analysis.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from compass.app import create_app
from compass.store import Store


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.app = create_app(Path(self.tempdir.name) / "test.sqlite3", demo=True)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.counter = 0
        self.login()

    def login(self, persona="ga-owner", appoint=True):
        response = self.client.post("/api/demo/session", json={"persona": persona})
        self.assertEqual(response.status_code, 200, response.text)
        session = self.client.get("/api/session")
        self.assertEqual(session.status_code, 200, session.text)
        self.session = session.json()
        # These existing workflow tests exercise a combined owner/reviewer office.
        # The permission is a real, attributed API grant; new D-2 tests separately
        # exercise the default-off and unappointed-owner cases.
        if appoint and self.session["workspace"]["role"] == "owner":
            granted = self.client.patch(f"/api/memberships/{persona}", json={"can_determine_applicability": True})
            self.assertEqual(granted.status_code, 200, granted.text)
            self.session = self.client.get("/api/session").json()
        return self.session

    def dashboard(self):
        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def source(self, kind="instrument", **overrides):
        self.counter += 1
        payload = {
            "kind": kind,
            "title": f"Synthetic {kind} fixture {self.counter}",
            "jurisdiction_id": "US-GA" if kind == "instrument" else "US-FED",
            "version": "fixture-v1",
            "text": (
                "This synthetic office policy describes a review process. "
                "The policy owner reviews the inventory on request."
                if kind == "instrument"
                else "This synthetic rule requires an annual inventory. "
                "Its exercise scope is the fictional demonstration office."
            ),
            "authority_type": "internal_policy" if kind == "instrument" else "statute",
            "legal_status": "in_force",
            "source_url": None,
            "effective_from": "2026-01-01",
            "effective_to": None,
            "verification": {"status": "verified", "primary_source_location": "Synthetic test fixture; not actual legal verification"},
        }
        payload.update(overrides)
        response = self.client.post("/api/sources", json=payload)
        self.assertIn(response.status_code, (200, 201), response.text)
        return response.json()

    def review_run(self, *sources, **overrides):
        payload = {
            "title": "Synthetic policy comparison",
            "as_of": "2026-11-03",
            "source_ids": [source["id"] for source in sources],
            "coverage_note": "Only the selected synthetic fixtures were reviewed.",
        }
        payload.update(overrides)
        response = self.client.post("/api/runs", json=payload)
        self.assertIn(response.status_code, (200, 201), response.text)
        return response.json()

    def finding_payload(self, instrument, external, **overrides):
        payload = {
            "summary": "The synthetic inventory review timing may be incomplete.",
            "category": "missing_obligation",
            "severity": "medium",
            "rationale": "The two quoted fixtures use different review schedules.",
            "instrument_source_id": instrument["id"],
            "external_source_id": external["id"],
            "instrument_quote": instrument["text"],
            "instrument_location": "Synthetic fixture paragraph 1",
            "external_quote": external["text"],
            "external_location": "Synthetic fixture paragraph 1",
        }
        payload.update(overrides)
        return payload

    def finding(self, run, instrument, external, **overrides):
        response = self.client.post(
            f"/api/runs/{run['id']}/findings",
            json=self.finding_payload(instrument, external, **overrides),
        )
        self.assertIn(response.status_code, (200, 201), response.text)
        return response.json()

    def fixture(self, **external_overrides):
        instrument = self.source()
        external = self.source("external", **external_overrides)
        run = self.review_run(instrument, external)
        finding = self.finding(run, instrument, external)
        return instrument, external, run, finding

    def determination(self, finding, value="persuasive"):
        return self.client.post(
            f"/api/findings/{finding['id']}/applicability",
            json={
                "determination": value,
                "rationale": "Policy owner reviewed the scope and supporting fixture.",
                "authority_relied_on": "Synthetic fixture authority only; not a real legal assertion.",
            },
        )

    def test_session_is_required_and_logout_revokes_it(self):
        self.assertEqual(self.client.post("/api/logout").status_code, 200)
        for path in ("/api/session", "/api/dashboard", "/api/sources", "/api/audit"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)

    def test_disabled_demo_cannot_create_a_session(self):
        app = create_app(Path(self.tempdir.name) / "disabled.sqlite3", demo=False)
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/demo/personas").status_code, 404)
            self.assertEqual(
                client.post("/api/demo/session", json={"persona": "ga-owner"}).status_code,
                404,
            )
            self.assertEqual(client.get("/api/dashboard").status_code, 401)

    def test_disabled_demo_rejects_persisted_demo_session_on_existing_database(self):
        self.assertEqual(self.client.get("/api/dashboard").status_code, 200)
        app = create_app(Path(self.tempdir.name) / "test.sqlite3", demo=False)
        with TestClient(app, cookies=self.client.cookies) as client:
            self.assertEqual(client.get("/api/session").status_code, 401)
            self.assertEqual(client.get("/api/dashboard").status_code, 401)
        # A disabled server must not remove the existing local development data.
        self.assertEqual(self.client.get("/api/dashboard").status_code, 200)

    def test_other_office_in_same_state_cannot_read_or_decide(self):
        instrument, external, run, finding = self.fixture()
        self.determination(finding)
        own_workspace = self.session["workspace"]["id"]
        peer_session = self.login("ga-peer-owner")
        self.assertEqual(peer_session["workspace"]["jurisdiction_id"], "US-GA")
        self.assertNotEqual(peer_session["workspace"]["id"], own_workspace)
        for path in (
            f"/api/sources/{instrument['id']}",
            f"/api/sources/{external['id']}",
            f"/api/runs/{run['id']}",
            f"/api/runs/{run['id']}/export",
            f"/api/findings/{finding['id']}",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.determination(finding).status_code, 404)
        response = self.client.post(
            f"/api/findings/{finding['id']}/decisions",
            json={"outcome": "accept", "rationale": "Attempted cross-office decision."},
        )
        self.assertEqual(response.status_code, 404)
        dashboard = self.dashboard()
        self.assertNotIn(instrument["id"], [item["id"] for item in dashboard["sources"]])
        self.assertNotIn(run["id"], [item["id"] for item in dashboard["runs"]])
        self.assertNotIn(finding["id"], [item["id"] for item in dashboard["findings"]])

    def test_other_state_cannot_attach_private_sources_to_a_run(self):
        private = self.source("external")
        self.login("ca-owner")
        instrument = self.source(jurisdiction_id="US-CA")
        response = self.client.post(
            "/api/runs",
            json={
                "title": "Unauthorized source attachment",
                "as_of": "2026-11-03",
                "source_ids": [instrument["id"], private["id"]],
                "coverage_note": "Exercise tenant boundary.",
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_reviewer_can_propose_but_cannot_approve_or_determine_applicability(self):
        instrument = self.source()
        external = self.source("external")
        run = self.review_run(instrument, external)
        self.login("ga-reviewer")
        finding = self.finding(run, instrument, external)
        self.assertEqual(self.determination(finding).status_code, 403)
        response = self.client.post(
            f"/api/findings/{finding['id']}/decisions",
            json={"outcome": "reject", "rationale": "Reviewer lacks decision authority."},
        )
        self.assertEqual(response.status_code, 403)

    def test_evidence_must_be_an_exact_excerpt(self):
        instrument = self.source()
        external = self.source("external")
        run = self.review_run(instrument, external)
        response = self.client.post(
            f"/api/runs/{run['id']}/findings",
            json=self.finding_payload(
                instrument, external, external_quote="An invented quotation not in the source."
            ),
        )
        self.assertIn(response.status_code, (400, 422))
        current = self.client.get(f"/api/runs/{run['id']}").json()
        self.assertEqual(current["findings"], [])

    def test_evidence_source_must_belong_to_the_pinned_run(self):
        instrument = self.source()
        external = self.source("external")
        unselected = self.source("external", version="fixture-v2")
        run = self.review_run(instrument, external)
        response = self.client.post(
            f"/api/runs/{run['id']}/findings",
            json=self.finding_payload(instrument, unselected),
        )
        self.assertIn(response.status_code, (400, 404, 422))

    def test_source_kinds_are_not_interchangeable(self):
        instrument = self.source()
        external = self.source("external")
        run = self.review_run(instrument, external)
        response = self.client.post(
            f"/api/runs/{run['id']}/findings",
            json=self.finding_payload(external, instrument),
        )
        self.assertIn(response.status_code, (400, 422))

    def test_unknown_applicability_cannot_be_accepted(self):
        _, _, _, finding = self.fixture()
        self.assertEqual(finding["applicability"]["determination"], "unknown")
        response = self.client.post(
            f"/api/findings/{finding['id']}/decisions",
            json={"outcome": "accept", "rationale": "Attempt before applicability review."},
        )
        self.assertIn(response.status_code, (400, 409, 422))
        current = self.client.get(f"/api/findings/{finding['id']}").json()
        self.assertEqual(current["status"], "pending")

    def test_owner_can_request_more_information_without_claiming_applicability(self):
        _, _, _, finding = self.fixture()
        response = self.client.post(
            f"/api/findings/{finding['id']}/decisions",
            json={"outcome": "needs_information", "rationale": "Need the covered program facts."},
        )
        self.assertEqual(response.status_code, 200, response.text)
        current = self.client.get(f"/api/findings/{finding['id']}").json()
        self.assertEqual(current["status"], "needs_information")
        self.assertEqual(current["applicability"]["determination"], "unknown")

    def test_not_applicable_finding_cannot_be_accepted(self):
        _, _, _, finding = self.fixture()
        response = self.determination(finding, "not_applicable")
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.post(
            f"/api/findings/{finding['id']}/decisions",
            json={"outcome": "accept", "rationale": "Cannot accept an inapplicable obligation."},
        )
        self.assertIn(response.status_code, (400, 409, 422))

    def test_new_applicability_review_invalidates_previous_acceptance(self):
        _, _, run, finding = self.fixture()
        self.assertEqual(self.determination(finding).status_code, 200)
        response = self.client.post(
            f"/api/findings/{finding['id']}/decisions",
            json={"outcome": "accept", "rationale": "Accepted after the first scope review."},
        )
        self.assertEqual(response.status_code, 200, response.text)
        previous_decision = response.json()["decision"]
        response = self.determination(finding, "conditional")
        self.assertEqual(response.status_code, 200, response.text)
        current = self.client.get(f"/api/findings/{finding['id']}").json()
        self.assertEqual(current["status"], "pending")
        self.assertNotIn("decision", current)
        bundle = self.client.get(f"/api/runs/{run['id']}/export").json()
        exported = next(item for item in bundle["findings"] if item["id"] == finding["id"])
        self.assertEqual(exported["status"], "pending")
        self.assertNotIn("decision", exported)
        events = self.client.get("/api/audit").json()["events"]
        related = [event for event in events if event["entity_id"] == finding["id"]]
        recorded = [event for event in related if event["action"] == "decision.recorded"]
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["details"]["outcome"], "accept")
        invalidated = [
            event for event in related
            if event["action"] == "applicability.reviewed"
            and event["details"].get("invalidated_decision")
        ]
        self.assertEqual(len(invalidated), 1)
        self.assertEqual(invalidated[0]["details"]["invalidated_status"], "accepted")
        self.assertEqual(invalidated[0]["details"]["invalidated_decision"], previous_decision)
        self.assertIn(recorded[0], bundle["audit"])
        self.assertIn(invalidated[0], bundle["audit"])

    def test_source_text_and_evidence_preserve_surrounding_whitespace(self):
        instrument_text = "\n  Synthetic policy text with meaningful layout.\t\n"
        external_text = "\t Synthetic reference text with preserved boundaries. \n\n"
        instrument = self.source(text=instrument_text)
        external = self.source("external", text=external_text)
        self.assertEqual(instrument["text"], instrument_text)
        self.assertEqual(external["text"], external_text)
        stored = self.client.get(f"/api/sources/{instrument['id']}").json()
        self.assertEqual(stored["text"], instrument_text)
        run = self.review_run(instrument, external)
        finding = self.finding(run, instrument, external)
        quotes = {item["kind"]: item["quote"] for item in finding["evidence"]}
        self.assertEqual(quotes, {"instrument": instrument_text, "external": external_text})
        bundle = self.client.get(f"/api/runs/{run['id']}/export").json()
        exported_quotes = {
            item["kind"]: item["quote"]
            for item in bundle["findings"][0]["evidence"]
        }
        self.assertEqual(exported_quotes, quotes)
        exported_text = {item["id"]: item["text"] for item in bundle["sources"]}
        self.assertEqual(exported_text[instrument["id"]], instrument_text)
        self.assertEqual(exported_text[external["id"]], external_text)

    def test_whitespace_only_source_is_rejected_without_import(self):
        before = self.dashboard()["counts"]["sources"]
        response = self.client.post(
            "/api/sources",
            json={
                "kind": "instrument",
                "title": "Empty synthetic source",
                "jurisdiction_id": "US-GA",
                "version": "empty-v1",
                "text": " \t\n\r ",
                "authority_type": "internal_policy",
                "legal_status": "unknown",
            },
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.dashboard()["counts"]["sources"], before)

    def test_duplicate_source_import_returns_original_without_extra_audit_event(self):
        source = self.source()
        before = self.dashboard()["counts"]["sources"]
        payload = {key: value for key, value in source.items() if key not in {"id", "hash", "created_at"}}
        payload["verification"] = {key: value for key, value in payload["verification"].items() if key in {"status", "primary_source_location"}}
        response = self.client.post("/api/sources", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), source)
        self.assertEqual(self.dashboard()["counts"]["sources"], before)
        events = self.client.get("/api/audit").json()["events"]
        created = [
            event for event in events
            if event["action"] == "source.created" and event["entity_id"] == source["id"]
        ]
        self.assertEqual(len(created), 1)

    def test_cross_origin_mutation_is_rejected_before_decision_changes(self):
        _, _, _, finding = self.fixture()
        self.assertEqual(self.determination(finding).status_code, 200)
        response = self.client.post(
            f"/api/findings/{finding['id']}/decisions",
            json={"outcome": "accept", "rationale": "Cross-origin attempt must be blocked."},
            headers={"Origin": "https://another-origin.example"},
        )
        self.assertEqual(response.status_code, 403, response.text)
        current = self.client.get(f"/api/findings/{finding['id']}").json()
        self.assertEqual(current["status"], "pending")
        self.assertNotIn("decision", current)
        events = self.client.get("/api/audit").json()["events"]
        self.assertFalse(any(
            event["action"] == "decision.recorded" and event["entity_id"] == finding["id"]
            for event in events
        ))

    def test_store_read_transaction_retains_one_snapshot_across_concurrent_commit(self):
        store = Store(Path(self.tempdir.name) / "snapshot.sqlite3")
        with store.connect(write=True) as db:
            db.execute("CREATE TABLE snapshot_fixture (id INTEGER PRIMARY KEY, value TEXT)")
            db.execute("INSERT INTO snapshot_fixture VALUES(1, 'original')")
        with store.connect() as reader:
            self.assertEqual(reader.execute("SELECT value FROM snapshot_fixture WHERE id=1").fetchone()[0], "original")
            with store.connect(write=True) as writer:
                writer.execute("UPDATE snapshot_fixture SET value='updated' WHERE id=1")
            self.assertEqual(reader.execute("SELECT value FROM snapshot_fixture WHERE id=1").fetchone()[0], "original")
        with store.connect() as reader:
            self.assertEqual(reader.execute("SELECT value FROM snapshot_fixture WHERE id=1").fetchone()[0], "updated")

    def test_research_and_voluntary_standards_cannot_be_made_binding(self):
        for authority in ("research", "voluntary_standard", "guidance"):
            with self.subTest(authority=authority):
                _, _, _, finding = self.fixture(authority_type=authority)
                response = self.determination(finding, "binding")
                self.assertIn(response.status_code, (400, 409, 422))
                current = self.client.get(f"/api/findings/{finding['id']}").json()
                self.assertEqual(current["applicability"]["determination"], "unknown")

    def test_inactive_or_future_sources_cannot_be_made_binding(self):
        cases = (
            {"legal_status": "adopted_not_effective"},
            {"legal_status": "repealed"},
            {"legal_status": "draft"},
            {"effective_from": "2027-01-01"},
            {"effective_to": "2026-10-01"},
            {"effective_from": None},
        )
        for source_values in cases:
            with self.subTest(source_values=source_values):
                _, _, _, finding = self.fixture(**source_values)
                self.assertIn(self.determination(finding, "binding").status_code, (400, 409, 422))

    def test_reviewed_eligible_source_can_support_an_attributed_decision(self):
        _, _, _, finding = self.fixture()
        response = self.determination(finding, "binding")
        self.assertEqual(response.status_code, 200, response.text)
        decision_payload = {
            "outcome": "accept",
            "rationale": "The owner confirmed the synthetic scope and evidence.",
            "actor_id": "not-the-authenticated-user",
            "actor_name": "Impersonated owner",
        }
        response = self.client.post(
            f"/api/findings/{finding['id']}/decisions", json=decision_payload
        )
        if response.status_code == 422:  # Strict schemas may reject actor fields outright.
            response = self.client.post(
                f"/api/findings/{finding['id']}/decisions",
                json={key: decision_payload[key] for key in ("outcome", "rationale")},
            )
        self.assertEqual(response.status_code, 200, response.text)
        current = self.client.get(f"/api/findings/{finding['id']}").json()
        self.assertEqual(current["status"], "accepted")
        events = self.client.get("/api/audit").json()["events"]
        related = [event for event in events if event["entity_id"] == finding["id"]]
        self.assertTrue(related)
        for event in related:
            self.assertEqual(event["actor_name"], self.session["user"]["name"])

    def test_evidence_bundle_preserves_selected_versions_after_later_import(self):
        instrument, external, run, finding = self.fixture()
        original = self.client.get(f"/api/runs/{run['id']}/export")
        self.assertEqual(original.status_code, 200, original.text)
        bundle = original.json()
        self.assertEqual(bundle["run"]["profile_hash"], run["profile_hash"])
        self.assertEqual(bundle["profile"]["hash"], run["profile_hash"])
        expected = {instrument["id"]: instrument, external["id"]: external}
        self.assertEqual({source["id"] for source in bundle["sources"]}, set(expected))
        for snapshot in bundle["sources"]:
            self.assertEqual(snapshot["hash"], expected[snapshot["id"]]["hash"])
            self.assertEqual(snapshot["text"], expected[snapshot["id"]]["text"])
        self.assertIn(finding["id"], [item["id"] for item in bundle["findings"]])
        later = self.source(
            "external", version="fixture-v2", text="Revised synthetic evidence is a new snapshot."
        )
        after = self.client.get(f"/api/runs/{run['id']}/export").json()
        self.assertNotIn(later["id"], after["run"]["source_ids"])
        self.assertEqual(after["sources"], bundle["sources"])
        self.assertEqual(after["profile"], bundle["profile"])
        self.assertEqual(after["run"]["profile_hash"], run["profile_hash"])

    def test_coverage_does_not_claim_a_live_external_service(self):
        dashboard = self.dashboard()
        self.assertEqual(dashboard["coverage"]["status"], "unverified")
        self.assertTrue(dashboard["coverage"]["message"])
        self.assertTrue(self.session["demo"])
        for source in dashboard["sources"]:
            self.assertIn("synthetic", (source["title"] + " " + source["text"]).lower())

    def test_run_allows_an_internal_only_absence_review_but_not_external_only(self):
        instrument = self.source()
        response = self.client.post(
            "/api/runs",
            json={
                "title": "Incomplete review inputs",
                "as_of": "2026-11-03",
                "source_ids": [instrument["id"]],
                "coverage_note": "Missing external source.",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        external = self.source("external")
        payload = {"title": "External only review", "as_of": "2026-11-03", "source_ids": [external["id"]], "coverage_note": "No internal source supplied"}
        self.assertEqual(self.client.post("/api/runs", json=payload).status_code, 422)


if __name__ == "__main__":
    unittest.main()
