"""PDF previews are authenticated, explicit about limits, and pinned as sources."""

from pathlib import Path
import unittest

import test_workflow as fixtures


ROOT = Path(__file__).resolve().parents[1]


class PDFAPITests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    login = fixtures.WorkflowTests.login
    review_run = fixtures.WorkflowTests.review_run

    def test_seven_actual_pdfs_import_with_original_hashes_and_page_evidence(self):
        sources = []
        page_count = 0
        for file in sorted((ROOT / "case-studies/georgia/instruments").glob("*.pdf")):
            preview = self.client.post("/api/import/pdf-text", content=file.read_bytes(), headers={"Content-Type": "application/pdf"})
            self.assertEqual(preview.status_code, 200, preview.text)
            extracted = preview.json()
            payload = {**extracted, "kind": "instrument", "title": file.name, "jurisdiction_id": "US-GA",
                       "version": "preserved-upload", "authority_type": "internal_policy", "legal_status": "unknown"}
            imported = self.client.post("/api/sources", json=payload)
            self.assertEqual(imported.status_code, 201, imported.text)
            saved = imported.json()
            self.assertEqual(saved["original_sha256"], extracted["original_sha256"])
            self.assertEqual(saved["page_spans"], extracted["page_spans"])
            self.assertEqual(saved["failed_pages"], [])
            self.assertEqual(saved["verification"]["status"], "unverified")
            sources.append(saved)
            page_count += saved["page_count"]
        self.assertEqual(len(sources), 7)
        self.assertEqual(page_count, 64)
        run = self.review_run(*sources)
        analysis = self.client.post(f"/api/runs/{run['id']}/analyze", json={})
        self.assertEqual(analysis.status_code, 200, analysis.text)
        quotes = [quote for item in analysis.json()["features"]["obligations"]["items"] for quote in item["evidence"]]
        self.assertTrue(quotes)
        for quote in quotes:
            self.assertIn("Page", quote["location"])
        exported = self.client.get(f"/api/runs/{run['id']}/export").json()
        self.assertEqual(len(exported["sources"]), 7)
        self.assertTrue(all(item["original_sha256"] and item["text_provenance"] == "extracted" for item in exported["sources"]))

    def test_failed_previews_do_not_create_sources_or_bypass_session_guards(self):
        before = self.client.get("/api/sources").json()
        self.assertEqual(self.client.post("/api/import/pdf-text", content=b"not a PDF", headers={"Content-Type": "application/pdf"}).status_code, 422)
        self.assertEqual(self.client.post("/api/import/pdf-text", content=b"text", headers={"Content-Type": "text/plain"}).status_code, 415)
        self.assertEqual(self.client.post("/api/import/pdf-text", content=b"%PDF-", headers={"Content-Type": "application/pdf", "Origin": "https://example.invalid"}).status_code, 403)
        self.assertEqual(self.client.get("/api/sources").json(), before)
        self.client.post("/api/logout")
        response = self.client.post("/api/import/pdf-text", content=b"%PDF-", headers={"Content-Type": "application/pdf"})
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
