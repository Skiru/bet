"""CS2 history in data/sofa.db: series, maps, and per-player map rows.

Kept as Sofascore reports it - home/away as Sofascore has them, never oriented
to a bookmaker - so the same rows serve any later question (team form, map
pool, player kill rates, overtime frequency) without re-asking Sofascore.

Written by `scripts/sofa/backfill_cs2.py` (history) and CS2_SETTLE (each day's
graded series). Nothing that builds a coupon reads these tables.

Historical Superbet prices do not exist - Superbet's offer API serves only the
current board - so this is results only. Price-against-outcome can only come
from CS2's own snapshots, one day at a time.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from datetime import timedelta
from typing import Any

# Sofascore publishes per-player rows after the score. A map still without
# them this long after the series is taken as never getting them, so the
# backfill stops re-asking.
STATS_GIVE_UP = timedelta(hours=72)
GAP_GIVE_UP = timedelta(days=14)
PLAYERS_PER_MAP = 10


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _num(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, int | float) else None


def is_cs_event(event: dict[str, Any]) -> bool:
    category = ((event.get("tournament") or {}).get("category") or {}).get("name")
    return category == "Counter Strike"


def maps_reproduce_score(event: dict[str, Any], games: list[dict[str, Any]]) -> bool:
    """The finished maps' winners add up to the series score Sofascore gives.

    A 404 on the games list, or a list that is missing a map, must not pass
    for a complete series (review 2026-09-28: 17205934, a 2-0, was stored
    complete with zero maps and would never have been asked again).
    """
    home = _int((event.get("homeScore") or {}).get("current"))
    away = _int((event.get("awayScore") or {}).get("current"))
    if home is None or away is None or home + away == 0:
        return False  # an "Ended" 0-0 with no maps is missing data, not a result
    won = {1: 0, 2: 0}
    for g in games:
        if (g.get("status") or {}).get("type") != "finished":
            continue
        code = _int(g.get("winnerCode"))
        if code not in (1, 2):
            hs = _int((g.get("homeScore") or {}).get("display"))
            aws = _int((g.get("awayScore") or {}).get("display"))
            if hs is None or aws is None or hs == aws:
                return False
            code = 1 if hs > aws else 2
        won[code] += 1
    return (won[1], won[2]) == (home, away)


def is_complete(
    event: dict[str, Any],
    games: list[dict[str, Any]],
    lineups: Mapping[int, dict[str, Any] | None],
    age: timedelta,
) -> bool:
    """Nothing left to ask Sofascore about this series.

    Finished, and either a series with no maps played (a walkover: finished
    but not "Ended", and nothing to fetch) or one whose maps reproduce its
    score and whose every finished map has its ten player rows. The player
    rows are waived after STATS_GIVE_UP - what Sofascore has not published by
    then it does not publish - but the score check never is.
    """
    status = event.get("status") or {}
    if status.get("type") != "finished":
        return False
    finished = [g for g in games if (g.get("status") or {}).get("type") == "finished"]
    if status.get("description") != "Ended" and not finished:
        # A walkover or an awarded series: nothing was played. Sofascore may
        # still list a "notstarted" placeholder map; it is not a map.
        return True
    # Waived only after GAP_GIVE_UP: a series whose maps do not add up is
    # missing data, worth asking for again - but not forever, since some
    # Sofascore gaps are permanent and each re-ask costs every lineup again.
    if not maps_reproduce_score(event, games):
        return age >= GAP_GIVE_UP
    if age >= STATS_GIVE_UP:
        return True  # player rows Sofascore has not published by now
    for g in games:
        if (g.get("status") or {}).get("type") != "finished":
            continue
        if len(_player_rows(lineups.get(int(g.get("id") or 0)))) < PLAYERS_PER_MAP:
            return False
    return True


def _player_rows(lineup: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for key, side in (("homeTeamPlayers", "home"), ("awayTeamPlayers", "away")):
        for row in (lineup or {}).get(key) or []:
            player = row.get("player") or {}
            if _int(player.get("id")) is not None and player.get("name"):
                out.append((side, row))
    return out


def save_series(
    conn: sqlite3.Connection,
    event: dict[str, Any],
    games: list[dict[str, Any]],
    lineups: Mapping[int, dict[str, Any] | None],
    fetched_at: str,
    complete: bool | None,
) -> None:
    """Replace everything stored for this series, in one transaction.

    A lineup that was not fetched (None) keeps the rows already stored for
    that map rather than erasing them, and `complete=None` keeps the stored
    flag: a settle run that did not need player rows must not undo a
    backfill that had them.
    """
    eid = int(event["id"])
    tournament = event.get("tournament") or {}
    home, away = event.get("homeTeam") or {}, event.get("awayTeam") or {}
    status = event.get("status") or {}
    keep = [gid for g in games if (gid := _int(g.get("id"))) is not None]
    with conn:
        # A game list that changed since the last write (a map re-listed under
        # a new id) must not leave the old map, and its player rows, behind.
        marks = ",".join("?" * len(keep)) or "NULL"
        stale = [
            row[0]
            for row in conn.execute(
                f"SELECT game_id FROM cs2_map WHERE sofascore_event_id = ? "
                f"AND game_id NOT IN ({marks})",
                (eid, *keep),
            )
        ]
        for gid in stale:
            conn.execute("DELETE FROM cs2_player_map WHERE game_id = ?", (gid,))
            conn.execute("DELETE FROM cs2_map WHERE game_id = ?", (gid,))
        if complete is None:
            row = conn.execute(
                "SELECT complete FROM cs2_series WHERE sofascore_event_id = ?", (eid,)
            ).fetchone()
            complete = bool(row and row[0])
        conn.execute(
            """INSERT OR REPLACE INTO cs2_series VALUES
               (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                eid,
                int(event.get("startTimestamp") or 0),
                tournament.get("name"),
                _int((tournament.get("uniqueTournament") or {}).get("id")),
                _int((event.get("season") or {}).get("id")),
                int(home.get("id") or 0),
                str(home.get("name") or ""),
                int(away.get("id") or 0),
                str(away.get("name") or ""),
                _int((event.get("homeScore") or {}).get("current")),
                _int((event.get("awayScore") or {}).get("current")),
                _int(event.get("bestOf")),
                str(status.get("type") or "unknown"),
                status.get("description"),
                int(complete),
                fetched_at,
            ),
        )
        ordered = sorted(games, key=lambda g: int(g.get("startTimestamp") or 0))
        for order, g in enumerate(ordered, start=1):
            gid = _int(g.get("id"))
            if gid is None:
                continue
            hs, aws = g.get("homeScore") or {}, g.get("awayScore") or {}
            lineup = lineups.get(gid)
            rows = _player_rows(lineup)
            if lineup is not None:
                conn.execute("DELETE FROM cs2_player_map WHERE game_id = ?", (gid,))
                conn.executemany(
                    "INSERT OR REPLACE INTO cs2_player_map VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            gid,
                            side,
                            int(r["player"]["id"]),
                            str(r["player"]["name"]),
                            _int(r.get("kills")),
                            _int(r.get("deaths")),
                            _int(r.get("assists")),
                            _int(r.get("headshots")),
                            _int(r.get("flashAssists")),
                            _int(r.get("firstKillsDiff")),
                            _int(r.get("kdDiff")),
                            _num(r.get("adr")),
                            _num(r.get("kast")),
                        )
                        for side, r in rows
                    ],
                )
            stored_rows = conn.execute(
                "SELECT COUNT(*) FROM cs2_player_map WHERE game_id = ?", (gid,)
            ).fetchone()[0]
            conn.execute(
                """INSERT OR REPLACE INTO cs2_map VALUES
                   (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    gid,
                    eid,
                    order,
                    (g.get("map") or {}).get("name"),
                    _int(g.get("startTimestamp")),
                    _int(g.get("length")),
                    str((g.get("status") or {}).get("type") or "unknown"),
                    _int(hs.get("display")),
                    _int(aws.get("display")),
                    _int(hs.get("period1")),
                    _int(hs.get("period2")),
                    _int(hs.get("overtime")),
                    _int(aws.get("period1")),
                    _int(aws.get("period2")),
                    _int(aws.get("overtime")),
                    _int(g.get("homeTeamStartingSide")),
                    _int(g.get("winnerCode")),
                    int(bool(g.get("hasCompleteStatistics"))),
                    int(stored_rows >= PLAYERS_PER_MAP),
                    fetched_at,
                ),
            )
        # Explicit: `with conn:`'s own commit is the C-level one and bypasses
        # RetryingConnection's busy-COMMIT retry (review 2026-10-01).
        conn.commit()


def complete_ids(
    conn: sqlite3.Connection, event_ids: Iterable[int], now_ts: int | None = None
) -> set[int]:
    """Which of these series need nothing more from Sofascore.

    Re-checked against what is stored, not only the flag: a series marked
    complete whose stored maps do not reproduce its score (and that is not a
    walkover) is asked again. Rows written before that rule existed - a 404
    games list stored as a complete 2-0 with no maps - heal on the next run.
    """
    ids = list(event_ids)
    done: set[int] = set()
    # Series older than GAP_GIVE_UP are not re-asked whatever their data -
    # the same waiver is_complete gives them. Without a now, nothing is waived.
    gap_cut = -1 if now_ts is None else now_ts - int(GAP_GIVE_UP.total_seconds())
    for i in range(0, len(ids), 500):
        chunk = ids[i : i + 500]
        marks = ",".join("?" * len(chunk))
        done.update(
            int(row[0])
            for row in conn.execute(
                f"""SELECT s.sofascore_event_id
                    FROM cs2_series s
                    LEFT JOIN (
                        SELECT sofascore_event_id,
                               SUM(CASE WHEN (CASE WHEN winner_code IN (1, 2)
                                   THEN winner_code
                                   WHEN home_rounds > away_rounds THEN 1
                                   WHEN away_rounds > home_rounds THEN 2 END)
                                   = 1 THEN 1 ELSE 0 END) AS hw,
                               SUM(CASE WHEN (CASE WHEN winner_code IN (1, 2)
                                   THEN winner_code
                                   WHEN home_rounds > away_rounds THEN 1
                                   WHEN away_rounds > home_rounds THEN 2 END)
                                   = 2 THEN 1 ELSE 0 END) AS aw
                        FROM cs2_map WHERE status_type = 'finished'
                        GROUP BY sofascore_event_id
                    ) m USING (sofascore_event_id)
                    WHERE s.complete = 1 AND s.sofascore_event_id IN ({marks})
                      AND (
                        (COALESCE(s.status_description, '') != 'Ended'
                         AND COALESCE(m.hw, 0) + COALESCE(m.aw, 0) = 0)
                        OR (COALESCE(m.hw, 0) = s.home_maps
                            AND COALESCE(m.aw, 0) = s.away_maps
                            AND s.home_maps + s.away_maps > 0)
                        OR s.start_ts < ?
                      )""",
                (*chunk, gap_cut),
            )
        )
    return done


def history_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """What the store holds, for audit_cs2 --history."""
    one = conn.execute(
        """SELECT COUNT(*), SUM(complete), MIN(start_ts), MAX(start_ts),
                  COUNT(DISTINCT home_id) + COUNT(DISTINCT away_id)
           FROM cs2_series"""
    ).fetchone()
    maps = conn.execute(
        "SELECT COUNT(*), SUM(has_player_rows), SUM(home_overtime > 0 OR "
        "away_overtime > 0) FROM cs2_map WHERE status_type = 'finished'"
    ).fetchone()
    players = conn.execute("SELECT COUNT(*) FROM cs2_player_map").fetchone()[0]
    teams = conn.execute(
        "SELECT COUNT(*) FROM (SELECT home_id FROM cs2_series "
        "UNION SELECT away_id FROM cs2_series)"
    ).fetchone()[0]
    tournaments = conn.execute(
        "SELECT tournament, COUNT(*) FROM cs2_series GROUP BY tournament "
        "ORDER BY COUNT(*) DESC LIMIT 15"
    ).fetchall()
    return {
        "series": one[0] or 0,
        "series_complete": one[1] or 0,
        "first_ts": one[2],
        "last_ts": one[3],
        "teams": teams,
        "maps_finished": maps[0] or 0,
        "maps_with_players": maps[1] or 0,
        "maps_overtime": maps[2] or 0,
        "player_rows": players,
        "top_tournaments": [(t or "?", n) for t, n in tournaments],
    }
