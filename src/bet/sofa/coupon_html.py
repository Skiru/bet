"""KUPON_<d>.html - the coupon's legs as a page the operator can filter.

The PDF (`scripts/sofa/build_coupon_pdf.py`) is the coupon and keeps its order
(confidence, then start). This is the same legs from the same
`11_coupon.json`, in one self-contained file (data inlined, plain JavaScript,
no server, no network) with filters - a time window, minimum confidence, sport,
competition, market, odds, minimum x - and sortable columns. Every leg's
figure is a field of the artifact; the one number it adds is the family's
record on the printed legs of the days before (bet.sofa.family_record,
`family_record.json`, a filter and a tag on the families on the plus). It
prices no builder and sizes no stake.

`build_view` is the pure part (tested: the HTML must hold exactly the legs of
the artifact); `render_html` only wraps it.
"""

from __future__ import annotations

import copy
import datetime
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from bet.sofa import confidence as cf
from bet.sofa import coupon_results as cr
from bet.sofa import coupon_sports as cs
from bet.sofa import family_record as fr
from bet.sofa import priced_view
from bet.sofa.atomic import tmp_path
from bet.sofa.peer_choice import label as peer_label
from bet.sofa.price_gap import label as price_gap_label
from bet.sofa.superbet_names import annotate as name_on_superbet
from bet.sofa.superbet_names import board_sides
from bet.sofa.superbet_names import label as superbet_label

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
    """Superbet's market name and selection when the leg carries them
    (bet.sofa.superbet_names), else the older label."""
    shown = superbet_label(leg)
    if shown:
        return shown
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


_RES_RANK = {cr.WON: 0, cr.LOST: 1, cr.REFUND: 2, cr.UNKNOWN: 3}


def _result(leg: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any] | None:
    """A row's settled result as the PDF writes it (bet.sofa.coupon_results)."""
    if not entry:
        return None
    return {"status": entry["status"], "word": cr.outcome_text(entry),
            "claim": cr.claim_text(leg), "actual": cr.actual_text(leg, entry),
            "score": entry.get("score") or ""}


def build_view(
    doc: Mapping[str, Any],
    day: str,
    fixture_status: Mapping[str, Any] | None = None,
    families: Mapping[str, Any] | None = None,
    results: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Rows of the page: the singles the PDF prints and its builders.
    `families` is the day's bet.sofa.family_record (None: the page has no
    family filter). `results` is the day's 13_results.json
    (bet.sofa.coupon_results; None before the day is settled): each row then
    carries its result and the page ends with the PDF's percent summary."""
    status = (fixture_status or {}).get("events") or {}
    record = (families or {}).get("families") or {}
    min_legs = int((families or {}).get("min_legs") or fr.MIN_LEGS)
    singles = cf.printed_singles(dict(doc))
    read_ids = {id(s) for s in cf.legs_requiring_read(dict(doc))}
    rows: list[dict[str, Any]] = []
    for i, leg in enumerate(singles):
        ko = to_local(leg.get("kickoff_utc"))
        odds = leg.get("offered_odds")
        conf = float(leg["confidence"])
        # as the PDF computes it (build_coupon_pdf.leg_x): unrounded
        x = fr.selection_x(leg)
        margin = leg.get("overround")
        clock = _clock(leg, status)
        peer = leg.get("peer") or {}
        fam = record.get(fr.family_key(leg))
        fam_plus = fr.on_plus(fam, min_legs)
        res = _result(leg, cr.of_leg(results, leg))
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
            "margin_txt": (("jednostr." if leg.get("one_sided_market") else "—")
                           if margin is None else f"{float(margin):.1%}"),
            "sample": _sample(leg),
            "position": leg.get("position"),
            "locked": bool(leg.get("locked")),
            "starred": bool(peer.get("preferred")),
            # the PDF's own sentence (peer_choice.label): the star is per leg,
            # "the surest of the near-priced legs on other variables"
            "peer": peer_label(leg),
            # bet.sofa.price_gap: confidence above the price, the PDF's sentence
            "price_gap": price_gap_label(leg),
            "verdict": _verdict(leg),
            "read": id(leg) in read_ids,
            "clock_note": clock["note"],
            "clock_checked": clock["checked"],
            # bet.sofa.family_record: the family's printed legs of the days
            # before were on the plus (a selection aid, never a gate)
            "fam_plus": fam_plus,
            "fam_note": fr.label(fam) if fam and fam_plus else "",
            "res": res,
            "res_rank": None if res is None else _RES_RANK[res["status"]],
        })
    builders: list[dict[str, Any]] = []
    printed_builders = cf.printed_builders(dict(doc))
    for b in printed_builders:
        ko = to_local(b.get("kickoff_utc"))
        b_res = cr.of_builder(results, b)
        b_legs = {x["key"]: x for x in b_res.get("legs") or []}
        builders.append({
            "res": None if results is None else {
                "status": b_res["status"], "word": cr.outcome_text(b_res),
                "score": b_res.get("score") or ""},
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
                "res": None if results is None else _result(x, {
                    **(b_legs.get(cr.key_of(x, b.get("sofascore_event_id")))
                       or {"outcome": "PENDING", "status": cr.UNKNOWN,
                           "actual": None}),
                    "score": b_res.get("score")}),
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
            "families": None if families is None else {
                "span": fr.span(families),
                "min_legs": min_legs,
                "on_plus": sum(fr.on_plus(v, min_legs) for v in record.values()),
                "measured": fr.MEASURED,
            },
            "results": None if results is None else {
                "computed_utc": str(results.get("computed_at_utc") or "")[:16],
                # the same strings as the PDF's closing table
                "summary": cr.summary_lines(cr.summarize(
                    (leg, cr.of_leg(results, leg)) for leg in singles)),
                "builders": cr.builders_summary(
                    cr.of_builder(results, b) for b in printed_builders),
            },
        },
    }


def render_html(date: str, view: Mapping[str, Any],
                priced: Mapping[str, Any] | None = None) -> str:
    """`priced`: the "Wszystkie wyceny" tab's payload (bet.sofa.priced_view;
    None: the page has no such tab)."""
    data = json.dumps(view, ensure_ascii=False, separators=(",", ":"))
    # a JSON string inside <script>: nothing in it may close the element
    data = data.replace("</", "<\\/").replace("<!--", "<\\!--")
    # base64 holds no "<": safe inside its element as it is
    blob = priced_view.encode(priced) if priced is not None else ""
    return (_TEMPLATE.replace("__DATE__", date).replace("__PRICED__", blob)
            .replace("__DATA__", data))


def write_html(run: Path, doc: Mapping[str, Any], day: str,
               results: Mapping[str, Any] | None = None) -> Path:
    """KUPON_<day>.html beside the PDF, from the same artifact and the day's
    fixture_status.json and family_record.json (read if present). Rendered
    aside and moved into place, like the PDF."""
    status_path = run / "fixture_status.json"
    status = (json.loads(status_path.read_text(encoding="utf-8"))
              if status_path.exists() else None)
    families = fr.load(run, day)
    # named in Superbet's words on a copy: the caller's artifact is not edited
    named: dict[str, Any] = copy.deepcopy(dict(doc))
    sides = board_sides(run)
    name_on_superbet(named, sides)
    out = run / f"KUPON_{day}.html"
    tmp = tmp_path(out)
    # `results` only from a results render (build_coupon_pdf.py
    # --with-results): a normal page never carries them
    # every row the day priced, printed or not (a view, never the coupon)
    priced = priced_view.build(run, named, day, sides, to_local,
                               minutes_of_day)
    tmp.write_text(render_html(day, build_view(named, day, status, families,
                                               results), priced),
                   encoding="utf-8")
    os.replace(tmp, out)
    return out


_TEMPLATE = (Path(__file__).parent / "templates" / "coupon_view.html").read_text(
    encoding="utf-8")
