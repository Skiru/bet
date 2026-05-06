#!/usr/bin/env python3
"""Deterministic §3.0 safety score calculator for betting market ranking.

Given structured stats data (JSON), computes the §3.0 ranking table:
- Hit rates for OVER/UNDER per market
- Safety score = min(hit_rate_L10, hit_rate_H2H)
- Three-way cross-check (L10 + H2H + L5)
- Ranked market table with markdown output

Input: JSON file with team stats and available market data
Output: JSON with computed rankings + markdown table
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

try:
    from probability_engine import optimize_line
except ImportError:
    try:
        from scripts.probability_engine import optimize_line
    except ImportError:
        optimize_line = None

# Minimum markets required per sport
MIN_MARKETS = {
    "football": 4,  # fouls + cards + corners + shots
    "tennis": 3,
    "basketball": 3,
    "volleyball": 3,
    "hockey": 3,
    "baseball": 3,
    "esports": 3,
    "snooker": 3,
    "darts": 3,
    "handball": 3,
    "table_tennis": 3,
    "mma": 3,
    "padel": 3,
    "speedway": 2,
}

# Sport-specific H2H penalty — niche sports rarely have H2H data
H2H_MISSING_PENALTY = {
    "football": 0.70,     # 30% penalty — H2H expected
    "tennis": 0.70,       # 30% penalty — H2H expected
    "basketball": 0.70,   # 30% penalty — H2H expected
    "volleyball": 0.75,   # 25% penalty — H2H common but not universal
    "hockey": 0.75,       # 25% penalty
    "handball": 0.80,     # 20% penalty
    "baseball": 0.80,     # 20% penalty
    "esports": 0.85,      # 15% penalty — roster changes make H2H less relevant
    "snooker": 0.85,      # 15% penalty — individual sport
    "darts": 0.85,        # 15% penalty — individual sport
    "table_tennis": 0.85, # 15% penalty — individual sport
    "mma": 0.90,          # 10% penalty — rarely same matchup
    "padel": 0.90,        # 10% penalty — new sport, limited H2H
    "speedway": 0.90,     # 10% penalty — team sport but format varies
}

# Input JSON schema description (for --help)
INPUT_SCHEMA = """
Input JSON format:
{
  "sport": "football",
  "team_a": "Liverpool",
  "team_b": "Arsenal",
  "competition": "Premier League",
  "markets": [
    {
      "name": "Corners Total O/U",
      "line": 9.5,
      "team_a_l10": [11, 8, 13, ...],     // raw values per match (last 10)
      "team_b_l10": [6, 9, 8, ...],       // raw values per match (last 10)
      "h2h_values": [12, 9, 14, ...],     // combined values from H2H meetings
      "team_a_l5": [12, 7, 11, ...],      // recent form (last 5)
      "team_b_l5": [10, 5, 8, ...],       // recent form (last 5)
      "is_combined": true,                 // true=add team values, false=use as-is
      "source": "TotalCorner + SoccerStats"
    }
  ]
}

For combined markets (total corners, total fouls):
  - L10 combined = team_a_l10[i] + team_b_l10[i] for each match
For team-specific markets (team corners O/U, team shots):
  - L10 values = team_a_l10 only (team_b not used for hit rate)
"""


def validate_input(data: dict) -> list[str]:
    """Validate input JSON structure. Returns list of errors."""
    errors = []

    if "sport" not in data:
        errors.append("Missing required field: 'sport'")
    if "team_a" not in data:
        errors.append("Missing required field: 'team_a'")
    if "team_b" not in data:
        errors.append("Missing required field: 'team_b'")
    if "markets" not in data or not isinstance(data.get("markets"), list):
        errors.append("Missing or invalid 'markets' array")
        return errors

    for i, market in enumerate(data["markets"]):
        prefix = f"markets[{i}]"
        if "name" not in market:
            errors.append(f"{prefix}: missing 'name'")
        if "line" not in market:
            errors.append(f"{prefix}: missing 'line'")
        elif not isinstance(market["line"], (int, float)):
            errors.append(f"{prefix}: 'line' must be numeric")

        for field in ["team_a_l10", "team_b_l10"]:
            if field not in market:
                errors.append(f"{prefix}: missing '{field}'")
            elif not isinstance(market[field], list):
                errors.append(f"{prefix}: '{field}' must be an array")
            elif not all(isinstance(v, (int, float)) for v in market[field]):
                errors.append(f"{prefix}: '{field}' must contain only numbers")

        if "h2h_values" in market:
            if not isinstance(market["h2h_values"], list):
                errors.append(f"{prefix}: 'h2h_values' must be an array")
            elif not all(isinstance(v, (int, float)) for v in market["h2h_values"]):
                errors.append(f"{prefix}: 'h2h_values' must contain only numbers")

    return errors


def compute_combined_values(market: dict) -> list[float]:
    """Compute combined L10 values from team A + team B."""
    is_combined = market.get("is_combined", True)
    a_vals = market.get("team_a_l10", [])
    b_vals = market.get("team_b_l10", [])

    if is_combined:
        # Combined market: add corresponding values
        min_len = min(len(a_vals), len(b_vals))
        return [a_vals[i] + b_vals[i] for i in range(min_len)]
    else:
        # Team-specific market: use team A only
        return list(a_vals)


def compute_combined_l5(market: dict) -> list[float]:
    """Compute combined L5 values from team A + team B."""
    is_combined = market.get("is_combined", True)
    a_vals = market.get("team_a_l5") or market.get("team_a_l10", [])[-5:]
    b_vals = market.get("team_b_l5") or market.get("team_b_l10", [])[-5:]

    if is_combined:
        min_len = min(len(a_vals), len(b_vals))
        return [a_vals[i] + b_vals[i] for i in range(min_len)]
    else:
        return list(a_vals)


def compute_hit_rate(values: list[float], line: float, direction: str) -> tuple[int, int]:
    """Count how many values are over/under the line.

    Args:
        values: list of stat values
        line: the betting line (e.g., 9.5)
        direction: "OVER" or "UNDER"

    Returns: (hits, total)
    """
    if not values:
        return 0, 0

    hits = 0
    for v in values:
        if direction == "OVER" and v > line:
            hits += 1
        elif direction == "UNDER" and v < line:
            hits += 1

    return hits, len(values)


def infer_direction(avg: float, line: float) -> str:
    """Infer whether OVER or UNDER is the natural bet direction."""
    return "OVER" if avg > line else "UNDER"


def compute_margin(avg: float, line: float, direction: str) -> float:
    """Compute margin: how much the average exceeds the line.

    OVER: avg/line (>1 = margin exists)
    UNDER: line/avg (>1 = margin exists)
    """
    if line == 0:
        return 0.0
    if avg == 0:
        # avg=0 with line>0: infinite UNDER margin, cap at 2.0
        return 2.0 if direction == "UNDER" else 0.0
    if direction == "OVER":
        return round(avg / line, 3)
    else:
        return round(line / avg, 3)


def compute_safety_score(hit_rate_l10: float, hit_rate_h2h: float) -> float:
    """Safety = min(hit_rate_L10, hit_rate_H2H). Higher = safer."""
    return round(min(hit_rate_l10, hit_rate_h2h), 2)


def compute_three_way_check(
    l10_avg: float, h2h_avg: float, l5_avg: float, line: float
) -> dict:
    """Compute three-way cross-check alignment."""
    l10_dir = infer_direction(l10_avg, line)
    h2h_dir = infer_direction(h2h_avg, line) if h2h_avg > 0 else "N/A"
    l5_dir = infer_direction(l5_avg, line)

    # Determine trend from L5 vs L10
    if l5_avg > 0 and l10_avg > 0:
        pct_change = (l5_avg - l10_avg) / l10_avg * 100
        if pct_change > 5:
            trend = "UP"
        elif pct_change < -5:
            trend = "DOWN"
        else:
            trend = "STABLE"
    else:
        trend = "N/A"

    # Count support
    primary_dir = l10_dir
    support_count = 1  # L10 always supports itself
    h2h_missing = h2h_dir == "N/A"

    directions = [l10_dir]
    if h2h_dir != "N/A":
        directions.append(h2h_dir)
        if h2h_dir == primary_dir:
            support_count += 1
    if l5_dir == primary_dir:
        support_count += 1
    directions.append(l5_dir)

    total = len([d for d in [l10_dir, h2h_dir, l5_dir] if d != "N/A"])
    if total == 0:
        alignment = "N/A"
    elif support_count == total:
        alignment = f"{total}/{total} SUPPORT"
    elif support_count >= 2:
        alignment = f"{support_count}/{total} SUPPORT"
    else:
        conflicts = total - support_count
        if conflicts >= total:
            alignment = f"{total}/{total} CONFLICT → REJECT"
        else:
            alignment = f"{support_count}/{total} CONFLICT → DOWNGRADE"

    # Mark when H2H is missing so alignment doesn't mask incomplete data
    if h2h_missing:
        alignment += " (H2H N/A)"

    return {
        "l10_avg": round(l10_avg, 2),
        "h2h_avg": round(h2h_avg, 2) if h2h_avg > 0 else None,
        "l5_avg": round(l5_avg, 2),
        "line": line,
        "l10_direction": l10_dir,
        "h2h_direction": h2h_dir,
        "l5_trend": trend,
        "alignment": alignment,
    }


def rank_markets(data: dict) -> dict:
    """Compute safety scores and rank all markets for a candidate."""
    sport = data["sport"].lower()
    team_a = data["team_a"]
    team_b = data["team_b"]
    competition = data.get("competition", "")
    markets = data.get("markets", [])

    results = []

    for market in markets:
        name = market["name"]
        line = market["line"]
        source = market.get("source", "")

        # Compute combined L10 values
        l10_values = compute_combined_values(market)
        l10_avg = statistics.mean(l10_values) if l10_values else 0.0

        # Compute team averages
        team_a_avg = statistics.mean(market.get("team_a_l10", [])) if market.get("team_a_l10") else 0.0
        team_b_avg = statistics.mean(market.get("team_b_l10", [])) if market.get("team_b_l10") else 0.0

        # Swap display labels for Team B-only markets
        team_swapped = market.get("team_swapped", False)
        display_a_avg = team_b_avg if team_swapped else team_a_avg
        display_b_avg = team_a_avg if team_swapped else team_b_avg

        # H2H values
        h2h_values = market.get("h2h_values", [])
        h2h_avg = statistics.mean(h2h_values) if h2h_values else 0.0

        # L5 values
        l5_values = compute_combined_l5(market)
        l5_avg = statistics.mean(l5_values) if l5_values else 0.0

        # Infer direction
        direction = infer_direction(l10_avg, line)

        # Compute hit rates
        hits_l10, total_l10 = compute_hit_rate(l10_values, line, direction)
        hits_h2h, total_h2h = compute_hit_rate(h2h_values, line, direction)
        hits_l5, total_l5 = compute_hit_rate(l5_values, line, direction)

        # Hit rates as fractions
        rate_l10 = hits_l10 / total_l10 if total_l10 > 0 else 0.0
        rate_h2h = hits_h2h / total_h2h if total_h2h > 0 else 0.0

        # Safety score
        if total_h2h > 0:
            safety = compute_safety_score(rate_l10, rate_h2h)
        else:
            penalty = H2H_MISSING_PENALTY.get(sport, 0.75)
            safety = round(rate_l10 * penalty, 2)

        # ONE-SIDED penalty: when one team has zero data in a combined market,
        # the safety score is less reliable — apply 0.70 penalty (same as H2H-missing)
        one_sided = market.get("one_sided", False)
        if one_sided:
            safety = round(safety * 0.70, 2)

        # Margin
        margin = compute_margin(l10_avg, line, direction)

        # Compute three-way check per market
        tw_l10_a = statistics.mean(l10_values) if l10_values else 0.0
        tw_h2h_a = statistics.mean(h2h_values) if h2h_values else 0.0
        tw_l5_a = statistics.mean(l5_values) if l5_values else 0.0
        per_market_three_way = compute_three_way_check(tw_l10_a, tw_h2h_a, tw_l5_a, line)

        results.append({
            "name": name,
            "team_a_avg": round(display_a_avg, 2),
            "team_b_avg": round(display_b_avg, 2),
            "combined_avg": round(l10_avg, 2),
            "h2h_avg": round(h2h_avg, 2) if h2h_values else None,
            "line": line,
            "direction": direction,
            "hit_rate_l10": f"{hits_l10}/{total_l10}",
            "hit_rate_h2h": f"{hits_h2h}/{total_h2h}" if total_h2h > 0 else "N/A",
            "hit_rate_l5": f"{hits_l5}/{total_l5}" if total_l5 > 0 else "N/A",
            "safety_score": safety,
            "margin": margin,
            "source": source,
            "h2h_blind": total_h2h == 0,
            "one_sided": one_sided,
            "three_way_check": per_market_three_way,
        })

    # --- Multi-line optimization (Task 7.1) ---
    # If a market has available_lines data, optimize to find best line
    for r in results:
        mkt = next((m for m in markets if m["name"] == r["name"]), None)
        available_lines = mkt.get("available_lines") if mkt else None
        if available_lines and optimize_line is not None:
            combined_vals = compute_combined_values(mkt) if mkt else []
            avg_val = statistics.mean(combined_vals) if combined_vals else r["combined_avg"]
            std_val = statistics.stdev(combined_vals) if len(combined_vals) >= 2 else 0.0
            # Infer model: goals/corners/cards → poisson; points/totals → normal
            name_lower = r["name"].lower()
            if any(kw in name_lower for kw in ("point", "total", "score")):
                mdl = "normal"
            else:
                mdl = "poisson"
            opt = optimize_line(
                base_stat=name_lower,
                avg_value=avg_val,
                std_dev=std_val,
                available_lines=available_lines,
                model=mdl,
            )
            if opt.get("best_line") is not None:
                r["optimized_line"] = opt["best_line"]
                r["optimized_direction"] = opt["direction"]
                r["optimized_prob"] = opt["prob"]
                r["optimized_ev"] = opt["ev"]
                r["optimized_safety"] = opt["safety_score"]
                # Use optimized safety if it's better than the hit-rate safety
                if opt["ev"] is not None and opt["ev"] > 0 and opt["safety_score"] > r["safety_score"]:
                    r["safety_score"] = opt["safety_score"]
                    r["line"] = opt["best_line"]
                    r["direction"] = opt["direction"].upper()

    # Sort by safety score (desc), margin as tiebreaker (desc)
    results.sort(key=lambda x: (x["safety_score"], x["margin"]), reverse=True)

    # Add rank
    for i, r in enumerate(results, 1):
        r["rank"] = i

    # Best market
    best = results[0] if results else None

    # Three-way cross-check for best market
    three_way = None
    if best:
        best_market = next(
            (m for m in markets if m["name"] == best["name"]), None
        )
        if best_market:
            l10_vals = compute_combined_values(best_market)
            l5_vals = compute_combined_l5(best_market)
            h2h_vals = best_market.get("h2h_values", [])

            l10_a = statistics.mean(l10_vals) if l10_vals else 0.0
            h2h_a = statistics.mean(h2h_vals) if h2h_vals else 0.0
            l5_a = statistics.mean(l5_vals) if l5_vals else 0.0

            three_way = compute_three_way_check(l10_a, h2h_a, l5_a, best["line"])
            three_way["market"] = best["name"]

    # Check minimum markets
    min_required = MIN_MARKETS.get(sport, 3)
    warnings = []
    if len(results) < min_required:
        warnings.append(
            f"INSUFFICIENT_MARKETS: {len(results)} markets evaluated, "
            f"minimum {min_required} required for {sport}"
        )

    return {
        "candidate": f"{team_a} vs {team_b}",
        "sport": sport,
        "competition": competition,
        "markets_evaluated": len(results),
        "min_required": min_required,
        "ranking": results,
        "three_way_check": three_way,
        "recommended_market": (
            f"{best['name']} {best['line']} ({best['direction']})"
            if best
            else None
        ),
        "recommended_safety": best["safety_score"] if best else None,
        "warnings": warnings,
        "markdown_ranking_table": generate_ranking_markdown(results),
        "markdown_three_way_table": generate_three_way_markdown(three_way) if three_way else "",
    }


def generate_ranking_markdown(ranking: list[dict]) -> str:
    """Generate §S3.3-compatible markdown ranking table."""
    lines = []
    lines.append(
        "| # | Market | TeamA avg | TeamB avg | H2H avg | Line | "
        "Hit L10 | Hit H2H | Safety | Source |"
    )
    lines.append(
        "|---|--------|-----------|-----------|---------|------|"
        "---------|---------|--------|--------|"
    )

    for r in ranking:
        h2h = f"{r['h2h_avg']}" if r["h2h_avg"] is not None else "N/A (H2H-BLIND)"
        lines.append(
            f"| {r['rank']} | {r['name']} | {r['team_a_avg']} | {r['team_b_avg']} | "
            f"{h2h} | {r['line']} | {r['hit_rate_l10']} | {r['hit_rate_h2h']} | "
            f"{r['safety_score']:.2f} | {r['source']} |"
        )

    if ranking:
        best = ranking[0]
        lines.append(
            f"SELECTED MARKET: Row {best['rank']} — {best['name']} "
            f"(highest safety score: {best['safety_score']:.2f})"
        )

    return "\n".join(lines)


def generate_three_way_markdown(tw: dict) -> str:
    """Generate §S3.4-compatible three-way cross-check table."""
    lines = []
    lines.append(
        "| Check | Value | vs Line | Hit Rate | Direction |"
    )
    lines.append(
        "|-------|-------|---------|----------|-----------|"
    )

    lines.append(
        f"| L10 avg | {tw['l10_avg']} | {tw['l10_direction']} {tw['line']} | — | "
        f"{'SUPPORTS' if 'SUPPORT' in tw['alignment'] else 'CONFLICTS'} |"
    )

    h2h_val = tw["h2h_avg"] if tw["h2h_avg"] is not None else "N/A"
    h2h_dir = tw["h2h_direction"]
    lines.append(
        f"| H2H avg | {h2h_val} | {h2h_dir} {tw['line']} | — | "
        f"{'SUPPORTS' if h2h_dir == tw['l10_direction'] else 'CONFLICTS'} |"
    )

    lines.append(
        f"| L5 trend | {tw['l5_avg']} | {tw['l5_trend']} | — | "
        f"{tw['l5_trend']} |"
    )

    lines.append(f"ALIGNMENT: {tw['alignment']}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Compute §3.0 safety score ranking from structured stats data.",
        epilog=INPUT_SCHEMA,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to JSON file with structured stats data",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Output markdown tables only (for pasting into S3 output)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate input structure only, don't compute",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(json.dumps({"error": f"File not found: {args.input}"}), file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}), file=sys.stderr)
        sys.exit(1)

    # Validate input
    errors = validate_input(data)
    if errors:
        print(json.dumps({"validation_errors": errors}, indent=2), file=sys.stderr)
        sys.exit(1)

    if args.validate_only:
        print(json.dumps({"status": "VALID", "markets": len(data.get("markets", []))}))
        sys.exit(0)

    # Compute rankings
    result = rank_markets(data)

    if args.markdown:
        print(result["markdown_ranking_table"])
        if result["markdown_three_way_table"]:
            print()
            print(result["markdown_three_way_table"])
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))

    # Exit with warning if insufficient markets
    if result["warnings"]:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
