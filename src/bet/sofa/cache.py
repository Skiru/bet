import json
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any, cast

from bet.sofa.config import MATCH_LOGIC_VERSION, SofaConfig
from bet.sofa.db import get_connection, migrate
from bet.sofa.timeutil import now


class SofaCache:
    def __init__(self, config: SofaConfig) -> None:
        self.config = config
        # The schema is created here, in the constructor, because there is no
        # way into the cache that bypasses it (F14). Nothing in production code
        # called migrate() before: the live database only had its tables
        # because someone once ran it by hand, so every table added afterwards
        # — sofa_entity_miss, added by F4 — never reached it, and the second
        # live run died on the first fixture of RESOLVE. On a clean machine
        # the pipeline would not start at all. migrate() is idempotent and
        # costs one no-op transaction after the first call.
        migrate(config.db_path)

    def get_event_stats(
        self, sofascore_event_id: int
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str] | None:
        """
        Zwraca krotkę (statistics, incidents, status_type) lub None jeśli brak w bazie.
        None w tuple = nie pobrano. {} = pobrano i zwróciło 404.
        """
        with get_connection(self.config.db_path) as conn:
            row = conn.execute(
                "SELECT statistics_json, incidents_json, status_type "
                "FROM sofa_event_stats WHERE sofascore_event_id = ?",
                (sofascore_event_id,),
            ).fetchone()
            if row:
                stats = (
                    cast(dict[str, Any], json.loads(row["statistics_json"]))
                    if row["statistics_json"]
                    else None
                )
                incidents = (
                    cast(dict[str, Any], json.loads(row["incidents_json"]))
                    if row["incidents_json"]
                    else None
                )
                return stats, incidents, row["status_type"]
        return None

    def save_event_stats(
        self,
        sofascore_event_id: int,
        statistics: dict[str, Any] | None,
        incidents: dict[str, Any] | None,
        status_type: str,
    ) -> None:
        """
        Zapisuje statystyki i incydenty (na stałe, nigdy nie wygasa).
        Pusta encja {} oznacza 404. None oznacza "nie pobrano w tym
        przebiegu" i nie nadpisuje bazy.
        """
        if status_type not in ("finished", "canceled", "abandoned"):
            raise ValueError(
                f"Cannot save event stats for non-terminal status: {status_type}"
            )

        fetched_at = now().isoformat()
        stats_json = json.dumps(statistics) if statistics is not None else None
        incidents_json = json.dumps(incidents) if incidents is not None else None

        with get_connection(self.config.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sofa_event_stats
                (sofascore_event_id, fetched_at, statistics_json,
                 incidents_json, status_type)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(sofascore_event_id) DO UPDATE SET
                    fetched_at = excluded.fetched_at,
                    statistics_json = COALESCE(
                        excluded.statistics_json, sofa_event_stats.statistics_json),
                    incidents_json = COALESCE(
                        excluded.incidents_json, sofa_event_stats.incidents_json),
                    status_type = excluded.status_type
                """,
                (
                    sofascore_event_id,
                    fetched_at,
                    stats_json,
                    incidents_json,
                    status_type,
                ),
            )
            conn.commit()

    def get_event_lineups(
        self, sofascore_event_id: int
    ) -> dict[str, Any] | None:
        """Per-player statistics for a finished event, or None if never asked.

        F54. Deliberately NOT folded into `get_event_stats`'s tuple: seven
        call sites unpack that tuple by position, one of them a test that
        monkeypatches the method, and widening it would make a player feature
        able to break the team pipeline.

        ``{}`` means asked and got nothing back — a 404, or a match Sofascore
        publishes no squad for — and it is a *fact*, so the next run does not
        pay for it again. ``None`` means nobody has asked.
        """
        with get_connection(self.config.db_path) as conn:
            row = conn.execute(
                "SELECT lineups_json FROM sofa_event_stats "
                "WHERE sofascore_event_id = ?",
                (sofascore_event_id,),
            ).fetchone()
        if not row or row["lineups_json"] is None:
            return None
        return cast(dict[str, Any], json.loads(row["lineups_json"]))

    def save_event_lineups(
        self,
        sofascore_event_id: int,
        lineups: dict[str, Any] | None,
        status_type: str,
    ) -> None:
        """Persist per-player statistics. ``None`` records the empty answer.

        Same terminal-status guard as `save_event_stats`, for the same reason:
        a squad list for a match still in progress is not a fact about a
        finished match.
        """
        if status_type not in ("finished", "canceled", "abandoned"):
            raise ValueError(
                f"Cannot save event lineups for non-terminal status: {status_type}"
            )
        payload = json.dumps(lineups if lineups is not None else {})
        with get_connection(self.config.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sofa_event_stats
                (sofascore_event_id, fetched_at, lineups_json, status_type)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(sofascore_event_id) DO UPDATE SET
                    lineups_json = excluded.lineups_json
                """,
                (sofascore_event_id, now().isoformat(), payload, status_type),
            )
            conn.commit()

    def get_entity_events(
        self, sofascore_entity_id: int, kind: str, page: int
    ) -> dict[str, Any] | None:
        """
        Pobiera listing zdarzeń dla encji (z zachowaniem TTL).
        """
        with get_connection(self.config.db_path) as conn:
            row = conn.execute(
                """
                SELECT fetched_at, events_json
                FROM sofa_entity_events
                WHERE sofascore_entity_id = ? AND kind = ? AND page = ?
                """,
                (sofascore_entity_id, kind, page),
            ).fetchone()

            if row:
                from datetime import datetime

                # fetched_at is ISO8601 with Z suffix (or +00:00)
                fetched_at = datetime.fromisoformat(
                    row["fetched_at"].replace("Z", "+00:00")
                )
                if now() - fetched_at <= timedelta(minutes=self.config.events_ttl_min):
                    return cast(dict[str, Any], json.loads(row["events_json"]))
        return None

    def save_entity_events(
        self, sofascore_entity_id: int, kind: str, page: int, events: dict[str, Any]
    ) -> None:
        """
        Zapisuje listing zdarzeń.
        """
        fetched_at = now().isoformat()
        events_json = json.dumps(events)

        with get_connection(self.config.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sofa_entity_events
                (sofascore_entity_id, kind, page, fetched_at, events_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sofascore_entity_id, kind, page, fetched_at, events_json),
            )
            conn.commit()

    def iter_entity_events(
        self,
    ) -> Iterator[tuple[int, str, int, dict[str, Any]]]:
        """Every cached listing, ignoring TTL.

        Auditing what a sample was built from is a question about the past, so
        an expired row is still the right answer here.
        """
        with get_connection(self.config.db_path) as conn:
            rows = conn.execute(
                """
                SELECT sofascore_entity_id, kind, page, events_json
                FROM sofa_entity_events
                """
            ).fetchall()
        for row in rows:
            payload = json.loads(row["events_json"])
            if isinstance(payload, dict):
                yield (
                    int(row["sofascore_entity_id"]),
                    str(row["kind"]),
                    int(row["page"]),
                    cast(dict[str, Any], payload),
                )

    def get_entity(self, sport: str, query_key: str) -> dict[str, Any] | None:
        """
        Pobiera encję z bazy (trafienie w cache, w tym 'rejected').
        """
        with get_connection(self.config.db_path) as conn:
            row = conn.execute(
                """
                SELECT sofascore_id, sofascore_name, entity_type, country, status
                FROM sofa_entity
                WHERE sport = ? AND query_key = ?
                """,
                (sport, query_key),
            ).fetchone()

            if row:
                conn.execute(
                    """
                    UPDATE sofa_entity
                    SET hit_count = hit_count + 1, last_used_at = ?
                    WHERE sport = ? AND query_key = ?
                    """,
                    (now().isoformat(), sport, query_key),
                )
                conn.commit()
                return {
                    "sofascore_id": row["sofascore_id"],
                    "sofascore_name": row["sofascore_name"],
                    "entity_type": row["entity_type"],
                    "country": row["country"],
                    "status": row["status"],
                }
        return None

    def get_entity_miss(self, sport: str, query_key: str) -> bool:
        """Did we recently look this name up and find nothing?

        A miss is as much a fact as a hit, and far cheaper to remember than to
        rediscover: an unknown name costs a search plus up to three listings,
        every single run, forever. Expires so that a team Sofascore adds later
        is eventually found.
        """
        with get_connection(self.config.db_path) as conn:
            row = conn.execute(
                "SELECT missed_at, match_logic_version FROM sofa_entity_miss "
                "WHERE sport = ? AND query_key = ?",
                (sport, query_key),
            ).fetchone()
            if not row:
                return False
            # A miss recorded by older matching logic is not evidence about the
            # world, it is evidence about the code that recorded it. Ignore it,
            # so fixing a matching bug takes effect on the next run instead of
            # in seven days' time (F34).
            if row["match_logic_version"] != MATCH_LOGIC_VERSION:
                return False
            missed_at = datetime.fromisoformat(row["missed_at"])
            return now() - missed_at <= timedelta(
                minutes=self.config.entity_miss_ttl_min
            )

    def get_event_detail(self, sofascore_event_id: int) -> dict[str, Any] | None:
        """The cached /event/{id} payload, or None.

        This route had no cache of any kind and was 46% of a whole RESOLVE
        stage's requests — one call per fixture, every run, forever (F33).

        Two lifetimes, because the payload has two. A **finished** match cannot
        change, so it is kept permanently, like sofa_event_stats. A match that
        has not been played can and does change — the referee is announced
        late, which is exactly why that field is filled for only 9% of
        fixtures — so it expires. Caching it forever would turn waste into a
        frozen empty referee, which is the trap F17 named and the worse error.
        """
        with get_connection(self.config.db_path) as conn:
            row = conn.execute(
                "SELECT fetched_at, status_type, detail_json "
                "FROM sofa_event_detail WHERE sofascore_event_id = ?",
                (sofascore_event_id,),
            ).fetchone()
            if not row:
                return None
            if row["status_type"] != "finished":
                fetched_at = datetime.fromisoformat(row["fetched_at"])
                if now() - fetched_at > timedelta(
                    minutes=self.config.event_detail_ttl_min
                ):
                    return None
            return cast(dict[str, Any], json.loads(row["detail_json"]))

    def save_event_detail(
        self, sofascore_event_id: int, detail: dict[str, Any], status_type: str | None
    ) -> None:
        """Remember one /event/{id} payload, with the status that dates it."""
        with get_connection(self.config.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sofa_event_detail
                (sofascore_event_id, fetched_at, status_type, detail_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    sofascore_event_id,
                    now().isoformat(),
                    status_type,
                    json.dumps(detail),
                ),
            )
            conn.commit()

    def get_listing_miss(self, entity_id: int, kind: str, page: int) -> bool:
        """Did this listing 404 recently?

        Same reasoning as get_entity_miss, applied to the thing nobody applied
        it to: 242 of RESOLVE's ~870 requests — 28% — were spent rediscovering
        404s, 225 of them already known from the previous run (F17). A 404 does
        not look like a cost in the log, which is why it went uncounted.

        The TTL is short on purpose. events/next changes by nature, so
        remembering a miss forever would convert waste into a silent gap.
        """
        with get_connection(self.config.db_path) as conn:
            row = conn.execute(
                "SELECT missed_at FROM sofa_listing_miss "
                "WHERE sofascore_entity_id = ? AND kind = ? AND page = ?",
                (entity_id, kind, page),
            ).fetchone()
            if not row:
                return False
            missed_at = datetime.fromisoformat(row["missed_at"])
            return now() - missed_at <= timedelta(
                minutes=self.config.listing_miss_ttl_min
            )

    def save_listing_miss(self, entity_id: int, kind: str, page: int) -> None:
        """Remember that this listing returned nothing."""
        with get_connection(self.config.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sofa_listing_miss
                (sofascore_entity_id, kind, page, missed_at)
                VALUES (?, ?, ?, ?)
                """,
                (entity_id, kind, page, now().isoformat()),
            )
            conn.commit()

    def save_entity_miss(self, sport: str, query_key: str) -> None:
        """Remember that this name resolved to nothing."""
        with get_connection(self.config.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sofa_entity_miss
                (sport, query_key, missed_at, match_logic_version)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(sport, query_key) DO UPDATE SET
                    missed_at = excluded.missed_at,
                    match_logic_version = excluded.match_logic_version
                """,
                (sport, query_key, now().isoformat(), MATCH_LOGIC_VERSION),
            )
            conn.commit()

    def clear_entity_miss(self, sport: str, query_key: str) -> None:
        """Forget a miss, because the name just resolved after all."""
        with get_connection(self.config.db_path) as conn:
            conn.execute(
                "DELETE FROM sofa_entity_miss WHERE sport = ? AND query_key = ?",
                (sport, query_key),
            )
            conn.commit()

    def save_entity(
        self,
        sport: str,
        query_key: str,
        sofascore_id: int,
        sofascore_name: str,
        entity_type: str,
        country: str | None,
        status: str,
    ) -> None:
        """
        Zapisuje encję (np. po weryfikacji).
        status='verified' ustawiany wyłącznie po znalezieniu eventu
        potwierdzonego datą i przeciwnikiem.
        """
        verified_at = now().isoformat() if status == "verified" else None

        with get_connection(self.config.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sofa_entity
                (sport, query_key, sofascore_id, sofascore_name, entity_type,
                 country, status, verified_at, last_used_at, hit_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    sport,
                    query_key,
                    sofascore_id,
                    sofascore_name,
                    entity_type,
                    country,
                    status,
                    verified_at,
                    now().isoformat(),
                ),
            )
            conn.commit()
