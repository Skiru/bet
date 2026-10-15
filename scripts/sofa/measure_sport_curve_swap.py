#!/usr/bin/env python3
"""Read-only evidence: one measured sport's settled Superbet lines read
through two history curves - the one a day reads today and a candidate.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sport_curve_swap.py \\
        --sport basketball --rows <dir>/basketball_superbet_settled.jsonl \\
        --old config/sofa_sport_confidence_calibration.next.json \\
        --new <dir>/basketball_section.json --from 2026-10-05 --to 2026-10-14 \\
        [--json-out f] [--md-out f]

The rows are fit_sport_confidence.py's `--rows-out` Superbet rows: the model's
p of each settled line (one estimator for both curves), its outcome. A
confidence is the curve's bucket lo95 with n >= min_bucket, admission not
required (SportCalibration.lookup(require_admitted=False), the line-evidence
reading) and without the line evidence - a check of the curve alone.

* log-loss of the confidence, candidate - today, paired on the lines both
  curves read, 95% from a bootstrap over games;
* calibration at confidence >= 0.70 per curve (all, per family, per key):
  lines, games, mean confidence, realised, realised - confidence [95%];
* printable lines per family: confidence >= 0.70, and the coupon's price
  gates as well (confidence x odds >= 0.90, overround <= 15%) - the odds are
  joined from runs/sofa/shadow/<sport>/<d>/settled.json for that count only.

No price enters a confidence. Writes nothing but --json-out / --md-out.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.confidence import COUPON_PROFILE  # noqa: E402
from bet.sofa.sport_confidence import (  # noqa: E402
    MIN_BUCKET,
    PRINTABLE_FROM,
    SportCalibration,
)

BOOT = 2000
SEED = 0
MIN_X = COUPON_PROFILE.min_ev or 1.0
MAX_MARGIN = COUPON_PROFILE.max_overround
Row = dict[str, Any]
Stat = dict[str, Any]


def load_rows(path: Path, start: str, end: str) -> list[Row]:
    out: list[Row] = []
    with path.open(encoding="utf-8") as f:
        for raw in f:
            r = json.loads(raw)
            if start <= str(r.get("date") or "") <= end:
                out.append(r)
    return out


def _sel(r: Row) -> tuple[Any, ...]:
    line = r.get("line")
    return (int(r["market_id"]), int(r.get("period") or 0),
            str(r.get("subject") or ""),
            None if line is None else float(line), str(r["side"]))


def attach_prices(rows: list[Row], runs_dir: Path, sport: str) -> int:
    """odds / overround of each row's graded selection (count only)."""
    book: dict[tuple[str, str], dict[tuple[Any, ...], dict[str, Any]]] = {}
    for date in sorted({str(r["date"]) for r in rows}):
        path = runs_dir / "shadow" / sport / date / "settled.json"
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        for sb_id, entry in (doc.get("events") or {}).items():
            sel: dict[tuple[Any, ...], dict[str, Any]] = {}
            for g in entry.get("graded") or []:
                sel.setdefault(_sel(g), g)
            book[(date, str(sb_id))] = sel
    found = 0
    for r in rows:
        sb_id = str(r["game"]).split(":")[-1]
        g = book.get((str(r["date"]), sb_id), {}).get(_sel(r))
        if g is not None and g.get("odds"):
            r["odds"] = float(g["odds"])
            r["overround"] = g.get("overround")
            found += 1
    return found


def calibration(path: Path, sport: str) -> SportCalibration:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if "sports" not in doc:  # a --rows-out <sport>_section.json
        doc = {"sports": {sport: doc}, "min_bucket": MIN_BUCKET}
    return SportCalibration(doc)


def confidence_of(cal: SportCalibration, sport: str, r: Row) -> float | None:
    c = cal.lookup(sport, str(r["family"]), str(r["side"]), float(r["p"]),
                   require_admitted=False)
    return None if c is None else c.value


def _ll(c: float, y: int) -> float:
    q = min(max(c, 1e-6), 1 - 1e-6)
    return -math.log(q if y else 1.0 - q)


def _boot(per_game: dict[str, tuple[float, int]], rng: random.Random
          ) -> list[float]:
    games = list(per_game.values())
    if not games:
        return [math.nan, math.nan, math.nan]
    tot_s = sum(s for s, _ in games)
    tot_n = sum(n for _, n in games)
    draws: list[float] = []
    for _ in range(BOOT):
        s = n = 0.0
        for _ in range(len(games)):
            gs, gn = games[rng.randrange(len(games))]
            s += gs
            n += gn
        if n:
            draws.append(s / n)
    draws.sort()
    return [tot_s / tot_n, draws[int(0.025 * len(draws))],
            draws[int(0.975 * len(draws)) - 1]]


def paired_logloss(rows: Sequence[Row], key: str = "") -> Stat:
    per: dict[str, tuple[float, int]] = {}
    old_ll = new_ll = 0.0
    n = 0
    for r in rows:
        if r["c_old"] is None or r["c_new"] is None:
            continue
        lo, ln = _ll(r["c_old"], r["y"]), _ll(r["c_new"], r["y"])
        old_ll += lo
        new_ll += ln
        n += 1
        s, k = per.get(r["game"], (0.0, 0))
        per[r["game"]] = (s + ln - lo, k + 1)
    if not n:
        return {"n": 0}
    return {"n": n, "games": len(per), "logloss_old": old_ll / n,
            "logloss_new": new_ll / n,
            "diff": _boot(per, random.Random(f"{SEED}:{key}"))}


def gap(rows: Sequence[Row], conf: str, key: str = "") -> Stat:
    """realised - confidence on lines whose `conf` >= PRINTABLE_FROM."""
    per: dict[str, tuple[float, int]] = {}
    cs = ys = 0.0
    n = 0
    for r in rows:
        c = r[conf]
        if c is None or c < PRINTABLE_FROM:
            continue
        s, k = per.get(r["game"], (0.0, 0))
        per[r["game"]] = (s + r["y"] - c, k + 1)
        cs += c
        ys += r["y"]
        n += 1
    if not n:
        return {"n": 0}
    return {"n": n, "games": len(per), "confidence": cs / n, "realised": ys / n,
            "gap": _boot(per, random.Random(f"{SEED}:{conf}:{key}"))}


def printable(r: Row, conf: str, gated: bool) -> bool:
    c = r[conf]
    if c is None or c < PRINTABLE_FROM:
        return False
    if not gated:
        return True
    odds = r.get("odds")
    margin = r.get("overround")
    return (odds is not None and c * float(odds) >= MIN_X
            and (margin is None or float(margin) <= MAX_MARGIN))


def counts(rows: Sequence[Row], group: Callable[[Row], str]) -> dict[str, Stat]:
    out: dict[str, Stat] = {}
    by: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by[group(r)].append(r)
    for name, rs in sorted(by.items()):
        st: Stat = {"lines": len(rs)}
        for gated in (False, True):
            tag = "gated" if gated else "conf70"
            old = {id(r) for r in rs if printable(r, "c_old", gated)}
            new = {id(r) for r in rs if printable(r, "c_new", gated)}
            sel_new = [r for r in rs if id(r) in new]
            st[tag] = {
                "old": len(old), "new": len(new), "added": len(new - old),
                "removed": len(old - new),
                "new_below_price": sum(
                    1 for r in sel_new
                    if r.get("odds") and r["c_new"] < 1.0 / float(r["odds"])),
                "new_odds": sorted(float(r["odds"]) for r in sel_new
                                   if r.get("odds")),
            }
        out[name] = st
    return out


def measure(rows: list[Row], old: SportCalibration, new: SportCalibration,
            sport: str) -> dict[str, Any]:
    for r in rows:
        r["c_old"] = confidence_of(old, sport, r)
        r["c_new"] = confidence_of(new, sport, r)
    fams = sorted({str(r["family"]) for r in rows})
    keys = sorted({str(r["key"]) for r in rows})
    out: dict[str, Any] = {
        "lines": len(rows), "games": len({r["game"] for r in rows}),
        "read_old": sum(1 for r in rows if r["c_old"] is not None),
        "read_new": sum(1 for r in rows if r["c_new"] is not None),
        "logloss": {"all": paired_logloss(rows, "all")},
        "gap": {"all": {"old": gap(rows, "c_old", "all"),
                        "new": gap(rows, "c_new", "all")}},
        "buckets": {},
        "printable_by_family": counts(rows, lambda r: str(r["family"])),
    }
    scopes = ([("family", f) for f in fams] + [("key", k) for k in keys])
    for scope, name in scopes:
        rs = [r for r in rows if r[scope] == name]
        out["logloss"][f"{scope}:{name}"] = paired_logloss(rs, name)
        out["gap"][f"{scope}:{name}"] = {"old": gap(rs, "c_old", name),
                                         "new": gap(rs, "c_new", name)}
    edges = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
    for conf in ("c_old", "c_new"):
        b: dict[str, Stat] = {}
        for lo, hi in zip(edges, edges[1:], strict=False):
            rs = [r for r in rows if r[conf] is not None and lo <= r[conf] < hi]
            if rs:
                b[f"{lo:.1f}-{min(hi, 1.0):.1f}"] = {
                    "n": len(rs),
                    "confidence": sum(r[conf] for r in rs) / len(rs),
                    "realised": sum(r["y"] for r in rs) / len(rs)}
        out["buckets"][conf] = b
    return out


def decision(res: dict[str, Any], min_n: int = 200, max_over: float = 0.02
             ) -> dict[str, Any]:
    """The coordinator's rule (2026-10-15): log-loss better with the interval
    below zero AND no family overstating by more than `max_over` at >= 0.70
    on >= `min_n` lines (the candidate curve)."""
    d = res["logloss"]["all"].get("diff") or [math.nan] * 3
    ll_ok = bool(d[0] < 0 and d[2] < 0)
    bad = {}
    for name, g in res["gap"].items():
        if not name.startswith("family:"):
            continue
        new = g["new"]
        if new.get("n", 0) >= min_n and new["gap"][0] < -max_over:
            bad[name] = {"n": new["n"], "gap": new["gap"]}
    return {"logloss_better": ll_ok, "families_overstating": bad,
            "install": ll_ok and not bad}


def _pp(x: float) -> str:
    return f"{100 * x:+.1f}"


def _ci(v: Sequence[float], pp: bool = False) -> str:
    if pp:
        return f"{_pp(v[0])} pp [{_pp(v[1])}; {_pp(v[2])}]"
    return f"{v[0]:+.5f} [{v[1]:+.5f}; {v[2]:+.5f}]"


def markdown(res: dict[str, Any], dec: dict[str, Any]) -> str:
    out = [f"lines {res['lines']} / games {res['games']}; read by today's "
           f"curve {res['read_old']}, by the candidate {res['read_new']}", ""]
    out.append("| scope | paired lines / games | log-loss today | candidate | "
               "candidate - today [95%] |")
    out.append("|---|---|---|---|---|")
    for name, s in res["logloss"].items():
        if s.get("n") and (name == "all" or name.startswith("family:")):
            out.append(f"| {name} | {s['n']} / {s['games']} | "
                       f"{s['logloss_old']:.5f} | {s['logloss_new']:.5f} | "
                       f"{_ci(s['diff'])} |")
    out += ["", "| scope | today >= 0.70: lines / games, conf., realised, gap | "
            "candidate |", "|---|---|---|"]
    for name, g in res["gap"].items():
        if name != "all" and not name.startswith("family:"):
            continue
        cells = []
        for c in ("old", "new"):
            s = g[c]
            cells.append("-" if not s.get("n") else
                         f"{s['n']} / {s['games']}, {s['confidence']:.3f}, "
                         f"{s['realised']:.3f}, {_ci(s['gap'], pp=True)}")
        out.append(f"| {name} | {cells[0]} | {cells[1]} |")
    out += ["", "| family | lines | conf >= 0.70 today -> candidate (+/-) | "
            "with x >= 0.90, margin <= 15% (+/-) | candidate below 1/odds |",
            "|---|---|---|---|---|"]
    for f, s in res["printable_by_family"].items():
        a, b = s["conf70"], s["gated"]
        if a["old"] or a["new"]:
            out.append(f"| {f} | {s['lines']} | {a['old']} -> {a['new']} "
                       f"(+{a['added']} / -{a['removed']}) | {b['old']} -> "
                       f"{b['new']} (+{b['added']} / -{b['removed']}) | "
                       f"{b['new_below_price']} |")
    out += ["", f"decision: {json.dumps(dec)}"]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sport", required=True)
    ap.add_argument("--rows", required=True, type=Path)
    ap.add_argument("--old", required=True, type=Path,
                    help="calibration file (or <sport>_section.json) read today")
    ap.add_argument("--new", required=True, type=Path,
                    help="candidate calibration file or <sport>_section.json")
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--runs-dir", type=Path, default=_REPO / "runs" / "sofa")
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--md-out", type=Path)
    args = ap.parse_args()
    rows = load_rows(args.rows, args.start, args.end)
    priced = attach_prices(rows, args.runs_dir, args.sport)
    res = measure(rows, calibration(args.old, args.sport),
                  calibration(args.new, args.sport), args.sport)
    res["priced_lines"] = priced
    res["window"] = [args.start, args.end]
    res["coupon_floor"] = COUPON_PROFILE.floor
    dec = decision(res)
    res["decision"] = dec
    md = markdown(res, dec)
    if args.json_out:
        args.json_out.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    if args.md_out:
        args.md_out.write_text(md + "\n", encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
