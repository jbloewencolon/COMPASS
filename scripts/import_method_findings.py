"""Produce BASE-1 suggestion JSON, optionally import it into a signed-in workspace.

The cookie file is an explicitly supplied Netscape/Mozilla cookie jar from a local
development session. Session values are never printed or accepted on the command
line. No original workbook, baseline, decision or prior run snapshot is overwritten.
"""

import argparse
import http.cookiejar
import json
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request


# Permit direct invocation from a checkout without requiring an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compass.method_import import convert_georgia_register, validate_import_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/method-import/georgia-base-1-suggestions.json"))
    parser.add_argument("--input", type=Path, help="Validate a previously generated bundle instead of converting")
    parser.add_argument("--post-run", help="Import suggestions into this existing run; otherwise only write JSON")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Local COMPASS base URL")
    parser.add_argument("--cookie-file", type=Path, help="Netscape/Mozilla cookie jar; required with --post-run")
    args = parser.parse_args()
    try:
        supplied = json.loads(args.input.read_text()) if args.input else convert_georgia_register()
        bundle = validate_import_bundle(supplied)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n")
        if args.post_run:
            url = urllib.parse.urlsplit(args.url)
            if url.scheme not in {"http", "https"} or not url.netloc or url.username or url.password or url.query or url.fragment:
                raise ValueError("Use a COMPASS base URL without credentials, query or fragment")
            if not args.cookie_file:
                raise ValueError("--cookie-file is required for an authenticated import")
            cookies = http.cookiejar.MozillaCookieJar(str(args.cookie_file))
            cookies.load(ignore_discard=True)
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
            run_id = urllib.parse.quote(args.post_run, safe="")
            request = urllib.request.Request(args.url.rstrip("/") + f"/api/runs/{run_id}/method-findings", data=json.dumps(bundle).encode(), headers={"Content-Type": "application/json"}, method="POST")
            with opener.open(request, timeout=30) as response:
                result = json.load(response)
            counts = {key: len(result[key]) if isinstance(result.get(key), list) else result.get(key) for key in ("imported", "skipped") if key in result}
            print(json.dumps({"status": "imported", "run_id": args.post_run, **counts}, ensure_ascii=False))
        else:
            print(json.dumps({"status": "prepared", "suggestions": 35, "output": str(args.output), "incomplete_or_needing_type_review": 35}))
    except (ValueError, OSError, urllib.error.HTTPError) as error:
        # Do not echo request headers, cookie contents or a URL with credentials.
        if isinstance(error, urllib.error.HTTPError):
            print(f"Import refused by COMPASS (HTTP {error.code}); no decisions were recorded.", file=sys.stderr)
        else:
            print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
