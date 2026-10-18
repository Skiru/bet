"""The record of every market family on the coupon's own printed legs - a
selection aid on the HTML view, never a gate and never a confidence.

A family is (sport, market, direction). Its record is what the official
coupon's printed singles of that family did on the days before the coupon
day, graded exactly as the ledger grades them (`record_results.
graded_confidence`, computed by `scripts/sofa/build_family_record.py`): legs
WIN / LOSS at the printed price; a refund, a void and a pending leg count
nothing. A family is "on the plus" when it holds >= `MIN_LEGS` graded legs
and its units are above zero.

Why it exists (operator 2026-10-18, "zysk"; `docs/sofa/evidence/
selection_walk_forward_2026-10-18.md`): the coupon is calibrated and loses
the margin (10-09..10-17 ROI -4.3% [-5.2, -3.5], 25,067 legs), and no fix of
one market changes that. Walk-forward on 10-12..10-17 (families chosen on the
3-8 days before each day), legs of a family on the plus with confidence x
odds >= 1 realised ROI -0.6% [-4.8, +3.9] on 1,254 legs against -4.5% for
the rest: better on 6 of 6 days, but pooled +4.0 pp [-0.3, +8.1] with 81% of
its legs on 10-17 - an advantage not yet shown, no proven profit
(T-FAMILY-SELECTION). The view lets the operator take that selection; the
coupon (the PDF) is unchanged.

The record pools the days of its window across the epochs inside it (the
file names them), and a day only partly settled counts what is graded.
"""

from __future__ import annotations

import datetime
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

FILE = "family_record.json"
# the first day of the current rules the ledger sums from (refit installed
# 2026-10-08 23:42Z, effective 10-09): earlier days are other experiments
FAMILY_RECORD_FROM = "2026-10-09"
WINDOW_DAYS = 14
MIN_LEGS = 50
VARIANT = "official"
# the measurement the page quotes beside the filter (evidence doc above)
MEASURED = ("Zmierzone walk-forward na kuponach 10-12..10-17 (rodziny wybrane "
            "na 3-8 dniach wcześniejszych): x ≥ 1 i rodzina na plusie - 1 254 "
            "nogi, ROI -0,6% [-4,8; +3,9], reszta kuponu -4,5%. Lepsza od reszty "
            "w 6 z 6 dni, ale łącznie +4,0 pp [-0,3; +8,1], 81% nóg z jednego "
            "dnia (10-17): przewaga niepotwierdzona, zysk nieudowodniony.")

# (printed leg, outcome, odds) as graded_confidence returns them
Graded = tuple[Mapping[str, Any], str, float | None]


def family_key(leg: Mapping[str, Any]) -> str:
    return "|".join((str(leg.get("sport") or "football"), str(leg.get("market") or ""),
                     str(leg.get("direction") or "")))


def selection_x(leg: Mapping[str, Any]) -> float | None:
    """x = confidence x odds exactly as the view shows it (coupon_html, after
    build_coupon_pdf.leg_x): the leg's own `x` when the artifact carries one
    (sport legs, rounded to 4 decimals), else confidence x offered_odds."""
    if leg.get("x") is not None:
        return float(leg["x"])
    odds = leg.get("offered_odds")
    return None if odds is None else float(leg["confidence"]) * float(odds)


def selected(leg: Mapping[str, Any], plus: set[str] | frozenset[str]) -> bool:
    """The view's button "x ≥ 1 i rodzina na plusie": x >= 1 and the leg's family on the
    plus. The measurement and the page apply this one rule."""
    x = selection_x(leg)
    return x is not None and x >= 1.0 and family_key(leg) in plus


def window(day: str) -> list[str]:
    """The days whose printed legs make `day`'s record: the `WINDOW_DAYS`
    before it, never before `FAMILY_RECORD_FROM`, never `day` itself."""
    end = datetime.date.fromisoformat(day)
    first = max(end - datetime.timedelta(days=WINDOW_DAYS),
                datetime.date.fromisoformat(FAMILY_RECORD_FROM))
    out = []
    d = first
    while d < end:
        out.append(d.isoformat())
        d += datetime.timedelta(days=1)
    return out


def summarize(graded: Iterable[Graded]) -> dict[str, dict[str, Any]]:
    """Per family: legs, matches, won, units, roi, hit and mean 1/odds of the
    WIN / LOSS legs (anything else counts nothing)."""
    acc: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"legs": 0, "won": 0, "units": 0.0, "implied": 0.0, "events": set()})
    for leg, outcome, odds in graded:
        if outcome not in ("WIN", "LOSS") or not odds:
            continue
        a = acc[family_key(leg)]
        a["legs"] += 1
        a["won"] += outcome == "WIN"
        a["units"] += float(odds) - 1.0 if outcome == "WIN" else -1.0
        a["implied"] += 1.0 / float(odds)
        a["events"].add(str(leg.get("group_key") or leg.get("sofascore_event_id")))
    out: dict[str, dict[str, Any]] = {}
    for key, a in sorted(acc.items()):
        n = a["legs"]
        out[key] = {"legs": n, "matches": len(a["events"]), "won": a["won"],
                    "units": round(a["units"], 4), "roi": round(a["units"] / n, 4),
                    "hit": round(a["won"] / n, 4),
                    "implied": round(a["implied"] / n, 4)}
    return out


def build(day: str, graded_by_day: Mapping[str, Iterable[Graded]],
          now: datetime.datetime) -> dict[str, Any]:
    days = sorted(graded_by_day)
    rows: list[Graded] = [g for d in days for g in graded_by_day[d]]
    return {
        "before": day,
        "days": days,
        "variant": VARIANT,
        "min_legs": MIN_LEGS,
        "window_days": WINDOW_DAYS,
        "created_at_utc": now.astimezone(datetime.UTC).isoformat(
            timespec="seconds").replace("+00:00", "Z"),
        "families": summarize(rows),
    }


def on_plus(entry: Mapping[str, Any] | None, min_legs: int = MIN_LEGS) -> bool:
    if not entry:
        return False
    return int(entry["legs"]) >= min_legs and float(entry["units"]) > 0


def load(run: Path, day: str) -> dict[str, Any] | None:
    """The day's record, or None when absent, unreadable, made for another
    day (a copied run directory never lends its record) or under other
    parameters (window, minimum legs)."""
    path = run / FILE
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("before") != day \
            or not isinstance(doc.get("families"), dict) \
            or doc.get("min_legs") != MIN_LEGS \
            or doc.get("window_days") != WINDOW_DAYS:
        return None
    return doc


def label(entry: Mapping[str, Any]) -> str:
    """The view's tag for a family on the plus (none is written for the
    others)."""
    roi = f"{float(entry['roi']) * 100:+.1f}".replace(".", ",")
    return f"rodzina na plusie: ROI {roi}% na {entry['legs']} nogach"


def span(doc: Mapping[str, Any]) -> str:
    days = doc.get("days") or []
    return f"{days[0]}..{days[-1]}" if days else ""
