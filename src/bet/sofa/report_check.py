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
from typing import Any

from bet.sofa import analyses
from bet.sofa.epochs import READ_SCOPE_DATE

CONTEXT_MARK = re.compile(r"kontekst\s*\(web\)", re.IGNORECASE)
DOSSIER_MARK = re.compile(r"dossier", re.IGNORECASE)
BARE_COUNT = re.compile(r"^\s*\d+\s*/\s*\d+\s*[.;]?\s*$")
SOURCE_MARK = re.compile(r"\[WEB:|niepotwierdzone|opinia|dossier|UNVERIFIED", re.I)
WEB_TAG = re.compile(r"\[WEB:[^\]]*\]", re.I)
DATED = re.compile(r"publ", re.I)
DEFECT_MARK = re.compile(r"DEFEKT")
KILL_MARK = re.compile(r"fakty\s+zab[oó]jcze", re.I)
# The two rules that change a verdict (a sourced removal, no match-wide KEEP)
# bind the reports of days from the analyst audit's switch (epochs
# READ_SCOPE_DATE, 2026-10-27, operator's go 10-26) - never mid-day.
SOURCED_REMOVALS_DATE = READ_SCOPE_DATE
REPORT_DAY = re.compile(r"(\d{4}-\d{2}-\d{2})_(?:analiza|weryfikacja)")
READS_BLOCK = re.compile(r"```json reads[^\n]*\n(.*?)```", re.DOTALL)
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


def report_day(name: str) -> str | None:
    """The day a report file is of ("2026-10-27_analiza_football.md")."""
    m = REPORT_DAY.search(name)
    return m.group(1) if m else None


def findings(text: str, day: str | None = None) -> list[str]:
    """Every depth problem of one report, in Polish (the analyst reads them).
    `day`: the report's day; before SOURCED_REMOVALS_DATE the verdict rules
    of the 10-26 audit are not applied (None: they are)."""
    sourced = day is None or day >= SOURCED_REMOVALS_DATE
    reads = reads_block(text)
    out: list[str] = []
    if not reads:
        return out
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
    # a match section's heading names its match by token, read exactly as
    # bet.sofa.analyses files it ("### Dewa – Persijap — Liga 1 · sofa:1527")
    sections = analyses.split_sections(text)
    headed = {s["event_id"] for s in sections}
    unheaded = sorted({
        int(e) for e in (r.get("sofascore_event_id") for r in reads)
        if isinstance(e, int) and e not in headed})
    if unheaded:
        out.append(
            "SEKCJA BEZ TOKENU: mecze " + ", ".join(str(e) for e in unheaded)
            + " - nagłówek sekcji meczu musi nieść `sofa:<sofascore_event_id>` "
            "(„### Gospodarz – Gość — rozgrywki · sofa:123”), inaczej analiza nie "
            "trafi przy nogach do HTML / PDF"
        )
    tags = WEB_TAG.findall(text)
    undated = [t for t in tags if not DATED.search(t)]
    if undated:
        out.append(
            f"TAG WEB BEZ DATY: {len(undated)} z {len(tags)} tagów bez „publ. <data>” "
            f"(np. {undated[0][:70]}) - fakt nowszy niż cena trzeba datować; "
            "nieznana data = „publ. ?”"
        )
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
        elif sourced and not (DEFECT_MARK.search(reason) or any(
                DATED.search(t) for t in WEB_TAG.findall(reason))):
            out.append(
                f"USUNIĘCIE BEZ FAKTU: {label}: {r.get('verdict')} - powód musi "
                "nazwać fakt nowszy niż cena ([WEB: domena, publ. <data>, fetched]) "
                "albo defekt artefaktu („DEFEKT: …”); h2h, forma, seria, tabela, "
                "luka model-próbka, price_gap ani most ratingu między ligami nie "
                "zdejmują nogi"
            )
        elif r.get("context") and not SOURCE_MARK.search(reason):
            out.append(
                f"ŹRÓDŁO: {label}: {r.get('verdict')} z tagiem {r.get('context')} "
                "bez [WEB: domena, publ., fetched] / „niepotwierdzone” / „opinia”"
            )
    return out
