from __future__ import annotations

from collections.abc import Sequence

from .calibration import (
    build_parser,
    calibrate_live,
    options_from_args,
    run_enrich_dry_run,
)


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "enrich-dry-run":
        run_enrich_dry_run(args)
    else:
        calibrate_live(options_from_args(args))


if __name__ == "__main__":
    main()
