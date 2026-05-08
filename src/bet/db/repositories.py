"""Repository classes for all database CRUD operations.

All SQL uses parameterized queries with ? placeholders — NEVER string interpolation.
JSON columns are serialized with json.dumps() on write and json.loads() on read.
"""

import json
import sqlite3
from datetime import datetime, timezone

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
    TeamOURecord,
    TeamRoster,
    Transaction,
)

_NOW = lambda: datetime.now(timezone.utc).isoformat()


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
            "volleyball": ["points", "aces", "blocks", "attack_pct", "sets_won", "total_points", "errors"],
            "handball": ["goals", "saves", "turnovers", "penalties", "suspensions", "total_goals"],
            "snooker": ["frames_won", "centuries", "highest_break", "total_frames", "fifty_plus_breaks"],
            "darts": ["legs_won", "checkout_pct", "one_eighties", "avg_score", "total_legs"],
            "table_tennis": ["sets_won", "points_per_set", "total_sets", "total_points"],
            "esports": ["maps_won", "rounds_won", "kills", "total_maps", "total_rounds"],
            "baseball": ["runs", "hits", "errors", "strikeouts", "walks", "total_runs", "home_runs"],
            "mma": ["takedowns", "sig_strikes", "submission_attempts", "rounds", "control_time"],
            "padel": ["games_won", "break_points", "sets_won", "total_games"],
            "speedway": ["heat_points", "total_points", "heat_wins"],
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
            ("hockey", 2),
            ("handball", 2),
            ("baseball", 2),
            ("esports", 2),
            ("snooker", 2),
            ("darts", 2),
            ("table_tennis", 2),
            ("mma", 2),
            ("padel", 2),
            ("speedway", 2),
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
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def find_or_create(
        self, name: str, sport_id: int, aliases: list[str] | None = None
    ) -> Team:
        """Find team by name or any alias. Create if not found."""
        existing = self.resolve(name, sport_id)
        if existing:
            return existing
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

        Searches the canonical name first, then aliases using json_each().
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
                fixture.fetched_at or _NOW(),
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
        """Batch upsert multiple fixtures in one transaction. Returns row IDs."""
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

    def save_match_stats(
        self,
        fixture_id: int,
        team_id: int,
        stats: dict[str, float],
        source: str,
    ) -> None:
        """Batch insert match stats (one row per stat_key)."""
        now = _NOW()
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

        Uses DELETE+INSERT because SQLite ON CONFLICT doesn't work with
        expression-based unique indexes (NULL h2h_opponent_id).
        """
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
            "h2h_values, h2h_opponent_id, trend, updated_at, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                form.updated_at or _NOW(),
                form.source,
            ),
        )

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
        now = _NOW()
        self.conn.executemany(
            "INSERT OR REPLACE INTO match_stats "
            "(fixture_id, team_id, stat_key, stat_value, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(fid, tid, sk, sv, src, now) for fid, tid, sk, sv, src in rows],
        )

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


# ---------------------------------------------------------------------------
# OddsRepo
# ---------------------------------------------------------------------------

class OddsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save_odds(self, record: OddsRecord) -> None:
        self.conn.execute(
            "INSERT INTO odds_history "
            "(fixture_id, bookmaker, market, selection, odds, line, fetched_at, is_closing) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.fixture_id,
                record.bookmaker,
                record.market,
                record.selection,
                record.odds,
                record.line,
                record.fetched_at or _NOW(),
                1 if record.is_closing else 0,
            ),
        )

    def upsert(self, record: OddsRecord) -> None:
        """Insert or ignore odds record (prevents duplicate inserts)."""
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
                record.fetched_at or _NOW(),
                1 if record.is_closing else 0,
            ),
        )

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
        """Batch odds lookup for a set of fixture IDs."""
        if not fixture_ids:
            return {}
        placeholders = ",".join("?" for _ in fixture_ids)
        rows = self.conn.execute(
            f"SELECT * FROM odds_history WHERE fixture_id IN ({placeholders}) "
            "ORDER BY fixture_id, fetched_at",
            fixture_ids,
        ).fetchall()
        result: dict[int, list[OddsRecord]] = {}
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
                coupon.created_at or _NOW(),
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
            (status, pnl, _NOW(), coupon_id),
        )

    def settle_bet(self, bet_id: int, status: str, pnl: float) -> None:
        self.conn.execute(
            "UPDATE bets SET status = ?, pnl_pln = ?, settled_at = ? WHERE id = ?",
            (status, pnl, _NOW(), bet_id),
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
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def start_step(self, date: str, step: str) -> None:
        self.conn.execute(
            "INSERT INTO pipeline_runs (date, step, status, started_at) "
            "VALUES (?, ?, 'running', ?) "
            "ON CONFLICT(date, step) DO UPDATE SET "
            "status = 'running', started_at = excluded.started_at, "
            "error_message = NULL",
            (date, step, _NOW()),
        )

    def complete_step(self, date: str, step: str, stats: dict | None = None) -> None:
        self.conn.execute(
            "UPDATE pipeline_runs SET status = 'completed', completed_at = ?, stats = ? "
            "WHERE date = ? AND step = ?",
            (_NOW(), json.dumps(stats) if stats else None, date, step),
        )

    def fail_step(self, date: str, step: str, error: str) -> None:
        self.conn.execute(
            "UPDATE pipeline_runs SET status = 'failed', completed_at = ?, error_message = ? "
            "WHERE date = ? AND step = ?",
            (_NOW(), error, date, step),
        )

    def get_completed_steps(self, date: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT step FROM pipeline_runs WHERE date = ? AND status = 'completed'",
            (date,),
        ).fetchall()
        return [r["step"] for r in rows]

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
                "stats": json.loads(r["stats"]) if r["stats"] else None,
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
            (source, _NOW(), response_ms, response_ms),
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
            (source, _NOW()),
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
             profile.sample_size, profile.updated_at or _NOW()),
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
                result.created_at or _NOW(),
            ),
        )

    def bulk_save(self, results: list[AnalysisResult]) -> None:
        """Bulk insert/replace analysis results."""
        for r in results:
            self.save(r)

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
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

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
                result.created_at or _NOW(),
            ),
        )

    def bulk_save(self, results: list[GateResult]) -> None:
        """Bulk insert/replace gate results."""
        for r in results:
            self.save(r)

    def get_by_date(self, betting_date: str) -> list[GateResult]:
        """Get all gate results for a betting date."""
        rows = self.conn.execute(
            "SELECT * FROM gate_results WHERE betting_date = ? ORDER BY best_safety_score DESC",
            (betting_date,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_approved(self, betting_date: str) -> list[GateResult]:
        """Get approved gate results for coupon building."""
        rows = self.conn.execute(
            "SELECT * FROM gate_results WHERE betting_date = ? AND UPPER(status) = 'APPROVED' "
            "ORDER BY best_safety_score DESC",
            (betting_date,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_extended(self, betting_date: str) -> list[GateResult]:
        """Get extended pool gate results."""
        rows = self.conn.execute(
            "SELECT * FROM gate_results WHERE betting_date = ? AND UPPER(status) = 'EXTENDED' "
            "ORDER BY best_safety_score DESC",
            (betting_date,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def delete_by_date(self, betting_date: str) -> int:
        """Delete all gate results for a date. Returns count deleted."""
        cursor = self.conn.execute(
            "DELETE FROM gate_results WHERE betting_date = ?", (betting_date,)
        )
        return cursor.rowcount

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> GateResult:
        return GateResult(
            id=row["id"],
            fixture_id=row["fixture_id"],
            betting_date=row["betting_date"],
            status=row["status"],
            gate_score=row["gate_score"],
            gate_details_json=json.loads(row["gate_details_json"]) if row["gate_details_json"] else {},
            best_market_name=row["best_market_name"] or "",
            best_market_line=row["best_market_line"],
            best_market_direction=row["best_market_direction"] or "",
            best_safety_score=row["best_safety_score"],
            ev=row["ev"],
            risk_tier=row["risk_tier"] or "",
            rejection_reasons_json=json.loads(row["rejection_reasons_json"]) if row["rejection_reasons_json"] else [],
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
                raw.created_at or _NOW(),
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
                snapshot.created_at or _NOW(),
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
                outcome.created_at or _NOW(),
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
        conditions: list[str] = []
        params: list = []
        if sport:
            conditions.append("sport = ?")
            params.append(sport)
        if market:
            conditions.append("market = ?")
            params.append(market)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        where_with_values = where + (" AND " if conditions else "WHERE ") + "actual_value IS NOT NULL AND predicted_value IS NOT NULL"

        row = self.conn.execute(
            f"SELECT COUNT(*) as count, "
            f"AVG(deviation) as avg_deviation, "
            f"AVG(deviation_pct) as avg_deviation_pct, "
            f"SUM(CASE WHEN deviation > 0 THEN 1 ELSE 0 END) as overestimate_count, "
            f"SUM(CASE WHEN deviation < 0 THEN 1 ELSE 0 END) as underestimate_count, "
            f"SUM(CASE WHEN result = 'won' THEN 1 ELSE 0 END) as won_count, "
            f"SUM(CASE WHEN result = 'lost' THEN 1 ELSE 0 END) as lost_count "
            f"FROM decision_outcomes {where_with_values}",
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
                    r.scan_timestamp or _NOW(),
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
                result.scan_timestamp or _NOW(),
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
                stats.scan_timestamp or _NOW(),
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
                athlete.weight, athlete.status, athlete.source, athlete.updated_at or _NOW(),
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
                split.season, split.source, split.updated_at or _NOW(),
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
                standing.streak, standing.source, standing.updated_at or _NOW(),
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
                record.source, record.updated_at or _NOW(),
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
                record.source, record.updated_at or _NOW(),
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
                pred.source, pred.fetched_at or _NOW(),
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
                entry.status, entry.depth_rank, entry.season, entry.updated_at or _NOW(),
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
                txn.description, txn.transaction_date, txn.source, txn.fetched_at or _NOW(),
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
                entry.source, entry.updated_at or _NOW(),
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
