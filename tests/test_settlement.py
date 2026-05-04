"""Tests for the settlement module."""

import sqlite3

import pytest

from bet.config import BettingConfig
from bet.db.models import Bet, Coupon, Fixture
from bet.db.repositories import CouponRepo, FixtureRepo
from bet.db.schema import init_db
from bet.settlement.settler import settle_bet, settle_totals, update_bankroll


# ---------------------------------------------------------------------------
# Totals settlement
# ---------------------------------------------------------------------------


def test_settle_totals_over_won():
    """OVER 9.5, actual=10 → won."""
    assert settle_totals("OVER", 9.5, 10) == "won"


def test_settle_totals_over_lost():
    """OVER 9.5, actual=9 → lost."""
    assert settle_totals("OVER", 9.5, 9) == "lost"


def test_settle_totals_push():
    """OVER 9.0, actual=9 → push (exact match on integer line)."""
    assert settle_totals("OVER", 9.0, 9) == "push"


def test_settle_totals_under_won():
    """UNDER 9.5, actual=8 → won."""
    assert settle_totals("UNDER", 9.5, 8) == "won"


def test_settle_totals_under_lost():
    """UNDER 9.5, actual=10 → lost."""
    assert settle_totals("UNDER", 9.5, 10) == "lost"


# ---------------------------------------------------------------------------
# Bet-level settlement
# ---------------------------------------------------------------------------


def test_settle_bet_totals():
    """settle_bet resolves O/U market correctly."""
    bet = Bet(
        id=1, coupon_id=1, fixture_id=1,
        sport="football", event_name="A vs B",
        market="Goals Total O/U", selection="OVER 2.5",
        odds=1.80,
    )
    fixture = Fixture(
        id=1, sport_id=1, competition_id=None,
        home_team_id=1, away_team_id=2,
        kickoff="2026-05-03T15:00:00",
        status="finished", score_home=2, score_away=1,  # total=3 > 2.5
    )
    assert settle_bet(bet, fixture) == "won"


# ---------------------------------------------------------------------------
# Coupon-level settlement
# ---------------------------------------------------------------------------


def _make_db_with_coupon(bets_data: list[dict]) -> sqlite3.Connection:
    """Create an in-memory DB with a coupon and bets."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)

    # Seed a sport and teams
    conn.execute(
        "INSERT INTO sports (name, tier, stat_keys) VALUES (?, ?, ?)",
        ("football", 1, "[]"),
    )
    conn.execute(
        "INSERT INTO teams (sport_id, name, aliases) VALUES (?, ?, ?)",
        (1, "Team A", "[]"),
    )
    conn.execute(
        "INSERT INTO teams (sport_id, name, aliases) VALUES (?, ?, ?)",
        (1, "Team B", "[]"),
    )

    coupon_repo = CouponRepo(conn)
    fixture_repo = FixtureRepo(conn)

    coupon = Coupon(
        id=None, coupon_id="AKO-2026-05-03-001",
        total_odds=3.24, stake_pln=2.0,
        status="pending", created_at="2026-05-03T00:00:00",
    )
    coupon_db_id = coupon_repo.create_coupon(coupon)

    for bd in bets_data:
        fix = Fixture(
            id=None, sport_id=1, competition_id=None,
            home_team_id=1, away_team_id=2,
            kickoff=bd["kickoff"], status="finished",
            score_home=bd["score_home"], score_away=bd["score_away"],
            source="test", fetched_at="2026-05-03T00:00:00",
        )
        fix_id = fixture_repo.upsert(fix)

        bet = Bet(
            id=None, coupon_id=coupon_db_id, fixture_id=fix_id,
            sport="football", event_name="Team A vs Team B",
            market=bd["market"], selection=bd["selection"],
            odds=bd["odds"],
        )
        coupon_repo.add_bet(bet)

    conn.commit()
    return conn


def test_settle_coupon_one_leg_lost():
    """Any leg lost → coupon is lost."""
    conn = _make_db_with_coupon([
        {
            "kickoff": "2026-05-03T15:00:00",
            "score_home": 2, "score_away": 1,  # total=3 > 2.5 → won
            "market": "Goals Total O/U", "selection": "OVER 2.5", "odds": 1.80,
        },
        {
            "kickoff": "2026-05-03T18:00:00",
            "score_home": 1, "score_away": 0,  # total=1 < 2.5 → lost (bet was OVER)
            "market": "Goals Total O/U", "selection": "OVER 2.5", "odds": 1.80,
        },
    ])

    coupon_repo = CouponRepo(conn)
    coupon, bets = coupon_repo.get_coupon_with_bets(1)

    fixture_repo = FixtureRepo(conn)
    any_lost = False
    for bet in bets:
        fixture = fixture_repo.get_by_id(bet.fixture_id)
        outcome = settle_bet(bet, fixture)
        coupon_repo.settle_bet(bet.id, outcome, 0.0)
        if outcome == "lost":
            any_lost = True

    if any_lost:
        coupon_repo.settle_coupon(coupon.id, "lost", -(coupon.stake_pln or 0))

    conn.commit()

    settled_coupon, _ = coupon_repo.get_coupon_with_bets(1)
    assert settled_coupon.status == "lost"
    assert settled_coupon.pnl_pln == -2.0


def test_settle_coupon_all_won():
    """All legs won → coupon won, PnL = stake * (total_odds - 1)."""
    conn = _make_db_with_coupon([
        {
            "kickoff": "2026-05-03T15:00:00",
            "score_home": 2, "score_away": 1,  # total=3 > 2.5 → won
            "market": "Goals Total O/U", "selection": "OVER 2.5", "odds": 1.80,
        },
        {
            "kickoff": "2026-05-03T18:00:00",
            "score_home": 3, "score_away": 2,  # total=5 > 2.5 → won
            "market": "Goals Total O/U", "selection": "OVER 2.5", "odds": 1.80,
        },
    ])

    coupon_repo = CouponRepo(conn)
    coupon, bets = coupon_repo.get_coupon_with_bets(1)

    fixture_repo = FixtureRepo(conn)
    all_won = True
    for bet in bets:
        fixture = fixture_repo.get_by_id(bet.fixture_id)
        outcome = settle_bet(bet, fixture)
        coupon_repo.settle_bet(bet.id, outcome, 0.0)
        if outcome != "won":
            all_won = False

    if all_won:
        pnl = round((coupon.stake_pln or 0) * ((coupon.total_odds or 1) - 1), 2)
        coupon_repo.settle_coupon(coupon.id, "won", pnl)

    conn.commit()

    settled_coupon, _ = coupon_repo.get_coupon_with_bets(1)
    assert settled_coupon.status == "won"
    # PnL = 2.0 * (3.24 - 1) = 2.0 * 2.24 = 4.48
    assert settled_coupon.pnl_pln == 4.48


# ---------------------------------------------------------------------------
# Bankroll update
# ---------------------------------------------------------------------------


def test_bankroll_update(config):
    """Bankroll increases on win, decreases on loss."""
    # Win scenario
    new_bankroll = update_bankroll(None, pnl=4.48, config=config)
    assert new_bankroll == 54.48  # 50.0 + 4.48

    # Loss scenario
    new_bankroll_loss = update_bankroll(None, pnl=-2.0, config=config)
    assert new_bankroll_loss == 48.0  # 50.0 - 2.0
