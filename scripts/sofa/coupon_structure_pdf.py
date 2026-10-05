"""The coupon's structure on the PDF (plan 2026-10-05 production grade,
F4.2-F4.4): the "ta sama zmienna" groups, the exposure per match and the
builders' screen price. Kept apart from build_coupon_pdf.py's renderer so
the two can change independently; every function reads 11_coupon.json's
fields (build_coupon.coupon_structure) and computes them only for an older
artifact that has none.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle  # noqa: E402

from bet.sofa import builder_screen as bs  # noqa: E402
from bet.sofa import coupon_sports as cs  # noqa: E402
from bet.sofa import leg_relations as lr  # noqa: E402

HEADER_BAND = colors.HexColor("#eef3fa")
RULE = colors.HexColor("#d8d8d8")
BAND = colors.HexColor("#f4f4f4")
MUTED = colors.HexColor("#6b6b6b")

# The PDF names a ladder rung "ta sama zmienna Z<n>"; the header says what
# the group is and lists its rungs.
LADDER_PHRASE = "ta sama zmienna"


def ladders_of(
    doc: Mapping[str, Any], singles: Sequence[dict[str, Any]]
) -> tuple[dict[int, int], dict[int, dict[str, Any]]]:
    """(id(leg) -> ladder number, ladder number -> ladder) for the printed
    singles: the artifact's own `ladder_no` / `ladders` when it has them,
    else computed (an 11 assembled before F4)."""
    if doc.get("ladders") is not None:
        docs = {int(x["ladder_no"]): dict(x) for x in doc["ladders"]}
        of = {id(s): int(s["ladder_no"]) for s in singles
              if s.get("ladder_no") is not None}
        return of, docs
    index = lr.ladder_index(singles)
    computed = lr.ladders(singles)
    docs = {i: {**x, "ladder_no": i} for i, x in enumerate(computed, 1)}
    return index, docs


def _rungs_word(n: int) -> str:
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "szczeble"
    return "szczebli"


def _rung_text(r: Mapping[str, Any], short: bool = False) -> str:
    line = "" if r.get("line") is None else f"{cs.display_line(r)} "
    where = "w grze" if r.get("position") is None else f"#{r['position']}"
    if short:
        return f"{line}{r.get('direction')} ({where})"
    subj = f" {r['subject']}" if r.get("subject") and str(
        r.get("subject")) not in ("T1", "T2") else ""
    return (f"{escape(str(r.get('market')))}{escape(subj)} {line}"
            f"{r.get('direction')} ({where})")


def ladder_header(lad: Mapping[str, Any]) -> str:
    """The group header of one ladder: what the variable is and its rungs."""
    n = int(lad["n_rungs"])
    rungs = list(lad.get("rungs") or [])
    # One market and subject for every rung: the label already names it.
    short = len({(r.get("market"), r.get("subject")) for r in rungs}) == 1
    text = (
        f"<b>{LADDER_PHRASE} Z{lad['ladder_no']}</b> — "
        f"{escape(str(lad.get('match') or ''))}: {escape(str(lad.get('label')))}"
        f" — {n} {_rungs_word(n)}: "
        + "; ".join(_rung_text(r, short) for r in rungs)
        + f". Jedna decyzja o jednej wielkości, nie {n} "
        + ("niezależne zakłady" if _rungs_word(n) == "szczeble"
           else "niezależnych zakładów")
    )
    if lad.get("over_under_pair"):
        text += " • OVER i UNDER tej samej wielkości"
    if lad.get("exclusive_pairs"):
        text += (f" • {lad['exclusive_pairs']} par(y) wykluczających się "
                 "(obie nie mogą wejść)")
    return text + "."


def ladder_marker(ladder_no: int | None) -> str:
    """What a rung's market cell says (nothing off a ladder)."""
    return "" if ladder_no is None else f" — {LADDER_PHRASE} Z{ladder_no}"


def table_with_headers(table: Table, header_rows: Sequence[int]) -> Table:
    """The table with each ladder header row spanning every column."""
    if header_rows:
        cmds: list[Any] = []
        for r in header_rows:
            cmds += [("SPAN", (0, r), (-1, r)),
                     ("BACKGROUND", (0, r), (-1, r), HEADER_BAND)]
        table.setStyle(TableStyle(cmds))
    return table


def _table(rows: list[list[Any]], widths: list[float]) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ("BACKGROUND", (0, 0), (-1, 0), BAND),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def exposure_flowables(
    doc: Mapping[str, Any], body: ParagraphStyle, small: ParagraphStyle,
    h2: ParagraphStyle,
) -> list[Any]:
    """F4.3 on the page: how much of the coupon stands on one match."""
    exp = doc.get("exposure")
    if not exp or not exp.get("positions"):
        return []
    rows_doc = list(exp.get("per_match") or [])
    out: list[Any] = [Spacer(1, 6), Paragraph("Ekspozycja na mecz", h2)]
    biggest = rows_doc[0] if rows_doc else None
    cap = exp.get("max_positions_per_match")
    text = (
        f"Pozycje 1-{exp['top_positions']} stoją na <b>{exp['top_positions_matches']}"
        f"</b> meczach; cały kupon: {exp['positions']} pozycji na "
        f"{exp['matches']} meczach."
    )
    if biggest is not None:
        text += (
            f" Najwięcej na jednym meczu: {escape(str(biggest['match']))} — "
            f"{biggest['n_positions']} pozycji ({biggest['share_of_positions']:.0%}"
            f" kuponu, suma pewności {biggest['confidence_sum']:.2f}).")
    text += (" Nogi jednego meczu wygrywają i przegrywają razem: kolumna "
             "„cały mecz przegrywa” to tyle pozycji (z nogami w grze i "
             "builderami), ile zabiera jeden zły mecz. Limit na mecz: "
             + ("brak (decyzja operatora)." if cap is None else f"{cap}."))
    out.append(Paragraph(text, body))
    shown = [r for r in rows_doc if r["n_positions"] + r["locked"] >= 2
             or r["builders"]]
    if not shown:
        return out
    rows: list[list[Any]] = [[Paragraph(h, small) for h in (
        "mecz", "pozycje", "udział", "suma pewności", "numery", "w grze",
        "BB", "cały mecz przegrywa")]]
    for r in shown:
        nums = r["positions"]
        listed = ", ".join(str(x) for x in nums[:10]) + (" …" if len(nums) > 10 else "")
        rows.append([
            Paragraph(escape(str(r["match"])) + (
                " <font color='#b25b00'>(ponad limit)</font>" if r.get("over_limit")
                else ""), small),
            Paragraph(str(r["n_positions"]), small),
            Paragraph(f"{r['share_of_positions']:.0%}", small),
            Paragraph(f"{r['confidence_sum']:.2f}", small),
            Paragraph(listed, small),
            Paragraph(str(r["locked"]), small),
            Paragraph(", ".join(r["builders"]) or "—", small),
            Paragraph(f"<b>{r['worst_case_lost']}</b>", small),
        ])
    out.append(_table(rows, [50*mm, 14*mm, 13*mm, 17*mm, 38*mm, 12*mm, 12*mm,
                             20*mm]))
    return out


_REFUSAL_PL = {
    bs.NO_SCREEN_PRICE: "brak kursu z ekranu",
    bs.UNTIMED: "kurs bez czasu odczytu",
    bs.AFTER_START: "kurs odczytany po starcie",
    bs.OTHER_SLIP: "kurs innego slipa (inne nogi)",
    bs.X_BELOW: "x = p × kurs z ekranu < 0,90",
}


def builder_price_lines(b: Mapping[str, Any], body: ParagraphStyle) -> list[Any]:
    """Under a printed builder: its screen price, or that it has none."""
    if b.get("screen_odds") is not None:
        x = float(b["combined_probability"]) * float(b["screen_odds"])
        when = str(b.get("screen_odds_fetched_at_utc") or "")[11:16]
        return [Paragraph(
            f"<b>kurs z ekranu Superbetu {b['screen_odds']}</b> "
            f"({escape(str(b.get('screen_odds_source') or '—'))}"
            + (f", odczyt {when}Z" if when else "") + ") • x = p × kurs z ekranu "
            f"<b>{x:.2f}</b>", body)]
    problem = b.get("screen_price_problem")
    if problem:
        return [Paragraph(
            "<font color='#b25b00'>kurs z ekranu odrzucony: "
            f"{escape(_REFUSAL_PL.get(str(problem), str(problem)))}</font> — kurs "
            "po narzucie to szacunek", body)]
    return [Paragraph("<font color='#b25b00'>brak kursu z ekranu</font> — kurs po "
                      "narzucie to szacunek, nie cena Superbetu", body)]


def refused_builder_flowables(
    doc: Mapping[str, Any], small: ParagraphStyle, h2: ParagraphStyle
) -> list[Any]:
    """F4.4: builders not printed for their screen price, listed with their
    legs so the operator can build the slip on the screen and record it."""
    refused = list(doc.get("builders_refused") or [])
    if not refused:
        return []
    out: list[Any] = [Spacer(1, 6), Paragraph(
        "Bet Buildery bez kursu z ekranu — nie na kuponie", h2), Paragraph(
        "Od 2026-10-06 builder drukuje się tylko z kursem odczytanym z ekranu "
        "Superbetu (runs/sofa/&lt;d&gt;/09_screen_prices.json: kurs, czas "
        "odczytu, źródło, opcjonalnie nogi). Zbuduj slip na ekranie, wpisz kurs "
        "i przebuduj kupon. Kurs po narzucie poniżej to szacunek.", small)]
    rows: list[list[Any]] = [[Paragraph(h, small) for h in (
        "mecz", "nogi", "łączne p", "kurs po narzucie (szac.)", "powód")]]
    for b in refused:
        legs = "<br/>".join(
            f"{escape(str(x.get('market')))}"
            + (f" {escape(str(x['subject']))}" if x.get("subject") else "")
            + f" {x.get('line')} {x.get('direction')}" for x in b.get("legs") or [])
        rows.append([
            Paragraph(f"{escape(str(b.get('match') or ''))}<br/><font size=6.5>"
                      f"{str(b.get('kickoff_utc') or '')[11:16]}Z</font>", small),
            Paragraph(legs, small),
            Paragraph(f"{float(b.get('combined_probability') or 0):.3f}", small),
            Paragraph(str(b.get("odds_after_haircut") or "—"), small),
            Paragraph(escape(_REFUSAL_PL.get(str(b["refusal"]), str(b["refusal"]))),
                      small),
        ])
    out.append(_table(rows, [48*mm, 66*mm, 16*mm, 22*mm, 26*mm]))
    return out
