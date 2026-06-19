from __future__ import annotations

from collections.abc import Sequence

from .calibration import build_parser, calibrate_live, options_from_args


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    calibrate_live(options_from_args(args))


if __name__ == "__main__":
    main()
