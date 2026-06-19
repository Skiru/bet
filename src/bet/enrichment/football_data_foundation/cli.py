from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .calibration import (
    build_parser,
    calibrate_live,
    options_from_args,
    run_enrich_dry_run,
)
from .scanner_bridge import run_scanner_enrich_dry_run


def _build_scanner_bridge_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Football Data Foundation scanner bridge CLI"
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--scanner-event-file", required=True)
    parser.add_argument("--store-kind", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--force-refresh", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    argv_list = list(argv) if argv is not None else sys.argv[1:]
    if argv_list and argv_list[0] == "scanner-enrich-dry-run":
        args = _build_scanner_bridge_parser().parse_args(argv_list[1:])
        args.command = "scanner-enrich-dry-run"
        run_scanner_enrich_dry_run(args)
        return

    parser = build_parser()
    args = parser.parse_args(argv_list)
    if args.command == "enrich-dry-run":
        run_enrich_dry_run(args)
    else:
        calibrate_live(options_from_args(args))


if __name__ == "__main__":
    main()
