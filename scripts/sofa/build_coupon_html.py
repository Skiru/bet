"""Render KUPON_<d>.html (the coupon's legs with filters) from 11_coupon.json.

build_coupon_pdf.py already writes it after every PDF; this is for the HTML
alone (a changed page, no new print record); the iCloud copy follows it
(bet.sofa.icloud_sync). A day marked with results (13_results.json) keeps
them. Exit 0 OK, 1 the iCloud copy failed, 2 failed."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from bet.sofa import coupon_results as cr
from bet.sofa.confidence import coupon_artifact
from bet.sofa.coupon_html import write_html
from bet.sofa.icloud_sync import sync_day
from scripts.sofa.build_family_record import ensure_quietly as ensure_family_record


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
    fam_error = ensure_family_record(args.runs_dir, args.date)
    if fam_error:
        print(f"family_record.json NOT refreshed: {fam_error}", file=sys.stderr)
    # a day already marked keeps its results (a plain render would drop the
    # colours, and the iCloud copy with them); like --with-results it is a
    # view, so the page's mtime - read as "printed" - is kept
    results = cr.load(run)
    html_out = run / f"KUPON_{args.date}.html"
    kept = html_out.stat().st_mtime if results and html_out.exists() else None
    out = write_html(run, doc, args.date, results)
    if kept is not None:
        os.utime(out, (kept, kept))
    icloud = sync_day(args.runs_dir, args.date)
    if icloud.status == "FAILED":
        print(f"iCloud copy NOT written: {icloud.detail}", file=sys.stderr)
    failed = icloud.status == "FAILED"
    print(json.dumps({"stage": "COUPON_HTML", "verdict": "PARTIAL" if failed else "OK",
                      "output_path": str(out), "legs": len(doc.get("singles") or []),
                      "icloud": icloud.as_json()}))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
