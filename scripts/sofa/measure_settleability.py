#!/usr/bin/env python3
"""How many printed legs had no grade by D+3? Measured (plan 2026-10-05, F0.6).

For every day in range, every football / tennis leg the coupon's PDF printed
(11_coupon.json on a stats-only day, else 08_confidence.json; the lists
SETTLE grades: printed_singles and the legs of printed_builders) is looked up
in sofa_settled_row (the day's row, else the same key under another live
date; 07_settled_printed.json for a leg with no sheet row) and its first
grade time compared with the end of D+``--horizon-days`` (UTC). A leg on an
event SETTLE found moved > 48 h or awarded, or that pushed, is void (owed no
grade) and out of the denominator.

The first grade time is the row's settled_at, or the earliest
old_settled_at in runs/sofa/regrade_*.json for its id (regrade overwrites
settled_at). A late grade is split: PROCESS when the event's statistics were
in the cache before the horizon (nobody re-settled the day), DATA when they
were fetched after it.

A day whose horizon has not passed yet is reported apart ("as of now") and
left out of the headline.

Measurement only: the DB is opened read-only, nothing the pipeline reads is
written. Writes the JSON (and a Polish markdown summary) only where asked.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_settleability.py \\
        --from 2026-09-19 --to 2026-10-04 \\
        --json-out docs/sofa/evidence/settleability_2026-10-05.json \\
        --md-out docs/sofa/evidence/settleability_2026-10-05.md
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import settleability as st  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.timeutil import now  # noqa: E402


def open_read_only(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)


def collect(
    conn: sqlite3.Connection,
    runs_dir: Path,
    days: list[str],
    horizon_days: int,
) -> dict[str, list[st.LegState]]:
    first = st.first_graded_times(st.load_regrade_logs(runs_dir))
    return {d: st.day_states(conn, runs_dir, d, first, horizon_days) for d in days}


def _table(tallies: dict[Any, st.Tally], label: Callable[[Any], str],
           top: int | None = None, min_due: int = 1) -> list[dict[str, Any]]:
    rows = [
        {"group": label(k), **t.as_dict()}
        for k, t in tallies.items()
        if t.due >= min_due
    ]
    rows.sort(key=lambda r: (-(r["unsettled_at_horizon"] or 0), r["group"]))
    return rows[:top] if top else rows


def summarise(
    states_by_day: dict[str, list[st.LegState]],
    horizon_days: int,
    at: datetime,
) -> dict[str, Any]:
    closed = [d for d in states_by_day
              if st.horizon_end(d, horizon_days) <= at]
    open_days = [d for d in states_by_day if d not in closed]
    headline = [s for d in closed for s in states_by_day[d]]
    total = st.Tally()
    for s in headline:
        total.add(s)

    def comp(s: st.LegState) -> tuple[Any, str, str]:
        return (s.leg.competition_id, s.leg.competition_name, s.leg.sport)

    def comp_label(k: tuple[Any, str, str]) -> str:
        return f"{k[1]} [{k[0]}] ({k[2]})"

    def comp_fam(s: st.LegState) -> tuple[Any, str, str]:
        return (s.leg.competition_id, s.leg.competition_name, s.leg.family)

    def comp_fam_label(k: tuple[Any, str, str]) -> str:
        return f"{k[1]} [{k[0]}] / {k[2]}"

    late_reasons: dict[str, int] = {}
    for s in headline:
        if s.status == st.UNGRADED:
            key = str(s.reason)
            late_reasons[key] = late_reasons.get(key, 0) + 1

    return {
        "measured_at_utc": at.isoformat(timespec="seconds"),
        "horizon_days": horizon_days,
        "days_closed": closed,
        "days_open": open_days,
        "headline": total.as_dict(),
        "by_day": {
            d: {**_tally(states_by_day[d]).as_dict(), "closed": d in closed}
            for d in sorted(states_by_day)
        },
        "by_family": _table(st.tally_by(headline, lambda s: s.leg.family), str),
        "by_sport": _table(st.tally_by(headline, lambda s: s.leg.sport), str),
        "by_competition": _table(st.tally_by(headline, comp), comp_label, top=60),
        "by_competition_family": _table(
            st.tally_by(headline, comp_fam), comp_fam_label, top=60, min_due=3),
        "ungraded_reasons": dict(sorted(late_reasons.items(), key=lambda kv: -kv[1])),
        "open_days_as_of_now": _tally(
            [s for d in open_days for s in states_by_day[d]]).as_dict(),
    }


def gated_residual(states: list[st.LegState],
                   refused: list[dict[str, Any]]) -> dict[str, Any]:
    """The headline over the legs a gate of these cells would have left (in
    sample: the cells were fitted on the same legs)."""
    cells = {(e["competition_id"], e["family"]) for e in refused}
    kept = [s for s in states if st.cell_key(s.leg.competition_id, s.leg.market)
            not in cells]
    return {**_tally(kept).as_dict(), "removed": len(states) - len(kept)}


def out_of_sample(states_by_day: dict[str, list[st.LegState]],
                  closed: list[str], fit_to: str) -> dict[str, Any]:
    """Cells fitted on the closed days <= fit_to, applied to the later ones."""
    fit = [s for d in closed if d <= fit_to for s in states_by_day[d]]
    test_days = [d for d in closed if d > fit_to]
    test = [s for d in test_days for s in states_by_day[d]]
    refused = st.fit_refusals(fit)
    return {
        "fit_to": fit_to,
        "test_days": test_days,
        "cells": [[e["competition_id"], e["family"]] for e in refused],
        "without_gate": _tally(test).as_dict(),
        "with_gate": gated_residual(test, refused),
    }


def _tally(states: list[st.LegState]) -> st.Tally:
    t = st.Tally()
    for s in states:
        t.add(s)
    return t


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.1f}%"


def render_md(doc: dict[str, Any], fitted: list[dict[str, Any]] | None = None) -> str:
    h = doc["headline"]
    lines = [
        f"# Rozliczalność wydrukowanych nóg (D+{doc['horizon_days']})",
        "",
        f"Pomiar: `scripts/sofa/measure_settleability.py`, {doc['measured_at_utc']}. "
        "Nogi: wszystko, co wydrukował PDF kuponu (11_coupon.json / "
        "08_confidence.json) - single i nogi builderów, piłka i tenis (sporty "
        "mierzone rozlicza się osobno). Ocena: "
        "`sofa_settled_row` (wiersz dnia, inaczej ten sam klucz pod inną datą), "
        "`07_settled_printed.json`. Pierwsze "
        "rozliczenie = `settled_at` albo najwcześniejsze `old_settled_at` z "
        "`runs/sofa/regrade_*.json`. Zwrot (przełożony > 48 h, walkower) i PUSH nie "
        "są winne rozliczenia - poza mianownikiem.",
        "",
        f"Dni z minionym horyzontem: {', '.join(doc['days_closed'])}. "
        f"Dni bez horyzontu (stan na teraz, poza wynikiem): "
        f"{', '.join(doc['days_open']) or 'brak'}.",
        "",
        "## Wynik",
        "",
        f"- **Nierozliczone po D+{doc['horizon_days']}: {h['unsettled_at_horizon']} "
        f"z {h['due']} nóg ({_pct(h['unsettled_share'])}, dolna granica Wilsona "
        f"{_pct(h['unsettled_wilson_lo'])}).** Kryterium planu F0.6: < 2% przez 7 dni "
        "- dziś niespełnione.",
        f"- z tego rozliczone później: {h['graded_later']} (w tym "
        f"{h['graded_later_process']} z danymi w cache przed horyzontem - proces: "
        "nikt nie rozliczył dnia ponownie), nadal nierozliczone: "
        f"{h['ungraded_now']} {h['ungraded_by_class']}.",
        f"- zwroty / PUSH: {h['voided']} z {h['printed']} wydrukowanych.",
    ]
    lines += ["", "## Według dnia", "",
              "| dzień | należne | nierozl. D+3 | % | później (proces) | nadal "
              "| horyzont |",
              "|---|---|---|---|---|---|---|"]
    for d, t in doc["by_day"].items():
        lines.append(
            f"| {d} | {t['due']} | {t['unsettled_at_horizon']} | "
            f"{_pct(t['unsettled_share'])} | {t['graded_later']} "
            f"({t['graded_later_process']}) | {t['ungraded_now']} | "
            f"{'minął' if t['closed'] else 'nie minął'} |")
    lines += ["", "## Według rodziny rynku", "",
              "| rodzina | należne | nierozl. D+3 | % | Wilson dolna "
              "| nadal (brak danych) |",
              "|---|---|---|---|---|---|"]
    for t in doc["by_family"]:
        lines.append(
            f"| {t['group']} | {t['due']} | {t['unsettled_at_horizon']} | "
            f"{_pct(t['unsettled_share'])} | {_pct(t['unsettled_wilson_lo'])} | "
            f"{t['ungraded_by_class'].get(st.DATA_GAP, 0)} |")
    lines += ["", "## Rozgrywki z największą liczbą nierozliczonych (top 25)", "",
              "| rozgrywki | należne | nierozl. D+3 | % | nadal |",
              "|---|---|---|---|---|"]
    for t in doc["by_competition"][:25]:
        lines.append(
            f"| {t['group']} | {t['due']} | {t['unsettled_at_horizon']} | "
            f"{_pct(t['unsettled_share'])} | {t['ungraded_now']} |")
    lines += ["", "## Powody nadal nierozliczonych (SETTLE, 07_settle_skips.json)", ""]
    for reason, n in list(doc["ungraded_reasons"].items())[:20]:
        lines.append(f"- `{reason}`: {n}")
    o = doc["open_days_as_of_now"]
    lines += ["", "## Dni bez minionego horyzontu (stan na teraz)", "",
              f"- należne {o['due']}, nierozliczone {o['unsettled_at_horizon']} "
              f"({_pct(o['unsettled_share'])}) - liczba jeszcze spadnie.", ""]
    lines += [
        "## Zastrzeżenia",
        "",
        "- „Rozliczone później” ze statystyk pobranych po horyzoncie: cache trzyma "
        "tylko ostatnie pobranie, więc nie da się odróżnić, czy feed ligi zamknął "
        "się po D+3, czy nikt nie zapytał wcześniej (do 10-05 ponownie rozliczano "
        "tylko D-5). Dla bramki to górna granica braku danych.",
        "- Dni 09-20 i 09-21 drukowały same buildery; kupon do 10-04 drukował "
        "30 singli.",
        "- Pewność, ROI i krzywe nie są tu mierzone - tylko to, czy noga dostała "
        "ocenę.",
        "",
    ]
    if fitted is not None:
        lines += [
            "## Bramka rozliczalności (fit, `config/sofa_settleability.json`)",
            "",
            f"Komórka (rozgrywki, rodzina) odmawiana `{st.REFUSAL_CODE}`, "
            "gdy co najmniej "
            f"{st.MIN_LEGS} ocenionych nóg i dolna granica Wilsona (95%) udziału "
            f"nierozliczonych z braku danych > {_pct(st.MAX_UNSETTLED_LOWER)}. "
            "Brak danych = nadal nierozliczona z powodem statystyki (NO_STATISTICS, "
            "STAT_KEY_ABSENT, ...) albo rozliczona po horyzoncie ze statystyk "
            "pobranych "
            "po nim. Mecz nierozegrany, gracz / strona nierozpoznani, błąd dostawcy - "
            "poza oceną (nic nie mówią o feedzie ligi).",
            "",
            "| rozgrywki | rodzina | ocenione | brak danych | % | Wilson dolna |",
            "|---|---|---|---|---|---|",
        ]
        for e in fitted:
            lines.append(
                f"| {e['competition_name']} [{e['competition_id']}] | {e['family']} | "
                f"{e['judged']} | {e['data_unsettled']} | {_pct(e['share'])} | "
                f"{_pct(e['wilson_lo'])} |")
        g = doc.get("with_gate_in_sample")
        if g:
            lines += [
                "",
                f"Z bramką (w próbie - komórki dopasowane na tych samych nogach): "
                f"usunięte {g['removed']} nóg, nierozliczone po "
                f"D+{doc['horizon_days']} "
                f"{g['unsettled_at_horizon']} z {g['due']} "
                f"({_pct(g['unsettled_share'])}).",
            ]
        for o in doc.get("with_gate_out_of_sample") or []:
            w, g2 = o["without_gate"], o["with_gate"]
            lines.append(
                f"- Poza próbą: komórki z dni <= {o['fit_to']} ({len(o['cells'])}) na "
                f"dniach {o['test_days'][0] if o['test_days'] else '-'}.."
                f"{o['test_days'][-1] if o['test_days'] else '-'}: bez bramki "
                f"{w['unsettled_at_horizon']}/{w['due']} "
                f"({_pct(w['unsettled_share'])}), "
                f"z bramką {g2['unsettled_at_horizon']}/{g2['due']} "
                f"({_pct(g2['unsettled_share'])}), usunięte {g2['removed']} nóg.")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--horizon-days", type=int, default=st.DEFAULT_HORIZON_DAYS)
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--md-out", default=None)
    ap.add_argument(
        "--with-fit", action="store_true",
        help="also list the cells fit_settleability would refuse on these days",
    )
    ap.add_argument(
        "--oos-fit-to", action="append", default=[],
        help="(with --with-fit) fit the cells on the closed days up to this one "
        "and apply them to the later closed days - out of sample; repeatable",
    )
    args = ap.parse_args()
    config = SofaConfig.from_env()
    runs_dir = Path(config.runs_dir)
    try:
        conn = open_read_only(config.db_path)
        states = collect(conn, runs_dir, st.date_range(args.start, args.end),
                         args.horizon_days)
    except sqlite3.Error as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2
    at = now().astimezone(UTC)
    doc = summarise(states, args.horizon_days, at)
    fitted = None
    if args.with_fit:
        closed = [s for d in doc["days_closed"] for s in states[d]]
        fitted = st.fit_refusals(closed)
        doc["fit_preview"] = fitted
        doc["with_gate_in_sample"] = gated_residual(closed, fitted)
        doc["with_gate_out_of_sample"] = [
            out_of_sample(states, doc["days_closed"], cut) for cut in args.oos_fit_to
        ]
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    if args.md_out:
        Path(args.md_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md_out).write_text(render_md(doc, fitted), encoding="utf-8")
    h = doc["headline"]
    print(
        "SOFA_SUMMARY: " + json.dumps({
            "stage": "MEASURE_SETTLEABILITY",
            "verdict": "OK",
            "metrics": {
                "days_closed": len(doc["days_closed"]),
                "due": h["due"],
                "unsettled_at_horizon": h["unsettled_at_horizon"],
                "unsettled_share": h["unsettled_share"],
                "graded_later": h["graded_later"],
                "ungraded_now": h["ungraded_now"],
                "fit_preview_cells": len(fitted) if fitted is not None else None,
            },
        }),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
