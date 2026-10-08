"""KUPON_<d>.html - the coupon's legs as a page the operator can filter.

The PDF (`scripts/sofa/build_coupon_pdf.py`) is the coupon and keeps its order
(confidence, then start). This is the same legs from the same
`11_coupon.json`, in one self-contained file (data inlined, plain JavaScript,
no server, no network) with filters - a time window, minimum confidence, sport,
competition, market, odds - and sortable columns. It adds no number: every
figure is a field of the artifact, and it prices no builder and sizes no stake.

`build_view` is the pure part (tested: the HTML must hold exactly the legs of
the artifact); `render_html` only wraps it.
"""

from __future__ import annotations

import datetime
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from bet.sofa import confidence as cf
from bet.sofa import coupon_sports as cs
from bet.sofa.atomic import tmp_path
from bet.sofa.peer_choice import label as peer_label

LOCAL_TZ = ZoneInfo("Europe/Warsaw")
# A fixture-check start that differs from the leg's clock by at least this is
# shown beside it: the day's clocks disagreed (10-08, Darwin: 08:30, 09:30 and
# - on the Superbet screen - 10:55 for one match).
CLOCK_GAP_MIN = 1
_VERDICT_RANK = {"NO_BET": 3, "WATCH": 2, "KEEP": 1}


def _parse(ts: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def to_local(ts: str | None) -> datetime.datetime | None:
    """A UTC timestamp string as Europe/Warsaw wall time (None if unparsable)."""
    if not ts:
        return None
    try:
        return _parse(ts).astimezone(LOCAL_TZ)
    except ValueError:
        return None


def minutes_of_day(ko: datetime.datetime | None, day: str) -> int:
    """Minutes since the coupon day's local midnight (past 1440 after it), so a
    time-window filter never mixes a 00:30 start of the next day with the
    morning; -1 when the start is unknown."""
    if ko is None:
        return -1
    midnight = datetime.datetime.combine(
        datetime.date.fromisoformat(day), datetime.time(), tzinfo=LOCAL_TZ)
    return int((ko - midnight).total_seconds() // 60)


def market_label(leg: Mapping[str, Any]) -> str:
    if leg.get("display_market"):
        return str(leg["display_market"])
    subject = f" ({leg['subject']})" if leg.get("subject") else ""
    return f"{leg.get('market')}{subject}"


def _verdict(leg: Mapping[str, Any]) -> str:
    verdicts = [str(r.get("verdict")) for r in leg.get("reads") or []]
    return max(verdicts, key=lambda v: _VERDICT_RANK.get(v, 0), default="")


def _sample(leg: Mapping[str, Any]) -> str:
    rate, n = leg.get("sample_hit_rate"), leg.get("sample_observations")
    if leg.get("sample_k") is not None and leg.get("sample_n"):
        return f"{leg['sample_k']}/{leg['sample_n']}"
    if rate is not None and n:
        return f"{round(float(rate) * int(n))}/{n}"
    return f"n={leg.get('sample_size', '—')}"


def _num(text: str) -> float | None:
    """A line as a number to sort by ("10.5" after "7.5"); None for no line."""
    try:
        return float(text)
    except ValueError:
        return None


def _rate(sample: str) -> float | None:
    """k/n as a rate to sort the sample column by; None for "n=..." """
    k, sep, n = sample.partition("/")
    try:
        return int(k) / int(n) if sep and int(n) else None
    except ValueError:
        return None


def _clock(
    leg: Mapping[str, Any], fixture_status: Mapping[str, Any]
) -> dict[str, str]:
    """The fresh fixture-check start beside the leg's own clock, when they differ."""
    row = fixture_status.get(str(leg.get("sofascore_event_id")))
    if not isinstance(row, Mapping):
        return {"note": "", "checked": ""}
    start = to_local(row.get("start_utc"))
    ko = to_local(leg.get("kickoff_utc"))
    checked = to_local(row.get("checked_at_utc"))
    note = ""
    if start and ko and abs((start - ko).total_seconds()) >= CLOCK_GAP_MIN * 60:
        note = f"FIXTURE_CHECK: start {start:%H:%M}"
    return {"note": note, "checked": f"{checked:%H:%M}" if checked else ""}


def build_view(
    doc: Mapping[str, Any],
    day: str,
    fixture_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Rows of the page: the singles the PDF prints and its builders."""
    status = (fixture_status or {}).get("events") or {}
    singles = cf.printed_singles(dict(doc))
    read_ids = {id(s) for s in cf.legs_requiring_read(dict(doc))}
    rows: list[dict[str, Any]] = []
    for i, leg in enumerate(singles):
        ko = to_local(leg.get("kickoff_utc"))
        odds = leg.get("offered_odds")
        conf = float(leg["confidence"])
        # as the PDF computes it (build_coupon_pdf.leg_x): unrounded
        x = (float(leg["x"]) if leg.get("x") is not None
             else None if odds is None else conf * float(odds))
        margin = leg.get("overround")
        clock = _clock(leg, status)
        peer = leg.get("peer") or {}
        rows.append({
            "id": i,
            "event": str(leg.get("group_key") or leg.get("sofascore_event_id")),
            "match": str(leg.get("match") or ""),
            "competition": str(leg.get("competition") or ""),
            "sport": str(leg.get("sport") or "football"),
            "ko_utc": str(leg.get("kickoff_utc") or ""),
            "ko_local": f"{ko:%Y-%m-%d %H:%M}" if ko else "",
            "ko_min": minutes_of_day(ko, day),
            "market": market_label(leg),
            "family": str(leg.get("family") or leg.get("market") or ""),
            "line": cs.display_line(leg),
            "line_num": _num(cs.display_line(leg)),
            "sample_rate": _rate(_sample(leg)),
            "direction": str(leg.get("direction") or ""),
            "confidence": conf,
            "odds": None if odds is None else float(odds),
            "x": x,
            "margin": margin,
            # the page shows these strings as the PDF writes them (Python's
            # formatting, not the browser's toFixed): the same text, never a
            # rounding that differs by a hundredth
            "confidence_txt": f"{conf:.3f}",
            "odds_txt": "—" if odds is None else str(odds),
            "x_txt": "—" if x is None else f"{x:.2f}",
            "margin_txt": "—" if margin is None else f"{float(margin):.1%}",
            "sample": _sample(leg),
            "position": leg.get("position"),
            "locked": bool(leg.get("locked")),
            "starred": bool(peer.get("preferred")),
            # the PDF's own sentence (peer_choice.label): the star is per leg,
            # "the surest of the near-priced legs on other variables"
            "peer": peer_label(leg),
            "verdict": _verdict(leg),
            "read": id(leg) in read_ids,
            "clock_note": clock["note"],
            "clock_checked": clock["checked"],
        })
    builders: list[dict[str, Any]] = []
    for b in cf.printed_builders(dict(doc)):
        ko = to_local(b.get("kickoff_utc"))
        builders.append({
            "no": str(b.get("builder_no") or ""),
            "match": str(b.get("match") or ""),
            "competition": str(b.get("competition") or ""),
            "ko_local": f"{ko:%Y-%m-%d %H:%M}" if ko else "",
            "ko_min": minutes_of_day(ko, day),
            "locked": bool(b.get("locked")),
            "combined_txt": "—" if b.get("combined_probability") is None
            else f"{float(b['combined_probability']):.3f}",
            "legs": [{
                "market": market_label(x),
                "line": cs.display_line(x),
                "direction": str(x.get("direction") or ""),
                "confidence_txt": "—" if x.get("confidence") is None
                else f"{float(x['confidence']):.3f}",
                "odds_txt": "—" if x.get("odds") is None else str(x["odds"]),
            } for x in b.get("legs") or []],
        })
    checked = (fixture_status or {}).get("checked_at_utc")
    local_checked = to_local(checked)
    built = to_local(doc.get("created_at_utc"))
    return {
        "rows": rows,
        "builders": builders,
        "meta": {
            "built_local": f"{built:%H:%M}" if built else "",
            "fixture_check_local": f"{local_checked:%H:%M}" if local_checked else "",
            "positions": doc.get("positions"),
        },
    }


def render_html(date: str, view: Mapping[str, Any]) -> str:
    data = json.dumps(view, ensure_ascii=False, separators=(",", ":"))
    # a JSON string inside <script>: nothing in it may close the element
    data = data.replace("</", "<\\/").replace("<!--", "<\\!--")
    return _TEMPLATE.replace("__DATE__", date).replace("__DATA__", data)


def write_html(run: Path, doc: Mapping[str, Any], day: str) -> Path:
    """KUPON_<day>.html beside the PDF, from the same artifact and the day's
    fixture_status.json (read if present). Rendered aside and moved into
    place, like the PDF."""
    status_path = run / "fixture_status.json"
    status = (json.loads(status_path.read_text(encoding="utf-8"))
              if status_path.exists() else None)
    out = run / f"KUPON_{day}.html"
    tmp = tmp_path(out)
    tmp.write_text(render_html(day, build_view(doc, day, status)),
                   encoding="utf-8")
    os.replace(tmp, out)
    return out


_TEMPLATE = (Path(__file__).parent / "templates" / "coupon_view.html").read_text(
    encoding="utf-8")
