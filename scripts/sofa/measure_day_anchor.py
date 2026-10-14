#!/usr/bin/env python3
"""DAY_ANCHOR backtest (identity plan K2; read-only evidence).

The rule under test: a Superbet event of hockey / basketball / volleyball
(CS2 is measured too, but not switched on: see epochs.DAY_ANCHOR_FROM_UTC)
is the one Sofascore game in which a side's resolved team id plays
within W of Superbet's start - whatever the other side's name says - when
that team has exactly one such game (gender as the board's, not postponed /
cancelled), and the other side's own resolved id, if it has one, is in it.
Today's rule (sport_identity.match_shadow) also demands the other name; the
2026-10-14 probe (PLAN_MAPA_DRUZYN_2026-10-14.md 3b) found the games it
refused that way (Takamatsu = Kagawa Five Arrows, Kavkasia = BC CIU 2 h late).

Measured, per sport and window W (1, 2, 3, 4 h):

- precision on IDENTIFIED events with the opponent's NAME hidden: the
  anchor is each side whose id the resolver had AT IDENTIFICATION
  (`team1_id` / `team2_id` of the record - today's ids would include names
  learned from this very game); the prediction must be the pinned event.
  Every wrong pick is listed: one is a wrong leg.
- on NOT_IDENTIFIED events: how many the rule would identify, and how many
  of those SHADOW_SETTLE / CS2_SETTLE found as the same Sofascore event
  later on its own rules (an independent check; a disagreement is listed);
- the start gap |Sofascore - Superbet| of every game the settle found
  (pinned or not), and of the rule's picks.

Candidates: every listed game of the anchor team in the database -
sofa_listed_event (finished games of every saved `last` page), the cached
pages of sofa_entity_events, and for CS2 cs2_series. A game postponed out of
the window and never played is in none of them, so the backtest cannot see
a pick the live listing would have refused NOT_AS_SCHEDULED; the live rule
keeps that filter.

  PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_day_anchor.py \
      [--from 2026-10-05] [--to 2026-10-14] [--md-out f] [--json-out f]
"""

from __future__ import annotations

import argparse
import glob
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.fixture_status import NOT_AS_SCHEDULED  # noqa: E402
from bet.sofa.resolve import sofascore_gender, superbet_gender  # noqa: E402

SPORT_SLUG = {
    "hockey": "ice-hockey",
    "basketball": "basketball",
    "volleyball": "volleyball",
    "cs2": "esports",
}
WINDOWS_H = (1.0, 2.0, 3.0, 4.0)


@dataclass(frozen=True)
class Game:
    event_id: int
    start_ts: int
    home_id: int | None
    away_id: int | None
    gender: str | None  # "M" / "W", None unknown (cs2_series)
    status: str


def _game(e: Mapping[str, Any]) -> Game | None:
    st, eid = e.get("startTimestamp"), e.get("id")
    if not isinstance(st, int) or not isinstance(eid, int):
        return None
    return Game(
        eid,
        st,
        (e.get("homeTeam") or {}).get("id"),
        (e.get("awayTeam") or {}).get("id"),
        sofascore_gender(dict(e)),
        str((e.get("status") or {}).get("type") or ""),
    )


def _event_slug(e: Mapping[str, Any]) -> str | None:
    return (((e.get("tournament") or {}).get("category") or {}).get("sport") or {}).get(
        "slug"
    )


def load_games(
    conn: sqlite3.Connection, slugs: Iterable[str], since_ts: int, team_ids: set[int]
) -> dict[int, dict[int, Game]]:
    """team id -> event id -> Game, for the anchors' teams: the listing
    index, the cached pages and (esports) cs2_series. One event seen in
    several of them keeps its most recently FETCHED version: a page cached
    before Sofascore moved a fixture still shows its old date (10-09 Rouen -
    Chamonix: the played game 16355418 read as January 2027 on an old page,
    its postponed twin 16355274 as 10-09 18:00)."""
    by_team: dict[int, dict[int, Game]] = defaultdict(dict)
    fetched: dict[int, str] = {}

    def add(g: Game, at: str) -> None:
        if fetched.get(g.event_id, "") > at:
            return
        fetched[g.event_id] = at
        for t in (g.home_id, g.away_id):
            if t in team_ids:
                by_team[t][g.event_id] = g

    want = set(slugs)
    for slug, at, txt in conn.execute(
        "SELECT sport, fetched_at, event_json FROM sofa_listed_event "
        "WHERE start_ts >= ?",
        (since_ts,),
    ):
        if slug not in want:
            continue
        g = _game(json.loads(txt))
        if g is not None:
            add(g, str(at))
    ids = sorted(team_ids)
    for i in range(0, len(ids), 500):
        chunk = ids[i : i + 500]
        marks = ",".join("?" * len(chunk))
        for at, txt in conn.execute(
            f"SELECT fetched_at, events_json FROM sofa_entity_events "
            f"WHERE sofascore_entity_id IN ({marks})",
            chunk,
        ):
            try:
                events = json.loads(txt).get("events") or []
            except (ValueError, AttributeError):
                continue
            for e in events:
                if _event_slug(e) in want:
                    g = _game(e)
                    if g is not None and g.start_ts >= since_ts:
                        add(g, str(at))
    if "esports" in want:
        for eid, ts, h, a, status, at in conn.execute(
            "SELECT sofascore_event_id, start_ts, home_id, away_id, status_type, "
            "fetched_at FROM cs2_series WHERE start_ts >= ?",
            (since_ts,),
        ):
            add(Game(int(eid), int(ts), h, a, None, str(status or "")), str(at))
    return by_team


def board_gender(team1: str, team2: str) -> str:
    return "W" if "W" in {superbet_gender(team1), superbet_gender(team2)} else "M"


def anchor_pick(
    games: Mapping[int, Game],
    anchor: int,
    other_id: int | None,
    kickoff_ts: int,
    window_s: float,
    gender: str,
) -> tuple[str, Game | None]:
    """The rule on one anchor side: ('PICK', game), ('NONE', None),
    ('AMBIGUOUS', None) or ('ID_DISAGREES', game)."""
    near = [
        g
        for g in games.values()
        if abs(g.start_ts - kickoff_ts) <= window_s
        and g.status not in NOT_AS_SCHEDULED
        and (g.gender is None or g.gender == gender)
    ]
    if not near:
        return "NONE", None
    if len(near) > 1:
        return "AMBIGUOUS", None
    g = near[0]
    if other_id is not None and other_id not in (g.home_id, g.away_id):
        return "ID_DISAGREES", g
    return "PICK", g


def predict(
    rec: Mapping[str, Any], by_team: Mapping[int, Mapping[int, Game]], window_s: float
) -> tuple[str, Game | None]:
    """The rule over both anchors of a record: a pick both anchors agree on
    (or the only anchor's), else the first refusal."""
    kickoff = int(
        datetime.fromisoformat(
            str(rec["kickoff_utc"]).replace("Z", "+00:00")
        ).timestamp()
    )
    gender = board_gender(str(rec["team1"]), str(rec["team2"]))
    t1, t2 = rec.get("team1_id"), rec.get("team2_id")
    results = []
    for anchor, other in ((t1, t2), (t2, t1)):
        if isinstance(anchor, int):
            results.append(
                anchor_pick(
                    by_team.get(anchor, {}),
                    anchor,
                    other if isinstance(other, int) else None,
                    kickoff,
                    window_s,
                    gender,
                )
            )
    if not results:
        return "NO_ANCHOR", None
    picks = {g.event_id: g for status, g in results if status == "PICK" and g}
    if len(picks) == 1 and all(s in ("PICK", "NONE") for s, _ in results):
        return "PICK", next(iter(picks.values()))
    if len(picks) > 1:
        return "ANCHORS_DISAGREE", None
    order = ("ID_DISAGREES", "AMBIGUOUS", "NONE")
    status = min(
        (s for s, _ in results),
        key=lambda s: order.index(s) if s in order else len(order),
    )
    return status, None


def records(runs_dir: str, first: str | None, last: str | None) -> list[dict[str, Any]]:
    """Latest SPORT_IDENTITY record per Superbet event, in the window,
    without 1x1 loops and DUPLICATE_SUPERBET_TEAM."""
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(glob.glob(str(Path(runs_dir) / "*" / "sport_fixtures.json"))):
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        for r in doc.get("fixtures") or []:
            out[str(r["superbet_event_id"])] = r
    keep = []
    for r in out.values():
        day = str(r["kickoff_utc"])[:10]
        if (first and day < first) or (last and day > last):
            continue
        if (
            r.get("status") == "DUPLICATE_SUPERBET_TEAM"
            or "1x1" in str(r.get("tournament") or "").lower()
        ):
            continue
        keep.append(r)
    return keep


def settle_found(runs_dir: str) -> dict[str, dict[str, Any]]:
    """Superbet event id -> what SHADOW_SETTLE / CS2_SETTLE found: the
    Sofascore event, how, and its start."""
    out: dict[str, dict[str, Any]] = {}
    root = Path(runs_dir)
    paths = sorted(
        glob.glob(str(root / "shadow" / "*" / "*" / "settled.json"))
    ) + sorted(glob.glob(str(root / "cs2" / "*" / "settled.json")))
    for path in paths:
        try:
            doc = json.loads(Path(path).read_text(encoding="utf-8"))
        except ValueError:
            continue
        for sb, ev in (doc.get("events") or {}).items():
            if isinstance(ev.get("sofascore_event_id"), int):
                out[str(sb)] = ev
    return out


def _gap_h(a: str, b: str) -> float:
    ta = datetime.fromisoformat(a.replace("Z", "+00:00"))
    tb = datetime.fromisoformat(b.replace("Z", "+00:00"))
    return abs((ta - tb).total_seconds()) / 3600


def gap_hist(gaps: Iterable[float]) -> dict[str, int]:
    bins: Counter[str] = Counter()
    for g in gaps:
        bins[
            "0"
            if g == 0
            else "<=0.25"
            if g <= 0.25
            else "<=1"
            if g <= 1
            else "<=2"
            if g <= 2
            else "<=3"
            if g <= 3
            else "<=4"
            if g <= 4
            else ">4"
        ] += 1
    order = ("0", "<=0.25", "<=1", "<=2", "<=3", "<=4", ">4")
    return {k: bins[k] for k in order if bins[k]}


def measure(
    conn: sqlite3.Connection, runs_dir: str, first: str | None, last: str | None
) -> dict[str, Any]:
    recs = records(runs_dir, first, last)
    settled = settle_found(runs_dir)
    anchors = {
        int(x)
        for r in recs
        for x in (r.get("team1_id"), r.get("team2_id"))
        if isinstance(x, int)
    }
    days = sorted({str(r["kickoff_utc"])[:10] for r in recs})
    since = (
        int(datetime.fromisoformat(days[0]).replace(tzinfo=UTC).timestamp()) - 86400
        if days
        else 0
    )
    by_team = load_games(conn, SPORT_SLUG.values(), since, anchors)
    out: dict[str, Any] = {
        "first": first,
        "last": last,
        "days": len(days),
        "sports": {},
    }
    for sport in SPORT_SLUG:
        rs = [r for r in recs if r.get("sport") == sport]
        sec: dict[str, Any] = {
            "events": len(rs),
            "identified": sum(r["status"] == "IDENTIFIED" for r in rs),
        }
        gaps_settle = [
            _gap_h(
                str(settled[r["superbet_event_id"]]["sofascore_start_utc"]),
                str(r["kickoff_utc"]),
            )
            for r in rs
            if r["superbet_event_id"] in settled
            and settled[r["superbet_event_id"]].get("sofascore_start_utc")
        ]
        sec["settle_start_gap_h"] = gap_hist(gaps_settle)
        for w in WINDOWS_H:
            ws = w * 3600
            ident: Counter[str] = Counter()
            wrong = []
            for r in rs:
                if r["status"] != "IDENTIFIED":
                    continue
                status, g = predict(r, by_team, ws)
                if status == "PICK" and g is not None:
                    ok = g.event_id == r["sofascore_event_id"]
                    ident["correct" if ok else "WRONG"] += 1
                    if not ok:
                        wrong.append(
                            {
                                "superbet_event_id": r["superbet_event_id"],
                                "match": r["match_name"],
                                "kickoff": r["kickoff_utc"],
                                "pinned": r["sofascore_event_id"],
                                "picked": g.event_id,
                            }
                        )
                else:
                    ident[status] += 1
            rec: Counter[str] = Counter()
            checked: Counter[str] = Counter()
            disagree = []
            picks = []
            gaps_pick = []
            for r in rs:
                if r["status"] == "IDENTIFIED":
                    continue
                status, g = predict(r, by_team, ws)
                rec[status] += 1
                if status != "PICK" or g is None:
                    continue
                gaps_pick.append(
                    abs(
                        g.start_ts
                        - datetime.fromisoformat(
                            str(r["kickoff_utc"]).replace("Z", "+00:00")
                        ).timestamp()
                    )
                    / 3600
                )
                s = settled.get(r["superbet_event_id"])
                picks.append(
                    {
                        "superbet_event_id": r["superbet_event_id"],
                        "match": r["match_name"],
                        "kickoff": r["kickoff_utc"],
                        "reason": r.get("reason"),
                        "picked": g.event_id,
                        "settle": None if s is None else s["sofascore_event_id"],
                        "settle_method": None if s is None else s.get("match_method"),
                    }
                )
                if s is None:
                    checked["not_found_by_settle"] += 1
                elif s["sofascore_event_id"] == g.event_id:
                    checked["settle_agrees"] += 1
                else:
                    checked["SETTLE_DISAGREES"] += 1
                    disagree.append(picks[-1])
            sec[f"W{w:g}h"] = {
                "identified_backtest": dict(ident),
                "identified_wrong": wrong,
                "not_identified": dict(rec),
                "not_identified_picks_checked": dict(checked),
                "settle_disagrees": disagree,
                "pick_start_gap_h": gap_hist(gaps_pick),
                "picks": picks,
            }
        out["sports"][sport] = sec
    return out


def render(res: dict[str, Any]) -> str:
    lines = [
        f"# DAY_ANCHOR backtest {res['first']}..{res['last']} ({res['days']} days)",
        "",
    ]
    for sport, sec in res["sports"].items():
        lines += [
            f"## {sport}: {sec['events']} events, {sec['identified']} identified",
            "",
            f"Start gap |Sofascore - Superbet| of the settle's games (h): "
            f"{sec['settle_start_gap_h']}",
            "",
            "| W | IDENTIFIED, opponent hidden | precision | NOT_IDENTIFIED: rule says "
            "| picks vs settle | pick start gap (h) |",
            "|---|---|---|---|---|---|",
        ]
        for w in WINDOWS_H:
            x = sec[f"W{w:g}h"]
            ib = x["identified_backtest"]
            n_pick = ib.get("correct", 0) + ib.get("WRONG", 0)
            prec = f"{ib.get('correct', 0)}/{n_pick}" if n_pick else "-"
            lines.append(
                f"| {w:g} h | {ib} | {prec} | {x['not_identified']} | "
                f"{x['not_identified_picks_checked']} | {x['pick_start_gap_h']} |"
            )
        for w in WINDOWS_H:
            x = sec[f"W{w:g}h"]
            for item in x["identified_wrong"]:
                lines.append(f"- W{w:g} WRONG on IDENTIFIED: {item}")
            for item in x["settle_disagrees"]:
                lines.append(f"- W{w:g} SETTLE DISAGREES: {item}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from", dest="first", default=None)
    ap.add_argument("--to", dest="last", default=None)
    ap.add_argument("--db-path", default=None)
    ap.add_argument("--runs-dir", default=None)
    ap.add_argument("--md-out", default=None)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()
    config = SofaConfig.from_env()
    conn = sqlite3.connect(f"file:{args.db_path or config.db_path}?mode=ro", uri=True)
    try:
        res = measure(conn, args.runs_dir or config.runs_dir, args.first, args.last)
    finally:
        conn.close()
    md = render(res)
    print(md)
    if args.md_out:
        Path(args.md_out).write_text(md, encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
