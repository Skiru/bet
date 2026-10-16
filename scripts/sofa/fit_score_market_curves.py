#!/usr/bin/env python3
"""History curves of the football score markets (bet.sofa.football_score_markets)
and the tennis exact-score complements (tennis_sets.SET_SCORE_NOT), with
their one-sided holdout gate - fitted and STAGED, never installed by this
script (scripts/sofa/install_new_market_curves.py installs the passing keys).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_score_market_curves.py \\
        --out-dir data/refit_new_markets_2026-10-17 \\
        --football-rows \\
          data/refit_new_markets_2026-10-16_cup/football_result_1x2_dnb/rows.csv.gz \\
        --tennis-rows data/refit_new_markets_2026-10-15/tennis_sets/rows.csv \\
        [--holdout-from 2026-09-01] [--holdout-to 2026-10-14] [--before 2026-10-15] \\
        [--result-config config/sofa_football_result.json]

No replay of its own: it reads the rows the installed curves' fits already
wrote, which carry everything these markets need -

  football  fit_result_1x2_dnb_curve.py's rows (one per match and key; the
            `result_1x2|OVER` side "1" row gives each match once): the PURE
            rating goals centres `lh` / `la` as of the match (the book with
            the cup league strength, --cup-strength, 2026-10-16), the
            90-minute goals, women, the as-of season phase; UNLINKED is
            already left out (SHEET's row carries CROSS_LEAGUE_UNLINKED and
            CONFIDENCE refuses it). P of every rung = its event's mass on
            the NB score grid (football_score_markets.event_mask, r from
            config/sofa_football_result.json) - SHEET's arithmetic;
  tennis    fit_incident_set_curves.py's tennis_sets rows: per best-of-three
            match the exact-score shares of the home player's rating
            neighbours, "home 2:0" .. "home 0:2", with the outcome. A
            set_score_not "<X> 0:2" row is 1 - p / 1 - y of "home 0:2"
            (X home) and of "home 2:0" (X away) - only the 0:2 complements
            are read live (classify_set_complement's canonical subject).

A p outside [P_FLOOR, P_CEILING] is not priced (engine.outside_model_resolution).
Keys: football "<market>@<subject>@<line>|OVER" - one curve per SLICE, as
CONFIDENCE reads it (confidence.curve_market; a curve pooled over a market's
lines hid -3..-9 pp slices inside a -0.5 pp pooled gap, 2026-10-16), tennis
"set_score_not|OVER" (its two slices, home / away 0:2, checked). Football
classes as football_score_markets.leg_class reads them: `women` (every
phase), `season_early` (a men's match in the as-of early phase), the
unclassed key every other men's match; tennis `tennis_women` apart. Each
class is fitted on its own rows only. Gate: new_market_gate.gate
(one-sided) of the curve fitted before --holdout-from on [--holdout-from,
--holdout-to), plus require_final; a key PASSES only if, besides, no
subject / line slice with n >= MIN_N overstates (realised - curve <
-MAX_GAP) - a pooled curve must not hide one bad selection. Diagnostics
(reported, never gated): per subject, per line, the early season phase.

Writes, per group (football_score_markets, tennis_set_complements),
<out-dir>/<group>/curves.json (the installer's shape) and gate_report.md.
Exit 0, 2 on a crash.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import football_result as res  # noqa: E402
from bet.sofa import football_score_markets as fsm  # noqa: E402
from bet.sofa.config import config_path  # noqa: E402
from bet.sofa.engine import P_CEILING, P_FLOOR  # noqa: E402
from bet.sofa.season_phase import PHASE_EARLY  # noqa: E402
from bet.sofa.tennis_sets import SET_SCORE_NOT  # noqa: E402
from scripts.sofa import new_market_gate as gm  # noqa: E402

TARGET = "config/sofa_confidence_calibration.json"
FOOTBALL_GROUP = "football_score_markets"
TENNIS_GROUP = "tennis_set_complements"
WOMEN = "women"
TENNIS_WOMEN = "tennis_women"
CHUNK = 50000
K = res.KMAX


def rungs() -> list[tuple[str, str, float]]:
    """Every (market, subject, line) SHEET can price."""
    out: list[tuple[str, str, float]] = []
    for market in (fsm.RESULT_OR_OVER, fsm.RESULT_OR_UNDER):
        out += [(market, s, line)
                for s in fsm.RESULT_SUBJECTS for line in fsm.GOAL_LINES]
    out += [(fsm.BTTS_OR_OVER, "", line) for line in fsm.GOAL_LINES]
    for market in (fsm.RESULT_OR_BTTS, fsm.RESULT_OR_CLEAN_SHEET):
        out += [(market, s, fsm.EVENT_LINE) for s in fsm.RESULT_SUBJECTS]
    out += [(fsm.HANDICAP_RESULT, s, line) for s in fsm.SIDE_SUBJECTS
            for line in fsm.HANDICAP_LINES]
    for market, subject in fsm.DC_SUBJECT.items():
        out += [(market, subject, line) for line in fsm.GOAL_LINES]
    return out


@dataclass
class Rows:
    """Columnar forecasts of one key: p, y, match id, ts, class, slice, early."""
    p: np.ndarray[Any, Any]
    y: np.ndarray[Any, Any]
    m: np.ndarray[Any, Any]
    ts: np.ndarray[Any, Any]
    klass: np.ndarray[Any, Any]  # "" = unclassed
    slice_: np.ndarray[Any, Any]
    early: np.ndarray[Any, Any]


class _Acc:
    def __init__(self) -> None:
        self.parts: list[tuple[np.ndarray[Any, Any], ...]] = []

    def add(self, *cols: np.ndarray[Any, Any]) -> None:
        self.parts.append(cols)

    def rows(self) -> Rows:
        cols = [np.concatenate([part[i] for part in self.parts])
                for i in range(len(self.parts[0]))]
        return Rows(*cols)


def _ts(day: str) -> int:
    d = date.fromisoformat(day)
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())


def football_rows(path: Path, nb_r: float) -> dict[str, Rows]:
    lh, la, hg, ag, ts, ev, women, early = [], [], [], [], [], [], [], []
    with gzip.open(path, "rt") as fh:
        for r in csv.DictReader(fh):
            if r["key"] != "result_1x2|OVER" or r["side"] != "1":
                continue
            lh.append(float(r["lh"]))
            la.append(float(r["la"]))
            hg.append(int(float(r["home_goals"])))
            ag.append(int(float(r["away_goals"])))
            ts.append(int(r["start_ts"]))
            ev.append(int(r["event_id"]))
            women.append(r["women"] == "1")
            early.append(r.get("season_phase") == PHASE_EARLY)
    n = len(lh)
    print(f"football matches {n}", flush=True)
    a_lh, a_la = np.asarray(lh), np.asarray(la)
    xi = np.minimum(np.asarray(hg), K)
    yi = np.minimum(np.asarray(ag), K)
    a_ts, a_ev = np.asarray(ts), np.asarray(ev)
    a_klass = np.where(np.asarray(women), WOMEN,
                       np.where(np.asarray(early), fsm.CLASS_SEASON_EARLY, ""))
    a_early = np.asarray(early)
    acc: dict[str, _Acc] = defaultdict(_Acc)
    masks = {rung: fsm.event_mask(*rung, kmax=K) for rung in rungs()}
    for s in range(0, n, CHUNK):
        e = min(n, s + CHUNK)
        grid = (res.count_pmf(a_lh[s:e], nb_r, K)[:, :, None]
                * res.count_pmf(a_la[s:e], nb_r, K)[:, None, :])
        for (market, subject, line), mask in masks.items():
            ps = (grid * mask[None]).sum(axis=(1, 2))
            ys = mask[xi[s:e], yi[s:e]].astype(np.int8)
            keep = (ps >= P_FLOOR) & (ps <= P_CEILING)
            label = f"subject {subject or '-'} line {line:g}"
            acc[f"{fsm.curve_market(market, subject, line)}|OVER"].add(
                ps[keep], ys[keep], a_ev[s:e][keep], a_ts[s:e][keep],
                a_klass[s:e][keep], np.full(int(keep.sum()), label),
                a_early[s:e][keep])
    return {k: a.rows() for k, a in acc.items()}


def tennis_rows(path: Path) -> dict[str, Rows]:
    by_match: dict[tuple[str, str, str], dict[str, tuple[float, int]]] = (
        defaultdict(dict))
    with path.open() as fh:
        for r in csv.DictReader(fh):
            if r["market"] != "set_score":
                continue
            by_match[(r["event_id"], r["date"], r["klass"])][r["subject"]] = (
                float(r["p"]), int(r["y"]))
    p, y, m, ts, kl, sl = [], [], [], [], [], []
    for (eid, day, klass), scores in by_match.items():
        for subject, who in (("home 0:2", "home"), ("home 2:0", "away")):
            if subject not in scores:
                continue
            q = 1.0 - scores[subject][0]
            if not (P_FLOOR <= q <= P_CEILING):
                continue
            p.append(q)
            y.append(1 - scores[subject][1])
            m.append(int(eid))
            ts.append(_ts(day))
            kl.append(klass or "")
            sl.append(f"subject {who}")
    print(f"tennis matches {len(by_match)}", flush=True)
    return {f"{SET_SCORE_NOT}|OVER": Rows(
        np.asarray(p), np.asarray(y), np.asarray(m), np.asarray(ts),
        np.asarray(kl), np.asarray(sl), np.zeros(len(p), dtype=bool))}


def class_key(klass: str | None, key: str) -> str:
    return key if klass is None else f"{klass}:{key}"


def _fc(rows: Rows, sel: np.ndarray[Any, Any]) -> list[gm.Forecast]:
    return list(zip(rows.p[sel].tolist(), rows.y[sel].tolist(),
                    rows.m[sel].tolist(), strict=True))


def fit_group(all_rows: dict[str, Rows], classes: Sequence[str | None],
              h0: int, h1: int, cut: int) -> dict[str, Any]:
    final: dict[str, Any] = {}
    gates: dict[str, Any] = {}
    diag: dict[str, Any] = {}
    for key, rows in sorted(all_rows.items()):
        for klass in classes:
            ck = class_key(klass, key)
            in_class = rows.klass == (klass or "")
            train = in_class & (rows.ts < h0)
            hold = in_class & (rows.ts >= h0) & (rows.ts < h1)
            fin = in_class & (rows.ts < cut)
            tc = gm.fit_curve(zip(rows.p[train].tolist(), rows.y[train].tolist(),
                                  strict=True))
            fc = gm.fit_curve(zip(rows.p[fin].tolist(), rows.y[fin].tolist(),
                                  strict=True))
            g = gm.require_final(gm.gate(tc, _fc(rows, hold), reps=300), fc)
            slices: dict[str, Any] = {}
            bad = []
            for label in sorted(set(rows.slice_[hold].tolist())):
                sg = gm.gate(tc, _fc(rows, hold & (rows.slice_ == label)), reps=200)
                slices[label] = {k: sg.get(k) for k in ("n", "gap", "gap_ci95", "pass")}
                if ((sg.get("n") or 0) >= gm.MIN_N and sg.get("gap") is not None
                        and sg["gap"] < -gm.MAX_GAP - 1e-9):
                    bad.append(label)
            if bad and g.get("pass"):
                g["pass"] = False
                g["why"] = f"a slice overstates: {', '.join(bad)}"
            early = hold & rows.early
            eg = gm.gate(tc, _fc(rows, early), reps=200) if early.any() else {}
            diag[ck] = {"slices": slices,
                        "early_phase": {k: eg.get(k) for k in ("n", "gap", "gap_ci95")},
                        "rows": {"train": int(train.sum()), "holdout": int(hold.sum()),
                                 "final": int(fin.sum())}}
            gates[ck] = g
            final[ck] = fc
    return {"final": final, "gate": gates, "diagnostics": diag}


def write_group(out: Path, group: str, result: dict[str, Any],
                fitted_from: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    by_md: dict[str, Any] = {}
    by_class: dict[str, Any] = {}
    for ck, g in result["gate"].items():
        if not g.get("pass"):
            continue
        klass, _, key = ck.rpartition(":")
        if klass:
            by_class.setdefault(klass, {"by_market_direction": {}})[
                "by_market_direction"][key] = result["final"][ck]
        else:
            by_md[key] = result["final"][ck]
    doc = {"target": TARGET, "group": group, "fitted_from": fitted_from,
           "by_market_direction": by_md, "by_class": by_class,
           "gate": result["gate"], "diagnostics": result["diagnostics"]}
    (out / "curves.json").write_text(json.dumps(doc, indent=1) + "\n")
    lines = [f"# Bramka krzywych: {group}", "",
             f"Reguła: {gm.RULE_TEXT}; dodatkowo żaden wycinek (podmiot / linia) "
             f"z n >= {gm.MIN_N} nie może zawyżać o więcej niż {gm.MAX_GAP:.0%}.", "",
             f"Źródło: {json.dumps(fitted_from, ensure_ascii=False)}", "",
             "| klucz | n holdout >= 0,70 | mecze | krzywa | realizacja | luka pp "
             "[95%] | wynik | wczesna faza: n / luka pp |",
             "|---|---|---|---|---|---|---|---|"]
    for ck, g in sorted(result["gate"].items()):
        e = result["diagnostics"][ck]["early_phase"]
        ci = g.get("gap_ci95") or [None, None]
        gap = "" if g.get("gap") is None else (
            f"{100 * g['gap']:+.2f} [{100 * ci[0]:+.2f}, {100 * ci[1]:+.2f}]")
        early = "" if not e.get("n") or e.get("gap") is None else (
            f"{e['n']} / {100 * e['gap']:+.2f}")
        lines.append(f"| {ck} | {g.get('n')} | {g.get('matches')} | "
                     f"{g.get('mean_curve')} | {g.get('realised')} | {gap} | "
                     f"{'PASS' if g.get('pass') else 'FAIL ' + str(g.get('why'))} | "
                     f"{early} |")
    lines += ["", "## Wycinki holdoutu (krzywa treningowa)", ""]
    for ck, d in sorted(result["diagnostics"].items()):
        lines.append(f"**{ck}** - wiersze {d['rows']}")
        lines.append("")
        for sl, sg in d["slices"].items():
            if not sg.get("n"):
                continue
            ci = sg.get("gap_ci95") or [0, 0]
            lines.append(f"- {sl}: n {sg['n']}, luka {100 * sg['gap']:+.2f} pp "
                         f"[{100 * ci[0]:+.2f}, {100 * ci[1]:+.2f}]")
        lines.append("")
    (out / "gate_report.md").write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--football-rows", required=True)
    ap.add_argument("--tennis-rows", required=True)
    ap.add_argument("--holdout-from", default="2026-09-01")
    ap.add_argument("--holdout-to", default="2026-10-14")
    ap.add_argument("--before", default="2026-10-15")
    ap.add_argument("--result-config")
    ap.add_argument("--only", choices=("football", "tennis"))
    args = ap.parse_args()
    out = Path(args.out_dir)
    h0, h1, cut = _ts(args.holdout_from), _ts(args.holdout_to), _ts(args.before)
    cfg = res.load_config(Path(args.result_config) if args.result_config
                          else config_path(res.CONFIG_FILE))
    window = {"holdout_from": args.holdout_from, "holdout_to": args.holdout_to,
              "before": args.before, "fitted_at_utc":
              datetime.now(UTC).isoformat(timespec="seconds"),
              "script": "scripts/sofa/fit_score_market_curves.py"}
    summary: dict[str, Any] = {}
    if args.only in (None, "football"):
        rows = football_rows(Path(args.football_rows), cfg.nb_r)
        result = fit_group(rows, (None, WOMEN, fsm.CLASS_SEASON_EARLY), h0, h1, cut)
        write_group(out / FOOTBALL_GROUP, FOOTBALL_GROUP, result,
                    {**window, "rows": args.football_rows, "nb_r": cfg.nb_r})
        summary[FOOTBALL_GROUP] = {k: g["pass"] for k, g in result["gate"].items()}
    if args.only in (None, "tennis"):
        rows = tennis_rows(Path(args.tennis_rows))
        result = fit_group(rows, (None, TENNIS_WOMEN), h0, h1, cut)
        write_group(out / TENNIS_GROUP, TENNIS_GROUP, result,
                    {**window, "rows": args.tennis_rows})
        summary[TENNIS_GROUP] = {k: g["pass"] for k, g in result["gate"].items()}
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
