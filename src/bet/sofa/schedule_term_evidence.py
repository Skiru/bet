"""Line evidence of the schedule term's keys at the CORRECTED p
(epochs.SCHEDULE_TERM; plan step 28 of
docs/sofa/evidence/kontekst_terminarza_2026-11-08/r3_final_review.md).

From the switch SHEET prices the rows of ``epochs.SCHEDULE_TERM_MARKETS`` on
the pure rating goals centres x exp(t) (bet.sofa.schedule_term). Their
curves are refitted on that p, so their settled Superbet lines must be read
at it too - the pattern of the tennis point model
(tennis_point_curves.evidence_p) and the volleyball rally model
(vb_point_pricer.BACKFILL):

* a settled sheet row of a day before the switch's first whole day reads the
  corrected p of ``BACKFILL["sheet"]`` (scripts/sofa/backfill_schedule_term_p.py:
  the row's own p_central plus the term's move of the same estimator on the
  row's noted pure centres, the term read as of the kick-off with SHEET's
  functions, ``schedule_term.ReplayTerms``); a row the table does not hold is
  no evidence (never the uncorrected p);
* a row of a day from the switch on reads its own p_central (its sheet priced
  it corrected);
* the simulator's backfilled Superbet lines (football_sim_curves.BACKFILL,
  before the simulator's own settled rows) read ``BACKFILL["sim_lines"]``.

The four simulator 0.60-floor keys (epochs.SCHEDULE_TERM_FLOOR_EXCLUDED) and
every other key are out of scope: their rows are read as before. fit_line_
evidence.py merges only the in-scope keys' entries (keys and bands); every
pooled number (sport offsets, price-gap pool, design effect) stays the fit of
the rows as stored, so no out-of-scope key moves. Off (the --before day
before the switch) nothing is read.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa import epochs

SPORT = "football"
BACKFILL = Path(__file__).resolve().parents[3] / "data" / "line_evidence" / (
    "schedule_term_p.json.gz")
SCHEMA = 1


def markets() -> frozenset[str]:
    """Every key the term corrects (the floor keys are not among them)."""
    return epochs.SCHEDULE_TERM_MARKETS


def sheet_markets() -> frozenset[str]:
    """The in-scope keys whose evidence is the sheet rows alone - the
    simulator's keys are read through football_sim_curves' own path."""
    return epochs.SCHEDULE_TERM_MARKETS - epochs.FOOTBALL_SIM_MARKETS


def sim_markets() -> frozenset[str]:
    return epochs.SCHEDULE_TERM_MARKETS & epochs.FOOTBALL_SIM_MARKETS


def first_whole_day(switch: datetime | None = None) -> str | None:
    """The first day whose sheet rows are all corrected: the switch's day
    when it starts at 00:00Z, else the next (a mixed day's rows read the
    backfill)."""
    s = epochs.SCHEDULE_TERM_FROM_UTC if switch is None else switch
    if s is None:
        return None
    if (s.hour, s.minute, s.second, s.microsecond) == (0, 0, 0, 0):
        return s.strftime("%Y-%m-%d")
    return (s + timedelta(days=1)).strftime("%Y-%m-%d")


def sheet_key(day: str, event_id: object, market: str, subject: object,
              line: object, direction: str) -> str:
    return (f"{day}|{int(str(event_id))}|{market}|{subject or ''}|"
            f"{float(str(line)):g}|{direction}")


def sim_line_key(day: str, event_id: object, market: str, subject: object,
                 direction: str) -> str:
    return f"{day}|{int(str(event_id))}|{market}|{subject or ''}|{direction}"


@dataclass(frozen=True)
class Backfill:
    sheet: Mapping[str, float] = field(default_factory=dict)
    sim_lines: Mapping[str, float] = field(default_factory=dict)
    meta: Mapping[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.sheet) + len(self.sim_lines)


def read_doc(path: Path | None = None) -> dict[str, Any] | None:
    p = path if path is not None else BACKFILL
    if not p.exists():
        return None
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        doc: dict[str, Any] = json.load(fh)
    if int(doc.get("schema") or 0) != SCHEMA:
        raise ValueError(f"{p}: schema {doc.get('schema')!r}, expected {SCHEMA}")
    return doc


def load_backfill(path: Path | None = None) -> Backfill | None:
    """`BACKFILL`, or None when absent (the caller keeps the rows as stored
    and says so)."""
    doc = read_doc(path)
    if doc is None:
        return None
    return Backfill(
        sheet={str(k): float(v) for k, v in (doc.get("sheet") or {}).items()},
        sim_lines={str(k): float(v)
                   for k, v in (doc.get("sim_lines") or {}).items()},
        meta={k: v for k, v in doc.items() if k not in ("sheet", "sim_lines")})


def evidence_p(row: Mapping[str, Any], day: str, backfill: Backfill,
               switch_day: str | None = None,
               scope: frozenset[str] | None = None) -> tuple[bool, float | None]:
    """(in scope, the corrected p) of one settled sheet row: out of scope
    (another sport, a market the term does not correct - the floor keys
    among them) -> (False, None); a backfilled row -> its corrected p; a row
    of a day from the switch's first whole day -> its own p_central; else
    (True, None) - no evidence."""
    in_scope = scope if scope is not None else markets()
    if row.get("sport") != SPORT or row.get("market") not in in_scope:
        return False, None
    key = sheet_key(day, row.get("sofascore_event_id"), str(row["market"]),
                    row.get("subject"), row.get("line"),
                    str(row.get("direction")))
    got = backfill.sheet.get(key)
    if got is not None:
        return True, float(got)
    first = switch_day if switch_day is not None else first_whole_day()
    if first is not None and day >= first and row.get("p_central") is not None:
        return True, float(row["p_central"])
    return True, None


def sim_lines(lines: Iterable[Mapping[str, Any]], backfill: Backfill
              ) -> Iterator[dict[str, Any]]:
    """football_sim_curves.BACKFILL's lines as the switch reads them: an
    in-scope line at its corrected p (none in the table: dropped - never
    the uncorrected p), every other line (the floor keys) as it is."""
    scope = sim_markets()
    for r in lines:
        if str(r["market"]) not in scope:
            yield dict(r)
            continue
        p = backfill.sim_lines.get(sim_line_key(
            str(r["day"]), r["eid"], str(r["market"]), r.get("subject"),
            str(r["direction"])))
        if p is not None:
            yield {**r, "p": float(p)}


def ours(key: str, scope: frozenset[str] | None = None) -> bool:
    """An evidence key ("<class>:<market>|<DIR>" or "<market>|<DIR>") of the
    sheet-path keys the term corrects (default `sheet_markets`)."""
    s = scope if scope is not None else sheet_markets()
    return key.rpartition(":")[2].partition("|")[0] in s


def merge_evidence(fitted: dict[str, Any], st_fit: Mapping[str, Any],
                   scope: frozenset[str] | None = None) -> None:
    """line_evidence.fit's output `fitted` with the in-scope keys' entries
    (keys and bands) taken from `st_fit` alone - an in-scope key without a
    corrected line has none. Pooled numbers stay `fitted`'s (in place)."""
    keys = fitted.setdefault("keys", {}).setdefault(SPORT, {})
    for key in [k for k in keys if ours(k, scope)]:
        del keys[key]
    theirs = (st_fit.get("keys") or {}).get(SPORT) or {}
    keys.update({k: v for k, v in theirs.items() if ours(k, scope)})
    bands = fitted.setdefault("bands", {}).setdefault(SPORT, {})
    for key in [k for k in bands if ours(k, scope)]:
        del bands[key]
    their_bands = (st_fit.get("bands") or {}).get(SPORT) or {}
    bands.update({k: v for k, v in their_bands.items() if ours(k, scope)})
