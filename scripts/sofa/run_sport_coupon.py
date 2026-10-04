#!/usr/bin/env python3
"""Build the experimental per-sport coupon from the day's measurement snapshots.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_coupon.py \\
        --date 2026-09-30 --sport hockey
    ... --sport all

Reads the snapshots of <d> AND <d+1> (runs/sofa/cs2/<d>/snapshots.jsonl or
runs/sofa/shadow/<sport>/<d>/snapshots.jsonl; refresh them first:
`run_pipeline.py --only CS2`, `run_shadow.py --horizon-h 24` - Superbet
only) for kickoffs up to 06:00 Warsaw on <d+1>, an optional vetoes.json in
<d>'s directory, and the previous build of <d> (legs that have started are
kept as printed), and writes into <d>'s directory:

    sport_coupon.json         the legs, the rule, what the rule would have done
                              on every settled day on disk, why the rest dropped
    sport_coupon.md
    sport_coupon_builds.jsonl every build appended - what each PDF held
    KUPON_<d>_<SPORT>.pdf

Refuses a day whose window has closed: its coupon is a record.

A price-only selector - see src/bet/sofa/sport_coupon.py for why, and for the
boundaries it keeps. It is NOT the coupon, is never written into
runs/sofa/<d>/, and its result is graded by settle_sport_coupon.py, never
pooled with the coupon's. No bridge, no Sofascore, no network.

Exit: 0 OK, 1 PARTIAL (a sport had no snapshots, no legs, or a veto that
matched nothing), 2 FAILED.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import sport_coupon as sc  # noqa: E402
from bet.sofa.atomic import tmp_path  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cs2 import append_records, write_atomic  # noqa: E402
from bet.sofa.timeutil import frozen_clock_refusal, now  # noqa: E402

WARSAW = ZoneInfo("Europe/Warsaw")


def local(raw: str) -> str:
    at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return at.astimezone(WARSAW).strftime("%d.%m %H:%M")


def settled_dates(runs_dir: str, sport: sc.SportKey, before: str) -> list[str]:
    """Every day of this sport with a settled.json, strictly before `before`."""
    root = sc.day_dir(runs_dir, sport, before).parent
    if not root.exists():
        return []
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and p.name < before and (p / "settled.json").exists()
    )


def load_previous(directory: Path, date: str) -> dict[str, Any] | None:
    path = directory / sc.COUPON_FILE
    if not path.exists():
        return None
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return doc if doc.get("date") == date else None


def build(
    sport: sc.SportKey, date: str, runs_dir: str, at: datetime, rule: sc.Rule
) -> dict[str, Any]:
    directory = sc.day_dir(runs_dir, sport, date)
    stats: dict[str, Any] = {}
    events, snapshots = sc.day_events(runs_dir, sport, date, stats)
    counts: dict[str, int] = {"events": len(events)}
    unsettleable = sc.unsettleable_tournaments(runs_dir, sport, date)
    # A CS2 side the series store has never seen is one CS2_SETTLE will not
    # find either (09-30: "Winners series 1x1", 30/30 NOT_ON_SOFASCORE).
    # Recorded, so audit_variants replays exactly what this build refused.
    refused: dict[str, str] = (
        sc.cs2_unseen_team_events(
            events, sc.cs2_known_team_names(SofaConfig.from_env().db_path)
        )
        if sport == "cs2"
        else {}
    )
    cands = sc.candidates(
        sport,
        events,
        at,
        rule,
        counts,
        until=sc.day_end(date),
        since=sc.day_end(sc.prev_date(date)),
        unsettleable=unsettleable,
        refused_events=refused,
    )
    vetoes = sc.load_vetoes(directory)
    previous = load_previous(directory, date)
    locked = sc.locked_legs(
        previous, at, {eid: ev.kickoff_utc for eid, ev in events.items()}
    )
    legs, vetoed = sc.select(sport, cands, vetoes, rule, locked)
    kept = {audit_key(leg) for leg in legs}
    # What an earlier build printed and this one does not: re-priced away,
    # vetoed, or gone from the board. Named, so the record says why a leg the
    # operator may have seen is no longer on the page.
    replaced = [
        {k: leg.get(k) for k in (*sc.LEG_KEY, "match_name", "odds", "kickoff_utc")}
        for leg in (previous or {}).get("legs", [])
        if audit_key(leg) not in kept
    ]
    return {
        "kind": "SPORT_COUPON_EXPERIMENT",
        "not_the_coupon": True,
        "sport": sport,
        "date": date,
        "created_at_utc": at.isoformat().replace("+00:00", "Z"),
        "window_start_utc": sc.day_end(sc.prev_date(date))
        .astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "window_end_utc": sc.day_end(date)
        .astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "probability": "fair_p = Superbet's price devigged over the market's "
        "whole outcome group; no model",
        "rule": rule.as_dict(),
        "UNFITTED_CONSTANTS": list(sc.UNFITTED_CONSTANTS),
        # what the build refused as ungradeable, and the evidence for each
        "unsettleable_tournaments": unsettleable,
        "refused_events": refused,
        "snapshots": snapshots,
        # what this build read, so audit_variants replays exactly it
        "snapshot_lines": stats["snapshot_lines"],
        "unreadable_snapshot_lines": stats["unreadable_snapshot_lines"],
        "vetoes_applied": vetoes,
        "counts": counts,
        "candidates": len(cands),
        "vetoes_file": len(vetoes),
        "vetoes_unmatched": sc.unmatched_vetoes(vetoes, cands, set(events)),
        "vetoed": vetoed,
        "locked": len(locked),
        "replaced_legs": replaced,
        "previous_build_utc": (previous or {}).get("created_at_utc"),
        "rule_history": {
            "graded_at": "last pre-start price (SETTLE), not a printed price",
            **sc.rule_history(
                runs_dir, sport, settled_dates(runs_dir, sport, date), rule
            ),
        },
        "legs": legs,
    }


def audit_key(leg: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(leg.get(k) for k in sc.LEG_KEY)


def render_md(doc: dict[str, Any]) -> str:
    sport = doc["sport"]
    h = doc["rule_history"]
    out = [
        f"# Kupon eksperymentalny {sc.SPORT_PL[sport]} - {doc['date']}",
        "",
        "**To nie jest kupon.** Eksperyment operatora, rozliczany osobno, nigdy "
        "nie łączony z kuponem. Brak modelu: pewność = cena Superbet bez marży.",
        "",
        f"UNFITTED_CONSTANTS: {', '.join(doc['UNFITTED_CONSTANTS'])}",
        "",
        f"Reguła: {json.dumps(doc['rule'], ensure_ascii=False)}",
        f"Zdarzenia w snapshotach: {doc['counts'].get('events', 0)}; "
        f"kandydatów: {doc['candidates']}; odrzucone: "
        + ", ".join(
            f"{k} {v}" for k, v in sorted(doc["counts"].items()) if k != "events"
        ),
        "",
        "Historia reguły (rozliczone dni, cena ostatnia przed startem): "
        + (
            f"n={h['n']}, trafione {h['wins']} ({h['hit']:.1%}) wobec "
            f"śr. fair p {h['mean_fair_p']:.1%}, ROI {h['roi']:+.1%}"
            + f" (void {h.get('void', 0)}, nierozliczalne {h.get('ungradeable', 0)})"
            if h.get("n")
            else "brak rozliczonych dni"
        ),
        *(
            f"- {sc.FAMILY_PL[sport].get(fam, fam)}: n={f['n']}, trafione "
            f"{f['hit']:.1%} wobec fair p "
            f"{f['mean_fair_p']:.1%}, ROI {f['roi']:+.1%}"
            for fam, f in (h.get("by_family") or {}).items()
            if f.get("n")
        ),
        "",
        "| start | mecz | rozgrywki | zakład | kurs | fair p | marża "
        "| fair p × kurs | wiek ceny |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for leg in doc["legs"]:
        out.append(
            f"| {local(leg['kickoff_utc'])}"
            f"{' (w toku)' if leg.get('locked') else ''} | "
            f"{leg['match_name']} | "
            f"{leg.get('tournament') or '-'} | {leg['label']} | {leg['odds']:.2f} | "
            f"{leg['fair_p']:.3f} | {leg['overround']:.1%} | "
            f"{leg['fair_p_x_odds']:.3f} | "
            + ("wydruk " + local(leg["price_fetched_at_utc"]) if leg.get("locked")
               else f"{leg['price_age_min']} min")
            + " |"
        )
    if not doc["legs"]:
        out.append("| - | brak pozycji spełniających regułę | | | | | | | |")
    if doc["vetoed"]:
        out += ["", "## Weta", ""]
        for leg in doc["vetoed"]:
            out.append(
                f"- {leg['match_name']} - {sc.describe(sport, leg)}: {leg['veto']}"
            )
    if doc["vetoes_unmatched"]:
        out += ["", "## Weta bez dopasowania (sprawdź id i klucze)", ""]
        out += [
            f"- {json.dumps(v, ensure_ascii=False)}" for v in doc["vetoes_unmatched"]
        ]
    return "\n".join(out) + "\n"


def veto_count_pl(n: int) -> str:
    """'1 weto nie pasuje', '2 weta nie pasują', '5 wet nie pasuje'."""
    if n == 1:
        return "1 weto nie pasuje"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} weta nie pasują"
    return f"{n} wet nie pasuje"


def render_pdf(doc: dict[str, Any], path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    from scripts.sofa.build_coupon_pdf import BASE, BOLD, INK, MUTED, WARN

    ss = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "H1", parent=ss["Title"], fontName=BOLD, fontSize=17, textColor=INK
    )
    sub = ParagraphStyle(
        "SUB",
        parent=ss["Normal"],
        fontName=BASE,
        fontSize=8.6,
        textColor=MUTED,
        leading=12.5,
    )
    body = ParagraphStyle(
        "BODY",
        parent=ss["Normal"],
        fontName=BASE,
        fontSize=8.2,
        textColor=INK,
        leading=11,
    )
    head = ParagraphStyle("HEAD", parent=body, fontName=BOLD)
    sport = doc["sport"]
    h = doc["rule_history"]
    warn = WARN.hexval().replace("0x", "#")
    story: list[Any] = [
        Paragraph(f"Kupon eksperymentalny — {sc.SPORT_PL[sport]} — {doc['date']}", h1),
        Paragraph(
            f"Zbudowany {doc['created_at_utc']} &nbsp;•&nbsp; {len(doc['legs'])} "
            f"pojedynczych &nbsp;•&nbsp; fair p ≥ {doc['rule']['floor']:.2f} "
            f"&nbsp;•&nbsp; marża linii ≤ {doc['rule']['max_overround']:.1%} "
            f"&nbsp;•&nbsp; kurs ≥ {doc['rule']['min_odds']:.3f}",
            sub,
        ),
        Spacer(1, 3 * mm),
        Paragraph(
            f"<font color='{warn}'><b>To nie jest kupon.</b></font> "
            "Eksperyment operatora od 30.09: sport mierzony (CS2 / SHADOW), "
            "rozliczany osobno, <b>nigdy nie łączony z kuponem</b>. Ten sport "
            "nie ma modelu — pewność to cena Superbet z usuniętą marżą, więc "
            "przy uczciwej cenie każda pozycja traci średnio tyle, ile marża "
            "(kolumna „fair p × kurs” poniżej 1,00 = strata oczekiwana). "
            "Wybór: na mecz jedna strona o najwyższym fair p × kurs (najmniejsza "
            "zapłacona marża). Tylko pojedyncze; "
            "stawka jest decyzją operatora.",
            body,
        ),
        Paragraph(
            f"<font color='{warn}'><b>UNFITTED_CONSTANTS: "
            f"{', '.join(doc['UNFITTED_CONSTANTS'])}</b></font> — wybrane, nie "
            "dopasowane do rozliczeń.",
            body,
        ),
        Paragraph(
            "Historia tej reguły na rozliczonych dniach pomiaru "
            f"({', '.join(str(d) for d in h['days']) or 'brak'}; cena ostatnia "
            "przed startem, nie wydrukowana): "
            + (
                f"<b>{h['n']}</b> zakładów, trafione {h['wins']} ({h['hit']:.1%}) "
                f"wobec średniego fair p {h['mean_fair_p']:.1%}, ROI "
                f"<b>{h['roi']:+.1%}</b> (void {h.get('void', 0)}, nierozliczalne "
                f"{h.get('ungradeable', 0)}). Za mało dni, by to był wynik."
                if h.get("n")
                else "brak rozliczonych dni."
            ),
            body,
        ),
        *(
            Paragraph(
                f"&nbsp;&nbsp;• {sc.FAMILY_PL[sport].get(fam, fam)}: {f['n']} zakł., "
                f"trafione {f['hit']:.1%} wobec "
                f"fair p {f['mean_fair_p']:.1%}, ROI {f['roi']:+.1%}",
                sub,
            )
            for fam, f in (h.get("by_family") or {}).items()
            if f.get("n")
        ),
        Spacer(1, 3 * mm),
    ]
    rows: list[list[Any]] = [
        [
            Paragraph(t, head)
            for t in (
                "start",
                "mecz / rozgrywki",
                "zakład",
                "kurs",
                "fair p",
                "marża",
                "p×kurs",
            )
        ]
    ]
    for leg in doc["legs"]:
        rows.append(
            [
                Paragraph(
                    local(leg["kickoff_utc"])
                    + ("<br/>(w toku)" if leg.get("locked") else ""),
                    body,
                ),
                Paragraph(
                    f"<b>{leg['match_name']}</b><br/>{leg.get('tournament') or ''}",
                    body,
                ),
                Paragraph(leg["label"], body),
                Paragraph(f"<b>{leg['odds']:.2f}</b>", body),
                Paragraph(f"{leg['fair_p']:.3f}", body),
                Paragraph(f"{leg['overround']:.1%}", body),
                Paragraph(f"{leg['fair_p_x_odds']:.3f}", body),
            ]
        )
    if not doc["legs"]:
        rows.append(
            [
                Paragraph("—", body),
                Paragraph("Brak pozycji spełniających regułę.", body),
                "",
                "",
                "",
                "",
                "",
            ]
        )
    table = Table(
        rows,
        colWidths=[20 * mm, 48 * mm, 56 * mm, 12 * mm, 13 * mm, 15 * mm, 17 * mm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, INK),
                ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#d0d0d0")),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 3 * mm))
    story.append(
        Paragraph(
            "Cena z ostatniego snapshotu Superbet przed zbudowaniem (wiek: "
            + ", ".join(
                sorted(
                    {
                        f"{leg['price_age_min']} min"
                        for leg in doc["legs"]
                        if not leg.get("locked")
                    }
                )
                or ["—"]
            )
            + "; pozycje „w toku” zostają po kursie z wcześniejszego wydruku"
            + "). Sprawdź kurs w aplikacji przed zakładem — jeśli spadł, pozycja "
            "jest droższa niż na tej stronie.",
            sub,
        )
    )
    if doc["vetoed"]:
        story.append(Paragraph("<b>Weta</b>", body))
        for leg in doc["vetoed"]:
            story.append(
                Paragraph(
                    f"{leg['match_name']} — {sc.describe(sport, leg)}: {leg['veto']}",
                    sub,
                )
            )
    if doc["vetoes_unmatched"]:
        story.append(
            Paragraph(
                f"<font color='{warn}'><b>"
                f"{veto_count_pl(len(doc['vetoes_unmatched']))} do żadnej pozycji"
                "</b></font> — sprawdź id w vetoes.json.",
                body,
            )
        )
    pdf = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=14 * mm,
        bottomMargin=13 * mm,
        title=f"Kupon eksperymentalny {sc.SPORT_PL[sport]} {doc['date']}",
        author="sofa pipeline",
    )
    pdf.build(story)


def write_outputs(
    sport: sc.SportKey, date: str, runs_dir: str, doc: dict[str, Any]
) -> Path:
    """PDF, JSON, md and the build log, in the order that never leaves a PDF
    and a JSON that disagree: the PDF is rendered to a temporary file first,
    so a failed render leaves the previous pair untouched."""
    directory = sc.day_dir(runs_dir, sport, date)
    directory.mkdir(parents=True, exist_ok=True)
    pdf_path = directory / sc.pdf_name(sport, date)
    tmp_pdf = tmp_path(pdf_path)
    render_pdf(doc, tmp_pdf)
    # The JSON names the exact PDF it was printed as: a reader checks the
    # hash, not file times, which a copy or a restore does not keep.
    doc["pdf_sha256"] = sc.file_sha256(tmp_pdf)
    write_atomic(
        directory / sc.COUPON_FILE, json.dumps(doc, ensure_ascii=False, indent=2)
    )
    os.replace(tmp_pdf, pdf_path)
    write_atomic(directory / sc.COUPON_MD, render_md(doc))
    # Every build, appended: what each printed PDF held. Through the shared
    # appender: whole lines under a lock, a torn tail newline-repaired first.
    append_records(
        directory / sc.BUILDS_FILE,
        [{"created_at_utc": doc["created_at_utc"], "legs": doc["legs"],
          "vetoed": doc["vetoed"]}],
    )
    return pdf_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--date", required=True)
    parser.add_argument("--sport", choices=[*sc.SPORT_KEYS, "all"], default="all")
    parser.add_argument("--max-legs", type=int, default=sc.MAX_LEGS)
    args = parser.parse_args()
    config = SofaConfig.from_env()
    _frozen = frozen_clock_refusal(config.runs_dir)
    if _frozen:
        print(_frozen, file=sys.stderr)
        return 2
    at = now()
    rule = sc.Rule(max_legs=args.max_legs)
    sports = sc.SPORT_KEYS if args.sport == "all" else (args.sport,)
    # A day whose window has closed is a record, not a board: rebuilding it
    # would print an empty coupon over the one that was printed.
    if at >= sc.day_end(args.date):
        print(
            "SOFA_SUMMARY: "
            + json.dumps(
                {
                    "stage": "SPORT_COUPON",
                    "verdict": "FAILED",
                    "error": f"the window of {args.date} closed at "
                    f"{sc.day_end(args.date).isoformat()}; its coupon is final",
                }
            )
        )
        return 2
    worst = 0
    metrics: dict[str, Any] = {}
    for sport in sports:
        directory = sc.day_dir(config.runs_dir, sport, args.date)
        pdf_path = directory / sc.pdf_name(sport, args.date)
        try:
            # build and write under one lock: a second runner for the same
            # sport waits, then builds on top of this build (its locked legs)
            with sc.dir_lock(directory):
                # the clock is read inside the lock: a runner that waited for
                # another builds at its own time, after the build it follows
                at = now()
                doc = build(sport, args.date, config.runs_dir, at, rule)
                write_outputs(sport, args.date, config.runs_dir, doc)
        except Exception as exc:  # one sport failing never stops the others
            metrics[sport] = {
                "verdict": "FAILED",
                "error": f"{type(exc).__name__}: {exc}",
            }
            worst = 2
            continue
        partial = not doc["snapshots"] or not doc["legs"] or doc["vetoes_unmatched"]
        worst = max(worst, 1 if partial else 0)
        metrics[sport] = {
            "verdict": "PARTIAL" if partial else "OK",
            "legs": len(doc["legs"]),
            "locked": doc["locked"],
            "candidates": doc["candidates"],
            "vetoed": len(doc["vetoed"]),
            "vetoes_unmatched": len(doc["vetoes_unmatched"]),
            "rule_history_n": doc["rule_history"].get("n", 0),
            "output_path": str(pdf_path),
        }
    verdict = {0: "OK", 1: "PARTIAL", 2: "FAILED"}[worst]
    print(
        "SOFA_SUMMARY: "
        + json.dumps(
            {"stage": "SPORT_COUPON", "verdict": verdict, "metrics": metrics},
            ensure_ascii=False,
        )
    )
    return worst


if __name__ == "__main__":
    sys.exit(main())
