"""Prepare a deterministic, UNLABELED corpus from preserved Georgia PDFs.

Uses the same R-1 PDF extractor as the application. No sentence selection
label is a gold annotation; original source metadata stays unverified.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from importlib.metadata import version
from pathlib import Path
import random
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from compass.pdf_import import extract_pdf
CORPUS_ID = "georgia-language-v1"
ABBREVIATIONS = ("U.S.C.", "U.S.", "C.F.R.", "O.C.G.A.", "Fed. Reg.", "Pub. L.", "No.", "e.g.", "i.e.", "Inc.", "Sec.")
MODALS = (
    ("prohibition", r"\b(?:may|must|shall|will)\s+not\b|\b(?:is|are)\s+prohibited\s+from\b"),
    ("mandatory", r"\b(?:must|shall|(?:is|are)\s+required\s+to)\b"),
    ("permission", r"\bmay\b"),
    ("advisory", r"\bshould\b"),
    ("weaker_drafting", r"\b(?:will|(?:is|are)\s+responsible\s+for|(?:is|are)\s+to)\b"),
)


def bucket(text):
    return next((name for name, pattern in MODALS if re.search(pattern, text, re.I)), "no_modal")


def sentence_spans(page):
    """Independent preparation splitter, not the rules engine under evaluation.

    Paragraphs and bullet items remain candidates for human segmentation review.
    Extraction line wrapping is preserved in each exact page slice.
    """
    protected = set()
    for abbreviation in ABBREVIATIONS:
        for match in re.finditer(re.escape(abbreviation), page, re.I):
            protected.update(i for i in range(match.start(), match.end()) if page[i] == ".")
    # Enumeration letters end labels, not sentences ("shall:\n a. do ...").
    protected.update(match.end() - 1 for match in re.finditer(r"(?<!\w)[a-z]\.(?=\s|$)", page))
    for paragraph in re.finditer(r"\S[^\n]*(?:\n(?![ \t]*\n)[^\n]*)*", page):
        start = paragraph.start()
        for boundary in re.finditer(r"[.!?](?=\s|$)", paragraph.group()):
            end = paragraph.start() + boundary.end()
            if end - 1 in protected:
                continue
            raw = page[start:end]
            left = start + len(raw) - len(raw.lstrip())
            if left < end:
                yield left, end
            start = end
        raw = page[start:paragraph.end()]
        left, end = start + len(raw) - len(raw.lstrip()), paragraph.end()
        if left < end:
            yield left, end


def content_start(page, start, end):
    """Trim leading print furniture/headings without altering the exact slice."""
    lines = page[start:end].splitlines(keepends=True)
    ignored = {"and", "of", "for", "the", "to", "in", "at"}
    for index, line in enumerate(lines[:-1]):
        words = re.findall(r"[A-Za-z][A-Za-z'-]*", line)
        next_words = re.findall(r"[A-Za-z][A-Za-z'-]*", lines[index + 1])
        metadata = re.match(r"\s*(?:field_psg_topics|Issue Date|Effective Date|Review Date|O\.C\.G\.A|PS-\d|PM-\d)", line)
        heading = (0 < len(words) <= 7 and next_words and next_words[0][0].isupper()
                   and not any(re.search(pattern, line, re.I) for _, pattern in MODALS)
                   and all(word[0].isupper() or word.casefold() in ignored for word in words)
                   and not re.search(r"[.!?,;]\s*$", line))
        if metadata or heading:
            start += len(line)
        else:
            break
    return start


def extract_candidates(root=ROOT):
    originals = sorted((root / "case-studies/georgia/instruments").glob("*.pdf"))
    if len(originals) != 7:
        raise ValueError("Expected the seven preserved Georgia instrument PDFs")
    sources, candidates = [], []
    for path in originals:
        relative = str(path.relative_to(root))
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        name = path.name
        # A filename/header tier is a sampling stratum, never legal verification.
        tier = "principles" if name.startswith("5 ") else "guidance" if "GS-" in name else "policy" if "PS-" in name or "SS-25-001" in name else "standard"
        extracted = extract_pdf(path.read_bytes())
        sources.append({"source": relative, "original_sha256": sha, "page_count": extracted["page_count"], "failed_pages": extracted["failed_pages"], "instrument_tier_candidate": tier, "legal_status": "unknown", "verification": "unverified", "effective_from": None, "effective_to": None})
        for span in extracted["page_spans"]:
            page_number = span["page"]
            page = extracted["text"][span["start"]:span["end"]]
            for start, end in sentence_spans(page):
                start = content_start(page, start, end)
                text = page[start:end]
                words = re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", text)
                if not (8 <= len(words) <= 110) or not text.endswith((".", "!", "?")) or not words[0][0].isupper():
                    continue
                if "http" in text or "/topics?" in text or "cookie" in text.lower():
                    continue
                if sum(character.isalpha() for character in text) / max(len(text), 1) < .55:
                    continue
                # Exclude print/browser furniture and bare metadata blocks.
                if re.match(r"^\d+/\d+/\d+,|^(?:Issue Date|Effective Date|Review Date|Topics:|PSG Number:|Title:)", text):
                    continue
                candidates.append({"source": relative, "original_sha256": sha, "page": page_number,
                                   "page_char_start": start, "page_char_end": end, "source_char_start": span["start"] + start, "source_char_end": span["start"] + end, "text": text,
                                   "context_before": page[max(0, start - 300):start], "context_after": page[end:end + 300],
                                   "instrument_tier_candidate": tier, "selection_modal_bucket": bucket(text),
                                   "segmentation_status": "unreviewed", "legal_status": "unknown", "verification": "unverified",
                                   "effective_from": None, "effective_to": None})
    return sources, candidates


def select_cases(candidates, count=150):
    groups = defaultdict(list)
    for case in candidates:
        groups[(case["source"], case["selection_modal_bucket"])].append(case)
    for key, values in groups.items():
        random.Random("compass-evaluation-v1:" + repr(key)).shuffle(values)
    selected = []
    # Round-robin strata oversample uncommon modals and small instrument families.
    # Consequently metrics describe this stratified set, not population prevalence.
    while len(selected) < count and any(groups.values()):
        for key in sorted(groups):
            if groups[key] and len(selected) < count:
                selected.append(groups[key].pop())
    if len(selected) != count:
        raise ValueError(f"Only {len(selected)} eligible excerpts; requested {count}")
    selected.sort(key=lambda case: (case["source"], case["page"], case["page_char_start"]))
    return [{"case_id": f"GA-EVAL-{i:03}", **case} for i, case in enumerate(selected, 1)]


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def prepare(root=ROOT, count=150):
    sources, candidates = extract_candidates(root)
    cases = select_cases(candidates, count)
    return {"schema_version": 1, "corpus_id": CORPUS_ID, "corpus_kind": "uploaded_pdf", "version": "1.0-draft",
            "status": "awaiting_independent_labels", "extraction": {"tool": "compass.pdf_import.extract_pdf / pypdf", "version": version("pypdf"), "offset_basis": "zero-based Unicode character offsets in extracted page and complete R-1 extracted source text"},
            "selection": {"method": "deterministic round-robin source/modal strata", "candidate_count": len(candidates), "seed": "compass-evaluation-v1", "count": count, "modal_counts": dict(Counter(case["selection_modal_bucket"] for case in cases)), "tier_counts": dict(Counter(case["instrument_tier_candidate"] for case in cases)), "limits": "Selection buckets and tier candidates are sampling aids, not independent labels or applicability decisions. Segmentation requires human review."},
            "source_metadata_note": "Unknown legal status/dates have not been inferred from a filename, header, historical effective date or current calendar. The SS-25-001 filename has a PS-25-001 header; its policy stratum is provisional.",
            "sources": sources, "cases": cases}


def label_template(corpus, role):
    return {"schema_version": 1, "corpus_id": corpus["corpus_id"], "corpus_sha256": fingerprint(corpus),
            "role": role, "person_id": None, "completed_at": None, "independently_completed": False,
            "labels": [{"case_id": case["case_id"], "segmentation_approved": None, "obligation_present": None, "actor": None,
                        "modality": None, "condition_present": None, "exception_present": None,
                        "scope_changing_exception": None, "temporal_status": None, "binding_status": None,
                        "notes": ""} for case in corpus["cases"]]}


def write_new(corpus, directory):
    directory.mkdir(parents=True, exist_ok=True)
    paths = [directory / name for name in ("corpus.json", "labeler-a.json", "labeler-b.json", "adjudication.json")]
    if any(path.exists() for path in paths):
        raise ValueError("Refusing to overwrite corpus/labels; prepare into a new version directory")
    paths[0].write_text(json.dumps(corpus, indent=2, ensure_ascii=False) + "\n")
    for path, role in zip(paths[1:], ("labeler_a", "labeler_b", "adjudicator")):
        path.write_text(json.dumps(label_template(corpus, role), indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    corpus = prepare()
    write_new(corpus, args.output_directory)
    print(json.dumps({"status": corpus["status"], "cases": len(corpus["cases"]), "selection": corpus["selection"]}, indent=2))
