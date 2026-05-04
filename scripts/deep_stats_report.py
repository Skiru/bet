#!/usr/bin/env python3
"""Deep Stats Report Generator (S3) — per-candidate 10-section statistical analysis.

For each candidate in the analysis pool or shortlist, reads the stats cache,
computes per-market safety rankings via compute_safety_scores.rank_markets(),
and generates a structured markdown report with all 10 required sections
(§S3.1–§S3.10).

Usage:
    python3 scripts/deep_stats_report.py --date 2026-05-01
    python3 scripts/deep_stats_report.py --date 2026-05-01 --shortlist betting/data/20260501_s2_shortlist.json
    python3 scripts/deep_stats_report.py --date 2026-05-01 --top 50
"""

import argparse
import concurrent.futures
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from scripts.normalize_stats import build_safety_input_from_cache, SPORT_STAT_KEYS
    from scripts.compute_safety_scores import rank_markets
except ImportError:
    from normalize_stats import build_safety_input_from_cache, SPORT_STAT_KEYS
    from compute_safety_scores import rank_markets

try:
    from db_data_loader import load_team_form_from_db
except ImportError:
    from scripts.db_data_loader import load_team_form_from_db

DATA_DIR = Path(__file__).parent.parent / "betting" / "data"
CACHE_DIR = Path(__file__).parent.parent / "betting" / "data" / "stats_cache"

# Stats where home+away should NOT be summed (percentages, not counts)
_PERCENTAGE_STATS = {"possession", "shot_accuracy", "pass_accuracy", "cross_accuracy",
                     "long_ball_accuracy", "tackle_accuracy"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    """Convert team/player name to filesystem-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_avg(values: list) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float))]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------

def extract_team_stats(sport: str, team_name: str) -> dict:
    """Read stats for a single team (DB-first, cache fallback).

    Returns dict with keys: team, sport, l10_avg, l5_avg, l10_matches,
    sources, raw_cache. Returns empty markers if no data found.
    """
    slug = slugify(team_name)

    result = {
        "team": team_name,
        "sport": sport,
        "slug": slug,
        "l10_avg": {},
        "l5_avg": {},
        "l10_matches": [],
        "sources": [],
        "has_data": False,
        "raw_cache": None,
    }

    # Try cache file first (respects CACHE_DIR override in tests and
    # is the primary source for enriched API data)
    cache = None
    cache_file = CACHE_DIR / sport / f"{slug}.json"
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # DB fallback — only if no cache file found
    if cache is None:
        try:
            db_data = load_team_form_from_db(team_name, sport)
            if db_data and isinstance(db_data, dict):
                form_section = db_data.get("form", {})
                # DB-format: form[stat_key] = {l10_avg: float, l5_avg: float, ...}
                # Cache-format: form = {l10_avg: {stat_key: float}, l5_avg: {stat_key: float}}
                # Convert DB-format to cache-format if needed.
                first_val = next(iter(form_section.values()), None) if form_section else None
                if isinstance(first_val, dict) and "l10_avg" in first_val:
                    # DB format detected — convert to cache format
                    converted = {"l10_avg": {}, "l5_avg": {}, "l10_matches": [], "sources": []}
                    for stat_key, stat_data in form_section.items():
                        if isinstance(stat_data, dict):
                            if stat_data.get("l10_avg") is not None:
                                converted["l10_avg"][stat_key] = stat_data["l10_avg"]
                            if stat_data.get("l5_avg") is not None:
                                converted["l5_avg"][stat_key] = stat_data["l5_avg"]
                            if stat_data.get("l10_values"):
                                for i, val in enumerate(stat_data["l10_values"]):
                                    if i >= len(converted["l10_matches"]):
                                        converted["l10_matches"].append({})
                                    converted["l10_matches"][i][stat_key] = val
                    cache = {"team": team_name, "sport": sport, "form": converted, "sources": db_data.get("sources", ["db"])}
                    print(f"  [db] Converted DB-format stats for {team_name} ({sport}): {len(converted['l10_avg'])} stat keys")
                elif isinstance(form_section.get("l10_avg"), dict) or "l10_matches" in form_section:
                    # Already in cache format
                    cache = db_data
        except Exception:
            pass

    if cache is None:
        return result

    result["raw_cache"] = cache
    result["has_data"] = True
    result["sources"] = cache.get("sources", [])

    form = cache.get("form", {})
    stat_keys = SPORT_STAT_KEYS.get(sport, [])

    # Extract L10 averages
    # Cache may store keys as "corners" (bare) or "corners_home"/"corners_away" (split)
    # For split keys: sum home+away for additive stats (corners, fouls, cards, shots, goals),
    # but keep home-only for percentage stats (possession) where sum is meaningless.
    l10_avg = form.get("l10_avg", {})
    l5_avg = form.get("l5_avg", {})
    for key in stat_keys:
        if key in l10_avg:
            result["l10_avg"][key] = l10_avg[key]
        elif f"{key}_home" in l10_avg:
            home_val = l10_avg.get(f"{key}_home", 0)
            away_val = l10_avg.get(f"{key}_away", 0)
            if key in _PERCENTAGE_STATS:
                result["l10_avg"][key] = home_val
            else:
                result["l10_avg"][key] = round(home_val + away_val, 2) if isinstance(home_val, (int, float)) else home_val
            result["l10_avg"][f"{key}_home"] = home_val
            result["l10_avg"][f"{key}_away"] = away_val
        if key in l5_avg:
            result["l5_avg"][key] = l5_avg[key]
        elif f"{key}_home" in l5_avg:
            home_val = l5_avg.get(f"{key}_home", 0)
            away_val = l5_avg.get(f"{key}_away", 0)
            if key in _PERCENTAGE_STATS:
                result["l5_avg"][key] = home_val
            else:
                result["l5_avg"][key] = round(home_val + away_val, 2) if isinstance(home_val, (int, float)) else home_val
            result["l5_avg"][f"{key}_home"] = home_val
            result["l5_avg"][f"{key}_away"] = away_val

    # Extract L10 match-by-match data
    l10 = form.get("l10_matches", form.get("recent_matches", []))
    result["l10_matches"] = l10[:10] if l10 else []

    return result


def extract_h2h_stats(sport: str, team_a: str, team_b: str) -> dict:
    """Extract H2H stats from team_a's cache looking up team_b.

    Returns dict with keys: meetings (list), averages (dict per stat),
    has_data (bool).
    """
    slug_a = slugify(team_a)
    slug_b = slugify(team_b)
    cache_file = CACHE_DIR / sport / f"{slug_a}.json"

    result = {
        "team_a": team_a,
        "team_b": team_b,
        "meetings": [],
        "averages": {},
        "has_data": False,
    }

    if not cache_file.exists():
        return result

    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return result

    h2h_section = cache.get("h2h", {})
    # Try exact slug, then fuzzy match
    h2h_data = h2h_section.get(slug_b)
    if not h2h_data:
        # Try matching by partial name
        for key, val in h2h_section.items():
            if slug_b in key or key in slug_b:
                h2h_data = val
                break

    if not h2h_data:
        return result

    meetings = h2h_data.get("matches", [])
    if not meetings:
        return result

    result["has_data"] = True
    result["meetings"] = meetings

    # Compute averages from h2h_data directly if available
    avg = h2h_data.get("avg", {})
    if avg:
        result["averages"] = avg
    else:
        # Compute from meetings
        stat_keys = SPORT_STAT_KEYS.get(sport, [])
        accum: dict[str, list] = {k: [] for k in stat_keys}
        for m in meetings:
            stats = m.get("stats", m)
            for key in stat_keys:
                if key in stats:
                    val = stats[key]
                    if isinstance(val, (int, float)):
                        accum[key].append(val)
                    elif isinstance(val, dict):
                        total = sum(v for v in val.values() if isinstance(v, (int, float)))
                        accum[key].append(total)
                # Also check for _total variants (fallback when base key has no data)
                total_key = f"{key}_total"
                if total_key in stats and not accum[key]:
                    val = stats[total_key]
                    if isinstance(val, (int, float)):
                        accum[key].append(val)

        for key, vals in accum.items():
            avg_val = _safe_avg(vals)
            if avg_val is not None:
                result["averages"][key] = avg_val

    return result


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_s31_h2h(sport: str, h2h: dict) -> str:
    """§S3.1 H2H Analysis (market-specific)."""
    lines = ["§S3.1 H2H Analysis (market-specific)"]

    if not h2h["has_data"]:
        lines.append("⚠️ NO H2H DATA AVAILABLE — H2H-blind analysis")
        lines.append("")
        return "\n".join(lines)

    stat_keys = SPORT_STAT_KEYS.get(sport, [])
    # Build header from available stats in meetings
    available_stats = []
    for key in stat_keys:
        if key in h2h["averages"]:
            available_stats.append(key)

    if not available_stats:
        lines.append("⚠️ H2H meetings found but no stat breakdowns available")
        lines.append("")
        return "\n".join(lines)

    header = "| Meeting | Date |"
    separator = "|---------|------|"
    for stat in available_stats:
        label = stat.replace("_", " ").title()
        header += f" {label} |"
        separator += f"{'---' * max(len(label) // 3, 1)}---|"

    lines.append(header)
    lines.append(separator)

    for i, meeting in enumerate(h2h["meetings"][:10], 1):
        date = meeting.get("date", "N/A")
        stats = meeting.get("stats", meeting)
        row = f"| {i} | {date} |"
        for stat in available_stats:
            val = stats.get(stat, stats.get(f"{stat}_total", "N/A"))
            if isinstance(val, dict):
                val = sum(v for v in val.values() if isinstance(v, (int, float)))
            row += f" {val} |"
        lines.append(row)

    # Averages summary
    avg_parts = []
    for stat in available_stats:
        avg_val = h2h["averages"].get(stat, "N/A")
        label = stat.replace("_", " ")
        avg_parts.append(f"H2H avg {label}: {avg_val}")
    lines.append(" | ".join(avg_parts) + " | Status: ✅ H2H DATA AVAILABLE")
    lines.append("")
    return "\n".join(lines)


def _build_s32_form(sport: str, stats_a: dict, stats_b: dict) -> str:
    """§S3.2 Form & Stats Table."""
    lines = ["§S3.2 Form & Stats Table"]
    stat_keys = SPORT_STAT_KEYS.get(sport, [])

    team_a = stats_a["team"]
    team_b = stats_b["team"]

    if not stats_a["has_data"] and not stats_b["has_data"]:
        lines.append("⚠️ NO CACHE DATA — requires manual analysis")
        lines.append("")
        return "\n".join(lines)

    header = f"| Stat | {team_a} L10 | {team_a} L5 | {team_b} L10 | {team_b} L5 | Combined L10 |"
    sep = "|------|" + "------|" * 5
    lines.append(header)
    lines.append(sep)

    for key in stat_keys:
        label = key.replace("_", " ").title()
        a_l10 = stats_a["l10_avg"].get(key, "N/A")
        a_l5 = stats_a["l5_avg"].get(key, "N/A")
        b_l10 = stats_b["l10_avg"].get(key, "N/A")
        b_l5 = stats_b["l5_avg"].get(key, "N/A")

        if isinstance(a_l10, (int, float)) and isinstance(b_l10, (int, float)):
            combined = round(a_l10 + b_l10, 2)
        else:
            combined = "N/A"

        lines.append(f"| {label} | {a_l10} | {a_l5} | {b_l10} | {b_l5} | {combined} |")

    lines.append("")
    return "\n".join(lines)


def _build_s33_ranking(ranking_result: dict) -> str:
    """§S3.3 Market Ranking (§3.0) with probability columns."""
    lines = ["§S3.3 Market Ranking (§3.0)"]

    ranking = ranking_result.get("ranking", [])
    if not ranking:
        lines.append("⚠️ No markets could be ranked — insufficient data")
        lines.append("")
        return "\n".join(lines)

    # Check if probability data is available (enriched by probability_engine)
    has_prob = any(mkt.get("probability") is not None for mkt in ranking)

    if has_prob:
        lines.append("| Rank | Market | Line | Dir | L10 Avg | H2H Avg | Hit L10 | Hit H2H | Safety | P(hit) | Fair Odds | Min EV>0 |")
        lines.append("|------|--------|------|-----|---------|---------|---------|---------|--------|--------|-----------|----------|")
    else:
        lines.append("| Rank | Market | Line | Direction | L10 Avg | H2H Avg | Hit L10 | Hit H2H | Safety |")
        lines.append("|------|--------|------|-----------|---------|---------|---------|---------|--------|")

    for mkt in ranking:
        h2h_avg = mkt.get("h2h_avg")
        h2h_display = f"{h2h_avg}" if h2h_avg is not None else "N/A"
        hit_h2h = mkt.get("hit_rate_h2h", "N/A")

        if has_prob:
            prob = mkt.get("probability")
            fair = mkt.get("fair_odds")
            min_ev = mkt.get("min_odds_ev0")
            prob_str = f"{prob:.0%}" if prob is not None else "N/A"
            fair_str = f"{fair:.2f}" if fair is not None else "N/A"
            min_ev_str = f"≥{min_ev:.2f}" if min_ev is not None else "N/A"
            lines.append(
                f"| {mkt['rank']} | {mkt['name']} | {mkt['line']} | {mkt['direction']} "
                f"| {mkt['combined_avg']} | {h2h_display} | {mkt['hit_rate_l10']} "
                f"| {hit_h2h} | {mkt['safety_score']} | {prob_str} | {fair_str} | {min_ev_str} |"
            )
        else:
            lines.append(
                f"| {mkt['rank']} | {mkt['name']} | {mkt['line']} | {mkt['direction']} "
                f"| {mkt['combined_avg']} | {h2h_display} | {mkt['hit_rate_l10']} "
                f"| {hit_h2h} | {mkt['safety_score']} |"
            )

    warnings = ranking_result.get("warnings", [])
    if warnings:
        for w in warnings:
            lines.append(f"⚠️ {w}")

    lines.append("")
    return "\n".join(lines)


def _build_s34_threeway(ranking_result: dict, best_market: dict | None) -> str:
    """§S3.4 Three-Way Cross-Check."""
    lines = ["§S3.4 Three-Way Cross-Check"]

    tw = ranking_result.get("three_way_check")
    if not tw or not best_market:
        lines.append("⚠️ Cannot compute three-way check — insufficient data")
        lines.append("")
        return "\n".join(lines)

    line = tw.get("line", best_market.get("line", "N/A"))
    direction = best_market.get("direction", "N/A")

    lines.append("| Check | Value | vs Line | Supports? |")
    lines.append("|-------|-------|---------|-----------|")

    l10_avg = tw.get("l10_avg", 0)
    l10_dir = tw.get("l10_direction", "N/A")
    l10_support = "✅" if l10_dir == direction else "❌"
    lines.append(f"| L10 avg | {l10_avg} | {line} | {l10_support} {l10_dir} |")

    h2h_avg = tw.get("h2h_avg")
    h2h_dir = tw.get("h2h_direction", "N/A")
    if h2h_avg is not None:
        h2h_support = "✅" if h2h_dir == direction else "❌"
        lines.append(f"| H2H avg | {h2h_avg} | {line} | {h2h_support} {h2h_dir} |")
    else:
        lines.append(f"| H2H avg | N/A | {line} | ⚠️ NO H2H DATA |")

    l5_avg = tw.get("l5_avg", 0)
    l5_trend = tw.get("l5_trend", "N/A")
    l5_dir = "OVER" if l5_avg > line else "UNDER" if line != 0 else "N/A"
    l5_support = "✅" if l5_dir == direction else "❌"
    lines.append(f"| L5 trend | {l5_avg} | {line} | {l5_support} {l5_dir} ({l5_trend}) |")

    alignment = tw.get("alignment", "N/A")
    emoji = "✅" if "SUPPORT" in str(alignment) and "CONFLICT" not in str(alignment) else "⚠️"
    lines.append(f"Alignment: {emoji} {alignment}")
    lines.append("")
    return "\n".join(lines)


def _build_s35_coach(stats_a: dict, stats_b: dict) -> str:
    """§S3.5 Coach/Roster Stability."""
    lines = ["§S3.5 Coach/Roster Stability"]

    for label, stats in [("Team A", stats_a), ("Team B", stats_b)]:
        team = stats.get("team", label)
        cache = stats.get("raw_cache") or {}

        # Check for coach/formation data in cache
        coach = cache.get("coach") or cache.get("manager")
        formation = cache.get("formation") or cache.get("tactical_formation")

        if coach:
            lines.append(f"- {team}: Coach = {coach}")

        if formation:
            lines.append(f"- {team}: Formation = {formation}")

        # Check formation changes in recent matches
        matches = stats.get("l10_matches", [])
        formations = [m.get("formation") for m in matches if m.get("formation")]
        if formations:
            unique = set(formations)
            if len(unique) > 2:
                lines.append(f"- {team}: ⚠ {len(unique)} different formations in L10 — tactical instability")
            elif len(unique) == 1:
                lines.append(f"- {team}: Consistent formation ({formations[0]})")
            else:
                lines.append(f"- {team}: {len(unique)} formations used in L10")

        if not coach and not formations:
            lines.append(f"- {team}: No coach/formation data available — verify manually")

    lines.append("")
    return "\n".join(lines)


def _build_s36_injury(stats_a: dict, stats_b: dict) -> str:
    """§S3.6 Injury/Suspension Check."""
    lines = ["§S3.6 Injury/Suspension Check"]

    for label, stats in [("Team A", stats_a), ("Team B", stats_b)]:
        team = stats.get("team", label)
        cache = stats.get("raw_cache") or {}

        injuries = cache.get("injuries") or cache.get("unavailable") or []
        suspensions = cache.get("suspensions") or []

        if injuries:
            lines.append(f"- {team}: {len(injuries)} injured — {', '.join(str(i) for i in injuries[:5])}")
        if suspensions:
            lines.append(f"- {team}: {len(suspensions)} suspended — {', '.join(str(s) for s in suspensions[:5])}")
        if not injuries and not suspensions:
            lines.append(f"- {team}: No injury data in cache — verify on Flashscore/Sofascore before placing bet")

    lines.append("")
    return "\n".join(lines)


def _build_s37_top3(ranking_result: dict) -> str:
    """§S3.7 Top 3 Markets."""
    lines = ["§S3.7 Top 3 Markets"]
    ranking = ranking_result.get("ranking", [])

    if not ranking:
        lines.append("⚠️ No markets available")
        lines.append("")
        return "\n".join(lines)

    for mkt in ranking[:3]:
        h2h_str = f", H2H {mkt['h2h_avg']}" if mkt.get("h2h_avg") is not None else ""
        lines.append(
            f"{mkt['rank']}. {mkt['name']} {mkt['direction'][0]}{mkt['line']} — "
            f"Safety {mkt['safety_score']}, L10 avg {mkt['combined_avg']}{h2h_str}"
        )

    lines.append("")
    return "\n".join(lines)


def _build_s38_recommended(ranking_result: dict) -> str:
    """§S3.8 Recommended Market with probability data."""
    lines = ["§S3.8 Recommended Market"]
    ranking = ranking_result.get("ranking", [])
    tw = ranking_result.get("three_way_check")

    if not ranking:
        lines.append("⚠️ No markets to recommend")
        lines.append("")
        return "\n".join(lines)

    best = ranking[0]
    h2h_avg = best.get("h2h_avg")
    name = f"{best['name']} {best['direction'][0]}{best['line']}"

    desc = f"{name} (Safety {best['safety_score']}) — Highest safety score from §S3.3."

    l10_avg = best["combined_avg"]
    line = best["line"]
    if line > 0:
        l10_margin = round((l10_avg - line) / line * 100, 1)
        desc += f" L10 avg ({l10_avg}) vs line ({line}): {'+' if l10_margin >= 0 else ''}{l10_margin}% margin."

    if h2h_avg is not None and line > 0:
        h2h_margin = round((h2h_avg - line) / line * 100, 1)
        desc += f" H2H avg ({h2h_avg}): {'+' if h2h_margin >= 0 else ''}{h2h_margin}% margin."

    # Add probability data if available
    prob = best.get("probability")
    fair_odds = best.get("fair_odds")
    if prob is not None and fair_odds is not None:
        desc += f"\n**Probability model:** P(hit)={prob:.1%}, fair odds={fair_odds:.2f}."
        desc += f" Bet if Betclic odds ≥{fair_odds:.2f} (EV>0 threshold)."
        ci_lower = best.get("ci_lower")
        ci_upper = best.get("ci_upper")
        if ci_lower is not None and ci_upper is not None:
            desc += f" 90% CI: [{ci_lower:.1%}–{ci_upper:.1%}]."
        model = best.get("model_used", "poisson")
        lam = best.get("lambda")
        if lam is not None:
            desc += f" λ={lam:.2f} ({model})."

    lines.append(desc)
    lines.append("")
    return "\n".join(lines)


def _build_s39_sources(stats_a: dict, stats_b: dict) -> str:
    """§S3.9 Sources Used."""
    lines = ["§S3.9 Sources Used"]
    lines.append("| Source | Data Type |")
    lines.append("|--------|-----------|")

    all_sources = set(stats_a.get("sources", []) + stats_b.get("sources", []))
    if all_sources:
        for src in sorted(all_sources):
            lines.append(f"| Stats cache ({src}) | L10, L5, H2H statistics |")
    else:
        lines.append("| Stats cache | L10, L5, H2H statistics |")

    lines.append("| compute_safety_scores.py | Safety score calculation |")
    lines.append("")
    return "\n".join(lines)


def _build_s310_depth(stats_a: dict, stats_b: dict, h2h: dict, ranking_result: dict) -> str:
    """§S3.10 Analysis Depth Proof."""
    lines = ["§S3.10 Analysis Depth Proof"]
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")

    l10_a = len(stats_a.get("l10_matches", []))
    l10_b = len(stats_b.get("l10_matches", []))
    h2h_count = len(h2h.get("meetings", []))
    markets_ranked = len(ranking_result.get("ranking", []))

    ranking = ranking_result.get("ranking", [])
    if ranking:
        scores = [m["safety_score"] for m in ranking]
        score_range = f"{min(scores):.2f}-{max(scores):.2f}"
    else:
        score_range = "N/A"

    lines.append(f"| L10 matches analyzed ({stats_a['team']}) | {l10_a} |")
    lines.append(f"| L10 matches analyzed ({stats_b['team']}) | {l10_b} |")
    lines.append(f"| H2H meetings found | {h2h_count} |")
    lines.append(f"| Markets ranked | {markets_ranked} |")
    lines.append(f"| Safety score range | {score_range} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def analyze_candidate(
    sport: str,
    home: str,
    away: str,
    competition: str,
    kickoff: str,
) -> dict:
    """Perform full S3 deep statistical analysis for one candidate.

    Returns dict with:
      - sport, home, away, competition, kickoff
      - ranking_result: raw output from rank_markets()
      - stats_a, stats_b: extracted team stats
      - h2h: extracted H2H stats
      - sections: dict of §S3.1–§S3.10 markdown strings
      - markdown: full combined markdown for this candidate
      - has_data: whether any useful stats were found
    """
    stats_a = extract_team_stats(sport, home)
    stats_b = extract_team_stats(sport, away)
    h2h = extract_h2h_stats(sport, home, away)

    # Build safety input and rank markets
    ranking_result = {}
    safety_input = build_safety_input_from_cache(sport, home, away, competition)
    if safety_input and safety_input.get("markets"):
        ranking_result = rank_markets(safety_input)
    else:
        ranking_result = {
            "ranking": [],
            "three_way_check": None,
            "recommended_market": None,
            "recommended_safety": None,
            "warnings": ["NO_STATS_DATA: Could not build safety input from cache"],
            "markdown_ranking_table": "",
            "markdown_three_way_table": "",
            "markets_evaluated": 0,
            "min_required": 3,
        }

    best_market = ranking_result["ranking"][0] if ranking_result.get("ranking") else None

    # Build all 10 sections
    sections = {
        "s31": _build_s31_h2h(sport, h2h),
        "s32": _build_s32_form(sport, stats_a, stats_b),
        "s33": _build_s33_ranking(ranking_result),
        "s34": _build_s34_threeway(ranking_result, best_market),
        "s35": _build_s35_coach(stats_a, stats_b),
        "s36": _build_s36_injury(stats_a, stats_b),
        "s37": _build_s37_top3(ranking_result),
        "s38": _build_s38_recommended(ranking_result),
        "s39": _build_s39_sources(stats_a, stats_b),
        "s310": _build_s310_depth(stats_a, stats_b, h2h, ranking_result),
    }

    # Compose full markdown
    header = (
        f"══ CANDIDATE: {home} vs {away} | {competition} | {kickoff} "
        f"| {sport.upper()} ══"
    )
    md_parts = [header, ""]
    for key in ["s31", "s32", "s33", "s34", "s35", "s36", "s37", "s38", "s39", "s310"]:
        md_parts.append(sections[key])

    md_parts.append("══ END CANDIDATE ══\n")
    markdown = "\n".join(md_parts)

    has_data = stats_a["has_data"] or stats_b["has_data"]

    # If slug-based cache missed but safety_input succeeded (from raw API cache fallback),
    # mark as having data so this candidate isn't counted as "no stats"
    if not has_data and safety_input and safety_input.get("markets"):
        has_data = True

    return {
        "sport": sport,
        "home_team": home,
        "away_team": away,
        "competition": competition,
        "kickoff": kickoff,
        "has_data": has_data,
        "ranking_result": ranking_result,
        "stats_a_summary": {
            "team": stats_a["team"],
            "has_data": stats_a["has_data"],
            "l10_avg": stats_a["l10_avg"],
            "l5_avg": stats_a["l5_avg"],
            "l10_matches_count": len(stats_a["l10_matches"]),
            "sources": stats_a["sources"],
        },
        "stats_b_summary": {
            "team": stats_b["team"],
            "has_data": stats_b["has_data"],
            "l10_avg": stats_b["l10_avg"],
            "l5_avg": stats_b["l5_avg"],
            "l10_matches_count": len(stats_b["l10_matches"]),
            "sources": stats_b["sources"],
        },
        "h2h_summary": {
            "has_data": h2h["has_data"],
            "meetings_count": len(h2h["meetings"]),
            "averages": h2h["averages"],
        },
        "best_market": (
            {
                "name": best_market["name"],
                "line": best_market["line"],
                "direction": best_market["direction"],
                "safety_score": best_market["safety_score"],
                "combined_avg": best_market["combined_avg"],
                "h2h_avg": best_market.get("h2h_avg"),
                "hit_rate_l10": best_market["hit_rate_l10"],
                "hit_rate_h2h": best_market["hit_rate_h2h"],
            }
            if best_market
            else None
        ),
        "markets_evaluated": len(ranking_result.get("ranking", [])),
        "sections": sections,
        "markdown": markdown,
    }


# ---------------------------------------------------------------------------
# Pool / shortlist loading
# ---------------------------------------------------------------------------

def _load_candidates_from_pool(date: str) -> list[dict]:
    """Load candidates from analysis_pool_{date}.json."""
    pool_path = DATA_DIR / f"analysis_pool_{date}.json"
    if not pool_path.exists():
        return []
    try:
        data = json.loads(pool_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    events = data.get("events", [])
    candidates = []
    for e in events:
        candidates.append({
            "sport": e.get("sport", "football"),
            "home_team": e.get("home_team", ""),
            "away_team": e.get("away_team", ""),
            "competition": e.get("competition", ""),
            "kickoff": e.get("kickoff", ""),
        })
    return candidates


def _load_candidates_from_shortlist(path: str) -> list[dict]:
    """Load candidates from a shortlist JSON file."""
    shortlist_path = Path(path)
    if not shortlist_path.exists():
        print(f"[deep_stats] Shortlist not found: {path}")
        return []
    try:
        data = json.loads(shortlist_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    entries = data.get("candidates", [])
    candidates = []
    for e in entries:
        candidates.append({
            "sport": e.get("sport", "football"),
            "home_team": e.get("home_team", ""),
            "away_team": e.get("away_team", ""),
            "competition": e.get("competition", ""),
            "kickoff": e.get("kickoff", ""),
        })
    return candidates


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_deep_stats(date: str, shortlist_path: str | None = None, top: int | None = None) -> dict:
    """Generate S3 deep stats report for all candidates.

    Args:
        date: betting day YYYY-MM-DD
        shortlist_path: optional path to shortlist JSON (overrides pool)
        top: limit to first N candidates

    Returns:
        dict with metadata and per-candidate analyses.
    """
    if shortlist_path:
        candidates = _load_candidates_from_shortlist(shortlist_path)
        source = f"shortlist:{shortlist_path}"
    else:
        candidates = _load_candidates_from_pool(date)
        source = f"analysis_pool_{date}.json"

    if not candidates:
        print(f"[deep_stats] No candidates found from {source}")
        return {
            "date": date,
            "generated_at": _now_iso(),
            "source": source,
            "total_candidates": 0,
            "candidates_with_data": 0,
            "analyses": [],
        }

    if top and top > 0:
        candidates = candidates[:top]

    # Filter out candidates missing team names upfront
    valid = [(i, c) for i, c in enumerate(candidates, 1)
             if c["home_team"] and c["away_team"]]

    print(f"[deep_stats] Analyzing {len(valid)} candidates from {source}")

    def _analyze_one(idx_candidate: tuple[int, dict]) -> dict | None:
        i, c = idx_candidate
        home = c["home_team"]
        away = c["away_team"]
        sport = c["sport"]
        comp = c["competition"]
        kickoff = c["kickoff"]
        print(f"[deep_stats] [{i}/{len(valid)}] {home} vs {away} ({sport})")
        return analyze_candidate(sport, home, away, comp, kickoff)

    analyses = []
    with_data = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_analyze_one, item): item for item in valid}
        # Collect results maintaining original order
        results_map: dict[int, dict] = {}
        for future in concurrent.futures.as_completed(futures):
            item = futures[future]
            idx = item[0]
            try:
                result = future.result()
            except Exception as e:
                home = item[1].get("home_team", "?")
                away = item[1].get("away_team", "?")
                print(f"[deep_stats] [ERROR] {home} vs {away} analysis failed: {e}")
                continue
            if result is not None:
                results_map[idx] = result

        for idx, _ in valid:
            if idx in results_map:
                analyses.append(results_map[idx])
                if results_map[idx]["has_data"]:
                    with_data += 1

    output = {
        "date": date,
        "generated_at": _now_iso(),
        "source": source,
        "total_candidates": len(analyses),
        "candidates_with_data": with_data,
        "analyses": analyses,
    }

    # Write outputs
    _write_markdown(output, date)
    _write_json(output, date)

    return output


def _write_markdown(output: dict, date: str) -> Path:
    """Write full markdown report."""
    md_path = DATA_DIR / f"{date}_s3_deep_stats.md"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# S3 Deep Stats Report — {date}",
        f"Generated: {output['generated_at']} | "
        f"Candidates: {output['total_candidates']} total, "
        f"{output['candidates_with_data']} with data | "
        f"Source: {output['source']}",
        "",
    ]

    for analysis in output["analyses"]:
        lines.append(analysis["markdown"])
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[deep_stats] Markdown: {md_path}")
    return md_path


def _write_json(output: dict, date: str) -> Path:
    """Write structured JSON report (without raw markdown in sections)."""
    json_path = DATA_DIR / f"{date}_s3_deep_stats.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Build JSON-friendly version (strip large markdown from sections)
    json_output = {
        "date": output["date"],
        "generated_at": output["generated_at"],
        "source": output["source"],
        "total_candidates": output["total_candidates"],
        "candidates_with_data": output["candidates_with_data"],
        "analyses": [],
    }

    for a in output["analyses"]:
        json_entry = {
            "sport": a["sport"],
            "home_team": a["home_team"],
            "away_team": a["away_team"],
            "competition": a["competition"],
            "kickoff": a["kickoff"],
            "has_data": a["has_data"],
            "best_market": a["best_market"],
            "markets_evaluated": a["markets_evaluated"],
            "stats_a_summary": a["stats_a_summary"],
            "stats_b_summary": a["stats_b_summary"],
            "h2h_summary": a["h2h_summary"],
            "ranking": a["ranking_result"].get("ranking", []),
            "three_way_check": a["ranking_result"].get("three_way_check"),
            "warnings": a["ranking_result"].get("warnings", []),
        }
        json_output["analyses"].append(json_entry)

    json_path.write_text(
        json.dumps(json_output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[deep_stats] JSON: {json_path}")
    return json_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="S3 Deep Stats Report — per-candidate 10-section statistical analysis"
    )
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Betting day YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--shortlist",
        default=None,
        help="Path to S2 shortlist JSON (overrides analysis pool)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Limit to first N candidates",
    )

    args = parser.parse_args()
    result = generate_deep_stats(args.date, args.shortlist, args.top)
    print(
        f"\n[deep_stats] Done: {result['total_candidates']} candidates, "
        f"{result['candidates_with_data']} with data"
    )
