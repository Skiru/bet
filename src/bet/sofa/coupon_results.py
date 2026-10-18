"""The settled result of every printed position, for the coupon's own pages.

After a day is settled, KUPON_<d>.pdf and KUPON_<d>.html mark each row they
print: green - the leg won, red - it lost, yellow - not known (still pending,
never graded, a disagreement between graders) or refunded (0 u.). Beside the
leg's claim (its line, side and confidence) each row shows what the market
actually counted, and every page ends with a summary in percent.

The grades are the ledger's (record_results.graded_confidence - audit_settlement
7c's keys, refunds and builder rule; the measured sports through
coupon_sports.grade), never a second grader. They are written once to
`13_results.json` by scripts/sofa/mark_coupon_results.py and only read by the
renderers. The match score shown beside a football / tennis match is read
from the Sofascore event payload the pipeline cached (sofa_event_detail),
display only.

`compute` and `summarize` are pure (tested); `match_scores` reads the DB.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from bet.sofa.coupon_sports import MEASURED_SPORTS, sport_key
from bet.sofa.football_incidents import PENALTIES, RED_CARDS
from bet.sofa.locked_print import leg_key
from bet.sofa.superbet_names import FIELD_SELECTION
from bet.sofa.tennis_winner import RATING_ONLY_MARKETS

RESULTS_FILE = "13_results.json"
SCHEMA = "CouponResults.v1"

WON, LOST, REFUND, UNKNOWN = "won", "lost", "refund", "unknown"
# the colours of a row (green / red / yellow, the operator's three) and the
# word the page writes in it
COLOURS = {WON: "#d9f2e1", LOST: "#f8d7d7", REFUND: "#fff1c2", UNKNOWN: "#fff1c2"}
WORDS = {WON: "weszło", LOST: "nie weszło", REFUND: "zwrot", UNKNOWN: "nie wiadomo"}
# A raw outcome the page cannot call a win or a loss, in the operator's words.
UNKNOWN_WHY = {
    "PENDING": "czeka na rozliczenie",
    "UNSETTLED": "nie rozliczono",
    "UNGRADEABLE": "wynik nie rozstrzyga linii",
    "MISMATCH": "dwa rozliczenia się różnią",
    "IN_PLAY_PRICE": "kurs wzięty w trakcie meczu",
}

# Football / tennis markets of one event (yes / no, the settled value 1 or 0):
# the page shows the match score for them, not "1". Red cards and penalties
# are counts.
EVENT_MARKETS = RATING_ONLY_MARKETS - {RED_CARDS, PENALTIES}


def status(outcome: str | None) -> str:
    """won / lost / refund / unknown of a graded position's outcome."""
    if outcome == "WIN":
        return WON
    if outcome == "LOSS":
        return LOST
    if outcome in ("REFUND", "VOID"):
        return REFUND
    return UNKNOWN


def is_measured(leg: Mapping[str, Any]) -> bool:
    return str(leg.get("sport") or "football") in MEASURED_SPORTS


def key_of(leg: Mapping[str, Any], event_id: Any = None) -> str:
    """One printed leg as a JSON string - the key every grader uses
    (sport_key for a measured sport's leg, leg_key otherwise)."""
    if is_measured(leg):
        return json.dumps(list(sport_key(leg)))
    return json.dumps(list(leg_key(leg, event_id)))


def builder_key(b: Mapping[str, Any]) -> str:
    legs = sorted(key_of(x, b.get("sofascore_event_id")) for x in b.get("legs") or [])
    return json.dumps([b.get("sofascore_event_id"), legs])


def _actual(row: Mapping[str, Any] | None) -> float | None:
    if row is None or row.get("actual_value") is None:
        return None
    if row.get("outcome") not in ("WIN", "LOSS"):
        return None
    return float(row["actual_value"])


def compute(
    date: str,
    graded: Iterable[Mapping[str, Any]],
    scores: Mapping[int, str] | None = None,
    computed_at_utc: str = "",
) -> dict[str, Any]:
    """The results document of one day from record_results.graded_confidence:
    every printed single and builder (the coupon's variants; `removed:reads`
    is not on the page and is left out) with its outcome, status, the value
    it was graded on and the match score."""
    scores = scores or {}
    legs: dict[str, dict[str, Any]] = {}
    builders: dict[str, dict[str, Any]] = {}
    for variant in graded:
        if str(variant.get("variant")) == "removed:reads":
            continue
        rows: Mapping[Any, Mapping[str, Any]] = variant.get("rows") or {}
        for g in variant.get("singles") or []:
            src = g["source"]
            outcome = str(g.get("outcome"))
            if is_measured(src):
                actual = (None if src.get("actual_value") is None
                          or outcome not in ("WIN", "LOSS")
                          else float(src["actual_value"]))
                score = src.get("score")
            else:
                actual = _actual(rows.get(leg_key(src)))
                score = scores.get(int(src["sofascore_event_id"]))
            legs[key_of(src)] = {
                "outcome": outcome, "status": status(outcome),
                "actual": actual, "score": score,
                "sport": str(src.get("sport") or "football"),
                "confidence": src.get("confidence"),
                "odds": g.get("odds"),
            }
        for g in variant.get("builders") or []:
            src = g["source"]
            eid = src["sofascore_event_id"]
            outcome = str(g.get("outcome"))
            leg_rows = []
            for x in src.get("legs") or []:
                row = rows.get(leg_key(x, eid))
                raw = None if row is None else str(row.get("outcome"))
                leg_rows.append({
                    "key": key_of(x, eid),
                    "outcome": raw or "PENDING",
                    "status": status("VOID" if raw == "PUSH" else raw),
                    "actual": _actual(row),
                })
            builders[builder_key(src)] = {
                "outcome": outcome, "status": status(outcome),
                "score": scores.get(int(eid)), "legs": leg_rows,
            }
    return {"schema": SCHEMA, "date": date, "computed_at_utc": computed_at_utc,
            "graded_by": "record_results.graded_confidence (audit_settlement 7c)",
            "legs": legs, "builders": builders}


def load(run: Path) -> dict[str, Any] | None:
    """The day's 13_results.json, None when the day has not been marked."""
    path = run / RESULTS_FILE
    if not path.exists():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) and doc.get("schema") == SCHEMA else None


def of_leg(results: Mapping[str, Any] | None, leg: Mapping[str, Any],
           event_id: Any = None) -> dict[str, Any]:
    """The result of one printed leg; an unknown one when the day's results
    do not hold it (a leg is never silently green)."""
    if results is None:
        return {}
    entry = (results.get("legs") or {}).get(key_of(leg, event_id))
    return dict(entry) if entry else {"outcome": "PENDING", "status": UNKNOWN,
                                      "actual": None, "score": None}


def of_builder(results: Mapping[str, Any] | None,
               b: Mapping[str, Any]) -> dict[str, Any]:
    if results is None:
        return {}
    entry = (results.get("builders") or {}).get(builder_key(b))
    return dict(entry) if entry else {"outcome": "PENDING", "status": UNKNOWN,
                                      "score": None, "legs": []}


def _num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.2f}".rstrip("0").rstrip(".")


def actual_text(leg: Mapping[str, Any], entry: Mapping[str, Any]) -> str:
    """What the market actually counted, as the page writes it: the value the
    leg was graded on (corners 11, games 23; a handicap's difference), the
    match score for a yes / no market, "—" when unknown."""
    if not entry:
        return ""
    actual, score = entry.get("actual"), entry.get("score")
    event_market = (str(leg.get("market")) in EVENT_MARKETS if not is_measured(leg)
                    else leg.get("line") is None)
    if event_market:
        return f"wynik {score}" if score else ("tak" if actual == 1 else
                                               "nie" if actual == 0 else "—")
    if actual is None:
        return "—"
    if is_measured(leg) and "handicap" in str(leg.get("family") or leg.get("market")):
        # shadow / cs2 actual_value: team1 minus team2
        return f"różnica {_num(float(actual))} (1. drużyna − 2.)"
    return _num(float(actual))


def claim_text(leg: Mapping[str, Any]) -> str:
    """What the leg said would happen: Superbet's selection when the leg
    carries it ("poniżej 1.5", "Tak"), else its side and line ("pow. 9.5")."""
    shown = leg.get(FIELD_SELECTION)
    if shown:
        return str(shown)
    side = str(leg.get("side") or leg.get("direction") or "")
    word = {"OVER": "pow.", "UNDER": "pon."}.get(side, side)
    line = leg.get("line")
    return f"{word} {_num(float(line))}" if line is not None else word


def outcome_text(entry: Mapping[str, Any]) -> str:
    """weszło / nie weszło / zwrot / nie wiadomo (and why)."""
    if not entry:
        return ""
    st = str(entry.get("status"))
    word = WORDS.get(st, WORDS[UNKNOWN])
    if st == UNKNOWN:
        raw = str(entry.get("outcome") or "")
        why = UNKNOWN_WHY.get(raw.split(":")[0]) or (
            "nie rozliczono: " + raw.split(":", 1)[1].lower()
            if raw.startswith("NOT_GRADED:") else raw.lower())
        word += f" ({why})" if why else ""
    return word


_Pair = tuple[Mapping[str, Any], Mapping[str, Any]]


def summarize(
    pairs: Iterable[tuple[Mapping[str, Any], Mapping[str, Any]]]
) -> dict[str, Any]:
    """Percent summary of the printed singles, (leg, result) pairs: the share
    that won / lost / was refunded / is not known, the hit rate of the
    decided legs against their mean confidence (what the coupon predicted),
    and flat one-unit units / ROI at the printed price - overall and per
    sport, never pooled into another day."""
    def block(items: list[_Pair]) -> dict[str, Any]:
        n = len(items)
        counts = {s: sum(1 for _, r in items if r.get("status") == s)
                  for s in (WON, LOST, REFUND, UNKNOWN)}
        decided = [(leg, r) for leg, r in items if r.get("status") in (WON, LOST)]
        units = sum((float(r.get("odds") or leg.get("offered_odds") or 0) - 1.0)
                    if r.get("status") == WON else -1.0 for leg, r in decided)
        conf = [float(leg["confidence"]) for leg, _ in decided
                if leg.get("confidence") is not None]
        return {
            "legs": n, **counts,
            "share": {s: (counts[s] / n if n else None) for s in counts},
            "decided": len(decided),
            "hit_rate": counts[WON] / len(decided) if decided else None,
            "mean_confidence": sum(conf) / len(conf) if conf else None,
            "units": round(units, 2),
            "roi": units / len(decided) if decided else None,
        }

    items = list(pairs)
    by_sport: dict[str, list[_Pair]] = {}
    for leg, r in items:
        by_sport.setdefault(str(leg.get("sport") or "football"), []).append((leg, r))
    return {"all": block(items),
            "sports": {sp: block(v) for sp, v in sorted(by_sport.items())}}


def builders_summary(entries: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    out = {WON: 0, LOST: 0, REFUND: 0, UNKNOWN: 0}
    for e in entries:
        out[str(e.get("status") or UNKNOWN)] = out.get(str(e.get("status")), 0) + 1
    return out


SPORT_PL = {"football": "piłka nożna", "tennis": "tenis", "hockey": "hokej",
            "basketball": "koszykówka", "volleyball": "siatkówka", "cs2": "CS2"}


def pct(v: float | None) -> str:
    return "—" if v is None else f"{100 * v:.1f}%"


def summary_lines(summary: Mapping[str, Any]) -> list[dict[str, str]]:
    """The summary table's rows as text (the PDF and the HTML print the same
    strings): one per sport, then the whole coupon."""
    rows = []
    for name, b in [*((SPORT_PL.get(k, k), v) for k, v in
                      (summary.get("sports") or {}).items()),
                    ("cały kupon", summary["all"])]:
        roi = b.get("roi")
        other = b[REFUND] + b[UNKNOWN]
        rows.append({
            "name": name,
            "legs": str(b["legs"]),
            "won": f"{b[WON]} ({pct(b['share'][WON])})",
            "lost": f"{b[LOST]} ({pct(b['share'][LOST])})",
            "other": f"{other} ({pct(other / b['legs'] if b['legs'] else None)})",
            "hit": pct(b.get("hit_rate")),
            "conf": pct(b.get("mean_confidence")),
            "units": f"{b['units']:+.2f}",
            "roi": "—" if roi is None else f"{100 * roi:+.1f}%",
        })
    return rows


def _score_of_detail(event: Mapping[str, Any]) -> str | None:
    home, away = event.get("homeScore") or {}, event.get("awayScore") or {}
    if home.get("current") is None or away.get("current") is None:
        return None
    text = f"{home['current']}:{away['current']}"
    sport = str(((event.get("tournament") or {}).get("category") or {})
                .get("sport", {}).get("slug") or "")
    if sport == "tennis":
        sets = [f"{home[k]}:{away[k]}" for k in
                ("period1", "period2", "period3", "period4", "period5")
                if home.get(k) is not None and away.get(k) is not None]
        return text + (f" ({', '.join(sets)})" if sets else "")
    if home.get("period1") is not None and away.get("period1") is not None:
        text += f" (do przerwy {home['period1']}:{away['period1']})"
    return text


def match_scores(db_path: str, event_ids: Iterable[int]) -> dict[int, str]:
    """{Sofascore event: "home:away (...)"} of the finished events the
    pipeline cached (sofa_event_detail); read-only, display only."""
    ids = sorted({int(i) for i in event_ids})
    if not ids or not Path(db_path).exists():
        return {}
    out: dict[int, str] = {}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            q = ",".join("?" * len(chunk))
            for eid, status_type, payload in conn.execute(
                "SELECT sofascore_event_id, status_type, detail_json "
                f"FROM sofa_event_detail WHERE sofascore_event_id IN ({q})", chunk
            ):
                if status_type != "finished":
                    continue
                event = (json.loads(payload) or {}).get("event") or {}
                score = _score_of_detail(event)
                if score:
                    out[int(eid)] = score
    finally:
        conn.close()
    return out
