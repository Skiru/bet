"""Repository classes for all database CRUD operations.

All SQL uses parameterized queries with ? placeholders — NEVER string interpolation.
JSON columns are serialized with json.dumps() on write and json.loads() on read.
"""

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from bet.db.models import (
    AnalysisRawData,
    AnalysisResult,
    Athlete,
    Bet,
    Competition,
    Coupon,
    DecisionOutcome,
    DecisionSnapshot,
    ESPNPrediction,
    Fixture,
    GateResult,
    LeagueProfile,
    MatchStat,
    OddsRecord,
    PipelineCandidate,
    PipelineRun,
    PlayerGamelog,
    PlayerSplit,
    PowerIndex,
    ScanResult,
    ScanRunStats,
    SourceHealth,
    Sport,
    Standing,
    Team,
    TeamATSRecord,
    TeamForm,
    TeamNews,
    TeamOURecord,
    TeamRoster,
    TipsterConsensus,
    TipsterPick,
    Transaction,
)

def _now() -> str:
    """Return current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# SportRepo
# ---------------------------------------------------------------------------

class SportRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def seed_defaults(self) -> None:
        """Insert all 14 sports with stat_keys."""
        _FALLBACK_STAT_KEYS = {
            "football": ["corners", "fouls", "yellow_cards", "red_cards", "shots", "shots_on_target", "possession", "goals", "offsides", "saves"],
            "basketball": ["points", "rebounds", "assists", "steals", "blocks", "turnovers", "fg_pct", "three_pct", "ft_pct"],
            "hockey": ["goals", "shots", "powerplay_goals", "pim", "hits", "blocks", "faceoff_pct"],
            "tennis": ["aces", "double_faults", "first_serve_pct", "break_points_won", "games_won", "sets_won", "total_games"],
            "volleyball": ["points", "aces", "blocks", "hitting_pct", "sets_won", "total_points", "errors"],
        }
        try:
            from bet.stats.market_ranking import SPORT_STAT_KEYS
            # Merge: imported keys override fallback where present
            stat_keys_dict = {**_FALLBACK_STAT_KEYS, **SPORT_STAT_KEYS}
        except (ImportError, ModuleNotFoundError):
            stat_keys_dict = _FALLBACK_STAT_KEYS

        defaults = [
            ("football", 1),
            ("volleyball", 1),
            ("basketball", 1),
            ("tennis", 1),
            ("hockey", 1),
        ]
        for name, tier in defaults:
            stat_keys = json.dumps(stat_keys_dict.get(name, []))
            self.conn.execute(
                "INSERT OR IGNORE INTO sports (name, tier, stat_keys) VALUES (?, ?, ?)",
                (name, tier, stat_keys),
            )

    def get_by_name(self, name: str) -> Sport | None:
        row = self.conn.execute(
            "SELECT id, name, tier, stat_keys FROM sports WHERE name = ?",
            (name,),
        ).fetchone()
        if row is None:
            return None
        return Sport(
            id=row["id"],
            name=row["name"],
            tier=row["tier"],
            stat_keys=json.loads(row["stat_keys"]),
        )

    def get_all(self) -> list[Sport]:
        rows = self.conn.execute(
            "SELECT id, name, tier, stat_keys FROM sports"
        ).fetchall()
        return [
            Sport(
                id=r["id"],
                name=r["name"],
                tier=r["tier"],
                stat_keys=json.loads(r["stat_keys"]),
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# TeamRepo
# ---------------------------------------------------------------------------

class TeamRepo:
    # Reject team names that are clearly scraped garbage (ads, odds, separators)
    _GARBAGE_PATTERNS = re.compile(
        r"^\s*$"                     # empty/whitespace
        r"|^\W+$"                    # only non-word chars ("- -", "---")
        r"|^#\d+"                    # ad anchors ("#100 FREE $20")
        r"|\$\d+"                    # dollar amounts
        r"|FREE|Sign Up|PICKSWISE"   # ad keywords
        r"|\[VIDEO\]"               # media tags
        r"|^\d[\d\s.]+$"            # pure numbers/odds ("1.03 11.00 23.00")
        r"|Bet \$"                   # betting promos
        r"|Get \$"                   # promo text
        r"|Bonus Bets"               # promo text
        , re.IGNORECASE
    )

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    @classmethod
    def _is_valid_team_name(cls, name: str) -> bool:
        """Return False for names that are clearly scraped garbage."""
        if not name or len(name.strip()) < 2:
            return False
        if cls._GARBAGE_PATTERNS.search(name):
            return False
        return True

    def find_or_create(
        self, name: str, sport_id: int, aliases: list[str] | None = None
    ) -> Team:
        """Find team by name or any alias. Create if not found.

        Rejects clearly invalid names (ads, odds strings, promo text)
        to prevent polluting the teams table with scraped garbage.
        """
        existing = self.resolve(name, sport_id)
        if existing:
            return existing
        if not self._is_valid_team_name(name):
            raise ValueError(
                f"Rejected garbage team name: {name!r} — "
                "likely scraped ad text, odds, or separator"
            )
        alias_json = json.dumps(aliases or [])
        cur = self.conn.execute(
            "INSERT INTO teams (sport_id, name, aliases) VALUES (?, ?, ?)",
            (sport_id, name, alias_json),
        )
        return Team(
            id=cur.lastrowid,
            sport_id=sport_id,
            name=name,
            aliases=aliases or [],
        )

    def resolve(self, name: str, sport_id: int) -> Team | None:
        """Resolve a name (possibly variant) to a canonical Team.

        Searches the canonical name first, then aliases using json_each(),
        then falls back to normalized (diacritics-stripped) comparison.

        Note: On diacritics match, auto-adds the ASCII variant as alias
        (write side-effect) to prevent future O(n) table scans for the
        same variant.
        """
        # Check canonical name
        row = self.conn.execute(
            "SELECT id, sport_id, name, aliases, country, venue, style_tags "
            "FROM teams WHERE sport_id = ? AND name = ?",
            (sport_id, name),
        ).fetchone()
        if row:
            return self._row_to_team(row)

        # Check aliases via json_each
        row = self.conn.execute(
            "SELECT t.id, t.sport_id, t.name, t.aliases, t.country, t.venue, t.style_tags "
            "FROM teams t, json_each(t.aliases) AS a "
            "WHERE t.sport_id = ? AND a.value = ?",
            (sport_id, name),
        ).fetchone()
        if row:
            return self._row_to_team(row)

        # Normalized fallback: strip diacritics + common suffixes
        import re
        import unicodedata
        from bet.utils import normalize_team_name

        normalized_input = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower().strip()
        suffix_stripped_input = normalize_team_name(name)
        # Guard: don't suffix-match if name has identity markers (reserves/youth/women)
        _identity_re = re.compile(r"\b(U2[0-9]|U1[7-9]|II|III|IV|B|W|Reserves?|Youth|Women|Juniors?)\b", re.IGNORECASE)
        has_identity_marker = bool(_identity_re.search(name))

        if not normalized_input or len(normalized_input) < 3:
            return None
        rows = self.conn.execute(
            "SELECT id, sport_id, name, aliases, country, venue, style_tags "
            "FROM teams WHERE sport_id = ?",
            (sport_id,),
        ).fetchall()
        for row in rows:
            canonical_norm = unicodedata.normalize("NFKD", row["name"]).encode("ascii", "ignore").decode("ascii").lower().strip()
            # Match on stripped diacritics
            if canonical_norm == normalized_input:
                # Auto-add the ASCII variant as alias to prevent future misses
                team = self._row_to_team(row)
                if name not in (team.aliases or []):
                    updated_aliases = list(team.aliases or []) + [name]
                    self.update_aliases(team.id, updated_aliases)
                return team
            # Match on fully normalized (suffix-stripped) — skip if identity markers differ
            if suffix_stripped_input and len(suffix_stripped_input) >= 3 and not has_identity_marker:
                candidate_has_marker = bool(_identity_re.search(row["name"]))
                if not candidate_has_marker:
                    canonical_suffix_stripped = normalize_team_name(row["name"])
                    if canonical_suffix_stripped == suffix_stripped_input:
                        team = self._row_to_team(row)
                        if name not in (team.aliases or []):
                            updated_aliases = list(team.aliases or []) + [name]
                            self.update_aliases(team.id, updated_aliases)
                        return team

        return None

    def update_aliases(self, team_id: int, new_aliases: list[str]) -> None:
        self.conn.execute(
            "UPDATE teams SET aliases = ? WHERE id = ?",
            (json.dumps(new_aliases), team_id),
        )

    def get_by_id(self, team_id: int) -> Team | None:
        row = self.conn.execute(
            "SELECT id, sport_id, name, aliases, country, venue, style_tags "
            "FROM teams WHERE id = ?",
            (team_id,),
        ).fetchone()
        return self._row_to_team(row) if row else None

    @staticmethod
    def _row_to_team(row: sqlite3.Row) -> Team:
        return Team(
            id=row["id"],
            sport_id=row["sport_id"],
            name=row["name"],
            aliases=json.loads(row["aliases"]),
            country=row["country"] or "",
            venue=row["venue"] or "",
            style_tags=json.loads(row["style_tags"]),
        )


class TeamSourceAliasRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._ensure_table()

    def _ensure_table(self) -> None:
        table_sql_row = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'team_source_aliases'"
        ).fetchone()
        table_sql = (table_sql_row["sql"] if table_sql_row and table_sql_row["sql"] else "")
        if table_sql and "UNIQUE(team_id, source, provider_team_name, provider_competition_hint)" not in table_sql:
            self._migrate_table()

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS team_source_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL REFERENCES teams(id),
                sport_id INTEGER NOT NULL REFERENCES sports(id),
                source TEXT NOT NULL,
                provider_team_name TEXT NOT NULL,
                provider_team_id TEXT,
                provider_slug TEXT,
                provider_competition_hint TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 0.0,
                verified_at TEXT,
                last_used_at TEXT,
                status TEXT NOT NULL DEFAULT 'candidate',
                UNIQUE(team_id, source, provider_team_name, provider_competition_hint)
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_team_source_aliases_lookup "
            "ON team_source_aliases(team_id, source, status, provider_competition_hint)"
        )

    def _migrate_table(self) -> None:
        self.conn.execute("ALTER TABLE team_source_aliases RENAME TO team_source_aliases_legacy")
        self.conn.execute(
            """
            CREATE TABLE team_source_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL REFERENCES teams(id),
                sport_id INTEGER NOT NULL REFERENCES sports(id),
                source TEXT NOT NULL,
                provider_team_name TEXT NOT NULL,
                provider_team_id TEXT,
                provider_slug TEXT,
                provider_competition_hint TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 0.0,
                verified_at TEXT,
                last_used_at TEXT,
                status TEXT NOT NULL DEFAULT 'candidate',
                UNIQUE(team_id, source, provider_team_name, provider_competition_hint)
            )
            """
        )
        self.conn.execute(
            """
            INSERT INTO team_source_aliases (
                team_id, sport_id, source, provider_team_name, provider_team_id,
                provider_slug, provider_competition_hint, confidence,
                verified_at, last_used_at, status
            )
            SELECT team_id, sport_id, source, provider_team_name, provider_team_id,
                   provider_slug, COALESCE(provider_competition_hint, ''), confidence,
                   verified_at, last_used_at, status
            FROM team_source_aliases_legacy
            """
        )
        self.conn.execute("DROP TABLE team_source_aliases_legacy")

    def get_verified_provider_team_id(
        self,
        team_id: int,
        source: str,
        provider_competition_hint: str = "",
    ) -> str | None:
        row = self.conn.execute(
            """
            SELECT id, provider_team_id
            FROM team_source_aliases
            WHERE team_id = ?
              AND source = ?
              AND status = 'verified'
              AND COALESCE(provider_team_id, '') != ''
              AND (provider_competition_hint = ? OR provider_competition_hint = '')
            ORDER BY
              CASE WHEN provider_competition_hint = ? THEN 0 ELSE 1 END,
              confidence DESC,
              COALESCE(last_used_at, verified_at, '') DESC
            LIMIT 1
            """,
            (team_id, source, provider_competition_hint or "", provider_competition_hint or ""),
        ).fetchone()
        if not row:
            return None
        self.conn.execute(
            "UPDATE team_source_aliases SET last_used_at = ? WHERE id = ?",
            (_now(), row["id"]),
        )
        return str(row["provider_team_id"])

    def get_candidate_provider_names(
        self,
        team_id: int,
        source: str,
        provider_competition_hint: str = "",
    ) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT provider_team_name
            FROM team_source_aliases
            WHERE team_id = ?
              AND source = ?
              AND status IN ('verified', 'candidate', 'stale')
              AND COALESCE(provider_team_name, '') != ''
              AND (provider_competition_hint = ? OR provider_competition_hint = '')
            ORDER BY
              CASE status
                WHEN 'verified' THEN 0
                WHEN 'candidate' THEN 1
                ELSE 2
              END,
              CASE WHEN provider_competition_hint = ? THEN 0 ELSE 1 END,
              confidence DESC,
              COALESCE(last_used_at, verified_at, '') DESC
            """,
            (team_id, source, provider_competition_hint or "", provider_competition_hint or ""),
        ).fetchall()
        return [str(row["provider_team_name"]) for row in rows if row["provider_team_name"]]

    def get_failed_provider_names(
        self,
        team_id: int,
        source: str,
        provider_competition_hint: str = "",
    ) -> set[str]:
        rows = self.conn.execute(
            """
            SELECT provider_team_name
            FROM team_source_aliases
            WHERE team_id = ?
              AND source = ?
              AND status = 'failed'
              AND COALESCE(provider_team_name, '') != ''
              AND (provider_competition_hint = ? OR provider_competition_hint = '')
            """,
            (team_id, source, provider_competition_hint or ""),
        ).fetchall()
        return {str(row["provider_team_name"]) for row in rows if row["provider_team_name"]}

    def upsert_alias(
        self,
        *,
        team_id: int,
        sport_id: int,
        source: str,
        provider_team_name: str,
        provider_team_id: str | None = None,
        provider_slug: str = "",
        provider_competition_hint: str = "",
        confidence: float = 1.0,
        status: str = "verified",
    ) -> None:
        timestamp = _now()
        verified_at = timestamp if status == "verified" else None
        self.conn.execute(
            """
            INSERT INTO team_source_aliases (
                team_id, sport_id, source, provider_team_name, provider_team_id,
                provider_slug, provider_competition_hint, confidence,
                verified_at, last_used_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_id, source, provider_team_name, provider_competition_hint) DO UPDATE SET
                sport_id = excluded.sport_id,
                provider_team_id = COALESCE(excluded.provider_team_id, team_source_aliases.provider_team_id),
                provider_slug = COALESCE(NULLIF(excluded.provider_slug, ''), team_source_aliases.provider_slug),
                confidence = CASE
                    WHEN excluded.confidence > team_source_aliases.confidence THEN excluded.confidence
                    ELSE team_source_aliases.confidence
                END,
                verified_at = COALESCE(excluded.verified_at, team_source_aliases.verified_at),
                last_used_at = excluded.last_used_at,
                status = CASE
                    WHEN excluded.status = 'verified' THEN 'verified'
                    WHEN team_source_aliases.status = 'verified' THEN team_source_aliases.status
                    ELSE excluded.status
                END
            """,
            (
                team_id,
                sport_id,
                source,
                provider_team_name,
                None if provider_team_id in (None, "") else str(provider_team_id),
                provider_slug,
                provider_competition_hint or "",
                confidence,
                verified_at,
                timestamp,
                status,
            ),
        )


# ---------------------------------------------------------------------------
# CompetitionRepo
# ---------------------------------------------------------------------------

class CompetitionRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def find_or_create(
        self,
        name: str,
        sport_id: int,
        country: str = "",
        importance: int = 3,
        season: str = "",
    ) -> int:
        """Return competition ID, creating if needed."""
        row = self.conn.execute(
            "SELECT id FROM competitions "
            "WHERE sport_id = ? AND name = ? AND season = ?",
            (sport_id, name, season),
        ).fetchone()
        if row:
            return row["id"]
        cur = self.conn.execute(
            "INSERT INTO competitions (sport_id, name, country, importance, season) "
            "VALUES (?, ?, ?, ?, ?)",
            (sport_id, name, country, importance, season),
        )
        return cur.lastrowid


# ---------------------------------------------------------------------------
# FixtureRepo
# ---------------------------------------------------------------------------

class FixtureRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, fixture: Fixture) -> int:
        """Insert or update fixture. Returns row ID."""
        cur = self.conn.execute(
            "INSERT INTO fixtures "
            "(external_id, sport_id, competition_id, home_team_id, away_team_id, "
            "kickoff, status, score_home, score_away, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(sport_id, home_team_id, away_team_id, kickoff) DO UPDATE SET "
            "status = excluded.status, "
            "score_home = excluded.score_home, "
            "score_away = excluded.score_away, "
            "source = excluded.source, "
            "fetched_at = excluded.fetched_at, "
            "external_id = COALESCE(excluded.external_id, fixtures.external_id), "
            "competition_id = COALESCE(excluded.competition_id, fixtures.competition_id)",
            (
                fixture.external_id or None,
                fixture.sport_id,
                fixture.competition_id,
                fixture.home_team_id,
                fixture.away_team_id,
                fixture.kickoff,
                fixture.status,
                fixture.score_home,
                fixture.score_away,
                fixture.source,
                fixture.fetched_at or _now(),
            ),
        )
        if cur.lastrowid:
            return cur.lastrowid
        # ON CONFLICT update doesn't set lastrowid; fetch it
        row = self.conn.execute(
            "SELECT id FROM fixtures "
            "WHERE sport_id = ? AND home_team_id = ? AND away_team_id = ? AND kickoff = ?",
            (fixture.sport_id, fixture.home_team_id, fixture.away_team_id, fixture.kickoff),
        ).fetchone()
        return row["id"]

    def get_by_date(self, date: str, sport_id: int | None = None) -> list[Fixture]:
        """Get fixtures for a date (YYYY-MM-DD prefix match on kickoff)."""
        if sport_id is not None:
            rows = self.conn.execute(
                "SELECT * FROM fixtures WHERE kickoff LIKE ? AND sport_id = ?",
                (f"{date}%", sport_id),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM fixtures WHERE kickoff LIKE ?",
                (f"{date}%",),
            ).fetchall()
        return [self._row_to_fixture(r) for r in rows]

    def get_by_id(self, fixture_id: int) -> Fixture | None:
        row = self.conn.execute(
            "SELECT * FROM fixtures WHERE id = ?", (fixture_id,)
        ).fetchone()
        return self._row_to_fixture(row) if row else None

    def get_pending_settlement(self, date: str) -> list[Fixture]:
        """Get fixtures for a date that haven't been settled."""
        rows = self.conn.execute(
            "SELECT * FROM fixtures WHERE kickoff LIKE ? AND status = 'scheduled'",
            (f"{date}%",),
        ).fetchall()
        return [self._row_to_fixture(r) for r in rows]

    def get_by_date_with_teams(self, date: str, sport_id: int | None = None) -> list[dict]:
        """JOIN fixtures + teams + competitions to return dicts with team names.

        Returns: [{fixture_id, sport_id, competition, home_team, away_team,
                   home_team_id, away_team_id, kickoff, status, ...}]
        """
        sql = (
            "SELECT f.id AS fixture_id, f.sport_id, f.kickoff, f.status, "
            "f.score_home, f.score_away, f.external_id, f.source, "
            "ht.name AS home_team, at.name AS away_team, "
            "ht.id AS home_team_id, at.id AS away_team_id, "
            "COALESCE(c.name, '') AS competition, "
            "COALESCE(s.name, '') AS sport_name "
            "FROM fixtures f "
            "JOIN teams ht ON f.home_team_id = ht.id "
            "JOIN teams at ON f.away_team_id = at.id "
            "LEFT JOIN competitions c ON f.competition_id = c.id "
            "LEFT JOIN sports s ON f.sport_id = s.id "
            "WHERE f.kickoff LIKE ?"
        )
        params: list = [f"{date}%"]
        if sport_id is not None:
            sql += " AND f.sport_id = ?"
            params.append(sport_id)
        sql += " ORDER BY f.kickoff"
        rows = self.conn.execute(sql, params).fetchall()
        return [
            {
                "fixture_id": r["fixture_id"],
                "sport_id": r["sport_id"],
                "sport_name": r["sport_name"],
                "competition": r["competition"],
                "home_team": r["home_team"],
                "away_team": r["away_team"],
                "home_team_id": r["home_team_id"],
                "away_team_id": r["away_team_id"],
                "kickoff": r["kickoff"],
                "status": r["status"],
                "score_home": r["score_home"],
                "score_away": r["score_away"],
                "external_id": r["external_id"] or "",
                "source": r["source"] or "",
            }
            for r in rows
        ]

    def get_by_teams_and_date(
        self, home_name: str, away_name: str, date: str, sport_id: int
    ) -> Fixture | None:
        """Resolve fixture by team names + date. Checks canonical name and aliases."""
        # First try canonical names
        row = self.conn.execute(
            "SELECT f.* FROM fixtures f "
            "JOIN teams ht ON f.home_team_id = ht.id "
            "JOIN teams at ON f.away_team_id = at.id "
            "WHERE ht.name = ? AND at.name = ? AND f.kickoff LIKE ? AND f.sport_id = ?",
            (home_name, away_name, f"{date}%", sport_id),
        ).fetchone()
        if row:
            return self._row_to_fixture(row)

        # Try aliases via json_each
        row = self.conn.execute(
            "SELECT f.* FROM fixtures f "
            "JOIN teams ht ON f.home_team_id = ht.id "
            "JOIN teams at ON f.away_team_id = at.id "
            "WHERE f.kickoff LIKE ? AND f.sport_id = ? "
            "AND (ht.name = ? OR EXISTS (SELECT 1 FROM json_each(ht.aliases) WHERE value = ?)) "
            "AND (at.name = ? OR EXISTS (SELECT 1 FROM json_each(at.aliases) WHERE value = ?))",
            (f"{date}%", sport_id, home_name, home_name, away_name, away_name),
        ).fetchone()
        if row:
            return self._row_to_fixture(row)

        return None

    def bulk_upsert(self, fixtures: list[Fixture]) -> list[int]:
        """Batch upsert multiple fixtures and return their row IDs.

        The caller owns transaction boundaries and commit behavior.
        """
        ids = []
        for fixture in fixtures:
            fid = self.upsert(fixture)
            ids.append(fid)
        return ids

    def update_result(
        self,
        fixture_id: int,
        score_home: int,
        score_away: int,
        status: str = "finished",
    ) -> None:
        self.conn.execute(
            "UPDATE fixtures SET score_home = ?, score_away = ?, status = ? WHERE id = ?",
            (score_home, score_away, status, fixture_id),
        )

    @staticmethod
    def _row_to_fixture(row: sqlite3.Row) -> Fixture:
        return Fixture(
            id=row["id"],
            sport_id=row["sport_id"],
            competition_id=row["competition_id"],
            home_team_id=row["home_team_id"],
            away_team_id=row["away_team_id"],
            kickoff=row["kickoff"],
            status=row["status"],
            score_home=row["score_home"],
            score_away=row["score_away"],
            external_id=row["external_id"] or "",
            source=row["source"] or "",
            fetched_at=row["fetched_at"] or "",
        )


# ---------------------------------------------------------------------------
# StatsRepo
# ---------------------------------------------------------------------------

class StatsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._sport_name_cache: dict[int, str] = {}

    def save_match_stats(
        self,
        fixture_id: int,
        team_id: int,
        stats: dict[str, float],
        source: str,
    ) -> None:
        """Batch insert match stats (one row per stat_key)."""
        now = _now()
        for key, value in stats.items():
            self.conn.execute(
                "INSERT OR REPLACE INTO match_stats "
                "(fixture_id, team_id, stat_key, stat_value, source, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (fixture_id, team_id, key, value, source, now),
            )

    def get_form(self, team_id: int, stat_key: str, n: int = 10) -> list[float]:
        """Get last N values for a stat from finished fixtures, most recent first."""
        rows = self.conn.execute(
            "SELECT ms.stat_value FROM match_stats ms "
            "JOIN fixtures f ON ms.fixture_id = f.id "
            "WHERE ms.team_id = ? AND ms.stat_key = ? AND f.status = 'finished' "
            "ORDER BY f.kickoff DESC LIMIT ?",
            (team_id, stat_key, n),
        ).fetchall()
        return [r["stat_value"] for r in rows]

    def get_h2h_stats(
        self, team_a_id: int, team_b_id: int, stat_key: str, n: int = 10
    ) -> list[float]:
        """Get stat values from H2H meetings between two teams."""
        rows = self.conn.execute(
            "SELECT ms.stat_value FROM match_stats ms "
            "JOIN fixtures f ON ms.fixture_id = f.id "
            "WHERE ms.team_id = ? AND ms.stat_key = ? "
            "AND f.status = 'finished' "
            "AND (f.home_team_id IN (?, ?) AND f.away_team_id IN (?, ?)) "
            "ORDER BY f.kickoff DESC LIMIT ?",
            (team_a_id, stat_key, team_a_id, team_b_id, team_a_id, team_b_id, n),
        ).fetchall()
        return [r["stat_value"] for r in rows]

    def is_stale(self, team_id: int, stat_key: str, max_age_hours: int = 12) -> bool:
        """Check if team_form data is older than max_age_hours."""
        row = self.conn.execute(
            "SELECT updated_at FROM team_form "
            "WHERE team_id = ? AND stat_key = ? AND h2h_opponent_id IS NULL",
            (team_id, stat_key),
        ).fetchone()
        if row is None:
            return True
        try:
            updated = datetime.fromisoformat(row["updated_at"])
            age = datetime.now(timezone.utc) - updated
            return age.total_seconds() > max_age_hours * 3600
        except (ValueError, TypeError):
            return True

    def save_team_form(self, form: TeamForm) -> None:
        """Upsert team_form row (denormalized cache).

        Validates stat values against SPORT_VALUE_RANGES before writing.
        Out-of-range values are filtered. If all values are invalid, the write is skipped.

        WARNING: Concurrent Write Hazard!
        Three scripts write to team_form simultaneously:
        - build_stats_cache.py (via ingest_scan_stats)
        - data_enrichment_agent.py (via _save_to_db) 
        - deep_stats_report.py (inline enrichment when NO_ENRICH is not set)
        Pipeline must serialize these writes (run sequentially, not in parallel).
        If parallel execution is needed, use WAL mode + retry on SQLITE_BUSY.
        
        Uses DELETE+INSERT wrapped in a SAVEPOINT to ensure atomicity.
        SQLite ON CONFLICT doesn't work with expression-based unique indexes
        (NULL h2h_opponent_id).
        """
        # --- ADR-2: Centralized stat validation (Task 1.1) ---
        form = self._validate_form_values(form)
        if form is None:
            return

        self.conn.execute("SAVEPOINT save_form")
        try:
            # Delete existing row (if any) matching the same logical key
            if form.h2h_opponent_id is None:
                self.conn.execute(
                    "DELETE FROM team_form "
                    "WHERE team_id = ? AND stat_key = ? AND h2h_opponent_id IS NULL",
                    (form.team_id, form.stat_key),
                )
            else:
                self.conn.execute(
                    "DELETE FROM team_form "
                    "WHERE team_id = ? AND stat_key = ? AND h2h_opponent_id = ?",
                    (form.team_id, form.stat_key, form.h2h_opponent_id),
                )
            self.conn.execute(
                "INSERT INTO team_form "
                "(team_id, sport_id, stat_key, l10_values, l5_values, l10_avg, l5_avg, "
                "h2h_values, h2h_opponent_id, trend, updated_at, source, source_event_ids, evidence_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    form.team_id,
                    form.sport_id,
                    form.stat_key,
                    json.dumps(form.l10_values),
                    json.dumps(form.l5_values),
                    form.l10_avg,
                    form.l5_avg,
                    json.dumps(form.h2h_values),
                    form.h2h_opponent_id,
                    form.trend,
                    form.updated_at or _now(),
                    form.source,
                    json.dumps(form.source_event_ids) if hasattr(form, 'source_event_ids') else "[]",
                    form.evidence_hash if hasattr(form, 'evidence_hash') else "",
                ),
            )
            self.conn.execute("RELEASE save_form")
        except Exception:
            self.conn.execute("ROLLBACK TO save_form")
            raise

    # --- Validation helpers (ADR-2) ---
    _logger = logging.getLogger("bet.db.repositories.StatsRepo")

    def _get_sport_name(self, sport_id: int) -> str | None:
        """Resolve sport_id to sport name (cached)."""
        if sport_id in self._sport_name_cache:
            return self._sport_name_cache[sport_id]
        row = self.conn.execute(
            "SELECT name FROM sports WHERE id = ?", (sport_id,)
        ).fetchone()
        if row:
            self._sport_name_cache[sport_id] = row["name"]
            return row["name"]
        return None

    def _validate_form_values(self, form: TeamForm) -> TeamForm | None:
        """Filter out-of-range stat values. Returns None if all values invalid."""
        try:
            from bet.stats.value_ranges import SPORT_VALUE_RANGES
        except ImportError:
            return form  # No validation module — pass through

        sport_name = self._get_sport_name(form.sport_id) if form.sport_id else None
        if not sport_name:
            return form  # Unknown sport — pass through

        ranges = SPORT_VALUE_RANGES.get(sport_name, {}).get(form.stat_key)
        if not ranges:
            return form  # No range defined for this stat — pass through

        lo, hi = ranges

        def _filter(values: list | None) -> list | None:
            if not values:
                return values
            filtered = [v for v in values if lo <= v <= hi]
            rejected = len(values) - len(filtered)
            if rejected:
                self._logger.warning(
                    "Rejected %d/%d values for %s/%s (range %.1f-%.1f): %s",
                    rejected, len(values), sport_name, form.stat_key, lo, hi,
                    [v for v in values if v < lo or v > hi][:5],
                )
            return filtered

        had_l10_values = bool(form.l10_values)
        had_l5_values = bool(form.l5_values)

        l10 = _filter(form.l10_values)
        l5 = _filter(form.l5_values)
        h2h = _filter(form.h2h_values)

        # If all L10 values were invalid, skip this write entirely
        if form.l10_values and not l10:
            self._logger.warning(
                "ALL l10 values out of range for sport=%s stat=%s — write SKIPPED",
                sport_name, form.stat_key,
            )
            return None

        # Rebuild form with filtered values and recomputed averages
        form.l10_values = l10
        form.l5_values = l5
        form.h2h_values = h2h
        if l10:
            form.l10_avg = round(sum(l10) / len(l10), 2)
        elif had_l10_values:
            form.l10_avg = None
        if l5:
            form.l5_avg = round(sum(l5) / len(l5), 2)
        elif had_l5_values:
            form.l5_avg = None
        return form

    def get_all_form_for_team(self, team_id: int, sport_id: int) -> list[TeamForm]:
        """All TeamForm rows for a team (all stat_keys, no H2H filter)."""
        rows = self.conn.execute(
            "SELECT * FROM team_form "
            "WHERE team_id = ? AND sport_id = ? AND h2h_opponent_id IS NULL",
            (team_id, sport_id),
        ).fetchall()
        return [self._row_to_team_form(r) for r in rows]

    def get_team_form_record(
        self, team_id: int, stat_key: str, h2h_opponent_id: int | None = None
    ) -> TeamForm | None:
        """Single TeamForm row by team_id + stat_key + optional H2H opponent."""
        if h2h_opponent_id is None:
            row = self.conn.execute(
                "SELECT * FROM team_form "
                "WHERE team_id = ? AND stat_key = ? AND h2h_opponent_id IS NULL",
                (team_id, stat_key),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT * FROM team_form "
                "WHERE team_id = ? AND stat_key = ? AND h2h_opponent_id = ?",
                (team_id, stat_key, h2h_opponent_id),
            ).fetchone()
        return self._row_to_team_form(row) if row else None

    def bulk_save_match_stats(
        self, rows: list[tuple[int, int, str, float, str]]
    ) -> None:
        """Batch insert/replace match_stats rows.

        Each tuple: (fixture_id, team_id, stat_key, stat_value, source).
        """
        now = _now()
        self.conn.executemany(
            "INSERT OR REPLACE INTO match_stats "
            "(fixture_id, team_id, stat_key, stat_value, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(fid, tid, sk, sv, src, now) for fid, tid, sk, sv, src in rows],
        )

    def get_match_stats(self, fixture_id: int) -> list[MatchStat]:
        """Return all match_stats rows for a fixture."""
        rows = self.conn.execute(
            "SELECT * FROM match_stats WHERE fixture_id = ? ORDER BY team_id, stat_key",
            (fixture_id,),
        ).fetchall()
        return [self._row_to_match_stat(row) for row in rows]

    @staticmethod
    def _row_to_team_form(row: sqlite3.Row) -> TeamForm:
        return TeamForm(
            id=row["id"],
            team_id=row["team_id"],
            sport_id=row["sport_id"],
            stat_key=row["stat_key"],
            l10_values=json.loads(row["l10_values"]),
            l5_values=json.loads(row["l5_values"]),
            l10_avg=row["l10_avg"],
            l5_avg=row["l5_avg"],
            h2h_values=json.loads(row["h2h_values"]),
            h2h_opponent_id=row["h2h_opponent_id"],
            trend=row["trend"] or "",
            updated_at=row["updated_at"] or "",
            source=row["source"] or "",
        )

    @staticmethod
    def _row_to_match_stat(row: sqlite3.Row) -> MatchStat:
        return MatchStat(
            id=row["id"],
            fixture_id=row["fixture_id"],
            team_id=row["team_id"],
            stat_key=row["stat_key"],
            stat_value=row["stat_value"],
            source=row["source"] or "",
            fetched_at=row["fetched_at"] or "",
        )

    # Public alias for external callers
    row_to_team_form = _row_to_team_form


# ---------------------------------------------------------------------------
# OddsRepo
# ---------------------------------------------------------------------------

class OddsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(self, record: OddsRecord) -> None:
        """Insert or ignore odds record (prevents duplicate inserts).

        Uses INSERT OR IGNORE against the unique index
        (fixture_id, bookmaker, market, selection, fetched_at).
        """
        self.conn.execute(
            "INSERT OR IGNORE INTO odds_history "
            "(fixture_id, bookmaker, market, selection, odds, line, fetched_at, is_closing) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.fixture_id,
                record.bookmaker,
                record.market,
                record.selection,
                record.odds,
                record.line,
                record.fetched_at or _now(),
                1 if record.is_closing else 0,
            ),
        )

    # Backwards-compatible aliases
    save_odds = save
    upsert = save

    def get_best_odds(
        self, fixture_id: int, market: str, selection: str
    ) -> float | None:
        row = self.conn.execute(
            "SELECT MAX(odds) AS best FROM odds_history "
            "WHERE fixture_id = ? AND market = ? AND selection = ?",
            (fixture_id, market, selection),
        ).fetchone()
        return row["best"] if row and row["best"] is not None else None

    def get_odds_history(self, fixture_id: int, market: str) -> list[OddsRecord]:
        rows = self.conn.execute(
            "SELECT * FROM odds_history WHERE fixture_id = ? AND market = ? "
            "ORDER BY fetched_at",
            (fixture_id, market),
        ).fetchall()
        return [
            OddsRecord(
                id=r["id"],
                fixture_id=r["fixture_id"],
                bookmaker=r["bookmaker"],
                market=r["market"],
                selection=r["selection"],
                odds=r["odds"],
                line=r["line"],
                fetched_at=r["fetched_at"],
                is_closing=bool(r["is_closing"]),
            )
            for r in rows
        ]

    def get_all_for_date(self, date: str) -> dict[int, list[OddsRecord]]:
        """All odds for fixtures on a date, keyed by fixture_id."""
        rows = self.conn.execute(
            "SELECT oh.* FROM odds_history oh "
            "JOIN fixtures f ON oh.fixture_id = f.id "
            "WHERE f.kickoff LIKE ? "
            "ORDER BY oh.fixture_id, oh.fetched_at",
            (f"{date}%",),
        ).fetchall()
        result: dict[int, list[OddsRecord]] = {}
        for r in rows:
            rec = self._row_to_odds_record(r)
            result.setdefault(rec.fixture_id, []).append(rec)
        return result

    def get_all_for_fixtures(self, fixture_ids: list[int]) -> dict[int, list[OddsRecord]]:
        """Batch odds lookup for a set of fixture IDs.

        Batches queries to stay under SQLite's variable limit (999).
        """
        if not fixture_ids:
            return {}
        result: dict[int, list[OddsRecord]] = {}
        BATCH = 900
        for i in range(0, len(fixture_ids), BATCH):
            batch = fixture_ids[i:i + BATCH]
            placeholders = ",".join("?" for _ in batch)
            rows = self.conn.execute(
                f"SELECT * FROM odds_history WHERE fixture_id IN ({placeholders}) "
                "ORDER BY fixture_id, fetched_at",
                batch,
            ).fetchall()
            for r in rows:
                rec = self._row_to_odds_record(r)
                result.setdefault(rec.fixture_id, []).append(rec)
        return result

    @staticmethod
    def _row_to_odds_record(r: sqlite3.Row) -> OddsRecord:
        return OddsRecord(
            id=r["id"],
            fixture_id=r["fixture_id"],
            bookmaker=r["bookmaker"],
            market=r["market"],
            selection=r["selection"],
            odds=r["odds"],
            line=r["line"],
            fetched_at=r["fetched_at"],
            is_closing=bool(r["is_closing"]),
        )


# ---------------------------------------------------------------------------
# CouponRepo
# ---------------------------------------------------------------------------

class CouponRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_coupon(self, coupon: Coupon) -> int:
        cur = self.conn.execute(
            "INSERT INTO coupons "
            "(coupon_id, coupon_type, total_odds, stake_pln, status, pnl_pln, "
            "placed_at, settled_at, betclic_ref, version, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                coupon.coupon_id,
                coupon.coupon_type,
                coupon.total_odds,
                coupon.stake_pln,
                coupon.status,
                coupon.pnl_pln,
                coupon.placed_at or None,
                coupon.settled_at or None,
                coupon.betclic_ref or None,
                coupon.version,
                coupon.created_at or _now(),
            ),
        )
        return cur.lastrowid

    def add_bet(self, bet: Bet) -> int:
        cur = self.conn.execute(
            "INSERT INTO bets "
            "(coupon_id, fixture_id, sport, event_name, market, selection, odds, "
            "min_odds, safety_score, hit_rate, status, pnl_pln, settled_at, "
            "market_pl, navigation_hint, stats_detail) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                bet.coupon_id,
                bet.fixture_id,
                bet.sport,
                bet.event_name,
                bet.market,
                bet.selection,
                bet.odds,
                bet.min_odds,
                bet.safety_score,
                bet.hit_rate,
                bet.status,
                bet.pnl_pln,
                bet.settled_at or None,
                bet.market_pl,
                bet.navigation_hint,
                json.dumps(bet.stats_detail) if bet.stats_detail else None,
            ),
        )
        return cur.lastrowid

    def get_pending(self) -> list[Coupon]:
        rows = self.conn.execute(
            "SELECT * FROM coupons WHERE status = 'pending'"
        ).fetchall()
        return [self._row_to_coupon(r) for r in rows]

    def settle_coupon(self, coupon_id: int, status: str, pnl: float) -> None:
        self.conn.execute(
            "UPDATE coupons SET status = ?, pnl_pln = ?, settled_at = ? WHERE id = ?",
            (status, pnl, _now(), coupon_id),
        )

    def settle_bet(self, bet_id: int, status: str, pnl: float) -> None:
        self.conn.execute(
            "UPDATE bets SET status = ?, pnl_pln = ?, settled_at = ? WHERE id = ?",
            (status, pnl, _now(), bet_id),
        )

    def get_coupon_with_bets(self, coupon_id: int) -> tuple[Coupon | None, list[Bet]]:
        row = self.conn.execute(
            "SELECT * FROM coupons WHERE id = ?", (coupon_id,)
        ).fetchone()
        if row is None:
            return None, []
        coupon = self._row_to_coupon(row)
        bet_rows = self.conn.execute(
            "SELECT * FROM bets WHERE coupon_id = ?", (coupon_id,)
        ).fetchall()
        bets = [self._row_to_bet(r) for r in bet_rows]
        return coupon, bets

    @staticmethod
    def _row_to_coupon(row: sqlite3.Row) -> Coupon:
        return Coupon(
            id=row["id"],
            coupon_id=row["coupon_id"],
            coupon_type=row["coupon_type"],
            total_odds=row["total_odds"],
            stake_pln=row["stake_pln"],
            status=row["status"],
            pnl_pln=row["pnl_pln"],
            placed_at=row["placed_at"] or "",
            settled_at=row["settled_at"] or "",
            betclic_ref=row["betclic_ref"] or "",
            version=row["version"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_bet(row: sqlite3.Row) -> Bet:
        return Bet(
            id=row["id"],
            coupon_id=row["coupon_id"],
            fixture_id=row["fixture_id"],
            sport=row["sport"],
            event_name=row["event_name"],
            market=row["market"],
            selection=row["selection"],
            odds=row["odds"],
            min_odds=row["min_odds"],
            safety_score=row["safety_score"],
            hit_rate=row["hit_rate"],
            status=row["status"],
            pnl_pln=row["pnl_pln"],
            settled_at=row["settled_at"] or "",
            market_pl=row["market_pl"] or "",
            navigation_hint=row["navigation_hint"] or "",
            stats_detail=json.loads(row["stats_detail"]) if row["stats_detail"] else None,
        )

    def create_with_bets(self, coupon: Coupon, bets: list[Bet]) -> tuple[int, list[int]]:
        """Atomic coupon + legs creation. Returns (coupon_db_id, [bet_db_ids])."""
        coupon_id = self.create_coupon(coupon)
        bet_ids = []
        for bet in bets:
            bet.coupon_id = coupon_id
            bet_ids.append(self.add_bet(bet))
        return coupon_id, bet_ids

    def get_pending_bets_with_details(self, date: str | None = None) -> list[dict]:
        """Pending bets with fixture + team info via JOINs."""
        query = (
            "SELECT b.*, c.coupon_id AS coupon_ref, c.stake_pln, c.total_odds, "
            "f.kickoff, f.score_home, f.score_away, "
            "ht.name AS home_team, at.name AS away_team, s.name AS sport_name "
            "FROM bets b "
            "JOIN coupons c ON b.coupon_id = c.id "
            "LEFT JOIN fixtures f ON b.fixture_id = f.id "
            "LEFT JOIN teams ht ON f.home_team_id = ht.id "
            "LEFT JOIN teams at ON f.away_team_id = at.id "
            "LEFT JOIN sports s ON f.sport_id = s.id "
            "WHERE b.status = 'pending'"
        )
        params: list = []
        if date:
            query += " AND f.kickoff LIKE ?"
            params.append(f"{date}%")
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_recent_losses(self, hours: int = 48) -> list[dict]:
        """Bets with status='lost' settled within last N hours."""
        rows = self.conn.execute(
            "SELECT b.event_name, b.market, b.selection, b.sport, b.settled_at "
            "FROM bets b "
            "WHERE b.status = 'lost' "
            "AND b.settled_at >= datetime('now', ?)",
            (f"-{hours} hours",),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# PipelineRepo
# ---------------------------------------------------------------------------

class PipelineRepo:
    PHASE_ORDER = ("PHASE_A", "PHASE_B", "PHASE_C", "PHASE_D", "PHASE_E")

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    @classmethod
    def _is_phase_step(cls, step: str) -> bool:
        return step in cls.PHASE_ORDER

    @staticmethod
    def _safe_load_stats(stats_raw: str | None):
        if not stats_raw:
            return None
        try:
            return json.loads(stats_raw)
        except json.JSONDecodeError:
            return "__MALFORMED_JSON__"

    @classmethod
    def _phase_index(cls, phase_id: str) -> int | None:
        try:
            return cls.PHASE_ORDER.index(phase_id)
        except ValueError:
            return None

    @classmethod
    def _base_phase_receipt(cls, date: str, phase_id: str, **overrides) -> dict:
        if not cls._is_phase_step(phase_id):
            raise ValueError(f"Unsupported phase receipt id: {phase_id}")
        receipt = {
            "run_date": date,
            "phase_id": phase_id,
            "status": "running",
            "completed_steps": [],
            "delegation_receipts": [],
            "artifacts": [],
            "db_receipts": [],
            "gate_verdict": "pending",
            "fallback_modes": [],
            "retry_count": 0,
            "resume_from": phase_id,
            "invalidate_if": [],
            "next_phase": None,
            "notes": "",
        }
        receipt.update(overrides)
        return receipt

    @staticmethod
    def _artifact_receipts_valid(receipt: dict) -> bool:
        artifacts = receipt.get("artifacts")
        if not isinstance(artifacts, list):
            return True
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                return False
            raw_path = artifact.get("path")
            if not raw_path:
                return False
            path = Path(raw_path)
            expected_exists = artifact.get("exists", True)
            if expected_exists and not path.exists():
                return False
            if not expected_exists:
                continue
            expected_size = artifact.get("size")
            if expected_size is not None:
                try:
                    observed_size = path.stat().st_size
                except OSError:
                    return False
                if int(observed_size) != int(expected_size):
                    return False
        return True

    @classmethod
    def _receipt_is_validated(cls, receipt: dict | None, row_status: str) -> bool:
        return (
            isinstance(receipt, dict)
            and row_status == "completed"
            and receipt.get("status") == "validated"
            and cls._artifact_receipts_valid(receipt)
        )

    def start_step(self, date: str, step: str) -> None:
        self.conn.execute(
            "INSERT INTO pipeline_runs (date, step, status, started_at) "
            "VALUES (?, ?, 'running', ?) "
            "ON CONFLICT(date, step) DO UPDATE SET "
            "status = 'running', started_at = excluded.started_at, "
            "error_message = NULL",
            (date, step, _now()),
        )

    def start_phase(self, date: str, phase_id: str, stats: dict | None = None) -> None:
        payload = self._base_phase_receipt(date, phase_id)
        if stats:
            payload.update(stats)
        self.conn.execute(
            "INSERT INTO pipeline_runs (date, step, status, started_at, stats) "
            "VALUES (?, ?, 'running', ?, ?) "
            "ON CONFLICT(date, step) DO UPDATE SET "
            "status = 'running', started_at = excluded.started_at, "
            "completed_at = NULL, error_message = NULL, stats = excluded.stats",
            (date, phase_id, _now(), json.dumps(payload)),
        )

    def complete_step(self, date: str, step: str, stats: dict | None = None) -> None:
        completed_at = _now()
        self.conn.execute(
            "INSERT INTO pipeline_runs (date, step, status, started_at, completed_at, stats) "
            "VALUES (?, ?, 'completed', ?, ?, ?) "
            "ON CONFLICT(date, step) DO UPDATE SET "
            "status = 'completed', completed_at = excluded.completed_at, stats = excluded.stats, error_message = NULL",
            (date, step, completed_at, completed_at, json.dumps(stats) if stats else None),
        )

    def complete_phase(self, date: str, phase_id: str, stats: dict | None = None) -> None:
        payload = self._base_phase_receipt(
            date,
            phase_id,
            status="validated",
            resume_from=phase_id,
        )
        if stats:
            payload.update(stats)
        phase_idx = self._phase_index(phase_id)
        payload["next_phase"] = (
            self.PHASE_ORDER[phase_idx + 1]
            if phase_idx is not None and phase_idx + 1 < len(self.PHASE_ORDER)
            else None
        )
        self.complete_step(date, phase_id, payload)

    def fail_step(self, date: str, step: str, error: str) -> None:
        completed_at = _now()
        self.conn.execute(
            "INSERT INTO pipeline_runs (date, step, status, started_at, completed_at, error_message) "
            "VALUES (?, ?, 'failed', ?, ?, ?) "
            "ON CONFLICT(date, step) DO UPDATE SET "
            "status = 'failed', completed_at = excluded.completed_at, error_message = excluded.error_message",
            (date, step, completed_at, completed_at, error),
        )

    def fail_phase(self, date: str, phase_id: str, error: str, stats: dict | None = None) -> None:
        payload = self._base_phase_receipt(
            date,
            phase_id,
            status="failed",
            resume_from=phase_id,
            notes=error,
        )
        if stats:
            payload.update(stats)
        self.conn.execute(
            "UPDATE pipeline_runs SET status = 'failed', completed_at = ?, error_message = ?, stats = ? "
            "WHERE date = ? AND step = ?",
            (_now(), error, json.dumps(payload), date, phase_id),
        )

    def get_completed_steps(self, date: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT step FROM pipeline_runs WHERE date = ? AND status = 'completed'",
            (date,),
        ).fetchall()
        return [r["step"] for r in rows]

    def get_step(self, date: str, step: str) -> dict | None:
        row = self.conn.execute(
            "SELECT step, status, started_at, completed_at, error_message, stats "
            "FROM pipeline_runs WHERE date = ? AND step = ?",
            (date, step),
        ).fetchone()
        if not row:
            return None
        return {
            "step": row["step"],
            "status": row["status"],
            "started_at": row["started_at"] or "",
            "completed_at": row["completed_at"] or "",
            "error_message": row["error_message"] or "",
            "stats": self._safe_load_stats(row["stats"]),
        }

    def get_phase_receipt(self, date: str, phase_id: str) -> dict | None:
        record = self.get_step(date, phase_id)
        if not record:
            return None
        stats = record.get("stats")
        if isinstance(stats, dict):
            return {
                **record,
                "phase_id": phase_id,
                "receipt": stats,
            }
        return {
            **record,
            "phase_id": phase_id,
            "receipt": stats,
        }

    def get_last_validated_phase(self, date: str) -> dict | None:
        validated: list[dict] = []
        for phase_id in self.PHASE_ORDER:
            receipt = self.get_phase_receipt(date, phase_id)
            if not receipt:
                break
            payload = receipt.get("receipt")
            if self._receipt_is_validated(payload, receipt.get("status")):
                validated.append(receipt)
                continue
            break
        if not validated:
            return None
        return validated[-1]

    def get_next_resume_phase(self, date: str) -> str | None:
        for phase_id in self.PHASE_ORDER:
            receipt = self.get_phase_receipt(date, phase_id)
            if not receipt:
                return phase_id
            payload = receipt.get("receipt")
            if not self._receipt_is_validated(payload, receipt.get("status")):
                return phase_id
        return None

    def get_run_status(self, date: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT step, status, started_at, completed_at, error_message, stats "
            "FROM pipeline_runs WHERE date = ? ORDER BY id",
            (date,),
        ).fetchall()
        return [
            {
                "step": r["step"],
                "status": r["status"],
                "started_at": r["started_at"] or "",
                "completed_at": r["completed_at"] or "",
                "error_message": r["error_message"] or "",
                "stats": self._safe_load_stats(r["stats"]),
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# SourceHealthRepo
# ---------------------------------------------------------------------------

class SourceHealthRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def record_success(self, source: str, response_ms: float) -> None:
        self.conn.execute(
            "INSERT INTO source_health (source_name, last_success, total_requests, avg_response_ms) "
            "VALUES (?, ?, 1, ?) "
            "ON CONFLICT(source_name) DO UPDATE SET "
            "last_success = excluded.last_success, "
            "consecutive_failures = 0, "
            "total_requests = source_health.total_requests + 1, "
            "avg_response_ms = ("
            "  (COALESCE(source_health.avg_response_ms, 0) * source_health.total_requests + ?) "
            "  / (source_health.total_requests + 1)"
            ")",
            (source, _now(), response_ms, response_ms),
        )

    def record_failure(self, source: str) -> None:
        self.conn.execute(
            "INSERT INTO source_health (source_name, last_failure, consecutive_failures, "
            "total_requests, total_failures) "
            "VALUES (?, ?, 1, 1, 1) "
            "ON CONFLICT(source_name) DO UPDATE SET "
            "last_failure = excluded.last_failure, "
            "consecutive_failures = source_health.consecutive_failures + 1, "
            "total_requests = source_health.total_requests + 1, "
            "total_failures = source_health.total_failures + 1",
            (source, _now()),
        )

    def get_health(self, source: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM source_health WHERE source_name = ?", (source,)
        ).fetchone()
        if row is None:
            return None
        return {
            "source_name": row["source_name"],
            "last_success": row["last_success"] or "",
            "last_failure": row["last_failure"] or "",
            "consecutive_failures": row["consecutive_failures"],
            "total_requests": row["total_requests"],
            "total_failures": row["total_failures"],
            "avg_response_ms": row["avg_response_ms"],
        }

    def get_all_health(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM source_health").fetchall()
        return [
            {
                "source_name": r["source_name"],
                "last_success": r["last_success"] or "",
                "last_failure": r["last_failure"] or "",
                "consecutive_failures": r["consecutive_failures"],
                "total_requests": r["total_requests"],
                "total_failures": r["total_failures"],
                "avg_response_ms": r["avg_response_ms"],
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# LeagueProfileRepo
# ---------------------------------------------------------------------------

class LeagueProfileRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, profile: LeagueProfile) -> None:
        self.conn.execute(
            "INSERT INTO league_profiles "
            "(competition_id, stat_key, season, avg_value, median_value, std_dev, sample_size, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(competition_id, stat_key, season) DO UPDATE SET "
            "avg_value = excluded.avg_value, "
            "median_value = excluded.median_value, "
            "std_dev = excluded.std_dev, "
            "sample_size = excluded.sample_size, "
            "updated_at = excluded.updated_at",
            (profile.competition_id, profile.stat_key, profile.season,
             profile.avg_value, profile.median_value, profile.std_dev,
             profile.sample_size, profile.updated_at or _now()),
        )

    def get_for_competition(self, competition_id: int, season: str = "") -> list[LeagueProfile]:
        rows = self.conn.execute(
            "SELECT * FROM league_profiles WHERE competition_id = ? AND season = ?",
            (competition_id, season),
        ).fetchall()
        return [
            LeagueProfile(
                id=r["id"], competition_id=r["competition_id"],
                stat_key=r["stat_key"], season=r["season"],
                avg_value=r["avg_value"], median_value=r["median_value"],
                std_dev=r["std_dev"], sample_size=r["sample_size"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def get_stat_avg(self, competition_id: int, stat_key: str, season: str = "") -> float | None:
        row = self.conn.execute(
            "SELECT avg_value FROM league_profiles "
            "WHERE competition_id = ? AND stat_key = ? AND season = ?",
            (competition_id, stat_key, season),
        ).fetchone()
        return row["avg_value"] if row else None


# ---------------------------------------------------------------------------
# AnalysisResultRepo
# ---------------------------------------------------------------------------

class AnalysisResultRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(self, result: AnalysisResult) -> None:
        """Insert or replace an analysis result."""
        self.conn.execute(
            "INSERT OR REPLACE INTO analysis_results "
            "(fixture_id, betting_date, has_data, best_market_name, best_market_line, "
            "best_market_direction, best_safety_score, markets_evaluated, ranking_json, "
            "three_way_check_json, warnings_json, stats_summary_json, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                result.fixture_id,
                result.betting_date,
                int(result.has_data),
                result.best_market_name,
                result.best_market_line,
                result.best_market_direction,
                result.best_safety_score,
                result.markets_evaluated,
                json.dumps(result.ranking_json),
                json.dumps(result.three_way_check_json) if result.three_way_check_json else None,
                json.dumps(result.warnings_json),
                json.dumps(result.stats_summary_json) if result.stats_summary_json else None,
                result.source,
                result.created_at or _now(),
            ),
        )

    def bulk_save(self, results: list[AnalysisResult]) -> None:
        """Bulk insert/replace analysis results using executemany."""
        if not results:
            return
        now = _now()
        self.conn.executemany(
            "INSERT OR REPLACE INTO analysis_results "
            "(fixture_id, betting_date, has_data, best_market_name, best_market_line, "
            "best_market_direction, best_safety_score, markets_evaluated, ranking_json, "
            "three_way_check_json, warnings_json, stats_summary_json, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    r.fixture_id,
                    r.betting_date,
                    int(r.has_data),
                    r.best_market_name,
                    r.best_market_line,
                    r.best_market_direction,
                    r.best_safety_score,
                    r.markets_evaluated,
                    json.dumps(r.ranking_json),
                    json.dumps(r.three_way_check_json) if r.three_way_check_json else None,
                    json.dumps(r.warnings_json),
                    json.dumps(r.stats_summary_json) if r.stats_summary_json else None,
                    r.source,
                    r.created_at or now,
                )
                for r in results
            ],
        )

    def get_by_date(self, betting_date: str) -> list[AnalysisResult]:
        """Get all analysis results for a betting date."""
        rows = self.conn.execute(
            "SELECT * FROM analysis_results WHERE betting_date = ? ORDER BY best_safety_score DESC",
            (betting_date,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_by_fixture(self, fixture_id: int, betting_date: str) -> AnalysisResult | None:
        """Get analysis result for a specific fixture on a date."""
        row = self.conn.execute(
            "SELECT * FROM analysis_results WHERE fixture_id = ? AND betting_date = ?",
            (fixture_id, betting_date),
        ).fetchone()
        return self._row_to_model(row) if row else None

    def get_with_data(self, betting_date: str) -> list[AnalysisResult]:
        """Get only analysis results that have data."""
        rows = self.conn.execute(
            "SELECT * FROM analysis_results WHERE betting_date = ? AND has_data = 1 "
            "ORDER BY best_safety_score DESC",
            (betting_date,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def update_stats_summary(self, fixture_id: int, betting_date: str, stats_summary: dict) -> int:
        """Update only the stats_summary_json field (for S4/S5/S6 enrichment).

        Uses UPDATE instead of INSERT OR REPLACE to preserve the row id.
        Returns number of rows updated (0 or 1).
        """
        cursor = self.conn.execute(
            "UPDATE analysis_results SET stats_summary_json = ? "
            "WHERE fixture_id = ? AND betting_date = ?",
            (json.dumps(stats_summary), fixture_id, betting_date),
        )
        return cursor.rowcount

    def delete_by_date(self, betting_date: str) -> int:
        """Delete all analysis results for a date. Returns count deleted."""
        cursor = self.conn.execute(
            "DELETE FROM analysis_results WHERE betting_date = ?", (betting_date,)
        )
        return cursor.rowcount

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> AnalysisResult:
        return AnalysisResult(
            id=row["id"],
            fixture_id=row["fixture_id"],
            betting_date=row["betting_date"],
            has_data=bool(row["has_data"]),
            best_market_name=row["best_market_name"] or "",
            best_market_line=row["best_market_line"],
            best_market_direction=row["best_market_direction"] or "",
            best_safety_score=row["best_safety_score"],
            markets_evaluated=row["markets_evaluated"],
            ranking_json=json.loads(row["ranking_json"]) if row["ranking_json"] else [],
            three_way_check_json=json.loads(row["three_way_check_json"]) if row["three_way_check_json"] else None,
            warnings_json=json.loads(row["warnings_json"]) if row["warnings_json"] else [],
            stats_summary_json=json.loads(row["stats_summary_json"]) if row["stats_summary_json"] else None,
            source=row["source"] or "",
            created_at=row["created_at"] or "",
        )


# ---------------------------------------------------------------------------
# GateResultRepo
# ---------------------------------------------------------------------------

class GateResultRepo:
    _STATUS_TO_BUCKET = {
        "APPROVED": "approved",
        "EXTENDED": "extended_pool",
        "EXTENDED_POOL": "extended_pool",
        "REJECTED": "rejected",
    }
    _BUCKET_TO_STATUS = {
        "approved": "APPROVED",
        "extended_pool": "EXTENDED",
        "rejected": "REJECTED",
    }

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    @classmethod
    def _normalize_bucket(cls, bucket: str | None) -> str | None:
        if not bucket:
            return None
        normalized = str(bucket).strip().lower()
        if normalized == "extended":
            return "extended_pool"
        if normalized in cls._BUCKET_TO_STATUS:
            return normalized
        return None

    @classmethod
    def _canonicalize_bucket_status(
        cls,
        status: str | None,
        gate_details: dict | None,
        rejection_reasons: list | None,
    ) -> tuple[str, str]:
        details = gate_details if isinstance(gate_details, dict) else {}
        reasons = rejection_reasons if isinstance(rejection_reasons, list) else []

        bucket = cls._normalize_bucket(details.get("bucket"))
        if not bucket and status:
            bucket = cls._STATUS_TO_BUCKET.get(str(status).strip().upper())
        if not bucket:
            if details.get("extended_pool_reason"):
                bucket = "extended_pool"
            elif reasons or details.get("rejection_reason"):
                bucket = "rejected"
            else:
                bucket = "approved"

        return bucket, cls._BUCKET_TO_STATUS[bucket]

    def save(self, result: GateResult) -> None:
        """Insert or replace a gate result."""
        self.conn.execute(
            "INSERT OR REPLACE INTO gate_results "
            "(fixture_id, betting_date, status, gate_score, gate_details_json, "
            "best_market_name, best_market_line, best_market_direction, best_safety_score, "
            "ev, risk_tier, rejection_reasons_json, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                result.fixture_id,
                result.betting_date,
                result.status,
                result.gate_score,
                json.dumps(result.gate_details_json),
                result.best_market_name,
                result.best_market_line,
                result.best_market_direction,
                result.best_safety_score,
                result.ev,
                result.risk_tier,
                json.dumps(result.rejection_reasons_json),
                result.source,
                result.created_at or _now(),
            ),
        )

    def bulk_save(self, results: list[GateResult]) -> None:
        """Bulk insert/replace gate results using executemany."""
        if not results:
            return
        now = _now()
        self.conn.executemany(
            "INSERT OR REPLACE INTO gate_results "
            "(fixture_id, betting_date, status, gate_score, gate_details_json, "
            "best_market_name, best_market_line, best_market_direction, best_safety_score, "
            "ev, risk_tier, rejection_reasons_json, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    r.fixture_id,
                    r.betting_date,
                    r.status,
                    r.gate_score,
                    json.dumps(r.gate_details_json),
                    r.best_market_name,
                    r.best_market_line,
                    r.best_market_direction,
                    r.best_safety_score,
                    r.ev,
                    r.risk_tier,
                    json.dumps(r.rejection_reasons_json),
                    r.source,
                    r.created_at or now,
                )
                for r in results
            ],
        )

    def get_by_date(self, betting_date: str) -> list[GateResult]:
        """Get all gate results for a betting date."""
        rows = self.conn.execute(
            "SELECT * FROM gate_results WHERE betting_date = ? ORDER BY best_safety_score DESC",
            (betting_date,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_approved(self, betting_date: str) -> list[GateResult]:
        """Get approved gate results for coupon building."""
        return [result for result in self.get_by_date(betting_date) if result.status == "APPROVED"]

    def get_extended(self, betting_date: str) -> list[GateResult]:
        """Get extended pool gate results."""
        return [result for result in self.get_by_date(betting_date) if result.status == "EXTENDED"]

    def get_rejected(self, betting_date: str) -> list[GateResult]:
        """Get rejected gate results."""
        return [result for result in self.get_by_date(betting_date) if result.status == "REJECTED"]

    def delete_by_date(self, betting_date: str) -> int:
        """Delete all gate results for a date. Returns count deleted."""
        cursor = self.conn.execute(
            "DELETE FROM gate_results WHERE betting_date = ?", (betting_date,)
        )
        return cursor.rowcount

    @classmethod
    def _row_to_model(cls, row: sqlite3.Row) -> GateResult:
        gate_details = json.loads(row["gate_details_json"]) if row["gate_details_json"] else {}
        if not isinstance(gate_details, dict):
            gate_details = {}

        rejection_reasons = json.loads(row["rejection_reasons_json"]) if row["rejection_reasons_json"] else []
        if isinstance(rejection_reasons, str):
            rejection_reasons = [rejection_reasons]
        elif not isinstance(rejection_reasons, list):
            rejection_reasons = []

        bucket, status = cls._canonicalize_bucket_status(
            row["status"],
            gate_details,
            rejection_reasons,
        )
        gate_details.setdefault("bucket", bucket)

        return GateResult(
            id=row["id"],
            fixture_id=row["fixture_id"],
            betting_date=row["betting_date"],
            status=status,
            gate_score=row["gate_score"],
            gate_details_json=gate_details,
            best_market_name=row["best_market_name"] or "",
            best_market_line=row["best_market_line"],
            best_market_direction=row["best_market_direction"] or "",
            best_safety_score=row["best_safety_score"],
            ev=row["ev"],
            risk_tier=row["risk_tier"] or "",
            rejection_reasons_json=rejection_reasons,
            source=row["source"] or "",
            created_at=row["created_at"] or "",
        )


# ---------------------------------------------------------------------------
# AnalysisRawDataRepo
# ---------------------------------------------------------------------------

class AnalysisRawDataRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(self, raw: AnalysisRawData) -> None:
        """Insert or replace raw analysis data."""
        self.conn.execute(
            "INSERT OR REPLACE INTO analysis_raw_data "
            "(fixture_id, betting_date, team_a_l10_json, team_b_l10_json, "
            "h2h_meetings_json, per_market_details_json, safety_input_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                raw.fixture_id,
                raw.betting_date,
                json.dumps(raw.team_a_l10_json, ensure_ascii=False),
                json.dumps(raw.team_b_l10_json, ensure_ascii=False),
                json.dumps(raw.h2h_meetings_json, ensure_ascii=False),
                json.dumps(raw.per_market_details_json, ensure_ascii=False),
                json.dumps(raw.safety_input_json, ensure_ascii=False) if raw.safety_input_json else None,
                raw.created_at or _now(),
            ),
        )

    def get_by_fixture(self, fixture_id: int, betting_date: str) -> AnalysisRawData | None:
        """Get raw data for a specific fixture and date."""
        row = self.conn.execute(
            "SELECT * FROM analysis_raw_data WHERE fixture_id = ? AND betting_date = ?",
            (fixture_id, betting_date),
        ).fetchone()
        if not row:
            return None
        return self._row_to_model(row)

    def get_by_date(self, betting_date: str) -> list[AnalysisRawData]:
        """Get all raw data for a betting date."""
        rows = self.conn.execute(
            "SELECT * FROM analysis_raw_data WHERE betting_date = ?",
            (betting_date,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> AnalysisRawData:
        return AnalysisRawData(
            id=row["id"],
            fixture_id=row["fixture_id"],
            betting_date=row["betting_date"],
            team_a_l10_json=json.loads(row["team_a_l10_json"]) if row["team_a_l10_json"] else {},
            team_b_l10_json=json.loads(row["team_b_l10_json"]) if row["team_b_l10_json"] else {},
            h2h_meetings_json=json.loads(row["h2h_meetings_json"]) if row["h2h_meetings_json"] else {},
            per_market_details_json=json.loads(row["per_market_details_json"]) if row["per_market_details_json"] else [],
            safety_input_json=json.loads(row["safety_input_json"]) if row["safety_input_json"] else None,
            created_at=row["created_at"] or "",
        )


# ---------------------------------------------------------------------------
# DecisionSnapshotRepo
# ---------------------------------------------------------------------------

class DecisionSnapshotRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(self, snapshot: DecisionSnapshot) -> None:
        """Insert or replace decision snapshot."""
        self.conn.execute(
            "INSERT OR REPLACE INTO decision_snapshots "
            "(bet_id, fixture_id, betting_date, chosen_market, chosen_line, "
            "chosen_direction, safety_score, all_markets_considered_json, "
            "reasoning_json, thresholds_json, flip_conditions_json, "
            "team_a_snapshot_json, team_b_snapshot_json, h2h_snapshot_json, "
            "three_way_check_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot.bet_id,
                snapshot.fixture_id,
                snapshot.betting_date,
                snapshot.chosen_market,
                snapshot.chosen_line,
                snapshot.chosen_direction,
                snapshot.safety_score,
                json.dumps(snapshot.all_markets_considered_json, ensure_ascii=False),
                json.dumps(snapshot.reasoning_json, ensure_ascii=False),
                json.dumps(snapshot.thresholds_json, ensure_ascii=False),
                json.dumps(snapshot.flip_conditions_json, ensure_ascii=False),
                json.dumps(snapshot.team_a_snapshot_json, ensure_ascii=False),
                json.dumps(snapshot.team_b_snapshot_json, ensure_ascii=False),
                json.dumps(snapshot.h2h_snapshot_json, ensure_ascii=False),
                json.dumps(snapshot.three_way_check_json, ensure_ascii=False) if snapshot.three_way_check_json else None,
                snapshot.created_at or _now(),
            ),
        )

    def get_by_bet(self, bet_id: int) -> DecisionSnapshot | None:
        """Get snapshot for a specific bet."""
        row = self.conn.execute(
            "SELECT * FROM decision_snapshots WHERE bet_id = ?", (bet_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_model(row)

    def get_by_fixture(self, fixture_id: int) -> list[DecisionSnapshot]:
        """Get all snapshots for a fixture."""
        rows = self.conn.execute(
            "SELECT * FROM decision_snapshots WHERE fixture_id = ?", (fixture_id,)
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_by_date(self, betting_date: str) -> list[DecisionSnapshot]:
        """Get all snapshots for a betting date."""
        rows = self.conn.execute(
            "SELECT * FROM decision_snapshots WHERE betting_date = ?", (betting_date,)
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> DecisionSnapshot:
        return DecisionSnapshot(
            id=row["id"],
            bet_id=row["bet_id"],
            fixture_id=row["fixture_id"],
            betting_date=row["betting_date"],
            chosen_market=row["chosen_market"],
            chosen_line=row["chosen_line"],
            chosen_direction=row["chosen_direction"],
            safety_score=row["safety_score"],
            all_markets_considered_json=json.loads(row["all_markets_considered_json"]) if row["all_markets_considered_json"] else [],
            reasoning_json=json.loads(row["reasoning_json"]) if row["reasoning_json"] else {},
            thresholds_json=json.loads(row["thresholds_json"]) if row["thresholds_json"] else {},
            flip_conditions_json=json.loads(row["flip_conditions_json"]) if row["flip_conditions_json"] else {},
            team_a_snapshot_json=json.loads(row["team_a_snapshot_json"]) if row["team_a_snapshot_json"] else {},
            team_b_snapshot_json=json.loads(row["team_b_snapshot_json"]) if row["team_b_snapshot_json"] else {},
            h2h_snapshot_json=json.loads(row["h2h_snapshot_json"]) if row["h2h_snapshot_json"] else {},
            three_way_check_json=json.loads(row["three_way_check_json"]) if row["three_way_check_json"] else None,
            created_at=row["created_at"] or "",
        )


# ---------------------------------------------------------------------------
# DecisionOutcomeRepo
# ---------------------------------------------------------------------------

class DecisionOutcomeRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(self, outcome: DecisionOutcome) -> None:
        """Insert or replace decision outcome."""
        self.conn.execute(
            "INSERT OR REPLACE INTO decision_outcomes "
            "(bet_id, fixture_id, betting_date, sport, competition, market, "
            "line, direction, predicted_value, actual_value, deviation, "
            "deviation_pct, result, prediction_accuracy_json, pattern_tags_json, "
            "notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                outcome.bet_id,
                outcome.fixture_id,
                outcome.betting_date,
                outcome.sport,
                outcome.competition,
                outcome.market,
                outcome.line,
                outcome.direction,
                outcome.predicted_value,
                outcome.actual_value,
                outcome.deviation,
                outcome.deviation_pct,
                outcome.result,
                json.dumps(outcome.prediction_accuracy_json, ensure_ascii=False),
                json.dumps(outcome.pattern_tags_json, ensure_ascii=False),
                outcome.notes or "",
                outcome.created_at or _now(),
            ),
        )

    def get_by_bet(self, bet_id: int) -> DecisionOutcome | None:
        """Get outcome for a specific bet."""
        row = self.conn.execute(
            "SELECT * FROM decision_outcomes WHERE bet_id = ?", (bet_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_model(row)

    def get_by_sport(self, sport: str, limit: int = 100) -> list[DecisionOutcome]:
        rows = self.conn.execute(
            "SELECT * FROM decision_outcomes WHERE sport = ? ORDER BY created_at DESC LIMIT ?",
            (sport, limit),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_by_market(self, market: str, limit: int = 100) -> list[DecisionOutcome]:
        rows = self.conn.execute(
            "SELECT * FROM decision_outcomes WHERE market = ? ORDER BY created_at DESC LIMIT ?",
            (market, limit),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_by_sport_and_market(self, sport: str, market: str, limit: int = 100) -> list[DecisionOutcome]:
        rows = self.conn.execute(
            "SELECT * FROM decision_outcomes WHERE sport = ? AND market = ? ORDER BY created_at DESC LIMIT ?",
            (sport, market, limit),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_by_competition(self, competition: str, limit: int = 100) -> list[DecisionOutcome]:
        rows = self.conn.execute(
            "SELECT * FROM decision_outcomes WHERE competition = ? ORDER BY created_at DESC LIMIT ?",
            (competition, limit),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_all_settled(self, limit: int = 500) -> list[DecisionOutcome]:
        rows = self.conn.execute(
            "SELECT * FROM decision_outcomes ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_deviation_stats(self, sport: str | None = None, market: str | None = None) -> dict:
        """Get aggregate deviation statistics."""
        conditions: list[str] = ["actual_value IS NOT NULL", "predicted_value IS NOT NULL"]
        params: list = []
        if sport:
            conditions.append("sport = ?")
            params.append(sport)
        if market:
            conditions.append("market = ?")
            params.append(market)

        where_clause = "WHERE " + " AND ".join(conditions)

        row = self.conn.execute(
            "SELECT COUNT(*) as count, "
            "AVG(deviation) as avg_deviation, "
            "AVG(deviation_pct) as avg_deviation_pct, "
            "SUM(CASE WHEN deviation > 0 THEN 1 ELSE 0 END) as overestimate_count, "
            "SUM(CASE WHEN deviation < 0 THEN 1 ELSE 0 END) as underestimate_count, "
            "SUM(CASE WHEN result = 'won' THEN 1 ELSE 0 END) as won_count, "
            "SUM(CASE WHEN result = 'lost' THEN 1 ELSE 0 END) as lost_count "
            "FROM decision_outcomes " + where_clause,
            params,
        ).fetchone()

        return {
            "count": row["count"] or 0,
            "avg_deviation": round(row["avg_deviation"], 3) if row["avg_deviation"] else 0.0,
            "avg_deviation_pct": round(row["avg_deviation_pct"], 1) if row["avg_deviation_pct"] else 0.0,
            "overestimate_count": row["overestimate_count"] or 0,
            "underestimate_count": row["underestimate_count"] or 0,
            "won_count": row["won_count"] or 0,
            "lost_count": row["lost_count"] or 0,
        }

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> DecisionOutcome:
        return DecisionOutcome(
            id=row["id"],
            bet_id=row["bet_id"],
            fixture_id=row["fixture_id"],
            betting_date=row["betting_date"],
            sport=row["sport"],
            competition=row["competition"] or "",
            market=row["market"],
            line=row["line"],
            direction=row["direction"],
            predicted_value=row["predicted_value"],
            actual_value=row["actual_value"],
            deviation=row["deviation"],
            deviation_pct=row["deviation_pct"],
            result=row["result"],
            prediction_accuracy_json=json.loads(row["prediction_accuracy_json"]) if row["prediction_accuracy_json"] else {},
            pattern_tags_json=json.loads(row["pattern_tags_json"]) if row["pattern_tags_json"] else [],
            notes=row["notes"] or "",
            created_at=row["created_at"] or "",
        )


# ---------------------------------------------------------------------------
# ScanResultRepo
# ---------------------------------------------------------------------------

class ScanResultRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def bulk_insert(self, results: list[ScanResult]) -> int:
        """Insert multiple scan results using INSERT OR IGNORE. Returns count inserted."""
        if not results:
            return 0
        before = self.conn.execute("SELECT COUNT(*) FROM scan_results").fetchone()[0]
        self.conn.executemany(
            "INSERT OR IGNORE INTO scan_results "
            "(betting_date, sport, source_domain, event_key, home_team, away_team, "
            "competition, kickoff, raw_data, scan_timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    r.betting_date,
                    r.sport,
                    r.source_domain,
                    r.event_key,
                    r.home_team,
                    r.away_team,
                    r.competition,
                    r.kickoff,
                    json.dumps(r.raw_data),
                    r.scan_timestamp or _now(),
                )
                for r in results
            ],
        )
        after = self.conn.execute("SELECT COUNT(*) FROM scan_results").fetchone()[0]
        return after - before

    def upsert(self, result: ScanResult) -> int:
        """Insert or replace a single scan result. Returns row ID."""
        cursor = self.conn.execute(
            "INSERT OR REPLACE INTO scan_results "
            "(betting_date, sport, source_domain, event_key, home_team, away_team, "
            "competition, kickoff, raw_data, scan_timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                result.betting_date,
                result.sport,
                result.source_domain,
                result.event_key,
                result.home_team,
                result.away_team,
                result.competition,
                result.kickoff,
                json.dumps(result.raw_data),
                result.scan_timestamp or _now(),
            ),
        )
        return cursor.lastrowid

    def get_by_date_and_sport(self, date: str, sport: str) -> list[ScanResult]:
        """Get all scan results for a betting date and sport."""
        rows = self.conn.execute(
            "SELECT * FROM scan_results WHERE betting_date = ? AND sport = ? "
            "ORDER BY event_key",
            (date, sport),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_all_by_date(self, date: str) -> list[ScanResult]:
        """Get all scan results for a betting date."""
        rows = self.conn.execute(
            "SELECT * FROM scan_results WHERE betting_date = ? ORDER BY sport, event_key",
            (date,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def delete_by_date(self, date: str) -> int:
        """Delete all scan results for a date. Returns count deleted."""
        cursor = self.conn.execute(
            "DELETE FROM scan_results WHERE betting_date = ?", (date,)
        )
        return cursor.rowcount

    def record_run_stats(self, stats: ScanRunStats) -> None:
        """Upsert scan run statistics for a sport on a date."""
        self.conn.execute(
            "INSERT OR REPLACE INTO scan_run_stats "
            "(betting_date, sport, scanner_group, events_found, sources_ok, "
            "sources_failed, deep_links_found, duration_seconds, validation_passed, "
            "gaps_description, scan_timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                stats.betting_date,
                stats.sport,
                stats.scanner_group,
                stats.events_found,
                stats.sources_ok,
                stats.sources_failed,
                stats.deep_links_found,
                stats.duration_seconds,
                int(stats.validation_passed),
                json.dumps(stats.gaps_description),
                stats.scan_timestamp or _now(),
            ),
        )

    def get_run_stats(self, date: str) -> list[ScanRunStats]:
        """Get all scan run stats for a date."""
        rows = self.conn.execute(
            "SELECT * FROM scan_run_stats WHERE betting_date = ? ORDER BY sport",
            (date,),
        ).fetchall()
        return [self._run_stats_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> ScanResult:
        return ScanResult(
            id=row["id"],
            betting_date=row["betting_date"],
            sport=row["sport"],
            source_domain=row["source_domain"],
            event_key=row["event_key"],
            home_team=row["home_team"] or "",
            away_team=row["away_team"] or "",
            competition=row["competition"] or "",
            kickoff=row["kickoff"] or "",
            raw_data=json.loads(row["raw_data"]) if row["raw_data"] else {},
            scan_timestamp=row["scan_timestamp"] or "",
        )

    @staticmethod
    def _run_stats_to_model(row: sqlite3.Row) -> ScanRunStats:
        return ScanRunStats(
            id=row["id"],
            betting_date=row["betting_date"],
            sport=row["sport"],
            scanner_group=row["scanner_group"],
            events_found=row["events_found"],
            sources_ok=row["sources_ok"],
            sources_failed=row["sources_failed"],
            deep_links_found=row["deep_links_found"],
            duration_seconds=row["duration_seconds"] or 0.0,
            validation_passed=bool(row["validation_passed"]),
            gaps_description=json.loads(row["gaps_description"]) if row["gaps_description"] else [],
            scan_timestamp=row["scan_timestamp"] or "",
        )


# ---------------------------------------------------------------------------
# AthleteRepo
# ---------------------------------------------------------------------------

class AthleteRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, athlete: Athlete) -> int:
        """Insert or update athlete, returning the row ID."""
        self.conn.execute(
            "INSERT INTO athletes (external_id, sport_id, team_id, name, position, jersey, age, height, weight, status, source, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(external_id, sport_id) DO UPDATE SET "
            "team_id=excluded.team_id, name=excluded.name, position=excluded.position, "
            "jersey=excluded.jersey, age=excluded.age, height=excluded.height, "
            "weight=excluded.weight, status=excluded.status, updated_at=excluded.updated_at",
            (
                athlete.external_id, athlete.sport_id, athlete.team_id, athlete.name,
                athlete.position, athlete.jersey, athlete.age, athlete.height,
                athlete.weight, athlete.status, athlete.source, athlete.updated_at or _now(),
            ),
        )
        row = self.conn.execute(
            "SELECT id FROM athletes WHERE external_id = ? AND sport_id = ?",
            (athlete.external_id, athlete.sport_id),
        ).fetchone()
        return row["id"] if row else 0

    def get_by_external_id(self, external_id: str, sport_id: int) -> Athlete | None:
        row = self.conn.execute(
            "SELECT * FROM athletes WHERE external_id = ? AND sport_id = ?",
            (external_id, sport_id),
        ).fetchone()
        return self._row_to_model(row) if row else None

    def get_by_team(self, team_id: int) -> list[Athlete]:
        rows = self.conn.execute(
            "SELECT * FROM athletes WHERE team_id = ? ORDER BY name", (team_id,)
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_by_sport(self, sport_id: int) -> list[Athlete]:
        rows = self.conn.execute(
            "SELECT * FROM athletes WHERE sport_id = ? ORDER BY name", (sport_id,)
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> Athlete:
        return Athlete(
            id=row["id"],
            external_id=row["external_id"],
            sport_id=row["sport_id"],
            team_id=row["team_id"],
            name=row["name"],
            position=row["position"] or "",
            jersey=row["jersey"] or "",
            age=row["age"],
            height=row["height"] or "",
            weight=row["weight"] or "",
            status=row["status"] or "active",
            source=row["source"] or "espn",
            updated_at=row["updated_at"] or "",
        )


# ---------------------------------------------------------------------------
# PlayerGamelogRepo
# ---------------------------------------------------------------------------

class PlayerGamelogRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, entry: PlayerGamelog) -> None:
        self.conn.execute(
            "INSERT INTO player_gamelogs (athlete_id, fixture_id, game_date, opponent, result, stats_json, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(athlete_id, game_date) DO UPDATE SET "
            "fixture_id=excluded.fixture_id, opponent=excluded.opponent, "
            "result=excluded.result, stats_json=excluded.stats_json",
            (
                entry.athlete_id, entry.fixture_id, entry.game_date,
                entry.opponent, entry.result, entry.stats_json, entry.source,
            ),
        )

    def get_last_n(self, athlete_id: int, n: int = 10) -> list[PlayerGamelog]:
        rows = self.conn.execute(
            "SELECT * FROM player_gamelogs WHERE athlete_id = ? ORDER BY game_date DESC LIMIT ?",
            (athlete_id, n),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_by_date_range(self, athlete_id: int, start: str, end: str) -> list[PlayerGamelog]:
        rows = self.conn.execute(
            "SELECT * FROM player_gamelogs WHERE athlete_id = ? AND game_date BETWEEN ? AND ? ORDER BY game_date",
            (athlete_id, start, end),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> PlayerGamelog:
        return PlayerGamelog(
            id=row["id"],
            athlete_id=row["athlete_id"],
            fixture_id=row["fixture_id"],
            game_date=row["game_date"],
            opponent=row["opponent"] or "",
            result=row["result"] or "",
            stats_json=row["stats_json"] or "{}",
            source=row["source"] or "espn",
        )


# ---------------------------------------------------------------------------
# PlayerSplitRepo
# ---------------------------------------------------------------------------

class PlayerSplitRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, split: PlayerSplit) -> None:
        self.conn.execute(
            "INSERT INTO player_splits (athlete_id, split_type, stats_json, season, source, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(athlete_id, split_type, season) DO UPDATE SET "
            "stats_json=excluded.stats_json, updated_at=excluded.updated_at",
            (
                split.athlete_id, split.split_type, split.stats_json,
                split.season, split.source, split.updated_at or _now(),
            ),
        )

    def get_for_athlete(self, athlete_id: int) -> list[PlayerSplit]:
        rows = self.conn.execute(
            "SELECT * FROM player_splits WHERE athlete_id = ?", (athlete_id,)
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> PlayerSplit:
        return PlayerSplit(
            id=row["id"],
            athlete_id=row["athlete_id"],
            split_type=row["split_type"],
            stats_json=row["stats_json"] or "{}",
            season=row["season"] or "",
            source=row["source"] or "espn",
            updated_at=row["updated_at"] or "",
        )


# ---------------------------------------------------------------------------
# StandingRepo
# ---------------------------------------------------------------------------

class StandingRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, standing: Standing) -> None:
        self.conn.execute(
            "INSERT INTO standings "
            "(competition_id, team_id, season, rank, wins, draws, losses, "
            "goals_for, goals_against, goal_diff, points, form, "
            "home_wins, home_draws, home_losses, away_wins, away_draws, away_losses, "
            "streak, source, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(competition_id, team_id, season) DO UPDATE SET "
            "rank=excluded.rank, wins=excluded.wins, draws=excluded.draws, losses=excluded.losses, "
            "goals_for=excluded.goals_for, goals_against=excluded.goals_against, "
            "goal_diff=excluded.goal_diff, points=excluded.points, form=excluded.form, "
            "home_wins=excluded.home_wins, home_draws=excluded.home_draws, home_losses=excluded.home_losses, "
            "away_wins=excluded.away_wins, away_draws=excluded.away_draws, away_losses=excluded.away_losses, "
            "streak=excluded.streak, updated_at=excluded.updated_at",
            (
                standing.competition_id, standing.team_id, standing.season, standing.rank,
                standing.wins, standing.draws, standing.losses,
                standing.goals_for, standing.goals_against, standing.goal_diff, standing.points,
                standing.form,
                standing.home_wins, standing.home_draws, standing.home_losses,
                standing.away_wins, standing.away_draws, standing.away_losses,
                standing.streak, standing.source, standing.updated_at or _now(),
            ),
        )

    def get_by_competition(self, competition_id: int, season: str = "") -> list[Standing]:
        if season:
            rows = self.conn.execute(
                "SELECT * FROM standings WHERE competition_id = ? AND season = ? ORDER BY rank",
                (competition_id, season),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM standings WHERE competition_id = ? ORDER BY rank",
                (competition_id,),
            ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_team_standing(self, team_id: int, competition_id: int, season: str = "") -> Standing | None:
        if season:
            row = self.conn.execute(
                "SELECT * FROM standings WHERE team_id = ? AND competition_id = ? AND season = ?",
                (team_id, competition_id, season),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT * FROM standings WHERE team_id = ? AND competition_id = ? ORDER BY updated_at DESC LIMIT 1",
                (team_id, competition_id),
            ).fetchone()
        return self._row_to_model(row) if row else None

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> Standing:
        return Standing(
            id=row["id"],
            competition_id=row["competition_id"],
            team_id=row["team_id"],
            season=row["season"] or "",
            rank=row["rank"],
            wins=row["wins"] or 0,
            draws=row["draws"] or 0,
            losses=row["losses"] or 0,
            goals_for=row["goals_for"] or 0,
            goals_against=row["goals_against"] or 0,
            goal_diff=row["goal_diff"] or 0,
            points=row["points"] or 0,
            form=row["form"] or "",
            home_wins=row["home_wins"] or 0,
            home_draws=row["home_draws"] or 0,
            home_losses=row["home_losses"] or 0,
            away_wins=row["away_wins"] or 0,
            away_draws=row["away_draws"] or 0,
            away_losses=row["away_losses"] or 0,
            streak=row["streak"] or "",
            source=row["source"] or "espn",
            updated_at=row["updated_at"] or "",
        )


# ---------------------------------------------------------------------------
# TeamATSRepo
# ---------------------------------------------------------------------------

class TeamATSRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, record: TeamATSRecord) -> None:
        self.conn.execute(
            "INSERT INTO team_ats_records "
            "(team_id, sport_id, season, season_type, wins, losses, pushes, "
            "home_wins, home_losses, home_pushes, away_wins, away_losses, away_pushes, "
            "source, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(team_id, season, season_type) DO UPDATE SET "
            "wins=excluded.wins, losses=excluded.losses, pushes=excluded.pushes, "
            "home_wins=excluded.home_wins, home_losses=excluded.home_losses, home_pushes=excluded.home_pushes, "
            "away_wins=excluded.away_wins, away_losses=excluded.away_losses, away_pushes=excluded.away_pushes, "
            "updated_at=excluded.updated_at",
            (
                record.team_id, record.sport_id, record.season, record.season_type,
                record.wins, record.losses, record.pushes,
                record.home_wins, record.home_losses, record.home_pushes,
                record.away_wins, record.away_losses, record.away_pushes,
                record.source, record.updated_at or _now(),
            ),
        )

    def get_for_team(self, team_id: int, season: str = "") -> list[TeamATSRecord]:
        if season:
            rows = self.conn.execute(
                "SELECT * FROM team_ats_records WHERE team_id = ? AND season = ?",
                (team_id, season),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM team_ats_records WHERE team_id = ? ORDER BY season DESC",
                (team_id,),
            ).fetchall()
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> TeamATSRecord:
        return TeamATSRecord(
            id=row["id"],
            team_id=row["team_id"],
            sport_id=row["sport_id"],
            season=row["season"],
            season_type=row["season_type"] or 2,
            wins=row["wins"] or 0,
            losses=row["losses"] or 0,
            pushes=row["pushes"] or 0,
            home_wins=row["home_wins"] or 0,
            home_losses=row["home_losses"] or 0,
            home_pushes=row["home_pushes"] or 0,
            away_wins=row["away_wins"] or 0,
            away_losses=row["away_losses"] or 0,
            away_pushes=row["away_pushes"] or 0,
            source=row["source"] or "espn",
            updated_at=row["updated_at"] or "",
        )


# ---------------------------------------------------------------------------
# TeamOURepo
# ---------------------------------------------------------------------------

class TeamOURepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, record: TeamOURecord) -> None:
        self.conn.execute(
            "INSERT INTO team_ou_records "
            "(team_id, sport_id, season, season_type, overs, unders, pushes, "
            "home_overs, home_unders, home_pushes, away_overs, away_unders, away_pushes, "
            "source, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(team_id, season, season_type) DO UPDATE SET "
            "overs=excluded.overs, unders=excluded.unders, pushes=excluded.pushes, "
            "home_overs=excluded.home_overs, home_unders=excluded.home_unders, home_pushes=excluded.home_pushes, "
            "away_overs=excluded.away_overs, away_unders=excluded.away_unders, away_pushes=excluded.away_pushes, "
            "updated_at=excluded.updated_at",
            (
                record.team_id, record.sport_id, record.season, record.season_type,
                record.overs, record.unders, record.pushes,
                record.home_overs, record.home_unders, record.home_pushes,
                record.away_overs, record.away_unders, record.away_pushes,
                record.source, record.updated_at or _now(),
            ),
        )

    def get_for_team(self, team_id: int, season: str = "") -> list[TeamOURecord]:
        if season:
            rows = self.conn.execute(
                "SELECT * FROM team_ou_records WHERE team_id = ? AND season = ?",
                (team_id, season),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM team_ou_records WHERE team_id = ? ORDER BY season DESC",
                (team_id,),
            ).fetchall()
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> TeamOURecord:
        return TeamOURecord(
            id=row["id"],
            team_id=row["team_id"],
            sport_id=row["sport_id"],
            season=row["season"],
            season_type=row["season_type"] or 2,
            overs=row["overs"] or 0,
            unders=row["unders"] or 0,
            pushes=row["pushes"] or 0,
            home_overs=row["home_overs"] or 0,
            home_unders=row["home_unders"] or 0,
            home_pushes=row["home_pushes"] or 0,
            away_overs=row["away_overs"] or 0,
            away_unders=row["away_unders"] or 0,
            away_pushes=row["away_pushes"] or 0,
            source=row["source"] or "espn",
            updated_at=row["updated_at"] or "",
        )


# ---------------------------------------------------------------------------
# ESPNPredictionRepo
# ---------------------------------------------------------------------------

class ESPNPredictionRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, pred: ESPNPrediction) -> None:
        self.conn.execute(
            "INSERT INTO espn_predictions "
            "(fixture_id, home_win_pct, away_win_pct, tie_pct, predictor_json, "
            "power_index_home, power_index_away, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(fixture_id) DO UPDATE SET "
            "home_win_pct=excluded.home_win_pct, away_win_pct=excluded.away_win_pct, "
            "tie_pct=excluded.tie_pct, predictor_json=excluded.predictor_json, "
            "power_index_home=excluded.power_index_home, power_index_away=excluded.power_index_away, "
            "fetched_at=excluded.fetched_at",
            (
                pred.fixture_id, pred.home_win_pct, pred.away_win_pct, pred.tie_pct,
                pred.predictor_json, pred.power_index_home, pred.power_index_away,
                pred.source, pred.fetched_at or _now(),
            ),
        )

    def get_for_fixture(self, fixture_id: int) -> ESPNPrediction | None:
        row = self.conn.execute(
            "SELECT * FROM espn_predictions WHERE fixture_id = ?", (fixture_id,)
        ).fetchone()
        return self._row_to_model(row) if row else None

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> ESPNPrediction:
        return ESPNPrediction(
            id=row["id"],
            fixture_id=row["fixture_id"],
            home_win_pct=row["home_win_pct"],
            away_win_pct=row["away_win_pct"],
            tie_pct=row["tie_pct"],
            predictor_json=row["predictor_json"],
            power_index_home=row["power_index_home"],
            power_index_away=row["power_index_away"],
            source=row["source"] or "espn",
            fetched_at=row["fetched_at"] or "",
        )


# ---------------------------------------------------------------------------
# TeamRosterRepo
# ---------------------------------------------------------------------------

class TeamRosterRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, entry: TeamRoster) -> None:
        self.conn.execute(
            "INSERT INTO team_rosters "
            "(team_id, athlete_id, position, jersey, status, depth_rank, season, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(team_id, athlete_id, season) DO UPDATE SET "
            "position=excluded.position, jersey=excluded.jersey, status=excluded.status, "
            "depth_rank=excluded.depth_rank, updated_at=excluded.updated_at",
            (
                entry.team_id, entry.athlete_id, entry.position, entry.jersey,
                entry.status, entry.depth_rank, entry.season, entry.updated_at or _now(),
            ),
        )

    def get_team_roster(self, team_id: int, season: str = "") -> list[TeamRoster]:
        if season:
            rows = self.conn.execute(
                "SELECT * FROM team_rosters WHERE team_id = ? AND season = ? ORDER BY depth_rank",
                (team_id, season),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM team_rosters WHERE team_id = ? ORDER BY depth_rank",
                (team_id,),
            ).fetchall()
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> TeamRoster:
        return TeamRoster(
            id=row["id"],
            team_id=row["team_id"],
            athlete_id=row["athlete_id"],
            position=row["position"] or "",
            jersey=row["jersey"] or "",
            status=row["status"] or "active",
            depth_rank=row["depth_rank"],
            season=row["season"] or "",
            updated_at=row["updated_at"] or "",
        )


# ---------------------------------------------------------------------------
# TransactionRepo
# ---------------------------------------------------------------------------

class TransactionRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert(self, txn: Transaction) -> None:
        self.conn.execute(
            "INSERT INTO transactions "
            "(team_id, athlete_id, transaction_type, description, transaction_date, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                txn.team_id, txn.athlete_id, txn.transaction_type,
                txn.description, txn.transaction_date, txn.source, txn.fetched_at or _now(),
            ),
        )

    def get_for_team(self, team_id: int, limit: int = 50) -> list[Transaction]:
        rows = self.conn.execute(
            "SELECT * FROM transactions WHERE team_id = ? ORDER BY transaction_date DESC LIMIT ?",
            (team_id, limit),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_recent(self, days: int = 7) -> list[Transaction]:
        rows = self.conn.execute(
            "SELECT * FROM transactions WHERE transaction_date >= date('now', ? || ' days') ORDER BY transaction_date DESC",
            (f"-{days}",),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> Transaction:
        return Transaction(
            id=row["id"],
            team_id=row["team_id"],
            athlete_id=row["athlete_id"],
            transaction_type=row["transaction_type"],
            description=row["description"] or "",
            transaction_date=row["transaction_date"] or "",
            source=row["source"] or "espn",
            fetched_at=row["fetched_at"] or "",
        )


# ---------------------------------------------------------------------------
# PowerIndexRepo
# ---------------------------------------------------------------------------

class PowerIndexRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, entry: PowerIndex) -> None:
        self.conn.execute(
            "INSERT INTO power_index "
            "(team_id, sport_id, season, rating, offensive_rating, defensive_rating, rank, source, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(team_id, season) DO UPDATE SET "
            "rating=excluded.rating, offensive_rating=excluded.offensive_rating, "
            "defensive_rating=excluded.defensive_rating, rank=excluded.rank, "
            "updated_at=excluded.updated_at",
            (
                entry.team_id, entry.sport_id, entry.season, entry.rating,
                entry.offensive_rating, entry.defensive_rating, entry.rank,
                entry.source, entry.updated_at or _now(),
            ),
        )

    def get_for_team(self, team_id: int) -> list[PowerIndex]:
        rows = self.conn.execute(
            "SELECT * FROM power_index WHERE team_id = ? ORDER BY season DESC",
            (team_id,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_sport_rankings(self, sport_id: int, season: str) -> list[PowerIndex]:
        rows = self.conn.execute(
            "SELECT * FROM power_index WHERE sport_id = ? AND season = ? ORDER BY rank",
            (sport_id, season),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> PowerIndex:
        return PowerIndex(
            id=row["id"],
            team_id=row["team_id"],
            sport_id=row["sport_id"],
            season=row["season"],
            rating=row["rating"],
            offensive_rating=row["offensive_rating"],
            defensive_rating=row["defensive_rating"],
            rank=row["rank"],
            source=row["source"] or "espn",
            updated_at=row["updated_at"] or "",
        )


# ---------------------------------------------------------------------------
# TeamNewsRepo
# ---------------------------------------------------------------------------
class TeamNewsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, news: TeamNews) -> int:
        cur = self.conn.execute(
            """INSERT INTO team_news
               (team_id, sport_id, betting_date, injuries_json, news_json,
                coaching_json, morale_json, sources_json, confidence, fetched_at, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(team_id, betting_date) DO UPDATE SET
                 injuries_json = excluded.injuries_json,
                 news_json = excluded.news_json,
                 coaching_json = excluded.coaching_json,
                 morale_json = excluded.morale_json,
                 sources_json = excluded.sources_json,
                 confidence = excluded.confidence,
                 fetched_at = excluded.fetched_at,
                 source = excluded.source""",
            (
                news.team_id,
                news.sport_id,
                news.betting_date,
                json.dumps(news.injuries_json),
                json.dumps(news.news_json),
                json.dumps(news.coaching_json),
                json.dumps(news.morale_json),
                json.dumps(news.sources_json),
                news.confidence,
                news.fetched_at or _now(),
                news.source,
            ),
        )
        self.conn.commit()
        return cur.lastrowid or 0

    def get_for_team_date(self, team_id: int, betting_date: str) -> TeamNews | None:
        row = self.conn.execute(
            "SELECT * FROM team_news WHERE team_id = ? AND betting_date = ?",
            (team_id, betting_date),
        ).fetchone()
        return self._row_to_model(row) if row else None

    def get_for_date(self, betting_date: str) -> list[TeamNews]:
        rows = self.conn.execute(
            "SELECT * FROM team_news WHERE betting_date = ? ORDER BY fetched_at DESC",
            (betting_date,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> TeamNews:
        return TeamNews(
            id=row["id"],
            team_id=row["team_id"],
            sport_id=row["sport_id"],
            betting_date=row["betting_date"],
            injuries_json=json.loads(row["injuries_json"]) if row["injuries_json"] else [],
            news_json=json.loads(row["news_json"]) if row["news_json"] else [],
            coaching_json=json.loads(row["coaching_json"]) if row["coaching_json"] else [],
            morale_json=json.loads(row["morale_json"]) if row["morale_json"] else [],
            sources_json=json.loads(row["sources_json"]) if row["sources_json"] else [],
            confidence=row["confidence"],
            fetched_at=row["fetched_at"] or "",
            source=row["source"] or "unknown",
        )


# ---------------------------------------------------------------------------
# TipsterRepo
# ---------------------------------------------------------------------------

class TipsterRepo:
    """Repository for tipster picks and consensus data."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save_picks(self, date: str, picks: list[dict]) -> int:
        """Bulk insert tipster picks for a date. Clears existing picks first.

        Atomic: DELETE + INSERT wrapped in implicit transaction via with self.conn.
        """
        rows = [
            (
                date,
                p.get("source_site", ""),
                p.get("tipster_name", ""),
                p.get("sport", ""),
                p.get("event", ""),
                p.get("home_team", ""),
                p.get("away_team", ""),
                p.get("competition", ""),
                p.get("market", ""),
                p.get("market_type", ""),
                p.get("direction", ""),
                p.get("odds"),
                p.get("reasoning", ""),
                p.get("accuracy_pct"),
                p.get("confidence", ""),
                json.dumps(p.get("stats_cited") if isinstance(p.get("stats_cited"), list) else []),
                p.get("fetch_time", ""),
            )
            for p in picks
        ]
        with self.conn:
            self.conn.execute("DELETE FROM tipster_picks WHERE betting_date = ?", (date,))
            self.conn.executemany("""
                INSERT INTO tipster_picks (betting_date, source_site, tipster_name, sport, event,
                    home_team, away_team, competition, market, market_type, direction, odds,
                    reasoning, accuracy_pct, confidence, stats_cited, fetch_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
        return len(rows)

    def save_consensus(self, date: str, entries: list[dict]) -> int:
        """Bulk insert consensus entries for a date. Clears existing entries first.

        Atomic: DELETE + INSERT wrapped in implicit transaction via with self.conn.
        """
        rows = [
            (
                date,
                ce.get("event", ""),
                ce.get("sport", ""),
                ce.get("competition", ""),
                ce.get("home_team", ""),
                ce.get("away_team", ""),
                ce.get("total_tipsters", 0),
                ce.get("consensus_market", ""),
                ce.get("consensus_direction", ""),
                ce.get("agreement_pct", 0),
                ce.get("statistical_picks", 0),
                ce.get("outcome_picks", 0),
                1 if ce.get("has_reasoning") else 0,
                json.dumps(ce.get("tipster_sources", [])),
                ce.get("confidence_adj", 0.0),
            )
            for ce in entries
        ]
        with self.conn:
            self.conn.execute("DELETE FROM tipster_consensus WHERE betting_date = ?", (date,))
            self.conn.executemany("""
                INSERT INTO tipster_consensus (betting_date, event, sport, competition,
                    home_team, away_team, total_tipsters, consensus_market, consensus_direction,
                    agreement_pct, statistical_picks, outcome_picks, has_reasoning,
                    tipster_sources, confidence_adj)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
        return len(rows)

    def get_picks_by_date(self, date: str) -> list:
        """Get all tipster picks for a betting date."""
        rows = self.conn.execute(
            "SELECT id, betting_date, source_site, tipster_name, sport, event, "
            "home_team, away_team, competition, market, market_type, direction, "
            "odds, reasoning, accuracy_pct, confidence, stats_cited, fetch_time, created_at "
            "FROM tipster_picks WHERE betting_date = ? ORDER BY source_site, sport",
            (date,),
        ).fetchall()
        results = []
        for r in rows:
            stats_cited = r["stats_cited"]
            if isinstance(stats_cited, str):
                try:
                    stats_cited = json.loads(stats_cited)
                except (json.JSONDecodeError, TypeError):
                    stats_cited = []
            results.append(TipsterPick(
                id=r["id"], betting_date=r["betting_date"], source_site=r["source_site"],
                tipster_name=r["tipster_name"], sport=r["sport"], event=r["event"],
                home_team=r["home_team"], away_team=r["away_team"],
                competition=r["competition"], market=r["market"], market_type=r["market_type"],
                direction=r["direction"], odds=r["odds"], reasoning=r["reasoning"],
                accuracy_pct=r["accuracy_pct"], confidence=r["confidence"],
                stats_cited=stats_cited if isinstance(stats_cited, list) else [],
                fetch_time=r["fetch_time"], created_at=r["created_at"] or "",
            ))
        return results

    def get_consensus_by_date(self, date: str) -> list:
        """Get all consensus entries for a betting date."""
        rows = self.conn.execute(
            "SELECT id, betting_date, event, sport, competition, home_team, away_team, "
            "total_tipsters, consensus_market, consensus_direction, agreement_pct, "
            "statistical_picks, outcome_picks, has_reasoning, tipster_sources, "
            "confidence_adj, created_at "
            "FROM tipster_consensus WHERE betting_date = ? ORDER BY agreement_pct DESC",
            (date,),
        ).fetchall()
        results = []
        for r in rows:
            sources = r["tipster_sources"]
            if isinstance(sources, str):
                try:
                    sources = json.loads(sources)
                except (json.JSONDecodeError, TypeError):
                    sources = []
            results.append(TipsterConsensus(
                id=r["id"], betting_date=r["betting_date"], event=r["event"],
                sport=r["sport"], competition=r["competition"],
                home_team=r["home_team"], away_team=r["away_team"],
                total_tipsters=r["total_tipsters"], consensus_market=r["consensus_market"],
                consensus_direction=r["consensus_direction"],
                agreement_pct=r["agreement_pct"], statistical_picks=r["statistical_picks"],
                outcome_picks=r["outcome_picks"], has_reasoning=bool(r["has_reasoning"]),
                tipster_sources=sources if isinstance(sources, list) else [],
                confidence_adj=r["confidence_adj"], created_at=r["created_at"] or "",
            ))
        return results

    def get_picks_for_event(self, date: str, home_team: str, away_team: str) -> list:
        """Get tipster picks for a specific event (case-insensitive team match)."""
        rows = self.conn.execute(
            "SELECT id, betting_date, source_site, tipster_name, sport, event, "
            "home_team, away_team, competition, market, market_type, direction, "
            "odds, reasoning, accuracy_pct, confidence, stats_cited, fetch_time, created_at "
            "FROM tipster_picks WHERE betting_date = ? "
            "AND LOWER(home_team) = LOWER(?) AND LOWER(away_team) = LOWER(?)",
            (date, home_team, away_team),
        ).fetchall()
        results = []
        for r in rows:
            stats_cited = r["stats_cited"]
            if isinstance(stats_cited, str):
                try:
                    stats_cited = json.loads(stats_cited)
                except (json.JSONDecodeError, TypeError):
                    stats_cited = []
            results.append(TipsterPick(
                id=r["id"], betting_date=r["betting_date"], source_site=r["source_site"],
                tipster_name=r["tipster_name"], sport=r["sport"], event=r["event"],
                home_team=r["home_team"], away_team=r["away_team"],
                competition=r["competition"], market=r["market"], market_type=r["market_type"],
                direction=r["direction"], odds=r["odds"], reasoning=r["reasoning"],
                accuracy_pct=r["accuracy_pct"], confidence=r["confidence"],
                stats_cited=stats_cited if isinstance(stats_cited, list) else [],
                fetch_time=r["fetch_time"], created_at=r["created_at"] or "",
            ))
        return results


# ---------------------------------------------------------------------------
# KnownMissingRepo — replaces JSON-based known_missing_teams cache
# ---------------------------------------------------------------------------

class KnownMissingRepo:
    """Repository for teams/players that consistently 404 across all enrichment sources."""

    def __init__(self, conn):
        self.conn = conn

    def _ensure_table(self) -> None:
        """Create table if not exists (idempotent)."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS known_missing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_name TEXT NOT NULL,
                sport TEXT NOT NULL,
                marked_at TEXT NOT NULL,
                reason TEXT DEFAULT '',
                source TEXT DEFAULT '',
                UNIQUE(team_name, sport)
            )
        """)

    def is_missing(self, team_name: str, sport: str, max_age_days: int = 7) -> bool:
        """Check if a team is known to 404 (entries expire after max_age_days)."""
        self._ensure_table()
        row = self.conn.execute(
            "SELECT marked_at FROM known_missing WHERE team_name = ? AND sport = ?",
            (team_name.lower().strip(), sport),
        ).fetchone()
        if not row:
            return False
        from datetime import datetime, timezone, timedelta
        try:
            marked = datetime.fromisoformat(row["marked_at"])
            if (datetime.now(timezone.utc) - marked).days > max_age_days:
                self.conn.execute(
                    "DELETE FROM known_missing WHERE team_name = ? AND sport = ?",
                    (team_name.lower().strip(), sport),
                )
                return False
            return True
        except (ValueError, TypeError):
            return False

    def mark_missing(self, team_name: str, sport: str, reason: str = "", source: str = "") -> None:
        """Mark a team as known-missing."""
        self._ensure_table()
        from datetime import datetime, timezone
        self.conn.execute(
            """INSERT OR REPLACE INTO known_missing (team_name, sport, marked_at, reason, source)
               VALUES (?, ?, ?, ?, ?)""",
            (team_name.lower().strip(), sport, datetime.now(timezone.utc).isoformat(), reason, source),
        )

    def clear_sport(self, sport: str) -> int:
        """Clear all entries for a sport. Returns count deleted."""
        self._ensure_table()
        cursor = self.conn.execute(
            "DELETE FROM known_missing WHERE sport = ?", (sport,)
        )
        return cursor.rowcount

    def clear_expired(self, days: int = 7) -> int:
        """Clear entries older than N days. Returns count deleted."""
        self._ensure_table()
        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cursor = self.conn.execute(
            "DELETE FROM known_missing WHERE marked_at < ?", (cutoff,)
        )
        return cursor.rowcount

    def count_by_sport(self) -> dict:
        """Count entries per sport."""
        self._ensure_table()
        rows = self.conn.execute(
            "SELECT sport, COUNT(*) as cnt FROM known_missing GROUP BY sport"
        ).fetchall()
        return {r["sport"]: r["cnt"] for r in rows}


class PipelineCandidateRepo:
    """Repository for pipeline_candidates table (replaces s2_shortlist JSON)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save_candidates(self, date: str, candidates: list[dict]) -> int:
        """Bulk insert candidates for a date, replacing any existing."""
        self.delete_by_date(date)
        now = _now()
        saved = 0
        for c in candidates:
            self.conn.execute(
                "INSERT INTO pipeline_candidates "
                "(fixture_id, betting_date, rank, score, sport, competition, "
                "home_team, away_team, kickoff, data_tier, comp_score, "
                "n_odds_markets, n_safety_markets, odds_markets_json, safety_markets_json, "
                "fixture_verified, verification_sources_json, "
                "tipster_count, tipster_support_json, source, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    c["fixture_id"],
                    date,
                    c.get("rank", saved + 1),
                    c.get("score", 0.0),
                    c.get("sport", ""),
                    c.get("competition", ""),
                    c.get("home_team", ""),
                    c.get("away_team", ""),
                    c.get("kickoff", ""),
                    c.get("data_tier", "FIXTURE_ONLY"),
                    c.get("comp_score", 3),
                    c.get("n_odds_markets", 0),
                    c.get("n_safety_markets", 0),
                    json.dumps(c.get("odds_markets", [])),
                    json.dumps(c.get("safety_markets", [])),
                    1 if c.get("fixture_verified") else 0,
                    json.dumps(c.get("verification_sources", [])),
                    c.get("tipster_count", 0),
                    json.dumps(c.get("tipster_support")) if c.get("tipster_support") else None,
                    c.get("source", "build_shortlist"),
                    now,
                ),
            )
            saved += 1
        self.conn.commit()
        return saved

    def get_by_date(self, date: str) -> list[dict]:
        """Get all candidates for a date, sorted by rank."""
        rows = self.conn.execute(
            "SELECT * FROM pipeline_candidates WHERE betting_date = ? ORDER BY rank",
            (date,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_by_date_and_sport(self, date: str, sport: str) -> list[dict]:
        """Get candidates for a date filtered by sport."""
        rows = self.conn.execute(
            "SELECT * FROM pipeline_candidates WHERE betting_date = ? AND sport = ? ORDER BY rank",
            (date, sport),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def enrich_tipster(self, fixture_id: int, date: str, tipster_count: int, tipster_support_json: dict | None) -> None:
        """Update tipster enrichment fields for a candidate."""
        self.conn.execute(
            "UPDATE pipeline_candidates SET tipster_count = ?, tipster_support_json = ? "
            "WHERE fixture_id = ? AND betting_date = ?",
            (
                tipster_count,
                json.dumps(tipster_support_json) if tipster_support_json else None,
                fixture_id,
                date,
            ),
        )
        self.conn.commit()

    def clear_tipster_enrichment(self, date: str) -> None:
        """Reset tipster enrichment for a betting date before re-running S2.

        S2 reruns must not leave stale `tipster_count` / `tipster_support_json`
        from earlier runs on candidates that no longer match.
        """
        self.conn.execute(
            "UPDATE pipeline_candidates SET tipster_count = 0, tipster_support_json = NULL "
            "WHERE betting_date = ?",
            (date,),
        )
        self.conn.commit()

    def get_count(self, date: str) -> int:
        """Count candidates for a date."""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM pipeline_candidates WHERE betting_date = ?",
            (date,),
        ).fetchone()
        return row["cnt"] if row else 0

    def delete_by_date(self, date: str) -> int:
        """Delete all candidates for a date. Returns count deleted."""
        cursor = self.conn.execute(
            "DELETE FROM pipeline_candidates WHERE betting_date = ?", (date,)
        )
        self.conn.commit()
        return cursor.rowcount

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        """Convert a DB row to a dict matching shortlist JSON format."""
        return {
            "fixture_id": row["fixture_id"],
            "rank": row["rank"],
            "score": row["score"],
            "sport": row["sport"],
            "competition": row["competition"],
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "kickoff": row["kickoff"],
            "data_tier": row["data_tier"],
            "comp_score": row["comp_score"],
            "n_odds_markets": row["n_odds_markets"],
            "n_safety_markets": row["n_safety_markets"],
            "odds_markets": json.loads(row["odds_markets_json"]),
            "safety_markets": json.loads(row["safety_markets_json"]),
            "fixture_verified": bool(row["fixture_verified"]),
            "verification_sources": json.loads(row["verification_sources_json"]),
            "tipster_count": row["tipster_count"] or 0,
            "tipster_support": json.loads(row["tipster_support_json"]) if row["tipster_support_json"] else None,
            "source": row["source"],
        }


class MarketMatrixRepo:
    """Repository for market_matrix_events + market_matrix_runs tables."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save_run(self, date: str, metadata: dict) -> int:
        """Insert or replace run metadata for a date."""
        now = _now()
        self.conn.execute(
            "INSERT OR REPLACE INTO market_matrix_runs "
            "(betting_date, generated_at, total_fixtures, total_events_in_matrix, "
            "events_with_odds, events_with_safety_data, "
            "sport_breakdown_json, market_type_counts_json, data_tier_breakdown_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                date,
                now,
                metadata.get("total_fixtures", 0),
                metadata.get("total_events_in_matrix", 0),
                metadata.get("events_with_odds", 0),
                metadata.get("events_with_safety_data", 0),
                json.dumps(metadata.get("sport_breakdown", {})),
                json.dumps(metadata.get("market_type_counts", {})),
                json.dumps(metadata.get("data_tier_breakdown", {})),
            ),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM market_matrix_runs WHERE betting_date = ?", (date,)
        ).fetchone()
        return row["id"] if row else 0

    def save_events(self, date: str, events: list[dict]) -> int:
        """Bulk insert matrix events for a date, replacing any existing."""
        self.delete_by_date(date)
        now = _now()
        saved = 0
        for e in events:
            self.conn.execute(
                "INSERT INTO market_matrix_events "
                "(fixture_id, betting_date, sport, competition, home_team, away_team, "
                "kickoff, data_tier, fixture_source, odds_markets_json, safety_markets_json, "
                "suggested_json, total_markets_available, "
                "scores24_h2h_json, scores24_form_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    e["fixture_id"],
                    date,
                    e.get("sport", ""),
                    e.get("competition", ""),
                    e.get("home_team", ""),
                    e.get("away_team", ""),
                    e.get("kickoff", ""),
                    e.get("data_tier", "FIXTURE_ONLY"),
                    e.get("fixture_source", ""),
                    json.dumps(e.get("odds_markets", [])),
                    json.dumps(e.get("safety_markets", [])),
                    json.dumps(e.get("suggested")) if e.get("suggested") else None,
                    e.get("total_markets_available", 0),
                    json.dumps(e.get("scores24_h2h")) if e.get("scores24_h2h") else None,
                    json.dumps(e.get("scores24_form")) if e.get("scores24_form") else None,
                    now,
                ),
            )
            saved += 1
        self.conn.commit()
        return saved

    def get_events_by_date(self, date: str) -> list[dict]:
        """Get all matrix events for a date."""
        rows = self.conn.execute(
            "SELECT * FROM market_matrix_events WHERE betting_date = ? ORDER BY sport, competition, home_team",
            (date,),
        ).fetchall()
        return [self._event_to_dict(r) for r in rows]

    def get_events_by_tier(self, date: str, tier: str) -> list[dict]:
        """Get matrix events filtered by data_tier."""
        rows = self.conn.execute(
            "SELECT * FROM market_matrix_events WHERE betting_date = ? AND data_tier = ? ORDER BY sport, competition",
            (date, tier),
        ).fetchall()
        return [self._event_to_dict(r) for r in rows]

    def get_run_metadata(self, date: str) -> dict | None:
        """Get run metadata for a date."""
        row = self.conn.execute(
            "SELECT * FROM market_matrix_runs WHERE betting_date = ?", (date,)
        ).fetchone()
        if not row:
            return None
        return {
            "betting_date": row["betting_date"],
            "generated_at": row["generated_at"],
            "total_fixtures": row["total_fixtures"],
            "total_events_in_matrix": row["total_events_in_matrix"],
            "events_with_odds": row["events_with_odds"],
            "events_with_safety_data": row["events_with_safety_data"],
            "sport_breakdown": json.loads(row["sport_breakdown_json"]),
            "market_type_counts": json.loads(row["market_type_counts_json"]),
            "data_tier_breakdown": json.loads(row["data_tier_breakdown_json"]),
        }

    def get_count(self, date: str) -> int:
        """Count events for a date."""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM market_matrix_events WHERE betting_date = ?",
            (date,),
        ).fetchone()
        return row["cnt"] if row else 0

    def delete_by_date(self, date: str) -> int:
        """Delete all events for a date. Returns count deleted."""
        cursor = self.conn.execute(
            "DELETE FROM market_matrix_events WHERE betting_date = ?", (date,)
        )
        self.conn.execute(
            "DELETE FROM market_matrix_runs WHERE betting_date = ?", (date,)
        )
        self.conn.commit()
        return cursor.rowcount

    def _event_to_dict(self, row: sqlite3.Row) -> dict:
        """Convert a DB row to a dict matching matrix JSON format."""
        return {
            "fixture_id": row["fixture_id"],
            "sport": row["sport"],
            "competition": row["competition"],
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "kickoff": row["kickoff"],
            "data_tier": row["data_tier"],
            "fixture_source": row["fixture_source"],
            "odds_markets": json.loads(row["odds_markets_json"]),
            "safety_markets": json.loads(row["safety_markets_json"]),
            "suggested": json.loads(row["suggested_json"]) if row["suggested_json"] else None,
            "total_markets_available": row["total_markets_available"],
            "scores24_h2h": json.loads(row["scores24_h2h_json"]) if row["scores24_h2h_json"] else None,
            "scores24_form": json.loads(row["scores24_form_json"]) if row["scores24_form_json"] else None,
        }
