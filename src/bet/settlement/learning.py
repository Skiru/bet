"""Betclic learning analysis — ADVISORY ONLY.

Reads from SQLite `bets` and `coupons` tables to produce hit rate analysis.
Results are displayed to the user but NEVER used for auto-rejection.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

# Market category mapping (Polish Betclic names -> English categories)
MARKET_CATEGORIES: dict[str, str] = {
    "Zwycięzca meczu": "match_winner",
    "Wynik meczu": "match_winner",
    "Wynik meczu (z wyłączeniem dogrywki)": "match_winner",
    "Łączna liczba gemów": "game_totals",
    "Gole Powyżej/Poniżej": "totals",
    "Rzuty rożne": "corners",
    "Rzuty rożne (bez dogrywki)": "corners",
    "Suma rzutów rożnych (razem z dogrywką)": "corners",
    "Rzuty rożne (bez dogrywki) -": "team_corners",
    "Oba zespoły strzelą gola": "btts",
    "Suma punktów": "totals",
    "Handicap": "handicap",
    "Handicap setowy": "set_handicap",
    "Liczba kartek": "cards",
    "Liczba fauli w meczu (OPTA)": "fouls",
    "Łączna liczba frejmów": "frame_totals",
    "Podwójna Szansa": "double_chance",
    "Wynik handicap": "handicap",
    "Przewaga dwoma bramkami lub wygrana w meczu (reg. czas)": "win_by_2_or_win",
    "Liczba Runs": "runs_totals",
    "Zawodnik wygra 1. seta 6-0, 6-1, 6-2 lub wygra mecz": "tennis_special",
    "Wynik i gole": "result_and_goals",
    "Liczba goli (Dogrywka i rzuty karne są wliczane do zakładu)": "totals_incl_et",
    "Liczba strzałów w meczu (OPTA)": "shots",
    "Liczba strzałów w meczu (OPTA) -": "team_shots",
    "Liczba celnych strzałów zawodnika (OPTA)": "player_shots",
    "Zwycięzca rywalizacji": "match_winner",
    "Head-to-Head": "match_winner",
    "Liczba rund (0.5 oznacza połowę czasu kolejnej rundy)": "round_totals",
    # English market names from the new system
    "Corners Total O/U": "corners",
    "Fouls Total O/U": "fouls",
    "Cards Total O/U": "cards",
    "Shots Total O/U": "shots",
    "Shots on Target Total O/U": "shots",
    "Goals Total O/U": "totals",
    "Total Goals O/U": "totals",
    "Total Points O/U": "totals",
    "Total Games O/U": "game_totals",
    "Total Sets O/U": "set_handicap",
    "Total Frames O/U": "frame_totals",
    "Total Rounds O/U": "round_totals",
    "Total Maps O/U": "totals",
    "Match Winner": "match_winner",
    "1X2": "match_winner",
    "Double Chance": "double_chance",
    "BTTS": "btts",
    "Handicap": "handicap",
}

_STATISTICAL_CATEGORIES = frozenset({
    "corners", "team_corners", "cards", "fouls",
    "game_totals", "frame_totals", "totals", "totals_incl_et",
    "set_handicap", "runs_totals", "shots", "team_shots",
    "player_shots", "round_totals",
})


def categorize_market(market_name: str) -> str:
    """Map market name to a standardized category."""
    if not market_name:
        return "unknown"
    for key, cat in sorted(MARKET_CATEGORIES.items(), key=lambda x: -len(x[0])):
        if key in market_name:
            return cat
    lower = market_name.lower()
    if "corner" in lower or "rożn" in lower:
        return "corners"
    if "card" in lower or "kartek" in lower:
        return "cards"
    if "foul" in lower or "faul" in lower:
        return "fouls"
    if "shot" in lower or "strzał" in lower:
        return "shots"
    if "game" in lower or "gem" in lower:
        return "game_totals"
    if "set" in lower:
        return "set_handicap"
    if "goal" in lower or "bramk" in lower or "gol" in lower:
        return "totals"
    if "point" in lower or "punkt" in lower:
        return "totals"
    if "handicap" in lower:
        return "handicap"
    return "other"


def is_statistical_market(category: str) -> bool:
    """Check if market category is statistical (not outcome-based)."""
    return category in _STATISTICAL_CATEGORIES


def analyze_history(db_conn: sqlite3.Connection) -> dict:
    """Analyze all historical bets from DB.

    Produces 7 analysis sections. All data is ADVISORY ONLY —
    displayed to user, never used for auto-rejection.

    Returns dict with all analysis sections.
    """
    # Fetch settled bets with coupon info
    bets = db_conn.execute(
        "SELECT b.*, c.coupon_id as coupon_id_str, c.total_odds, "
        "c.stake_pln as coupon_stake, c.status as coupon_status, c.pnl_pln as coupon_pnl "
        "FROM bets b JOIN coupons c ON b.coupon_id = c.id "
        "WHERE b.status IN ('won', 'lost')"
    ).fetchall()

    if not bets:
        return {"status": "no_data", "message": "No settled bets found"}

    result: dict = {}

    # §1. Market hit rates
    market_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"won": 0, "lost": 0})
    for bet in bets:
        cat = categorize_market(bet["market"])
        market_stats[cat][bet["status"]] += 1

    result["market_hit_rates"] = {
        cat: {
            "won": d["won"],
            "lost": d["lost"],
            "total": d["won"] + d["lost"],
            "rate": d["won"] / (d["won"] + d["lost"]) if (d["won"] + d["lost"]) > 0 else 0,
            "is_statistical": is_statistical_market(cat),
        }
        for cat, d in market_stats.items()
    }

    # §2. Sport hit rates
    sport_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"won": 0, "lost": 0})
    for bet in bets:
        sport_stats[bet["sport"]][bet["status"]] += 1

    result["sport_hit_rates"] = {
        sport: {
            "won": d["won"],
            "lost": d["lost"],
            "total": d["won"] + d["lost"],
            "rate": d["won"] / (d["won"] + d["lost"]) if (d["won"] + d["lost"]) > 0 else 0,
        }
        for sport, d in sport_stats.items()
    }

    # §3. Direction bias (OVER vs UNDER)
    direction_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"won": 0, "lost": 0})
    for bet in bets:
        sel = (bet["selection"] or "").upper()
        if "OVER" in sel:
            direction_stats["over"][bet["status"]] += 1
        elif "UNDER" in sel:
            direction_stats["under"][bet["status"]] += 1

    result["direction_bias"] = {
        d: {
            "won": stats["won"],
            "lost": stats["lost"],
            "rate": stats["won"] / (stats["won"] + stats["lost"]) if (stats["won"] + stats["lost"]) > 0 else 0,
        }
        for d, stats in direction_stats.items()
    }

    # §4. Coupon size analysis
    coupon_rows = db_conn.execute(
        "SELECT c.id, c.status, c.stake_pln, c.pnl_pln, "
        "(SELECT COUNT(*) FROM bets WHERE coupon_id = c.id) as leg_count "
        "FROM coupons c WHERE c.status IN ('won', 'lost')"
    ).fetchall()

    size_stats: dict[int, dict[str, int | float]] = defaultdict(
        lambda: {"won": 0, "lost": 0, "staked": 0.0, "pnl": 0.0}
    )
    for crow in coupon_rows:
        legs = crow["leg_count"]
        size_stats[legs][crow["status"]] += 1
        size_stats[legs]["staked"] += crow["stake_pln"] or 0
        size_stats[legs]["pnl"] += crow["pnl_pln"] or 0

    result["coupon_size"] = {
        legs: {
            "won": d["won"],
            "lost": d["lost"],
            "rate": d["won"] / (d["won"] + d["lost"]) if (d["won"] + d["lost"]) > 0 else 0,
            "staked": d["staked"],
            "pnl": d["pnl"],
        }
        for legs, d in sorted(size_stats.items())
    }

    # §5. Coupon-killer analysis
    killer_stats: dict[str, int] = defaultdict(int)
    lost_coupons = db_conn.execute(
        "SELECT c.id FROM coupons c WHERE c.status = 'lost'"
    ).fetchall()

    for lc in lost_coupons:
        lost_legs = db_conn.execute(
            "SELECT market, sport FROM bets WHERE coupon_id = ? AND status = 'lost'",
            (lc["id"],),
        ).fetchall()
        for leg in lost_legs:
            cat = categorize_market(leg["market"])
            killer_stats[f"{leg['sport']}×{cat}"] += 1

    result["coupon_killers"] = dict(
        sorted(killer_stats.items(), key=lambda x: -x[1])[:10]
    )

    # §6. ROI by sport
    sport_pnl: dict[str, dict[str, float]] = defaultdict(
        lambda: {"staked": 0.0, "pnl": 0.0}
    )
    for crow in coupon_rows:
        # Get sport of first bet in coupon
        first_bet = db_conn.execute(
            "SELECT sport FROM bets WHERE coupon_id = ? LIMIT 1",
            (crow["id"],),
        ).fetchone()
        if first_bet:
            sport_pnl[first_bet["sport"]]["staked"] += crow["stake_pln"] or 0
            sport_pnl[first_bet["sport"]]["pnl"] += crow["pnl_pln"] or 0

    result["roi_by_sport"] = {
        sport: {
            "staked": d["staked"],
            "pnl": d["pnl"],
            "roi": d["pnl"] / d["staked"] * 100 if d["staked"] > 0 else 0,
        }
        for sport, d in sport_pnl.items()
    }

    # §7. Statistical vs outcome markets
    stat_won = sum(1 for b in bets if is_statistical_market(categorize_market(b["market"])) and b["status"] == "won")
    stat_lost = sum(1 for b in bets if is_statistical_market(categorize_market(b["market"])) and b["status"] == "lost")
    outc_won = sum(1 for b in bets if not is_statistical_market(categorize_market(b["market"])) and b["status"] == "won")
    outc_lost = sum(1 for b in bets if not is_statistical_market(categorize_market(b["market"])) and b["status"] == "lost")

    result["stat_vs_outcome"] = {
        "statistical": {
            "won": stat_won,
            "lost": stat_lost,
            "rate": stat_won / (stat_won + stat_lost) if (stat_won + stat_lost) > 0 else 0,
        },
        "outcome": {
            "won": outc_won,
            "lost": outc_lost,
            "rate": outc_won / (outc_won + outc_lost) if (outc_won + outc_lost) > 0 else 0,
        },
    }

    return result


def get_market_hit_rates(db_conn: sqlite3.Connection) -> dict[str, float]:
    """Return hit rates per market category for advisory display.

    Never modifies candidate rankings — purely informational.
    """
    bets = db_conn.execute(
        "SELECT market, status FROM bets WHERE status IN ('won', 'lost')"
    ).fetchall()

    category_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"won": 0, "lost": 0})
    for bet in bets:
        cat = categorize_market(bet["market"])
        category_stats[cat][bet["status"]] += 1

    return {
        cat: d["won"] / (d["won"] + d["lost"]) if (d["won"] + d["lost"]) > 0 else 0
        for cat, d in category_stats.items()
    }
