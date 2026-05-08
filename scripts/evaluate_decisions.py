#!/usr/bin/env python3
"""Post-settlement decision evaluation — compare predictions to actual outcomes.

After bets are settled (won/lost), this script:
1. Finds all settled bets with decision snapshots
2. Fetches actual match stats from match_stats table
3. Compares predicted values to actual values
4. Computes deviation and generates pattern tags
5. Saves decision_outcomes for learning queries

Usage:
    python3 scripts/evaluate_decisions.py --date 2026-05-01
    python3 scripts/evaluate_decisions.py --date 2026-05-01 --verbose
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

_NOW = lambda: datetime.now(timezone.utc).isoformat()

# Market name → stat_key mapping for extracting actual values
MARKET_TO_STAT_KEY = {
    "corners": "corners",
    "Corners Total O/U": "corners",
    "fouls": "fouls",
    "Fouls Total O/U": "fouls",
    "cards": "yellow_cards",
    "Cards Total O/U": "yellow_cards",
    "yellow_cards": "yellow_cards",
    "shots": "shots",
    "Shots Total O/U": "shots",
    "shots_on_target": "shots_on_target",
    "goals": "goals",
    "Goals Total O/U": "goals",
    "Total Goals O/U": "goals",
    "total_games": "total_games",
    "Total Games O/U": "total_games",
    "games_won": "games_won",
    "total_points": "total_points",
    "Total Points O/U": "total_points",
    "points": "points",
    "total_frames": "total_frames",
    "Total Frames O/U": "total_frames",
    "frames_won": "frames_won",
    "total_runs": "runs",
    "Total Runs O/U": "runs",
    "runs": "runs",
    "total_maps": "total_maps",
    "Total Maps O/U": "total_maps",
    "maps_won": "maps_won",
    "aces": "aces",
    "Total Aces O/U": "aces",
    "double_faults": "double_faults",
    "total_legs": "total_legs",
    "Total Legs O/U": "total_legs",
    "legs_won": "legs_won",
    "one_eighties": "one_eighties",
    "Total 180s O/U": "one_eighties",
    "rebounds": "rebounds",
    "Total Rebounds O/U": "rebounds",
    "assists": "assists",
    "steals": "steals",
    "blocks": "blocks",
    "turnovers": "turnovers",
    "saves": "saves",
    "offsides": "offsides",
    "possession": "possession",
    "total_goals": "total_goals",
    "sets_won": "sets_won",
    "Total Sets O/U": "sets_won",
}


def load_settled_bets_for_date(betting_date: str) -> list[dict]:
    """Load all settled bets for a given date from DB."""
    try:
        from bet.db.connection import get_db

        with get_db() as conn:
            rows = conn.execute(
                "SELECT b.id AS bet_id, b.fixture_id, b.sport, b.market, "
                "b.selection, b.odds, b.status, b.stats_detail, b.event_name, "
                "c.coupon_id, c.placed_at, "
                "COALESCE(comp.name, '') AS competition "
                "FROM bets b "
                "JOIN coupons c ON b.coupon_id = c.id "
                "LEFT JOIN fixtures f ON b.fixture_id = f.id "
                "LEFT JOIN competitions comp ON f.competition_id = comp.id "
                "WHERE b.status IN ('won', 'lost') "
                "AND COALESCE(c.placed_at, c.created_at) LIKE ? "
                "AND b.fixture_id IS NOT NULL",
                (f"{betting_date}%",),
            ).fetchall()

            results = []
            for r in rows:
                stats_detail = None
                if r["stats_detail"]:
                    try:
                        stats_detail = json.loads(r["stats_detail"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                results.append({
                    "bet_id": r["bet_id"],
                    "fixture_id": r["fixture_id"],
                    "sport": r["sport"],
                    "market": r["market"],
                    "selection": r["selection"],
                    "odds": r["odds"],
                    "status": r["status"],
                    "stats_detail": stats_detail,
                    "event_name": r["event_name"],
                    "competition": r["competition"],
                })
            return results
    except Exception as e:
        print(f"[evaluate] Failed to load settled bets: {e}")
        return []


def load_actual_match_stats(fixture_id: int) -> dict:
    """Load actual match stats from match_stats table.

    Returns: {team_id: {stat_key: stat_value}}
    """
    try:
        from bet.db.connection import get_db

        with get_db() as conn:
            rows = conn.execute(
                "SELECT team_id, stat_key, stat_value FROM match_stats WHERE fixture_id = ?",
                (fixture_id,),
            ).fetchall()
            stats = {}
            for r in rows:
                team_id = r["team_id"]
                if team_id not in stats:
                    stats[team_id] = {}
                stats[team_id][r["stat_key"]] = r["stat_value"]
            return stats
    except Exception as e:
        print(f"[evaluate] Failed to load match stats for fixture {fixture_id}: {e}")
        return {}


def extract_actual_value(match_stats: dict, market: str, sport: str) -> float | None:
    """Extract the actual combined value for a market from match_stats.

    For combined markets (corners, fouls, etc.): sum both teams.
    Returns None if stat not found.
    """
    stat_key = MARKET_TO_STAT_KEY.get(market, market)

    total = 0.0
    found = False
    for team_id, stats in match_stats.items():
        if stat_key in stats:
            total += stats[stat_key]
            found = True

    return total if found else None


def extract_predicted_value(snapshot: dict) -> float | None:
    """Extract the predicted value from the decision snapshot.

    Uses the combined L10 average for the chosen market.
    """
    if not snapshot:
        return None

    # Try from team snapshots first
    chosen_market = snapshot.get("chosen_market", "")
    stat_key = MARKET_TO_STAT_KEY.get(chosen_market, chosen_market)

    team_a = snapshot.get("team_a_snapshot") or {}
    team_b = snapshot.get("team_b_snapshot") or {}

    # Get L10 averages
    a_l10 = team_a.get("l10_avg", {})
    b_l10 = team_b.get("l10_avg", {})

    a_val = a_l10.get(stat_key)
    b_val = b_l10.get(stat_key)

    if a_val is not None and b_val is not None:
        return round(a_val + b_val, 2)
    if a_val is not None:
        return round(a_val, 2)
    if b_val is not None:
        return round(b_val, 2)

    # Fallback: look in all_markets_considered for combined_avg
    for mkt in snapshot.get("all_markets_considered", []):
        if mkt.get("name") == chosen_market:
            avg = mkt.get("combined_avg")
            if avg is not None:
                return float(avg)

    return None


def did_line_hit(actual_value: float | None, line: float | None, direction: str) -> bool | None:
    """Check if the actual value hit the line in the predicted direction."""
    if actual_value is None or line is None:
        return None
    if direction == "OVER":
        return actual_value > line
    elif direction == "UNDER":
        return actual_value < line
    return None


def generate_pattern_tags(
    sport: str, market: str, competition: str,
    deviation_pct: float | None, result: str
) -> list[str]:
    """Generate searchable pattern tags for learning queries."""
    tags = [sport, market]
    if competition:
        tags.append(competition)
    if result:
        tags.append(result)
    if deviation_pct is not None:
        if deviation_pct > 15:
            tags.append("overestimate_large")
        elif deviation_pct > 5:
            tags.append("overestimate_small")
        elif deviation_pct < -15:
            tags.append("underestimate_large")
        elif deviation_pct < -5:
            tags.append("underestimate_small")
        else:
            tags.append("accurate")
    return tags


def check_existing_outcome(bet_id: int) -> bool:
    """Check if a decision outcome already exists for this bet."""
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import DecisionOutcomeRepo

        with get_db() as conn:
            repo = DecisionOutcomeRepo(conn)
            return repo.get_by_bet(bet_id) is not None
    except Exception:
        return False


def evaluate_settled_bets(betting_date: str, verbose: bool = False) -> list[dict]:
    """Evaluate all settled bets for a date against their predictions.

    For each settled bet with a decision_snapshot:
    1. Load actual match stats
    2. Compare predicted vs actual values
    3. Compute deviation
    4. Save decision_outcome

    Returns list of outcomes created.
    """
    from db_data_loader import load_decision_snapshot, save_decision_outcome

    settled = load_settled_bets_for_date(betting_date)
    if not settled:
        print(f"[evaluate] No settled bets found for {betting_date}")
        return []

    print(f"[evaluate] Found {len(settled)} settled bets for {betting_date}")

    outcomes = []
    skipped_no_snapshot = 0
    skipped_existing = 0
    skipped_no_stats = 0

    for bet in settled:
        bet_id = bet["bet_id"]

        # Skip if outcome already exists
        if check_existing_outcome(bet_id):
            skipped_existing += 1
            continue

        # Load decision snapshot
        snapshot = load_decision_snapshot(bet_id)
        if not snapshot:
            skipped_no_snapshot += 1
            if verbose:
                print(f"  [skip] Bet {bet_id} ({bet['event_name']}): no decision snapshot")
            continue

        # Load actual match stats
        match_stats = load_actual_match_stats(bet["fixture_id"])

        # Extract actual value for the chosen market
        actual_value = extract_actual_value(
            match_stats, snapshot["chosen_market"], bet["sport"]
        )

        # Extract predicted value from snapshot
        predicted_value = extract_predicted_value(snapshot)

        # Compute deviation
        deviation = None
        deviation_pct = None
        if actual_value is not None and predicted_value is not None and predicted_value != 0:
            deviation = round(actual_value - predicted_value, 2)
            deviation_pct = round((deviation / predicted_value) * 100, 1)

        # Check if line hit
        line_hit = did_line_hit(actual_value, snapshot.get("chosen_line"), snapshot.get("chosen_direction", ""))

        # Build prediction accuracy
        prediction_accuracy = {
            "predicted_l10_avg": predicted_value,
            "predicted_h2h_avg": None,
            "predicted_safety_score": snapshot.get("safety_score"),
            "actual_value": actual_value,
            "line": snapshot.get("chosen_line"),
            "direction": snapshot.get("chosen_direction"),
            "line_hit": line_hit,
        }
        # Try to get H2H average
        h2h = snapshot.get("h2h_snapshot") or {}
        h2h_avgs = h2h.get("averages", {})
        stat_key = MARKET_TO_STAT_KEY.get(snapshot["chosen_market"], snapshot["chosen_market"])
        if stat_key in h2h_avgs:
            prediction_accuracy["predicted_h2h_avg"] = h2h_avgs[stat_key]

        # Generate pattern tags
        pattern_tags = generate_pattern_tags(
            sport=bet["sport"],
            market=snapshot["chosen_market"],
            competition=bet.get("competition", ""),
            deviation_pct=deviation_pct,
            result=bet["status"],
        )

        # Build notes
        notes_parts = []
        if actual_value is None:
            notes_parts.append("actual_stats_unavailable")
            skipped_no_stats += 1
        if line_hit is True:
            notes_parts.append("line_hit")
        elif line_hit is False:
            notes_parts.append("line_missed")

        # Save outcome
        outcome_data = {
            "bet_id": bet_id,
            "fixture_id": bet["fixture_id"],
            "betting_date": betting_date,
            "sport": bet["sport"],
            "competition": bet.get("competition", ""),
            "market": snapshot["chosen_market"],
            "line": snapshot.get("chosen_line"),
            "direction": snapshot.get("chosen_direction", ""),
            "predicted_value": predicted_value,
            "actual_value": actual_value,
            "deviation": deviation,
            "deviation_pct": deviation_pct,
            "result": bet["status"],
            "prediction_accuracy": prediction_accuracy,
            "pattern_tags": pattern_tags,
            "notes": "; ".join(notes_parts) if notes_parts else "",
        }

        success = save_decision_outcome(outcome_data)
        if success:
            outcomes.append(outcome_data)
            if verbose:
                dev_str = f"dev={deviation:+.2f} ({deviation_pct:+.1f}%)" if deviation is not None else "no actual stats"
                print(f"  [{bet['status']}] {bet['event_name']} | {snapshot['chosen_market']} "
                      f"{snapshot.get('chosen_direction', '')} {snapshot.get('chosen_line', '')} | {dev_str}")

    # Summary
    print(f"[evaluate] Results: {len(outcomes)} outcomes created, "
          f"{skipped_no_snapshot} skipped (no snapshot), "
          f"{skipped_existing} skipped (existing), "
          f"{skipped_no_stats} without actual stats")

    return outcomes


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluate settled bets against predictions for decision learning"
    )
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Betting day YYYY-MM-DD to evaluate (default: today)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print per-bet evaluation details",
    )
    args = parser.parse_args()

    outcomes = evaluate_settled_bets(args.date, verbose=args.verbose)
    if outcomes:
        # Print quick stats
        with_actual = [o for o in outcomes if o.get("actual_value") is not None and o.get("deviation") is not None]
        if with_actual:
            avg_dev = sum(o["deviation"] for o in with_actual) / len(with_actual)
            print(f"\n[evaluate] Average deviation: {avg_dev:+.2f}")
            won = sum(1 for o in outcomes if o["result"] == "won")
            print(f"[evaluate] Results: {won} won / {len(outcomes) - won} lost")
