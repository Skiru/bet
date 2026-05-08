"""Shared pytest fixtures for the new bet package tests.

All fixtures are function-scoped (fresh per test). DB is in-memory SQLite.
"""

import sqlite3

import pytest

from bet.config import BettingConfig
from bet.db.models import Fixture, MarketCandidate, Team
from bet.db.repositories import (
    CouponRepo,
    FixtureRepo,
    SportRepo,
    StatsRepo,
    TeamRepo,
)
from bet.db.schema import init_db


@pytest.fixture
def db():
    """In-memory SQLite database with schema initialized."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def db_with_sports(db):
    """DB with 7 sports seeded."""
    SportRepo(db).seed_defaults()
    db.commit()
    return db


@pytest.fixture
def db_with_sample_data(db_with_sports):
    """DB with sample fixtures, teams, stats, and bets for testing."""
    conn = db_with_sports
    sport_repo = SportRepo(conn)
    team_repo = TeamRepo(conn)
    fixture_repo = FixtureRepo(conn)
    stats_repo = StatsRepo(conn)

    football = sport_repo.get_by_name("football")
    basketball = sport_repo.get_by_name("basketball")
    tennis = sport_repo.get_by_name("tennis")

    # Football teams
    liverpool = team_repo.find_or_create("Liverpool", football.id, aliases=["LFC"])
    arsenal = team_repo.find_or_create("Arsenal", football.id, aliases=["ARS", "Gunners"])
    barca = team_repo.find_or_create("FC Barcelona", football.id, aliases=["Barca", "FCB"])
    real = team_repo.find_or_create("Real Madrid", football.id, aliases=["RMA"])

    # Basketball teams
    lakers = team_repo.find_or_create("LA Lakers", basketball.id)
    celtics = team_repo.find_or_create("Boston Celtics", basketball.id)

    # Tennis players
    djokovic = team_repo.find_or_create("Novak Djokovic", tennis.id)
    sinner = team_repo.find_or_create("Jannik Sinner", tennis.id)

    # Fixtures
    fix1 = Fixture(
        id=None, sport_id=football.id, competition_id=None,
        home_team_id=liverpool.id, away_team_id=arsenal.id,
        kickoff="2026-05-03T15:00:00", status="scheduled",
        source="test", fetched_at="2026-05-03T00:00:00",
    )
    fix1_id = fixture_repo.upsert(fix1)

    fix2 = Fixture(
        id=None, sport_id=football.id, competition_id=None,
        home_team_id=barca.id, away_team_id=real.id,
        kickoff="2026-05-03T20:00:00", status="scheduled",
        source="test", fetched_at="2026-05-03T00:00:00",
    )
    fix2_id = fixture_repo.upsert(fix2)

    fix3 = Fixture(
        id=None, sport_id=basketball.id, competition_id=None,
        home_team_id=lakers.id, away_team_id=celtics.id,
        kickoff="2026-05-03T02:00:00", status="scheduled",
        source="test", fetched_at="2026-05-03T00:00:00",
    )
    fix3_id = fixture_repo.upsert(fix3)

    fix4 = Fixture(
        id=None, sport_id=tennis.id, competition_id=None,
        home_team_id=djokovic.id, away_team_id=sinner.id,
        kickoff="2026-05-03T12:00:00", status="scheduled",
        source="test", fetched_at="2026-05-03T00:00:00",
    )
    fix4_id = fixture_repo.upsert(fix4)

    # Sample match stats for finished fixtures (to populate form)
    # Create a finished fixture to source stats from
    fix_fin = Fixture(
        id=None, sport_id=football.id, competition_id=None,
        home_team_id=liverpool.id, away_team_id=arsenal.id,
        kickoff="2026-04-26T15:00:00", status="finished",
        score_home=2, score_away=1,
        source="test", fetched_at="2026-04-26T00:00:00",
    )
    fix_fin_id = fixture_repo.upsert(fix_fin)

    stats_repo.save_match_stats(fix_fin_id, liverpool.id, {
        "corners": 6.0, "fouls": 11.0, "shots": 14.0,
    }, source="test")
    stats_repo.save_match_stats(fix_fin_id, arsenal.id, {
        "corners": 5.0, "fouls": 13.0, "shots": 10.0,
    }, source="test")

    conn.commit()
    return conn


@pytest.fixture
def sample_candidates():
    """List of MarketCandidate objects for coupon builder tests."""
    # Create minimal teams and fixtures for candidate generation
    teams = {
        "liverpool": Team(id=1, sport_id=1, name="Liverpool"),
        "arsenal": Team(id=2, sport_id=1, name="Arsenal"),
        "barca": Team(id=3, sport_id=1, name="FC Barcelona"),
        "real": Team(id=4, sport_id=1, name="Real Madrid"),
        "lakers": Team(id=5, sport_id=3, name="LA Lakers"),
        "celtics": Team(id=6, sport_id=3, name="Boston Celtics"),
        "djokovic": Team(id=7, sport_id=4, name="Novak Djokovic"),
        "sinner": Team(id=8, sport_id=4, name="Jannik Sinner"),
        "inter": Team(id=9, sport_id=1, name="Inter Milan"),
        "milan": Team(id=10, sport_id=1, name="AC Milan"),
        "warriors": Team(id=11, sport_id=3, name="Golden State Warriors"),
        "heat": Team(id=12, sport_id=3, name="Miami Heat"),
    }

    fixtures = [
        Fixture(id=1, sport_id=1, competition_id=None,
                home_team_id=1, away_team_id=2,
                kickoff="2026-05-03T15:00:00"),
        Fixture(id=2, sport_id=1, competition_id=None,
                home_team_id=3, away_team_id=4,
                kickoff="2026-05-03T20:00:00"),
        Fixture(id=3, sport_id=3, competition_id=None,
                home_team_id=5, away_team_id=6,
                kickoff="2026-05-03T02:00:00"),
        Fixture(id=4, sport_id=4, competition_id=None,
                home_team_id=7, away_team_id=8,
                kickoff="2026-05-03T12:00:00"),
        Fixture(id=5, sport_id=1, competition_id=None,
                home_team_id=9, away_team_id=10,
                kickoff="2026-05-03T18:00:00"),
        Fixture(id=6, sport_id=3, competition_id=None,
                home_team_id=11, away_team_id=12,
                kickoff="2026-05-03T01:00:00"),
    ]

    candidates = [
        MarketCandidate(
            fixture=fixtures[0], home_team=teams["liverpool"], away_team=teams["arsenal"],
            sport_name="football", competition_name="Premier League",
            market_name="Corners Total O/U", direction="OVER", line=9.5,
            safety_score=0.80, hit_rate_l10=0.80, hit_rate_h2h=0.75,
            hit_rate_l5=0.80, three_way_aligned=True,
            min_odds=1.25, best_odds=1.72, ev=0.15,
            betclic_hit_rate=0.70,
        ),
        MarketCandidate(
            fixture=fixtures[1], home_team=teams["barca"], away_team=teams["real"],
            sport_name="football", competition_name="La Liga",
            market_name="Fouls Total O/U", direction="OVER", line=22.5,
            safety_score=0.75, hit_rate_l10=0.75, hit_rate_h2h=0.80,
            hit_rate_l5=0.80, three_way_aligned=True,
            min_odds=1.33, best_odds=1.65, ev=0.12,
            betclic_hit_rate=0.65,
        ),
        MarketCandidate(
            fixture=fixtures[2], home_team=teams["lakers"], away_team=teams["celtics"],
            sport_name="basketball", competition_name="NBA",
            market_name="Total Points O/U", direction="OVER", line=215.5,
            safety_score=0.70, hit_rate_l10=0.70, hit_rate_h2h=None,
            hit_rate_l5=0.60, three_way_aligned=False,
            min_odds=1.43, best_odds=1.85, ev=0.10,
            betclic_hit_rate=None,
        ),
        MarketCandidate(
            fixture=fixtures[3], home_team=teams["djokovic"], away_team=teams["sinner"],
            sport_name="tennis", competition_name="Roland Garros",
            market_name="Total Games O/U", direction="OVER", line=22.5,
            safety_score=0.65, hit_rate_l10=0.65, hit_rate_h2h=0.60,
            hit_rate_l5=0.60, three_way_aligned=True,
            min_odds=1.54, best_odds=1.90, ev=0.08,
            betclic_hit_rate=0.55,
        ),
        MarketCandidate(
            fixture=fixtures[4], home_team=teams["inter"], away_team=teams["milan"],
            sport_name="football", competition_name="Serie A",
            market_name="Cards Total O/U", direction="OVER", line=4.5,
            safety_score=0.72, hit_rate_l10=0.72, hit_rate_h2h=0.70,
            hit_rate_l5=0.75, three_way_aligned=True,
            min_odds=1.39, best_odds=1.70, ev=0.11,
            betclic_hit_rate=0.60,
        ),
        MarketCandidate(
            fixture=fixtures[5], home_team=teams["warriors"], away_team=teams["heat"],
            sport_name="basketball", competition_name="NBA",
            market_name="Total Rebounds O/U", direction="UNDER", line=44.5,
            safety_score=0.68, hit_rate_l10=0.68, hit_rate_h2h=None,
            hit_rate_l5=0.65, three_way_aligned=True,
            min_odds=1.47, best_odds=1.80, ev=0.09,
            betclic_hit_rate=None,
        ),
    ]
    return candidates


@pytest.fixture
def config():
    """BettingConfig with test defaults."""
    return BettingConfig(
        bankroll_pln=50.0,
        daily_exposure_range=(5.0, 15.0),
        max_stake_pln=2.0,
        max_legs_per_coupon=4,
        min_coupons_per_day=3,
        min_safety_score=0.4,
        timezone="Europe/Warsaw",
        sports=[
            "football", "volleyball", "basketball", "tennis",
            "hockey", "snooker", "speedway", "baseball",
            "esports", "darts", "table_tennis", "handball",
            "mma", "padel",
        ],
        db_path=":memory:",
        low_risk_coupon_max_stake_pln=3.0,
        higher_risk_coupon_max_stake_pln=2.0,
        min_legs_per_coupon=2,
        max_same_sport_legs_in_coupon=2,
        low_risk_price_gap_threshold_pct=-2.0,
        higher_risk_price_gap_threshold_pct=-5.0,
        max_core_coupons=15,
        max_combo_coupons=20,
        max_singles=50,
        max_picks_per_day=80,
    )
