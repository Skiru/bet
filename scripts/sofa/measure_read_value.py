#!/usr/bin/env python3
"""Do the analysts' and the verifier's reads improve the coupon? Every read
football / tennis leg of the days, graded as the ledger grades it
(record_results.graded_confidence: the printed legs and removed:reads, minus
the legs the automatic MODEL_ABOVE_OWN_SAMPLE gate removed), split by who
removed it: hit rate against the mean confidence and the mean
1/odds, flat ROI at the printed price, match bootstrap (95%).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_read_value.py \\
        --from <d> --to <d> [--md-out f]

Read-only evidence (CLAUDE.md "Changing the pipeline" 1), never a gate. The
measured sports' legs are graded apart (coupon_sports) and are not in it.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.confidence import is_sheet_sport  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from scripts.sofa.record_results import graded_confidence  # noqa: E402

Row = dict[str, Any]


def _key(x: dict[str, Any]) -> tuple[Any, ...]:
    line = x.get("line")
    return (int(x["sofascore_event_id"]), x.get("market"),
            str(x.get("subject") or "").lower(),
            None if line is None else float(line), x.get("direction"))


def rows(runs_dir: str, days: list[str], db_path: str) -> list[Row]:
    out: list[Row] = []
    for d in days:
        path = Path(runs_dir) / d / "reads.json"
        if not path.exists():
            continue
        verdict: dict[tuple[Any, ...], tuple[str, str]] = {}
        for r in json.loads(path.read_text(encoding="utf-8")):
            k = _key(r)
            # WATCH / NO_BET win over KEEP, as veto.read_refusal reads them
            if k not in verdict or r["verdict"] != "KEEP":
                verdict[k] = (r["verdict"], r["author"])
        for var in graded_confidence(runs_dir, d, db_path):
            if var["variant"] not in ("official", "removed:reads"):
                continue
            removed = var["variant"] == "removed:reads"
            for pos in var["singles"]:
                src, outcome = pos["source"], str(pos.get("outcome"))
                # the measured sports are graded apart - never pooled here;
                # a leg the automatic gate removed (reason "auto") is no read's
                if not is_sheet_sport(src) or outcome not in (
                        "WIN", "LOSS", "WON", "LOST"):
                    continue
                if removed and src.get("reason") in (None, "auto"):
                    continue
                v = verdict.get(_key(src))
                odds = pos.get("odds") or src.get("offered_odds")
                if v is None or not odds:
                    continue
                out.append({
                    "day": d, "event": int(src["sofascore_event_id"]),
                    "removed": removed, "verdict": v[0],
                    # who removed it, as the coupon records it ("analyst+verifier")
                    "author": str(src.get("reason")) if removed else v[1],
                    "win": outcome in ("WIN", "WON"), "odds": float(odds),
                    "conf": float(src.get("confidence") or 0.0),
                })
    return out


def stats(rs: list[Row]) -> dict[str, float]:
    n = len(rs)
    return {
        "n": n,
        "hit": sum(r["win"] for r in rs) / n,
        "conf": sum(r["conf"] for r in rs) / n,
        "price": sum(1 / r["odds"] for r in rs) / n,
        "roi": sum((r["odds"] - 1) if r["win"] else -1.0 for r in rs) / n,
    }


def bootstrap(rs: list[Row], f: Callable[[list[Row]], float], b: int = 2000,
              seed: int = 1) -> tuple[float, float]:
    by: dict[tuple[str, int], list[Row]] = defaultdict(list)
    for r in rs:
        by[(r["day"], r["event"])].append(r)
    keys = list(by)
    rng = random.Random(seed)
    vals = sorted(f([x for k in rng.choices(keys, k=len(keys)) for x in by[k]])
                  for _ in range(b))
    return vals[int(0.025 * b)], vals[int(0.975 * b) - 1]


def _edge(rs: list[Row]) -> float:
    s = stats(rs)
    return s["hit"] - s["price"]


def diff(rs: list[Row]) -> float:
    """(hit - 1/odds) of the removed legs minus that of the kept legs."""
    kept = [r for r in rs if not r["removed"]]
    gone = [r for r in rs if r["removed"]]
    if not kept or not gone:
        return 0.0
    return _edge(gone) - _edge(kept)


def report(rs: list[Row], first: str, last: str) -> str:
    lines = [f"# Read value {first}..{last} (football / tennis, read and settled legs)",
             "", "| group | n | matches | hit | confidence | 1/odds | ROI | ROI 95% |",
             "|---|---|---|---|---|---|---|---|"]
    gone = [r for r in rs if r["removed"]]
    groups: list[tuple[str, list[Row]]] = [
        ("kept (read, on the coupon)", [r for r in rs if not r["removed"]]),
        ("removed", gone),
        ("removed by analyst", [r for r in gone if "analyst" in r["author"]]),
        ("removed by verifier", [r for r in gone if "verifier" in r["author"]]),
    ]
    for name, g in groups:
        if not g:
            continue
        s = stats(g)
        lo, hi = bootstrap(g, lambda x: stats(x)["roi"])
        matches = len({(r["day"], r["event"]) for r in g})
        lines.append(f"| {name} | {len(g)} | {matches} | {s['hit']:.3f} "
                     f"| {s['conf']:.3f} | {s['price']:.3f} | {100 * s['roi']:+.1f}% "
                     f"| [{100 * lo:+.1f}, {100 * hi:+.1f}] |")
    lo, hi = bootstrap(rs, diff)
    lines += ["", f"(hit - 1/odds) removed minus kept: {100 * diff(rs):+.1f} pp "
              f"[{100 * lo:+.1f}, {100 * hi:+.1f}] (match bootstrap)."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument("--md-out")
    args = ap.parse_args(argv)
    a, b = date.fromisoformat(args.start), date.fromisoformat(args.end)
    days = [(a + timedelta(n)).isoformat() for n in range((b - a).days + 1)]
    rs = rows(args.runs_dir, days, SofaConfig.from_env().db_path)
    if not rs:
        print("no read and settled legs")
        return 1
    text = report(rs, args.start, args.end)
    print(text)
    if args.md_out:
        Path(args.md_out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
