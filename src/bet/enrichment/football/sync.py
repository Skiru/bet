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

    def run_in_immediate_transaction(self, callback):
        if self.conn.in_transaction:
            raise RuntimeError("Connection already has an active transaction")
        cursor = self.conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            res = callback()
            self.conn.commit()
            return res
        except Exception as e:
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
            raise e

    def acquire_lease(self, provider: str, sport: str, operation: str, scope_key: str, lease_owner: str, ttl_minutes: int = 15) -> bool:
        def callback():
            row = self.conn.execute(
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

            is_lease_active = False
            if row:
                owner, exp_str, lock_ver = row
                if owner and exp_str:
                    exp_dt = parse_canonical_or_offset_datetime(exp_str)
                    if exp_dt > now:
                        is_lease_active = True

            if not is_lease_active:
                running_runs = self.conn.execute(
                    """SELECT id FROM sports_sync_run
                       WHERE provider = ? AND sport = ? AND operation = ? AND scope_key = ? AND status = 'RUNNING'
                    """,
                    (provider, sport, operation, scope_key)
                ).fetchall()
                for r_row in running_runs:
                    run_id = r_row[0]
                    self.conn.execute(
                        """UPDATE sports_sync_run
                           SET status = 'ABANDONED', completed_at = ?, error_code = 'STALE_LEASE_RECOVERY'
                           WHERE id = ?
                        """,
                        (now_str, run_id)
                    )

            if not row:
                self.conn.execute(
                    """INSERT INTO sports_sync_cursor
                       (provider, sport, operation, scope_key, lease_owner, lease_expires_at, lock_version, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (provider, sport, operation, scope_key, lease_owner, expires_str, now_str, now_str)
                )
                return True

            owner, exp_str, lock_ver = row
            if owner and exp_str:
                exp_dt = parse_canonical_or_offset_datetime(exp_str)
                if exp_dt > now and owner != lease_owner:
                    return False

            res = self.conn.execute(
                """UPDATE sports_sync_cursor
                   SET lease_owner = ?, lease_expires_at = ?, lock_version = lock_version + 1, updated_at = ?
                   WHERE provider = ? AND sport = ? AND operation = ? AND scope_key = ? AND lock_version = ?
                """,
                (lease_owner, expires_str, now_str, provider, sport, operation, scope_key, lock_ver)
            )
            if res.rowcount == 1:
                return True
            else:
                return False
        return self.run_in_immediate_transaction(callback)

    def renew_lease(self, provider: str, sport: str, operation: str, scope_key: str, lease_owner: str, ttl_minutes: int = 15) -> bool:
        def callback():
            row = self.conn.execute(
                """SELECT lock_version FROM sports_sync_cursor
                   WHERE provider = ? AND sport = ? AND operation = ? AND scope_key = ? AND lease_owner = ?
                """,
                (provider, sport, operation, scope_key, lease_owner)
            ).fetchone()
            if not row:
                return False
            lock_ver = row[0]
            now = self.clock.now_utc()
            expires = now + timedelta(minutes=ttl_minutes)
            expires_str = format_utc(expires)
            now_str = format_utc(now)
            res = self.conn.execute(
                """UPDATE sports_sync_cursor
                   SET lease_expires_at = ?, lock_version = lock_version + 1, updated_at = ?
                   WHERE provider = ? AND sport = ? AND operation = ? AND scope_key = ? AND lock_version = ?
                """,
                (expires_str, now_str, provider, sport, operation, scope_key, lock_ver)
            )
            if res.rowcount == 1:
                return True
            else:
                return False
        return self.run_in_immediate_transaction(callback)

    def release_lease(self, provider: str, sport: str, operation: str, scope_key: str, lease_owner: str) -> None:
        def callback():
            row = self.conn.execute(
                """SELECT lock_version FROM sports_sync_cursor
                   WHERE provider = ? AND sport = ? AND operation = ? AND scope_key = ? AND lease_owner = ?
                """,
                (provider, sport, operation, scope_key, lease_owner)
            ).fetchone()
            if row:
                lock_ver = row[0]
                now_str = format_utc(self.clock.now_utc())
                self.conn.execute(
                    """UPDATE sports_sync_cursor
                       SET lease_owner = NULL, lease_expires_at = NULL, lock_version = lock_version + 1, updated_at = ?
                       WHERE provider = ? AND sport = ? AND operation = ? AND scope_key = ? AND lock_version = ?
                    """,
                    (now_str, provider, sport, operation, scope_key, lock_ver)
                )
        self.run_in_immediate_transaction(callback)

    def start_run(self, cursor_id: int, run_identity: str, provider: str, sport: str, operation: str, scope_key: str, mode: str, window_from: str, window_to: str, cursor_before_json: str) -> int:
        def callback():
            now_str = format_utc(self.clock.now_utc())
            res = self.conn.execute(
                """INSERT INTO sports_sync_run
                   (run_identity, cursor_id, provider, sport, operation, scope_key, mode, window_from, window_to, status, started_at, cursor_before_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'RUNNING', ?, ?)
                """,
                (run_identity, cursor_id, provider, sport, operation, scope_key, mode, window_from, window_to, now_str, cursor_before_json)
            )
            return res.lastrowid
        return self.run_in_immediate_transaction(callback)

    def complete_run(self, run_id: int, status: str, cursor_after_json: str, metrics: dict, error_code: str | None = None) -> None:
        def callback():
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
            query = f"UPDATE sports_sync_run SET {", ".join(updates)} WHERE id = ?"
            self.conn.execute(query, params)
        self.run_in_immediate_transaction(callback)

    def transition_cursor(self, cursor_id: int, committed_through_date: str, last_success_at: str) -> None:
        def callback():
            row = self.conn.execute(
                "SELECT committed_through_date FROM sports_sync_cursor WHERE id = ?",
                (cursor_id,)
            ).fetchone()

            existing_comm_date = row[0] if row else None

            from datetime import date as dt_date
            new_date = committed_through_date
            if existing_comm_date:
                try:
                    c_date = dt_date.fromisoformat(committed_through_date)
                    e_date = dt_date.fromisoformat(existing_comm_date)
                    if e_date > c_date:
                        new_date = existing_comm_date
                except ValueError:
                    pass

            self.conn.execute(
                """UPDATE sports_sync_cursor
                   SET committed_through_date = ?,
                       last_success_at = ?,
                       updated_at = ?,
                       lock_version = lock_version + 1
                   WHERE id = ?
                """,
                (new_date, last_success_at, last_success_at, cursor_id)
            )
        self.run_in_immediate_transaction(callback)
