"""The "Wszystkie wyceny" tab of KUPON_<d>.html: every row the day priced.

The operator (2026-10-21): "you compute markets but don't show them - why
compute them?". The coupon page shows the printed legs; this tab lists every
row the confidence stages read - each football / tennis 05_sheet.json row and
each priced Superbet side of the measured sports - with its odds, the
statistics' p, the confidence where the stage got that far, whether it
printed (11_coupon.json) and, when not, why (bet.sofa.priced_rows:
08_refusals.json, 08_refusals_sports.json).

**A view, not a coupon.** It prints nothing, gates nothing and adds no number:
every figure is a field of those artifacts. A day built before the refusal
record existed falls back to 05_sheet.json and the sports' legs, with the
reason unknown ("?").

`build` returns the payload (columnar, string-interned; the page inlines it
gzip-compressed and renders it a page at a time).
"""

from __future__ import annotations

import base64
import gzip
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from bet.sofa import confidence as cf
from bet.sofa import coupon_sports as cs
from bet.sofa import priced_rows
from bet.sofa.superbet_names import Sides, names

# the printed column of a row
NOT_PRINTED, SINGLE, BUILDER_LEG = 0, 1, 2
UNKNOWN_REASON = "?"
# passed its stage, yet not on the coupon (a measured sport's read removal,
# the coupon form, a later rebuild ...)
NOT_ON_COUPON = "NOT_ON_COUPON"
REMOVED_BY_READ = "REMOVED_BY_READ"

Key = tuple[int, str, int, str, float | None, str]


def _key(eid: Any, market: Any, period: Any, subject: Any, line: Any,
         direction: Any) -> Key | None:
    try:
        return (int(eid), str(market or ""), int(period or 0), str(subject or ""),
                None if line is None else round(float(line), 4), str(direction or ""))
    except (TypeError, ValueError):
        return None


def leg_key(leg: Mapping[str, Any], eid: Any = None) -> Key | None:
    """A coupon leg's key: football / tennis by `market`, a measured sport by
    `family` and period (as the refusal record writes them)."""
    sheet = cf.is_sheet_sport(leg)
    return _key(leg.get("sofascore_event_id", eid),
                leg.get("market") if sheet
                else (leg.get("family") or leg.get("market")),
                0 if sheet else leg.get("period"), leg.get("subject"),
                leg.get("line"), leg.get("direction") if sheet
                else (leg.get("side") or leg.get("direction")))


def _printed(doc: Mapping[str, Any]) -> tuple[dict[Key, int], list[dict[str, Any]]]:
    """Every printed key (single / builder leg) and the printed singles."""
    out: dict[Key, int] = {}
    singles = cf.printed_singles(dict(doc))
    for b in cf.printed_builders(dict(doc)):
        for x in b.get("legs") or []:
            k = leg_key({"sport": b.get("sport") or "football", **x},
                        b.get("sofascore_event_id"))
            if k is not None:
                out[k] = BUILDER_LEG
    for s in singles:
        k = leg_key(s)
        if k is not None:
            out[k] = SINGLE
    return out, singles


def _fallback_football(run: Path) -> dict[str, Any] | None:
    """05_sheet.json as a refusal record with every reason unknown."""
    try:
        sheet = json.loads((run / "05_sheet.json").read_text(encoding="utf-8"))
        fixtures = {f["sofascore_event_id"]: f for f in json.loads(
            (run / "02_fixtures.json").read_text(encoding="utf-8"))}
    except (OSError, ValueError, KeyError, TypeError):
        return None
    rec = priced_rows.RefusalRecord()
    for row in sheet if isinstance(sheet, list) else []:
        fx = fixtures.get(row.get("sofascore_event_id")) or {}
        ev = rec.event((row.get("sofascore_event_id"),), {
            "sport": row.get("sport"),
            "sofascore_event_id": row.get("sofascore_event_id"),
            "match": f"{fx['home_name']} - {fx['away_name']}" if fx else "",
            "competition": fx.get("competition_name"),
            "kickoff_utc": fx.get("kickoff_utc")})
        rec.start(ev, str(row.get("market")), None, None, row.get("subject") or "",
                  row.get("line"), str(row.get("direction")), row.get("offered_odds"),
                  row.get("p_central"))
        rec.passed(UNKNOWN_REASON)
    return rec.doc("", "", "05_sheet.json (no 08_refusals.json)")


def _fallback_sports(run: Path) -> dict[str, Any] | None:
    """08_confidence_sports.json's legs (the refused sides are not known)."""
    try:
        doc = json.loads(
            (run / "08_confidence_sports.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rec = priced_rows.RefusalRecord()
    for leg in doc.get("legs") or []:
        ev = rec.event((leg.get("sport"), str(leg.get("superbet_event_id"))), leg)
        rec.start(ev, str(leg.get("family")), leg.get("market_id"), leg.get("period"),
                  leg.get("subject") or "", leg.get("line"), str(leg.get("side")),
                  leg.get("odds"), leg.get("forecast_p"))
        rec.confidence = leg.get("confidence")
        rec.passed()
    return rec.doc("", "", "08_confidence_sports.json (no 08_refusals_sports.json)")


def _named(row: Mapping[str, Any], sides: Mapping[int, Sides]) -> dict[str, Any]:
    """A record row as a leg bet.sofa.superbet_names / display_line read."""
    sport = str(row.get("sport") or "football")
    leg: dict[str, Any] = {
        "sport": sport, "sofascore_event_id": row.get("sofascore_event_id"),
        "match": row.get("match") or "", "subject": row.get("subject") or "",
        "line": row.get("line"), "direction": row.get("direction")}
    if sport in cf.SHEET_SPORTS:
        leg["market"] = row.get("market")
    else:
        leg.update({"family": row.get("market"), "market": row.get("market"),
                    "market_id": row.get("market_id"), "period": row.get("period"),
                    "map_nr": row.get("period"), "side": row.get("direction")})
    return leg


def _label(leg: Mapping[str, Any], sides: Mapping[int, Sides]) -> str:
    eid = leg.get("sofascore_event_id")
    got = names(leg, sides.get(eid) if isinstance(eid, int) else None)
    if got is not None:
        return f"{got[0]}: {got[1]}" if got[1] else got[0]
    subject = f" ({leg['subject']})" if leg.get("subject") else ""
    return f"{leg.get('market')}{subject}"


class _Strings:
    def __init__(self) -> None:
        self.items: list[str] = []
        self._ix: dict[str, int] = {}

    def __call__(self, s: Any) -> int:
        text = "" if s is None else str(s)
        i = self._ix.get(text)
        if i is None:
            i = self._ix[text] = len(self.items)
            self.items.append(text)
        return i


def build(run: Path, doc: Mapping[str, Any], day: str,
          sides: Mapping[int, Sides], to_local: Any, minutes_of_day: Any,
          ) -> dict[str, Any] | None:
    """The tab's payload, or None when the day has no priced row on disk.
    `doc` is the coupon artifact (11_coupon.json); `to_local` /
    `minutes_of_day` the page's own clock helpers (bet.sofa.coupon_html)."""
    sources: list[tuple[str, dict[str, Any]]] = []
    football = priced_rows.load(run / priced_rows.FILE)
    if football is None:
        football = _fallback_football(run)
    if football is not None:
        sources.append(("football", football))
    sports = priced_rows.load(run / priced_rows.SPORTS_FILE)
    if sports is None:
        sports = _fallback_sports(run)
    if sports is not None:
        sources.append(("sports", sports))
    if not sources:
        return None
    printed, singles = _printed(doc)
    removed = {k for x in doc.get("removed_by_reads") or []
               if (k := leg_key(x)) is not None}
    strs = _Strings()
    events: list[list[Any]] = []
    event_ix: dict[tuple[Any, ...], int] = {}
    rows: list[list[Any]] = []
    seen: set[Key] = set()

    def event_of(row: Mapping[str, Any]) -> int:
        k = (row.get("sport"), row.get("sofascore_event_id"),
             row.get("superbet_event_id"), row.get("match"))
        i = event_ix.get(k)
        if i is None:
            ko = to_local(row.get("kickoff_utc"))
            i = event_ix[k] = len(events)
            events.append([strs(row.get("sport") or "football"), row.get("match") or "",
                           row.get("competition") or "",
                           f"{ko:%Y-%m-%d %H:%M}" if ko else "",
                           minutes_of_day(ko, day)])
        return i

    def add(row: Mapping[str, Any], reason: str | None, conf: Any) -> None:
        leg = _named(row, sides)
        k = _key(row.get("sofascore_event_id"), row.get("market"), row.get("period"),
                 row.get("subject"), row.get("line"), row.get("direction")) \
            if row.get("sofascore_event_id") is not None else None
        state = printed.get(k, NOT_PRINTED) if k is not None else NOT_PRINTED
        if k is not None:
            seen.add(k)
        if state == NOT_PRINTED and reason is None:
            reason = REMOVED_BY_READ if k in removed else NOT_ON_COUPON
        rows.append([event_of(row), strs(_label(leg, sides)),
                     strs(row.get("market")), strs(cs.display_line(leg)),
                     strs(row.get("direction")), row.get("odds"), row.get("p"),
                     None if conf is None else round(float(conf), 4), state,
                     strs(reason or "")])

    for _, rec in sources:
        for row in priced_rows.rows_as_dicts(rec):
            add(row, row.get("reason"), row.get("confidence"))
    # a printed single the records do not hold (a locked leg from an earlier
    # build whose row is gone): shown from the coupon itself
    for s in singles:
        k = leg_key(s)
        if k is None or k in seen:
            continue
        sheet = cf.is_sheet_sport(s)
        add({"sport": s.get("sport") or "football",
             "sofascore_event_id": s.get("sofascore_event_id"),
             "match": s.get("match"), "competition": s.get("competition"),
             "kickoff_utc": s.get("kickoff_utc"),
             "market": s.get("market") if sheet else s.get("family"),
             "market_id": s.get("market_id"), "period": s.get("period"),
             "subject": s.get("subject"), "line": s.get("line"),
             "direction": s.get("direction") if sheet else s.get("side"),
             "odds": s.get("offered_odds", s.get("odds")),
             "p": s.get("model_p", s.get("forecast_p"))}, None, s.get("confidence"))
    return {
        "sources": [str(rec.get("stage") or name) for name, rec in sources],
        "strs": strs.items,
        "events": events,
        "rows": rows,
    }


def encode(payload: Mapping[str, Any]) -> str:
    """gzip + base64 of the payload's JSON (the page decompresses it with the
    browser's DecompressionStream when the tab is first opened)."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return base64.b64encode(gzip.compress(raw, 9, mtime=0)).decode("ascii")


def decode(blob: str) -> dict[str, Any]:
    out: dict[str, Any] = json.loads(gzip.decompress(base64.b64decode(blob)))
    return out


def as_dicts(payload: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    """The payload's rows spelled out (tests)."""
    s, ev = payload["strs"], payload["events"]
    for r in payload["rows"]:
        e = ev[r[0]]
        yield {"sport": s[e[0]], "match": e[1], "competition": e[2], "ko_local": e[3],
               "market": s[r[1]], "family": s[r[2]], "line": s[r[3]],
               "direction": s[r[4]], "odds": r[5], "p": r[6], "confidence": r[7],
               "printed": r[8], "reason": s[r[9]]}
