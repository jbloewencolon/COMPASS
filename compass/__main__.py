import argparse
from pathlib import Path

import uvicorn

from .app import create_app


def main():
    parser = argparse.ArgumentParser(description="Run the local COMPASS review foundation")
    parser.add_argument("--demo", action="store_true", help="Enable synthetic fixtures and local demonstration personas")
    parser.add_argument("--db", default=".compass/development.sqlite3", type=Path)
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    # No public bind option: local demo identity must not become public auth.
    uvicorn.run(create_app(args.db, demo=args.demo, run_worker=True), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
