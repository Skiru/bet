"""DB-based settlement engine.

Settles pending bets by fetching results from DB fixtures
or external APIs (The-Odds-API scores endpoint).

Auto-settles: totals O/U, BTTS, 1X2, Double Chance.
Flags manual: corners, cards, fouls (need Betclic verification).
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone

from bet.config import BettingConfig
from bet.db.models import Bet, Coupon, Fixture
from bet.db.repositories import CouponRepo, FixtureRepo

logger = logging.getLogger(__name__)

# Markets that can be auto-settled from final score (goals/runs only)
AUTO_SETTLE_MARKETS = {
    "Goals Total O/U",
    "Total Goals O/U",
    "Match Winner",
    "1X2",
    "Double Chance",
    "BTTS",
}

# Markets requiring Betclic app verification (stat-based or sport-specific)
# Total Games/Frames/Sets/Points/Rounds/Maps CANNOT be auto-settled from
# fixture score_home + score_away (e.g., tennis sets ≠ total games).
MANUAL_MARKETS = {
    "Total Points O/U",
    "Total Sets O/U",
    "Total Games O/U",
    "Total Frames O/U",
    "Total Rounds O/U",
    "Total Maps O/U",
    "Corners Total O/U",
    "Team A Corners O/U",
    "Team B Corners O/U",
    "Fouls Total O/U",
    "Team A Fouls O/U",
    "Team B Fouls O/U",
    "Cards Total O/U",
    "Team A Cards O/U",
    "Team B Cards O/U",
    "Shots Total O/U",
    "Shots on Target Total O/U",
    "Team A Shots O/U",
    "Team B Shots O/U",
    "Team A Shots on Target O/U",
    "Team B Shots on Target O/U",
}


async def settle_day(target_date: date, db_conn) -> dict:
    """Settle all pending bets for a given day.

    1. Find pending bets where fixture kickoff matches target_date
    2. For each pending bet:
       a. Check if fixture has a final score in DB
       b. If finished: auto-settle standard markets
       c. If stat-based: flag as manual
       d. If not finished: skip (will retry next run)
    3. Update coupon status based on leg outcomes
    4. Calculate PnL

    Returns: {"settled": N, "still_pending": M, "manual": K, "pnl": X.XX}
    """
    coupon_repo = CouponRepo(db_conn)
    fixture_repo = FixtureRepo(db_conn)

    date_str = target_date.isoformat()
    settled_count = 0
    still_pending = 0
    manual_count = 0
    total_pnl = 0.0

    # Get all pending coupons
    pending_coupons = coupon_repo.get_pending()

    for coupon in pending_coupons:
        coupon_obj, bets = coupon_repo.get_coupon_with_bets(coupon.id)
        if not coupon_obj:
            continue

        # Check if any bet belongs to our target date
        date_match = False
        for bet in bets:
            if bet.fixture_id:
                fix = fixture_repo.get_by_id(bet.fixture_id)
                if fix and fix.kickoff.startswith(date_str):
                    date_match = True
                    break

        if not date_match:
            continue

        # Try to settle each leg
        all_settled = True
        any_lost = False
        has_manual = False

        for bet in bets:
            if bet.status != "pending":
                if bet.status == "lost":
                    any_lost = True
                continue

            # Check if this is a manual market
            if bet.market in MANUAL_MARKETS:
                has_manual = True
                manual_count += 1
                all_settled = False
                continue

            # Get fixture result
            fixture = None
            if bet.fixture_id:
                fixture = fixture_repo.get_by_id(bet.fixture_id)

            if not fixture or fixture.status != "finished":
                all_settled = False
                still_pending += 1
                continue

            # Auto-settle
            outcome = settle_bet(bet, fixture)
            if outcome == "pending":
                all_settled = False
                still_pending += 1
                continue

            bet_pnl = 0.0
            if outcome == "won":
                bet_pnl = 0.0  # PnL calculated at coupon level
            elif outcome == "lost":
                any_lost = True

            coupon_repo.settle_bet(bet.id, outcome, bet_pnl)
            settled_count += 1

        # Update coupon status
        if any_lost:
            pnl = -(coupon_obj.stake_pln or 0)
            coupon_repo.settle_coupon(coupon_obj.id, "lost", pnl)
            total_pnl += pnl
        elif all_settled and not has_manual:
            pnl = (coupon_obj.stake_pln or 0) * ((coupon_obj.total_odds or 1) - 1)
            pnl = round(pnl, 2)
            coupon_repo.settle_coupon(coupon_obj.id, "won", pnl)
            total_pnl += pnl

    db_conn.commit()

    return {
        "settled": settled_count,
        "still_pending": still_pending,
        "manual": manual_count,
        "pnl": round(total_pnl, 2),
    }


def settle_bet(bet: Bet, fixture: Fixture) -> str:
    """Determine bet outcome from fixture result.

    Returns: "won" | "lost" | "void" | "push" | "pending"
    """
    if fixture.score_home is None or fixture.score_away is None:
        return "pending"

    market = bet.market
    selection = bet.selection.upper()

    # Totals O/U
    if "Total" in market and "O/U" in market:
        direction, line = _parse_selection(selection)
        if direction is None or line is None:
            return "pending"

        total = fixture.score_home + fixture.score_away
        return settle_totals(direction, line, total)

    # Match Winner / 1X2
    if market in ("Match Winner", "1X2"):
        return _settle_1x2(selection, fixture.score_home, fixture.score_away)

    # Double Chance
    if market == "Double Chance":
        return _settle_double_chance(selection, fixture.score_home, fixture.score_away)

    # BTTS
    if market == "BTTS":
        both_scored = fixture.score_home > 0 and fixture.score_away > 0
        if "YES" in selection:
            return "won" if both_scored else "lost"
        else:
            return "won" if not both_scored else "lost"

    return "pending"


def settle_totals(direction: str, line: float, actual_value: float) -> str:
    """Settle O/U market.

    'OVER 9.5' with actual=10 -> 'won'
    'UNDER 9.5' with actual=10 -> 'lost'
    Exact match on integer line -> 'push'
    """
    if actual_value == line:
        return "push"

    if direction == "OVER":
        return "won" if actual_value > line else "lost"
    elif direction == "UNDER":
        return "won" if actual_value < line else "lost"

    return "pending"


def _settle_1x2(selection: str, score_home: int, score_away: int) -> str:
    """Settle 1X2/Match Winner market."""
    if score_home > score_away:
        result = "1"
    elif score_away > score_home:
        result = "2"
    else:
        result = "X"

    sel_upper = selection.strip().upper()

    if sel_upper in ("1", "HOME"):
        return "won" if result == "1" else "lost"
    elif sel_upper in ("2", "AWAY"):
        return "won" if result == "2" else "lost"
    elif sel_upper in ("X", "DRAW"):
        return "won" if result == "X" else "lost"

    return "pending"


def _settle_double_chance(selection: str, score_home: int, score_away: int) -> str:
    """Settle Double Chance market."""
    if score_home > score_away:
        result = "1"
    elif score_away > score_home:
        result = "2"
    else:
        result = "X"

    sel_upper = selection.strip().upper()

    if sel_upper in ("1X", "HOME_DRAW"):
        return "won" if result in ("1", "X") else "lost"
    elif sel_upper in ("X2", "DRAW_AWAY"):
        return "won" if result in ("X", "2") else "lost"
    elif sel_upper in ("12", "HOME_AWAY"):
        return "won" if result in ("1", "2") else "lost"

    return "pending"


def _parse_selection(selection: str) -> tuple[str | None, float | None]:
    """Parse selection like 'OVER 9.5' into (direction, line)."""
    m = re.match(r"(OVER|UNDER)\s+(\d+\.?\d*)", selection.upper())
    if m:
        return m.group(1), float(m.group(2))
    return None, None


def update_bankroll(db_conn, pnl: float, config: BettingConfig) -> float:
    """Update bankroll after settlement. Returns new bankroll."""
    new_bankroll = config.bankroll_pln + pnl
    return round(new_bankroll, 2)
