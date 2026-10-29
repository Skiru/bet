"""Depth checks on an analyst's report (operator 2026-10-20).

merge_reads validates that a report's blocks are well formed; this module
asks whether the read behind them was made: every match with a KEEP had a
web context pass ("Kontekst (web)"), the dossier was read (or its absence
named), and no KEEP rests on a bare count ("15/18"). A context removal names
its source; every removal names a fact newer than the price (a dated
[WEB: ..., publ. ...] tag) or an artifact defect ("DEFEKT: ...") - 10-26: 19
of 24 WATCHes rested on h2h, form, the table or a model gap, which the
literature and our ledger measure as noise. Every [WEB:] tag is dated, every
match section writes its kill facts before the search (a delta section
inherits them), and a KEEP is per market family, never a match-wide null.
Every read match has a section whose heading carries its
`sofa:<id>` token (bet.sofa.analyses files the section by it). Run by
`scripts/sofa/check_analyst_report.py`, by the analyst before it returns,
and by the PostToolUse hook (`.claude/hooks/check_analyst_report.py`) on
every report written - the
findings go back to the analyst, which rewrites. Display / process only:
nothing here changes a confidence or a gate.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from bet.sofa import analyses
from bet.sofa.dossier import STYLE_POSSESSION_MIN, dossier_path, leg_metric
from bet.sofa.epochs import READ_SCOPE_DATE
from bet.sofa.price_gap import GAP

CONTEXT_MARK = re.compile(r"kontekst\s*\(web\)", re.IGNORECASE)
DOSSIER_MARK = re.compile(r"dossier", re.IGNORECASE)
BARE_COUNT = re.compile(r"^\s*\d+\s*/\s*\d+\s*[.;]?\s*$")
SOURCE_MARK = re.compile(r"\[WEB:|niepotwierdzone|opinia|dossier|UNVERIFIED", re.I)
WEB_TAG = re.compile(r"\[WEB:[^\]]*\]", re.I)
DATED = re.compile(r"publ", re.I)
DEFECT_MARK = re.compile(r"DEFEKT")
KILL_MARK = re.compile(r"fakty\s+zab[oó]jcze", re.I)
SUMMARY_MARK = re.compile(r"\*\*W skr[oó]cie", re.I)
STYLE_MARK = re.compile(r"styl gry i zestawienie", re.I)
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.M)
# The readable section (operator 2026-10-29: the reports were unreadable and
# never set a team's count against what its opponent concedes) binds reports
# of days from 2026-10-29 (operator 2026-10-29, after the E2E test: "od
# dzisiaj" - moved from 10-30 into the day, whose reads were not yet merged)
# - a process rule, never a gate.
READABLE_SECTION_DATE = "2026-10-29"
# The two rules that change a verdict (a sourced removal, no match-wide KEEP)
# bind the reports of days from the analyst audit's switch (epochs
# READ_SCOPE_DATE, 2026-10-27, operator's go 10-26) - never mid-day.
SOURCED_REMOVALS_DATE = READ_SCOPE_DATE
REPORT_DAY = re.compile(r"(\d{4}-\d{2}-\d{2})_(?:analiza|weryfikacja)")
READS_BLOCK = re.compile(r"```json reads[^\n]*\n(.*?)```", re.DOTALL)
VETOES_BLOCK = re.compile(r"```json vetoes[^\n]*\n(.*?)```", re.DOTALL)
# A market-driver WATCH (operator 2026-10-29: a style / concession signal is
# never skipped): "RYNEK: <driver>: <numbers>" carrying at least one k/n count
# read from the dossier, binding reports of days from READABLE_SECTION_DATE.
MARKET_MARK = re.compile(r"RYNEK:")
COUNT = re.compile(r"\d+\s*/\s*\d+")
# A correct value the model does not use is a note, not a defect: a
# "DEFEKT:" resting on rest, a back-to-back, form, a streak, h2h or the table
# (10-28: "DEFEKT: dossier rest_days=1.0 ... Spurs na 2. nocy") removes nothing.
FALSE_DEFECT = re.compile(
    r"rest_days|games_7d|games_14d|back[- ]to[- ]back|\bb2b\b|2\. noc|drug\w* noc|"
    r"\bform[ay]?\b|\bseri[aię]\b|\bh2h\b|\btabel|"
    # a rating one disagrees with (10-29: ~30 removals "DEFEKT: 05_sheet
    # FOOTBALL_RATING ... log strength gap") is the forbidden cross-league basis
    r"FOOTBALL_RATING|FOOTBALL_SCORE_MARKETS|strength gap|cup_strength|rating", re.I)
# The two thresholds a `RYNEK:` WATCH stands on (sofa-analysis-core, "What a
# removal's reason must name" 3), checked against the leg's own row of the
# dossier's `style.matchup` (schema >= MARKET_DOSSIER_SCHEMA) - a k/n written
# into the reason is never trusted on its own (E2E 2026-10-29: "RYNEK: h2h:
# 0/4" and a 9/10 above the confidence both merged).
MARKET_GAP = 0.25
MARKET_MIN_N = 8
MARKET_DOSSIER_SCHEMA = 3
MARKET_POSSESSION_MARKET = "corners_for"  # (b): full-match corners OVER only
MARKET_BLOCKING = ("RYNEK ZAKAZANY", "RYNEK BEZ LINII", "RYNEK BEZ DOSSIER",
                   "RYNEK BEZ WIERSZA", "RYNEK PONIŻEJ PROGU", "RYNEK INNE LICZBY")
CONTRA_ROW = re.compile(r"^\s*\|.*ZESTAWIENIE PRZECIW.*\|\s*$", re.M)
# A KEEP reason shorter than this cannot carry an expectation, a dossier fact
# and a context finding (the contract's example runs ~120 characters).
MIN_KEEP_REASON = 40


def reads_block(text: str) -> list[dict[str, Any]]:
    """The report's ```json reads array (empty when absent or malformed -
    merge_reads reports those)."""
    out: list[dict[str, Any]] = []
    for body in READS_BLOCK.findall(text):
        try:
            entries = json.loads(body)
        except ValueError:
            continue
        if isinstance(entries, list):
            out += [e for e in entries if isinstance(e, dict)]
    return out


def vetoes_block(text: str) -> list[dict[str, Any]]:
    """The report's ```json vetoes array (empty when absent or malformed)."""
    out: list[dict[str, Any]] = []
    for body in VETOES_BLOCK.findall(text):
        try:
            entries = json.loads(body)
        except ValueError:
            continue
        if isinstance(entries, list):
            out += [e for e in entries if isinstance(e, dict)]
    return out


def market_sourced(reason: str) -> bool:
    """A removal reason resting on a market driver with its numbers."""
    return bool(MARKET_MARK.search(reason) and COUNT.search(reason))


def fact_sourced(reason: str) -> bool:
    """A removal reason naming a dated web fact or an artifact defect (a
    "defect" that is a schedule / form / h2h fact does not count)."""
    defect = DEFECT_MARK.search(reason)
    real_defect = bool(defect and not FALSE_DEFECT.search(reason[defect.start():]))
    return real_defect or any(DATED.search(t) for t in WEB_TAG.findall(reason))


def report_kind(name: str) -> dict[str, Any]:
    """What a report file is: `verifier` for "<d>_weryfikacja*", else the
    analyst's `sport` ("<d>_analiza_football_2.md" -> football; None when
    the name does not say)."""
    if "_weryfikacja" in name:
        return {"verifier": True, "sport": None}
    m = re.search(r"_analiza_([a-z0-9]+)", name)
    return {"verifier": False, "sport": m.group(1) if m else None}


def report_run(path: Path) -> Path | None:
    """The run a report sits in (runs/sofa/<d>/<d>_analiza_*.md: the
    directory holding 11_coupon.json); None for a report written elsewhere."""
    parent = path.resolve().parent
    return parent if (parent / "11_coupon.json").exists() else None


def report_day(name: str) -> str | None:
    """The day a report file is of ("2026-10-27_analiza_football.md")."""
    m = REPORT_DAY.search(name)
    return m.group(1) if m else None


def findings(
    text: str, day: str | None = None, *, verifier: bool = False,
    sport: str | None = None,
    dossiers: Mapping[int, Mapping[str, Any] | None] | None = None,
) -> list[str]:
    """Every depth problem of one report, in Polish (the analyst reads them).
    `day`: the report's day; before SOURCED_REMOVALS_DATE the verdict rules
    of the 10-26 audit are not applied (None: they are). `verifier`: the
    verifier's report (`_weryfikacja_`) - the same removal and summary rules,
    no context pass, kill facts or style table (it rebuilds legs, it does not
    read matches). `sport`: the analyst's sport (`report_kind`); the style
    table binds football reports only (None: treated as football).
    `dossiers`: {event id: dossier or None} (`load_dossiers`) - with it every
    `RYNEK:` WATCH is checked against its leg's `style.matchup` row
    (`market_findings`); merge_reads always passes it."""
    sourced = day is None or day >= SOURCED_REMOVALS_DATE
    readable = day is None or day >= READABLE_SECTION_DATE
    reads = reads_block(text)
    out: list[str] = []
    if dossiers is not None and readable and sport in (None, "football"):
        out += market_findings(reads, dossiers)
    if readable:
        for v in vetoes_block(text):
            reason = str(v.get("reason") or "")
            if not fact_sourced(reason):
                out.append(
                    f"WETO BEZ FAKTU: {v.get('sofascore_event_id')} "
                    f"{v.get('market')}: weto musi nazwać fakt nowszy niż cena "
                    "([WEB: domena, publ. <data>, fetched]) albo defekt artefaktu "
                    "(„DEFEKT: …”, nie odpoczynek / forma / h2h); czynnik rynku "
                    "(„RYNEK: …”) daje najwyżej WATCH w odczycie, nigdy weto")
    if not reads:
        return out
    tags = WEB_TAG.findall(text)
    undated = [t for t in tags if not DATED.search(t)]
    if undated:
        out.append(
            f"TAG WEB BEZ DATY: {len(undated)} z {len(tags)} tagów bez „publ. <data>” "
            f"(np. {undated[0][:70]}) - fakt nowszy niż cena trzeba datować; "
            "nieznana data = „publ. ?”"
        )
    if verifier:
        return (out + _unheaded(text, reads)
                + _verdicts(reads, sourced, readable, sport)
                + _summaries(text, reads, readable, summary_only=True))
    keep_events = {
        r.get("sofascore_event_id") for r in reads if r.get("verdict") == "KEEP"
    }
    contexts = len(CONTEXT_MARK.findall(text))
    if contexts < len(keep_events):
        out.append(
            f"KONTEKST: {len(keep_events)} meczów z KEEP, a sekcji „Kontekst (web)” "
            f"{contexts} - każdy nierozpoczęty mecz dostaje przegląd kontekstu "
            "(newsy, pogoda, nastroje / kulisy, stawka, opinie), także "
            "„nic istotnego dla tych nóg”"
        )
    if not DOSSIER_MARK.search(text):
        out.append(
            "DOSSIER: raport nie wspomina dossier meczu - przeczytaj plik z pola "
            "`dossier` nogi albo napisz „brak dossier” w Czego zabrakło"
        )
    out += _unheaded(text, reads)
    sections = analyses.split_sections(text)
    read_ids = {r.get("sofascore_event_id") for r in reads}
    no_kill = sorted({
        s["event_id"] for s in sections
        if s["event_id"] in read_ids and not s["delta"]
        and not KILL_MARK.search(s["markdown"])})
    if no_kill:
        out.append(
            "FAKTY ZABÓJCZE: mecze " + ", ".join(str(e) for e in no_kill)
            + " - sekcja bez linii „**Fakty zabójcze (przed siecią):**” (co "
            "złamałoby te nogi, zapisane przed wyszukiwaniem)"
        )
    out += _summaries(text, reads, readable,
                      summary_only=sport not in (None, "football"))
    return out + _verdicts(reads, sourced, readable, sport)


def _unheaded(text: str, reads: list[dict[str, Any]]) -> list[str]:
    """Every read match has a section headed `sofa:<id>` (analyses.json files
    the section by it)."""
    headed = {s["event_id"] for s in analyses.split_sections(text)}
    unheaded = sorted({
        int(e) for e in (r.get("sofascore_event_id") for r in reads)
        if isinstance(e, int) and e not in headed})
    if not unheaded:
        return []
    return [
        "SEKCJA BEZ TOKENU: mecze " + ", ".join(str(e) for e in unheaded)
        + " - nagłówek sekcji meczu musi nieść `sofa:<sofascore_event_id>` "
        "(„### Gospodarz – Gość — rozgrywki · sofa:123”), inaczej analiza nie "
        "trafi przy nogach do HTML / PDF"]


def _summaries(
    text: str, reads: list[dict[str, Any]], readable: bool, *,
    summary_only: bool = False,
) -> list[str]:
    """W SKRÓCIE on every read match's section (a delta too: it is what the
    operator reads first) and, for a football analyst, the style table of a
    count-market read (`summary_only`: the verifier, the other sports)."""
    out: list[str] = []
    if not readable:
        return out
    read_ids = {r.get("sofascore_event_id") for r in reads}
    sections = [s for s in analyses.split_sections(text) if s["event_id"] in read_ids]
    no_summary = sorted({s["event_id"] for s in sections
                         if not SUMMARY_MARK.search(s["markdown"])})
    if no_summary:
        out.append(
            "W SKRÓCIE: mecze " + ", ".join(str(e) for e in no_summary)
            + " - sekcja (także delta) zaczyna się od „**W skrócie:**” (2-3 zdania "
            "prostym językiem: faworyt, jak ułoży się mecz, co decyduje o nogach)")
    if summary_only:
        return out
    count_legs = {r.get("sofascore_event_id") for r in reads
                  if leg_metric(str(r.get("market"))) is not None}
    no_style = sorted({
        s["event_id"] for s in sections if s["event_id"] in count_legs
        and not s["delta"]
        and not (STYLE_MARK.search(s["markdown"])
                 and TABLE_ROW.search(s["markdown"]))})
    # a rung the table marks PRZECIW is read on its own (a line, not a
    # family-wide KEEP): WATCH "RYNEK:" or a KEEP naming what changes tonight
    lined = {r.get("sofascore_event_id") for r in reads if r.get("line") is not None}
    contra = sorted({s["event_id"] for s in sections
                     if CONTRA_ROW.search(s["markdown"])
                     and s["event_id"] not in lined})
    if contra:
        out.append(
            "PRZECIW BEZ ODCZYTU: mecze " + ", ".join(str(e) for e in contra)
            + " - wiersz „ZESTAWIENIE PRZECIW” wymaga odczytu tej nogi z linią "
            "(WATCH „RYNEK: …” albo KEEP z faktem, który dziś zmienia, kto ma piłkę)")
    if no_style:
        out.append(
            "ZESTAWIENIE: mecze " + ", ".join(str(e) for e in no_style)
            + " - nogi rynków liczbowych (gole, rożne, kartki, strzały, "
            "celne, spalone, obrony, „każda z drużyn”) bez akapitu „**Styl gry "
            "i zestawienie.**” i tabeli nóg (własne / rywal pozwolił / mecze "
            "stron / liga z bloku `style.matchup` dossier)")
    return out


def _verdicts(
    reads: list[dict[str, Any]], sourced: bool, readable: bool,
    sport: str | None = None,
) -> list[str]:
    """Each read's reason: a KEEP argued per family, a removal sourced. A
    `RYNEK:` removal is football's (its thresholds read style.matchup; a
    tennis / measured-sport driver's numbers are a note)."""
    out: list[str] = []
    market_ok = readable and sport in (None, "football")
    for r in reads:
        reason = str(r.get("reason") or "")
        label = (
            f"{r.get('sofascore_event_id')} {r.get('market')} {r.get('subject') or ''} "
            f"{r.get('line')} {r.get('direction')}"
        ).replace("  ", " ")
        if r.get("verdict") == "KEEP":
            if sourced and r.get("market") is None:
                out.append(
                    f"KEEP ZBIORCZY: {label}: KEEP z `market: null` - jeden odczyt "
                    "na rodzinę (rynek, kierunek) z oczekiwaniem wobec jej linii"
                )
            if BARE_COUNT.match(reason) or len(reason) < MIN_KEEP_REASON:
                out.append(
                    f"KEEP BEZ UZASADNIENIA: {label}: „{reason}” - podaj oczekiwanie "
                    "w jednostkach rynku, fakt z dossier i ustalenie z kontekstu"
                )
        elif (sourced and market_ok and not fact_sourced(reason)
              and market_sourced(reason)):
            if r.get("verdict") != "WATCH":
                out.append(
                    f"RYNEK TYLKO WATCH: {label}: {r.get('verdict')} oparty na "
                    "czynniku rynku - taki powód daje najwyżej WATCH")
            elif r.get("context") != "MARKET":
                out.append(
                    f"RYNEK BEZ TAGU: {label}: WATCH z „RYNEK:” wymaga "
                    "`context: \"MARKET\"` (rozliczany osobno w księdze)")
        elif sourced and not fact_sourced(reason):
            out.append(
                f"USUNIĘCIE BEZ FAKTU: {label}: {r.get('verdict')} - powód musi "
                "nazwać fakt nowszy niż cena ([WEB: domena, publ. <data>, fetched]), "
                "defekt artefaktu („DEFEKT: …”)"
                + (" albo - dla WATCH - czynnik rynku z liczbami k/n z dossier "
                   "(„RYNEK: <czynnik>: …”, `context: \"MARKET\"`)" if market_ok
                   else "")
                + (" (DEFEKT to wartość artefaktu błędna na dziś - tożsamość, "
                   "zakres, nawierzchnia, format, inna kadra; poprawny odpoczynek, "
                   "forma czy h2h to notatka)" if DEFECT_MARK.search(reason) else "")
                + "; h2h, forma, seria, tabela, luka model-próbka, price_gap ani "
                "most ratingu między ligami nie zdejmują nogi"
            )
        elif r.get("context") and not SOURCE_MARK.search(reason):
            out.append(
                f"ŹRÓDŁO: {label}: {r.get('verdict')} z tagiem {r.get('context')} "
                "bez [WEB: domena, publ., fetched] / „niepotwierdzone” / „opinia”"
            )
    return out


def market_reads(reads: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The reads whose removal rests on a market driver (`RYNEK:`, no dated
    web fact or real defect beside it)."""
    return [r for r in reads if r.get("verdict") in ("WATCH", "NO_BET")
            and MARKET_MARK.search(str(r.get("reason") or ""))
            and not fact_sourced(str(r.get("reason") or ""))]


def load_dossiers(
    run: Path, event_ids: Iterable[Any],
    read_set_legs: Iterable[Mapping[str, Any]] = (),
) -> dict[int, dict[str, Any] | None]:
    """{event id: football dossier or None}: the path a read-set leg names
    (`dossier`, a scratch dossier dir included) first, else
    `<run>/dossier/football_<id>.json`. Unreadable = None, never a guess."""
    named: dict[int, Path] = {}
    for leg in read_set_legs:
        eid, path = leg.get("sofascore_event_id"), leg.get("dossier")
        if isinstance(eid, int) and isinstance(path, str) and path:
            named.setdefault(eid, Path(path))
    out: dict[int, dict[str, Any] | None] = {}
    for raw in event_ids:
        if not isinstance(raw, int):
            continue
        path = named.get(raw) or dossier_path(run, "football", raw)
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = None
        out[raw] = doc if isinstance(doc, dict) else None
    return out


def _share(cell: object) -> tuple[float, int] | None:
    m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", str(cell or ""))
    if not m or int(m.group(2)) == 0:
        return None
    return int(m.group(1)) / int(m.group(2)), int(m.group(2))


def _row_for(
    doc: Mapping[str, Any], read: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """The leg's own `style.matchup` row (market, subject, line, direction)."""
    rows: list[Mapping[str, Any]] = (doc.get("style") or {}).get("matchup") or []
    for row in rows:
        if (row.get("market") == read.get("market")
                and str(row.get("subject") or "").casefold()
                == str(read.get("subject") or "").casefold()
                and row.get("direction") == read.get("direction")
                and isinstance(row.get("line"), int | float)
                and abs(float(row["line"]) - float(read["line"])) < 1e-9):
            return row
    return None


def _possession_side(doc: Mapping[str, Any], team: object) -> str | None:
    for side in ("home", "away"):
        if team and (doc.get("sides") or {}).get(side, {}).get("name") == team:
            return side
    return None


def _win_prices(doc: Mapping[str, Any]) -> dict[str, float]:
    """Superbet's home / away win prices from the dossier's ladder (the
    double chance X2 "no" is the home win, 1X "no" the away win)."""
    out: dict[str, float] = {}
    for rung in (doc.get("market") or {}).get("rungs_of_leg_markets") or []:
        if rung.get("market") != "double_chance":
            continue
        side = {"X2": "home", "1X": "away"}.get(str(rung.get("subject")))
        price = rung.get("under_odds")
        if side and isinstance(price, int | float):
            out[side] = float(price)
    return out


def market_threshold(
    doc: Mapping[str, Any], row: Mapping[str, Any],
) -> tuple[bool, list[str], str]:
    """Whether the row clears threshold (a) or (b), the dossier's k/n the
    reason must cite (empty for (b)) and what was computed (Polish)."""
    implied = row.get("implied")
    ref = (float(implied) + GAP if row.get("price_gap") and isinstance(
        implied, int | float) else float(row.get("confidence") or 0.0))
    bar = ref - MARKET_GAP
    sides = row.get("sides") or []
    league = row.get("league") or {}
    basis = " (1/kurs + 0.03, price_gap)" if row.get("price_gap") else " (pewność)"
    notes = [f"odniesienie {ref:.3f}{basis}, próg <= {bar:.3f}, n >= {MARKET_MIN_N}"]
    passed, cited = False, []
    if sides and all("opponent_conceded" in c for c in sides) and not row.get("joint"):
        cell = sides[0]
        got = _share(cell.get("opponent_conceded"))
        notes.append(f"{cell.get('opponent')} oddaje {cell.get('opponent_conceded')}")
        if got and got[1] >= MARKET_MIN_N and got[0] <= bar + 1e-9:
            passed, cited = True, [str(cell["opponent_conceded"])]
        if (row.get("market") == MARKET_POSSESSION_MARKET
                and row.get("direction") == "OVER"):
            ok_b, note_b = _threshold_b(doc, row, cell)
            notes.append(note_b)
            if ok_b and not passed:
                passed, cited = True, []
    else:
        games = [_share(c.get("games")) for c in sides]
        share = league.get("share")
        notes.append(" · ".join(f"mecze {c.get('team')} {c.get('games')}"
                                for c in sides)
                     + f" · liga {share} (n={league.get('n')})")
        if (len(games) == 2 and all(g and g[1] >= MARKET_MIN_N and g[0] <= bar + 1e-9
                                    for g in games)
                and isinstance(share, int | float) and share <= bar + 1e-9
                and int(league.get("n") or 0) >= MARKET_MIN_N):
            passed, cited = True, [str(c["games"]) for c in sides]
    return passed, cited, "; ".join(notes)


def _threshold_b(
    doc: Mapping[str, Any], row: Mapping[str, Any], cell: Mapping[str, Any],
) -> tuple[bool, str]:
    """(b): corners OVER on the side that will not have the ball - possession
    mean < 50 and the longer win price (a cup tie: the price alone) - whose
    corners at < 50 % possession average under the line on >= 4 games."""
    side = _possession_side(doc, cell.get("team"))
    if side is None:
        return False, "(b): strona nogi nie znaleziona w dossier"
    style = (doc.get("style") or {}).get(side) or {}
    possession = (style.get("means") or {}).get("possession")
    split = (style.get("corners_by_own_possession") or {}).get(
        "posiadanie_ponizej_50") or {}
    prices = _win_prices(doc)
    other = "away" if side == "home" else "home"
    longer = (prices[side] > prices[other]
              if side in prices and other in prices else None)
    cup = (doc.get("header") or {}).get("competition") != (
        (doc.get("style") or {}).get("league") or {}).get("competition")
    no_ball = (longer is True and cup) or (
        isinstance(possession, int | float) and possession < 50 and longer is not False)
    n, mean = int(split.get("n") or 0), split.get("srednia")
    line = float(row["line"])
    ok = bool(no_ball and n >= STYLE_POSSESSION_MIN
              and isinstance(mean, int | float) and mean < line)
    return ok, (f"(b): posiadanie {possession}, kurs na wygraną {prices.get(side)} vs "
                f"{prices.get(other)}, rożne przy posiadaniu < 50: średnia {mean} "
                f"(n={n}) wobec linii {line}")


def market_findings(
    reads: Iterable[Mapping[str, Any]],
    dossiers: Mapping[int, Mapping[str, Any] | None],
) -> list[str]:
    """Every `RYNEK:` removal checked against the dossier: no forbidden
    basis after the mark, a line, the leg's own `style.matchup` row, threshold
    (a) or (b) cleared and the reason citing the dossier's own k/n."""
    out: list[str] = []
    for r in market_reads(reads):
        reason = str(r.get("reason") or "")
        label = (f"{r.get('sofascore_event_id')} {r.get('market')} "
                 f"{r.get('subject') or ''} {r.get('line')} {r.get('direction')}"
                 ).replace("  ", " ")
        mark = MARKET_MARK.search(reason)
        after = reason[mark.end():] if mark else reason
        if FALSE_DEFECT.search(after):
            out.append(
                f"RYNEK ZAKAZANY: {label}: „RYNEK:” na h2h / formie / serii / "
                "tabeli / odpoczynku / ratingu - to notatka, nie czynnik rynku "
                "(czynnik to wiersz `style.matchup` dossier albo rożne przy "
                "posiadaniu < 50)")
            continue
        if not isinstance(r.get("line"), int | float):
            out.append(
                f"RYNEK BEZ LINII: {label}: WATCH „RYNEK:” dotyczy jednej nogi z "
                "linią (próg liczy się dla linii), nigdy całej rodziny")
            continue
        eid = r.get("sofascore_event_id")
        doc = dossiers.get(eid) if isinstance(eid, int) else None
        if not doc or int(doc.get("schema") or 0) < MARKET_DOSSIER_SCHEMA:
            out.append(
                f"RYNEK BEZ DOSSIER: {label}: brak dossier piłkarskiego meczu w "
                f"schemacie >= {MARKET_DOSSIER_SCHEMA} - przebuduj go "
                "(`read_set.py` / `build_slip.py`); bez wiersza `style.matchup` "
                "„RYNEK:” niczego nie zdejmuje")
            continue
        row = _row_for(doc, r)
        if row is None:
            out.append(
                f"RYNEK BEZ WIERSZA: {label}: dossier nie ma wiersza "
                "`style.matchup` tej nogi (rynek, strona, linia, kierunek) - "
                "„RYNEK:” stoi tylko na liczbach z dossier")
            continue
        passed, cited, computed = market_threshold(doc, row)
        if not passed:
            out.append(
                f"RYNEK PONIŻEJ PROGU: {label}: {computed} - ani próg (a), ani "
                "(b) nie zachodzi; kod (próbka, MODEL_ABOVE_OWN_SAMPLE) już "
                "zdecydował - zapisz to jako notatkę i KEEP")
            continue
        compact = re.sub(r"\s+", "", reason)
        if cited and not any(c.replace(" ", "") in compact for c in cited):
            out.append(
                f"RYNEK INNE LICZBY: {label}: powód nie cytuje k/n z dossier "
                f"({' / '.join(cited)}) - przepisz liczby z `style.matchup`, "
                "nie licz ich sam")
    return out
