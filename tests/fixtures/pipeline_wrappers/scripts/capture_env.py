#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> None:
    record_path = Path(os.environ["FIXTURE_RECORD_PATH"])
    payload = {
        "argv": sys.argv[1:],
        "database_url": os.environ.get("DATABASE_URL"),
        "dry_run": os.environ.get("DRY_RUN"),
    }
    record_path.write_text(json.dumps(payload), encoding="utf-8")
    raise SystemExit(int(os.environ.get("FIXTURE_EXIT_CODE", "0")))


if __name__ == "__main__":
    main()
