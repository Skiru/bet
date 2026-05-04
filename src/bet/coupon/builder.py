"""Coupon builder — constructs max 3-leg coupons from ranked candidates.

Rules:
- Max 3 legs per coupon (HARD CAP)
- Each coupon has legs from DIFFERENT events (fixture IDs)
- Max 2 legs from the same sport per coupon
- Flat staking: config.max_stake_pln per coupon
- Total daily exposure ≤ config.daily_exposure_range[1]
"""

from __future__ import annotations

from datetime import date, datetime

from bet.config import BettingConfig
from bet.db.models import Bet, Coupon, MarketCandidate

MAX_LEGS = 3  # Hard cap — 5+ legs = 0% win rate empirically
MAX_SAME_SPORT = 2


def build_coupons(
    candidates: list[MarketCandidate],
    config: BettingConfig,
    max_coupons: int = 5,
) -> list[tuple[Coupon, list[Bet]]]:
    """Build coupons from ranked candidates.

    Algorithm (greedy):
    1. Sort candidates by safety_score desc (best first)
    2. For each candidate, try to add to current coupon
    3. If independence rules violated, start new coupon
    4. Stop when max_coupons reached or candidates exhausted

    Returns list of (Coupon, [Bet, ...]) tuples.
    """
    if not candidates:
        return []

    # Mandatory data gate: only candidates with real stats pass
    candidates = [c for c in candidates if c.safety_score > 0.0 and c.hit_rate_l10 > 0.0]
    if not candidates:
        return []

    # Sort by EV then safety score
    sorted_candidates = sorted(
        candidates,
        key=lambda c: (
            -(c.ev if c.ev is not None else 0),
            -c.safety_score,
        ),
    )

    today = date.today().isoformat()
    coupons: list[tuple[Coupon, list[Bet]]] = []
    current_bets: list[Bet] = []
    current_candidates: list[MarketCandidate] = []
    coupon_index = 1
    daily_exposure = 0.0
    max_daily = config.daily_exposure_range[1]

    for candidate in sorted_candidates:
        if daily_exposure >= max_daily:
            break

        if _are_independent(current_bets, current_candidates, candidate):
            bet = _candidate_to_bet(candidate, coupon_id=0)
            current_bets.append(bet)
            current_candidates.append(candidate)
        else:
            # Flush current coupon if it has legs
            if current_bets:
                coupon, bets = _finalize_coupon(
                    current_bets, today, coupon_index, config,
                )
                coupons.append((coupon, bets))
                daily_exposure += config.max_stake_pln
                coupon_index += 1

                if len(coupons) >= max_coupons:
                    break

            # Start new coupon with this candidate
            current_bets = []
            current_candidates = []
            bet = _candidate_to_bet(candidate, coupon_id=0)
            current_bets.append(bet)
            current_candidates.append(candidate)

        # If current coupon reached max legs, flush
        if len(current_bets) >= MAX_LEGS:
            coupon, bets = _finalize_coupon(
                current_bets, today, coupon_index, config,
            )
            coupons.append((coupon, bets))
            daily_exposure += config.max_stake_pln
            coupon_index += 1
            current_bets = []
            current_candidates = []

            if len(coupons) >= max_coupons:
                break

    # Flush remaining
    if current_bets and len(coupons) < max_coupons and daily_exposure < max_daily:
        coupon, bets = _finalize_coupon(
            current_bets, today, coupon_index, config,
        )
        coupons.append((coupon, bets))

    return coupons


def _are_independent(
    existing_bets: list[Bet],
    existing_candidates: list[MarketCandidate],
    new_candidate: MarketCandidate,
) -> bool:
    """Check if adding candidate maintains coupon independence.

    - Must not exceed MAX_LEGS
    - Different event (different fixture_id)
    - Max 2 legs from same sport
    """
    if len(existing_bets) >= MAX_LEGS:
        return False

    # Check same fixture
    new_fixture_id = new_candidate.fixture.id
    for c in existing_candidates:
        if c.fixture.id == new_fixture_id:
            return False

    # Check same sport limit
    sport_count = sum(
        1 for c in existing_candidates if c.sport_name == new_candidate.sport_name
    )
    if sport_count >= MAX_SAME_SPORT:
        return False

    return True


def _generate_coupon_id(date_str: str, index: int) -> str:
    """Generate coupon ID: AKO-YYYY-MM-DD-NNN."""
    return f"AKO-{date_str}-{index:03d}"


def _candidate_to_bet(candidate: MarketCandidate, coupon_id: int) -> Bet:
    """Convert a MarketCandidate to a Bet model."""
    import statistics as stats_mod

    from bet.coupon.translations import betclic_navigation, translate_market

    event_name = f"{candidate.home_team.name} vs {candidate.away_team.name}"

    # Determine which team name to use for team-specific markets
    team_name = ""
    if "Team A" in candidate.market_name:
        team_name = candidate.home_team.name
    elif "Team B" in candidate.market_name:
        team_name = candidate.away_team.name

    market_pl = translate_market(
        candidate.market_name,
        candidate.direction,
        candidate.line,
        team_name=team_name,
    )

    # Derive market category for navigation
    market_cat = _market_to_category(candidate.market_name)
    nav_hint = betclic_navigation(
        sport=candidate.sport_name,
        competition=candidate.competition_name,
        home=candidate.home_team.name,
        away=candidate.away_team.name,
        market_category=market_cat,
    )

    selection = f"{candidate.direction} {candidate.line:g}"

    # Build deep stats detail
    stats_detail = None
    if candidate.l10_values:
        l10_vals = candidate.l10_values
        l5_vals = candidate.l5_values or l10_vals[:5]
        stats_detail = {
            "l10_avg": round(stats_mod.mean(l10_vals), 1),
            "l5_avg": round(stats_mod.mean(l5_vals), 1) if l5_vals else None,
            "trend": candidate.trend,
            "hit_l10": round(candidate.hit_rate_l10 * 10) if candidate.hit_rate_l10 else 0,
            "total_l10": len(l10_vals),
            "hit_h2h": f"{candidate.hit_rate_h2h:.0%}" if candidate.hit_rate_h2h is not None else None,
            "aligned": candidate.three_way_aligned,
            "recent_values": l10_vals[:5],
        }

    return Bet(
        id=None,
        coupon_id=coupon_id,
        fixture_id=candidate.fixture.id,
        sport=candidate.sport_name,
        event_name=event_name,
        market=candidate.market_name,
        selection=selection,
        odds=candidate.best_odds or candidate.min_odds,
        min_odds=candidate.min_odds,
        safety_score=candidate.safety_score,
        hit_rate=candidate.hit_rate_l10,
        status="pending",
        market_pl=market_pl,
        navigation_hint=nav_hint,
        stats_detail=stats_detail,
    )


def _finalize_coupon(
    bets: list[Bet],
    date_str: str,
    index: int,
    config: BettingConfig,
) -> tuple[Coupon, list[Bet]]:
    """Create a Coupon and assign bet coupon_ids."""
    coupon_id_str = _generate_coupon_id(date_str, index)

    total_odds = 1.0
    for bet in bets:
        total_odds *= bet.odds
    total_odds = round(total_odds, 2)

    coupon = Coupon(
        id=None,
        coupon_id=coupon_id_str,
        coupon_type="AKO",
        total_odds=total_odds,
        stake_pln=config.max_stake_pln,
        status="pending",
        created_at=datetime.now().isoformat(),
    )

    return coupon, bets


def _market_to_category(market_name: str) -> str:
    """Map market name to Betclic navigation category."""
    lower = market_name.lower()
    if "corner" in lower:
        return "corners"
    if "foul" in lower:
        return "fouls"
    if "card" in lower:
        return "cards"
    if "shot" in lower:
        return "shots"
    if "goal" in lower:
        return "goals"
    if "point" in lower:
        return "points"
    if "set" in lower:
        return "sets"
    if "game" in lower:
        return "games"
    if "frame" in lower:
        return "frames"
    if "map" in lower:
        return "maps"
    if "round" in lower:
        return "rounds"
    if "leg" in lower:
        return "legs"
    if "ace" in lower:
        return "aces"
    if "rebound" in lower:
        return "rebounds"
    if "180" in lower:
        return "180s"
    if "heat" in lower:
        return "heat_wins"
    return "main"
