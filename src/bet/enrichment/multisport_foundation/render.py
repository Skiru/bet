from __future__ import annotations

import argparse
from pathlib import Path

from .renderer import render_all
from .verifier import verify_plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Render multisport enrichment wave POC reports.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    outputs = render_all(args.out)
    result = verify_plan()
    print("MULTISPORT_WAVE_RENDER_RESULT_BEGIN")
    print(f"VERDICT={result.verdict}")
    print(f"FAILED_REQUIREMENTS={result.failed_requirements}")
    for key, value in outputs.items():
        print(f"{key.upper()}={value}")
    print("MULTISPORT_WAVE_RENDER_RESULT_END")
    return 0 if result.verdict == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
