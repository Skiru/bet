#!/usr/bin/env python3
"""The history curve of football double chance (bet.sofa.football_result),
with its holdout gate - fitted and STAGED, never installed by this script.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_double_chance_curve.py \\
        --out-dir data/refit_new_markets_2026-10-15/double_chance \\
        [--history data/cache/football_history.pkl] [--from 2024-10-01] \\
        [--holdout-from 2026-09-01] [--holdout-to 2026-10-14] \\
        [--before 2026-10-15] [--result-config config/sofa_football_result.json]

Plan docs/sofa/history/PLAN_KRZYWE_NOWE_RYNKI_2026-10-14.md steps 2-4.

Replay: the parsed football history SHEET keeps (the pickle, opened
read-only - a parsed copy, never the live DB), in time order; before each
match the rating book holds only earlier matches (`football_rating.RatingBook`,
as `replay` builds SHEET's). A match is priced exactly as
`run_sheet.double_chance_rows` prices it: both sides' PURE rating centres
`FootballForecast.centre("goals_for", side)` (no row without both), NB goals
with `nb_r` from config/sofa_football_result.json
(`football_result.result_probs` arithmetic), each selection 1X / X2 / 12 its
own OVER row, a p outside [P_FLOOR, P_CEILING] not priced
(`engine.outside_model_resolution`), and an UNLINKED fixture left out
(CONFIDENCE refuses CROSS_LEAGUE_UNLINKED). Outcome: the selection on the
history's goals (normaltime, as SETTLE grades it).

Keys, as CONFIDENCE reads them (`Calibration.realised(market, p, sport,
direction, klass)` -> `by_market_direction["double_chance|OVER"]`; the
selection is not in the key): `double_chance|OVER` fitted on every match
(fit_confidence's unclassed curves hold every row) and gated on men's
matches (the legs that read it); `women:double_chance|OVER` - the women's
class curve (`by_class.women.by_market_direction`), fitted and gated on
women's matches (`FootballResult.women`, Sofascore's gender; the live class
is confidence.match_class).

Gate (new_market_gate.gate): the curve fitted on matches in [--from,
--holdout-from) is read on [--holdout-from, --holdout-to); PASS = curve
value >= 0.70 forecasts with |realised - curve| <= 2 pp and n >= 300. The
final curve of every PASSING key is refitted on [--from, --before). The
dispersion r is the config's, measured on 2024-10-01..2026-06-08 (before the
holdout). Per-selection gates are reported, never decisive.

Writes curves.json (`target`, `fitted_from`, `by_market_direction` and
`by_class` of PASSING keys only, `gate` of every key), rows.csv.gz (every
priced selection with its phase and curve value) and gate_report.md.
Exit 0, 2 on a crash.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import pickle
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa import football_result as res  # noqa: E402
from bet.sofa.config import config_path  # noqa: E402
from bet.sofa.engine import outside_model_resolution  # noqa: E402
from scripts.sofa import new_market_gate as gate_mod  # noqa: E402

TARGET = "config/sofa_confidence_calibration.json"
KEY = "double_chance|OVER"
CLASS_WOMEN = "women"
WOMEN_KEY = f"{CLASS_WOMEN}:{KEY}"
CHUNK = 20000


@dataclass(frozen=True)
class Match:
    ts: int
    event_id: int
    women: bool
    link: str
    lh: float
    la: float
    x: int
    y: int


@dataclass(frozen=True)
class Priced:
    match: Match
    selection: str
    p: float
    y: int


def replay(history: Iterable[fr.FootballResult], from_ts: int,
           to_ts: int) -> list[Match]:
    """Every match in [from_ts, to_ts) with both pure rating goals centres,
    priced before the book learns it."""
    book = fr.RatingBook()
    out: list[Match] = []
    for r in history:
        if r.ts >= to_ts:
            break
        goals = r.values.get("goals_for")
        if r.ts >= from_ts and goals is not None:
            fc = fr.FootballForecast(book, r.competition_id, r.home_id, r.away_id)
            ch = fc.centre("goals_for", "side_a")
            ca = fc.centre("goals_for", "side_b")
            if ch is not None and ca is not None:
                out.append(Match(int(r.ts), int(r.event_id), bool(r.women),
                                 fc.fixture_link(), float(ch[0]), float(ca[0]),
                                 int(goals[0]), int(goals[1])))
        book.update(r)
    return out


def price(matches: Sequence[Match], nb_r: float) -> list[Priced]:
    """Every DC selection of the LINKED matches, as SHEET prices it."""
    linked = [m for m in matches if m.link != fr.UNLINKED
              and m.lh > 0 and m.la > 0]
    if not linked:
        return []
    lh = np.array([m.lh for m in linked])
    la = np.array([m.la for m in linked])
    probs = np.concatenate([
        res.market_probs(res.score_grid(res.count_pmf(lh[i:i + CHUNK], nb_r),
                                        res.count_pmf(la[i:i + CHUNK], nb_r)))
        for i in range(0, len(linked), CHUNK)])
    out: list[Priced] = []
    for m, (h, d, a) in zip(linked, probs, strict=True):
        for sel, p in (("1X", h + d), ("X2", d + a), ("12", h + a)):
            p = float(p)
            if outside_model_resolution(p):
                continue
            out.append(Priced(m, sel, p, int(res.selection_holds(sel, m.x, m.y))))
    return out


def _ts(day: str) -> int:
    d = date.fromisoformat(day)
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())


def _forecasts(rows: Iterable[Priced]) -> list[gate_mod.Forecast]:
    return [(r.p, r.y, r.match.event_id) for r in rows]


def run(priced: Sequence[Priced], h0: int, h1: int, cut: int) -> dict[str, Any]:
    """Training curves, gates and final curves of both keys."""
    train = [r for r in priced if r.match.ts < h0]
    hold = [r for r in priced if h0 <= r.match.ts < h1]
    final_rows = [r for r in priced if r.match.ts < cut]
    women = {KEY: False, WOMEN_KEY: True}
    training = {
        KEY: gate_mod.fit_curve((r.p, r.y) for r in train),
        WOMEN_KEY: gate_mod.fit_curve((r.p, r.y) for r in train if r.match.women)}
    final = {
        KEY: gate_mod.fit_curve((r.p, r.y) for r in final_rows),
        WOMEN_KEY: gate_mod.fit_curve((r.p, r.y) for r in final_rows
                                      if r.match.women)}
    gates: dict[str, Any] = {}
    diagnostics: dict[str, Any] = {}
    for key, w in women.items():
        pop = [r for r in hold if r.match.women == w]
        gates[key] = gate_mod.gate(training[key], _forecasts(pop))
        diagnostics[key] = {
            sel: gate_mod.gate(training[key],
                               _forecasts(r for r in pop if r.selection == sel))
            for sel in res.SELECTIONS}
    diagnostics["double_chance|OVER on every holdout match"] = gate_mod.gate(
        training[KEY], _forecasts(hold))
    return {"training": training, "final": final, "gate": gates,
            "diagnostics": diagnostics,
            "counts": {"train": len(train), "holdout": len(hold),
                       "final": len(final_rows)}}


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--history", help="the parsed football history pickle "
                    "(read-only); default data/cache/football_history.pkl")
    ap.add_argument("--from", dest="from_", default="2024-10-01")
    ap.add_argument("--holdout-from", default="2026-09-01")
    ap.add_argument("--holdout-to", default="2026-10-14")
    ap.add_argument("--before", default="2026-10-15")
    ap.add_argument("--result-config")
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    hist_path = Path(args.history or _REPO / "data" / "cache" / "football_history.pkl")
    fingerprint, history = pickle.loads(hist_path.read_bytes())
    cfg_path = Path(args.result_config) if args.result_config else config_path(
        res.CONFIG_FILE)
    cfg = res.load_config(cfg_path)
    h0, h1, cut = _ts(args.holdout_from), _ts(args.holdout_to), _ts(args.before)
    matches = replay(history, _ts(args.from_), cut)
    del history
    priced = price(matches, cfg.nb_r)
    result = run(priced, h0, h1, cut)
    passing = {k for k, g in result["gate"].items() if g["pass"]}
    fitted_from = {
        "history": str(hist_path), "history_fingerprint": str(fingerprint),
        "history_mtime_utc": datetime.fromtimestamp(
            hist_path.stat().st_mtime, UTC).isoformat(),
        "window": [args.from_, args.before], "before": args.before,
        "fitted_at_utc": datetime.now(UTC).isoformat(),
        "script": "scripts/sofa/fit_double_chance_curve.py",
        "estimator": "football_result.result_probs: NB goals on the pure "
                     "rating centres (FootballForecast.centre goals_for), "
                     f"nb_r {cfg.nb_r} from {cfg_path}",
        "nb_r": cfg.nb_r, "nb_r_source": cfg.source,
        "matches_rated": len(matches),
        "matches_unlinked_excluded": sum(1 for m in matches
                                         if m.link == fr.UNLINKED),
        "selections": result["counts"],
        "holdout": {"train_window": [args.from_, args.holdout_from],
                    "holdout_window": [args.holdout_from, args.holdout_to],
                    "rule": f"curve value >= {gate_mod.PRINT_FLOOR}: |realised - "
                            f"curve| <= {gate_mod.MAX_GAP}, n >= {gate_mod.MIN_N}"},
    }
    doc: dict[str, Any] = {
        "target": TARGET, "group": "double_chance", "fitted_from": fitted_from,
        "by_market_direction": ({KEY: result["final"][KEY]}
                                if KEY in passing and result["final"][KEY] else {}),
        "by_class": ({CLASS_WOMEN: {"by_market_direction": {
            KEY: result["final"][WOMEN_KEY]}}}
            if WOMEN_KEY in passing and result["final"][WOMEN_KEY] else {}),
        "gate": result["gate"],
        "gate_diagnostics": result["diagnostics"],
        "training_curves": result["training"],
        "final_curves_all_keys": result["final"],
    }
    (out / "curves.json").write_text(json.dumps(doc, indent=1) + "\n")
    with gzip.open(out / "rows.csv.gz", "wt", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["phase", "start_ts", "event_id", "women", "link", "lh", "la",
                    "home_goals", "away_goals", "selection", "p", "y",
                    "train_curve_value"])
        for r in priced:
            m = r.match
            phase = ("train" if m.ts < h0 else "holdout" if m.ts < h1
                     else "final_only")
            cv = gate_mod.curve_value(
                result["training"][WOMEN_KEY if m.women else KEY], r.p)
            w.writerow([phase, m.ts, m.event_id, int(m.women), m.link,
                        round(m.lh, 5), round(m.la, 5), m.x, m.y, r.selection,
                        round(r.p, 6), r.y, "" if cv is None else cv])
    lines = [f"# Double chance - holdout gate ({args.holdout_from} .. "
             f"{args.holdout_to}, train {args.from_} ..)", "",
             f"nb_r {cfg.nb_r}; rated matches {len(matches)}, UNLINKED left out "
             f"{fitted_from['matches_unlinked_excluded']}; selections "
             f"{result['counts']}", ""]
    for key in (KEY, WOMEN_KEY):
        lines += gate_mod.gate_lines(key, result["gate"][key])
        for sel, g in result["diagnostics"][key].items():
            lines += gate_mod.gate_lines(f"{key} - selection {sel} (diagnostic)", g)
    lines += gate_mod.gate_lines(
        "double_chance|OVER on every holdout match (diagnostic)",
        result["diagnostics"]["double_chance|OVER on every holdout match"])
    for key, c in result["final"].items():
        lines.append(f"## final curve {key} (before {args.before})"
                     + ("" if key in passing else " - not installable (FAIL)"))
        lines += [f"- {b}: n {e['n']}, realised {e['realised']}, lo95 "
                  f"{e['realised_lo95']}" for b, e in c.items()]
        lines.append("")
    (out / "gate_report.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"out_dir": str(out), "pass": sorted(passing),
                      "fail": sorted(set(result["gate"]) - passing),
                      "counts": result["counts"]}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc!r}", file=sys.stderr)
        raise SystemExit(2) from exc
