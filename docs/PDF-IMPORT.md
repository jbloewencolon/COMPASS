# PDF text import

R-1 uses **pypdf 7.0.0**, pinned as the cycle's one named runtime-dependency
exception. Python's standard library can hash and store bytes but cannot decode
PDF page/text operators, fonts and character maps. A general importer or custom
PDF parser would be substantially larger and less reliable. pypdf is maintained,
uses the BSD-3-Clause license, and needs no extra runtime package for the plain,
unencrypted PDFs supported here. No OCR or DOCX parser is installed.

`compass.pdf_import.extract_pdf(data)` accepts PDF bytes and returns:

| Field | Meaning |
|---|---|
| `text` | Extracted page text; two newlines separate successful pages |
| `original_sha256` | SHA-256 of the exact uploaded PDF bytes, independent of the extracted-text snapshot hash |
| `text_provenance` | Always `extracted`; this is not claimed to be original authored plain text |
| `page_spans` | One-based PDF page numbers with zero-based, half-open offsets into `text` |
| `failed_pages` | Original page number and reason for every empty or failed extraction |
| `page_count` | Total original PDF pages, including pages without usable text |

Page labels are not inserted into the source text. `evidence_location(spans,
start, end)` renders intersecting original page numbers alongside character
locations. An excerpt crossing a missing page lists the pages actually represented;
missing text is never invented. Exact extracted quotes remain traceable to their
stored character offsets and original PDF hash. Reviewers should inspect the
original page for layout, tables, footnotes and any extraction uncertainty.

An import is refused before persisting a source when the file is empty, not a
readable PDF, encrypted, larger than 15 MiB, longer than 500 pages, or produces
more than 200,000 text characters. If no page yields text, `PDFImportError` includes
the failed-page list and total page count. A partially readable document returns
its explicit failures for the caller to display; successful text is not a claim
that the whole document was reviewed. This function does not persist original
binary files or silently create an analysis finding.

The regression tests exercise all seven preserved Georgia instrument PDFs: all
64 pages yield text, all original byte hashes are retained, and page spans cover
the expected original page numbers. Synthetic PDFs also test blank pages,
encryption and limits; an injected damaged page tests explicit failure reporting.
These tests check extraction/provenance, not legal applicability or independent
human evaluation labels. Original case-study files remain unchanged.

The optional browser regression uses the locked development Playwright package
against a throwaway local `--demo` instance:

```sh
npm ci
node scripts/check_import_ui.mjs --url http://127.0.0.1:8000
```

Use `--chromium /path/to/chromium` when an existing system browser is preferred.
Only PDF-preview timing and source-submit capture are mocked; login, page rendering
and the seeded review use the actual app. The test refuses stale-file overwrites,
lost partial-extraction warnings and unsupported-file acceptance. It also checks
that editing preserves the original hash while clearing page mappings. Captured
submissions do not create sources. The synthetic owner's view preference changes;
the script refuses nonlocal or non-demo targets.

Only public or non-confidential text is in scope for this local tool. Production
storage, access control and hosting remain subject to the signed-pilot gate.
OCR/DOCX stay deferred until a real supplied document cannot be handled by the
PDF/text paths. Binary retention behavior can be revisited when a pilot records
requirement names it; an original hash by itself is not a retained original file.
