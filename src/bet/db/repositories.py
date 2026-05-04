"""Repository classes for all database CRUD operations.

All SQL uses parameterized queries with ? placeholders — NEVER string interpolation.
JSON columns are serialized with json.dumps() on write and json.loads() on read.
"""

import json
import sqlite3
from datetime import datetime, timezone

from bet.db.models import (
    Bet,
    Competition,
    Coupon,
    Fixture,
    LeagueProfile,
    MatchStat,
    OddsRecord,
    PipelineRun,
    SourceHealth,
    Sport,
    Team,
    TeamForm,
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
        """Upsert team_form row (denormalized cache)."""
        self.conn.execute(
            "INSERT INTO team_form "
            "(team_id, sport_id, stat_key, l10_values, l5_values, l10_avg, l5_avg, "
            "h2h_values, h2h_opponent_id, trend, updated_at, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(team_id, stat_key, h2h_opponent_id) DO UPDATE SET "
            "l10_values = excluded.l10_values, "
            "l5_values = excluded.l5_values, "
            "l10_avg = excluded.l10_avg, "
            "l5_avg = excluded.l5_avg, "
            "h2h_values = excluded.h2h_values, "
            "trend = excluded.trend, "
            "updated_at = excluded.updated_at, "
            "source = excluded.source",
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
            "market_pl, navigation_hint) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
        )


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
            (_NOW(), response_ms, response_ms),
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
