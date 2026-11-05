"""History curves of the tennis point model's keys (epochs.TENNIS_POINT_MODEL).

Under the switch SHEET prices the tennis rows of
``epochs.TENNIS_POINT_MODEL_MARKETS`` with the bottom-up point model
(bet.sofa.tennis_point_sheet), so the installed curves of those keys -
fitted on the old estimator, and partly live-only
(config/sofa_live_only_curves.json) - describe another p. Their curves come
from ``FILE`` instead: fitted by scripts/sofa/fit_tennis_point_curves.py on
the model's own walk-forward over the Sofascore history (as of each match,
matches before the Superbet hold-out), in fit_confidence's format (EDGES,
MIN_MARKET_BUCKET / MIN_THIN_BUCKET, realised_lo95 = Wilson lower bound);
history-fitted, so never stripped as live-only.

``for_day`` (CONFIDENCE and fit_line_evidence, after
live_only_curves.for_day): on a day the switch is on, every in-scope key's
curves are REPLACED by the file's - top level and per class (a class the file
has no section for keeps no curve for them: NO_CLASS_CURVE) - its per-line
curves dropped, and the keys put in ``no_pool_keys`` (a hole in their own
curve is no curve, no pool stands in). Off, the calibration is returned
unchanged; on without the file, the keys have no curve. The installed
calibration file is never written.

Line evidence (fit_line_evidence.py) reads these keys' settled Superbet lines
against these curves, so a line's p must be the point model's too: a day whose
sheet was priced before the switch reads it from ``BACKFILL`` (the point
model's p for every in-scope tennis sheet row of 2026-09-18 .. 2026-11-05,
priced by the SHEET path as of each fixture's start - fit_tennis_point_curves
.py --backfill-out); a line it does not hold is no evidence (skipped), never
read at the old estimator's p.
"""

from __future__ import annotations

import dataclasses
import gzip
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bet.sofa import epochs
from bet.sofa.config import config_path

if TYPE_CHECKING:
    from bet.sofa.confidence import Calibration

FILE = "sofa_tennis_point_curves.json"
# The point model's p of the in-scope tennis sheet rows of days priced before
# the switch (jsonl.gz-free: one gzipped JSON object {key: p}, `backfill_key`).
BACKFILL = Path(__file__).resolve().parents[3] / "data" / "line_evidence" / (
    "tennis_point_model_p.json.gz")
SECTIONS = ("by_market", "by_market_direction", "thin_by_market_direction")


def _in_scope(key: str) -> bool:
    return key.partition("|")[0] in epochs.TENNIS_POINT_MODEL_MARKETS


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
    keys = set(epochs.TENNIS_POINT_MODEL_MARKETS)
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


def backfill_key(day: str, event_id: object, market: str, subject: object,
                 line: object, direction: str) -> str:
    return (f"{day}|{int(str(event_id))}|{market}|{subject or ''}|"
            f"{float(str(line)):g}|{direction}")


def load_backfill(path: Path | None = None) -> dict[str, float]:
    """`BACKFILL` ({} when absent: such lines are then no evidence)."""
    p = path if path is not None else BACKFILL
    if not p.exists():
        return {}
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        doc: dict[str, float] = json.load(fh)
    return doc


def evidence_p(row: Mapping[str, Any], day: str, backfill: Mapping[str, float],
               switch_day: str | None) -> tuple[bool, float | None]:
    """(in scope, the point model's p) of one settled sheet row for the line
    evidence: out of scope -> (False, None); a backfilled line -> its p; a
    day from the switch on -> the row's own p_central (its sheet priced it
    with the point model); else (True, None) - no evidence."""
    if row.get("sport") != "tennis" or row.get("market") not in (
            epochs.TENNIS_POINT_MODEL_MARKETS):
        return False, None
    key = backfill_key(day, row.get("sofascore_event_id"), str(row["market"]),
                       row.get("subject"), row.get("line"), str(row.get("direction")))
    if key in backfill:
        return True, float(backfill[key])
    if (switch_day is not None and day >= switch_day
            and row.get("p_central") is not None):
        return True, float(row["p_central"])
    return True, None


def merge_evidence(fitted: dict[str, Any], point_fit: Mapping[str, Any],
                   sport: str = "tennis") -> None:
    """line_evidence.fit's output `fitted` with the point model's keys'
    entries (keys and bands; a class key "<class>:<market>|<DIR>" too) taken
    from `point_fit` alone - an in-scope key without point-model lines has
    none. The sport's pooled numbers are `fitted`'s (in place)."""
    def ours(key: str) -> bool:
        return _in_scope(key.rpartition(":")[2])

    keys = fitted.setdefault("keys", {}).setdefault(sport, {})
    for key in [k for k in keys if ours(k)]:
        del keys[key]
    theirs = (point_fit.get("keys") or {}).get(sport) or {}
    keys.update({k: v for k, v in theirs.items() if ours(k)})
    bands = fitted.setdefault("bands", {}).setdefault(sport, {})
    for key in [k for k in bands if ours(k)]:
        del bands[key]
    their_bands = (point_fit.get("bands") or {}).get(sport) or {}
    bands.update({k: v for k, v in their_bands.items() if ours(k)})


def for_day(cal: Calibration, date: str, build_at: datetime | None = None,
            path: Path | None = None) -> Calibration:
    """The calibration `date` reads: the point model's keys from `FILE`
    while epochs.TENNIS_POINT_MODEL is on (day and build clock); unchanged
    before it. On without the file the keys have no curve at all (their old
    curves describe another p): line evidence or NO_LINE_EVIDENCE."""
    if not epochs.tennis_point_model(date, build_at):
        return cal
    return overlay(cal, load(path) or {})
