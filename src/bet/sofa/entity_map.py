"""The one Superbet -> Sofascore entity map (identity plan K1,
docs/sofa/history/PLAN_MAPA_DRUZYN_2026-10-14.md).

`sofa_entity` was written by RESOLVE (football / tennis, and the shadow
sports through SHADOW_SETTLE's resolver) and by backfill_cs2.py; SPORT_IDENTITY
read it and remembered nothing, so a name it had pinned on Monday was
TEAM_UNRESOLVED again on Tuesday (2026-10-05..10-14: hockey 78, basketball
286, volleyball 107, CS2 10 names). This module makes SPORT_IDENTITY a writer:

- **Learned** (`source` IDENTITY_NAMES): a side of an IDENTIFIED event whose
  own name confirmed it - a name-checked method (NAME_METHODS) and its name
  score above resolve.NAME_MATCH_THRESHOLD. The rule RESOLVE's `remember()`
  keeps: a shared word (the *_ID_AND_OPPONENT methods) is evidence about one
  game, not about the name.
- **Candidate** (sofa_entity_candidate, the NEEDS_ALIAS queue of plan K4): a
  side confirmed only by the opponent rule. Never read as an identity; a
  person decides once.
- **Conflict** (sofa_entity_conflict): a name the map already holds with a
  different id. From ENTITY_MAP_FROM_UTC nothing overwrites a held id - the
  offer is queued (cache.save_entity follows the same rule); before it the
  old overwrite stands and the conflict is still recorded.
- **Tournaments** (sofa_tournament_map): Superbet tournament -> the Sofascore
  competition (uniqueTournament) of each identified event, with a count. One
  Superbet tournament may hold several competitions (qualifying and main
  draw); nothing reads the map yet (K2).

Reading a learned row changes which events are identified, so it is behind
epochs.ENTITY_MAP_FROM_UTC (`learned_reads`); writing is not, and starts
with the code. A row with `source` NULL is the map as it was (RESOLVE,
SHADOW_SETTLE, backfill_cs2) and is read as before.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bet.sofa import cs2, epochs
from bet.sofa.names import normalize_name

# resolve.NAME_MATCH_THRESHOLD; not imported (resolve imports cache, and
# cache.save_entity reads this module). tests/sofa pins the two equal.
NAME_MATCH_THRESHOLD = 82.0

SOURCE_RESOLVE = "resolve"
SOURCE_IDENTITY_NAMES = "identity_names"
SOURCE_MANUAL = "manual"
# Sources whose rows only the switch reads; None (the map before K1) and
# SOURCE_RESOLVE are read as they always were.
LEARNED_SOURCES = frozenset({SOURCE_IDENTITY_NAMES, SOURCE_MANUAL})

# SPORT_IDENTITY match methods that check a side's own name against the
# threshold (sport_identity._side_ok, cs2.pick_event). The opponent-rule
# methods (LISTING_ID_AND_OPPONENT, CS2_LISTING_ID_AND_OPPONENT) do not.
NAME_METHODS = frozenset({"LISTING_NAMES", "LISTING_ID_AND_NAME", "CS2_PICK_EVENT"})
# Methods whose other side is at most a NEEDS_ALIAS candidate: the opponent
# rule (a shared word) and DAY_ANCHOR (no name at all - K2 found the anchor's
# game listed with another opponent: BC Barcelos (K) - Francisco Franco (K)
# is Sofascore's BC Barcelos - CAB Madeira).
OPPONENT_METHODS = frozenset(
    {"LISTING_ID_AND_OPPONENT", "CS2_LISTING_ID_AND_OPPONENT", "DAY_ANCHOR"}
)

# The shadow sports' sofa_entity key space is Sofascore's sport slug, as
# RESOLVE / SHADOW_SETTLE write it; CS2's is backfill_cs2.ENTITY_SPORT.
ENTITY_SPORT = {
    "hockey": "ice-hockey",
    "basketball": "basketball",
    "volleyball": "volleyball",
    "cs2": "cs2",
    "football": "football",
    "tennis": "tennis",
}

LEARNED = "LEARNED"
ALREADY_HELD = "ALREADY_HELD"
CONFLICT = "CONFLICT"
CANDIDATE = "CANDIDATE"

# The K1 tables and sofa_entity columns live in db.migrate (SCHEMA and
# added_columns there).


def entity_sport(sport: str) -> str:
    return ENTITY_SPORT.get(sport, sport)


def entity_key(sport: str, name: str) -> str:
    """The query_key a name is held under: CS2 folded (cs2.esports_name, as
    backfill_cs2 and the CS2 resolver read it), every other sport as RESOLVE
    writes it (names.normalize_name)."""
    return str(cs2.esports_name(name) if sport == "cs2" else normalize_name(name))


def learned_reads(date: str | None, at: datetime | None = None) -> bool:
    """May a reader use LEARNED_SOURCES rows (epochs.ENTITY_MAP_FROM_UTC)?"""
    return epochs.entity_map(date, at)


def tournament_key(name: str | None, superbet_id: int | None = None) -> str | None:
    """Superbet's tournament as the map keys it: its name (the shadow sports'
    snapshots carry it), else `id:<n>` (football / tennis boards carry only
    the id)."""
    if name and name.strip():
        return name.strip()
    return f"id:{superbet_id}" if superbet_id is not None else None


# --- reads ------------------------------------------------------------------------


def verified_id(
    conn: sqlite3.Connection, slug: str, key: str, learned: bool
) -> int | None:
    """The verified id held for (slug, key); a LEARNED_SOURCES row only when
    `learned`. A database without the K1 columns has no learned rows."""
    try:
        row = conn.execute(
            "SELECT sofascore_id, status, source FROM sofa_entity "
            "WHERE sport = ? AND query_key = ?",
            (slug, key),
        ).fetchone()
    except sqlite3.OperationalError:
        row = conn.execute(
            "SELECT sofascore_id, status, NULL FROM sofa_entity "
            "WHERE sport = ? AND query_key = ?",
            (slug, key),
        ).fetchone()
    if row is None or row[1] != "verified" or row[0] is None:
        return None
    if row[2] in LEARNED_SOURCES and not learned:
        return None
    return int(row[0])


def learned_id(conn: sqlite3.Connection, slug: str, key: str) -> int | None:
    """The id of a LEARNED_SOURCES row for (slug, key), else None - for a
    reader that never read the map's other rows (CS2's resolver)."""
    try:
        row = conn.execute(
            "SELECT sofascore_id, status, source FROM sofa_entity "
            "WHERE sport = ? AND query_key = ?",
            (slug, key),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None or row[1] != "verified" or row[2] not in LEARNED_SOURCES:
        return None
    return int(row[0])


# --- what a record teaches ---------------------------------------------------------


@dataclass(frozen=True)
class Side:
    sport: str
    name: str  # Superbet's
    sofascore_id: int
    sofascore_name: str
    event_id: int
    score: float | None
    method: str
    # The id the resolver had for this side at identification (team1_id /
    # team2_id of the record), if any.
    resolved_id: int | None = None


def _split_match(sofascore_match: str | None) -> tuple[str, str]:
    parts = str(sofascore_match or "").split(" - ")
    return (parts[0], parts[1]) if len(parts) == 2 else ("", "")


def record_sides(rec: Mapping[str, Any]) -> list[Side]:
    """team1 / team2 of an IDENTIFIED SPORT_IDENTITY record with the
    Sofascore id and name each was pinned to."""
    if rec.get("status") != "IDENTIFIED" or rec.get("home_is_team1") is None:
        return []
    home_name = str(rec.get("sofascore_home") or "")
    away_name = str(rec.get("sofascore_away") or "")
    if not (home_name and away_name):
        home_name, away_name = _split_match(rec.get("sofascore_match"))
    h, a = rec.get("home_id"), rec.get("away_id")
    if rec["home_is_team1"]:
        pairs = (
            (rec["team1"], h, home_name, "team1"),
            (rec["team2"], a, away_name, "team2"),
        )
    else:
        pairs = (
            (rec["team1"], a, away_name, "team1"),
            (rec["team2"], h, home_name, "team2"),
        )
    scores = rec.get("name_scores") or {}
    out = []
    for name, sid, sname, side in pairs:
        if not isinstance(sid, int) or not name:
            continue
        sc = scores.get(side)
        own = rec.get(f"{side}_id")
        out.append(
            Side(
                str(rec["sport"]),
                str(name),
                sid,
                sname,
                int(rec["sofascore_event_id"]),
                float(sc) if isinstance(sc, (int, float)) else None,
                str(rec.get("match_method") or ""),
                own if isinstance(own, int) else None,
            )
        )
    return out


def name_confirmed(side: Side) -> bool:
    """Learnable: the side's own name confirmed it (NAME_METHODS, score
    above the threshold), or the resolver already had this very id for it
    (the anchor of an opponent-rule or DAY_ANCHOR game - learning it only
    holds what the resolver's index knew). Anything else is a candidate at
    most."""
    if side.resolved_id is not None and side.resolved_id == side.sofascore_id:
        return True
    return (
        side.method in NAME_METHODS
        and side.score is not None
        and side.score > NAME_MATCH_THRESHOLD
    )


# --- writes ------------------------------------------------------------------------


def record_conflict(
    conn: sqlite3.Connection,
    slug: str,
    key: str,
    held: Mapping[str, Any],
    offered_id: int,
    offered_name: str,
    offered_source: str | None,
    evidence_event_id: int | None,
    at: str,
) -> None:
    conn.execute(
        """INSERT INTO sofa_entity_conflict
           (sport, query_key, held_id, held_name, held_source, offered_id,
            offered_name, offered_source, evidence_event_id, first_seen_utc,
            last_seen_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(sport, query_key, offered_id) DO UPDATE SET
             last_seen_utc = excluded.last_seen_utc, seen = seen + 1,
             held_id = excluded.held_id, held_name = excluded.held_name""",
        (
            slug,
            key,
            int(held["sofascore_id"]),
            held.get("sofascore_name"),
            held.get("source"),
            offered_id,
            offered_name,
            offered_source,
            evidence_event_id,
            at,
            at,
        ),
    )


def held_row(conn: sqlite3.Connection, slug: str, key: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT sofascore_id, sofascore_name, status, source FROM sofa_entity "
        "WHERE sport = ? AND query_key = ?",
        (slug, key),
    ).fetchone()
    if row is None:
        return None
    return {
        "sofascore_id": row[0],
        "sofascore_name": row[1],
        "status": row[2],
        "source": row[3],
    }


def learn(
    conn: sqlite3.Connection, side: Side, at: str, source: str = SOURCE_IDENTITY_NAMES
) -> str:
    """Hold `side`'s name as its id. A name held with the same id is left as
    it is (its source too); with another verified id it is never
    overwritten - a conflict is queued."""
    slug, key = entity_sport(side.sport), entity_key(side.sport, side.name)
    held = held_row(conn, slug, key)
    if held is not None and held["status"] == "verified":
        if int(held["sofascore_id"]) == side.sofascore_id:
            return ALREADY_HELD
        record_conflict(
            conn,
            slug,
            key,
            held,
            side.sofascore_id,
            side.sofascore_name,
            source,
            side.event_id,
            at,
        )
        return CONFLICT
    conn.execute(
        """INSERT OR REPLACE INTO sofa_entity
           (sport, query_key, sofascore_id, sofascore_name, entity_type, country,
            status, verified_at, last_used_at, hit_count, source, evidence_event_id)
           VALUES (?, ?, ?, ?, 'team', NULL, 'verified', ?, ?, 0, ?, ?)""",
        (
            slug,
            key,
            side.sofascore_id,
            side.sofascore_name or side.name,
            at,
            at,
            source,
            side.event_id,
        ),
    )
    return LEARNED


def queue_candidate(conn: sqlite3.Connection, side: Side, reason: str, at: str) -> str:
    """A NEEDS_ALIAS entry: this name may be that id, a person decides. A
    name already held with this id is not queued."""
    slug, key = entity_sport(side.sport), entity_key(side.sport, side.name)
    held = held_row(conn, slug, key)
    if (
        held is not None
        and held["status"] == "verified"
        and int(held["sofascore_id"]) == side.sofascore_id
    ):
        return ALREADY_HELD
    conn.execute(
        """INSERT INTO sofa_entity_candidate
           (sport, query_key, superbet_name, candidate_id, candidate_name, reason,
            evidence_event_id, first_seen_utc, last_seen_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(sport, query_key, candidate_id) DO UPDATE SET
             last_seen_utc = excluded.last_seen_utc, seen = seen + 1""",
        (
            slug,
            key,
            side.name,
            side.sofascore_id,
            side.sofascore_name,
            reason,
            side.event_id,
            at,
            at,
        ),
    )
    return CANDIDATE


def record_tournament(
    conn: sqlite3.Connection,
    sport: str,
    superbet_tournament: str,
    competition_id: int,
    sofascore_tournament: str | None,
    event_id: int | None,
    at: str,
    superbet_tournament_id: int | None = None,
) -> None:
    conn.execute(
        """INSERT INTO sofa_tournament_map
           (sport, superbet_tournament, competition_id, sofascore_tournament,
            superbet_tournament_id, events, evidence_event_id, first_seen_utc,
            last_seen_utc)
           VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
           ON CONFLICT(sport, superbet_tournament, competition_id) DO UPDATE SET
             events = events + 1, last_seen_utc = excluded.last_seen_utc,
             sofascore_tournament = COALESCE(excluded.sofascore_tournament,
                                             sofascore_tournament)""",
        (
            sport,
            superbet_tournament,
            competition_id,
            sofascore_tournament,
            superbet_tournament_id,
            event_id,
            at,
            at,
        ),
    )


def mark_taught(conn: sqlite3.Connection, sport: str, event_id: int, at: str) -> bool:
    """Record that this Sofascore event has taught the map; False when it
    already had (a pinned record is re-read every run and must not count
    its tournament twice)."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO sofa_entity_taught (sofascore_event_id, sport, "
        "taught_at_utc) VALUES (?, ?, ?)",
        (event_id, sport, at),
    )
    return cur.rowcount == 1


def learn_records(
    conn: sqlite3.Connection, records: Iterable[Mapping[str, Any]], at: str
) -> dict[str, int]:
    """Everything the IDENTIFIED records teach, once per Sofascore event
    (mark_taught): sides by name (learn), sides by the opponent rule only
    (queue_candidate), the tournament map. The caller commits."""
    counts: dict[str, int] = {
        LEARNED: 0,
        ALREADY_HELD: 0,
        CONFLICT: 0,
        CANDIDATE: 0,
        "tournaments": 0,
        "events": 0,
    }
    for rec in records:
        sides = record_sides(rec)
        if not sides:
            continue
        eid = int(rec["sofascore_event_id"])
        if not mark_taught(conn, str(rec["sport"]), eid, at):
            continue
        counts["events"] += 1
        for side in sides:
            if name_confirmed(side):
                counts[learn(conn, side, at)] += 1
            elif side.method in OPPONENT_METHODS:
                counts[queue_candidate(conn, side, side.method, at)] += 1
        comp = rec.get("competition_id")
        tkey = tournament_key(rec.get("tournament"))
        if isinstance(comp, int) and tkey:
            record_tournament(
                conn,
                str(rec["sport"]),
                tkey,
                comp,
                rec.get("sofascore_tournament"),
                eid,
                at,
            )
            counts["tournaments"] += 1
    return counts


def learn_resolve_tournaments(
    conn: sqlite3.Connection,
    rows: Iterable[tuple[str, int | None, int, str | None, int]],
    at: str,
) -> int:
    """RESOLVE's fixtures into the tournament map: (sport, Superbet
    tournament id, competition id, competition name, Sofascore event id),
    keyed `id:<superbet id>` (the board carries no tournament name), once
    per event (mark_taught). Returns the events recorded; the caller commits."""
    n = 0
    for sport, tid, comp, name, eid in rows:
        key = tournament_key(None, tid)
        if key is None or not mark_taught(conn, sport, eid, at):
            continue
        record_tournament(
            conn, sport, key, comp, name, eid, at, superbet_tournament_id=tid
        )
        n += 1
    return n


def reteach_sides(
    conn: sqlite3.Connection, records: Iterable[Mapping[str, Any]], at: str
) -> dict[str, int]:
    """Re-read the sides of already taught events under the current
    name_confirmed (no tournament counted again): a newly learnable side is
    learned and its OPEN candidate row closed (status HELD). For a rule
    change after a backfill; the caller commits."""
    counts: dict[str, int] = {LEARNED: 0, ALREADY_HELD: 0, CONFLICT: 0, "closed": 0}
    for rec in records:
        for side in record_sides(rec):
            if not name_confirmed(side):
                continue
            counts[learn(conn, side, at)] += 1
            cur = conn.execute(
                "UPDATE sofa_entity_candidate SET status = 'HELD', last_seen_utc = ?"
                " WHERE sport = ? AND query_key = ? AND candidate_id = ?"
                " AND status = 'OPEN'",
                (
                    at,
                    entity_sport(side.sport),
                    entity_key(side.sport, side.name),
                    side.sofascore_id,
                ),
            )
            counts["closed"] += cur.rowcount
    return counts


# --- manual decisions (identity plan K4) ---------------------------------------------

MANUAL_FILE = "sofa_entity_aliases.json"
_MANUAL_KEYS = ("sport", "superbet_name", "sofascore_id", "decided_by", "decided_at")


def load_manual(path: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """config/sofa_entity_aliases.json: `aliases` (a Superbet name IS this
    Sofascore id) and `rejected` (it is NOT this candidate), each entry with
    sport, superbet_name, sofascore_id, decided_by, decided_at and evidence.
    A missing file is no decision; a malformed entry raises (a person typed
    it and should hear about it)."""
    import json
    from pathlib import Path

    from bet.sofa.config import config_path

    p = Path(path) if path else Path(config_path(MANUAL_FILE))
    if not p.exists():
        return {"aliases": [], "rejected": []}
    doc = json.loads(p.read_text(encoding="utf-8"))
    out: dict[str, list[dict[str, Any]]] = {}
    for part in ("aliases", "rejected"):
        entries = list(doc.get(part) or [])
        for i, e in enumerate(entries):
            missing = [k for k in _MANUAL_KEYS if e.get(k) in (None, "")]
            if missing or e.get("sport") not in ENTITY_SPORT:
                raise ValueError(f"{p}: {part}[{i}] missing {missing} or bad sport")
            if not isinstance(e["sofascore_id"], int):
                raise ValueError(f"{p}: {part}[{i}] sofascore_id is not an integer")
        out[part] = entries
    return out


def sync_manual(
    conn: sqlite3.Connection,
    decisions: Mapping[str, list[dict[str, Any]]],
    at: str,
    now: datetime | None = None,
) -> dict[str, int]:
    """Write the person's decisions into the map: an alias is held with
    `source` manual (replacing any held id - the decision is the point), its
    conflicts and candidates for that name are closed (RESOLVED / ACCEPTED /
    SUPERSEDED); a rejection closes that candidate (REJECTED). Nothing before
    ENTITY_MAP_FROM_UTC: a manual row is only read from then, and replacing a
    held row earlier would change what today's readers see. The caller
    commits."""
    counts = {"aliases": 0, "rejected": 0, "skipped_before_switch": 0}
    if not learned_reads(None, now):
        counts["skipped_before_switch"] = len(decisions.get("aliases") or []) + len(
            decisions.get("rejected") or []
        )
        return counts
    for e in decisions.get("aliases") or []:
        slug, key = entity_sport(e["sport"]), entity_key(e["sport"], e["superbet_name"])
        sid = int(e["sofascore_id"])
        conn.execute(
            """INSERT OR REPLACE INTO sofa_entity
               (sport, query_key, sofascore_id, sofascore_name, entity_type, country,
                status, verified_at, last_used_at, hit_count, source, evidence_event_id)
               VALUES (?, ?, ?, ?, 'team', NULL, 'verified', ?, ?, 0, ?, ?)""",
            (
                slug,
                key,
                sid,
                str(e.get("sofascore_name") or e["superbet_name"]),
                at,
                at,
                SOURCE_MANUAL,
                e.get("evidence_event_id"),
            ),
        )
        conn.execute(
            "UPDATE sofa_entity_conflict SET status = 'RESOLVED' WHERE sport = ?"
            " AND query_key = ? AND status = 'OPEN'",
            (slug, key),
        )
        conn.execute(
            "UPDATE sofa_entity_candidate SET status = CASE WHEN candidate_id = ?"
            " THEN 'ACCEPTED' ELSE 'SUPERSEDED' END WHERE sport = ?"
            " AND query_key = ? AND status = 'OPEN'",
            (sid, slug, key),
        )
        counts["aliases"] += 1
    for e in decisions.get("rejected") or []:
        slug, key = entity_sport(e["sport"]), entity_key(e["sport"], e["superbet_name"])
        conn.execute(
            "UPDATE sofa_entity_candidate SET status = 'REJECTED' WHERE sport = ?"
            " AND query_key = ? AND candidate_id = ?",
            (slug, key, int(e["sofascore_id"])),
        )
        counts["rejected"] += 1
    return counts


def open_queue(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """The NEEDS_ALIAS queue: OPEN conflicts and candidates, most seen first."""
    conflicts = [
        dict(
            zip(
                (
                    "sport",
                    "query_key",
                    "held_id",
                    "held_name",
                    "held_source",
                    "offered_id",
                    "offered_name",
                    "evidence_event_id",
                    "seen",
                ),
                tuple(r),
                strict=True,
            )
        )
        for r in conn.execute(
            "SELECT sport, query_key, held_id, held_name, held_source,"
            " offered_id, offered_name, evidence_event_id, seen"
            " FROM sofa_entity_conflict WHERE status = 'OPEN'"
            " ORDER BY seen DESC, sport, query_key"
        )
    ]
    candidates = [
        dict(
            zip(
                (
                    "sport",
                    "superbet_name",
                    "candidate_id",
                    "candidate_name",
                    "reason",
                    "evidence_event_id",
                    "seen",
                    "last_seen_utc",
                ),
                tuple(r),
                strict=True,
            )
        )
        for r in conn.execute(
            "SELECT sport, superbet_name, candidate_id, candidate_name, reason,"
            " evidence_event_id, seen, last_seen_utc FROM sofa_entity_candidate"
            " WHERE status = 'OPEN' ORDER BY seen DESC, sport, superbet_name"
        )
    ]
    return {"conflicts": conflicts, "candidates": candidates}
