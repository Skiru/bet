#!/usr/bin/env python3
"""Fit and gate the history curves of CS2's series rounds
(epochs.CS2_SERIES_ROUNDS_FROM_UTC; cs2_engine.SERIES_ROUND_FAMILIES):
rounds_total, rounds_handicap and team_rounds over the whole series.

The model (cs2_engine.series_rounds_side_p): the maps each team wins from the
series distribution the series families use (series_distribution_mixed,
SERIES_KAPPA), each map's rounds from the round race given its winner
(map_distribution_for) - a map never played adds nothing. No price is read.

On a COPY of the CS2 history tables (--db-path; never data/sofa.db), one
walk-forward pass (sport_confidence.cs2_walk_forward_rows, series_rounds=True,
the estimator switches of --final-before's first build):

* fit      series before --fit-before (history from LOOKBACK_DAYS on);
* holdout  [--fit-before, --holdout-end);
* superbet the same pass priced at the lines Superbet actually posted and
           CS2_SETTLE graded (runs/sofa/cs2/<d>/settled.json, --superbet-from
           .. --superbet-to), oriented to Sofascore's home side - a second
           population, never the gate's;
* final    every series before --final-before.

Gate per key (operator 2026-10-14, one-sided): the holdout read through the
fit curve, rows whose curve value >= 0.70 pooled, n >= GATE_MIN_N and
realised - curve >= -GATE_MAX_SHORTFALL, AND the sport admission rule
(sport_confidence.admission on the holdout: no bucket of n >= 200 more than
3 pp above realised; printable rows pooled not overstating). A passing key's
curve is refitted on `final` and written in the sport calibration's shape to
<out>/curves.json (install_new_market_curves.py's sport group shape) with
<out>/gate_report.md. Nothing under config/ is touched.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_cs2_series_rounds.py \\
        --db-path data/refit_new_markets_2026-10-15/cs2_series_rounds/cs2_history.db \\
        --out-dir data/refit_new_markets_2026-10-15/cs2_series_rounds
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import cs2, cs2_engine, epochs  # noqa: E402
from bet.sofa import sport_confidence as scf  # noqa: E402

TARGET = "config/" + scf.CALIBRATION_FILE
GATE_MIN_N = 300
GATE_MAX_SHORTFALL = 0.02  # realised - curve >= -0.02 (one-sided)
BOOTSTRAP = 2000
FAMILIES = cs2_engine.SERIES_ROUND_FAMILIES
SuperbetLine = tuple[str, float, str, str]


def _ts(day: str) -> int:
    return scf.day_ts(day)


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat().replace("+00:00", "Z")


def home_oriented(family: str, line: float, side: str, subject_side: str | None,
                  home_is_team1: bool) -> SuperbetLine | None:
    """A graded Superbet side in the home / away orientation the history uses.
    rounds_handicap's line is team1's handicap on team1 - team2 rounds
    (cs2.grade): with team1 away, home - away = -(t1 - t2), so the side flips
    and the handicap changes sign."""
    flip = {"T1": "T2", "T2": "T1"}
    if family == "rounds_total":
        return (family, line, side, "")
    if family == "rounds_handicap":
        if side not in flip:
            return None
        return (family, line, side, "") if home_is_team1 else \
            (family, -line, flip[side], "")
    if family == "team_rounds" and subject_side in flip:
        subject = subject_side if home_is_team1 else flip[subject_side]
        return (family, line, side, subject)
    return None


def superbet_lines(runs_dir: str, first: str, last: str
                   ) -> tuple[dict[int, list[SuperbetLine]],
                              dict[tuple[int, SuperbetLine], int]]:
    """Sofascore event id -> the series-rounds sides CS2_SETTLE graded
    WIN / LOSS (home oriented), and each side's graded outcome (1 = WIN)."""
    lines: dict[int, list[SuperbetLine]] = defaultdict(list)
    outcome: dict[tuple[int, SuperbetLine], int] = {}
    d, end = date.fromisoformat(first), date.fromisoformat(last)
    while d <= end:
        path = Path(runs_dir) / "cs2" / d.isoformat() / "settled.json"
        d += timedelta(days=1)
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        for entry in (doc.get("events") or {}).values():
            eid = entry.get("sofascore_event_id")
            if eid is None or entry.get("home_is_team1") is None:
                continue
            for g in entry.get("graded") or []:
                if g.get("family") not in FAMILIES or g.get("line") is None \
                        or g.get("outcome") not in ("WIN", "LOSS"):
                    continue
                subj = cs2.team_of(str(g.get("subject") or ""),
                                   str(entry.get("team1") or ""),
                                   str(entry.get("team2") or ""))
                if subj is None and g["family"] == "team_rounds":
                    # older settled.json entries carry no team names: the
                    # match name is "team1·team2"
                    parts = str(entry.get("match_name") or "").split("·")
                    if len(parts) == 2:
                        subj = cs2.team_of(str(g.get("subject") or ""),
                                           parts[0], parts[1])
                ln = home_oriented(str(g["family"]), float(g["line"]),
                                   str(g["side"]), subj,
                                   bool(entry["home_is_team1"]))
                if ln is None:
                    continue
                key = (int(eid), ln)
                if key not in outcome:
                    lines[int(eid)].append(ln)
                    outcome[key] = 1 if g["outcome"] == "WIN" else 0
    return dict(lines), outcome


def _logloss(p: float, y: int) -> float:
    q = min(max(p, 1e-6), 1 - 1e-6)
    return -math.log(q if y else 1.0 - q)


def base_rates(rows: Sequence[scf.Row]) -> dict[tuple[Any, ...], float]:
    """The fit window's realised rate per (family, format, line, side) - the
    line's base rate a model must beat (team_rounds: both teams pooled)."""
    acc: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    for r in rows:
        acc[(r["family"], r.get("best_of"), r["line"], r["side"])].append(int(r["y"]))
    return {k: sum(v) / len(v) for k, v in acc.items() if len(v) >= 30}


def skill(rows: Sequence[scf.Row], base: Mapping[tuple[Any, ...], float],
          seed: int = 11) -> dict[str, Any]:
    """Per key: log-loss of the model's p minus the base rate's, paired on
    the rows with a base rate, with a 95% bootstrap interval over games."""
    by_key: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        b = base.get((r["family"], r.get("best_of"), r["line"], r["side"]))
        if b is None:
            continue
        y = int(r["y"])
        by_key[r["key"]][str(r["game"])].append(
            _logloss(float(r["p"]), y) - _logloss(b, y))
    rng = random.Random(seed)
    out: dict[str, Any] = {}
    for key, games in sorted(by_key.items()):
        ids = list(games)
        n = sum(len(v) for v in games.values())
        diff = sum(sum(v) for v in games.values()) / n
        stats = []
        for _ in range(BOOTSTRAP):
            s = c = 0.0
            for _ in ids:
                g = games[ids[rng.randrange(len(ids))]]
                s += sum(g)
                c += len(g)
            stats.append(s / c)
        stats.sort()
        out[key] = {"n": n, "games": len(ids), "diff": round(diff, 5),
                    "diff_lo": round(stats[int(0.025 * BOOTSTRAP)], 5),
                    "diff_hi": round(stats[int(0.975 * BOOTSTRAP)], 5)}
    return out


def share_printable(curves: Mapping[str, Any], rows: Sequence[scf.Row]
                    ) -> dict[str, dict[str, Any]]:
    """Per key: covered rows and the share whose curve value is >= 0.70."""
    acc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        entry = scf._find(curves.get(r["key"]) or {}, float(r["p"]))
        if entry is None:
            continue
        acc[r["key"]][0] += 1
        acc[r["key"]][1] += float(entry["realised_lo95"]) >= scf.PRINTABLE_FROM
    return {k: {"covered": c, "printable": p,
                "share": round(p / c, 4) if c else 0.0}
            for k, (c, p) in sorted(acc.items())}


def gate_key(check: Mapping[str, Any] | None, admission_reason: str | None
             ) -> dict[str, Any]:
    out: dict[str, Any] = {"pass": False}
    pr = (check or {}).get("printable") or {}
    n = int(pr.get("n") or 0)
    out["holdout_printable_n"] = n
    out["holdout_printable_games"] = int(pr.get("games") or 0)
    if n:
        gap = pr["realised_minus_confidence"]
        out["holdout_printable_confidence"] = pr["confidence"]
        out["holdout_printable_realised"] = pr["realised"]
        out["holdout_gap"] = gap[0]
        out["holdout_gap_95"] = [gap[1], gap[2]]
    out["holdout_n_covered"] = int((check or {}).get("n") or 0)
    out["sport_admission"] = admission_reason or "ADMITTED"
    reasons: list[str] = []
    if n < GATE_MIN_N:
        reasons.append(f"HOLDOUT_PRINTABLE_N<{GATE_MIN_N} (n={n})")
    elif float(out["holdout_gap"]) < -GATE_MAX_SHORTFALL:
        reasons.append(f"HOLDOUT_SHORTFALL>{GATE_MAX_SHORTFALL:.2f} "
                       f"({float(out['holdout_gap']):+.4f})")
    if admission_reason is not None:
        reasons.append(f"SPORT_ADMISSION: {admission_reason}")
    out["pass"] = not reasons
    out["reasons"] = reasons
    return out


def run(args: argparse.Namespace) -> dict[str, Any]:
    out = Path(args.out_dir)
    final_ts = _ts(args.final_before)
    fit_ts, hold_end = _ts(args.fit_before), _ts(args.holdout_end)
    first = datetime.strptime(args.final_before, "%Y-%m-%d").replace(tzinfo=UTC)
    switches = {"team_rounds_race": epochs.cs2_team_rounds_race(
                    args.final_before, first),
                "map_identity": epochs.cs2_map_identity(args.final_before, first)}
    sb_lines, sb_outcome = superbet_lines(args.runs_dir, args.superbet_from,
                                          args.superbet_to)
    t0 = time.monotonic()
    maps, series = scf.load_cs2(args.db_path, final_ts)
    rows = [r for r in scf.cs2_walk_forward_rows(
        maps, series, 0, final_ts, "history", switches["team_rounds_race"],
        switches["map_identity"], series_rounds=True,
        series_round_lines=sb_lines) if r["family"] in FAMILIES]
    print(f"walk-forward: {len(rows)} rows, {time.monotonic() - t0:.0f} s",
          file=sys.stderr, flush=True)
    hist = [r for r in rows if r["source"] == "history"]
    sets = {
        "fit": [r for r in hist if r["ts"] < fit_ts],
        "holdout": [r for r in hist if fit_ts <= r["ts"] < hold_end],
        "final": hist,
        "superbet": [r for r in rows if r["source"] == "history_superbet"],
    }
    mismatch = 0
    for r in sets["superbet"]:
        ln = (r["family"], float(r["line"]), r["side"], r["subject"])
        if sb_outcome.get((int(str(r["game"])[2:]), ln)) not in (None, r["y"]):
            mismatch += 1
    rows_dir = out / "rows"
    rows_dir.mkdir(parents=True, exist_ok=True)
    for name, rs in sets.items():
        if name != "final":
            (rows_dir / f"{name}.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in rs), encoding="utf-8")
    fit_curves = scf.fit_curves(sets["fit"])
    check = scf.evaluate(fit_curves, sets["holdout"])
    sb_check = scf.evaluate(fit_curves, sets["superbet"])
    admitted, refused = scf.admission(fit_curves, {"history_holdout": check})
    _, refused_with_sb = scf.admission(
        fit_curves, {"history_holdout": check, "superbet_lines": sb_check})
    base = base_rates(sets["fit"])
    sk = skill(sets["holdout"], base)
    sk_sb = skill(sets["superbet"], base)
    share = share_printable(fit_curves, sets["holdout"])
    share_sb = share_printable(fit_curves, sets["superbet"])
    final_curves = scf.fit_curves(sets["final"])
    gate: dict[str, Any] = {}
    for key in sorted({r["key"] for r in hist}):
        if key not in fit_curves:
            entry: dict[str, Any] = {
                "pass": False, "reasons": [f"NO_FIT_BUCKET_WITH_N>={scf.MIN_BUCKET}"]}
        else:
            entry = gate_key(check.get(key),
                             None if key in admitted else refused.get(key))
            entry["holdout_buckets"] = (check.get(key) or {}).get("buckets", {})
            entry["holdout_logloss_confidence"] = (check.get(key) or {}).get(
                "logloss_confidence")
        entry["logloss_vs_base"] = sk.get(key)
        entry["share_printable"] = share.get(key)
        sbk = sb_check.get(key) or {}
        entry["superbet_lines"] = {
            "n_covered": sbk.get("n", 0), "uncovered": sbk.get("uncovered", 0),
            "games": sbk.get("games", 0), "buckets": sbk.get("buckets", {}),
            "printable": sbk.get("printable"),
            "realised_minus_confidence": sbk.get("realised_minus_confidence"),
            "logloss_vs_base": sk_sb.get(key), "share_printable": share_sb.get(key),
            "admission_with_superbet": refused_with_sb.get(key, "ADMITTED")}
        entry["fit_curve"] = fit_curves.get(key, {})
        entry["final_curve"] = final_curves.get(key, {})
        if entry["pass"] and key not in final_curves:
            entry["pass"] = False
            entry["reasons"] = [f"FINAL_NO_BUCKET_WITH_N>={scf.MIN_BUCKET}"]
        gate[f"cs2:{key}"] = entry
    windows = {"fit": [_iso(min(r["ts"] for r in sets["fit"])), _iso(fit_ts)],
               "holdout": [_iso(fit_ts), _iso(hold_end)],
               "final": [_iso(min(r["ts"] for r in hist)), _iso(final_ts)]}
    return {
        "switches": switches, "windows_utc": windows,
        "rows": {k: len(v) for k, v in sets.items()},
        "games": {k: len({r["game"] for r in v}) for k, v in sets.items()},
        "superbet_events": len(sb_lines),
        "superbet_sides": sum(len(v) for v in sb_lines.values()),
        "superbet_outcome_mismatch": mismatch,
        "gate": gate,
    }


def assemble(part: Mapping[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    fitted_at = datetime.now(UTC).isoformat(timespec="seconds")
    passing = sorted(k.split(":", 1)[1] for k, g in part["gate"].items() if g["pass"])
    prov = {
        "script": "scripts/sofa/fit_cs2_series_rounds.py",
        "fitted_at_utc": fitted_at, "db_path": args.db_path,
        "before": args.final_before, "fit_window_utc": part["windows_utc"]["final"],
        "gate_fit_window_utc": part["windows_utc"]["fit"],
        "gate_holdout_window_utc": part["windows_utc"]["holdout"],
        "forecast_source": "cs2_engine.series_rounds_side_p",
        "estimator_switches": part["switches"],
        "lines": "sport_confidence.CS2_SERIES_ROUND_LINES",
    }
    sports: dict[str, Any] = {}
    if passing:
        sports["cs2"] = {
            "curves": {k: part["gate"][f"cs2:{k}"]["final_curve"] for k in passing},
            "curve_source": {k: "history" for k in passing},
            "admitted": passing,
            "fitted_from_by_key": {k: prov for k in passing},
        }
    return {
        "target": TARGET,
        "also_target": "config/" + scf.NEXT_CALIBRATION_FILE,
        "fitted_from": {
            **prov,
            "gate": {"fit_before": args.fit_before,
                     "holdout": [args.fit_before, args.holdout_end],
                     "min_n": GATE_MIN_N,
                     "realised_minus_curve_at_least": -GATE_MAX_SHORTFALL,
                     "sport_admission": "sport_confidence.admission on the "
                                        "holdout (MIN_BUCKET 200, "
                                        "MAX_OVERSTATEMENT 0.03)"},
            "never_mid_day": True,
            "installed": False,
        },
        "edges": scf.EDGES,
        "min_bucket": scf.MIN_BUCKET,
        "sports": sports,
        "gate": {k: {kk: vv for kk, vv in g.items()
                     if kk not in ("fit_curve",)} for k, g in part["gate"].items()},
    }


def _f(v: Any, nd: int = 3) -> str:
    return "-" if v is None else f"{float(v):.{nd}f}".replace(".", ",")


def _ci(d: Mapping[str, Any] | None) -> str:
    if not d:
        return "-"
    return f"{d['diff']:+.4f} [{d['diff_lo']:+.4f}; {d['diff_hi']:+.4f}]"


def report_md(doc: Mapping[str, Any], part: Mapping[str, Any]) -> str:
    w, r, g = part["windows_utc"], part["rows"], part["games"]
    lines = [
        "# CS2: rundy serii - dopasowanie krzywych i bramka (2026-10-15, "
        "NIE zainstalowane)", "",
        "Skrypt: `scripts/sofa/fit_cs2_series_rounds.py`; kopia tabel CS2: "
        f"`{doc['fitted_from']['db_path']}`. Ceny nie ma w modelu.", "",
        f"- fit: {w['fit'][0][:10]}..{w['fit'][1][:10]} - {r['fit']} wierszy, "
        f"{g['fit']} serii",
        f"- holdout: {w['holdout'][0][:10]}..{w['holdout'][1][:10]} (bez końca) - "
        f"{r['holdout']} wierszy, {g['holdout']} serii",
        f"- final: {w['final'][0][:10]}..{w['final'][1][:10]} - {r['final']} "
        f"wierszy, {g['final']} serii",
        f"- linie Superbetu (CS2_SETTLE 2026-09-28..10-13): {part['superbet_events']}"
        f" zdarzeń, {part['superbet_sides']} stron; w historii {r['superbet']} "
        f"wierszy / {g['superbet']} serii; niezgodne wyniki z CS2_SETTLE: "
        f"{part['superbet_outcome_mismatch']}", "",
        "## Bramka (jednostronna, operator 2026-10-14)", "",
        f"Druk = wiersze holdoutu z wartością krzywej (realised_lo95) >= 0,70. "
        f"PASS: n >= {GATE_MIN_N} i zrealizowane - krzywa >= "
        f"-{GATE_MAX_SHORTFALL:.2f}, ORAZ `sport_confidence.admission` na "
        "holdoucie (żaden kubełek n >= 200 nie zawyża o > 3 pp; druk łącznie "
        "nie zawyża).", "",
        "| klucz | wynik | druk n (serie) | krzywa | zrealizowane | luka [95%] | "
        "udział >= 0,70 | LL model - baza [95%] | powód |",
        "|---|---|---|---|---|---|---|---|---|"]
    for key, e in sorted(doc["gate"].items()):
        gap = (f"{e['holdout_gap']:+.4f} [{e['holdout_gap_95'][0]:+.4f}; "
               f"{e['holdout_gap_95'][1]:+.4f}]" if "holdout_gap" in e else "-")
        sh = e.get("share_printable") or {}
        lines.append(
            f"| `{key.replace('|', chr(92) + '|')}` | "
            f"{'PASS' if e['pass'] else 'FAIL'} | "
            f"{e.get('holdout_printable_n', 0)} ({e.get('holdout_printable_games', 0)})"
            f" | {_f(e.get('holdout_printable_confidence'))} | "
            f"{_f(e.get('holdout_printable_realised'))} | {gap} | "
            f"{_f(sh.get('share'))} | {_ci(e.get('logloss_vs_base'))} | "
            f"{'; '.join(e.get('reasons') or [])} |")
    lines += ["", "## Kalibracja holdoutu po kubełkach (krzywa z okna fit)", ""]
    for key, e in sorted(doc["gate"].items()):
        hb = e.get("holdout_buckets") or {}
        cells = ", ".join(
            f"{lab}: n {b['n']}, krzywa {b['confidence']:.3f}, zreal. "
            f"{b['realised']:.3f}" for lab, b in hb.items())
        lines.append(f"- `{key}`: {cells or '-'}")
    lines += ["", "## Linie Superbetu (druga populacja, nie bramka)", "",
              "| klucz | n (serie) | druk n | druk: krzywa / zreal. / luka [95%] | "
              "udział >= 0,70 | LL model - baza [95%] | dopuszczenie z liniami SB |",
              "|---|---|---|---|---|---|---|"]
    for key, e in sorted(doc["gate"].items()):
        sb = e.get("superbet_lines") or {}
        pr = sb.get("printable") or {}
        prs = (f"{_f(pr.get('confidence'))} / {_f(pr.get('realised'))} / "
               f"{pr['realised_minus_confidence'][0]:+.4f} "
               f"[{pr['realised_minus_confidence'][1]:+.4f}; "
               f"{pr['realised_minus_confidence'][2]:+.4f}]" if pr else "-")
        sh = sb.get("share_printable") or {}
        lines.append(
            f"| `{key.replace('|', chr(92) + '|')}` | {sb.get('n_covered', 0)} "
            f"({sb.get('games', 0)}) | {pr.get('n', 0)} | {prs} | "
            f"{_f(sh.get('share'))} | {_ci(sb.get('logloss_vs_base'))} | "
            f"{sb.get('admission_with_superbet')} |")
    lines += ["", "## Krzywe końcowe (PASS, okno final)", ""]
    for sport, sec in doc["sports"].items():
        for key, curve in sec["curves"].items():
            cells = ", ".join(f"{lab}: {b['realised_lo95']:.3f} (n {b['n']})"
                              for lab, b in curve.items())
            lines.append(f"- {sport} `{key}`: {cells}")
    if not doc["sports"]:
        lines.append("Żaden klucz nie przeszedł bramki - `sports` jest puste.")
    lines += ["", "Kształt `curves.json` jak `sport_derived/curves.json` "
              "(`sports.cs2.curves / curve_source / admitted / "
              "fitted_from_by_key`, `gate[\"cs2:<klucz>\"].pass`); "
              "`install_new_market_curves.py` grupa `cs2_series_rounds`."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db-path", required=True,
                    help="a COPY of the CS2 history tables (never data/sofa.db)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument("--fit-before", default="2026-09-01")
    ap.add_argument("--holdout-end", default="2026-10-14",
                    help="holdout end, exclusive (default: through 2026-10-13)")
    ap.add_argument("--final-before", default="2026-10-15")
    ap.add_argument("--superbet-from", default="2026-09-28")
    ap.add_argument("--superbet-to", default="2026-10-13")
    args = ap.parse_args(argv)
    if Path(args.db_path).resolve() == (_REPO / "data" / "sofa.db").resolve():
        ap.error("--db-path must be a copy, not the live database")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    part = run(args)
    (out / "partial_cs2.json").write_text(json.dumps(part, indent=1) + "\n",
                                          encoding="utf-8")
    doc = assemble(part, args)
    (out / "curves.json").write_text(json.dumps(doc, indent=1) + "\n",
                                     encoding="utf-8")
    (out / "gate_report.md").write_text(report_md(doc, part), encoding="utf-8")
    print(json.dumps({k: [g["pass"], g.get("reasons")] for k, g in doc["gate"].items()},
                     indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
