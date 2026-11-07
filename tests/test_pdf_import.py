"""R-1 imports real Georgia PDFs and refuses unusable evidence without OCR."""

import hashlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from compass.pdf_import import PDFImportError, evidence_location, extract_pdf


ROOT = Path(__file__).resolve().parents[1]


def pdf_bytes(texts, *, encrypted=False):
    """Small actual PDFs; no fixture-generation dependency is needed."""
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        if text is not None:
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                     NameObject("/Subtype"): NameObject("/Type1"),
                                     NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode())
            page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("synthetic-test-password", algorithm="RC4-128")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class PDFImportTests(unittest.TestCase):
    def test_all_seven_georgia_instruments_keep_original_hash_and_page_offsets(self):
        paths = list((ROOT / "case-studies/georgia/instruments").glob("*.pdf"))
        self.assertEqual(len(paths), 7)
        total_pages = 0
        for path in paths:
            with self.subTest(document=path.name):
                data = path.read_bytes()
                result = extract_pdf(data)
                self.assertEqual(result["original_sha256"], hashlib.sha256(data).hexdigest())
                self.assertEqual(result["text_provenance"], "extracted")
                self.assertEqual(result["failed_pages"], [])
                spans = result["page_spans"]
                self.assertEqual([span["page"] for span in spans], list(range(1, result["page_count"] + 1)))
                previous_end = -1
                for span in spans:
                    self.assertGreater(span["start"], previous_end)
                    self.assertTrue(result["text"][span["start"]:span["end"]].strip())
                    self.assertIn(f"Page {span['page']};", evidence_location(spans, span["start"], span["end"]))
                    previous_end = span["end"]
                total_pages += result["page_count"]
        self.assertEqual(total_pages, 64)

    def test_blank_page_is_reported_and_later_page_keeps_its_original_number(self):
        result = extract_pdf(pdf_bytes(["First page text.", None, "Third page text."]))
        self.assertEqual(result["page_count"], 3)
        self.assertEqual([span["page"] for span in result["page_spans"]], [1, 3])
        self.assertEqual([failure["page"] for failure in result["failed_pages"]], [2])
        self.assertIn("OCR is not available", result["failed_pages"][0]["reason"])
        for span, expected in zip(result["page_spans"], ("First page text.", "Third page text.")):
            self.assertEqual(result["text"][span["start"]:span["end"]].strip(), expected)
        first, third = result["page_spans"]
        self.assertEqual(evidence_location(result["page_spans"], first["start"], third["end"]),
                         f"Pages 1, 3; characters 1–{third['end']}")

    def test_page_extraction_error_is_reported_instead_of_silently_omitted(self):
        bad_page = Mock()
        bad_page.extract_text.side_effect = RuntimeError("synthetic damaged text object")
        good_page = Mock()
        good_page.extract_text.return_value = "A readable second page."
        reader = SimpleNamespace(is_encrypted=False, pages=[bad_page, good_page])
        with patch("compass.pdf_import.PdfReader", return_value=reader):
            result = extract_pdf(b"%PDF-synthetic")
        self.assertEqual(result["failed_pages"], [{"page": 1, "reason": "Text extraction failed; inspect this page manually."}])
        self.assertEqual(result["page_spans"], [{"page": 2, "start": 0, "end": 23}])

    def test_empty_non_pdf_and_malformed_pdf_are_refused(self):
        for data in (b"", b"ordinary Markdown text", b"%PDF-1.7\nnot a valid object stream"):
            with self.subTest(data=data), self.assertRaises(PDFImportError):
                extract_pdf(data)

    def test_encrypted_pdf_is_refused_even_if_it_has_extractable_text(self):
        with self.assertRaisesRegex(PDFImportError, "Encrypted PDFs"):
            extract_pdf(pdf_bytes(["Confidential-looking synthetic text."], encrypted=True))

    def test_all_blank_pdf_is_refused_with_explicit_page_failures(self):
        with self.assertRaises(PDFImportError) as caught:
            extract_pdf(pdf_bytes([None, None]))
        self.assertIn("OCR is not available", str(caught.exception))
        self.assertEqual(caught.exception.page_count, 2)
        self.assertEqual([item["page"] for item in caught.exception.failed_pages], [1, 2])

    def test_file_text_and_page_limits_refuse_the_whole_import(self):
        data = pdf_bytes(["Public synthetic text."])
        with patch("compass.pdf_import.MAX_PDF_BYTES", len(data) - 1):
            with self.assertRaisesRegex(PDFImportError, "15 MiB"):
                extract_pdf(data)
        with patch("compass.pdf_import.MAX_TEXT_CHARACTERS", 5):
            with self.assertRaisesRegex(PDFImportError, "200,000 characters"):
                extract_pdf(data)
        with patch("compass.pdf_import.MAX_PAGES", 1):
            with self.assertRaisesRegex(PDFImportError, "500 pages"):
                extract_pdf(pdf_bytes(["First page.", "Second page."]))

    def test_empty_evidence_offsets_are_refused_and_unmapped_text_has_no_fake_page(self):
        with self.assertRaises(ValueError):
            evidence_location([], 3, 3)
        self.assertEqual(evidence_location([], 0, 8), "characters 1–8")


if __name__ == "__main__":
    unittest.main()
