"""Bounded, page-aware PDF text extraction. This does not perform OCR.

R-1's single runtime dependency is pypdf. The original byte hash and exact
extracted-character spans let reviewers trace an excerpt back to its PDF page.
"""

import hashlib
from io import BytesIO

from pypdf import PdfReader


MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_TEXT_CHARACTERS = 200_000
MAX_PAGES = 500


class PDFImportError(ValueError):
    """A failed extraction with any page failures available to the caller."""

    def __init__(self, message, *, failed_pages=None, page_count=None):
        super().__init__(message)
        self.failed_pages = failed_pages or []
        self.page_count = page_count


def extract_pdf(data):
    """Extract public/non-confidential PDF bytes, or refuse an unusable file.

    Page numbers are one-based. Spans are zero-based, half-open character offsets
    into ``text``. The two newlines between successful pages belong to no page.
    Empty or failed pages appear in ``failed_pages``; they are never implied to
    have been reviewed. No source is persisted by this function.
    """
    if not isinstance(data, bytes) or not data:
        raise PDFImportError("Choose a non-empty PDF file.")
    if len(data) > MAX_PDF_BYTES:
        raise PDFImportError("Choose a PDF no larger than 15 MiB.")
    if not data.startswith(b"%PDF-"):
        raise PDFImportError("This file is not a PDF. Choose a PDF or import plain text.")
    try:
        reader = PdfReader(BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise PDFImportError("Encrypted PDFs are not supported. Supply an authorized, unencrypted copy.")
        page_count = len(reader.pages)
    except PDFImportError:
        raise
    except Exception as error:
        raise PDFImportError("The PDF could not be read. Supply a valid PDF or import plain text.") from error
    if not page_count:
        raise PDFImportError("This PDF has no pages.", page_count=0)
    if page_count > MAX_PAGES:
        raise PDFImportError("Choose a PDF with no more than 500 pages.", page_count=page_count)

    parts, page_spans, failed_pages = [], [], []
    length = 0
    for index in range(page_count):
        page_number = index + 1
        try:
            page_text = reader.pages[index].extract_text() or ""
        except Exception:
            failed_pages.append({"page": page_number, "reason": "Text extraction failed; inspect this page manually."})
            continue
        if not page_text.strip():
            failed_pages.append({"page": page_number, "reason": "No extractable text; inspect this page manually. OCR is not available."})
            continue
        separator = "\n\n" if parts else ""
        start = length + len(separator)
        end = start + len(page_text)
        if end > MAX_TEXT_CHARACTERS:
            raise PDFImportError("Extracted text exceeds 200,000 characters. Split the PDF into smaller documents.",
                                 failed_pages=failed_pages, page_count=page_count)
        parts.extend((separator, page_text))
        page_spans.append({"page": page_number, "start": start, "end": end})
        length = end
    if not page_spans:
        raise PDFImportError("No PDF text could be extracted. Supply a text-based PDF or manually transcribed plain text; OCR is not available.",
                             failed_pages=failed_pages, page_count=page_count)
    return {
        "text": "".join(parts),
        "original_sha256": hashlib.sha256(data).hexdigest(),
        "text_provenance": "extracted",
        "page_spans": page_spans,
        "failed_pages": failed_pages,
        "page_count": page_count,
    }


def evidence_location(page_spans, start, end):
    """Describe an exact nonempty excerpt, including all intersecting PDF pages."""
    if start < 0 or end <= start:
        raise ValueError("Evidence offsets must describe a nonempty text range")
    pages = sorted({span["page"] for span in page_spans
                    if start < span["end"] and end > span["start"]})
    prefix = ("Page " if len(pages) == 1 else "Pages ") + ", ".join(map(str, pages)) + "; " if pages else ""
    return f"{prefix}characters {start + 1}–{end}"
