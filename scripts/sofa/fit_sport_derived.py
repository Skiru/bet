#!/usr/bin/env python3
"""Fit and gate the history curves of the measured sports' derived markets
(plan docs/sofa/history/PLAN_KRZYWE_NOWE_RYNKI_2026-10-14.md, steps 2-4).

shadow.DERIVED_MARKETS (epochs.SPORT_DERIVED_MARKETS_FROM_UTC): hockey and
basketball double chance (game, period / half / quarter; regulation), and
volleyball's team_wins_set, team_sets_exact and sets_count. They have no
history curve today, so SPORT_CONFIDENCE reads them through their own settled
Superbet lines only (NO_LINE_EVIDENCE until a bucket holds 50). This STAGES
curves for them - it never writes config/.

Per sport, on a COPY of the history tables (--db-path; never data/sofa.db):

1. walk-forward rows (sport_confidence.walk_forward_rows, the replay the sport
   curves are fitted on, the estimator switches of --final-before's first
   build, markets = DERIVED_HISTORY_MARKETS):
   * fit       [--fit-before - fit-days, --fit-before), thinned to --max-games
   * holdout   [--fit-before, --holdout-end), every game
   * final     [--final-before - fit-days, --final-before), thinned
2. curves (sport_confidence.fit_curves: EDGES buckets, MIN_BUCKET 200, the
   bucket's Wilson lower bound `realised_lo95` is the confidence) on fit;
3. gate per key on the holdout read through the fit curve
   (sport_confidence.evaluate): the rows whose curve value >= 0.70 pooled,
   n >= GATE_MIN_N and realised - curve value >= -GATE_MAX_GAP - ONE-SIDED
   since 2026-10-14 ~18:55Z (operator): only an overstating curve fails; the
   old two-sided verdict (|gap| <= GATE_MAX_GAP, measure_calibration.py's
   PASS) is kept as `two_sided_pass` - AND fit_sport_confidence's own
   admission rule (sport_confidence.admission: no out-of-sample bucket of
   n >= 200 more than 3 pp above realised, printable rows pooled not
   overstating; one-sided already); a draw-free "12" key FAILS by policy
   (no skill over the line's base rate, measured 2026-10-14,
   docs/sofa/evidence/sport_derived_2026-10-14.md; its log-loss against the
   base rate is still reported), and so does a key whose final curve has
   no bucket reaching 0.70 (it would print nothing);
4. a passing key's curve is refitted on `final` and written in the sport
   calibration's own shape (`sports.<sport>.curves / curve_source /
   admitted`) to <out>/curves.json; failing keys never enter `sports`.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_sport_derived.py \\
        --db-path data/refit_new_markets_2026-10-15/sport_derived/sport_history.db \\
        --out-dir data/refit_new_markets_2026-10-15/sport_derived --sport hockey
    ... --assemble   # after every sport: curves.json + gate_report.md
    ... --regate     # no replay: re-gate rows/<sport>_*.jsonl, then --assemble

No price is read. Read-only on the database.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import epochs  # noqa: E402
from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa.score_model import load_events  # noqa: E402
from bet.sofa.shadow import SPORTS  # noqa: E402
from scripts.sofa import measure_sport_derived as msd  # noqa: E402

TARGET = "config/" + scf.CALIBRATION_FILE
GATE_MIN_N = 300  # measure_calibration.py's PASS: n >= 300 ...
GATE_MAX_GAP = 0.02  # ... and |realised - confidence| <= 2 pp
NO_DRAW_SIDES = frozenset({"12"})
SCORE_SPORTS = ("hockey", "basketball", "volleyball")
# The lines a key's history rows were scored on, where the live market may
# post others: the curve says nothing about those (as
# sport_confidence.FITTED_LINES for CS2's team rounds). Superbet posted
# "wygra dokładnie N set(y)" at N = 1 and 2 only on 2026-10-14 (32 sides).
FITTED_LINES: dict[str, dict[str, list[float]]] = {
    "volleyball": {"team_sets_exact": [float(x)
                                       for x in scf.DERIVED_EXACT_SET_LINES]},
}


def _ts(day: str) -> int:
    return scf.day_ts(day)


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat().replace("+00:00", "Z")


def estimator_switches(sport: str, day: str) -> dict[str, Any]:
    """The score model's switches on `day`'s first build (as
    fit_sport_confidence reads them for --before)."""
    first = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC)
    return {
        "freshness": sport == "basketball" and epochs.bb_freshness_enabled(day, first),
        "overtime": sport == "basketball" and epochs.bb_overtime(day, first),
        "strict_league_rate": epochs.league_rate_rule(day, first),
        "pace": sport == "basketball" and epochs.bb_pace(day, first),
        "pace_level": sport == "basketball" and epochs.bb_pace_level(day, first),
        "hk_shots": epochs.hk_shots(day, first) if sport == "hockey" else None,
        "hk_empty_net": sport == "hockey" and epochs.hk_empty_net(day, first),
        "set_length": sport == "volleyball" and epochs.vb_set_length(day, first),
    }


def side_of_key(key: str) -> str:
    return key.split("|", 1)[1]


def gate_key(key: str, check: Mapping[str, Any] | None,
             admission_reason: str | None, skill: Mapping[str, Any] | None
             ) -> dict[str, Any]:
    """One key's verdict from its holdout check (sport_confidence.evaluate's
    entry), the sport admission's refusal (None = admitted) and the log-loss
    against the base rate (measure_sport_derived.summarise's entry)."""
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
    out["holdout_uncovered"] = int((check or {}).get("uncovered") or 0)
    out["sport_admission"] = admission_reason or "ADMITTED"
    if skill:
        out["logloss_vs_base"] = {
            k: skill[k] for k in ("logloss_model", "logloss_base", "diff",
                                  "diff_lo", "diff_hi", "n", "games")}
    reasons: list[str] = []
    gap = float(out["holdout_gap"]) if n else None
    if n < GATE_MIN_N:
        reasons.append(f"HOLDOUT_PRINTABLE_N<{GATE_MIN_N} (n={n})")
    elif gap is not None and gap < -GATE_MAX_GAP - 1e-9:
        reasons.append(f"HOLDOUT_OVERSTATES>{GATE_MAX_GAP:.2f} ({gap:+.4f})")
    if admission_reason is not None:
        reasons.append(f"SPORT_ADMISSION: {admission_reason}")
    if side_of_key(key) in NO_DRAW_SIDES:
        d = (f"{skill['diff']:+.4f} [{skill['diff_lo']:+.4f}, "
             f"{skill['diff_hi']:+.4f}]" if skill else "not measured")
        reasons.append(f"NO_DRAW_POLICY: log-loss vs base rate {d}")
    out["pass"] = not reasons
    out["reasons"] = reasons
    out["rule"] = "one_sided"
    out["two_sided_pass"] = (
        gap is not None and n >= GATE_MIN_N and abs(gap) <= GATE_MAX_GAP + 1e-9
        and admission_reason is None
        and (side_of_key(key) not in NO_DRAW_SIDES
             or (skill is not None and float(skill["diff_hi"]) < 0)))
    return out


def _events(db_path: str, sport: str, cache: Path) -> dict[int, Any]:
    path = cache / f"{sport}.pkl"
    if path.exists():
        data: dict[int, Any] = pickle.loads(path.read_bytes())
        return data
    events = load_events(db_path, SPORTS[sport])  # type: ignore[index]
    cache.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(events))
    return events


def judge(rows: Mapping[str, Sequence[scf.Row]],
          skill: Mapping[str, Any]) -> dict[str, Any]:
    """Every key's verdict from the fit / holdout / final rows and the
    holdout's log-loss against the base rate (reported only)."""
    fit_curves = scf.fit_curves(rows["fit"])
    check = scf.evaluate(fit_curves, rows["holdout"])
    admitted, refused = scf.admission(fit_curves, {"history_holdout": check})
    final_curves = scf.fit_curves(rows["final"])
    keys = sorted({r["key"] for rs in rows.values() for r in rs})
    gate: dict[str, Any] = {}
    for key in keys:
        if key not in fit_curves:
            entry: dict[str, Any] = {
                "pass": False, "two_sided_pass": False,
                "reasons": [f"NO_FIT_BUCKET_WITH_N>={scf.MIN_BUCKET}"]}
        else:
            entry = gate_key(key, check.get(key),
                             None if key in admitted else refused.get(key),
                             skill.get(key))
            entry["holdout_buckets"] = (check.get(key) or {}).get("buckets", {})
        entry["fit_curve"] = fit_curves.get(key, {})
        entry["final_curve"] = final_curves.get(key, {})
        if entry["pass"] and key not in final_curves:
            entry["pass"] = False
            entry["reasons"] = [f"FINAL_NO_BUCKET_WITH_N>={scf.MIN_BUCKET}"]
        elif entry["pass"] and not any(
                float(b["realised_lo95"]) >= scf.PRINTABLE_FROM
                for b in final_curves[key].values()):
            entry["pass"] = False
            entry["reasons"] = [f"FINAL_CURVE_BELOW_{scf.PRINTABLE_FROM} "
                                "(prints nothing)"]
        gate[key] = entry
    return gate


def regate_sport(sport: str, out: Path) -> dict[str, Any]:
    """Re-decide a saved sport from rows/<sport>_{fit,holdout,final}.jsonl;
    the log-loss against the base rate is taken from the saved partial
    (reported, never decisive)."""
    part: dict[str, Any] = json.loads(
        (out / f"partial_{sport}.json").read_text(encoding="utf-8"))
    rows: dict[str, list[scf.Row]] = {}
    for name in ("fit", "holdout", "final"):
        path = out / "rows" / f"{sport}_{name}.jsonl"
        rows[name] = [json.loads(line) for line in
                      path.read_text(encoding="utf-8").splitlines() if line]
    skill = {k: g["logloss_vs_base"] for k, g in part["gate"].items()
             if g.get("logloss_vs_base")}
    previous = sorted(k for k, g in part["gate"].items() if g.get("pass"))
    part["gate"] = judge(rows, skill)
    part["regated"] = {"at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                       "rule": "one_sided", "previous_pass": previous,
                       "from": f"rows/{sport}_{{fit,holdout,final}}.jsonl"}
    (out / f"partial_{sport}.json").write_text(
        json.dumps(part, indent=1) + "\n", encoding="utf-8")
    return part


def run_sport(sport: str, args: argparse.Namespace) -> dict[str, Any]:
    out = Path(args.out_dir)
    shadow_sport = SPORTS[sport]  # type: ignore[index]
    final_ts = _ts(args.final_before)
    fit_ts, hold_end = _ts(args.fit_before), _ts(args.holdout_end)
    span = args.fit_days * 86400
    sw = estimator_switches(sport, args.final_before)
    events = _events(args.db_path, sport, out / "events")
    history = [g for g in scf.parse_history(events, shadow_sport)
               if g.rating.ts < final_ts]
    markets = scf.DERIVED_HISTORY_MARKETS[sport]
    windows = {"fit": (fit_ts - span, fit_ts, args.max_games),
               "holdout": (fit_ts, hold_end, None),
               "final": (final_ts - span, final_ts, args.max_games)}
    rows: dict[str, list[scf.Row]] = {}
    for name, (a, b, cap) in windows.items():
        t0 = time.monotonic()
        rows[name] = scf.walk_forward_rows(
            history, shadow_sport, a, b, args.sims, cap, f"derived_{name}",
            sw["freshness"], sw["overtime"], sw["strict_league_rate"],
            sw["pace"], sw["pace_level"], sw["hk_shots"], sw["hk_empty_net"],
            sw["set_length"], False, None, markets=markets)
        print(f"{sport} {name}: {len(rows[name])} rows, "
              f"{len({r['game'] for r in rows[name]})} games, "
              f"{time.monotonic() - t0:.0f} s", file=sys.stderr, flush=True)
    rows_dir = out / "rows"
    rows_dir.mkdir(parents=True, exist_ok=True)
    for name, rs in rows.items():
        (rows_dir / f"{sport}_{name}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rs), encoding="utf-8")
    base = msd.base_rates(history, shadow_sport, fit_ts)
    skill = msd.summarise(rows["holdout"], base)
    gate = judge(rows, skill)
    partial = {
        "sport": sport,
        "switches": sw,
        "history_games_before_final": len(history),
        "windows_utc": {k: [_iso(a), _iso(b)] for k, (a, b, _) in windows.items()},
        "max_games": {k: c for k, (_, _, c) in windows.items()},
        "rows": {k: len(v) for k, v in rows.items()},
        "games": {k: len({r["game"] for r in v}) for k, v in rows.items()},
        "gate": gate,
    }
    (out / f"partial_{sport}.json").write_text(
        json.dumps(partial, indent=1) + "\n", encoding="utf-8")
    return partial


def assemble(partials: Sequence[Mapping[str, Any]], args: argparse.Namespace
             ) -> dict[str, Any]:
    """curves.json: the passing keys' final curves in the sport calibration's
    shape, plus every key's gate verdict (`<sport>:<key>`)."""
    fitted_at = datetime.now(UTC).isoformat(timespec="seconds")
    sports: dict[str, Any] = {}
    gate: dict[str, Any] = {}
    for part in partials:
        sport = str(part["sport"])
        prov = {
            "script": "scripts/sofa/fit_sport_derived.py",
            "fitted_at_utc": fitted_at,
            "db_path": args.db_path,
            "before": args.final_before,
            "fit_window_utc": part["windows_utc"]["final"],
            "max_games": part["max_games"]["final"],
            "sims": args.sims,
            "gate_fit_window_utc": part["windows_utc"]["fit"],
            "gate_holdout_window_utc": part["windows_utc"]["holdout"],
            "forecast_source": "score_model",
            "estimator_switches": part["switches"],
            "markets": "shadow.DERIVED_MARKETS (sport_confidence."
                       "DERIVED_HISTORY_MARKETS)",
        }
        passing = sorted(k for k, g in part["gate"].items() if g["pass"])
        for key, g in part["gate"].items():
            gate[f"{sport}:{key}"] = g
        if not passing:
            continue  # a sport with no PASS key is not in `sports`
        sports[sport] = {
            "curves": {k: part["gate"][k]["final_curve"] for k in passing},
            "curve_source": {k: "history" for k in passing},
            "admitted": passing,
            "fitted_from_by_key": {k: prov for k in passing},
        }
        lines = {fam: v for fam, v in FITTED_LINES.get(sport, {}).items()
                 if any(k.split("|")[0] == fam for k in passing)}
        if lines:
            sports[sport]["fitted_lines"] = lines
    return {
        "target": TARGET,
        "also_target": "config/" + scf.NEXT_CALIBRATION_FILE,
        "fitted_from": {
            "script": "scripts/sofa/fit_sport_derived.py",
            "fitted_at_utc": fitted_at,
            "db_path": args.db_path,
            "before": args.final_before,
            "max_history_date": "2026-10-14",
            "gate": {"fit_before": args.fit_before,
                     "holdout": [args.fit_before, args.holdout_end],
                     "min_n": GATE_MIN_N, "max_gap": GATE_MAX_GAP,
                     "rule": "one_sided: realised - curve >= -max_gap "
                             "(operator 2026-10-14 ~18:55Z)",
                     "sport_admission": "sport_confidence.admission "
                                        "(MIN_BUCKET 200, MAX_OVERSTATEMENT 0.03)",
                     "no_draw_policy": "12 keys fail (no skill over the base "
                                       "rate, measured 2026-10-14)"},
            "never_mid_day": True,
            "installed": False,
        },
        "edges": scf.EDGES,
        "min_bucket": scf.MIN_BUCKET,
        "sports": sports,
        "gate": gate,
    }


def _f(v: Any, nd: int = 3) -> str:
    return "-" if v is None else f"{float(v):.{nd}f}".replace(".", ",")


def report_md(doc: Mapping[str, Any], partials: Sequence[Mapping[str, Any]]) -> str:
    ff = doc["fitted_from"]
    lines = [
        "# Krzywe rynków pochodnych sportów mierzonych - dopasowanie i bramka "
        "(2026-10-15, NIE zainstalowane)", "",
        "Skrypt: `scripts/sofa/fit_sport_derived.py`, kopia tabel historii: "
        f"`{ff['db_path']}`. Ceny nie ma nigdzie.", "",
        "| sport | okno fit | holdout | final | wiersze fit / holdout / final | "
        "mecze fit / holdout / final |",
        "|---|---|---|---|---|---|"]
    for p in partials:
        w, r, g = p["windows_utc"], p["rows"], p["games"]
        lines.append(
            f"| {p['sport']} | {w['fit'][0][:10]}..{w['fit'][1][:10]} | "
            f"{w['holdout'][0][:10]}..{w['holdout'][1][:10]} | "
            f"{w['final'][0][:10]}..{w['final'][1][:10]} | "
            f"{r['fit']} / {r['holdout']} / {r['final']} | "
            f"{g['fit']} / {g['holdout']} / {g['final']} |")
    lines += [
        "", "## Bramka", "",
        f"Holdout czytany przez krzywą z okna fit. Druk = wiersze z wartością "
        f"krzywej (realised_lo95) >= 0,70. PASS (bramka jednostronna, decyzja "
        f"operatora 2026-10-14): n >= {GATE_MIN_N} i zrealizowane - krzywa >= "
        f"-{GATE_MAX_GAP * 100:.0f} pp (odpada tylko zawyżenie), ORAZ reguła "
        "dopuszczenia `fit_sport_confidence` (`sport_confidence.admission`: "
        "żaden kubełek n >= 200 nie zawyża o > 3 pp, druk łącznie nie zawyża), "
        "ORAZ klucz nie jest „12” (bez remisu: FAIL z zasady, brak przewagi "
        "nad bazą; log-loss tylko raportowana), ORAZ krzywa końcowa sięga "
        "0,70. Kolumna „dwustronna” = dawna reguła |luka| <= 2 pp, tylko do "
        "porównania. Konwencja sportów: kubełek krzywej n >= 200 "
        "(`MIN_BUCKET`, nie 400 piłki), dolna granica Wilsona jako pewność.", "",
        "| klucz | wynik | dwustronna | druk n (mecze) | krzywa | zrealizowane | "
        "luka [95%] | LL model - baza [95%] | powód |",
        "|---|---|---|---|---|---|---|---|---|"]
    for key, g in sorted(doc["gate"].items()):
        ll = g.get("logloss_vs_base")
        lld = (f"{ll['diff']:+.4f} [{ll['diff_lo']:+.4f}; {ll['diff_hi']:+.4f}]"
               if ll else "-")
        gap = (f"{g['holdout_gap']:+.4f} [{g['holdout_gap_95'][0]:+.4f}; "
               f"{g['holdout_gap_95'][1]:+.4f}]" if "holdout_gap" in g else "-")
        lines.append(
            f"| `{key.replace('|', chr(92) + '|')}` | "
            f"{'PASS' if g['pass'] else 'FAIL'} | "
            f"{'PASS' if g.get('two_sided_pass') else 'FAIL'} | "
            f"{g.get('holdout_printable_n', 0)} ({g.get('holdout_printable_games', 0)})"
            f" | {_f(g.get('holdout_printable_confidence'))} | "
            f"{_f(g.get('holdout_printable_realised'))} | {gap} | {lld} | "
            f"{'; '.join(g.get('reasons') or []) or g.get('note', '')} |")
    lines += ["", "## Krzywe końcowe (PASS, dopasowane na oknie final)", ""]
    for sport, sec in doc["sports"].items():
        for key, curve in sec["curves"].items():
            cells = ", ".join(f"{lab}: {b['realised_lo95']:.3f} (n {b['n']})"
                              for lab, b in curve.items())
            lines.append(f"- {sport} `{key}`: {cells}")
    lines += ["", SHAPE_MD]
    return "\n".join(lines) + "\n"


SHAPE_MD = """## Kształt do instalacji

`curves.json` (ten katalog):

```
{
  "target": "config/sofa_sport_confidence_calibration.json",
  "also_target": "config/sofa_sport_confidence_calibration.next.json",
  "fitted_from": {...},      # provenance; installed: false
  "edges": [...],            # == sport_confidence.EDGES (the target's)
  "min_bucket": 200,         # == sport_confidence.MIN_BUCKET (the target's)
  "sports": {
    "<sport>": {             # hockey | basketball | volleyball, PASS keys only
      "curves": {
        "<family>|<side class>": {
          "<lo>-<hi>": {"n": int, "realised": float, "realised_lo95": float},
          ...}},
      "curve_source": {"<key>": "history"},
      "admitted": ["<key>", ...],
      "fitted_from_by_key": {"<key>": {...provenance...}},
      "fitted_lines": {"<family>": [lines]}   # only where present
    }
  },
  "gate": {"<sport>:<family>|<side class>": {"pass": bool, "reasons": [...], ...}}
}
```

Klucze jak `sport_confidence.curve_key(family, side)`: `double_chance|TEAM`
(1X i X2), `double_chance|12`, `period_double_chance|...` (hokej, tercje
1-3 razem), `h1_double_chance|...`, `h2_double_chance|...`,
`quarter_double_chance|...` (koszykówka, kwarty 1-4 razem),
`team_wins_set|YES/NO`, `team_sets_exact|YES/NO` (N = 1 i 2, obie drużyny
razem), `sets_count|SETS=3/4/5`. `SportCalibration.lookup` czyta
`doc["sports"][sport]["curves"][key]` po p (kubełek `<lo>-<hi>` z
`lo <= p < hi`, n >= `min_bucket` dokumentu), przy line evidence BEZ
wymogu `admitted` - więc **do `curves` wolno włożyć tylko klucze z
`gate[...]["pass"] == true`** (`sports` zawiera wyłącznie takie).

Scalanie (na sekcję sportu `doc["sports"][sport]` pliku docelowego):

1. `section["curves"][key] = new["curves"][key]` dla każdego klucza z
   `new["sports"][sport]["curves"]` (nowe klucze - żaden z nich nie istnieje
   dziś w pliku; nadpisanie istniejącego = błąd do zgłoszenia);
2. `section["curve_source"][key] = "history"`;
3. `key` dopisany do `section["admitted"]` (bez duplikatów, posortowane)
   i usunięty z `section["not_calibrated"]`, jeśli tam jest;
4. `section.setdefault("fitted_from_by_key", {})[key] = ...` - sekcyjnego
   `section["fitted_from"]` i `section["oos"]` NIE ruszać (opisują
   istniejące krzywe); globalne `doc["fitted_from"]` dostaje np.
   `new_market_curves: {"sport_derived": new["fitted_from"]}`;
5. `fitted_lines` (np. `volleyball.team_sets_exact: [1.0, 2.0]`) NIE jest
   czytane przez `SportCalibration` - to linie, na których krzywa była
   dopasowana; linia N = 0 / 3 przeczytałaby tę samą krzywą. Do decyzji przy
   instalacji: wpis w `sport_confidence.FITTED_LINES`
   (`("volleyball", "team_sets_exact"): (1.0, 2.0)` -> `LINE_OUTSIDE_FIT`)
   albo świadome pominięcie (Superbet 10-14 wystawił tylko N = 1 i 2);
6. `doc["edges"]` i `doc["min_bucket"]` muszą być równe tym z `curves.json`
   (inaczej odmowa).

**Oba pliki:** od 2026-10-14 dzień czyta
`config/sofa_sport_confidence_calibration.next.json`
(`effective_from` 2026-10-14, `sport_confidence.calibration_path_for`) -
instalacja musi scalić te same wpisy do `.next.json` (jeśli istnieje) i do
pliku głównego, inaczej 10-15 nie zobaczy nowych krzywych.
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db-path", required=True,
                    help="a COPY of the history tables (never data/sofa.db)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--sport", choices=[*SCORE_SPORTS, "all"], default="all")
    ap.add_argument("--assemble", action="store_true",
                    help="no replay: partial_<sport>.json -> curves.json + "
                    "gate_report.md")
    ap.add_argument("--regate", action="store_true",
                    help="no replay: re-gate rows/<sport>_*.jsonl into "
                    "partial_<sport>.json (then --assemble)")
    ap.add_argument("--fit-before", default="2026-09-01")
    ap.add_argument("--holdout-end", default="2026-10-14",
                    help="holdout end, exclusive (default: through 2026-10-13)")
    ap.add_argument("--final-before", default="2026-10-15")
    ap.add_argument("--fit-days", type=int, default=365)
    ap.add_argument("--sims", type=int, default=1000)
    ap.add_argument("--max-games", type=int, default=4000,
                    help="games scored in the fit / final windows (evenly "
                    "thinned, as fit_sport_confidence); the holdout is whole")
    args = ap.parse_args(argv)
    if Path(args.db_path).resolve() == (_REPO / "data" / "sofa.db").resolve():
        ap.error("--db-path must be a copy, not the live database")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sports = list(SCORE_SPORTS) if args.sport == "all" else [args.sport]
    if args.regate:
        for sport in sports:
            regate_sport(sport, out)
        return 0
    if not args.assemble:
        for sport in sports:
            run_sport(sport, args)
        return 0
    partials = [json.loads((out / f"partial_{s}.json").read_text(encoding="utf-8"))
                for s in SCORE_SPORTS if (out / f"partial_{s}.json").exists()]
    doc = assemble(partials, args)
    (out / "curves.json").write_text(json.dumps(doc, indent=1) + "\n",
                                     encoding="utf-8")
    (out / "gate_report.md").write_text(report_md(doc, partials), encoding="utf-8")
    print(json.dumps({k: g["pass"] for k, g in doc["gate"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
