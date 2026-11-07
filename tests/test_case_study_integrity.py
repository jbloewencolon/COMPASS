"""Preserve uploaded originals and fail closed on damaged or missing evidence."""

import hashlib
import re
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import unquote

from scripts.check_case_study import check_snapshots


ROOT = Path(__file__).resolve().parents[1]


class CaseStudyIntegrityTests(unittest.TestCase):
    def test_original_uploads_and_errata_snapshot_keys_match(self):
        self.assertEqual(check_snapshots(ROOT), [])
        case = ROOT / "case-studies/georgia"
        text = (case / "ERRATA.md").read_text()
        rows = re.findall(r"^\| S\d+ \| \[([^]]+)\]\(([^)]+)\) \| `([a-f0-9]{64})`", text, re.M)
        self.assertEqual(len(rows), 18)
        self.assertEqual(re.findall(r"^\| (S\d+) \|", text, re.M), [f"S{i:02}" for i in range(1, 19)])
        for name, location, digest in rows:
            file = case / unquote(location)
            self.assertEqual(file.name, name)
            self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), digest)
        self.assertEqual(re.findall(r"^## (E[12]-\d+)", text, re.M), ["E1-01", "E1-02", "E1-03", "E2-01"])
        self.assertIn("agency policy/legal review pending", text)

    def test_altered_and_missing_originals_are_refused(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "case-studies/georgia/example.txt"
            path.parent.mkdir(parents=True)
            path.write_text("Original evidence")
            row = {"organized_path": "case-studies/georgia/example.txt", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            self.assertEqual(check_snapshots(root, [row]), [])
            path.write_text("Silently altered evidence")
            self.assertIn("Original snapshot changed", check_snapshots(root, [row])[0])
            path.unlink()
            self.assertIn("Missing original snapshot", check_snapshots(root, [row])[0])

    def test_snapshot_manifest_cannot_point_outside_case_materials(self):
        errors = check_snapshots(ROOT, [{"organized_path": "compass/app.py", "sha256": "0" * 64}])
        self.assertIn("outside the case study", errors[0])

    def test_empty_missing_or_truncated_manifest_is_refused(self):
        self.assertIn("Empty preservation manifest", check_snapshots(ROOT, [])[0])
        original = ROOT / "case-studies/georgia/provenance/upload-manifest.csv"
        with TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertIn("Missing preservation manifest", check_snapshots(root)[0])
            manifest = root / original.relative_to(ROOT)
            manifest.parent.mkdir(parents=True)
            manifest.write_text("\n".join(original.read_text().splitlines()[:2]) + "\n")
            self.assertIn("Preservation manifest changed", check_snapshots(root)[0])

    def test_neutral_prompt_numbers_are_unique(self):
        files = list((ROOT / "method/prompts").glob("*.md"))
        numbers = [file.name.split("-", 1)[0] for file in files]
        self.assertEqual(len(numbers), len(set(numbers)))
        self.assertIn("06", numbers)


if __name__ == "__main__":
    unittest.main()
