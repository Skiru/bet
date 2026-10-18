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
from typing import Any
from xml.sax.saxutils import escape

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

from bet.sofa import coupon_results as cr  # noqa: E402
from bet.sofa import coupon_sports as cs  # noqa: E402
from bet.sofa import price_gap, timeutil  # noqa: E402
from bet.sofa.artifact_guard import incomplete_reason  # noqa: E402
from bet.sofa.atomic import tmp_path  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    CONFIDENCE_ARTIFACT,
    COUPON_PROFILE,
    MAX_OVERROUND,
    MIN_MINUTES_TO_KICKOFF,
    calibration_path_for,
    coupon_artifact,
    displayed_ev,
    fixture_leg_counts,
    ladder_key,
    ladder_leg_counts,
    printed_builders,
    printed_singles,
    too_close_to_kickoff,
)
from bet.sofa.config import config_path  # noqa: E402
from bet.sofa.contracts import Fixture  # noqa: E402
from bet.sofa.coupon_html import write_html  # noqa: E402
from bet.sofa.epochs import STATS_ONLY, artifact_epoch  # noqa: E402
from bet.sofa.locked_print import record_print  # noqa: E402
from bet.sofa.peer_choice import label as peer_choice_label  # noqa: E402
from bet.sofa.superbet_names import (  # noqa: E402
    FIELD_MARKET,
    FIELD_SELECTION,
    board_sides,  # noqa: E402
)
from bet.sofa.superbet_names import annotate as name_on_superbet  # noqa: E402
from scripts.sofa.build_family_record import (  # noqa: E402
    ensure_quietly as ensure_family_record,
)
from scripts.sofa.coupon_structure_pdf import (  # noqa: E402
    builder_screen_note,
    exposure_flowables,
    ladder_header,
    ladder_marker,
    ladders_of,
    refused_builder_flowables,
    table_with_headers,
)
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


def _referee(fixture: dict[str, Any]) -> str:
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
    sheet_rows: list[dict[str, Any]], keys: set[tuple[Any, ...]]
) -> list[str]:
    """Every constant a printed row names in its UNFITTED_CONSTANTS note.

    The sheet stamped it on all 16,052 rows on 2026-09-23 and the PDF - the
    one document the operator stakes from - said it zero times. CLAUDE.md
    forbids stripping it to make a report read better; leaving it out of the
    page did exactly that.
    """
    found: set[str] = set()
    for r in sheet_rows:
        k = (r["sofascore_event_id"], r["market"], r["subject"], r["line"],
             r["direction"])
        if k not in keys:
            continue
        for note in r.get("notes") or []:
            if note.startswith("UNFITTED_CONSTANTS:"):
                found.update(
                    c.strip() for c in note.split(":", 1)[1].split(",") if c.strip()
                )
    return sorted(found)


def watch_label(leg: dict[str, Any]) -> str:
    """A WATCH on a printed leg (a locked leg read after its print), shown on
    the leg so it is never staked unread."""
    watched = [r for r in leg.get("reads") or [] if r.get("verdict") == "WATCH"]
    if not watched:
        return ""
    who = ", ".join(sorted({str(r.get("author")) for r in watched}))
    return (f"<br/><font size=6.5 color='#b25b00'><b>WATCH ({who})</b>: "
            f"{escape(str(watched[0].get('reason') or ''))[:160]}</font>")


def context_label(leg: dict[str, Any]) -> str:
    """bet.sofa.schedule's tags (make-up fixture, long layoff, congestion)."""
    flags = leg.get("context_flags") or []
    if not flags:
        return ""
    return (f"<br/><font size=6.5 color='#b25b00'>"
            f"{escape(', '.join(str(f) for f in flags))}</font>")


PEER_MARK = "▲"
STAKES_NAMES = {
    "STAKES_SIX_POINTER": "mecz o utrzymanie (oba kluby przy linii spadkowej)",
    "STAKES_TOP4": "mecz o czołówkę (oba kluby przy linii 4./5. miejsca)",
}


def peer_label(leg: dict[str, Any]) -> str:
    """bet.sofa.peer_choice on a printed leg: the surest of the near-priced
    legs of its match gets a star, a weaker one names the surer."""
    # Arial (the page's font) has no U+2605: the page's mark is a triangle.
    text = peer_choice_label(leg).replace("★", PEER_MARK)
    if not text:
        return ""
    colour = "#1f7a3a" if (leg.get("peer") or {}).get("preferred") else "#6b6b6b"
    return f"<br/><font size=6.5 color='{colour}'>{escape(text)}</font>"


def stakes_label(leg: dict[str, Any]) -> str:
    """bet.sofa.stakes: what the match is played for, and which way that
    measured effect pushes this leg. Shown, never a gate."""
    st = leg.get("stakes")
    if not st:
        return ""
    names = "; ".join(
        STAKES_NAMES.get(str(f).split("(", 1)[0], str(f)) + " "
        + (str(f).split("(", 1)[1].rstrip(")") if "(" in str(f) else "")
        for f in st["flags"])
    effect = {"za": " - efekt stawki idzie za tą nogą",
              "przeciw": " - efekt stawki idzie przeciw tej nodze"}.get(
                  str(st.get("effect") or ""), "")
    return (f"<br/><font size=6.5 color='#b25b00'>{escape(names)}"
            f"{escape(effect)}</font>")


def price_gap_label(leg: dict[str, Any]) -> str:
    """bet.sofa.price_gap: a confidence above the price, and what such legs
    realised. Shown, never a gate."""
    text = price_gap.label(leg)
    if not text:
        return ""
    return f"<br/><font size=6.5 color='#b25b00'>{escape(text)}</font>"


# A leg the previous build printed and whose match started before this
# rebuild (bet.sofa.locked_print, the operator's decision of 2026-10-05): it
# counts, stays on the page as printed, and says so.
LOCKED_LABEL = "w grze - wydrukowane przed startem"


def locked_label(item: dict[str, Any]) -> str:
    """The mark on a locked single or builder, with the build it was printed
    in; empty for everything else."""
    if not item.get("locked"):
        return ""
    at = str(item.get("printed_at_utc") or "")
    when = f" (wydruk {at[11:16]}Z)" if len(at) >= 16 else ""
    return (f"<br/><font size=6.5 color='#1f5fa8'><b>{LOCKED_LABEL}</b>"
            f"{escape(when)}</font>")


def started_at_render(leg: dict[str, Any], now: datetime.datetime) -> bool:
    """Is this printed leg inside CONFIDENCE's kickoff margin at render time?

    CONFIDENCE gates on its own clock; a PDF rendered later from the same JSON
    (a rebuild, a re-render) would print a leg that has already started with
    nothing on the page saying so. The leg is kept - the JSON is what is
    graded - and marked. Its kickoff_utc is the earlier of the two clocks.
    """
    ko = leg.get("kickoff_utc")
    if not ko:
        return True
    clock = datetime.datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
    return too_close_to_kickoff([clock], now)


def confidence_older_than_sheet(run: Path, artifact: str) -> str | None:
    """Why the PDF must not be built, or None.

    The PDF is the coupon and prints CONFIDENCE's legs at CONFIDENCE's prices.
    A 05_sheet.json newer than the confidence artifact means SHEET (and so,
    since 2026-09-25, an OFFER refresh) ran after CONFIDENCE did: the PDF
    would print the earlier prices as today's coupon. Found in review
    2026-09-29 - a day built the afternoon before would otherwise be printed
    again whenever the morning's CONFIDENCE failed.
    """
    conf = run / artifact
    if not conf.exists():
        return None
    # vetoes.json and reads.json too (2026-09-29, 2026-10-04): a veto or a
    # WATCH merged after CONFIDENCE must not print on the PDF.
    for newer in ("05_sheet.json", "vetoes.json", "reads.json"):
        path = run / newer
        if path.exists() and conf.stat().st_mtime < path.stat().st_mtime:
            return (
                f"STALE_CONFIDENCE: {artifact} is older than {newer} - run "
                "run_confidence.py for this day before the PDF"
            )
    # The operator's refused_markets / admitted_player_markets live in the
    # calibration file (review 2026-10-04): a PDF-only re-render after an
    # entry was added would print the newly refused market.
    calibration = calibration_path_for(run.name)
    if calibration.exists() and conf.stat().st_mtime < calibration.stat().st_mtime:
        return (
            f"STALE_CONFIDENCE: {artifact} is older than {calibration.name} "
            "(refused / admitted markets, curves) - run run_confidence.py first"
        )
    return None


def coupon_older_than_sources(run: Path) -> str | None:
    """Why 11_coupon.json must not be printed: it is older than one of the
    artifacts it was assembled from (build_coupon.py, K3)."""
    eleven = run / "11_coupon.json"
    if not eleven.exists():
        return None
    # 09_screen_prices.json and the coupon form (F4.2-F4.4): a screen price
    # or a dial entered after the assembly is not on the coupon yet.
    for source in ("08_confidence.json", "08_confidence_sports.json",
                   "read_requests.json", "09_screen_prices.json",
                   str(config_path("sofa_coupon_form.json"))):
        path = run / source
        if path.exists() and eleven.stat().st_mtime < path.stat().st_mtime:
            return (
                f"STALE_COUPON: 11_coupon.json is older than {path.name} - run "
                "build_coupon.py for this day before the PDF"
            )
    return None


def single_sample(leg: dict[str, Any]) -> str:
    """The leg's own sample on the page: k/n where the leg carries its hit
    rate, else n."""
    rate, n = leg.get("sample_hit_rate"), leg.get("sample_observations")
    if leg.get("sample_k") is not None and leg.get("sample_n"):
        return f"{leg['sample_k']}/{leg['sample_n']}"
    if rate is not None and n:
        return f"{round(float(rate) * int(n))}/{n}"
    return f"n={leg.get('sample_size', '—')}"


def market_cell(leg: dict[str, Any], marker: str, fallback: str) -> str:
    """The "rynek" cell: Superbet's market name and, in bold, the selection
    to click (bet.sofa.superbet_names) - "3. tercja - Seattle Kraken - liczba
    goli: <b>poniżej 1.5</b>"; a leg it cannot name keeps its old label."""
    market, pick = leg.get(FIELD_MARKET), leg.get(FIELD_SELECTION)
    if market:
        return (escape(str(market))
                + (f": <b>{escape(str(pick))}</b>" if pick else "") + marker)
    if leg.get("display_market"):
        return escape(str(leg["display_market"])) + marker
    return fallback


# The "linia" column's direction in the screen's words (the market cell
# names the side; T1 / T2 stay as the handicap's side code).
DIRECTION_SHORT = {"OVER": "pow.", "UNDER": "pon.", "YES": "tak", "NO": "nie"}


def line_cell(leg: dict[str, Any]) -> str:
    direction = str(leg.get("direction") or "")
    return f"{cs.display_line(leg)} {DIRECTION_SHORT.get(direction, direction)}"


def leg_x(leg: dict[str, Any]) -> float:
    if leg.get("x") is not None:
        return float(leg["x"])
    return float(leg["confidence"]) * float(leg["offered_odds"])


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
    # A settled day's results on its own coupon (bet.sofa.coupon_results,
    # scripts/sofa/mark_coupon_results.py): a view of a finished day, not a
    # print - no print record, and the freshness guards (a coupon priced on
    # curves installed since) do not apply to a day that is over.
    ap.add_argument("--with-results", action="store_true")
    args = ap.parse_args()
    profile = COUPON_PROFILE

    run = Path(args.runs_dir) / args.date
    frozen = timeutil.frozen_clock_refusal(args.runs_dir)
    if frozen:
        print(frozen, file=sys.stderr)
        return 2
    refusal = incomplete_reason(run / "02_fixtures.json")
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    now = timeutil.now()  # the one clock (bet.sofa.timeutil)
    # The coupon artifact (K3): 11_coupon.json on a stats-only day.
    artifact = coupon_artifact(run).name
    doc_json = json.loads((run / artifact).read_text(encoding="utf-8"))
    # the legs named in Superbet's words (an artifact assembled before the
    # names existed gets them here; display only, no leg changes)
    name_on_superbet(doc_json, board_sides(run))
    so = artifact_epoch(doc_json) == STATS_ONLY
    if so and artifact != "11_coupon.json":
        print("REFUSED: a stats-only 08_confidence.json is not the coupon - "
              "run build_coupon.py first (11_coupon.json)", file=sys.stderr)
        return 2
    # The artifact names the profile it was built with; a retired variant's
    # JSON (renamed into the coupon's slot) never prints as the coupon.
    built_with = doc_json.get("profile", "standard")
    if built_with != profile.name:
        print(
            f"{artifact} was built with profile {built_with!r}, not {profile.name!r}",
            file=sys.stderr,
        )
        return 2
    # Only a results render reads the results: a normal render (a print, a
    # rebuild) never carries them, whatever is on disk.
    results = cr.load(run) if so and args.with_results else None
    if args.with_results:
        why = cr.markable(args.date, now)
        if why:
            print(f"REFUSED: --with-results on {args.date}: {why}", file=sys.stderr)
            return 2
        if results is None:
            print(f"REFUSED: no {cr.RESULTS_FILE} - run mark_coupon_results.py",
                  file=sys.stderr)
            return 2
    stale = None if args.with_results else (
        confidence_older_than_sheet(run, CONFIDENCE_ARTIFACT) or (
            coupon_older_than_sources(run) if so else None))
    if stale:
        print(stale, file=sys.stderr)
        return 2
    samples = {
        s["sofascore_event_id"]: s
        for s in json.loads((run / "03_samples.json").read_text(encoding="utf-8"))
    }
    raw = (run / "02_fixtures.json").read_bytes()
    fx_obj = {f.sofascore_event_id: f
              for f in RootModel[list[Fixture]].model_validate_json(raw).root}
    fx_raw = {f["sofascore_event_id"]: f for f in json.loads(raw)}

    legs_idx = {
        (leg["sofascore_event_id"], leg["market"], leg["subject"], leg["line"],
         leg["direction"]): leg
        for leg in doc_json["legs"]
    }

    def own_sample(
        eid: Any, market: Any, subject: Any, line: Any, direction: Any
    ) -> tuple[int, int, float, int, list[Any]] | None:
        side: str | None
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
        age = (now - datetime.datetime.fromisoformat(
            newest.replace("Z", "+00:00"))).days
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
        if "ev_after_haircut" in (doc_json["builders"][0]
                                  if doc_json["builders"] else {})
        else "ev_if_product_priced"
    )
    # Until 2026-09-29 the variant printed no builders (a singles
    # experiment); since then it prints its stakeable ones, at the operator's
    # request. The artifact records which, so an old variant artifact
    # rebuilt today still prints none.
    picks = printed_builders(doc_json)
    # Singles. Present since 2026-09-22: on a day where no Bet Builder forms —
    # which needs two legs of DIFFERENT quantity families in the SAME match —
    # this renderer used to emit a blank page while the confidence artifact
    # held dozens of qualifying legs. 2026-09-22 had 37 legs and 0 builders.
    # What the page prints, not what the artifact holds: the official profile
    # caps the table at PDF_MAX_SINGLES, and a header, an UNFITTED banner or a
    # summary counting rows nobody sees describes a different coupon.
    singles = printed_singles(doc_json)
    # The margin the artifact was selected under. The page used to quote the
    # global 10.5% even on the variant, whose limit is 15% and whose rows
    # print margins above 10.5% one column over.
    max_overround = doc_json.get("max_overround", MAX_OVERROUND)
    # Locked builders first (they are already in play), then by EV - or, in
    # the stats-only epoch (K10), by the combined probability.
    if so:
        picks.sort(key=lambda b: (not b.get("locked"), -b["combined_probability"]))
    else:
        picks.sort(key=lambda b: (not b.get("locked"), -b[ev_key]))
    n_locked = sum(1 for x in [*singles, *picks] if x.get("locked"))

    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=ss["Title"], fontName=BOLD, fontSize=19,
                        textColor=INK, spaceAfter=2, alignment=TA_LEFT)
    subtitle = ParagraphStyle("SUB", parent=ss["Normal"], fontName=BASE,
                              fontSize=8.6, textColor=MUTED, leading=12.5)
    h2 = ParagraphStyle("H2", parent=ss["Heading2"], fontName=BOLD, fontSize=11.5,
                        textColor=INK, spaceBefore=9, spaceAfter=4)
    body = ParagraphStyle("BODY", parent=ss["Normal"], fontName=BASE,
                          fontSize=8.6, textColor=INK, leading=12.4)
    small = ParagraphStyle("SMALL", parent=ss["Normal"], fontName=BASE,
                           fontSize=7.5, textColor=MUTED, leading=10.2)
    pick = ParagraphStyle("PICK", parent=ss["Normal"], fontName=BOLD, fontSize=10.5,
                          textColor=INK, spaceAfter=1)

    out_path = Path(args.out or (run / f"KUPON_{args.date}.pdf"))
    # Rendered beside the target and moved into place: a crash mid-render
    # must never leave a truncated KUPON_*.pdf where the coupon was.
    tmp_out = tmp_path(out_path)
    pdf = SimpleDocTemplate(
        str(tmp_out), pagesize=A4,
        leftMargin=15 * mm, rightMargin=13 * mm, topMargin=14 * mm,
        bottomMargin=13 * mm,
        title=f"Kupon {args.date}", author="sofa pipeline",
    )
    story: list[Any] = []
    title = f"Kupon — {args.date}"
    story.append(Paragraph(title, h1))
    story.append(Paragraph(
        f"Zbudowany {doc_json['created_at_utc']} &nbsp;•&nbsp; "
        f"{len(picks)} zakładów łączonych, {len(singles)} pojedynczych "
        + (f"(w tym {n_locked} {LOCKED_LABEL}) " if n_locked else "")
        + "&nbsp;•&nbsp; "
        f"próg pewności {doc_json['confidence_floor']}"
        + ("" if profile.min_ev is None
           else f" &nbsp;•&nbsp; pewność × kurs ≥ {profile.min_ev:.2f}"
                f" &nbsp;•&nbsp; marża rynku ≤ {profile.max_overround:.0%}"), subtitle))
    if profile.min_ev is not None:
        story.append(Paragraph(
            "<b>Od 05.10 (decyzja operatora)</b> oficjalny kupon przyjmuje "
            f"pewność × kurs ≥ {profile.min_ev:.2f} (kurs do "
            f"{1 - profile.min_ev:.0%} poniżej uczciwego) i marżę rynku do "
            f"{profile.max_overround:.0%}; wcześniej x &gt; 1,00 i 10,5%. "
            "Zmierzone wcześniej dawały więcej zakładów, nie "
            "przewagę; nogi kuponu z marżą 10,5–15% traciły dotąd −12,8% "
            "(n=50) wobec −4,6% (n=78). Wyniki sprzed 05.10 to inny "
            "eksperyment i nie są z nimi łączone.", subtitle))
    sheet_doc = json.loads((run / "05_sheet.json").read_text(encoding="utf-8"))
    sheet_rows = sheet_doc if isinstance(sheet_doc, list) else sheet_doc["rows"]
    # A builder's legs carry no event id of their own; it is on the builder.
    printed = {
        (item["sofascore_event_id"], leg["market"], leg["subject"], leg["line"],
         leg["direction"])
        for item in [*picks, *singles]
        for leg in (item.get("legs") or [item])
    }
    unfitted = sorted(set(unfitted_constants(sheet_rows, printed)) | {
        c for item in [*picks, *singles] for leg in (item.get("legs") or [item])
        for c in (leg.get("unfitted_constants") or [])})
    if unfitted:
        story.append(Paragraph(
            "<font color='#b25b00'><b>UNFITTED_CONSTANTS: "
            f"{', '.join(unfitted)}</b></font> "
            "— te stałe nie są dopasowane do rozliczeń. Liczby w tym kuponie na nich "
            "stoją; traktuj je jako niezmierzone.", subtitle))
    if results is not None:
        story.append(Paragraph(results_headline(singles, picks, results), body))
    story.append(Spacer(1, 7))

    if so:
        render_stats_only(story, doc_json, singles, picks, legs_idx, now,
                          body, small, h2, pick, max_overround, results)
        pdf.build(story)
        # A results render keeps the printed PDF beside it and the PDF's
        # time: run_confidence and audit_variants read the PDF's mtime as
        # "the last build was printed", and a view of a finished day is no
        # print.
        keep_time = (out_path.stat().st_mtime
                     if args.with_results and out_path.exists() else None)
        if args.with_results and args.out is None:
            cr.keep_original(out_path)
        os.replace(tmp_out, out_path)
        if keep_time is not None:
            os.utime(out_path, (keep_time, keep_time))
        # The record of what this PDF printed (locked_print.record_print):
        # printed/<render time>.json, append-only (F0.1), and
        # PRINTED_MANIFEST as the latest render. The next rebuild carries
        # over every printed leg whose match has started, as first printed,
        # whatever build or render came in between. Only for the day's own
        # coupon, never for a --out render elsewhere.
        if args.out is None and not args.with_results:
            record_print(run, {**doc_json, "pdf": out_path.name,
                               "pdf_rendered_at_utc": now.isoformat().replace(
                                   "+00:00", "Z")})
        # The same legs as a filterable page (bet.sofa.coupon_html), beside the
        # PDF and rendered with it: a rebuilt PDF always brings its HTML.
        # Skipped for a --out render elsewhere. A failure leaves the PDF as it
        # is and ends PARTIAL (exit 1).
        html_path: Path | None = None
        html_error = ""
        if args.out is None:
            # the families' record the page filters on (bet.sofa.family_record):
            # recomputed when the ledger moved; a failure only hides the filter
            fam_error = ensure_family_record(args.runs_dir, args.date)
            if fam_error:
                print(f"family_record.json NOT refreshed: {fam_error}",
                      file=sys.stderr)
            try:
                html_out = run / f"KUPON_{args.date}.html"
                html_time = (html_out.stat().st_mtime
                             if args.with_results and html_out.exists() else None)
                if args.with_results:
                    cr.keep_original(html_out)
                html_path = write_html(run, doc_json, args.date, results)
                if html_time is not None:
                    os.utime(html_path, (html_time, html_time))
            except Exception as exc:  # noqa: BLE001 - the PDF is already written
                html_error = f"{type(exc).__name__}: {exc}"
                print(f"KUPON_{args.date}.html NOT written: {html_error}",
                      file=sys.stderr)
        print(json.dumps({
            "stage": "COUPON_PDF", "verdict": "PARTIAL" if html_error else "OK",
            "epoch": STATS_ONLY,
            "metrics": {"picks": len(picks), "singles": len(singles),
                        "positions": doc_json.get("positions"),
                        "locked": n_locked},
            "output_path": str(out_path),
            "html_path": str(html_path) if html_path else None,
        }))
        return 1 if html_error else 0

    story.append(Paragraph("Jak czytać ten kupon", h2))
    story.append(Paragraph(
        "<b>pewność</b> to <i>dolna granica zmierzonej realizacji</i> — ile razy na 1 "
        "868 474 "
        "rozliczonych wierszy zdarzenie faktycznie zaszło przy tej ocenie modelu. To "
        "nie jest "
        "deklaracja modelu. Model jest skalibrowany z dokładnością do 0,3 pkt proc. "
        "do poziomu 0,90, "
        "i ma tam <b>sufit ~0,92</b>: kubełki 0,900–0,925 i 0,925–0,950 realizują "
        "identyczne 0,9083. "
        "<b>Nogi 98% nie istnieją.</b>", body))
    story.append(Paragraph(
        "<b>kurs uczciwy</b> to cena, jakiej kombinacja wymaga, żeby być warta "
        "ryzyka. To <b>nie</b> "
        "prognoza ceny Bet Buildera w Superbecie — bukmacher stosuje własną korektę "
        "korelacji. "
        "Porównaj z ekranem.", body))
    story.append(Paragraph(
        "<b>Po narzucie</b> to iloczyn kursów nóg pomniejszony o <b>12%</b> — tyle "
        "Superbet bierze "
        "za korelację. Zmierzone 2026-09-20 na trzech slipach z ekranu: 8,8% (2 "
        "nogi), 15,8% "
        "(2 nogi zagnieżdżone), 19,6% (4 nogi). <b>EV liczone jest od tej ceny</b>, "
        "nie od iloczynu. "
        "Wcześniej kupon wybierał po iloczynie, czyli po cenie, której bukmacher "
        "nigdy nie podał: "
        "z 37 slipów z 2026-09-19 nawet najmniejszy zmierzony narzut zostawiał "
        "dodatnie <b>dwa</b>. "
        "Jeśli ekran pokazuje więcej niż „po narzucie”, slip jest lepszy niż tu "
        "napisano; jeśli "
        "mniej — gorszy, i wtedy go nie bierz.", body))
    story.append(Paragraph(
        "<b>Zaniżenie kursu</b> wynosi płasko ok. 5,4 pkt proc. niezależnie od "
        "pewności i "
        "<b>kumuluje się</b> przy dokładaniu nóg: mediana EV to −0,058 przy jednej "
        "nodze, −0,082 "
        "przy trzech, −0,118 przy czterech. Dokładanie „pewniaków” nie poprawia "
        "kuponu. "
        "Wybrane niżej zakłady to te, w których konkretna noga jest źle wyceniona i "
        "EV wychodzi "
        "na plus mimo zaniżenia.", body))
    story.append(Paragraph(
        "Nogi w jednym zakładzie pochodzą z <b>różnych wielkości</b> (gole / rożne / "
        "faule / kartki). "
        "Gole drużyny i gole meczu to ta sama wielkość liczona dwa razy (λ=2,165), "
        "więc nigdy nie "
        "trafiają do jednego kuponu. Rynki złożone (both_over_*, handicap_*) są "
        "odrzucone — mają "
        "18–252 rozliczonych wierszy, za mało by cokolwiek twierdzić.", body))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Model <b>nie</b> bije ceny (Brier 0,2067 vs 0,1845 dla rynku). Ten kupon nie "
        "twierdzi, że "
        "znajduje value — twierdzi, że wie, jak często dane zdarzenie zachodzi. "
        "Rentowność nie jest "
        "wykazana; potrzeba kilku dni rozliczeń.", small))
    story.append(PageBreak())

    story.append(Paragraph("Zakłady pojedyncze", h2))
    story.append(Paragraph(
        "Uszeregowane po <b>pewności</b>, nie po EV. To celowe: <b>EV nogi jest "
        "zmierzone jako odwrócone</b>. `confidence` jest funkcją schodkową, więc "
        "wewnątrz jednego kubełka kalibracji EV rośnie wyłącznie z kursem — a "
        "dłużej wyceniona jedna trzecia kubełka trafia <b>rzadziej</b> niż "
        "krótsza, za każdym razem, i różnica rośnie z pewnością (2 pkt proc. "
        "przy 0,811, 10 pkt proc. przy 0,906).", body))
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
            "ryzyko; na tej liście przyjmowane są też pozycje od "
            f"<b>{profile.min_ev:.2f}</b> do 1,00 — czyli kurs do "
            f"{1 - profile.min_ev:.0%} <b>poniżej</b> uczciwego. Każda pozycja z "
            "x &lt; 1,00 jest świadomie przepłacona: to koszt większej liczby "
            "zakładów, nie przewaga."
        )
    story.append(Paragraph(x_rule, body))
    story.append(Paragraph(
        f"<b>marża</b> to narzut Superbeta na tej drabinie, policzony z ceny "
        f"dwustronnej. Powyżej <b>{max_overround:.1%}</b> noga nie trafia na tę "
        "listę. Próg 10,5% to jedyny, na którym wyniki się rozdzielają (poniżej "
        "zwrot jest płaski ok. −3,5%, powyżej spada do −5,7%)"
        + ("" if math.isclose(max_overround, MAX_OVERROUND)
           else f"; ta lista świadomie przyjmuje marże do {max_overround:.1%}")
        + ". Rogi wyceniane są medianowo na 8,6%, gole na 10,2%.", body))
    story.append(Paragraph(
        "<b>To nie jest obietnica zysku.</b> Ta populacja nóg rozliczyła się na "
        "−4,0% przy trafialności 87,1%, i niemal całość tego pomiaru to jeden "
        "dzień (5 220 z 5 285 nóg to 2026-09-19). Lista mówi: to jest prawdopodobne "
        "i nie jest to zdzierstwo. Nie mówi, że to wygrywa.", small))
    story.append(Spacer(1, 5))

    if singles:
        shead = ("#", "mecz", "rynek", "linia", "pewność", "kurs", "x",
                 "marża", "próbka")
        srows = [[Paragraph(h, small) for h in shead]]
        # See fixture_leg_counts: singles of one match are one bet in pieces.
        per_fixture = fixture_leg_counts(singles)
        per_ladder = ladder_leg_counts(singles)
        n_ladders = sum(1 for n in per_ladder.values() if n > 1)
        if n_ladders:
            story.append(Paragraph(
                f"<b>{n_ladders} drabin(a/y) ma na tej liście więcej niż jeden "
                "szczebel</b> — oznaczone 'ta sama drabina: N'. To jedno "
                "twierdzenie o jednej liczbie kupione kilka razy.", small))
            story.append(Spacer(1, 3))
        shared = sum(1 for n in per_fixture.values() if n > 1)
        if shared:
            story.append(Paragraph(
                f"<b>{shared} mecz(e/ów) ma na tej liście więcej niż jedną "
                "nogę</b> — oznaczone 'ten sam mecz: N nóg'. Takie nogi "
                "wygrywają i przegrywają razem: to jeden zakład w kawałkach, "
                "nie kilka niezależnych.", small))
            story.append(Spacer(1, 3))
        for i, leg in enumerate(singles, 1):
            subj = f" ({leg['subject']})" if leg.get("subject") else ""
            n_same = per_fixture[int(leg["sofascore_event_id"])]
            same = (f"<br/><font size=6.5 color='#b23b3b'>ten sam mecz: "
                    f"{n_same} nóg</font>" if n_same > 1 else "")
            n_rungs = per_ladder[ladder_key(leg)]
            if n_rungs > 1:
                same += (f"<br/><font size=6.5 color='#b23b3b'>ta sama drabina: "
                         f"{n_rungs}</font>")
            if leg.get("locked"):
                same += locked_label(leg)
            elif started_at_render(leg, now):
                same += ("<br/><font size=6.5 color='#b23b3b'><b>start przed "
                         "renderem PDF</b></font>")
            same += watch_label(leg) + context_label(leg) + price_gap_label(leg)
            srows.append([
                Paragraph(str(i), small),
                Paragraph(f"{leg['match']}<br/><font size=6.5>"
                          f"{leg['kickoff_utc'][11:16]}Z</font>{same}", small),
                Paragraph(f"{leg['market']}{subj}", small),
                Paragraph(f"{leg['line']} {leg['direction']}", small),
                Paragraph(f"<b>{leg['confidence']:.3f}</b>", small),
                Paragraph(f"<b>{leg['offered_odds']}</b>", small),
                Paragraph(f"<b>{leg['leg_ev'] + 1.0:.2f}</b>", small),
                Paragraph("—" if leg.get("overround") is None
                          else f"{leg['overround']:.1%}", small),
                Paragraph(f"n={leg['sample_size']}", small),
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
        story.append(st_)
    else:
        story.append(Paragraph(
            "Dziś żadna noga nie stoi na drabinie tańszej niż "
            f"{max_overround:.1%}. To nie jest awaria — to odmowa.", body))
    story.append(PageBreak())

    for i, b in enumerate(picks, 1):
        fxr = fx_raw[b["sofascore_event_id"]]
        block: list[Any] = []
        ko = b["kickoff_utc"][11:16]
        block.append(Paragraph(f"{i}. {b['match']}", pick))
        block.append(Paragraph(
            f"{fxr.get('competition_name') or '—'}"
            + (f" • {fxr.get('round_name')}" if fxr.get("round_name") else "")
            + f" • start {ko}Z"
            + _referee(fxr) + locked_label(b), small))
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
                        f"noga {j}: własna próbka {hits}/{nobs}={emp:.2f} wyraźnie "
                        "poniżej "
                        f"pewności {leg['confidence']:.2f}")
            else:
                smp = "—"
                caveats.append(f"noga {j}: brak próbki do weryfikacji")
            for flag in leg.get("context_flags") or []:
                caveats.append(f"noga {j}: {escape(str(flag))}")
            for r in leg.get("reads") or []:
                if r.get("verdict") == "WATCH":
                    caveats.append(
                        f"noga {j}: WATCH ({r.get('author')}): "
                        f"{escape(str(r.get('reason') or ''))[:160]}")
            sub = f" {x['subject']}" if x["subject"] else ""
            rows.append([
                str(j),
                Paragraph(f"<b>{x['market']}{sub}</b> {x['line']} "
                          f"{x['direction']}", body),
                f"{leg['confidence']:.3f}",
                f"{x['odds']}",
                f"{leg['implied_p']:.3f}",
                f"{leg['shading']:+.3f}",
                Paragraph(smp.replace("\n", "<br/>"), small),
                Paragraph(f"{leg['calibrated_on'].replace('market:','')}<br/>"
                          f"n={leg['calibration_n']:,}".replace(",", " "), small),
            ])
        t = Table(rows, colWidths=[7*mm, 52*mm, 16*mm, 13*mm, 15*mm, 18*mm,
                                   26*mm, 34*mm])
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
            Paragraph(f"<b>{b['n_legs']} nogi</b>", body),
            Paragraph(f"łączne p <b>{b['combined_probability']:.3f}</b>", body),
            Paragraph(f"kurs uczciwy <b>{b['fair_odds']}</b>", body),
            # Never the product of the legs' prices: Superbet does not price a
            # slip that way (CLAUDE.md, measured markup 8.8-19.6%). Only the
            # haircut price confidence.py computed is printed.
            Paragraph(
                f"kurs po narzucie <b>{after}</b>" if after else "kurs po narzucie —",
                body,
            ),
            Paragraph(f"<font color='#1b7f4b'><b>EV {ev:+.3f}</b></font>", body),
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
                "<font color='#b25b00'><b>Zastrzeżenia:</b></font> "
                + "; ".join(caveats), small))
        block.append(Spacer(1, 10))
        story.append(KeepTogether(block))

    pdf.build(story)
    os.replace(tmp_out, out_path)
    # A locked leg started on purpose: it is the record, not a late print.
    late = [leg for leg in singles
            if not leg.get("locked") and started_at_render(leg, now)]
    if late:
        print(
            f"WARNING: {len(late)} printed single(s) kick off within "
            f"{MIN_MINUTES_TO_KICKOFF} min of this render (or already started) - "
            "marked on the page",
            file=sys.stderr,
        )
    print(json.dumps({
        "stage": "COUPON_PDF", "verdict": "OK",
        "metrics": {"picks": len(picks), "singles": len(singles),
                    "fixtures": len({b["sofascore_event_id"] for b in picks}),
                    "legs": sum(b["n_legs"] for b in picks)},
        "output_path": str(out_path),
    }))
    return 0


def _table(rows: list[list[Any]], widths: list[float]) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), BOLD, 7.6),
        ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ("BACKGROUND", (0, 0), (-1, 0), BAND),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


# Why FIXTURE_CHECK has no fresh status (fixture_status.UNVERIFIED_REASONS),
# in the operator's words. Until F0.5 every one printed as "bez mostka"; the
# one UNVERIFIED match of 10-05 had been asked through a working bridge.
UNVERIFIED_REASON_PL = {
    "NOT_FOUND": "Sofascore nie zna meczu (404)",
    "PROVIDER_REFUSED": "Sofascore odmówił (403/429)",
    "PROVIDER_ERROR": "błąd Sofascore (5xx)",
    "BAD_PAYLOAD": "niepełna odpowiedź Sofascore",
    "NO_BRIDGE": "brak mostka / zerwane połączenie",
    "CIRCUIT_OPEN": "bezpiecznik otwarty",
    "NOT_ASKED": "nie pytano - sprawdzanie przerwane po błędzie",
    "OVER_CAP": "nie pytano - kandydat ponad limit sprawdzanych meczów",
    "UNKNOWN": "powód niezapisany",
}


def fixture_status_notes(doc: dict[str, Any]) -> list[str]:
    """The page's notes on FIXTURE_CHECK: how many matches have no fresh
    status and why (F0.5), and how many printed matches were never asked
    (F0.4: fixture_status_not_asked)."""
    out: list[str] = []
    n = doc.get("fixture_status_unverified")
    if n:
        reasons = doc.get("fixture_status_unverified_reasons") or {"UNKNOWN": n}
        why = ", ".join(
            f"{UNVERIFIED_REASON_PL.get(str(r), escape(str(r)))}: {c}"
            for r, c in sorted(reasons.items()))
        out.append(f"{n} mecz(e/ów) bez świeżego statusu ({why})")
    if doc.get("fixture_status_not_asked"):
        out.append(f"{doc['fixture_status_not_asked']} mecz(e/ów) na kuponie bez "
                   "sprawdzonego statusu (FIXTURE_CHECK o nie nie pytał)")
    return out


def render_stats_only(
    story: list[Any],  # the renderer's story, as in main()
    doc: dict[str, Any],
    singles: list[dict[str, Any]],
    picks: list[dict[str, Any]],
    legs_idx: dict[tuple[Any, ...], dict[str, Any]],
    now: datetime.datetime,
    body: ParagraphStyle,
    small: ParagraphStyle,
    h2: ParagraphStyle,
    pick: ParagraphStyle,
    max_overround: float,
    results: dict[str, Any] | None = None,
) -> None:
    """The one coupon of a stats-only day (plan 2026-10-05, K3/K10/K11).
    With `results` (bet.sofa.coupon_results) every row carries its result
    and colour, and the page ends with the percent summary."""
    story.append(Paragraph("Jak czytać ten kupon", h2))
    story.append(Paragraph(
        "<b>pewność</b> pochodzi wyłącznie ze statystyk: to dolna granica "
        "zmierzonej realizacji dla tej oceny próbki (krzywa kalibracji na "
        "rozliczonej historii). Cena Superbeta <b>nie</b> wchodzi do pewności, "
        "kolejności ani wyboru builderów — jest tylko warunkiem postawienia: "
        f"<b>x = pewność × kurs ≥ {doc.get('min_ev') or 0.90:.2f}</b> i marża "
        f"drabiny ≤ {max_overround:.0%}. Kolejność: pewność malejąco, potem "
        "wcześniejszy start; nogi jednego meczu stoją razem, blok na miejscu "
        "najlepszej nogi.", body))
    story.append(Paragraph(
        "<b>model</b> to druga liczba: prognoza z ratingu (piłka: siła ataku i "
        "obrony z ligi; tenis: rating zawodników), bez ceny. Jest "
        "<b>nieskalibrowana</b> i niczego nie bramkuje — pokazana obok, żeby "
        "było widać, gdzie rating i próbka się rozchodzą. "
        "„—” = brak ratingu.",
        body))
    if (doc.get("peer_choice") or {}).get("active"):
        story.append(Paragraph(
            f"<b>{PEER_MARK}</b> oznacza najpewniejszą nogę meczu spośród nóg "
            f"o kursie w pasie ±{doc['peer_choice']['band']:.2f} - to samo "
            "<b>pewność</b>, nic więcej: na 57,8 tys. rozstrzygniętych par "
            "(piłka i tenis, 20 dni) pewniejsza noga wygrała 53,4% "
            "[52,2; 54,7], a żadna statystyka próbki ani metadana turnieju "
            "nie poprawiła tego poza próbą; w hokeju, koszykówce i siatkówce "
            "różnicy nie zmierzono. Jest to wskazanie słabe, nie pewniak. "
            "<b>Mecz o utrzymanie / czołówkę</b> to kontekst z tabeli (mierzony: "
            "średnio +0,2 kartki, +0,9 faulu, -0,15 gola na mecz), pokazany "
            "obok nogi i nigdy jej nie bramkujący.", small))
    unit = (
        "<b>wszystkie nogi 30 meczów o najwyższej wartości</b> (pewność x kurs "
        "najlepszej nogi meczu, pewność nogi nad ceną liczona najwyżej "
        "1/kurs + 0,03; 30 wydarzeń, nie 30 rynków)"
        if doc.get("read_unit") == "event" and doc.get("read_order") == "value"
        else "<b>wszystkie nogi 30 pierwszych meczów</b> kuponu (mecz najlepszej "
        "nogi pierwszy; 30 wydarzeń, nie 30 rynków)"
        if doc.get("read_unit") == "event" else "<b>30 pierwszych pozycji</b>")
    story.append(Paragraph(
        f"Analitycy czytają {unit} i każdą nogę "
        "drukowanego buildera; pozostałe drukują się bez odczytu (dodatkowe "
        "na życzenie operatora). Noga zdjęta przez odczyt (WATCH / NO_BET) "
        "nie jest na kuponie i rozlicza się osobno.", small))
    # F7 / K14: what the page does not hold, said on the page.
    notes = []
    for sport, st in sorted((doc.get("sports") or {}).items()):
        status = st.get("status") if isinstance(st, dict) else st
        if status and status != "OK":
            notes.append(f"{escape(str(sport))}: "
                         + {"NOT_CALIBRATED": "brak kalibracji",
                            "NOT_IDENTIFIED": "mecze nierozpoznane"}.get(
                                str(status), escape(str(status))))
    for fx in doc.get("fixtures_not_as_scheduled") or []:
        notes.append(f"{escape(str(fx.get('match')))}: {escape(str(fx.get('status')))}"
                     " - nie gra wg terminarza, poza kuponem")
    notes += fixture_status_notes(doc)
    if notes:
        story.append(Paragraph("<font color='#b25b00'><b>Uwaga:</b></font> "
                               + "; ".join(notes) + ".", small))
    story.append(Spacer(1, 4))

    locked = [s for s in singles if s.get("locked")]
    fresh = [s for s in singles if not s.get("locked")]
    blocks = {int(b["block"]): b for b in doc.get("blocks") or []}
    # F4.2: the legs of one variable of a match (a ladder, an OVER + UNDER
    # pair) under one header "ta sama zmienna" - one decision, not N bets.
    ladder_of, ladder_docs = ladders_of(doc, singles)
    if locked:
        story.append(Paragraph("W grze — wydrukowane przed startem meczu", h2))
        rows: list[list[Any]] = [[Paragraph(h, small) for h in (
            "mecz", "rynek", "linia", "pewność", "kurs", "wydruk")
            + (("wynik",) if results is not None else ())]]
        header_rows: list[int] = []
        headed: set[int] = set()
        locked_paint: list[tuple[int, str]] = []
        for leg in locked:
            subj = f" ({leg['subject']})" if leg.get("subject") else ""
            lno = ladder_of.get(id(leg))
            if lno is not None and lno not in headed:
                headed.add(lno)
                header_rows.append(len(rows))
                rows.append([Paragraph(ladder_header(ladder_docs[lno]), small)]
                            + [""] * (5 if results is None else 6))
            subj += ladder_marker(lno)
            entry = cr.of_leg(results, leg)
            if results is not None:
                locked_paint.append((len(rows), entry["status"]))
            rows.append([
                Paragraph(f"{escape(str(leg.get('match', '')))}<br/><font size=6.5>"
                          f"{str(leg.get('kickoff_utc') or '')[11:16]}Z</font>"
                          + score_note(entry), small),
                Paragraph(market_cell(leg, ladder_marker(lno),
                                      f"{leg.get('market')}{escape(subj)}"), small),
                Paragraph(line_cell(leg), small),
                Paragraph(f"{leg['confidence']:.3f}", small),
                Paragraph(f"{leg.get('offered_odds')}", small),
                Paragraph(str(leg.get("printed_at_utc") or "")[11:16] + "Z", small),
            ] + ([Paragraph(result_cell(leg, entry), small)]
                 if results is not None else []))
        widths = ([50*mm, 52*mm, 16*mm, 18*mm, 16*mm, 18*mm] if results is None
                  else [40*mm, 42*mm, 14*mm, 16*mm, 12*mm, 14*mm, 36*mm])
        story.append(paint_results(table_with_headers(
            _table(rows, widths), header_rows), locked_paint))
        story.append(Spacer(1, 6))

    story.append(Paragraph("Pozycje", h2))
    if not fresh:
        story.append(Paragraph("Dziś żadna noga nie przeszła filtrów.", body))
    else:
        rows = [[Paragraph(h, small) for h in (
            "#", "mecz", "rynek", "linia", "pewność", "model", "kurs", "x",
            "marża", "próbka") + (("wynik",) if results is not None else ())]]
        pos_paint: list[tuple[int, str]] = []
        seen_block: set[int] = set()
        # Rungs of one ladder are one claim bought several times (the
        # verifier, 10-05: 53 such ladders, unmarked): each ladder gets a
        # header row before its first rung, and every rung its number.
        pos_headers: list[int] = []
        pos_headed: set[int] = set()
        for leg in fresh:
            first = int(leg.get("block") or 0) not in seen_block
            seen_block.add(int(leg.get("block") or 0))
            match_cell = ""
            if first:
                blk = blocks.get(int(leg.get("block") or 0), {})
                refs = blk.get("builders") or []
                match_cell = (
                    f"<b>{escape(str(leg.get('match', '')))}</b><br/><font size=6.5>"
                    f"{str(leg.get('kickoff_utc') or '')[11:16]}Z"
                    + (f" • {escape(str(leg['sport']))}"
                       if leg.get("sport") not in (None, "football") else "")
                    + "</font>"
                    + (f"<br/><font size=6.5 color='#1f5fa8'>Bet Builder: "
                       f"{', '.join(refs)} (osobna strona)</font>" if refs else "")
                )
                mk = leg.get("makeup_of")
                if mk:
                    match_cell += (
                        f"<br/><font size=6.5 color='#b25b00'>mecz zaległy za "
                        f"{mk['sofascore_event_id']} (przełożony "
                        f"{str(mk.get('postponed_utc') or '?')[:10]})</font>")
            entry = cr.of_leg(results, leg)
            if first:
                match_cell += score_note(entry)
            if results is None and started_at_render(leg, now):
                match_cell += ("<br/><font size=6.5 color='#b23b3b'><b>start przed "
                               "renderem PDF</b></font>")
            match_cell += (watch_label(leg) + context_label(leg)
                           + stakes_label(leg) + price_gap_label(leg)
                           + peer_label(leg))
            subj = f" ({leg['subject']})" if leg.get("subject") else ""
            lno = ladder_of.get(id(leg))
            if lno is not None and lno not in pos_headed:
                pos_headed.add(lno)
                pos_headers.append(len(rows))
                rows.append([Paragraph(ladder_header(ladder_docs[lno]), small)]
                            + [""] * (9 if results is None else 10))
            subj += ladder_marker(lno)
            model = leg.get("forecast_p")
            margin = leg.get("overround")
            rows.append([
                Paragraph(str(leg.get("position")), small),
                Paragraph(match_cell, small),
                Paragraph(market_cell(leg, ladder_marker(lno),
                                      f"{leg.get('market')}{escape(subj)}"), small),
                Paragraph(line_cell(leg), small),
                Paragraph(f"<b>{leg['confidence']:.3f}</b>", small),
                Paragraph("—" if model is None else f"{float(model):.3f}", small),
                Paragraph(f"<b>{leg.get('offered_odds')}</b>", small),
                Paragraph(f"{leg_x(leg):.2f}", small),
                Paragraph(("1-str." if leg.get("one_sided_market") else "—")
                          if margin is None else f"{float(margin):.1%}", small),
                Paragraph(single_sample(leg), small),
            ] + ([Paragraph(result_cell(leg, entry), small)]
                 if results is not None else []))
            if results is not None:
                pos_paint.append((len(rows) - 1, entry["status"]))
        widths = ([10*mm, 36*mm, 44*mm, 13*mm, 16*mm, 13*mm, 12*mm, 11*mm, 13*mm,
                   14*mm] if results is None else
                  [9*mm, 28*mm, 33*mm, 11*mm, 13*mm, 11*mm, 10*mm, 9*mm, 11*mm,
                   12*mm, 35*mm])
        story.append(paint_results(table_with_headers(_table(rows, widths),
                                                      pos_headers), pos_paint))
    # F4.3: how much of the coupon stands on one match.
    story.extend(exposure_flowables(doc, body, small, h2))
    # F4.4: the builders refused for want of a screen price, to price by hand.
    story.extend(refused_builder_flowables(doc, small, h2))

    for b in picks:
        story.append(PageBreak())
        block: list[Any] = []
        no = b.get("builder_no") or "B"
        block.append(Paragraph(f"Bet Builder {no}. {escape(str(b['match']))}", pick))
        b_entry = cr.of_builder(results, b)
        block.append(Paragraph(
            f"{escape(str(b.get('competition') or '—'))} • start "
            f"{str(b['kickoff_utc'])[11:16]}Z" + locked_label(b)
            + score_note(b_entry), small))
        if results is not None:
            block.append(Paragraph(
                f"<font color='{STATUS_INK[b_entry['status']]}'><b>Builder: "
                f"{escape(cr.outcome_text(b_entry))}</b></font>", body))
        block.append(Spacer(1, 3))
        rows = [[Paragraph(h, small) for h in (
            "#", "zakład", "pewność", "model", "kurs", "kalibracja")
            + (("wynik",) if results is not None else ())]]
        b_paint: list[tuple[int, str]] = []
        b_legs = {x["key"]: x for x in b_entry.get("legs") or []}
        for j, x in enumerate(b["legs"], 1):
            key = (b["sofascore_event_id"], x["market"], x["subject"],
                   x["line"], x["direction"])
            leg = legs_idx.get(key, x)
            sub = f" {x['subject']}" if x.get("subject") else ""
            model = leg.get("forecast_p")
            rows.append([
                Paragraph(str(j), small),
                Paragraph(market_cell(
                    x, "", f"<b>{x['market']}{escape(sub)}</b> {x['line']} "
                    f"{x['direction']}"), small),
                Paragraph(f"{float(leg['confidence']):.3f}", small),
                Paragraph("—" if model is None else f"{float(model):.3f}", small),
                Paragraph(f"{x['odds']}", small),
                Paragraph(f"{str(leg.get('calibrated_on', '')).replace('market:', '')}"
                          f"<br/>n={leg.get('calibration_n', '—')}", small),
            ] + ([Paragraph(result_cell(x, {
                **(b_legs.get(cr.key_of(x, b["sofascore_event_id"]))
                   or {"outcome": "PENDING", "status": cr.UNKNOWN, "actual": None}),
                "score": b_entry.get("score")}), small)]
                if results is not None else []))
            if results is not None:
                leg_st = (b_legs.get(cr.key_of(x, b["sofascore_event_id"]))
                          or {}).get("status", cr.UNKNOWN)
                b_paint.append((len(rows) - 1, leg_st))
        widths = ([7*mm, 70*mm, 18*mm, 16*mm, 16*mm, 48*mm] if results is None
                  else [7*mm, 46*mm, 14*mm, 12*mm, 11*mm, 54*mm, 36*mm])
        block.append(paint_results(_table(rows, widths), b_paint))
        block.append(Spacer(1, 4))
        # The operator, 2026-10-05: "nie wyceniaj mi ich, sam będę widział" -
        # no builder price of ours on the page (fair / after-haircut / x / EV);
        # the price is Superbet's screen. The legs' own odds above are
        # Superbet's prices of the singles, not a builder price.
        block.append(Paragraph(
            f"<b>{b['n_legs']} nogi</b> • łączne p "
            f"<b>{b['combined_probability']:.3f}</b> • kurs buildera: "
            "<b>sprawdź na ekranie Superbetu</b> (sofa nie wycenia builderów)",
            body))
        block.extend(builder_screen_note(b, body))
        block.append(Paragraph(
            "Wybrany po łącznym prawdopodobieństwie (najwyższe dla meczu). "
            "Builder 2-, 3- i 4-nogowy powstaje z jednej puli, więc najczęściej "
            "najwyższe p ma 2-nogowy. Łączne p mnoży nogi (zakłada "
            "niezależność); Superbet nie wycenia buildera iloczynem nóg.", small))
        story.append(KeepTogether(block))
    if results is not None:
        story.append(PageBreak())
        story.extend(results_summary_flowables(singles, picks, results, body,
                                                small, h2))


# The colour of a row by its result (the operator: green won, yellow not
# known, red lost; a refund is yellow and says so) and of its word.
STATUS_INK = {cr.WON: "#1b7f4b", cr.LOST: "#b23b3b", cr.REFUND: "#8a6d00",
              cr.UNKNOWN: "#8a6d00"}


def score_note(entry: dict[str, Any]) -> str:
    """The match's final score under the match name, once settled."""
    if not entry or not entry.get("score"):
        return ""
    return (f"<br/><font size=6.5 color='#1a1a1a'>wynik: "
            f"<b>{escape(str(entry['score']))}</b></font>")


def result_cell(leg: dict[str, Any], entry: dict[str, Any]) -> str:
    """What the leg said, what the market counted, and the verdict."""
    if not entry:
        return ""
    conf = leg.get("confidence")
    said = escape(cr.claim_text(leg)) + (
        "" if conf is None else f" ({float(conf):.0%})")
    return (f"<font size=6.5>typ: {said}</font><br/>"
            f"<font size=6.5>było: <b>{escape(cr.actual_text(leg, entry))}</b>"
            f"</font><br/><font color='{STATUS_INK[entry['status']]}'><b>"
            f"{escape(cr.outcome_text(entry))}</b></font>")


def paint_results(table: Table, paint: list[tuple[int, str]]) -> Table:
    """Each result row's background in its colour; the result column takes
    its width from the cells' side padding, so numbers never wrap."""
    if paint:
        table.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            *(("BACKGROUND", (0, r), (-1, r), colors.HexColor(cr.COLOURS[st]))
              for r, st in paint)]))
    return table


def _summary_pairs(
    singles: list[dict[str, Any]], results: dict[str, Any]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [(leg, cr.of_leg(results, leg)) for leg in singles]


def results_headline(singles: list[dict[str, Any]], picks: list[dict[str, Any]],
                     results: dict[str, Any]) -> str:
    """One line under the title: the coupon's result in percent."""
    s = cr.summarize(_summary_pairs(singles, results))["all"]
    return (f"<b>Wyniki (rozliczenie {escape(str(results.get('computed_at_utc'))[:16])}"
            f"Z):</b> <font color='#1b7f4b'><b>weszło {s[cr.WON]} "
            f"({cr.pct(s['share'][cr.WON])})</b></font>, "
            f"<font color='#b23b3b'><b>nie weszło {s[cr.LOST]} "
            f"({cr.pct(s['share'][cr.LOST])})</b></font>, nie wiadomo / zwrot "
            f"{s[cr.UNKNOWN] + s[cr.REFUND]} z {s['legs']} pojedynczych; "
            f"trafność rozstrzygniętych {cr.pct(s['hit_rate'])} przy średniej "
            f"pewności {cr.pct(s['mean_confidence'])}. Podsumowanie na końcu.")


def results_summary_flowables(
    singles: list[dict[str, Any]], picks: list[dict[str, Any]],
    results: dict[str, Any], body: ParagraphStyle, small: ParagraphStyle,
    h2: ParagraphStyle,
) -> list[Any]:
    """The closing page: the percent summary per sport and in all, and the
    builders' count."""
    out: list[Any] = [Paragraph("Podsumowanie wyników", h2)]
    out.append(Paragraph(
        "Każdy wiersz kuponu ma kolor wyniku: <font color='#1b7f4b'><b>zielony"
        "</b></font> weszło, <font color='#b23b3b'><b>czerwony</b></font> nie "
        "weszło, <font color='#8a6d00'><b>żółty</b></font> nie wiadomo (czeka "
        "na rozliczenie, nie rozliczono) albo zwrot (0 j.). <b>typ</b> to linia "
        "i strona nogi z jej pewnością, <b>było</b> - co faktycznie policzył "
        "rynek (przy rynkach tak/nie wynik meczu). Rozliczenie to samo co "
        "w rejestrze wyników (audit_settlement 7c): trafność liczona tylko na "
        "rozstrzygniętych nogach, jednostki płaskie po 1 j. po wydrukowanym "
        "kursie. Średnia pewność rozstrzygniętych nóg to, ile kupon "
        "przewidywał; trafność - ile faktycznie weszło.", small))
    rows: list[list[Any]] = [[Paragraph(h, small) for h in (
        "sport", "nóg", "weszło", "nie weszło", "nie wiadomo / zwrot",
        "trafność", "śr. pewność", "jedn.", "ROI")]]
    lines = cr.summary_lines(cr.summarize(_summary_pairs(singles, results)))
    for i, line in enumerate(lines):
        bold = i == len(lines) - 1
        rows.append([Paragraph(f"<b>{v}</b>" if bold else v, small) for v in (
            escape(line["name"]), line["legs"], line["won"], line["lost"],
            line["other"], line["hit"], line["conf"], line["units"],
            line["roi"])])
    out.append(_table(rows, [26*mm, 12*mm, 24*mm, 24*mm, 26*mm, 17*mm, 18*mm,
                             16*mm, 17*mm]))
    if picks:
        b = cr.builders_summary(cr.of_builder(results, p) for p in picks)
        out.append(Spacer(1, 5))
        out.append(Paragraph(
            f"<b>Bet Buildery ({len(picks)}):</b> weszło {b[cr.WON]}, nie weszło "
            f"{b[cr.LOST]}, nie wiadomo / zwrot {b[cr.UNKNOWN] + b[cr.REFUND]} "
            "(kurs buildera to ekran Superbetu - sofa go nie wycenia).", body))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
