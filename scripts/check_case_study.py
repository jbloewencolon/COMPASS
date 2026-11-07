"""Refuse missing or altered original snapshots; sidecar documents may evolve."""

import csv
import hashlib
from pathlib import Path


# Pin the membership as well as the files: deleting manifest rows must not make
# a missing original disappear from verification. Rebaseline only for a reviewed
# intake change, while retaining every existing original and mapping.
MANIFEST_SHA256 = "89d0e07852af0dfed674b0551f09688714ba87d850c7947a08c112052848f2ff"


def check_snapshots(root, rows=None):
    root = Path(root).resolve()
    if rows is None:
        manifest = root / "case-studies/georgia/provenance/upload-manifest.csv"
        if not manifest.is_file():
            return ["Missing preservation manifest"]
        if hashlib.sha256(manifest.read_bytes()).hexdigest() != MANIFEST_SHA256:
            return ["Preservation manifest changed; review membership before rebaselining"]
        with manifest.open() as file:
            rows = list(csv.DictReader(file))
    if not rows:
        return ["Empty preservation manifest"]
    errors = []
    for row in rows:
        path = (root / row["organized_path"]).resolve()
        if not path.is_relative_to(root / "case-studies/georgia"):
            errors.append("Snapshot path is outside the case study: " + row["organized_path"])
        elif not path.is_file():
            errors.append("Missing original snapshot: " + row["organized_path"])
        elif hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            errors.append("Original snapshot changed: " + row["organized_path"])
    return errors


if __name__ == "__main__":
    errors = check_snapshots(Path(__file__).resolve().parents[1])
    if errors:
        print("\n".join(errors))
        raise SystemExit(1)
    print("All original case-study snapshots match their preservation hashes.")
