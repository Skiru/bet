"""Render KUPON_<d>.html (the coupon's legs with filters) from 11_coupon.json.

build_coupon_pdf.py already writes it after every PDF; this is for the HTML
alone (a changed page, no new print record). Exit 0 OK, 2 failed."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from bet.sofa.confidence import coupon_artifact
from bet.sofa.coupon_html import write_html


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True)
    ap.add_argument(
        "--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"))
    args = ap.parse_args()
    run = Path(args.runs_dir) / args.date
    artifact = coupon_artifact(run)
    if artifact.name != "11_coupon.json":
        print("REFUSED: no 11_coupon.json - run build_coupon.py first",
              file=sys.stderr)
        return 2
    doc = json.loads(artifact.read_text(encoding="utf-8"))
    out = write_html(run, doc, args.date)
    print(json.dumps({"stage": "COUPON_HTML", "verdict": "OK",
                      "output_path": str(out), "legs": len(doc.get("singles") or [])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
