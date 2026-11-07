"""Synthetic permission, evidence, provenance and migration regressions."""

import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

import test_workflow as fixtures
from compass.app import create_app
from compass.store import SCHEMA, Store, canonical, digest


class MilestoneTwoTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.app = create_app(Path(self.tempdir.name) / "test.sqlite3", demo=True)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.counter = 0
        self.login()

    def login(self, persona="ga-owner"):
        return fixtures.WorkflowTests.login(self, persona, appoint=False)

    def source(self, kind="instrument", **changes):
        return fixtures.WorkflowTests.source(self, kind, **{"legal_status": "unknown", "verification": {"status": "unverified"}, **changes})

    review_run = fixtures.WorkflowTests.review_run
    finding_payload = fixtures.WorkflowTests.finding_payload
    finding = fixtures.WorkflowTests.finding
    determination = fixtures.WorkflowTests.determination

    def grant(self, user="ga-owner", enabled=True):
        response = self.client.patch(f"/api/memberships/{user}", json={"can_determine_applicability": enabled})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def reviewed(self, source, **changes):
        payload = {"verification": {"status": "verified", "primary_source_location": "Synthetic official fixture, section 4"}, "legal_status": "in_force", "rationale": "Synthetic reviewer checked the exact exercise source and scope.", **changes}
        response = self.client.patch(f"/api/sources/{source['id']}/review", json=payload)
        self.assertIn(response.status_code, (200, 201), response.text)
        return response.json()

    def app_review(self, finding, **changes):
        payload = {"determination": "persuasive", "rationale": "Synthetic scope review against the declared exercise corpus.", "authority_relied_on": "Synthetic policy basis; no real legal duty asserted.", **changes}
        return self.client.post(f"/api/findings/{finding['id']}/applicability", json=payload)

    def decide(self, finding, outcome="accept"):
        return self.client.post(f"/api/findings/{finding['id']}/decisions", json={"outcome": outcome, "rationale": "Synthetic owner decision after reviewing the recorded evidence."})

    def add_structured(self, run, kind, **changes):
        payload = {"summary": "Synthetic policy issue for structured evidence review", "category": "conflict", "severity": "medium", "rationale": "The synthetic exercise passages need a scoped agency review.", "finding_type": kind, **changes}
        return self.client.post(f"/api/runs/{run['id']}/findings", json=payload)

    def test_permissions_default_off_and_grants_are_explicit_attributed_and_scoped(self):
        members = self.client.get("/api/memberships").json()["memberships"]
        self.assertTrue(members)
        self.assertTrue(all(not member["can_determine_applicability"] for member in members))
        self.assertFalse(self.client.get("/api/session").json()["workspace"]["can_determine_applicability"])
        self.grant()
        self.grant("ga-reviewer")
        self.assertTrue(self.client.get("/api/session").json()["workspace"]["can_determine_applicability"])
        events = self.client.get("/api/audit").json()["events"]
        grants = [event for event in events if event["action"] == "membership.applicability_permission_changed"]
        self.assertEqual(len(grants), 2)
        self.assertTrue(all(event["actor_id"] == "ga-owner" and event["details"] == {"previous": False, "current": True} for event in grants))
        self.login("ga-reviewer")
        self.assertEqual(self.client.patch("/api/memberships/ga-owner", json={"can_determine_applicability": False}).status_code, 403)
        self.assertEqual(self.client.patch("/api/memberships/ca-owner", json={"can_determine_applicability": True}).status_code, 404)

    def test_unappointed_owner_and_reviewer_cannot_verify_or_claim_in_force(self):
        internal, external = self.source(), self.source("external")
        run = self.review_run(internal, external)
        finding = self.finding(run, internal, external)
        for persona in ("ga-owner", "ga-reviewer"):
            self.login(persona)
            with self.subTest(persona=persona):
                self.assertEqual(self.app_review(finding, determination="binding").status_code, 403)
                self.assertEqual(self.app_review(finding, determination="conditional").status_code, 403)
                response = self.client.patch(f"/api/sources/{external['id']}/review", json={"verification": {"status": "verified", "primary_source_location": "Synthetic primary fixture"}, "legal_status": "in_force", "rationale": "Synthetic review requiring an appointed applicability reviewer."})
                self.assertEqual(response.status_code, 403)
                payload = {key: value for key, value in external.items() if key not in {"id", "hash", "created_at"}}
                payload["verification"] = {"status": "unverified"}
                payload["legal_status"] = "in_force"
                self.assertEqual(self.client.post("/api/sources", json=payload).status_code, 403)

    def test_verification_is_server_attributed_and_old_snapshots_remain_unchanged(self):
        internal, external = self.source(), self.source("external")
        run = self.review_run(internal, external)
        finding = self.finding(run, internal, external)
        self.client.post(f"/api/runs/{run['id']}/analyze", json={})
        before = self.client.get(f"/api/runs/{run['id']}/export").json()
        self.grant()
        self.assertEqual(self.app_review(finding, determination="binding").status_code, 422)
        revised = self.reviewed(external)
        self.assertNotEqual(revised["id"], external["id"])
        self.assertEqual(revised["replaces_source_id"], external["id"])
        self.assertEqual(revised["verification"]["verified_by"], "Alex Morgan")
        self.assertEqual(revised["verification"]["verified_by_id"], "ga-owner")
        self.assertTrue(revised["verification"]["verified_at"])
        self.assertEqual(self.client.get(f"/api/sources/{external['id']}").json(), external)
        after = self.client.get(f"/api/runs/{run['id']}/export").json()
        self.assertEqual(before["sources"], after["sources"])
        self.assertEqual(before["analyses"], after["analyses"])
        self.assertEqual(self.app_review(finding, determination="binding").status_code, 422)
        newer_run = self.review_run(internal, revised)
        newer = self.finding(newer_run, internal, revised)
        self.assertEqual(self.app_review(newer, determination="binding").status_code, 200)
        events = self.client.get("/api/audit").json()["events"]
        event = next(event for event in events if event["action"] == "source.reviewed")
        self.assertEqual(event["details"]["previous_legal_status"], "unknown")
        self.assertEqual(event["details"]["current_legal_status"], "in_force")
        self.assertEqual(event["details"]["revised_source_id"], revised["id"])

    def test_forged_verifier_short_rationale_and_missing_authority_are_refused(self):
        internal, external = self.source(), self.source("external")
        run = self.review_run(internal, external)
        finding = self.finding(run, internal, external)
        self.grant()
        payload = {key: value for key, value in external.items() if key not in {"id", "hash", "created_at"}}
        payload["verification"] = {"status": "verified", "primary_source_location": "Synthetic primary", "verified_by": "Invented counsel"}
        self.assertEqual(self.client.post("/api/sources", json=payload).status_code, 422)
        payload["verification"] = {"status": "verified"}
        self.assertEqual(self.client.post("/api/sources", json=payload).status_code, 422)
        self.assertEqual(self.app_review(finding, rationale="Too short").status_code, 422)
        response = self.client.post(f"/api/findings/{finding['id']}/applicability", json={"determination": "persuasive", "rationale": "A long but unsupported rationale without an identified authority."})
        self.assertEqual(response.status_code, 422)

    def test_legacy_duty_determination_cannot_be_newly_accepted_after_upgrade(self):
        internal, external = self.source(), self.source("external")
        run = self.review_run(internal, external)
        finding = self.finding(run, internal, external)
        legacy = {key: value for key, value in finding.items() if key not in {"id", "created_at"}}
        legacy["applicability"] = {"determination": "binding", "rationale": "Historical owner-only review without the newer verification controls.", "reviewed_by": "Alex Morgan", "reviewed_at": "2026-07-27T12:00:00+00:00"}
        with self.app.state.store.connect(write=True) as db:
            db.execute("UPDATE findings SET payload=? WHERE id=?", (canonical(legacy), finding["id"]))
        before = self.client.get(f"/api/findings/{finding['id']}").json()
        response = self.decide(finding)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("fresh applicability review", response.json()["detail"])
        self.assertEqual(self.client.get(f"/api/findings/{finding['id']}").json(), before)
        self.assertEqual(self.decide(finding, "needs_information").status_code, 200)

    def test_repeated_disputed_review_reuses_revision_without_constraint_failure(self):
        external = self.source("external")
        self.grant()
        changes = {"verification": {"status": "disputed", "primary_source_location": "Synthetic source dispute"}, "legal_status": "unknown"}
        first = self.reviewed(external, **changes)
        second = self.reviewed(external, **changes)
        self.assertEqual(first, second)
        self.assertEqual(self.client.get(f"/api/sources/{external['id']}").json(), external)

    def test_legacy_invalid_jurisdiction_review_is_flagged_without_mutating_snapshot(self):
        external = self.source("external")
        legacy = {key: value for key, value in external.items() if key not in {"id", "hash", "created_at"}}
        legacy["jurisdiction_id"] = "US-XX"
        with self.app.state.store.connect(write=True) as db:
            db.execute("UPDATE sources SET payload=?,content_hash=? WHERE id=?", (canonical(legacy), digest(legacy), external["id"]))
        before = self.client.get(f"/api/sources/{external['id']}").json()
        self.grant()
        response = self.client.patch(f"/api/sources/{external['id']}/review", json={"verification": {"status": "disputed"}, "legal_status": "unknown", "rationale": "Synthetic review flags an invalid historical jurisdiction identifier."})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("Historical source metadata", response.json()["detail"])
        self.assertEqual(self.client.get(f"/api/sources/{external['id']}").json(), before)

    def test_appointed_reviewer_can_determine_but_cannot_accept(self):
        internal, external = self.source(), self.source("external")
        self.grant("ga-reviewer")
        self.login("ga-reviewer")
        revised = self.reviewed(external)
        run = self.review_run(internal, revised)
        finding = self.finding(run, internal, revised)
        self.assertEqual(self.app_review(finding, determination="binding").status_code, 200)
        self.assertEqual(self.decide(finding).status_code, 403)
        self.login()
        self.assertEqual(self.decide(finding).status_code, 200)

    def test_absence_requires_actual_search_and_authorized_corpus_confirmation(self):
        internal = self.source()
        run = self.review_run(internal)
        response = self.add_structured(run, "absence", evidence=[], search_source_ids=[internal["id"]], search_description="Searched every paragraph in the selected synthetic instrument for review rights.", concentrated_harm=True, irreversible=False)
        self.assertEqual(response.status_code, 201, response.text)
        finding = response.json()
        self.assertEqual(finding["evidence"], [])
        self.assertEqual(self.app_review(finding).status_code, 200)
        self.assertEqual(self.decide(finding).status_code, 409)
        self.assertEqual(self.app_review(finding, scope_complete=True).status_code, 403)
        self.grant()
        self.assertEqual(self.app_review(finding, scope_complete=True).status_code, 200)
        self.assertEqual(self.decide(finding).status_code, 200)
        exported = self.client.get(f"/api/runs/{run['id']}/export").json()["findings"][0]
        self.assertTrue(exported["concentrated_harm"])
        self.assertFalse(exported["irreversible"])
        self.assertEqual(exported["applicability"]["completeness_confirmed_by"], "ga-owner")
        self.assertEqual(self.add_structured(run, "absence", evidence=[], search_source_ids=[], search_description="Searched the complete synthetic corpus for the missing policy element.").status_code, 422)
        quote = {"source_id": internal["id"], "quote": internal["text"], "location": "Synthetic paragraph"}
        self.assertEqual(self.add_structured(run, "absence", evidence=[quote], search_source_ids=[internal["id"]], search_description="Searched the synthetic corpus but invented a quotation for the absence.").status_code, 422)
        other = self.source()
        self.assertEqual(self.add_structured(run, "absence", evidence=[], search_source_ids=[other["id"]], search_description="Searched another instrument outside the pinned review corpus.").status_code, 422)
        wider_run = self.review_run(internal, other)
        partial = self.add_structured(wider_run, "absence", evidence=[], search_source_ids=[internal["id"]], search_description="Searched only the first source in a two-source declared review corpus.").json()
        self.assertEqual(self.app_review(partial, scope_complete=True).status_code, 422)

    def test_internal_conflict_accepts_instrument_passages_and_refuses_external_or_unpinned(self):
        first, second, external = self.source(text="The office reviews each month."), self.source(text="The office reviews each year."), self.source("external")
        run = self.review_run(first, second, external)
        evidence = [{"source_id": source["id"], "quote": source["text"], "location": "Synthetic paragraph"} for source in (first, second)]
        response = self.add_structured(run, "internal_conflict", evidence=evidence)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["finding_type"], "internal_conflict")
        self.assertEqual(self.add_structured(run, "internal_conflict", evidence=[*evidence[:1], {"source_id": external["id"], "quote": external["text"], "location": "Paragraph"}]).status_code, 422)
        self.assertEqual(self.add_structured(run, "internal_conflict", evidence=[evidence[0], evidence[0]]).status_code, 422)
        self.assertEqual(self.add_structured(run, "internal_conflict", evidence=[evidence[0], {**evidence[0], "location": "Invented second location"}]).status_code, 422)
        third = self.source()
        self.assertEqual(self.add_structured(run, "internal_conflict", evidence=[evidence[0], {"source_id": third["id"], "quote": third["text"], "location": "Paragraph"}]).status_code, 422)
        self.assertEqual(self.add_structured(run, "external_gap", evidence=evidence).status_code, 422)

    def test_new_authority_pathways_require_attachment_and_court_material_stays_flag_only(self):
        self.grant()
        internal = self.source()
        for authority in ("funding_condition", "agreement", "court_or_ag"):
            with self.subTest(authority=authority):
                external = self.source("external", authority_type=authority)
                revised = self.reviewed(external)
                run = self.review_run(internal, revised)
                finding = self.finding(run, internal, revised)
                self.assertEqual(self.app_review(finding, determination="binding").status_code, 422)
                if authority == "court_or_ag":
                    self.assertEqual(self.app_review(finding, determination="conditional").status_code, 422)
                    self.assertEqual(self.app_review(finding).status_code, 200)
                else:
                    attached = self.finding(run, internal, revised, program_or_contract="Synthetic program grant 2026 / defined exercise scope")
                    self.assertEqual(self.app_review(attached, determination="binding").status_code, 200)

    def test_us_ids_and_pdf_provenance_are_validated_and_exported(self):
        internal = self.source()
        template = {key: value for key, value in internal.items() if key not in {"id", "hash", "created_at"}}
        template["verification"] = {"status": "unverified"}
        for jurisdiction in ("US-XX", "US-PR", "US", "Georgia"):
            with self.subTest(jurisdiction=jurisdiction):
                self.assertEqual(self.client.post("/api/sources", json={**template, "jurisdiction_id": jurisdiction}).status_code, 422)
        self.assertEqual(self.client.post("/api/sources", json={**template, "kind": "external", "jurisdiction_id": "US-XX"}).status_code, 422)
        foreign = self.source("external", jurisdiction_id="EU", authority_type="regulation")
        self.assertEqual(foreign["authority_type"], "regulation")
        text = "Synthetic extracted page text."
        extracted = self.source(text=text, text_provenance="extracted", original_sha256="a" * 64, page_count=2, page_spans=[{"page": 1, "start": 0, "end": len(text)}], failed_pages=[{"page": 2, "reason": "Synthetic image-only page"}])
        run = self.review_run(extracted)
        source = self.client.get(f"/api/runs/{run['id']}/export").json()["sources"][0]
        self.assertEqual(source["original_sha256"], "a" * 64)
        self.assertEqual(source["failed_pages"][0]["page"], 2)
        invalid = {**template, "text": text, "text_provenance": "extracted", "original_sha256": "a" * 64, "page_count": 2, "page_spans": [{"page": 1, "start": 0, "end": len(text)}]}
        self.assertEqual(self.client.post("/api/sources", json=invalid).status_code, 422)
        invalid["page_spans"][0]["end"] = len(text) + 1
        self.assertEqual(self.client.post("/api/sources", json=invalid).status_code, 422)
        transcribed = {**invalid, "text_provenance": "transcribed", "page_spans": [], "failed_pages": [{"page": 2, "reason": "Original extraction was incomplete"}]}
        self.assertEqual(self.client.post("/api/sources", json=transcribed).status_code, 201)


class SchemaMigrationTests(unittest.TestCase):
    def test_legacy_upgrade_preserves_every_payload_and_does_not_add_tables(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "old.sqlite3"
            old_schema = SCHEMA.replace("    can_determine_applicability INTEGER NOT NULL DEFAULT 0 CHECK(can_determine_applicability IN (0,1)),\n", "").replace("instrument_source_id TEXT, external_source_id TEXT,", "instrument_source_id TEXT NOT NULL, external_source_id TEXT NOT NULL,")
            with sqlite3.connect(path) as db:
                db.executescript(old_schema)
                db.execute("INSERT INTO tenants VALUES(?,?,?,?,?)", ("office", "Synthetic", "US-GA", "{}", "profile-hash"))
                db.execute("INSERT INTO users VALUES(?,?)", ("owner", "Synthetic Owner"))
                db.execute("INSERT INTO memberships VALUES(?,?,?)", ("office", "owner", "owner"))
                for source_id in ("internal", "external"):
                    payload = canonical({"text": "Historical text", "kind": source_id})
                    db.execute("INSERT INTO sources VALUES(?,?,?,?,?)", (source_id, "office", payload, digest(payload + source_id), "original-time"))
                db.execute("INSERT INTO runs VALUES(?,?,?,?)", ("review", "office", canonical({"profile": "original snapshot"}), "original-time"))
                db.execute("INSERT INTO findings VALUES(?,?,?,?,?,?,?)", ("finding", "office", "review", "internal", "external", canonical({"status": "pending", "evidence": "original"}), "original-time"))
                before = {table: db.execute(f"SELECT * FROM {table}").fetchall() for table in ("sources", "runs", "findings")}
                tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
            store = Store(path)
            Store(path)
            with store.connect() as db:
                after = {table: [tuple(row) for row in db.execute(f"SELECT * FROM {table}")] for table in before}
                self.assertEqual(after, before)
                self.assertEqual([tuple(row) for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")], tables)
                self.assertEqual(db.execute("SELECT can_determine_applicability FROM memberships").fetchone()[0], 0)
                columns = {row[1]: row for row in db.execute("PRAGMA table_info(findings)")}
                self.assertFalse(columns["instrument_source_id"][3])
                self.assertFalse(columns["external_source_id"][3])
                self.assertEqual(list(db.execute("PRAGMA foreign_key_check")), [])

    def test_invalid_legacy_references_refuse_and_roll_back_schema_migration(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "broken-old.sqlite3"
            old_schema = SCHEMA.replace("    can_determine_applicability INTEGER NOT NULL DEFAULT 0 CHECK(can_determine_applicability IN (0,1)),\n", "").replace("instrument_source_id TEXT, external_source_id TEXT,", "instrument_source_id TEXT NOT NULL, external_source_id TEXT NOT NULL,")
            with sqlite3.connect(path) as db:
                db.executescript(old_schema)
                db.execute("INSERT INTO users VALUES(?,?)", ("owner", "Synthetic Owner"))
                db.execute("INSERT INTO memberships VALUES(?,?,?)", ("missing-office", "owner", "owner"))
            with self.assertRaisesRegex(sqlite3.IntegrityError, "rolled back"):
                Store(path)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute("SELECT * FROM memberships").fetchall(), [("missing-office", "owner", "owner")])
                self.assertNotIn("can_determine_applicability", {row[1] for row in db.execute("PRAGMA table_info(memberships)")})
                self.assertFalse(db.execute("SELECT name FROM sqlite_master WHERE name='findings_migration'").fetchall())
