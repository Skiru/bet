"""Depth checks on an analyst's report (operator 2026-10-20).

merge_reads validates that a report's blocks are well formed; this module
asks whether the read behind them was made: every match with a KEEP had a
web context pass ("Kontekst (web)"), the dossier was read (or its absence
named), and no KEEP rests on a bare count ("15/18"). A context removal names
its source. Run by `scripts/sofa/check_analyst_report.py`, by the analyst
before it returns, and by the PostToolUse hook
(`.claude/hooks/check_analyst_report.py`) on every report written - the
findings go back to the analyst, which rewrites. Display / process only:
nothing here changes a confidence or a gate.
"""

from __future__ import annotations

import json
import re
from typing import Any

CONTEXT_MARK = re.compile(r"kontekst\s*\(web\)", re.IGNORECASE)
DOSSIER_MARK = re.compile(r"dossier", re.IGNORECASE)
BARE_COUNT = re.compile(r"^\s*\d+\s*/\s*\d+\s*[.;]?\s*$")
SOURCE_MARK = re.compile(r"\[WEB:|niepotwierdzone|opinia|dossier|UNVERIFIED", re.I)
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


def findings(text: str) -> list[str]:
    """Every depth problem of one report, in Polish (the analyst reads them)."""
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
    for r in reads:
        reason = str(r.get("reason") or "")
        label = (
            f"{r.get('sofascore_event_id')} {r.get('market')} {r.get('subject') or ''} "
            f"{r.get('line')} {r.get('direction')}"
        ).replace("  ", " ")
        if r.get("verdict") == "KEEP":
            if BARE_COUNT.match(reason) or len(reason) < MIN_KEEP_REASON:
                out.append(
                    f"KEEP BEZ UZASADNIENIA: {label}: „{reason}” - podaj oczekiwanie "
                    "w jednostkach rynku, fakt z dossier i ustalenie z kontekstu"
                )
        elif r.get("context") and not SOURCE_MARK.search(reason):
            out.append(
                f"ŹRÓDŁO: {label}: {r.get('verdict')} z tagiem {r.get('context')} "
                "bez [WEB: domena, publ., fetched] / „niepotwierdzone” / „opinia”"
            )
    return out
