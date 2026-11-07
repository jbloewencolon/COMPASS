"""Compatibility launcher for the locked, development-only Node browser audit.

Run npm ci first. Arguments are forwarded to scripts/check_ui.mjs; Python
Playwright is no longer required. This helper installs nothing.
"""

from pathlib import Path
import shutil
import subprocess
import sys


if __name__ == "__main__":
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node.js is required for this optional development check")
    raise SystemExit(subprocess.call([node, str(Path(__file__).with_suffix(".mjs")), *sys.argv[1:]]))
