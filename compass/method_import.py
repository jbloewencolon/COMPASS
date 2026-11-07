"""Read the supplied BASE-1 register as pending, provenance-linked suggestions.

This intentionally supports one real producer, not a finding exchange framework.
The workbook's source types, historical scores and inferred owners are retained
as source data. None becomes verification, an assignment or an agency decision.
"""

from collections import Counter
import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = "case-studies/georgia/registers/governance-register-v1.0-BASE-1-2026-07-27.xlsx"
BASELINE = "case-studies/georgia/runs/2026-07-27/GTA-BASE-1-baseline-assessment-2026-07-27.md"
SOURCE_HASHES = {
    WORKBOOK: "f42e3db3f470ad69d7906aa497f3ca00ab2c7ee4887d6ad07a6885914f6c47a4",
    BASELINE: "23f01bfa281f65f3c71a614faf77b77a1184aef5bfcd9187609ea76a9a688ac9",
}
SHEET = "1 Active Findings"
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_PACKAGE = {"p": "http://schemas.openxmlformats.org/package/2006/relationships"}

# Provisional evidence structures, not substantive approval. Mixed findings can
# need splitting after the agency locates the actual passages. F01 and F02 are
# the two concrete structural examples called out by ticket D-1.
TYPE_HINTS = {
    1: "absence", 2: "internal_conflict", 3: "absence", 4: "external_gap",
    5: "absence", 6: "absence", 7: "external_gap", 8: "external_gap",
    9: "absence", 10: "external_gap", 11: "external_gap", 12: "external_gap",
    13: "absence", 14: "absence", 15: "absence", 16: "external_gap",
    17: "absence", 18: "internal_conflict", 19: "internal_conflict",
    20: "internal_conflict", 21: "internal_conflict", 22: "external_gap",
    23: "absence", 24: "external_gap", 25: "absence", 26: "absence",
    27: "absence", 28: "external_gap", 29: "internal_conflict",
    30: "internal_conflict", 31: "external_gap", 32: "external_gap",
    33: "absence", 34: "absence", 35: "absence",
}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _register_rows(path):
    """Read only the named findings sheet; skip worked decision examples."""
    try:
        with zipfile.ZipFile(path) as archive:
            strings = []
            if "xl/sharedStrings.xml" in archive.namelist():
                strings = ["".join(node.itertext()) for node in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("s:si", NS)]
            book = ET.fromstring(archive.read("xl/workbook.xml"))
            sheet = next((node for node in book.findall("s:sheets/s:sheet", NS) if node.get("name") == SHEET), None)
            if sheet is None:
                raise ValueError("The register has no '1 Active Findings' sheet")
            relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            target = next((node.get("Target") for node in relationships.findall("p:Relationship", REL_PACKAGE) if node.get("Id") == sheet.get("{" + REL_NS + "}id")), None)
            if not target or ".." in Path(target).parts:
                raise ValueError("Invalid worksheet location")
            target = target.lstrip("/") if target.startswith("/") else "xl/" + target
            rows = []
            headers = {}
            for row in ET.fromstring(archive.read(target)).findall("s:sheetData/s:row", NS):
                values, formulas = {}, {}
                for cell in row.findall("s:c", NS):
                    column = re.sub(r"\d", "", cell.get("r", ""))
                    value = cell.find("s:v", NS)
                    inline = cell.find("s:is", NS)
                    text = value.text or "" if value is not None else "".join(inline.itertext()) if inline is not None else ""
                    if cell.get("t") == "s":
                        text = strings[int(text)]
                    values[column] = text
                    formula = cell.find("s:f", NS)
                    if formula is not None:
                        formulas[column] = formula.text or ""
                if row.get("r") == "1":
                    headers = values
                    continue
                finding_id = values.get("A", "")
                if not re.fullmatch(r"BASE-2026-01-F\d{2}", finding_id):
                    continue
                rows.append({"row": int(row.get("r")), "fields": {headers.get(column, column): value for column, value in values.items()}, "formulas": {headers.get(column, column): value for column, value in formulas.items()}})
    except (zipfile.BadZipFile, KeyError, ET.ParseError, IndexError) as error:
        raise ValueError("Unreadable governance workbook") from error
    return rows


def convert_georgia_register(root=ROOT):
    """Return the 35 original rows as unresolved suggestions, never decisions."""
    root = Path(root)
    workbook, baseline = root / WORKBOOK, root / BASELINE
    for location, expected_hash in SOURCE_HASHES.items():
        if not (root / location).is_file() or _sha(root / location) != expected_hash:
            raise ValueError("Missing or changed original BASE-1 source: " + location)
    rows = _register_rows(workbook)
    expected = {f"BASE-2026-01-F{number:02}" for number in range(1, 36)}
    ids = [row["fields"].get("ID") for row in rows]
    if len(ids) != 35 or set(ids) != expected:
        raise ValueError("BASE-1 must contain each original finding F01–F35 exactly once")
    baseline_text = baseline.read_text()
    for number in range(1, 36):
        if not re.search(rf"\bF-?{number:02}\b", baseline_text):
            raise ValueError(f"BASE-1 baseline does not reference F{number:02}")
    provenance = {
        "workbook": {"path": WORKBOOK, "sha256": _sha(workbook), "sheet": SHEET},
        "baseline": {"path": BASELINE, "sha256": _sha(baseline)},
    }
    findings = []
    for row in rows:
        fields = row["fields"]
        finding_id = fields["ID"]
        number = int(finding_id[-2:])
        kind = TYPE_HINTS[number]
        gaps = [
            "Historical legal claims and applicability have not been verified for this workspace or review date.",
            "Agency must review the provisional evidence structure; combined issues may require separate findings.",
        ]
        if kind == "absence":
            gaps.insert(0, "No workspace source IDs or authorized completeness review establish the complete in-scope search corpus.")
        elif kind == "internal_conflict":
            gaps.insert(0, "Two or more exact instrument passages must be attached from this run's pinned sources.")
        else:
            gaps.insert(0, "Exact instrument and external-source passages must be attached from this run's pinned sources.")
        if number in {4, 8, 28}:
            gaps.append("Review the linked Georgia ERRATA.md before relying on related legal premises or dates.")
        findings.append({
            "original_finding_id": finding_id,
            "summary": fields["Finding"],
            "category": "stale_reference" if number in {11, 25, 32} else "conflict" if kind == "internal_conflict" else "missing_obligation",
            "severity": {"1": "low", "2": "low", "3": "medium", "4": "high", "5": "critical"}.get(fields.get("Severity"), "medium"),
            "rationale": "Historical BASE-1 suggestion for agency review: " + fields["Finding"],
            "status": "pending",
            "finding_type": kind,
            "evidence": [],
            "search_source_ids": [],
            "search_description": "BASE-1 declares a seven-instrument historical review. This conversion has not searched or confirmed the current workspace corpus." if kind == "absence" else "",
            "evidence_gaps": gaps,
            "method_record": {"sheet": SHEET, **row},
        })
    return {
        "origin": "method_run",
        "run_id": "BASE-1",
        "provenance": provenance,
        "findings": findings,
        "import_report": {
            "total": len(findings), "pending": len(findings),
            "type_counts": dict(Counter(item["finding_type"] for item in findings)),
            "classification_status": "Provisional developer mapping; agency review pending",
            "incomplete_or_needing_type_review": [{"original_finding_id": item["original_finding_id"], "finding_type": item["finding_type"], "reasons": item["evidence_gaps"]} for item in findings],
            "conclusion": "All 35 rows can be preserved as suggestions. None is yet a fully evidenced D-1 finding; this does not establish that a fourth finding type is needed.",
        },
    }


def validate_import_bundle(bundle, root=ROOT):
    """Refuse altered provenance/decisions and return canonical original records.

    This import supports the actual supplied BASE-1 producer only. Another source
    producer is a trigger to revisit this small adapter, not a silent free-form
    authority to claim provenance against arbitrary local files.
    """
    if not isinstance(bundle, dict) or bundle.get("origin") != "method_run" or bundle.get("run_id") != "BASE-1":
        raise ValueError("Expected the BASE-1 method_run bundle")
    canonical = convert_georgia_register(root)
    if bundle.get("provenance") != canonical["provenance"]:
        raise ValueError("Unknown source path, sheet or SHA-256 provenance")
    findings = bundle.get("findings")
    if not isinstance(findings, list) or len(findings) != 35:
        raise ValueError("Expected all 35 BASE-1 suggestions")
    if any(not isinstance(item, dict) or not isinstance(item.get("original_finding_id"), str) for item in findings):
        raise ValueError("Malformed original finding ID")
    if len({item["original_finding_id"] for item in findings}) != 35:
        raise ValueError("Duplicate or malformed original finding IDs")
    expected = {item["original_finding_id"]: item for item in canonical["findings"]}
    for item in findings:
        if not isinstance(item, dict) or item.get("status") != "pending" or any(key in item for key in ("decision", "accepted_by", "applicability")):
            raise ValueError("Method imports must be pending suggestions without recorded decisions or applicability")
        if item != expected.get(item.get("original_finding_id")):
            raise ValueError("Method suggestion differs from its original source row or evidence-gap record")
    if set(bundle) - {"origin", "run_id", "provenance", "findings", "import_report"}:
        raise ValueError("Unsupported method import fields")
    return canonical
