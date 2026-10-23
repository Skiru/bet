"""Curve keys with no history behind them (epochs.LIVE_ONLY_CURVE_REFUSED).

The rule (CLAUDE.md): curves are fitted on the HISTORY of events and
statistics replayed as of each match; our settled days are an audit of a
curve, never its source. `fit_confidence` reads every `sofa_settled_row`,
the replay's rows (run_date `REPLAY_RUN_DATE`) and SETTLE's live rows alike,
so a market the replay does not price (tennis service points, aces / double
faults in a set, tiebreaks...) got a curve fitted from our settled days ALONE
(found 2026-10-22, docs/sofa/history/REFIT_PILKA_2026-10-22.md, "Znalezisko").

Two halves:

* The fit. `fit_confidence` tracks, per curve key, whether a replayed row
  reached it; a key reached only by live rows is left out and listed in the
  fit's output under `REFUSED_FIELD` (`refuse` / `refuse_lines`). A key with
  no curve reads line evidence / NO_LINE_EVIDENCE like any market without
  one.
* The installed curves. They predate the rule; the keys measured to be
  live-only on the DB they were fitted from are listed in
  `config/sofa_live_only_curves.json` (`FILE`), and from
  `epochs.LIVE_ONLY_CURVE_REFUSED_FROM_UTC` CONFIDENCE (and the line
  evidence's base of such a day) reads the calibration without them
  (`strip`): the key has no curve, no pool stands in for it.

An entry is "<section>:<key>", a class's "<class>.<section>:<key>", a line
curve's "by_market_direction_line:<market>|<DIR>@<line>"; a pool
"pooled_by_sport:<sport>" / "pooled:all".
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bet.sofa import epochs
from bet.sofa.config import config_path
from bet.sofa.line_curves import SECTION as LINE_SECTION

if TYPE_CHECKING:
    from bet.sofa.confidence import Calibration

# The literal run_date the cache replay (calibrate_from_cache.py, prepare_refit
# rebuild-cache-rows) files its rows under; every other run_date is a day
# SETTLE graded live.
REPLAY_RUN_DATE = "cache-calibration"
# The fit output's list of the keys left without a curve.
REFUSED_FIELD = "live_only_refused"
FILE = "sofa_live_only_curves.json"
POOLED_ALL = "all"
# The sections of one curve set (top level or a class) a key is refused from.
CURVE_SECTIONS: tuple[str, ...] = (
    "by_market", "by_market_direction", "thin_by_market_direction",
    "pooled_by_sport")


def entry(section: str, key: str, klass: str = "") -> str:
    """The list entry of one curve key."""
    return f"{klass}.{section}:{key}" if klass else f"{section}:{key}"


def parse(raw: str) -> tuple[str, str, str]:
    """(class or "", section, key) of an entry."""
    head, _, key = raw.partition(":")
    klass, dot, section = head.rpartition(".")
    return (klass if dot else "", section, key)


def refuse(curves: Mapping[str, Any], history: set[str], section: str,
           refused: list[str], klass: str = "") -> dict[str, Any]:
    """`curves` without the keys no replayed row reached (`history` holds
    the keys that one did); each one left out is appended to `refused`."""
    out: dict[str, Any] = {}
    for key, curve in curves.items():
        if key in history:
            out[key] = curve
        else:
            refused.append(entry(section, key, klass))
    return out


def refuse_lines(section: Mapping[str, Mapping[str, Any]],
                 history: set[tuple[str, str]], refused: list[str]
                 ) -> dict[str, dict[str, Any]]:
    """The per-line section without the (key, line) curves no replayed row
    reached."""
    out: dict[str, dict[str, Any]] = {}
    for key, lines in section.items():
        kept = {}
        for line, curve in lines.items():
            if (key, line) in history:
                kept[line] = curve
            else:
                refused.append(entry(LINE_SECTION, f"{key}@{line}"))
        if kept:
            out[key] = kept
    return out


def present(doc: Mapping[str, Any], raw: str) -> bool:
    """Does the calibration document hold the curve of this entry?"""
    klass, section, key = parse(raw)
    if section == LINE_SECTION:
        mk, _, line = key.rpartition("@")
        return line in ((doc.get(LINE_SECTION) or {}).get(mk) or {})
    if section == "pooled":
        return bool(doc.get("pooled"))
    owner = ((doc.get("by_class") or {}).get(klass) or {}) if klass else doc
    return key in (owner.get(section) or {})


def load_entries(path: Path | None = None) -> frozenset[str]:
    """The installed curve keys measured live-only (`FILE`; none when the
    file is absent)."""
    p = path if path is not None else config_path(FILE)
    if not p.exists():
        return frozenset()
    doc = json.loads(p.read_text(encoding="utf-8"))
    return frozenset(str(e) for e in doc.get("entries") or ())


def _drop(curves: Mapping[str, Any], keys: set[str]) -> dict[str, Any]:
    return {k: v for k, v in curves.items() if k not in keys}


def strip(cal: Calibration, entries: Iterable[str]) -> Calibration:
    """`cal` without the listed curves: each such key reads as a market with
    no curve - no pool stands in for it (`Calibration.no_pool_keys`), so
    under line evidence it reads its own Superbet lines or NO_LINE_EVIDENCE.
    The unproven-market ceiling stays the one the full file gives, so no
    other leg moves."""
    by_section: dict[tuple[str, str], set[str]] = {}
    lines: dict[str, set[str]] = {}
    for raw in entries:
        klass, section, key = parse(raw)
        if section == LINE_SECTION:
            mk, _, line = key.rpartition("@")
            lines.setdefault(mk, set()).add(line)
            continue
        by_section.setdefault((klass, section), set()).add(key)
    if not by_section and not lines:
        return cal

    def section_keys(klass: str, section: str) -> set[str]:
        return by_section.get((klass, section), set())

    def no_pool(klass: str) -> set[str]:
        return (section_keys(klass, "by_market")
                | section_keys(klass, "by_market_direction")
                | section_keys(klass, "thin_by_market_direction"))

    by_class: dict[str, dict[str, Any]] = {}
    for klass, sec in cal.by_class.items():
        new = dict(sec)
        for name in CURVE_SECTIONS:
            if isinstance(sec.get(name), Mapping):
                new[name] = _drop(sec[name], section_keys(klass, name))
        new["no_pool_keys"] = sorted(no_pool(klass))
        whole = cal.for_class(klass)
        new["unproven_ceiling"] = (whole.unproven_ceiling_value()
                                   if whole is not None else None)
        by_class[klass] = new
    line_section = {}
    for key, per_line in cal.by_market_direction_line.items():
        kept = {ln: c for ln, c in per_line.items()
                if ln not in lines.get(key, set())}
        if kept:
            line_section[key] = kept
    pooled = {} if POOLED_ALL in section_keys("", "pooled") else cal.pooled
    return dataclasses.replace(
        cal,
        pooled=pooled,
        by_market=_drop(cal.by_market, section_keys("", "by_market")),
        by_market_direction=_drop(cal.by_market_direction,
                                  section_keys("", "by_market_direction")),
        thin_by_market_direction=_drop(
            cal.thin_by_market_direction,
            section_keys("", "thin_by_market_direction")),
        pooled_by_sport=_drop(cal.pooled_by_sport,
                              section_keys("", "pooled_by_sport")),
        by_market_direction_line=line_section,
        by_class=by_class,
        no_pool_keys=frozenset(no_pool("")),
        unproven_ceiling=cal.unproven_ceiling_value(),
    )


def for_day(cal: Calibration, date: str, build_at: datetime | None = None,
            path: Path | None = None) -> Calibration:
    """The calibration day `date` reads: without the listed live-only keys
    from epochs.LIVE_ONLY_CURVE_REFUSED_FROM_UTC (day and build clock),
    unchanged before it."""
    if not epochs.live_only_curve_refused(date, build_at):
        return cal
    return strip(cal, load_entries(path))
