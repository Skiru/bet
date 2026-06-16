import sqlite3
from datetime import UTC, datetime


class FootballSyncEngine:
    def __init__(self, conn: sqlite3.Connection, provider_client=None):
        self.conn = conn
        self.client = provider_client

    def acquire_lease(self, provider: str, sport: str, operation: str, scope_key: str, lease_owner: str) -> bool:
        # Check if cursor exists
        row = self.conn.execute(
            "SELECT lease_owner, lease_expires_at, lock_version FROM sports_sync_cursor WHERE provider = ? AND sport = ? AND operation = ? AND scope_key = ?",
            (provider, sport, operation, scope_key)
        ).fetchone()

        now = datetime.now(UTC).isoformat()
        expires = datetime.now(UTC).replace(year=datetime.now().year + 1).isoformat() # just a simple expiration

        if not row:
            # Create
            try:
                self.conn.execute(
                    "INSERT INTO sports_sync_cursor (provider, sport, operation, scope_key, lease_owner, lease_expires_at, lock_version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                    (provider, sport, operation, scope_key, lease_owner, expires, now, now)
                )
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

        owner, exp_str, lock_ver = row
        if owner and exp_str:
            exp_dt = datetime.fromisoformat(exp_str)
            if exp_dt > datetime.now(UTC) and owner != lease_owner:
                return False

        # Acquire
        res = self.conn.execute(
            "UPDATE sports_sync_cursor SET lease_owner = ?, lease_expires_at = ?, lock_version = lock_version + 1, updated_at = ? WHERE provider = ? AND sport = ? AND operation = ? AND scope_key = ? AND lock_version = ?",
            (lease_owner, expires, now, provider, sport, operation, scope_key, lock_ver)
        )
        self.conn.commit()
        return res.rowcount == 1
