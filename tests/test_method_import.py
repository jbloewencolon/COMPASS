"""BASE-1 conversion preserves source claims without inventing legal approval."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from compass.method_import import BASELINE, ROOT, WORKBOOK, convert_georgia_register, validate_import_bundle


class MethodImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = convert_georgia_register()

    def test_all_35_original_rows_become_pending_suggestions(self):
        bundle = self.bundle
        self.assertEqual(bundle["origin"], "method_run")
        self.assertEqual(bundle["run_id"], "BASE-1")
        self.assertEqual([row["original_finding_id"] for row in bundle["findings"]], [f"BASE-2026-01-F{number:02}" for number in range(1, 36)])
        self.assertEqual({row["status"] for row in bundle["findings"]}, {"pending"})
        self.assertTrue(all(row["evidence"] == [] and row["evidence_gaps"] for row in bundle["findings"]))
        self.assertTrue(all("decision" not in row and "applicability" not in row for row in bundle["findings"]))
        self.assertEqual(len(bundle["import_report"]["incomplete_or_needing_type_review"]), 35)
        self.assertEqual(bundle["findings"][0]["finding_type"], "absence")
        self.assertEqual(bundle["findings"][1]["finding_type"], "internal_conflict")
        self.assertEqual(bundle["findings"][3]["finding_type"], "external_gap")
        self.assertEqual(validate_import_bundle(bundle), bundle)

    def test_preserves_historical_fields_formulas_and_real_file_hashes(self):
        first = self.bundle["findings"][0]
        self.assertEqual(first["method_record"]["row"], 2)
        self.assertEqual(first["method_record"]["fields"]["Evidence tier"], "E1")
        self.assertEqual(first["method_record"]["fields"]["Status"], "OPEN")
        self.assertEqual(first["method_record"]["fields"]["Priority"], "20")
        self.assertIn("G2*H2", first["method_record"]["formulas"]["Priority"])
        self.assertEqual(first["method_record"]["fields"]["Owner"], "State CIO")
        self.assertNotIn("assignment", first)
        for record in self.bundle["provenance"].values():
            self.assertEqual(hashlib.sha256((ROOT / record["path"]).read_bytes()).hexdigest(), record["sha256"])

    def test_generated_json_is_reproducible_from_the_originals(self):
        path = ROOT / "data/method-import/georgia-base-1-suggestions.json"
        self.assertEqual(json.loads(path.read_text()), self.bundle)

    def test_forged_acceptance_or_applicability_is_refused(self):
        for extra in ({"status": "accepted"}, {"decision": {"outcome": "accept"}}, {"applicability": {"determination": "binding"}}, {"accepted_by": "Invented reviewer"}):
            with self.subTest(extra=extra):
                bundle = deepcopy(self.bundle)
                bundle["findings"][0].update(extra)
                with self.assertRaisesRegex(ValueError, "pending suggestions"):
                    validate_import_bundle(bundle)

    def test_duplicate_omitted_or_unknown_ids_are_refused(self):
        duplicate = deepcopy(self.bundle)
        duplicate["findings"][1] = deepcopy(duplicate["findings"][0])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_import_bundle(duplicate)
        omitted = deepcopy(self.bundle)
        omitted["findings"].pop()
        with self.assertRaisesRegex(ValueError, "all 35"):
            validate_import_bundle(omitted)
        unknown = deepcopy(self.bundle)
        unknown["findings"][0]["original_finding_id"] = "Invented-F01"
        with self.assertRaisesRegex(ValueError, "differs"):
            validate_import_bundle(unknown)

    def test_unknown_paths_false_hashes_and_altered_rows_are_refused(self):
        for field, value in (("path", "../../not-a-source"), ("sha256", "0" * 64), ("sheet", "3 Accepted")):
            with self.subTest(field=field):
                bundle = deepcopy(self.bundle)
                bundle["provenance"]["workbook"][field] = value
                with self.assertRaisesRegex(ValueError, "provenance"):
                    validate_import_bundle(bundle)
        for field, value in (("summary", "A fabricated conclusion"), ("evidence", [{"quote": "An invented quote"}]), ("evidence_gaps", [])):
            with self.subTest(field=field):
                bundle = deepcopy(self.bundle)
                bundle["findings"][0][field] = value
                with self.assertRaisesRegex(ValueError, "differs"):
                    validate_import_bundle(bundle)

    def test_malformed_ids_are_validation_errors(self):
        for value in (None, {}, [], 1):
            bundle = deepcopy(self.bundle)
            bundle["findings"][0]["original_finding_id"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_import_bundle(bundle)

    def test_changed_original_source_is_refused_without_editing_the_real_file(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for relative in (WORKBOOK, BASELINE):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / relative).read_bytes())
            (root / BASELINE).write_text("An altered baseline")
            with self.assertRaisesRegex(ValueError, "changed original"):
                convert_georgia_register(root)

    def test_cli_writes_only_validated_pending_json(self):
        script = ROOT / "scripts/import_method_findings.py"
        with TemporaryDirectory() as folder:
            output = Path(folder) / "suggestions.json"
            result = subprocess.run([sys.executable, str(script), "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text()), self.bundle)
            forged = deepcopy(self.bundle)
            forged["findings"][0]["status"] = "accepted"
            source = Path(folder) / "forged.json"
            source.write_text(json.dumps(forged))
            before = output.read_bytes()
            result = subprocess.run([sys.executable, str(script), "--input", str(source), "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("pending suggestions", result.stderr)
            self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
