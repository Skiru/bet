"""History curves of the football simulator's keys (epochs.FOOTBALL_SIM).

Under the switch SHEET prices the football rows of
``epochs.FOOTBALL_SIM_MARKETS`` (the path markets) with the minute-by-minute
simulator (bet.sofa.football_sim_sheet). No installed curve reads these keys
(OFFER never mapped them before), so their curves come from ``FILE`` alone:
fitted by scripts/sofa/fit_football_sim_curves.py on the simulator's own
walk-forward over the Sofascore history (centres as of each match; matches
2026-06-01 .. 2026-10-19 - after the window the simulator's constants were
fitted on, before the Superbet hold-out of the wiring), in fit_confidence's
format (EDGES, MIN_MARKET_BUCKET / MIN_THIN_BUCKET, realised_lo95 = Wilson
lower bound); history-fitted, so never stripped as live-only.

``for_day`` (CONFIDENCE and fit_line_evidence, after
live_only_curves.for_day): on a day the switch is on, every in-scope key's
curves are REPLACED by the file's - top level and per class (the women's
class reads its own section; a class the file has no section for keeps no
curve for them: NO_CLASS_CURVE) - its per-line curves dropped, and the keys
put in ``no_pool_keys`` (a hole in their own curve is no curve, no pool stands
in). Off, the calibration is returned unchanged; on without the file, the
keys have no curve. The installed calibration file is never written.

Line evidence (fit_line_evidence.py) reads these keys' settled Superbet lines
against these curves at the simulator's p. Before the switch no such line was
ever a sheet row, so ``BACKFILL`` holds them: every path-market price OFFER
recorded in ``unmapped_prices`` (2026-10-14 .. 2026-11-05, the latest
pre-match snapshot of each selection), priced by the simulator as SHEET
prices it and graded by ``football_sim_markets.sim_value`` on the cached
event (fit_football_sim_curves.py --backfill-out). From the switch on, the
days' own settled rows (p_central = the simulator's p) are read as any line.
"""

from __future__ import annotations

import dataclasses
import gzip
import json
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bet.sofa import epochs
from bet.sofa.config import config_path

if TYPE_CHECKING:
    from bet.sofa.confidence import Calibration

FILE = "sofa_football_sim_curves.json"
BACKFILL = Path(__file__).resolve().parents[3] / "data" / "line_evidence" / (
    "football_sim_lines.jsonl.gz")
SECTIONS = ("by_market", "by_market_direction", "thin_by_market_direction")
SPORT = "football"


def _in_scope(key: str) -> bool:
    return key.partition("|")[0] in epochs.FOOTBALL_SIM_MARKETS


def load(path: Path | None = None) -> dict[str, Any] | None:
    p = path if path is not None else config_path(FILE)
    if not p.exists():
        return None
    doc: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    return doc


def _replace(section: Mapping[str, Any] | None,
             new: Mapping[str, Any] | None) -> dict[str, Any]:
    kept = {k: v for k, v in (section or {}).items() if not _in_scope(k)}
    kept.update({k: v for k, v in (new or {}).items() if _in_scope(k)})
    return kept


def no_pool(doc_section: Mapping[str, Any]) -> set[str]:
    keys = set(epochs.FOOTBALL_SIM_MARKETS)
    for name in SECTIONS:
        keys |= {k for k in (doc_section.get(name) or {}) if _in_scope(k)}
    return keys


def overlay(cal: Calibration, doc: Mapping[str, Any]) -> Calibration:
    """`cal` with the in-scope keys read from `doc` alone."""
    by_class: dict[str, dict[str, Any]] = {}
    doc_classes = doc.get("by_class") or {}
    for klass, sec in cal.by_class.items():
        new = dict(sec)
        theirs = doc_classes.get(klass) or {}
        for name in SECTIONS:
            new[name] = _replace(sec.get(name), theirs.get(name))
        new["no_pool_keys"] = sorted(
            set(sec.get("no_pool_keys") or ()) | no_pool(theirs))
        by_class[klass] = new
    for klass, theirs in doc_classes.items():
        if klass not in by_class:
            by_class[klass] = {name: _replace({}, theirs.get(name))
                               for name in SECTIONS}
            by_class[klass]["no_pool_keys"] = sorted(no_pool(theirs))
    lines = {k: v for k, v in cal.by_market_direction_line.items()
             if not _in_scope(k)}
    return dataclasses.replace(
        cal,
        by_market=_replace(cal.by_market, doc.get("by_market")),
        by_market_direction=_replace(cal.by_market_direction,
                                     doc.get("by_market_direction")),
        thin_by_market_direction=_replace(cal.thin_by_market_direction,
                                          doc.get("thin_by_market_direction")),
        by_market_direction_line=lines,
        by_class=by_class,
        no_pool_keys=frozenset(cal.no_pool_keys | no_pool(doc)),
        # the ceiling of an unproven market stays the one the day read
        unproven_ceiling=cal.unproven_ceiling_value(),
    )


def for_day(cal: Calibration, date: str, build_at: datetime | None = None,
            path: Path | None = None) -> Calibration:
    """The calibration `date` reads: the simulator's keys from `FILE` while
    epochs.FOOTBALL_SIM is on (day and build clock); unchanged before it."""
    if not epochs.football_sim(date, build_at):
        return cal
    return overlay(cal, load(path) or {})


# --- line evidence --------------------------------------------------------------


def load_backfill(path: Path | None = None) -> list[dict[str, Any]]:
    """`BACKFILL`'s graded lines ([] when absent: no evidence before the
    switch's own settled rows)."""
    p = path if path is not None else BACKFILL
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                out.append(json.loads(line))
    return out


def backfill_rows(lines: Iterable[Mapping[str, Any]], before: str,
                  cal: Calibration, switch_day: str | None
                  ) -> Iterator[dict[str, Any]]:
    """line_evidence rows of the backfilled lines of days before `before`
    (and before the switch's first day, whose own settled rows take over),
    each read through `cal` (the overlaid calibration) at its p."""
    from bet.sofa import line_evidence as le
    from bet.sofa.confidence import direction_key

    for r in lines:
        day = str(r["day"])
        if day >= before or (switch_day is not None and day >= switch_day):
            continue
        klass = r.get("klass") or None
        p = float(r["p"])
        hit = cal.realised(str(r["market"]), p, SPORT, str(r["direction"]),
                           klass)
        yield {"sport": SPORT,
               "key": le.evidence_key(direction_key(str(r["market"]),
                                                    str(r["direction"])), klass),
               "p": p, "y": int(r["y"]), "game": f"{day}:{r['eid']}",
               "base": None if hit is None else float(hit[0]),
               "odds": float(r["odds"])}


def ours(key: str) -> bool:
    """An evidence key ("<class>:<market>|<DIR>" or "<market>|<DIR>") of the
    simulator's markets."""
    return _in_scope(key.rpartition(":")[2])


def merge_evidence(fitted: dict[str, Any], sim_fit: Mapping[str, Any]) -> None:
    """line_evidence.fit's output `fitted` with the simulator's keys' entries
    (keys and bands) taken from `sim_fit` alone - an in-scope key without
    simulator lines has none. The sport's pooled numbers are `fitted`'s (in
    place)."""
    keys = fitted.setdefault("keys", {}).setdefault(SPORT, {})
    for key in [k for k in keys if ours(k)]:
        del keys[key]
    theirs = (sim_fit.get("keys") or {}).get(SPORT) or {}
    keys.update({k: v for k, v in theirs.items() if ours(k)})
    bands = fitted.setdefault("bands", {}).setdefault(SPORT, {})
    for key in [k for k in bands if ours(k)]:
        del bands[key]
    their_bands = (sim_fit.get("bands") or {}).get(SPORT) or {}
    bands.update({k: v for k, v in their_bands.items() if ours(k)})
