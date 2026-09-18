import json
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any, cast

from bet.sofa.config import SofaConfig
from bet.sofa.db import get_connection
from bet.sofa.timeutil import now


class SofaCache:
    def __init__(self, config: SofaConfig) -> None:
        self.config = config

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
                "SELECT missed_at FROM sofa_entity_miss "
                "WHERE sport = ? AND query_key = ?",
                (sport, query_key),
            ).fetchone()
            if not row:
                return False
            missed_at = datetime.fromisoformat(row["missed_at"])
            return now() - missed_at <= timedelta(
                minutes=self.config.entity_miss_ttl_min
            )

    def save_entity_miss(self, sport: str, query_key: str) -> None:
        """Remember that this name resolved to nothing."""
        with get_connection(self.config.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sofa_entity_miss (sport, query_key, missed_at)
                VALUES (?, ?, ?)
                ON CONFLICT(sport, query_key) DO UPDATE SET
                    missed_at = excluded.missed_at
                """,
                (sport, query_key, now().isoformat()),
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
