# ruff: noqa: E501
import logging
import sqlite3
from datetime import timedelta

from bet.enrichment.football.time import format_utc, parse_canonical_or_offset_datetime

logger = logging.getLogger(__name__)

class FootballSyncEngine:
    def __init__(self, conn: sqlite3.Connection, clock=None):
        self.conn = conn
        if clock is not None:
            self.clock = clock
        else:
            from bet.enrichment.football.contracts import SystemClock
            self.clock = SystemClock()

    def acquire_lease(self, provider: str, sport: str, operation: str, scope_key: str, lease_owner: str, ttl_minutes: int = 15) -> bool:
        cursor = self.conn.cursor()
        if not self.conn.in_transaction: cursor.execute("BEGIN IMMEDIATE")
        try:
            row = cursor.execute(
                """SELECT lease_owner, lease_expires_at, lock_version
                   FROM sports_sync_cursor
                   WHERE provider = ? AND sport = ? AND operation = ? AND scope_key = ?
                """,
                (provider, sport, operation, scope_key)
            ).fetchone()

            now = self.clock.now_utc()
            expires = now + timedelta(minutes=ttl_minutes)
            expires_str = format_utc(expires)
            now_str = format_utc(now)

            if not row:
                cursor.execute(
                    """INSERT INTO sports_sync_cursor
                       (provider, sport, operation, scope_key, lease_owner, lease_expires_at, lock_version, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (provider, sport, operation, scope_key, lease_owner, expires_str, now_str, now_str)
                )
                self.conn.commit()
                return True

            owner, exp_str, lock_ver = row
            if owner and exp_str:
                exp_dt = parse_canonical_or_offset_datetime(exp_str)
                if exp_dt > now and owner != lease_owner:
                    cursor.execute("ROLLBACK")
                    return False

            res = cursor.execute(
                """UPDATE sports_sync_cursor
                   SET lease_owner = ?, lease_expires_at = ?, lock_version = lock_version + 1, updated_at = ?
                   WHERE provider = ? AND sport = ? AND operation = ? AND scope_key = ? AND lock_version = ?
                """,
                (lease_owner, expires_str, now_str, provider, sport, operation, scope_key, lock_ver)
            )

            if res.rowcount == 1:
                self.conn.commit()
                return True
            else:
                cursor.execute("ROLLBACK")
                return False
        except Exception as e:
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
            raise e

    def renew_lease(self, provider: str, sport: str, operation: str, scope_key: str, lease_owner: str, ttl_minutes: int = 15) -> bool:
        cursor = self.conn.cursor()
        if not self.conn.in_transaction: cursor.execute("BEGIN IMMEDIATE")
        try:
            row = cursor.execute(
                """SELECT lock_version FROM sports_sync_cursor
                   WHERE provider = ? AND sport = ? AND operation = ? AND scope_key = ? AND lease_owner = ?
                """,
                (provider, sport, operation, scope_key, lease_owner)
            ).fetchone()

            if not row:
                cursor.execute("ROLLBACK")
                return False

            lock_ver = row[0]
            now = self.clock.now_utc()
            expires = now + timedelta(minutes=ttl_minutes)
            expires_str = format_utc(expires)
            now_str = format_utc(now)

            res = cursor.execute(
                """UPDATE sports_sync_cursor
                   SET lease_expires_at = ?, lock_version = lock_version + 1, updated_at = ?
                   WHERE provider = ? AND sport = ? AND operation = ? AND scope_key = ? AND lock_version = ?
                """,
                (expires_str, now_str, provider, sport, operation, scope_key, lock_ver)
            )

            if res.rowcount == 1:
                self.conn.commit()
                return True
            else:
                cursor.execute("ROLLBACK")
                return False
        except Exception as e:
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
            raise e

    def release_lease(self, provider: str, sport: str, operation: str, scope_key: str, lease_owner: str) -> None:
        cursor = self.conn.cursor()
        if not self.conn.in_transaction: cursor.execute("BEGIN IMMEDIATE")
        try:
            row = cursor.execute(
                """SELECT lock_version FROM sports_sync_cursor
                   WHERE provider = ? AND sport = ? AND operation = ? AND scope_key = ? AND lease_owner = ?
                """,
                (provider, sport, operation, scope_key, lease_owner)
            ).fetchone()

            if row:
                lock_ver = row[0]
                now_str = format_utc(self.clock.now_utc())
                cursor.execute(
                    """UPDATE sports_sync_cursor
                       SET lease_owner = NULL, lease_expires_at = NULL, lock_version = lock_version + 1, updated_at = ?
                       WHERE provider = ? AND sport = ? AND operation = ? AND scope_key = ? AND lock_version = ?
                    """,
                    (now_str, provider, sport, operation, scope_key, lock_ver)
                )
            self.conn.commit()
        except Exception as e:
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
            raise e

    def start_run(self, cursor_id: int, run_identity: str, provider: str, sport: str, operation: str, scope_key: str, mode: str, window_from: str, window_to: str, cursor_before_json: str) -> int:
        now_str = format_utc(self.clock.now_utc())
        res = self.conn.execute(
            """INSERT INTO sports_sync_run
               (run_identity, cursor_id, provider, sport, operation, scope_key, mode, window_from, window_to, status, started_at, cursor_before_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'RUNNING', ?, ?)
            """,
            (run_identity, cursor_id, provider, sport, operation, scope_key, mode, window_from, window_to, now_str, cursor_before_json)
        )
        return res.lastrowid

    def complete_run(self, run_id: int, status: str, cursor_after_json: str, metrics: dict, error_code: str | None = None) -> None:
        now_str = format_utc(self.clock.now_utc())

        updates = ["status = ?", "completed_at = ?"]
        params = [status, now_str]

        if cursor_after_json:
            updates.append("cursor_after_json = ?")
            params.append(cursor_after_json)

        ALLOWLIST = {
            "physical_http_attempts",
            "fallback_stats_calls",
            "discovered_count",
            "complete_count",
            "partial_count",
            "score_only_count",
            "permanently_unavailable_count",
            "transient_failed_count",
        }

        for k, v in metrics.items():
            if k in ALLOWLIST:
                updates.append(f"{k} = ?")
                params.append(v)

        if error_code:
            updates.append("error_code = ?")
            params.append(error_code)

        params.append(run_id)

        query = f"UPDATE sports_sync_run SET {', '.join(updates)} WHERE id = ?"
        self.conn.execute(query, params)
