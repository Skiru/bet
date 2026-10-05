#!/usr/bin/env python3
"""SPORT_IDENTITY replayed offline on past days, and its golden set (plan
2026-10-05 production grade, F1.2).

Per sport (hockey, basketball, volleyball, CS2) and day: the day's Superbet
board as the snapshots last quoted it (sport_identity.board_events), the team
ids as TeamResolver gives them from the database today (read-only - an entity
RESOLVE or the settle verified after the day is visible, so the resolution is
optimistic; on 10-05 live, 15 events were TEAM_UNRESOLVED), and as the "next"
listing of the asked team every game of that team the cache holds from D-1 to
D+8 (sofa_listed_event - indexed from the pages RESOLVE, SETTLE and the
backfills fetched, also after the game). So this measures the MATCHER given a
listing, not whether the bridge would have returned one before the start.

The answer key is the settle's own Sofascore id (settled.json), which a
different matcher found after the game (settle_shadow.find_event / CS2
settle). Per event: CORRECT (same id), WRONG (another id - a precision
defect, or a settle defect: see the report), MISSED (the settle found one,
the replay did not, with the replay's reason), ID_NO_TRUTH (the replay found
one, the settle did not) and BOTH_NONE.

`--golden-out DIR` writes DIR/sport_identity_golden_<sport>.json: the cases
whose identity is verifiable offline - the settle's id is in the cache,
finished, starts within MAX_START_GAP of Superbet's kickoff, its final score
equals the settle's graded score (t1_full / t2_full; CS2 the maps won), and
each side is confirmed independently of the matcher's opponent rule (the
board name's RESOLVE-verified entity is that side's id, or its marker-free
name scores above NAME_MATCH_THRESHOLD at a compatible squad level; CS2
cs2.esports_score) - or listed in REVIEWED (read by a person, with why). A
settle id that is a postponed copy of a game played under another id is
replaced by the played one (POSTPONED_TWIN, reviewed: 10-03 Yunost - Zhlobin,
Panter - Liepaja, 10-04 Spisska Nova Ves - Slovan). Each case carries the
listing the replay asked for, trimmed to the fields the matcher reads, so
tests/sofa/test_sport_identity_golden.py re-runs the matcher offline.
Superbet's own result is not recorded anywhere (the snapshots are prices
only), so "the Superbet-side result" is not part of the check.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sport_identity.py \\
        --from 2026-09-29 --to 2026-10-04 [--sport hockey] \\
        [--golden-out docs/sofa/evidence] [--cases-per-sport 120]

Measurement only: the DB is opened read-only; runs/ is only read.
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import cs2  # noqa: E402
from bet.sofa import sport_identity as si  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.fixture_status import NOT_AS_SCHEDULED  # noqa: E402
from bet.sofa.names import normalize_name  # noqa: E402
from bet.sofa.resolve import NAME_MATCH_THRESHOLD, part_score  # noqa: E402

SLUGS = {"hockey": "ice-hockey", "basketball": "basketball",
         "volleyball": "volleyball", "cs2": "esports"}
LISTING_BEFORE = timedelta(days=1)
LISTING_AFTER = timedelta(days=8)
# A golden case keeps the asked team's games within this of the kickoff:
# every game the matcher could weigh (shadow MAX_START_GAP, CS2 pick_event's
# MATCH_WINDOW), with an hour to spare.
GOLDEN_SPAN = {"cs2": cs2.MATCH_WINDOW + timedelta(hours=1)}
GOLDEN_SPAN_SHADOW = si.MAX_START_GAP + timedelta(hours=1)
# Superbet event ids whose identity a person read (2026-10-05, F1.2) where
# the independent name / id check cannot confirm a side: sponsor names,
# rebrands, Polish exonyms. Each was read against Sofascore's name, start and
# competition in the replay output.
#
# Read and NOT admitted (the settle's own id is doubtful - see the F1.2
# report): 15247563 Texas A&M Aggies (K) read as "Texas AM Commerce Lions",
# 15210193 "U. De Santiago" read as "Universidad Catolica", 14979678 "Kataja
# Talents" read as Kataja Basket (Kataja Basket Talents is team 395581),
# 14979711 "Umea IK" read as "Umea BSKT", 15025535 "MAC Budapeszt" read as
# "Budapest Jegkorong Akademia HC", 15242006 "Keyd Stars" read as
# "ex-Keyd Stars".
_REVIEW_NOTE = ("read by a person 2026-10-05 (F1.2): the same game under a "
                "sponsor name, rebrand, exonym or abbreviation")
REVIEWED: dict[str, str] = {sid: _REVIEW_NOTE for sid in (
    # hockey
    "14860501", "14979723", "14995049", "15025290", "15025434", "15025546",
    "15025704", "15039960", "15039977", "15040167", "15041026", "15041444",
    "15041792", "15057188", "15057196", "15058564",
    # basketball
    "14979679", "14731600", "15144910", "14979727", "14979728", "14979734",
    "14812561", "14596822", "15165102", "15009931", "15009932", "15009969",
    "15246756", "15025214", "15025369", "15132367", "15025438", "15208223",
    "14628345", "15025673", "15025685", "15025695", "15181738", "15025721",
    "15025733", "15247139", "15040318", "15195920", "15008632", "15195910",
    "15041505", "15041525", "15041583", "15041586", "15042288", "15041893",
    "15042115", "15042452", "15042562", "15042769", "15057240", "15057366",
    "15197917", "15164494", "15058254", "14720450", "15025382", "15058349",
    "14657617", "14875177", "15058603", "14937450", "15132810",
    # volleyball
    "14979690", "15198060", "15198051", "15213965", "15213966", "15238983",
    "15208437", "15266486", "15235661", "15041415", "15041552", "15041572",
    "15163107", "15042227", "15282057", "15057498", "15295383", "15296308",
    "15058861",
)}


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _days(start: str, end: str) -> list[str]:
    d0, d1 = datetime.strptime(start, "%Y-%m-%d"), datetime.strptime(end, "%Y-%m-%d")
    return [(d0 + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range((d1 - d0).days + 1)]


def settled_events(runs_dir: str, sport: str, date: str) -> dict[str, dict[str, Any]]:
    from bet.sofa import sport_coupon

    path = sport_coupon.day_dir(runs_dir, sport, date) / "settled.json"  # type: ignore[arg-type]
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    raw = doc.get("events") or {}
    items = raw.items() if isinstance(raw, dict) else raw
    return {str(k): dict(v) for k, v in items}


def load_listed(conn: sqlite3.Connection, slug: str, lo: datetime, hi: datetime
                ) -> tuple[dict[int, list[dict[str, Any]]], dict[int, dict[str, Any]]]:
    """(team id -> its cached games, event id -> event) between lo and hi."""
    by_team: dict[int, list[dict[str, Any]]] = defaultdict(list)
    by_id: dict[int, dict[str, Any]] = {}
    for (text,) in conn.execute(
            "SELECT event_json FROM sofa_listed_event WHERE sport = ? "
            "AND start_ts >= ? AND start_ts < ?",
            (slug, int(lo.timestamp()), int(hi.timestamp()))):
        try:
            e = json.loads(text)
        except ValueError:
            continue
        if not isinstance(e.get("id"), int):
            continue
        by_id[int(e["id"])] = e
        for side in ("homeTeam", "awayTeam"):
            tid = (e.get(side) or {}).get("id")
            if isinstance(tid, int):
                by_team[tid].append(e)
    return by_team, by_id


class CachedListing:
    """entity_events from the cache: the team's games in [lo, hi)."""

    def __init__(self, by_team: dict[int, list[dict[str, Any]]], lo: datetime,
                 hi: datetime) -> None:
        self.by_team = by_team
        self.lo, self.hi = int(lo.timestamp()), int(hi.timestamp())
        self.asked: list[int] = []

    def entity_events(self, entity_id: int, kind: Any, page: int) -> Any | None:
        self.asked.append(entity_id)
        return {"events": [e for e in self.by_team.get(entity_id, [])
                           if self.lo <= int(e.get("startTimestamp") or 0) < self.hi]}


def classify(rec: dict[str, Any], truth: dict[str, Any] | None) -> str:
    tid = (truth or {}).get("sofascore_event_id")
    got = rec.get("sofascore_event_id") if rec["status"] == si.IDENTIFIED else None
    if got is not None and tid is not None:
        return "CORRECT" if int(got) == int(tid) else "WRONG"
    if got is not None:
        return "ID_NO_TRUTH"
    if tid is not None:
        why = rec.get("reason") if rec["status"] == si.NOT_IDENTIFIED else rec["status"]
        return f"MISSED:{why}"
    return f"BOTH_NONE:{(truth or {}).get('state')}"


# --- golden -----------------------------------------------------------------------


def _score(e: dict[str, Any], side: str) -> int | None:
    v = (e.get(side) or {}).get("current")
    return int(v) if isinstance(v, int) else None


def truth_score(sport: str, truth: dict[str, Any]) -> tuple[int, int] | None:
    """(team1, team2) as the settle graded it."""
    if sport == "cs2":
        maps = truth.get("maps") or []
        if not maps:
            return None
        t1 = sum(1 for m in maps if m[0] > m[1])
        return t1, sum(1 for m in maps if m[1] > m[0])
    a, b = truth.get("t1_full"), truth.get("t2_full")
    return (int(a), int(b)) if isinstance(a, int) and isinstance(b, int) else None


def _twin(e: dict[str, Any], by_id: dict[int, dict[str, Any]],
          by_team: dict[int, list[dict[str, Any]]]) -> dict[str, Any] | None:
    """The played game of a postponed copy: the same two teams, the same
    start, finished."""
    def pair(x: dict[str, Any]) -> set[Any]:
        return {(x.get(side) or {}).get("id") for side in ("homeTeam", "awayTeam")}

    hid = (e.get("homeTeam") or {}).get("id")
    if not isinstance(hid, int):
        return None
    out = [c for c in by_team.get(hid, []) if c["id"] != e["id"]
           and pair(c) == pair(e) and c.get("startTimestamp") == e.get("startTimestamp")
           and (c.get("status") or {}).get("type") == "finished"]
    return out[0] if len(out) == 1 else None


def _side_check(conn: sqlite3.Connection, sport: str, board: str, ev_id: int | None,
                ev_name: str) -> str | None:
    """How this side is confirmed without the matcher's opponent rule."""
    if sport == "cs2":
        score = cs2.esports_score(cs2.esports_name(board), cs2.esports_name(ev_name))
        return "name" if score > NAME_MATCH_THRESHOLD else None
    key = normalize_name(board)
    row = conn.execute("SELECT sofascore_id, status FROM sofa_entity "
                       "WHERE sport = ? AND query_key = ?",
                       (SLUGS[sport], key)).fetchone()
    if row and row[1] == "verified" and ev_id is not None and int(row[0]) == ev_id:
        return "verified_entity"
    b = normalize_name(ev_name)
    if part_score(key, b) > NAME_MATCH_THRESHOLD and si.same_squad(key, b):
        return "name"
    return None


def trim(e: dict[str, Any]) -> dict[str, Any]:
    """The fields the matcher (and the golden check) reads."""
    t = e.get("tournament") or {}
    cat = t.get("category") or {}
    ut = t.get("uniqueTournament") or {}

    def team(x: dict[str, Any] | None) -> dict[str, Any]:
        x = x or {}
        return {k: x[k] for k in ("id", "name", "gender") if k in x}

    out: dict[str, Any] = {
        "id": e["id"], "startTimestamp": e.get("startTimestamp"),
        "status": {"type": (e.get("status") or {}).get("type")},
        "tournament": {
            "id": t.get("id"), "name": t.get("name"),
            "category": {"name": cat.get("name"),
                         "sport": {"slug": (cat.get("sport") or {}).get("slug")}},
            "uniqueTournament": {"id": ut.get("id"), "name": ut.get("name")}},
        "homeTeam": team(e.get("homeTeam")), "awayTeam": team(e.get("awayTeam")),
        "homeScore": {"current": _score(e, "homeScore")},
        "awayScore": {"current": _score(e, "awayScore")},
    }
    if "bestOf" in e:
        out["bestOf"] = e["bestOf"]
    return out


def golden_case(conn: sqlite3.Connection, sport: str, date: str, rec: dict[str, Any],
                truth: dict[str, Any], by_id: dict[int, dict[str, Any]],
                by_team: dict[int, list[dict[str, Any]]], ids: dict[str, int | None],
                qids: dict[str, int | None]) -> tuple[dict[str, Any] | None, str]:
    """A verified case, or (None, why it is not verifiable offline)."""
    tid = truth.get("sofascore_event_id")
    if not isinstance(tid, int) or truth.get("home_is_team1") is None:
        return None, "NO_SETTLE_ID"
    e = by_id.get(tid)
    if e is None:
        return None, "NOT_IN_CACHE"
    verified_by = None
    if (e.get("status") or {}).get("type") in NOT_AS_SCHEDULED:
        twin = _twin(e, by_id, by_team)
        if twin is None:
            return None, "SETTLE_ID_POSTPONED"
        e, verified_by = twin, "POSTPONED_TWIN"
    elif (e.get("status") or {}).get("type") != "finished":
        return None, "NOT_FINISHED"
    kick = _utc(rec["kickoff_utc"])
    start = datetime.fromtimestamp(int(e["startTimestamp"]), UTC)
    if abs(start - kick) > si.MAX_START_GAP:
        return None, "START_GAP_OVER_1H"
    home_is_t1 = bool(truth["home_is_team1"])
    if verified_by == "POSTPONED_TWIN" and _reversed(e, by_id[tid]):
        # the played copy reads the other way round from the postponed one
        home_is_t1 = not home_is_t1
    hs, as_ = _score(e, "homeScore"), _score(e, "awayScore")
    want = truth_score(sport, truth)
    if verified_by != "POSTPONED_TWIN":
        if want is None or hs is None or as_ is None:
            return None, "NO_SCORE"
        got = (hs, as_) if home_is_t1 else (as_, hs)
        if got != want:
            return None, "SCORE_DISAGREES"
    h, a = e.get("homeTeam") or {}, e.get("awayTeam") or {}
    t1_side, t2_side = (h, a) if home_is_t1 else (a, h)
    checks = {
        "team1": _side_check(conn, sport, rec["team1"], t1_side.get("id"),
                             str(t1_side.get("name") or "")),
        "team2": _side_check(conn, sport, rec["team2"], t2_side.get("id"),
                             str(t2_side.get("name") or "")),
    }
    if verified_by is None:
        if all(checks.values()):
            verified_by = "INDEPENDENT_NAMES"
        elif rec["superbet_event_id"] in REVIEWED:
            verified_by = "REVIEWED"
        else:
            return None, "SIDE_UNCONFIRMED"
    span = GOLDEN_SPAN.get(sport, GOLDEN_SPAN_SHADOW)
    lo, hi = kick - span, kick + span
    asked = [i for i in (ids["team1"], ids["team2"], qids["team1"], qids["team2"])
             if i is not None]
    listings = {
        str(t): [trim(x) for x in by_team.get(t, [])
                 if lo.timestamp() <= int(x.get("startTimestamp") or 0)
                 < hi.timestamp()]
        for t in dict.fromkeys(asked)
    }
    case = {
        "date": date, "sport": sport, "superbet_event_id": rec["superbet_event_id"],
        "match_name": rec["match_name"], "team1": rec["team1"], "team2": rec["team2"],
        "kickoff_utc": rec["kickoff_utc"], "tournament": rec.get("tournament"),
        "expected_sofascore_event_id": int(e["id"]),
        "expected_home_is_team1": home_is_t1,
        "sofascore_match": f"{h.get('name')} - {a.get('name')}",
        "verified_by": verified_by, "side_checks": checks,
        "score_team1_team2": list(want) if want else None,
        "team_ids": ids, "query_ids": qids, "listings": listings,
        "replay_status": rec["status"], "replay_reason": rec.get("reason"),
        "replay_method": rec.get("match_method"),
    }
    if verified_by == "REVIEWED":
        case["review_note"] = REVIEWED[rec["superbet_event_id"]]
    return case, verified_by


def _reversed(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (a.get("homeTeam") or {}).get("id") == (b.get("awayTeam") or {}).get("id")


# --- the run ----------------------------------------------------------------------


def run_sport(conn: sqlite3.Connection, runs_dir: str, sport: str, days: list[str],
              want_golden: bool, show_unconfirmed: bool = False
              ) -> tuple[Counter[str], list[dict[str, Any]], Counter[str], list[str]]:
    lo = datetime.strptime(days[0], "%Y-%m-%d").replace(tzinfo=UTC) - LISTING_BEFORE
    hi = datetime.strptime(days[-1], "%Y-%m-%d").replace(tzinfo=UTC) + LISTING_AFTER
    by_team, by_id = load_listed(conn, SLUGS[sport], lo, hi)
    tally: Counter[str] = Counter()
    golden: list[dict[str, Any]] = []
    why_not: Counter[str] = Counter()
    wrong: list[str] = []
    for d in days:
        truth = settled_events(runs_dir, sport, d)
        events = si.board_events(runs_dir, sport, d)
        start, _ = si.day_window(d)
        client = CachedListing(by_team, start - LISTING_BEFORE, start + LISTING_AFTER)
        resolver = si.TeamResolver(conn, int(start.timestamp()))
        records, _ = si.identify(events, client, None, resolver.team_id, start, d,
                                 None, resolver.query_id)
        for rec in records:
            t = truth.get(rec["superbet_event_id"])
            k = classify(rec, t)
            if k == "WRONG":
                settle_ev = by_id.get(int((t or {}).get("sofascore_event_id") or 0))
                twin = _twin(settle_ev, by_id, by_team) if settle_ev and (
                    (settle_ev.get("status") or {}).get("type") in NOT_AS_SCHEDULED
                ) else None
                if twin is not None and twin["id"] == rec.get("sofascore_event_id"):
                    # the settle pinned the postponed copy; the game was
                    # played under the id the replay found
                    k = "CORRECT_SETTLE_PINNED_POSTPONED_COPY"
            tally[k] += 1
            if rec["status"] == si.IDENTIFIED:
                tally["method:" + str(rec.get("match_method"))
                      + (":query_only" if rec.get("query_only") else "")] += 1
            if k in ("WRONG", "ID_NO_TRUTH", "CORRECT_SETTLE_PINNED_POSTPONED_COPY"):
                tt = t or {}
                wrong.append(
                    f"{d} {k} {rec['match_name']} {rec['kickoff_utc']} -> "
                    f"{rec.get('sofascore_event_id')} {rec.get('sofascore_match')}"
                    f" | settle {tt.get('sofascore_event_id')} "
                    f"{tt.get('sofascore_match')} {tt.get('state')}")
            if not want_golden or t is None:
                continue
            ids = {"team1": resolver.team_id(sport, rec["team1"]),
                   "team2": resolver.team_id(sport, rec["team2"])}
            qids = {"team1": resolver.query_id(sport, rec["team1"]),
                    "team2": resolver.query_id(sport, rec["team2"])}
            case, why = golden_case(conn, sport, d, rec, t, by_id, by_team, ids, qids)
            why_not[why] += 1
            if case is not None:
                golden.append(case)
            elif why == "SIDE_UNCONFIRMED" and show_unconfirmed:
                print(f"  UNCONFIRMED {sport} {d} {rec['superbet_event_id']} "
                      f"{rec['match_name']} {rec['kickoff_utc']} "
                      f"{rec.get('tournament')} | settle "
                      f"{t.get('sofascore_event_id')} {t.get('sofascore_match')}"
                      f" | replay {rec['status']} {rec.get('match_method')}")
    return tally, golden, why_not, wrong


def pick_cases(cases: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Every hard case (a reviewed one, a postponed twin, a replay that did
    not identify it or did so through the opponent rule, no exact team id
    on either side), then a seeded sample of the rest."""
    def hard(c: dict[str, Any]) -> bool:
        return (c["verified_by"] != "INDEPENDENT_NAMES"
                or c["replay_status"] != si.IDENTIFIED
                or c["replay_method"] == "LISTING_ID_AND_OPPONENT"
                or set(c["team_ids"].values()) == {None})
    first = [c for c in cases if hard(c)]
    rest = [c for c in cases if not hard(c)]
    random.Random(20261005).shuffle(rest)
    keep = first + rest[:max(0, n - len(first))]
    return sorted(keep, key=lambda c: (c["date"], c["kickoff_utc"],
                                       c["superbet_event_id"]))


def dump_golden(doc: dict[str, Any]) -> str:
    """The header indented, one case per line: diffable, a third the size."""
    head = {k: v for k, v in doc.items() if k != "cases"}
    text = json.dumps(head, indent=1, ensure_ascii=False)[:-2]
    lines = ",\n".join(json.dumps(c, ensure_ascii=False, separators=(",", ":"))
                       for c in doc["cases"])
    return f'{text},\n "cases": [\n{lines}\n ]\n}}\n'


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--sport", action="append", choices=list(si.SPORT_KEYS))
    ap.add_argument("--golden-out")
    ap.add_argument("--cases-per-sport", type=int, default=120)
    ap.add_argument("--show-wrong", action="store_true")
    ap.add_argument("--show-unconfirmed", action="store_true")
    args = ap.parse_args()
    config = SofaConfig.from_env()
    conn = sqlite3.connect(f"file:{config.db_path}?mode=ro", uri=True)
    days = _days(args.start, args.end)
    summary: dict[str, Any] = {}
    try:
        for sport in args.sport or list(si.SPORT_KEYS):
            tally, golden, why_not, wrong = run_sport(
                conn, config.runs_dir, sport, days, bool(args.golden_out),
                args.show_unconfirmed)
            board = sum(v for k, v in tally.items() if not k.startswith("method:"))
            settled = sum(v for k, v in tally.items()
                          if k.startswith(("CORRECT", "WRONG", "MISSED")))
            correct = sum(v for k, v in tally.items() if k.startswith("CORRECT"))
            summary[sport] = {
                "board_events": board, "settle_found": settled,
                "correct": correct, "wrong": tally["WRONG"],
                "recall_vs_settle": round(correct / settled, 3) if settled else None,
                "recall_vs_board": round(correct / board, 3) if board else None,
                "tally": dict(sorted(tally.items(), key=lambda kv: -kv[1])),
            }
            if args.show_wrong:
                for line in wrong:
                    print(f"  {sport} {line}")
            if args.golden_out:
                cases = pick_cases(golden, args.cases_per_sport)
                identified = sum(c["replay_status"] == si.IDENTIFIED for c in cases)
                doc = {
                    "built_at_utc": si.iso(datetime.now(UTC)),
                    "builder": "scripts/sofa/measure_sport_identity.py",
                    "sport": sport, "days": [days[0], days[-1]],
                    "criteria": __doc__.split("`--golden-out DIR`")[1].split(
                        "    PYTHONPATH")[0].strip(),
                    "verifiable_cases": len(golden),
                    "settled_cases_by_outcome": dict(why_not),
                    "cases_kept": len(cases),
                    "identified_at_build": identified,
                    "cases": cases,
                }
                out = Path(args.golden_out) / f"sport_identity_golden_{sport}.json"
                out.write_text(dump_golden(doc), encoding="utf-8")
                summary[sport]["golden"] = {"path": str(out), "kept": len(cases),
                                            "verifiable": len(golden),
                                            "identified": identified,
                                            "by_outcome": dict(why_not)}
    finally:
        conn.close()
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    return 1 if any(s["wrong"] for s in summary.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
