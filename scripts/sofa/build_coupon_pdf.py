#!/usr/bin/env python3
"""Render the confidence coupon to PDF, every position with its own evidence.

One page-block per Bet Builder: the legs, what each leg's own sample says, the
calibration bucket behind its confidence, what Superbet's shading costs, and
any caveat the verification raised. Nothing is summarised away — a position the
operator cannot audit from the page is a position he should not stake.
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pydantic import RootModel  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from bet.sofa.confidence import (  # noqa: E402
    MAX_OVERROUND,
    PROFILES,
    confidence_artifact,
    displayed_ev,
    is_stakeable,
    printed_singles,
    quantity_family,
)
from bet.sofa.contracts import Fixture  # noqa: E402
from scripts.sofa.run_sheet import determine_side  # noqa: E402

# Helvetica's built-in encoding has no Latin-2, so every Polish diacritic in
# the first draft rendered as a black box — "zak<box>ad", "pewno<box><box>".
# A coupon the operator cannot read is not a coupon. Register a Unicode TTF
# and fall back to Helvetica only if none is installed.
BASE, BOLD = "Helvetica", "Helvetica-Bold"
for _regular, _bold in (
    ("/System/Library/Fonts/Supplemental/Arial.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
):
    if Path(_regular).exists() and Path(_bold).exists():
        pdfmetrics.registerFont(TTFont("CouponSans", _regular))
        pdfmetrics.registerFont(TTFont("CouponSans-Bold", _bold))
        pdfmetrics.registerFontFamily(
            "CouponSans", normal="CouponSans", bold="CouponSans-Bold",
            italic="CouponSans", boldItalic="CouponSans-Bold",
        )
        BASE, BOLD = "CouponSans", "CouponSans-Bold"
        break

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#6b6b6b")
GOOD = colors.HexColor("#1b7f4b")
WARN = colors.HexColor("#b25b00")
RULE = colors.HexColor("#d8d8d8")
BAND = colors.HexColor("#f4f4f4")


def _referee(fixture: dict) -> str:
    """The fixture carries the referee as an object, not a name.

    Interpolating it printed the whole dict — games, yellow_cards and all —
    into the header of every pick. Where the record is there it is worth
    showing, because a referee's card rate is the one context a cards leg
    turns on.
    """
    ref = fixture.get("referee")
    if not ref:
        return ""
    if isinstance(ref, str):
        return f" • sędzia {ref}"
    name = ref.get("name")
    if not name:
        return ""
    games, yellows = ref.get("games"), ref.get("yellow_cards")
    if games and yellows:
        return f" • sędzia {name} ({yellows / games:.1f} żółtych/mecz, {games} meczów)"
    return f" • sędzia {name}"


def wilson_lo(k: int, n: int, z: float = 1.2816) -> float:
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - m)


def unfitted_constants(
    sheet_rows: list[dict], keys: set[tuple]
) -> list[str]:
    """Every constant a printed row names in its UNFITTED_CONSTANTS note.

    The sheet stamped it on all 16,052 rows on 2026-09-23 and the PDF - the
    one document the operator stakes from - said it zero times. CLAUDE.md
    forbids stripping it to make a report read better; leaving it out of the
    page did exactly that.
    """
    found: set[str] = set()
    for r in sheet_rows:
        k = (r["sofascore_event_id"], r["market"], r["subject"], r["line"], r["direction"])
        if k not in keys:
            continue
        for note in r.get("notes") or []:
            if note.startswith("UNFITTED_CONSTANTS:"):
                found.update(
                    c.strip() for c in note.split(":", 1)[1].split(",") if c.strip()
                )
    return sorted(found)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True)
    # The same directory every other stage reads (SofaConfig.runs_dir). A
    # hard-coded default let a scratch rebuild under SOFA_RUNS_DIR overwrite
    # the real day's 08_confidence.json and PDF on 2026-09-23.
    ap.add_argument(
        "--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa")
    )
    ap.add_argument("--out", default=None)
    ap.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="standard",
        help="wariant renders 08_confidence_wariant.json to KUPON_<date>_WARIANT.pdf",
    )
    args = ap.parse_args()
    profile = PROFILES[args.profile]

    run = Path(args.runs_dir) / args.date
    doc_json = json.loads(
        (run / confidence_artifact(profile)).read_text(encoding="utf-8")
    )
    # The artifact names the profile it was built with. A variant JSON renamed
    # into the official slot (or the reverse) must not print under the wrong
    # banner, because the banner is what tells the operator which one he holds.
    built_with = doc_json.get("profile", "standard")
    if built_with != profile.name:
        print(
            f"{confidence_artifact(profile)} was built with profile {built_with!r}, "
            f"not {profile.name!r}",
            file=sys.stderr,
        )
        return 2
    samples = {
        s["sofascore_event_id"]: s
        for s in json.loads((run / "03_samples.json").read_text(encoding="utf-8"))
    }
    raw = (run / "02_fixtures.json").read_bytes()
    fx_obj = {f.sofascore_event_id: f for f in RootModel[list[Fixture]].model_validate_json(raw).root}
    fx_raw = {f["sofascore_event_id"]: f for f in json.loads(raw)}
    cal = json.loads(Path("config/sofa_confidence_calibration.json").read_text())
    now = datetime.datetime.now(datetime.timezone.utc)

    legs_idx = {
        (l["sofascore_event_id"], l["market"], l["subject"], l["line"], l["direction"]): l
        for l in doc_json["legs"]
    }

    def own_sample(eid, market, subject, line, direction):
        mv = (samples.get(eid, {}).get("metrics") or {}).get(market)
        if not mv:
            return None
        if not subject:
            obs, seen = [], set()
            for side in ("side_a", "side_b", "h2h"):
                for o in mv.get(side) or []:
                    if o["sofascore_event_id"] in seen:
                        continue
                    seen.add(o["sofascore_event_id"])
                    obs.append(o)
        else:
            fo = fx_obj.get(eid)
            side = determine_side(subject, fo) if fo else None
            obs = list(mv.get(side) or []) if side else []
        vals = [o["value"] for o in obs if o.get("value") is not None]
        if not vals:
            return None
        hits = sum(1 for v in vals if (v > line if direction == "OVER" else v < line))
        newest = max(o["match_date_utc"] for o in obs)
        age = (now - datetime.datetime.fromisoformat(newest.replace("Z", "+00:00"))).days
        return hits, len(vals), wilson_lo(hits, len(vals)), age, sorted(vals)

    # Selected on the price the operator can actually get, not on the product
    # of the leg prices. Superbet's correlation markup was measured at 9-20%
    # on 2026-09-20, and at the smallest of those only 2 of that week's 37
    # slips stayed positive — so `ev_if_product_priced` was admitting slips
    # that were already negative when the screen quoted them.
    # Named `ev_key`, not `key`: the per-leg loop below binds a tuple called
    # `key`, and a loop variable outlives its loop. The summary row then read
    # `b.get(<tuple>, b.get("ev_if_product_priced"))` and always fell through
    # to the product EV — so every pick on the staked PDF printed an EV that
    # ignored the 12% correlation haircut, on a page whose own text says "EV
    # liczone jest od tej ceny". Selection was right; only the printed number
    # was wrong, which is the harder kind to notice.
    ev_key = (
        "ev_after_haircut"
        if "ev_after_haircut" in (doc_json["builders"][0] if doc_json["builders"] else {})
        else "ev_if_product_priced"
    )
    picks = [b for b in doc_json["builders"] if is_stakeable(b)]
    # The variant is a singles experiment. Its looser legs would admit
    # builders the official coupon does not print, and a builder is a
    # different bet (correlation haircut, joint probability) that the
    # variant was never measured on - so its PDF prints none.
    if profile.min_ev is not None:
        picks = []
    # Singles. Present since 2026-09-22: on a day where no Bet Builder forms —
    # which needs two legs of DIFFERENT quantity families in the SAME match —
    # this renderer used to emit a blank page while the confidence artifact
    # held dozens of qualifying legs. 2026-09-22 had 37 legs and 0 builders.
    singles = doc_json.get("singles", [])
    picks.sort(key=lambda b: -b[ev_key])

    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("H1", parent=ss["Title"], fontName=BOLD, fontSize=19,
                        textColor=INK, spaceAfter=2, alignment=TA_LEFT)
    SUB = ParagraphStyle("SUB", parent=ss["Normal"], fontName=BASE, fontSize=8.6, textColor=MUTED, leading=12.5)
    H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontName=BOLD, fontSize=11.5,
                        textColor=INK, spaceBefore=9, spaceAfter=4)
    BODY = ParagraphStyle("BODY", parent=ss["Normal"], fontName=BASE, fontSize=8.6, textColor=INK, leading=12.4)
    SMALL = ParagraphStyle("SMALL", parent=ss["Normal"], fontName=BASE, fontSize=7.5, textColor=MUTED, leading=10.2)
    PICK = ParagraphStyle("PICK", parent=ss["Normal"], fontName=BOLD, fontSize=10.5,
                          textColor=INK, spaceAfter=1)

    out_path = Path(args.out or (run / f"KUPON_{args.date}{profile.pdf_suffix}.pdf"))
    pdf = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=15 * mm, rightMargin=13 * mm, topMargin=14 * mm, bottomMargin=13 * mm,
        title=f"Kupon {args.date}", author="sofa pipeline",
    )
    S: list = []
    title = f"Kupon — {args.date}"
    if profile.min_ev is not None:
        title += " — WARIANT"
    S.append(Paragraph(title, H1))
    S.append(Paragraph(
        f"Zbudowany {doc_json['created_at_utc']} &nbsp;•&nbsp; "
        f"{len(picks)} zakładów łączonych, {len(singles)} pojedynczych "
        f"&nbsp;•&nbsp; "
        f"próg pewności {doc_json['confidence_floor']}"
        + ("" if profile.min_ev is None
           else f" &nbsp;•&nbsp; pewność × kurs ≥ {profile.min_ev:.2f}"
                f" &nbsp;•&nbsp; marża rynku ≤ {profile.max_overround:.0%}"), SUB))
    if profile.min_ev is not None:
        S.append(Paragraph(
            "<font color='#b25b00'><b>To nie jest oficjalny kupon.</b></font> Wariant "
            f"przyjmuje pewność od {doc_json['confidence_floor']} i kurs do "
            f"{1 - profile.min_ev:.0%} poniżej uczciwego (wg tej pewności), przy "
            f"marży rynku do {profile.max_overround:.0%} (oficjalny: 10,5%). "
            "Wersja z marżą 10,5% dała na 18–22.09 <b>−3,2%</b> na zakład wobec "
            "−2,9% oficjalnego; rynki z marżą 10,5–15% traciły tam o 1–2 pkt "
            "proc. więcej niż tańsze. Od 23.09 mierzony w tym ustawieniu, "
            "obok oficjalnego (sekcja 7d raportu rozliczenia).", SUB))
    sheet_doc = json.loads((run / "05_sheet.json").read_text(encoding="utf-8"))
    sheet_rows = sheet_doc if isinstance(sheet_doc, list) else sheet_doc["rows"]
    # A builder's legs carry no event id of their own; it is on the builder.
    printed = {
        (item["sofascore_event_id"], l["market"], l["subject"], l["line"], l["direction"])
        for item in [*picks, *singles]
        for l in (item.get("legs") or [item])
    }
    unfitted = unfitted_constants(sheet_rows, printed)
    if unfitted:
        S.append(Paragraph(
            f"<font color='#b25b00'><b>UNFITTED_CONSTANTS: {', '.join(unfitted)}</b></font> "
            "— te stałe nie są dopasowane do rozliczeń. Liczby w tym kuponie na nich "
            "stoją; traktuj je jako niezmierzone.", SUB))
    S.append(Spacer(1, 7))

    S.append(Paragraph("Jak czytać ten kupon", H2))
    S.append(Paragraph(
        "<b>pewność</b> to <i>dolna granica zmierzonej realizacji</i> — ile razy na 1 868 474 "
        "rozliczonych wierszy zdarzenie faktycznie zaszło przy tej ocenie modelu. To nie jest "
        "deklaracja modelu. Model jest skalibrowany z dokładnością do 0,3 pkt proc. do poziomu 0,90, "
        "i ma tam <b>sufit ~0,92</b>: kubełki 0,900–0,925 i 0,925–0,950 realizują identyczne 0,9083. "
        "<b>Nogi 98% nie istnieją.</b>", BODY))
    S.append(Paragraph(
        "<b>kurs uczciwy</b> to cena, jakiej kombinacja wymaga, żeby być warta ryzyka. To <b>nie</b> "
        "prognoza ceny Bet Buildera w Superbecie — bukmacher stosuje własną korektę korelacji. "
        "Porównaj z ekranem.", BODY))
    S.append(Paragraph(
        "<b>Po narzucie</b> to iloczyn kursów nóg pomniejszony o <b>12%</b> — tyle Superbet bierze "
        "za korelację. Zmierzone 2026-09-20 na trzech slipach z ekranu: 8,8% (2 nogi), 15,8% "
        "(2 nogi zagnieżdżone), 19,6% (4 nogi). <b>EV liczone jest od tej ceny</b>, nie od iloczynu. "
        "Wcześniej kupon wybierał po iloczynie, czyli po cenie, której bukmacher nigdy nie podał: "
        "z 37 slipów z 2026-09-19 nawet najmniejszy zmierzony narzut zostawiał dodatnie <b>dwa</b>. "
        "Jeśli ekran pokazuje więcej niż „po narzucie”, slip jest lepszy niż tu napisano; jeśli "
        "mniej — gorszy, i wtedy go nie bierz.", BODY))
    S.append(Paragraph(
        "<b>Zaniżenie kursu</b> wynosi płasko ok. 5,4 pkt proc. niezależnie od pewności i "
        "<b>kumuluje się</b> przy dokładaniu nóg: mediana EV to −0,058 przy jednej nodze, −0,082 "
        "przy trzech, −0,118 przy czterech. Dokładanie „pewniaków” nie poprawia kuponu. "
        "Wybrane niżej zakłady to te, w których konkretna noga jest źle wyceniona i EV wychodzi "
        "na plus mimo zaniżenia.", BODY))
    S.append(Paragraph(
        "Nogi w jednym zakładzie pochodzą z <b>różnych wielkości</b> (gole / rożne / faule / kartki). "
        "Gole drużyny i gole meczu to ta sama wielkość liczona dwa razy (λ=2,165), więc nigdy nie "
        "trafiają do jednego kuponu. Rynki złożone (both_over_*, handicap_*) są odrzucone — mają "
        "18–252 rozliczonych wierszy, za mało by cokolwiek twierdzić.", BODY))
    S.append(Spacer(1, 4))
    S.append(Paragraph(
        "Model <b>nie</b> bije ceny (Brier 0,2067 vs 0,1845 dla rynku). Ten kupon nie twierdzi, że "
        "znajduje value — twierdzi, że wie, jak często dane zdarzenie zachodzi. Rentowność nie jest "
        "wykazana; potrzeba kilku dni rozliczeń.", SMALL))
    S.append(PageBreak())

    S.append(Paragraph("Zakłady pojedyncze", H2))
    S.append(Paragraph(
        "Uszeregowane po <b>pewności</b>, nie po EV. To celowe: <b>EV nogi jest "
        "zmierzone jako odwrócone</b>. `confidence` jest funkcją schodkową, więc "
        "wewnątrz jednego kubełka kalibracji EV rośnie wyłącznie z kursem — a "
        "dłużej wyceniona jedna trzecia kubełka trafia <b>rzadziej</b> niż "
        "krótsza, za każdym razem, i różnica rośnie z pewnością (2 pkt proc. "
        "przy 0,811, 10 pkt proc. przy 0,906).", BODY))
    if profile.min_ev is None:
        x_rule = (
            "<b>x</b> to <b>pewność × kurs</b> — jedyny test, który decyduje. "
            "Powyżej <b>1,00</b> cena płaci za ryzyko, poniżej nie. Zdarzenie na "
            "70% wymaga kursu <b>1,43</b>, na 80% wymaga <b>1,25</b>: samo wysokie "
            "prawdopodobieństwo nie wystarcza. Marża bukmachera jest rozłożona na "
            "<b>obie</b> strony rynku, więc nie każda noga jest ujemna — wiersze "
            "przy p 0,85–0,95 wycenione 1,20–1,35 zwróciły <b>+1,94%</b> (n=94)."
        )
    else:
        x_rule = (
            "<b>x</b> to <b>pewność × kurs</b>. Powyżej <b>1,00</b> cena płaci za "
            "ryzyko; w tym wariancie przyjmowane są też pozycje od "
            f"<b>{profile.min_ev:.2f}</b> do 1,00 — czyli kurs do "
            f"{1 - profile.min_ev:.0%} <b>poniżej</b> uczciwego. Każda pozycja z "
            "x &lt; 1,00 jest świadomie przepłacona: to koszt większej liczby "
            "zakładów, nie przewaga."
        )
    S.append(Paragraph(x_rule, BODY))
    S.append(Paragraph(
        f"<b>marża</b> to narzut Superbeta na tej drabinie, policzony z ceny "
        f"dwustronnej. Powyżej <b>{MAX_OVERROUND:.1%}</b> noga nie trafia na tę "
        "listę — to jedyny próg, na którym wyniki się rozdzielają (poniżej "
        "zwrot jest płaski ok. −3,5%, powyżej spada do −5,7%). Rogi wyceniane "
        "są medianowo na 8,6%, gole na 10,2%.", BODY))
    S.append(Paragraph(
        "<b>To nie jest obietnica zysku.</b> Ta populacja nóg rozliczyła się na "
        "−4,0% przy trafialności 87,1%, i niemal całość tego pomiaru to jeden "
        "dzień (5 220 z 5 285 nóg to 2026-09-19). Lista mówi: to jest prawdopodobne "
        "i nie jest to zdzierstwo. Nie mówi, że to wygrywa.", SMALL))
    S.append(Spacer(1, 5))

    if singles:
        shead = ("#", "mecz", "rynek", "linia", "pewność", "kurs", "x",
                 "marża", "próbka")
        srows = [[Paragraph(h, SMALL) for h in shead]]
        for i, leg in enumerate(printed_singles(doc_json), 1):
            subj = f" ({leg['subject']})" if leg.get("subject") else ""
            srows.append([
                Paragraph(str(i), SMALL),
                Paragraph(f"{leg['match']}<br/><font size=6.5>"
                          f"{leg['kickoff_utc'][11:16]}Z</font>", SMALL),
                Paragraph(f"{leg['market']}{subj}", SMALL),
                Paragraph(f"{leg['line']} {leg['direction']}", SMALL),
                Paragraph(f"<b>{leg['confidence']:.3f}</b>", SMALL),
                Paragraph(f"<b>{leg['offered_odds']}</b>", SMALL),
                Paragraph(f"<b>{leg['leg_ev'] + 1.0:.2f}</b>", SMALL),
                Paragraph(f"{leg['overround']:.1%}", SMALL),
                Paragraph(f"n={leg['sample_size']}", SMALL),
            ])
        st_ = Table(srows, colWidths=[
            6*mm, 40*mm, 34*mm, 18*mm, 16*mm, 13*mm, 12*mm, 14*mm, 13*mm])
        st_.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), BOLD, 7.6),
            ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
            ("BACKGROUND", (0, 0), (-1, 0), BAND),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
            ("LINEBELOW", (0, 1), (-1, -2), 0.25, RULE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (4, 1), (8, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ]))
        S.append(st_)
    else:
        S.append(Paragraph(
            "Dziś żadna noga nie stoi na drabinie tańszej niż "
            f"{MAX_OVERROUND:.1%}. To nie jest awaria — to odmowa.", BODY))
    S.append(PageBreak())

    for i, b in enumerate(picks, 1):
        fxr = fx_raw[b["sofascore_event_id"]]
        block: list = []
        ko = b["kickoff_utc"][11:16]
        block.append(Paragraph(f"{i}. {b['match']}", PICK))
        block.append(Paragraph(
            f"{fxr.get('competition_name') or '—'}"
            + (f" • {fxr.get('round_name')}" if fxr.get("round_name") else "")
            + f" • start {ko}Z"
            + _referee(fxr), SMALL))
        block.append(Spacer(1, 3))

        rows = [["#", "zakład", "pewność", "kurs", "implik.", "zaniżenie",
                 "własna próbka", "kalibracja"]]
        caveats: list[str] = []
        for j, x in enumerate(b["legs"], 1):
            leg_key = (
                b["sofascore_event_id"], x["market"], x["subject"],
                x["line"], x["direction"],
            )
            leg = legs_idx[leg_key]
            osp = own_sample(*leg_key)
            if osp:
                hits, nobs, lo, age, vals = osp
                emp = hits / nobs
                smp = f"{hits}/{nobs} = {emp:.2f}\n(ost. {age} dni)"
                if nobs < 10:
                    caveats.append(f"noga {j}: mała próbka n={nobs}")
                if emp < leg["confidence"] - 0.15:
                    caveats.append(
                        f"noga {j}: własna próbka {hits}/{nobs}={emp:.2f} wyraźnie poniżej "
                        f"pewności {leg['confidence']:.2f}")
            else:
                smp = "—"
                caveats.append(f"noga {j}: brak próbki do weryfikacji")
            sub = f" {x['subject']}" if x["subject"] else ""
            rows.append([
                str(j),
                Paragraph(f"<b>{x['market']}{sub}</b> {x['line']} {x['direction']}", BODY),
                f"{leg['confidence']:.3f}",
                f"{x['odds']}",
                f"{leg['implied_p']:.3f}",
                f"{leg['shading']:+.3f}",
                Paragraph(smp.replace("\n", "<br/>"), SMALL),
                Paragraph(f"{leg['calibrated_on'].replace('market:','')}<br/>n={leg['calibration_n']:,}".replace(",", " "), SMALL),
            ])
        t = Table(rows, colWidths=[7*mm, 52*mm, 16*mm, 13*mm, 15*mm, 18*mm, 26*mm, 34*mm])
        t.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), BOLD, 7.6),
            ("FONT", (0, 1), (-1, -1), BASE, 8.4),
            ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
            ("BACKGROUND", (0, 0), (-1, 0), BAND),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
            ("LINEBELOW", (0, 1), (-1, -2), 0.25, RULE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (2, 1), (5, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ]))
        block.append(t)
        block.append(Spacer(1, 4))

        after = b.get("odds_after_haircut")
        ev = displayed_ev(b)
        summ = [[
            Paragraph(f"<b>{b['n_legs']} nogi</b>", BODY),
            Paragraph(f"łączne p <b>{b['combined_probability']:.3f}</b>", BODY),
            Paragraph(f"kurs uczciwy <b>{b['fair_odds']}</b>", BODY),
            Paragraph(
                f"iloczyn {b['odds_if_product']} → po narzucie <b>{after}</b>"
                if after else f"iloczyn kursów {b['odds_if_product']}",
                BODY,
            ),
            Paragraph(f"<font color='#1b7f4b'><b>EV {ev:+.3f}</b></font>", BODY),
        ]]
        ts = Table(summ, colWidths=[20*mm, 31*mm, 31*mm, 50*mm, 49*mm])
        ts.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BAND),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        block.append(ts)
        if caveats:
            block.append(Spacer(1, 3))
            block.append(Paragraph(
                "<font color='#b25b00'><b>Zastrzeżenia:</b></font> " + "; ".join(caveats), SMALL))
        block.append(Spacer(1, 10))
        S.append(KeepTogether(block))

    pdf.build(S)
    print(json.dumps({
        "stage": "COUPON_PDF", "verdict": "OK",
        "metrics": {"picks": len(picks), "singles": len(singles),
                    "fixtures": len({b["sofascore_event_id"] for b in picks}),
                    "legs": sum(b["n_legs"] for b in picks)},
        "output_path": str(out_path),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
