"""Run Phase 4 browser checks against isolated local Projects, Output and SQLite.

This helper never removes data. It rejects paths outside the repository's
ignored output directory so a test cannot be pointed at normal user projects.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (ROOT / "output").resolve()
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=OUTPUT / "phase4-isolated")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    data = args.data.resolve()
    if not data.is_relative_to(OUTPUT) or data == OUTPUT:
        parser.error("Test data must be a subdirectory of this repository's output/")
    if not 1024 <= args.port <= 65535 or args.port == 8765:
        parser.error("Choose a non-production local port (default 8766)")

    for child in (data / "projects", data / "output", data / "data", data / "private"):
        if child.is_symlink() or child.exists() and not child.resolve().is_relative_to(data):
            parser.error(f"Refusing linked test data path: {child}")
    database = data / "data" / "pmc_engineering.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.is_symlink() or database.exists() and not database.resolve().is_relative_to(data):
        parser.error(f"Refusing linked test database: {database}")
    if not database.exists():
        shutil.copy2(ROOT / "data" / "pmc_engineering.db", database)
    os.environ["PMC_ENGINEERING_DB"] = str(database)
    os.environ.pop("PMC_LAN", None)

    from manifold import store

    store.PROJECT = data / "projects" / "demo.json"
    store.OUTPUT = data / "output"

    from manifold.ai_design import config
    from manifold import server

    config.path = lambda: data / "private" / "ai-provider.json"
    server.OUTPUT = store.OUTPUT
    base = f"http://127.0.0.1:{args.port}"
    server.host_allowed = lambda host, test_client=False: host in {
        f"127.0.0.1:{args.port}", f"localhost:{args.port}"
    }
    server.endpoints = lambda: {"mode": "local", "urls": [base]}

    import uvicorn

    print(f"PHASE4_ISOLATED_DATA={data}", flush=True)
    uvicorn.run(server.app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
