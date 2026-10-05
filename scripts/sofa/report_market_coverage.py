"""MARKET COVERAGE - label every Superbet market OFFER could not read (plan F1.1).

Read-only over the day's artifacts: `01_board.json`, `02_fixtures.json` and
`04_offer.json`. No client, no bridge, no database. It changes nothing OFFER
maps or the coupon selects; it writes a report:

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/report_market_coverage.py \
        --date 2026-10-05

by default to runs/sofa/<d>/market_coverage.json and .md (``--out-json`` /
``--out-md`` elsewhere). The method is in `bet.sofa.market_coverage`.

Exit: 0 OK (every unmapped name has a label), 1 PARTIAL (some names are
UNCLASSIFIED - a rule is missing; they are listed), 2 FAILED (an artifact is
missing or unreadable).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.market_coverage import build_report, render_markdown  # noqa: E402

STAGE = "MARKET_COVERAGE"


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--runs-dir", default=None, help="default: SofaConfig runs_dir")
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--out-md", default=None)
    args = ap.parse_args(argv)

    runs_dir = Path(args.runs_dir or SofaConfig.from_env().runs_dir)
    day = runs_dir / args.date
    try:
        board = _load(day / "01_board.json")
        fixtures = _load(day / "02_fixtures.json")
        offers = _load(day / "04_offer.json")
    except (OSError, ValueError) as exc:
        print(f"{STAGE}: FAILED - {exc}", file=sys.stderr)
        failed = {"stage": STAGE, "verdict": "FAILED", "error": str(exc)}
        print("SOFA_SUMMARY: " + json.dumps(failed))
        return 2

    report = build_report(offers, fixtures, board, date=args.date)
    # Every OFFER refresh rewrites 04_offer.json: say which bytes this report
    # describes.
    report["inputs"] = {}
    for name in ("01_board.json", "02_fixtures.json", "04_offer.json"):
        path = day / name
        mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        report["inputs"][name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "mtime_utc": mtime.isoformat(timespec="seconds"),
        }
    out_json = Path(args.out_json) if args.out_json else day / "market_coverage.json"
    out_md = Path(args.out_md) if args.out_md else day / "market_coverage.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    out_md.write_text(render_markdown(report), encoding="utf-8")

    unclassified = report["by_label"]["UNCLASSIFIED"]
    verdict = "OK" if unclassified["occurrences"] == 0 else "PARTIAL"
    metrics = {
        "fixtures": report["fixtures"],
        "mapped_instances": report["mapped"]["instances"],
        "unmapped_occurrences": report["unmapped"]["occurrences"],
        "unmapped_distinct_names": report["unmapped"]["distinct_names"],
        **{
            f"{lab.lower()}_occurrences": v["occurrences"]
            for lab, v in report["by_label"].items()
        },
        **{
            f"{lab.lower()}_distinct_names": v["distinct_names"]
            for lab, v in report["by_label"].items()
        },
    }
    summary: dict[str, Any] = {
        "stage": STAGE,
        "verdict": verdict,
        "metrics": metrics,
        "output_path": str(out_json),
    }
    print("SOFA_SUMMARY: " + json.dumps(summary))
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
