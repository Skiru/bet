#!/usr/bin/env python3
"""Printed confidence against the realised rate, per curve, per sport, per
ledger variant (plan docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md, F2.1).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_calibration.py \\
        --from 2026-10-05 --to 2026-10-05 --epoch stats_only
    ... --from 2026-09-19 --to 2026-10-04 --epoch old       # reference
    ... --write-config --before 2026-10-07                   # between days

Every printed position is read graded exactly as the ledger records it
(record_results.graded_confidence: audit_settlement 7c / 7i for football
and tennis, coupon_sports for the measured sports' legs on the one coupon) and
measured by bet.sofa.calibration_audit: gap = mean confidence - realised, a 95%
interval from resampling matches, PASS / FAIL / INSUFFICIENT per curve.
Variants (and so epochs) are never pooled.

Writes docs/sofa/evidence/kalibracja_<from>_<to>_<epoch>.md (Polish) and
.json, unless --out-dir -. Read-only on runs/ and the database.

--write-config --before <d> writes config/sofa_curve_status.json: the FAIL
curves of `official` in the stats-only epoch, measured on days strictly
before <d>, applying from <d>. Refused when <d> already has a confidence
artifact (that would change a day mid-way) or the window reaches <d>. The file
refuses nothing until the operator sets epochs.CURVE_STATUS_FROM_UTC.

Exit 0 = measured (INSUFFICIENT is an answer); 1 = a curve FAILs; 2 = a crash.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import calibration_audit as ca  # noqa: E402
from bet.sofa import curve_status  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.clv import MIN_CLUSTERS  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.epochs import OLD, STATS_ONLY  # noqa: E402
from bet.sofa.fit_meta import fit_stamp  # noqa: E402
from bet.sofa.settleability import date_range as days  # noqa: E402
from scripts.sofa.record_results import graded_confidence  # noqa: E402

EPOCHS = {"stats_only": (STATS_ONLY,), "old": (OLD,), "all": (STATS_ONLY, OLD)}
CONFIG_VARIANT = "official"
EVIDENCE_DIR = _REPO / "docs" / "sofa" / "evidence"


def collect(runs_dir: str, dates: list[str], db_path: str
            ) -> tuple[list[ca.CalLeg], dict[str, dict[str, int]]]:
    """Every settled printed position of the window, and per "variant|epoch"
    the outcomes that are not a result (pending, refunds, unsettled...)."""
    legs: list[ca.CalLeg] = []
    other: dict[str, dict[str, int]] = {}
    for date in dates:
        for g in graded_confidence(runs_dir, date, db_path):
            got, rest = ca.legs_from_positions(
                date, g["variant"], g["epoch"], g["singles"], g["builders"])
            legs += got
            acc = other.setdefault(f"{g['variant']}|{g['epoch']}", {})
            for k, n in rest.items():
                acc[k] = acc.get(k, 0) + n
    return legs, other


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:.1f}"


def _ci(ci: tuple[float, float] | None) -> str:
    return "-" if ci is None else f"[{100 * ci[0]:+.1f}; {100 * ci[1]:+.1f}]"


def _cell(text: str) -> str:
    """A curve name in a markdown table: its "|" would split the cell."""
    return text.replace("|", "\\|")


def _table(results: list[ca.CurveResult]) -> list[str]:
    lines = [
        "| wariant | epoka | sport | krzywa | drukowane | rozliczone | mecze "
        "| pewność % | realizacja % | luka pp | 95% (po meczach) pp | werdykt |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        gap = "-" if r.gap is None else f"{100 * r.gap:+.1f}"
        lines.append(
            f"| {r.variant} | {r.epoch} | {r.sport} | `{_cell(r.curve)}` | "
            f"{r.n_printed} | "
            f"{r.n_settled} | "
            f"{r.n_matches} | {_pct(r.mean_confidence)} | {_pct(r.realised)} | "
            f"{gap} | {_ci(r.ci95)} | {r.verdict} |"
        )
    return lines


def render_md(doc: dict[str, Any], variants: list[ca.CurveResult],
              sports: list[ca.CurveResult], curves: list[ca.CurveResult]) -> str:
    counts: dict[str, int] = {}
    for r in curves:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1
    out = [
        f"# Kalibracja: drukowana pewność a realizacja, {doc['from']}..{doc['to']} "
        f"(epoka: {doc['epoch']})",
        "",
        f"Wygenerowane {doc['generated_at_utc']} przez "
        "`scripts/sofa/measure_calibration.py` (plan "
        "`docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md`, F2.1). Tylko odczyt: "
        "nogi ocenione dokładnie tak, jak zapisuje je ledger "
        "(`record_results.graded_confidence`: 7c / 7i, sporty przez "
        "`coupon_sports`).",
        "",
        "- **luka = średnia pewność - realizacja** (dodatnia = pewność zawyżona);",
        "  przedział 95% z losowania całych **meczów** (nie nóg; 2000 prób,",
        f"  ziarno 7; poniżej {MIN_CLUSTERS} meczów brak przedziału).",
        f"- **PASS**: n >= {ca.MIN_SETTLED} rozliczonych, |luka| <= "
        f"{100 * ca.MAX_GAP:.0f} pp i przedział zawiera 0; **FAIL**: n >= "
        f"{ca.MIN_SETTLED} i nie; **INSUFFICIENT**: n < {ca.MIN_SETTLED}.",
        "- Liczą się tylko WIN / LOSS. Zwroty, VOID, PENDING, UNSETTLED, "
        "MISMATCH, NOT_GRADED są w tabeli „nie liczone”, nigdy jako wynik.",
        "- Warianty (a więc epoki) **nigdy nie są sumowane**: `official` "
        "(stats_only od 2026-10-05 07:15Z), `official:pre_stats_only` "
        "(nogi zablokowane z porannego wydruku 10-05), `official` dnia sprzed "
        "10-05 (stara reguła), `removed:reads` (nogi "
        "zdjęte odczytem - nie kupon).",
        "- Wiersze „sport” i „wariant” (krzywa `*`) sumują krzywe danego sportu / "
        "wariantu - to podsumowanie, nie werdykt o żadnej krzywej.",
        "- Builder (`builder:combined_probability`) to jedna pozycja na kupon "
        "przy jego `combined_probability`; nie jest krzywą CONFIDENCE.",
        "",
    ]
    if doc["epoch"] in ("old", "all"):
        out += [
            "**Uwaga dla epoki `old`:** okno sprzed 10-05 obejmuje kilka epok "
            "refitu (krzywe zainstalowane 09-26, 10-03 i 10-05 02:52Z) - ta sama "
            "nazwa krzywej to w nich różne krzywe. Wynik jest odniesieniem, "
            "nie werdyktem o krzywych dziś zainstalowanych.",
            "",
        ]
    out += [
        f"Werdykty krzywych: PASS {counts.get(ca.PASS, 0)} · FAIL "
        f"{counts.get(ca.FAIL, 0)} · INSUFFICIENT {counts.get(ca.INSUFFICIENT, 0)}.",
        "",
        "## Wariant (wszystkie krzywe razem)",
        "",
        *_table(variants),
        "",
        "## Sport (krzywe sportu razem)",
        "",
        *_table(sports),
        "",
        "## Krzywa (`calibrated_on`)",
        "",
        *_table(curves),
        "",
        "## Nie liczone (poza WIN / LOSS)",
        "",
        "| wariant / epoka | wyniki |",
        "|---|---|",
    ]
    for variant, rest in sorted(doc["not_counted"].items()):
        txt = ", ".join(f"{k} {n}" for k, n in sorted(rest.items())) or "-"
        out.append(f"| {variant.replace('|', ' / ')} | {txt} |")
    if not any(r.n_settled for r in variants):
        out += ["", "**Brak rozliczonych nóg w oknie** - każda krzywa "
                "INSUFFICIENT; zgodność pewności z realizacją nie jest zmierzona."]
    out.append("")
    return "\n".join(out)


def write_config(path: Path, before: str, start: str, end: str, db_path: str,
                 curves: list[ca.CurveResult]) -> dict[str, Any]:
    if Path(db_path).exists():
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            stamp = fit_stamp(conn)
        finally:
            conn.close()
    else:
        stamp = {"fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds")}
    doc = {
        "fitted_from": {
            **stamp,
            "script": "scripts/sofa/measure_calibration.py",
            "window": [start, end],
            "before": before,
            "variant": CONFIG_VARIANT,
            "epoch": STATS_ONLY,
            "rule": (f"FAIL = n_settled >= {ca.MIN_SETTLED} and (|gap| > "
                     f"{ca.MAX_GAP} or the match-bootstrap 95% interval "
                     "excludes 0)"),
        },
        "applies_from_date": before,
        "enforced_from_utc_constant": "bet.sofa.epochs.CURVE_STATUS_FROM_UTC",
        "failed_curves": ca.failed_curves(curves, CONFIG_VARIANT, STATS_ONLY),
    }
    write_atomic(path, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    return doc


def write_config_refusal(runs_dir: str, before: str, end: str) -> str | None:
    """Why --write-config must not run, or None."""
    if end >= before:
        return (f"REFUSED: the window ends {end}, not strictly before {before}; "
                "a status for day <d> is measured on days before it")
    day = Path(runs_dir) / before
    built = [n for n in ("08_confidence.json", "08_confidence_sports.json",
                         "11_coupon.json") if (day / n).exists()]
    if built:
        return (f"REFUSED: {before} already has {', '.join(built)} - writing "
                "the curve status now would change that day mid-way; write it "
                "between days, before the day's first CONFIDENCE")
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--epoch", choices=sorted(EPOCHS), default="all")
    ap.add_argument("--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"))
    ap.add_argument("--db", default=None, help="default: SofaConfig db_path")
    ap.add_argument("--out-dir", default=str(EVIDENCE_DIR),
                    help="where the .md / .json go; '-' writes none")
    ap.add_argument("--write-config", action="store_true")
    ap.add_argument("--before", default=None)
    ap.add_argument("--config", default=None,
                    help="status file (default config/"
                    f"{curve_status.CURVE_STATUS_FILE})")
    args = ap.parse_args()
    db_path = args.db or SofaConfig.from_env().db_path
    if args.write_config:
        if not args.before:
            ap.error("--write-config needs --before <d>")
        why = write_config_refusal(args.runs_dir, args.before, args.end)
        if why:
            print(why, file=sys.stderr)
            return 2
    legs, other = collect(args.runs_dir, days(args.start, args.end), db_path)
    wanted = EPOCHS[args.epoch]
    legs = [leg for leg in legs if leg.epoch in wanted]
    other = {k: n for k, n in other.items() if k.split("|")[1] in wanted}
    curves = ca.by_curve(legs)
    sports = ca.by_sport(legs)
    variants = ca.by_variant(legs)
    doc: dict[str, Any] = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "from": args.start, "to": args.end, "epoch": args.epoch,
        "rule": {"min_settled": ca.MIN_SETTLED, "max_gap": ca.MAX_GAP,
                 "bootstrap": "matches, 2000 draws, seed 7",
                 "min_matches": MIN_CLUSTERS},
        "by_variant": [r.to_json() for r in variants],
        "by_sport": [r.to_json() for r in sports],
        "by_curve": [r.to_json() for r in curves],
        "not_counted": other,
    }
    md = render_md(doc, variants, sports, curves)
    print(md)
    if args.out_dir != "-":
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        stem = f"kalibracja_{args.start}_{args.end}_{args.epoch}"
        write_atomic(out / f"{stem}.md", md)
        write_atomic(out / f"{stem}.json",
                     json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        print(f"\nwritten: {out / stem}.md / .json")
    if args.write_config:
        path = Path(args.config) if args.config else curve_status.default_path()
        status = write_config(path, args.before, args.start, args.end, db_path, curves)
        print(f"curve status: {path} - {len(status['failed_curves'])} failed curve(s), "
              f"applies from {args.before}; refuses nothing until "
              "epochs.CURVE_STATUS_FROM_UTC is set")
    return 1 if any(r.verdict == ca.FAIL for r in curves) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - a crash is FAILED, never PARTIAL
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
