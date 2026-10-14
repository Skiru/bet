#!/usr/bin/env python3
"""Identity coverage, every sport and entity type (read-only evidence).

The yardstick of the identity map plan
(docs/sofa/history/PLAN_MAPA_DRUZYN_2026-10-14.md, step K0): how many
Superbet events, players and tournaments end a day in an UNEXPLAINED state -
neither IDENTIFIED (with a Sofascore id) nor deliberately set aside - per
kickoff day (UTC), per sport and per entity type.

Each item is in one of four states:

- IDENTIFIED - it has a Sofascore id;
- EXCLUDED - deliberately not identified (a CS2 1x1 loop, a
  DUPLICATE_SUPERBET_TEAM refusal); not a mapping failure;
- EXPLAINED - identity known, missing for another reason (a footballer
  found in the squads who never started: the sample is his starts);
- UNEXPLAINED - anything else, with today's reason code. Until the plan's
  NOT_ON_SOFASCORE / NEEDS_ALIAS states exist, every failure is here.

Sources (all on disk; data/sofa.db opened read-only):

- events of hockey / basketball / volleyball / CS2: runs/sofa/<d>/sport_fixtures.json
  (deduplicated by Superbet event id, the latest record wins);
- events of football / tennis: runs/sofa/<d>/01_board.json entries whose
  Superbet id is in no 02_fixtures.json (RESOLVE writes only gap counters,
  so the gap is reconstructed); each gap is diagnosed offline - how many of
  its sides the verified sofa_entity map knows, and whether a known side's
  cached listing (sofa_entity_events, today's state) holds a game within
  LISTING_WINDOW_H of the Superbet start;
- football players: runs/sofa/<d>/03_samples.json (players + NO_ENTITY_FOUND
  gaps), one item per (Sofascore event, Superbet player name);
- hockey / basketball players: runs/sofa/shadow/<sport>/<d>/player_model.jsonl,
  the latest row per (Superbet event, subject);
- CS2 players: runs/sofa/cs2/<d>/snapshots.jsonl player lines; the event's
  identity from sport_fixtures.json, the nickname looked up in the map
  history before the kickoff day the way cs2_engine.player_id does;
- tournaments: Superbet tournament -> Sofascore competition ids learnable
  from the identified events (a summary, not a per-day state).

Name diagnostics use today's database (TeamResolver, sofa_entity): a name
learned after a day reads as known for that day too. That is the point of
the "learnable" column - an upper bound on what learning from pinned events
recovers, not what the day saw.

  PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_team_identity.py \
      [--from 2026-10-05] [--to 2026-10-14] [--sport all|football|...] \
      [--md-out f] [--json-out f]
"""

from __future__ import annotations

import argparse
import ast
import glob
import json
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import cs2, cs2_engine  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.names import normalize_name  # noqa: E402
from bet.sofa.sport_identity import TeamResolver  # noqa: E402

ALL_SPORTS = ("football", "tennis", "hockey", "basketball", "volleyball", "cs2")
RESOLVE_SPORTS = ("football", "tennis")
IDENTITY_SPORTS = ("hockey", "basketball", "volleyball", "cs2")
PLAYER_MODEL_SPORTS = ("hockey", "basketball")

IDENTIFIED = "IDENTIFIED"
EXCLUDED = "EXCLUDED"
EXPLAINED = "EXPLAINED"
UNEXPLAINED = "UNEXPLAINED"
STATES = (IDENTIFIED, EXCLUDED, EXPLAINED, UNEXPLAINED)

# player_model reasons that are an identity failure; THIN_SAMPLE and a
# priced row are an identified player.
PLAYER_MODEL_IDENTITY_REASONS = frozenset(
    {"TEAM_UNRESOLVED", "NOT_IN_HISTORY", "NAME_UNCERTAIN"})
LISTING_WINDOW_H = 3.0
LAST_DAYS = 7

_PLAYER_GAP = re.compile(
    r"""^player (?P<name>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*") (?P<rest>.*)$""")


@dataclass(frozen=True)
class Item:
    sport: str
    entity: str  # event | player
    day: str  # kickoff day, UTC
    key: str
    state: str
    reason: str | None = None
    name: str = ""


@dataclass
class NameStats:
    names: int = 0
    unresolved_now: int = 0
    learnable: int = 0
    conflicts: list[tuple[str, list[int]]] = field(default_factory=list)
    unresolved_in_unexplained: int = 0
    top_unlearnable: list[tuple[int, str, str]] = field(default_factory=list)


def in_window(day: str, first: str | None, last: str | None) -> bool:
    return (first is None or day >= first) and (last is None or day <= last)


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def iter_jsonl(path: str) -> Iterator[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def run_day_dirs(runs_dir: str, filename: str) -> list[tuple[str, str]]:
    """(run date, path) of every runs/sofa/<YYYY-MM-DD>/<filename>, in order."""
    out = []
    for p in sorted(glob.glob(str(Path(runs_dir) / "*" / filename))):
        day = Path(p).parent.name
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            out.append((day, p))
    return out


# --- events of the measured sports --------------------------------------------------


def sport_fixture_records(runs_dir: str) -> dict[str, dict[str, Any]]:
    """Superbet event id -> its latest sport_fixtures.json record (by the
    file's date, then its created_at_utc)."""
    recs: dict[str, dict[str, Any]] = {}
    for day, path in run_day_dirs(runs_dir, "sport_fixtures.json"):
        doc = load_json(path)
        created = str(doc.get("created_at_utc") or "")
        for r in doc.get("fixtures") or []:
            rank = (day, created)
            key = str(r["superbet_event_id"])
            old = recs.get(key)
            if old is None or rank >= old["_rank"]:
                recs[key] = {**r, "_rank": rank}
    return recs


def is_excluded_fixture(r: dict[str, Any]) -> bool:
    return (r.get("status") == "DUPLICATE_SUPERBET_TEAM"
            or "1x1" in str(r.get("tournament") or "").lower())


def fixture_item(r: dict[str, Any]) -> Item:
    day = str(r["kickoff_utc"])[:10]
    if is_excluded_fixture(r):
        why = ("DUPLICATE_SUPERBET_TEAM" if r.get("status") == "DUPLICATE_SUPERBET_TEAM"
               else "1x1")
        return Item(r["sport"], "event", day, str(r["superbet_event_id"]),
                    EXCLUDED, why, r.get("match_name") or "")
    if r.get("status") == IDENTIFIED:
        return Item(r["sport"], "event", day, str(r["superbet_event_id"]),
                    IDENTIFIED, None, r.get("match_name") or "")
    return Item(r["sport"], "event", day, str(r["superbet_event_id"]),
                UNEXPLAINED, str(r.get("reason") or r.get("status")),
                r.get("match_name") or "")


def side_ids(r: dict[str, Any]) -> tuple[int | None, int | None] | None:
    """(team1 id, team2 id) of an IDENTIFIED record, else None."""
    if r.get("status") != IDENTIFIED or r.get("home_is_team1") is None:
        return None
    h, a = r.get("home_id"), r.get("away_id")
    return (h, a) if r["home_is_team1"] else (a, h)


def name_key(sport: str, name: str) -> str:
    return str(cs2.esports_name(name) if sport == "cs2" else normalize_name(name))


def team_name_stats(sport: str, recs: Iterable[dict[str, Any]],
                    resolver: TeamResolver) -> NameStats:
    """Distinct Superbet team names of the sport's non-excluded events: how
    many today's resolver leaves without an id, how many of those an
    IDENTIFIED event already pinned (learnable), and pinned-name conflicts."""
    main = [r for r in recs if not is_excluded_fixture(r)]
    resolved: dict[str, int | None] = {}

    def rid(name: str) -> int | None:
        if name not in resolved:
            resolved[name] = resolver.team_id(sport, name)
        return resolved[name]

    events_of: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in main:
        for nm in (r["team1"], r["team2"]):
            events_of[nm].append(r)
    learned: dict[str, set[int]] = defaultdict(set)
    for r in main:
        ids = side_ids(r)
        if not ids:
            continue
        for nm, sid in zip((r["team1"], r["team2"]), ids, strict=True):
            if sid is not None and rid(nm) is None:
                learned[name_key(sport, nm)].add(int(sid))
    unresolved = [nm for nm in events_of if rid(nm) is None]
    learnable = [nm for nm in unresolved
                 if len(learned.get(name_key(sport, nm), ())) == 1]
    stats = NameStats(
        names=len(events_of),
        unresolved_now=len(unresolved),
        learnable=len(learnable),
        conflicts=sorted((k, sorted(v)) for k, v in learned.items() if len(v) > 1),
    )
    in_unexp = [nm for nm in unresolved
                if any(e.get("status") != IDENTIFIED for e in events_of[nm])]
    stats.unresolved_in_unexplained = len(in_unexp)
    never = [nm for nm in unresolved if name_key(sport, nm) not in learned]
    stats.top_unlearnable = sorted(
        ((len(events_of[nm]), nm,
          Counter(str(e.get("tournament")) for e in events_of[nm]).most_common(1)[0][0])
         for nm in never), key=lambda x: (-x[0], x[1]))[:15]
    return stats


# --- events of football / tennis (RESOLVE) ------------------------------------------


def verified_id(conn: sqlite3.Connection, sport: str, name: str) -> int | None:
    row = conn.execute(
        "SELECT sofascore_id FROM sofa_entity WHERE sport = ? AND query_key = ? "
        "AND status = 'verified'", (sport, normalize_name(name))).fetchone()
    return None if row is None or row[0] is None else int(row[0])


def listing_has_game(conn: sqlite3.Connection, team_id: int, kickoff_ts: int,
                     window_h: float = LISTING_WINDOW_H) -> bool:
    """Does any cached listing page of the team hold one of its games within
    window_h of the start (today's cache: a past day's 'next' page may have
    rolled into 'last')."""
    for (txt,) in conn.execute(
            "SELECT events_json FROM sofa_entity_events WHERE sofascore_entity_id = ?",
            (team_id,)):
        try:
            events = json.loads(txt).get("events") or []
        except (ValueError, AttributeError):
            continue
        for e in events:
            st = e.get("startTimestamp")
            if not isinstance(st, int) or abs(st - kickoff_ts) > window_h * 3600:
                continue
            ids = ((e.get("homeTeam") or {}).get("id"),
                   (e.get("awayTeam") or {}).get("id"))
            if team_id in ids:
                return True
    return False


def resolve_gap_reason(known: int, game_in_listing: bool) -> str:
    """A RESOLVE gap's offline diagnosis: sides the verified map knows, and
    for a known side whether its cached listing holds a game near the start."""
    if known == 0:
        return "GAP_NO_SIDE_KNOWN"
    tail = "GAME_IN_LISTING" if game_in_listing else "NO_GAME_IN_LISTING"
    return f"GAP_{'BOTH_SIDES' if known == 2 else 'ONE_SIDE'}_KNOWN_{tail}"


def board_sides(entry: dict[str, Any]) -> tuple[str, str]:
    name = str(entry.get("match_name") or "")
    if "·" in name:
        a, b = name.split("·", 1)
        if a.strip() and b.strip():
            return a.strip(), b.strip()
    return str(entry.get("side_a") or ""), str(entry.get("side_b") or "")


Tournaments = dict[str, dict[str, set[int]]]


def resolve_items(runs_dir: str, conn: sqlite3.Connection | None,
                  sports: Iterable[str]) -> tuple[list[Item], Tournaments]:
    """Football / tennis events: one item per Superbet event id of any board,
    IDENTIFIED when any day's 02_fixtures.json bridged it. Also returns the
    tournament map learnable from them: sport -> Superbet tournament id ->
    Sofascore competition ids."""
    wanted = set(sports)
    resolved_ids: set[str] = set()
    comp_of: dict[str, int | None] = {}
    for _, path in run_day_dirs(runs_dir, "02_fixtures.json"):
        try:
            fixtures = load_json(path)
        except ValueError:
            continue
        for f in fixtures if isinstance(fixtures, list) else []:
            for sb in f.get("superbet_event_ids") or []:
                resolved_ids.add(str(sb))
                comp_of[str(sb)] = f.get("competition_id")
    entries: dict[str, dict[str, Any]] = {}
    for day, path in run_day_dirs(runs_dir, "01_board.json"):
        try:
            board = load_json(path)
        except ValueError:
            continue
        for e in board if isinstance(board, list) else []:
            if e.get("sport") in wanted:
                entries[str(e["superbet_event_id"])] = {**e, "_run_day": day}
    items: list[Item] = []
    tours: Tournaments = defaultdict(dict)
    for sb, e in entries.items():
        sport = str(e["sport"])
        day = str(e.get("kickoff_utc") or e["_run_day"])[:10]
        tkey = str(e.get("tournament_id"))
        comps = tours[sport].setdefault(tkey, set())
        if sb in resolved_ids:
            comp = comp_of.get(sb)
            if comp is not None:
                comps.add(int(comp))
            items.append(Item(sport, "event", day, sb, IDENTIFIED, None,
                              str(e.get("match_name") or "")))
            continue
        reason = "RESOLVE_GAP"
        if conn is not None:
            a, b = board_sides(e)
            ids = [verified_id(conn, sport, s) for s in (a, b) if s]
            known = [i for i in ids if i is not None]
            ko = datetime.fromisoformat(str(e["kickoff_utc"]).replace("Z", "+00:00"))
            ts = int(ko.timestamp())
            in_listing = any(listing_has_game(conn, i, ts) for i in known)
            reason = resolve_gap_reason(len(known), in_listing)
        items.append(Item(sport, "event", day, sb, UNEXPLAINED, reason,
                          str(e.get("match_name") or "")))
    return items, dict(tours)


# --- players --------------------------------------------------------------------------


def parse_player_gap(detail: str) -> tuple[str, str] | None:
    """(Superbet player name, reason) of a SAMPLES player NO_ENTITY_FOUND
    detail, or None. NEVER_STARTED / NEVER_CAME_ON: named in the squads;
    NO_SQUAD_MATCH: matched nobody."""
    m = _PLAYER_GAP.match(detail)
    if not m:
        return None
    try:
        name = str(ast.literal_eval(m.group("name")))
    except (ValueError, SyntaxError):
        return None
    rest = m.group("rest")
    if rest.startswith("matched no squad member"):
        return name, "NO_SQUAD_MATCH"
    if "never started" in rest:
        return name, "NEVER_STARTED"
    if "never came on" in rest:
        return name, "NEVER_CAME_ON"
    return None


def football_player_items(runs_dir: str) -> list[Item]:
    """One item per (Sofascore event, Superbet player name): IDENTIFIED when
    any metric matched him on any day, EXPLAINED when he was found in the
    squads but never started (came on), UNEXPLAINED NO_SQUAD_MATCH otherwise."""
    best: dict[tuple[int, str], tuple[str, str | None, str]] = {}
    rank = {IDENTIFIED: 3, EXPLAINED: 2, UNEXPLAINED: 1}
    for day, path in run_day_dirs(runs_dir, "03_samples.json"):
        try:
            rows = load_json(path)
        except ValueError:
            continue
        for r in rows if isinstance(rows, list) else []:
            eid = int(r["sofascore_event_id"])
            found: list[tuple[str, str, str | None]] = []
            for p in (r.get("players") or {}).values():
                found.append((str(p.get("player")), IDENTIFIED, None))
            for g in r.get("gaps") or []:
                if g.get("reason") != "NO_ENTITY_FOUND" or not str(
                        g.get("metric", "")).startswith("player_"):
                    continue
                parsed = parse_player_gap(str(g.get("detail") or ""))
                if parsed is None:
                    continue
                gap_name, gap_why = parsed
                found.append((gap_name, UNEXPLAINED if gap_why == "NO_SQUAD_MATCH"
                              else EXPLAINED, gap_why))
            for name, state, why in found:
                old = best.get((eid, name))
                if old is None or rank[state] > rank[old[0]]:
                    best[(eid, name)] = (state, why, day)
    # The event's day: the run day of its sample (a SAMPLES day is its board's).
    return [Item("football", "player", day, f"{eid}|{name}", state, why, name)
            for (eid, name), (state, why, day) in best.items()]


def sport_player_items(runs_dir: str, sport: str) -> list[Item]:
    """Hockey / basketball: the latest player_model row per (Superbet event,
    subject); an identity reason is UNEXPLAINED, anything else IDENTIFIED."""
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    pattern = str(Path(runs_dir) / "shadow" / sport / "*" / "player_model.jsonl")
    for path in sorted(glob.glob(pattern)):
        for row in iter_jsonl(path):
            k = (str(row.get("superbet_event_id")), str(row.get("subject") or ""))
            stamp = (str(row.get("computed_at_utc") or ""),
                     str(row.get("fetched_at_utc") or ""))
            old = latest.get(k)
            if old is None or stamp >= old["_stamp"]:
                latest[k] = {**row, "_stamp": stamp}
    out = []
    for (eid, subject), row in latest.items():
        why = row.get("model_reason")
        state = UNEXPLAINED if why in PLAYER_MODEL_IDENTITY_REASONS else IDENTIFIED
        out.append(Item(sport, "player", str(row["kickoff_utc"])[:10],
                        f"{eid}|{subject}", state,
                        str(why) if state == UNEXPLAINED else None, subject))
    return out


def cs2_player_state(history: list[cs2_engine.MapRow], teams: Iterable[int],
                     nick: str) -> tuple[str, str | None]:
    """The way cs2_engine.player_id reads a nickname, split by why it fails:
    one id on a team's recent maps is IDENTIFIED; ids found only as namesakes
    (two ids on a team) NAME_UNCERTAIN; nothing NOT_IN_HISTORY."""
    folded = cs2.esports_name(nick)
    namesake = False
    for team in teams:
        ids = {pid for m in cs2_engine._team_maps(history, team)
               for t, pid, n, _ in m.players if t == team and n == folded}
        if len(ids) == 1:
            return IDENTIFIED, None
        if len(ids) > 1:
            namesake = True
    return UNEXPLAINED, "NAME_UNCERTAIN" if namesake else "NOT_IN_HISTORY"


def cs2_player_items(runs_dir: str, recs: dict[str, dict[str, Any]],
                     conn: sqlite3.Connection | None,
                     first: str | None, last: str | None) -> tuple[list[Item], int]:
    """CS2 player lines' nicknames, one item per (Superbet event, subject).
    Returns the items and the count of subjects whose event has no identity
    record (snapshots older than SPORT_IDENTITY), left out."""
    subjects: dict[tuple[str, str], str] = {}
    pattern = str(Path(runs_dir) / "cs2" / "*" / "snapshots.jsonl")
    for path in sorted(glob.glob(pattern)):
        for rec in iter_jsonl(path):
            day = str(rec.get("kickoff_utc") or "")[:10]
            if not in_window(day, first, last):
                continue
            for ln in rec.get("lines") or []:
                family = str(ln.get("family", ""))
                if family.startswith("player_") and ln.get("subject"):
                    subjects[(str(rec["superbet_event_id"]), str(ln["subject"]))] = day
    histories: dict[str, list[cs2_engine.MapRow]] = {}
    items: list[Item] = []
    no_record = 0
    for (eid, nick), day in sorted(subjects.items()):
        r = recs.get(eid)
        key = f"{eid}|{nick}"
        if r is None:
            no_record += 1
            continue
        if is_excluded_fixture(r):
            items.append(Item("cs2", "player", day, key, EXCLUDED,
                              "EVENT_EXCLUDED", nick))
            continue
        ids = side_ids(r)
        if ids is None:
            items.append(Item("cs2", "player", day, key, UNEXPLAINED,
                              "EVENT_NOT_IDENTIFIED", nick))
            continue
        if conn is None:
            continue
        if day not in histories:
            start = int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())
            histories[day] = cs2_engine.load_history(conn, start, None)
        teams = [i for i in ids if i is not None]
        state, why = cs2_player_state(histories[day], teams, nick)
        items.append(Item("cs2", "player", day, key, state, why, nick))
    return items, no_record


def sport_tournaments(recs: Iterable[dict[str, Any]],
                      sport: str) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    for r in recs:
        if r.get("sport") != sport or is_excluded_fixture(r):
            continue
        t = str(r.get("tournament"))
        out.setdefault(t, set())  # a tournament with no identified event counts too
        if r.get("status") == IDENTIFIED and r.get("competition_id") is not None:
            out[t].add(int(r["competition_id"]))
    return out


# --- summary ------------------------------------------------------------------------


def summarise(items: list[Item]) -> dict[str, Any]:
    """Per (sport, entity): totals by state, unexplained by reason, by day."""
    groups: dict[tuple[str, str], list[Item]] = defaultdict(list)
    for it in items:
        groups[(it.sport, it.entity)].append(it)
    out: dict[str, Any] = {}
    for (sport, entity), its in sorted(groups.items(), key=lambda kv: (
            ALL_SPORTS.index(kv[0][0]), kv[0][1])):
        days = sorted({i.day for i in its})
        last_days = days[-LAST_DAYS:]
        unexp = [i for i in its if i.state == UNEXPLAINED]
        by_day: dict[str, dict[str, Any]] = {}
        for d in days:
            di = [i for i in its if i.day == d]
            by_day[d] = {
                "total": len(di),
                **{s: sum(1 for i in di if i.state == s) for s in STATES},
                "reasons": dict(Counter(i.reason for i in di
                                        if i.state == UNEXPLAINED).most_common()),
            }
        out[f"{sport}/{entity}"] = {
            "sport": sport,
            "entity": entity,
            "days": len(days),
            "first": days[0] if days else None,
            "last": days[-1] if days else None,
            "total": len(its),
            **{s: sum(1 for i in its if i.state == s) for s in STATES},
            "unexplained_per_day": round(len(unexp) / len(days), 1) if days else 0.0,
            "unexplained_per_day_last7": round(
                sum(by_day[d][UNEXPLAINED] for d in last_days) / len(last_days), 1)
            if last_days else 0.0,
            "reasons": dict(Counter(i.reason for i in unexp).most_common()),
            "other_reasons": dict(Counter(
                f"{i.state}:{i.reason}" for i in its
                if i.state in (EXCLUDED, EXPLAINED)).most_common()),
            "by_day": by_day,
        }
    return out


def tournament_summary(tours: Tournaments) -> dict[str, Any]:
    out = {}
    for sport in ALL_SPORTS:
        t = tours.get(sport)
        if not t:
            continue
        out[sport] = {
            "tournaments": len(t),
            "mapped": sum(1 for v in t.values() if v),
            "unmapped": sum(1 for v in t.values() if not v),
            "several_competitions": sum(1 for v in t.values() if len(v) > 1),
        }
    return out


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}%" if d else "-"


def render(result: dict[str, Any]) -> str:
    s = result["summary"]
    lines = [
        f"# Identity coverage {result['first'] or '...'}..{result['last'] or '...'}",
        "",
        f"Computed {result['computed_at_utc']}; names judged on today's database.",
        "",
        "## Unexplained states by sport and entity",
        "",
        "| sport / entity | days | items | identified | excluded | explained | "
        "**unexplained** | per day | per day, last 7 | reasons |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for k, v in s.items():
        reasons = ", ".join(f"{r} {n}" for r, n in v["reasons"].items())
        share = _pct(v[UNEXPLAINED], v["total"])
        lines.append(
            f"| {k} | {v['days']} | {v['total']} | {v[IDENTIFIED]} | "
            f"{v[EXCLUDED]} | {v[EXPLAINED]} | **{v[UNEXPLAINED]}** ({share}) | "
            f"{v['unexplained_per_day']} | {v['unexplained_per_day_last7']} | "
            f"{reasons} |")
    days = sorted({d for v in s.values() for d in v["by_day"]})
    keys = list(s)
    lines += ["", "## Unexplained per kickoff day (unexplained / items)", "",
              "| day | " + " | ".join(keys) + " |",
              "|---|" + "---|" * len(keys)]
    for d in days:
        cells = []
        for k in keys:
            bd = s[k]["by_day"].get(d)
            cells.append(f"{bd[UNEXPLAINED]} / {bd['total']}" if bd else "")
        lines.append(f"| {d} | " + " | ".join(cells) + " |")
    other = {k: v["other_reasons"] for k, v in s.items() if v["other_reasons"]}
    if other:
        lines += ["", "## Excluded / explained (not a mapping failure)", ""]
        lines += [f"- {k}: " + ", ".join(f"{r} {n}" for r, n in v.items())
                  for k, v in other.items()]
    if result.get("names"):
        lines += ["", "## Team names (measured sports, today's resolver)", "",
                  "| sport | names | without an id now | learnable from pinned "
                  "events | conflicts | in an unexplained event |",
                  "|---|---|---|---|---|---|"]
        for sport, n in result["names"].items():
            lines.append(f"| {sport} | {n['names']} | {n['unresolved_now']} | "
                         f"{n['learnable']} | {len(n['conflicts'])} | "
                         f"{n['unresolved_in_unexplained']} |")
        lines += ["", "Most frequent names nothing pinned yet:", ""]
        for sport, n in result["names"].items():
            top = "; ".join(f"{nm} ({c}, {t})" for c, nm, t in n["top_unlearnable"][:8])
            lines.append(f"- {sport}: {top}")
    if result.get("tournaments"):
        lines += ["", "## Tournaments (Superbet -> Sofascore competition, learnable "
                  "from identified events)", "",
                  "| sport | tournaments | mapped | unmapped | several competitions |",
                  "|---|---|---|---|---|"]
        for sport, t in result["tournaments"].items():
            lines.append(f"| {sport} | {t['tournaments']} | {t['mapped']} | "
                         f"{t['unmapped']} | {t['several_competitions']} |")
    if result.get("cs2_players_without_identity_record"):
        left = result["cs2_players_without_identity_record"]
        lines += ["", "CS2 player subjects left out (their event predates "
                  f"SPORT_IDENTITY's records): {left}."]
    return "\n".join(lines) + "\n"


def measure(runs_dir: str, conn: sqlite3.Connection | None, sports: Iterable[str],
            first: str | None, last: str | None, now_ts: int | None = None
            ) -> dict[str, Any]:
    wanted = [s for s in ALL_SPORTS if s in set(sports)]
    items: list[Item] = []
    tours: Tournaments = {}
    names: dict[str, Any] = {}
    recs = sport_fixture_records(runs_dir)
    in_days = {k: r for k, r in recs.items()
               if in_window(str(r["kickoff_utc"])[:10], first, last)}
    resolve_sports = [s for s in wanted if s in RESOLVE_SPORTS]
    if resolve_sports:
        ev, tours = resolve_items(runs_dir, conn, resolve_sports)
        items += ev
    resolver = (TeamResolver(conn, now_ts if now_ts is not None else int(time.time()))
                if conn is not None else None)
    for sport in wanted:
        if sport not in IDENTITY_SPORTS:
            continue
        srecs = [r for r in in_days.values() if r.get("sport") == sport]
        items += [fixture_item(r) for r in srecs]
        tours[sport] = sport_tournaments(srecs, sport)
        if resolver is not None:
            st = team_name_stats(sport, srecs, resolver)
            names[sport] = {
                "names": st.names, "unresolved_now": st.unresolved_now,
                "learnable": st.learnable, "conflicts": st.conflicts,
                "unresolved_in_unexplained": st.unresolved_in_unexplained,
                "top_unlearnable": st.top_unlearnable,
            }
    if "football" in wanted:
        items += football_player_items(runs_dir)
    for sport in PLAYER_MODEL_SPORTS:
        if sport in wanted:
            items += sport_player_items(runs_dir, sport)
    no_record = 0
    if "cs2" in wanted:
        cs_items, no_record = cs2_player_items(runs_dir, recs, conn, first, last)
        items += cs_items
    items = [i for i in items if in_window(i.day, first, last)]
    return {
        "computed_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "first": first,
        "last": last,
        "sports": wanted,
        "summary": summarise(items),
        "names": names,
        "tournaments": tournament_summary(tours),
        "cs2_players_without_identity_record": no_record,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from", dest="first", default=None,
                    help="first kickoff day (default: every day on disk)")
    ap.add_argument("--to", dest="last", default=None)
    ap.add_argument("--sport", default="all", choices=("all", *ALL_SPORTS))
    ap.add_argument("--db-path", default=None)
    ap.add_argument("--runs-dir", default=None)
    ap.add_argument("--md-out", default=None)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()
    config = SofaConfig.from_env()
    db_path = args.db_path or config.db_path
    runs_dir = args.runs_dir or config.runs_dir
    sports = ALL_SPORTS if args.sport == "all" else (args.sport,)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        result = measure(runs_dir, conn, sports, args.first, args.last)
    finally:
        conn.close()
    md = render(result)
    print(md)
    if args.md_out:
        Path(args.md_out).write_text(md, encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result, indent=1, ensure_ascii=False, default=sorted),
            encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
