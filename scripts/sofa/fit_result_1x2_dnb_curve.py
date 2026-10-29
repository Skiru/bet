#!/usr/bin/env python3
"""The season-phase-aware history curves of football 1X2 (home / away win)
and draw no bet, with their holdout gate - fitted and STAGED, never
installed by this script.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_result_1x2_dnb_curve.py \\
        --out-dir data/refit_new_markets_2026-10-15/football_result_1x2_dnb \\
        [--history data/cache/football_history.pkl] [--from 2024-10-01] \\
        [--holdout-from 2026-09-01] [--holdout-to 2026-10-14] \\
        [--before 2026-10-15] [--result-config config/sofa_football_result.json] \\
        [--matches-cache <out-dir>/matches.csv.gz]

Why: docs/sofa/evidence/football_result_phase_2026-10-13.md (D1) - DNB failed
its threshold because the HISTORY CURVE overstated at the season start
(-2.9 pp test, -3.5 pp Aug-Sep) while the raw NB p on the pure rating was
calibrated; 1X2 -4.08 pp after the curve. Candidate measured here (operator
2026-10-14 ~18:55Z): a curve CLASS by season phase - `season_early` (the
match's as-of phase is `early`, season_phase.phases_by_event) apart from the
rest - next to the variant "no curve, the raw NB p".

Replay: as fit_double_chance_curve.replay (the parsed football history
pickle, read-only; the rating book holds only earlier matches; both sides'
PURE rating goals centres; NB with `nb_r` from config/sofa_football_result.json;
UNLINKED left out - SHEET's row carries CROSS_LEAGUE_UNLINKED and CONFIDENCE
refuses it). Per match (football_result.result_probs arithmetic):

    result_1x2|OVER   subject "1": P(home win), y = home won (90 min)
                      subject "2": P(away win), y = away won
    draw_no_bet|OVER  subject "1" (the rung's OVER = the home side):
                      P(home | no draw) = h / (h + a), y = home won
    draw_no_bet|UNDER the away side: a / (h + a), y = away won
                      - a draw is a refund (Superbet voids the stake), so a
                      drawn match is no DNB forecast at all.

A p outside [P_FLOOR, P_CEILING] is not priced (engine.outside_model_resolution).

Classes (as CONFIDENCE reads them, `Calibration.realised(..., klass)`):
`women` - a women's match (confidence.match_class, every phase);
`season_early` - a men's match whose as-of phase is `early`
(football_1x2_dnb.curve_class); the unclassed key - every other men's match
(mid / late / final / no phase). Every key is fitted on its own rows only.

Gate (new_market_gate.gate, the one-sided rule): the curve fitted on
[--from, --holdout-from) read on [--holdout-from, --holdout-to); PASS =
curve value >= 0.70 forecasts n >= 300 and realised - curve >= -2 pp, and the
final curve must reach 0.70 (new_market_gate.require_final). The final curve
of every key is refitted on [--from, --before); only PASSING keys go into
`by_market_direction` / `by_class`. Reported beside it, never installed:
the same keys without the phase class (one curve for every men's match) and
"raw p" (no curve: p >= 0.70 forecasts, realised - p).

Writes curves.json (the installer's shape: `target`, `group`,
`fitted_from`, `by_market_direction`, `by_class`, `gate` keyed
"<market>|<DIR>" / "<class>:<market>|<DIR>"), rows.csv.gz and
gate_report.md. Exit 0, 2 on a crash.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import pickle
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import football_1x2_dnb as rp  # noqa: E402
from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa import football_result as res  # noqa: E402
from bet.sofa.config import config_path  # noqa: E402
from bet.sofa.engine import outside_model_resolution  # noqa: E402
from bet.sofa.season_phase import PHASE_EARLY, phases_by_event  # noqa: E402
from scripts.sofa import fit_double_chance_curve as dc_fit  # noqa: E402
from scripts.sofa import new_market_gate as gate_mod  # noqa: E402
from scripts.sofa.fit_double_chance_curve import Match, replay  # noqa: E402

TARGET = "config/sofa_confidence_calibration.json"
GROUP = "football_result_1x2_dnb"
CHUNK = 20000
KEYS = (f"{rp.RESULT_1X2}|OVER", f"{rp.DRAW_NO_BET}|OVER",
        f"{rp.DRAW_NO_BET}|UNDER")
CLASSES = (None, rp.CLASS_SEASON_EARLY, rp.CLASS_WOMEN)


@dataclass(frozen=True)
class PhasedMatch:
    m: Match
    phase: str | None


@dataclass(frozen=True)
class Sel:
    pm: PhasedMatch
    key: str  # "<market>|<DIR>"
    side: str  # "1" home / "2" away
    p: float
    y: int

    @property
    def klass(self) -> str | None:
        return rp.curve_class(self.pm.m.women, self.pm.phase)


def _ts(day: str) -> int:
    d = date.fromisoformat(day)
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())


AWARDED_TAG = "|awarded_excluded"


def load_matches(hist_path: Path, from_ts: int, cut: int,
                 cache: Path | None, awarded_out: bool = False,
                 ) -> tuple[str, list[PhasedMatch]]:
    """The replayed matches; `awarded_out` (--awarded-excluded,
    epochs.AWARDED_EXCLUDED, as SHEET's history from 2026-10-30): results
    awarded at the table are neither rating history nor targets. The
    fingerprint carries AWARDED_TAG so a --matches-cache written under the
    other rule is refused, never mixed."""
    if cache is not None and cache.exists():
        out: list[PhasedMatch] = []
        with gzip.open(cache, "rt") as fh:
            rd = csv.DictReader(fh)
            fp = ""
            for row in rd:
                fp = row["fingerprint"]
                out.append(PhasedMatch(Match(
                    int(row["ts"]), int(row["event_id"]), row["women"] == "1",
                    row["link"], float(row["lh"]), float(row["la"]),
                    int(row["x"]), int(row["y"])), row["phase"] or None))
        held = fp.endswith(AWARDED_TAG)
        if out and held != awarded_out:  # no rows: no rule to disagree with
            raise SystemExit(
                f"{cache} was written {'with' if held else 'without'}"
                " --awarded-excluded; this run asks the other rule - drop the "
                "cache or match the flag")
        return fp, out
    fingerprint, history = pickle.loads(hist_path.read_bytes())
    if awarded_out:
        history = fr.without_awarded(history)
        fingerprint = f"{fingerprint}{AWARDED_TAG}"
    phases = phases_by_event(history)
    matches = replay(history, from_ts, cut)
    del history
    out = [PhasedMatch(m, phases.get(m.event_id)) for m in matches]
    if cache is not None:
        with gzip.open(cache, "wt", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["fingerprint", "ts", "event_id", "women", "link", "lh",
                        "la", "x", "y", "phase"])
            for pm in out:
                m = pm.m
                w.writerow([fingerprint, m.ts, m.event_id, int(m.women), m.link,
                            repr(m.lh), repr(m.la), m.x, m.y, pm.phase or ""])
    return str(fingerprint), out


def price(matches: Sequence[PhasedMatch], nb_r: float) -> list[Sel]:
    linked = [pm for pm in matches if pm.m.link != fr.UNLINKED
              and pm.m.lh > 0 and pm.m.la > 0]
    if not linked:
        return []
    lh = np.array([pm.m.lh for pm in linked])
    la = np.array([pm.m.la for pm in linked])
    probs = np.concatenate([
        res.market_probs(res.score_grid(res.count_pmf(lh[i:i + CHUNK], nb_r),
                                        res.count_pmf(la[i:i + CHUNK], nb_r)))
        for i in range(0, len(linked), CHUNK)])
    out: list[Sel] = []
    k1x2, kdo, kdu = KEYS
    for pm, (h, _d, a) in zip(linked, probs, strict=True):
        x, y = pm.m.x, pm.m.y
        cand = [(k1x2, "1", float(h), int(x > y)), (k1x2, "2", float(a), int(y > x))]
        if x != y:  # a draw voids DNB
            cand += [(kdo, "1", float(h / (h + a)), int(x > y)),
                     (kdu, "2", float(a / (h + a)), int(y > x))]
        for key, side, p, yy in cand:
            if outside_model_resolution(p):
                continue
            out.append(Sel(pm, key, side, p, yy))
    return out


def _fc(rows: Iterable[Sel]) -> list[gate_mod.Forecast]:
    return [(r.p, r.y, r.pm.m.event_id) for r in rows]


def class_key(klass: str | None, key: str) -> str:
    return key if klass is None else f"{klass}:{key}"


def raw_gate(rows: Sequence[Sel]) -> dict[str, Any]:
    """No curve: forecasts with p >= PRINT_FLOOR, realised - p."""
    pr = [r for r in rows if r.p >= gate_mod.PRINT_FLOOR]
    if not pr:
        return {"n": 0, "gap": None}
    n = len(pr)
    mp = sum(r.p for r in pr) / n
    real = sum(r.y for r in pr) / n
    lo, hi = gate_mod._boot_gap([r.pm.m.event_id for r in pr],
                                [r.y - r.p for r in pr], gate_mod.BOOT_REPS, 0)
    return {"n": n, "mean_p": round(mp, 4), "realised": round(real, 4),
            "gap": round(real - mp, 4), "gap_ci95": [round(lo, 4), round(hi, 4)],
            "would_pass_one_sided": gate_mod.one_sided_pass(n, real - mp)}


def run(sels: Sequence[Sel], h0: int, h1: int, cut: int) -> dict[str, Any]:
    train = [s for s in sels if s.pm.m.ts < h0]
    hold = [s for s in sels if h0 <= s.pm.m.ts < h1]
    final_rows = [s for s in sels if s.pm.m.ts < cut]

    def pick(rows: Iterable[Sel], key: str,
             pred: Callable[[Sel], bool]) -> list[Sel]:
        return [s for s in rows if s.key == key and pred(s)]

    training: dict[str, Any] = {}
    final: dict[str, Any] = {}
    gates: dict[str, Any] = {}
    diag: dict[str, Any] = {}
    for key in KEYS:
        for klass in CLASSES:
            ck = class_key(klass, key)

            def in_class(s: Sel, k: str | None = klass) -> bool:
                return s.klass == k
            training[ck] = gate_mod.fit_curve(
                (s.p, s.y) for s in pick(train, key, in_class))
            final[ck] = gate_mod.fit_curve(
                (s.p, s.y) for s in pick(final_rows, key, in_class))
            pop = pick(hold, key, in_class)
            g = gate_mod.gate(training[ck], _fc(pop))
            gates[ck] = gate_mod.require_final(g, final[ck])
            d: dict[str, Any] = {"raw_p": raw_gate(pop)}
            if key.startswith(rp.RESULT_1X2):
                for side in ("1", "2"):
                    sp = [s for s in pop if s.side == side]
                    d[f"side {side}"] = gate_mod.gate(training[ck], _fc(sp))
                    d[f"side {side} raw_p"] = raw_gate(sp)
            diag[ck] = d
        # without the phase class: one curve for every men's match
        men = lambda s: not s.pm.m.women  # noqa: E731
        c_np = gate_mod.fit_curve((s.p, s.y) for s in pick(train, key, men))
        pop_men = pick(hold, key, men)
        diag[f"{key} (men, no phase class)"] = {
            "gate": gate_mod.gate(c_np, _fc(pop_men)),
            "early only": gate_mod.gate(c_np, _fc(
                s for s in pop_men if s.pm.phase == PHASE_EARLY)),
            "rest only": gate_mod.gate(c_np, _fc(
                s for s in pop_men if s.pm.phase != PHASE_EARLY)),
            "raw_p": raw_gate(pop_men)}
    counts = {"train": len(train), "holdout": len(hold), "final": len(final_rows),
              "holdout_by_class": {
                  str(k): sum(1 for s in hold if s.klass == k) for k in CLASSES}}
    return {"training": training, "final": final, "gate": gates,
            "diagnostics": diag, "counts": counts}


def _raw_line(name: str, g: dict[str, Any]) -> str:
    if g.get("gap") is None:
        return f"- {name}: raw p >= 0.70 n {g.get('n', 0)}"
    lo, hi = g["gap_ci95"]
    return (f"- {name}: raw p >= 0.70 n {g['n']}, mean p {g['mean_p']:.4f}, "
            f"realised {g['realised']:.4f}, gap {100 * g['gap']:+.2f} pp "
            f"[{100 * lo:+.2f}, {100 * hi:+.2f}]")


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--history")
    ap.add_argument("--from", dest="from_", default="2024-10-01")
    ap.add_argument("--holdout-from", default="2026-09-01")
    ap.add_argument("--holdout-to", default="2026-10-14")
    ap.add_argument("--before", default="2026-10-15")
    ap.add_argument("--result-config")
    ap.add_argument("--awarded-excluded", action="store_true", help=(
        "results awarded at the table out of the rating history and the "
        "targets (epochs.AWARDED_EXCLUDED, SHEET from 2026-10-30)"))
    ap.add_argument("--matches-cache", help="replayed matches (csv.gz): read "
                    "when present, else written")
    ap.add_argument("--cup-strength", nargs="?", const="", default=None,
                    metavar="CONFIG", help="the book with the cup league strength "
                    "(fit_double_chance_curve.set_cup)")
    args = ap.parse_args()
    dc_fit.set_cup(args.cup_strength)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    hist_path = Path(args.history or _REPO / "data" / "cache" / "football_history.pkl")
    cfg_path = Path(args.result_config) if args.result_config else config_path(
        res.CONFIG_FILE)
    cfg = res.load_config(cfg_path)
    h0, h1, cut = _ts(args.holdout_from), _ts(args.holdout_to), _ts(args.before)
    fingerprint, matches = load_matches(
        hist_path, _ts(args.from_), cut,
        Path(args.matches_cache) if args.matches_cache else None,
        awarded_out=args.awarded_excluded)
    sels = price(matches, cfg.nb_r)
    result = run(sels, h0, h1, cut)
    passing = {k for k, g in result["gate"].items() if g["pass"]}
    fitted_from = {
        "history": str(hist_path), "history_fingerprint": fingerprint,
        "window": [args.from_, args.before], "before": args.before,
        "fitted_at_utc": datetime.now(UTC).isoformat(),
        "script": "scripts/sofa/fit_result_1x2_dnb_curve.py",
        "awarded_excluded": bool(args.awarded_excluded),
        "estimator": "football_result.result_probs: NB goals on the pure "
                     "rating centres (FootballForecast.centre goals_for), "
                     f"nb_r {cfg.nb_r} from {cfg_path}; DNB = P(side | no draw)",
        "classes": {"season_early": "men's match, as-of phase early "
                    "(season_phase.phases_by_event; football_1x2_dnb.curve_class)",
                    "women": "women's match, every phase",
                    "(none)": "men's match, any other phase or none"},
        "nb_r": cfg.nb_r, "nb_r_source": cfg.source,
        "cup_strength": (None if dc_fit.CUP is None
                         else args.cup_strength or "config"),
        "matches_rated": len(matches),
        "matches_unlinked_excluded": sum(1 for pm in matches
                                         if pm.m.link == fr.UNLINKED),
        "selections": result["counts"],
        "holdout": {"train_window": [args.from_, args.holdout_from],
                    "holdout_window": [args.holdout_from, args.holdout_to],
                    "rule": gate_mod.RULE_TEXT},
    }
    by_md: dict[str, Any] = {}
    by_class: dict[str, Any] = {}
    for ck in sorted(passing):
        if ":" in ck:
            klass, key = ck.split(":", 1)
            by_class.setdefault(klass, {"by_market_direction": {}})[
                "by_market_direction"][key] = result["final"][ck]
        else:
            by_md[ck] = result["final"][ck]
    doc: dict[str, Any] = {
        "target": TARGET, "group": GROUP, "fitted_from": fitted_from,
        "by_market_direction": by_md, "by_class": by_class,
        "gate": result["gate"], "gate_diagnostics": result["diagnostics"],
        "training_curves": result["training"],
        "final_curves_all_keys": result["final"],
    }
    (out / "curves.json").write_text(json.dumps(doc, indent=1) + "\n")
    with gzip.open(out / "rows.csv.gz", "wt", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["phase", "season_phase", "class", "start_ts", "event_id",
                    "women", "lh", "la", "home_goals", "away_goals", "key",
                    "side", "p", "y", "train_curve_value"])
        for s in sels:
            m = s.pm.m
            win = ("train" if m.ts < h0 else "holdout" if m.ts < h1
                   else "final_only")
            cv = gate_mod.curve_value(
                result["training"][class_key(s.klass, s.key)], s.p)
            w.writerow([win, s.pm.phase or "", s.klass or "", m.ts, m.event_id,
                        int(m.women), round(m.lh, 5), round(m.la, 5), m.x, m.y,
                        s.key, s.side, round(s.p, 6), s.y,
                        "" if cv is None else cv])
    lines = [f"# 1X2 / DNB with a season-phase curve class - holdout gate "
             f"({args.holdout_from} .. {args.holdout_to}, train {args.from_} ..)",
             "", f"nb_r {cfg.nb_r}; rated matches {len(matches)}, UNLINKED left "
             f"out {fitted_from['matches_unlinked_excluded']}; selections "
             f"{result['counts']}", "", f"rule: {gate_mod.RULE_TEXT}", ""]
    for key in KEYS:
        for klass in CLASSES:
            ck = class_key(klass, key)
            lines += gate_mod.gate_lines(ck, result["gate"][ck])
            d = result["diagnostics"][ck]
            lines.append(_raw_line(f"{ck} no curve", d["raw_p"]))
            for side in ("1", "2"):
                if f"side {side}" in d:
                    g = d[f"side {side}"]
                    lines.append(
                        f"- {ck} side {side}: n {g['n']}, gap "
                        + ("-" if g.get("gap") is None
                           else f"{100 * g['gap']:+.2f} pp "
                           f"[{100 * g['gap_ci95'][0]:+.2f}, "
                           f"{100 * g['gap_ci95'][1]:+.2f}]")
                        + f" ({'PASS' if g['pass'] else 'FAIL'})")
                    lines.append(_raw_line(f"{ck} side {side} no curve",
                                           d[f"side {side} raw_p"]))
            lines.append("")
        d = result["diagnostics"][f"{key} (men, no phase class)"]
        lines += gate_mod.gate_lines(f"{key} men, NO phase class (diagnostic)",
                                     d["gate"])
        for part in ("early only", "rest only"):
            g = d[part]
            lines.append(f"- no-class curve, {part}: n {g['n']}, gap "
                         + ("-" if g.get("gap") is None
                            else f"{100 * g['gap']:+.2f} pp"))
        lines.append(_raw_line(f"{key} men no curve", d["raw_p"]))
        lines.append("")
    for ck, c in result["final"].items():
        lines.append(f"## final curve {ck} (before {args.before})"
                     + ("" if ck in passing else " - not installable (FAIL)"))
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
