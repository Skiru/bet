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
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from normalize_stats import build_safety_input, build_safety_input_from_cache
from compute_safety_scores import rank_markets

from bet.stats.market_ranking import SPORT_STAT_KEYS

from utils import normalize_kickoff

DATA_DIR = Path(__file__).parent.parent / "betting" / "data"
CACHE_DIR = Path(__file__).parent.parent / "betting" / "data" / "stats_cache"


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


def _resolve_team_ids(conn, team_a: str, team_b: str, sport: str) -> tuple[int | None, int | None]:
    """Resolve team names to DB IDs via TeamRepo.resolve().

    Returns (team_id_a, team_id_b). Either may be None if not found.
    """
    from bet.db.repositories import SportRepo, TeamRepo

    sr = SportRepo(conn)
    s = sr.get_by_name(sport)
    if not s:
        return None, None

    tr = TeamRepo(conn)
    ta = tr.resolve(team_a, s.id)
    tb = tr.resolve(team_b, s.id)
    return (ta.id if ta else None), (tb.id if tb else None)


def compute_data_quality(stats_a: dict, stats_b: dict, h2h: dict, sport: str) -> dict:
    """Compute data quality score (0-10) based on data availability.

    Returns dict with score, label (FULL/PARTIAL/MINIMAL), and breakdown.
    """
    score = 0
    breakdown = {}

    # +2 if L10 has ≥8 data points (across both teams)
    l10_count = len(stats_a.get("l10_matches", [])) + len(stats_b.get("l10_matches", []))
    l10_ok = l10_count >= 8
    if l10_ok:
        score += 2
    breakdown["l10_data"] = l10_ok

    # +2 if H2H has ≥3 meetings
    h2h_ok = h2h.get("has_data", False) and len(h2h.get("meetings", [])) >= 3
    if h2h_ok:
        score += 2
    breakdown["h2h_data"] = h2h_ok

    # +1 if L5 available for at least one team
    l5_ok = bool(stats_a.get("l5_avg")) or bool(stats_b.get("l5_avg"))
    if l5_ok:
        score += 1
    breakdown["l5_trend"] = l5_ok

    # +1 if injury data checked (present in cache)
    cache_a = stats_a.get("raw_cache") or {}
    cache_b = stats_b.get("raw_cache") or {}
    injuries_ok = bool(
        cache_a.get("injuries") or cache_a.get("unavailable")
        or cache_b.get("injuries") or cache_b.get("unavailable")
    )
    league_ok = False
    # Check DB injuries + standings (single DB connection, resolve once)
    try:
        from bet.db.connection import get_db
        with get_db() as conn:
            tid_a, tid_b = _resolve_team_ids(
                conn, stats_a.get("team", ""), stats_b.get("team", ""),
                sport,
            )
            ids = [i for i in (tid_a, tid_b) if i is not None]
            if ids:
                placeholders = ",".join("?" * len(ids))
                if not injuries_ok:
                    row = conn.execute(
                        f"SELECT COUNT(*) FROM injuries WHERE team_id IN ({placeholders})",
                        ids,
                    ).fetchone()
                    if row and row[0] > 0:
                        injuries_ok = True
                # standings check
                row = conn.execute(
                    f"SELECT COUNT(*) FROM standings WHERE team_id IN ({placeholders})",
                    ids,
                ).fetchone()
                if row and row[0] > 0:
                    league_ok = True
    except Exception as e:
        print(f"[deep_stats] DB injuries/standings check failed: {e}")
    if injuries_ok:
        score += 1
    breakdown["injuries"] = injuries_ok

    # +1 if standings available
    if league_ok:
        score += 1
    breakdown["league_context"] = league_ok

    # +1 if tipster data available
    tipster_ok = False
    try:
        from bet.db.connection import get_db
        with get_db() as conn:
            # Check tipster_picks first (primary source)
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM tipster_picks WHERE "
                    "(LOWER(home_team) LIKE ? OR LOWER(away_team) LIKE ? "
                    "OR LOWER(home_team) LIKE ? OR LOWER(away_team) LIKE ?)",
                    (f"%{stats_a.get('team', '').lower()}%", f"%{stats_a.get('team', '').lower()}%",
                     f"%{stats_b.get('team', '').lower()}%", f"%{stats_b.get('team', '').lower()}%"),
                ).fetchone()
                if row and row[0] > 0:
                    tipster_ok = True
            except Exception:
                pass
            # Fallback: web_research_cache
            if not tipster_ok:
                row = conn.execute(
                    "SELECT COUNT(*) FROM web_research_cache WHERE query LIKE ? OR query LIKE ?",
                    (f"%{stats_a.get('team', '')}%", f"%{stats_b.get('team', '')}%"),
                ).fetchone()
                if row and row[0] > 0:
                    tipster_ok = True
    except Exception:
        pass
    if tipster_ok:
        score += 1
    breakdown["tipster_data"] = tipster_ok

    # +1 if odds from ≥2 sources
    sources_a = set(stats_a.get("sources", []))
    sources_b = set(stats_b.get("sources", []))
    all_sources = sources_a | sources_b
    odds_ok = len(all_sources) >= 2
    if odds_ok:
        score += 1
    breakdown["odds_validated"] = odds_ok

    # +1 if 3-way alignment (checked downstream, default False)
    breakdown["three_way_check"] = False

    label = "FULL" if score >= 7 else "PARTIAL" if score >= 4 else "MINIMAL"

    return {"score": score, "label": label, "breakdown": breakdown}


def _ranking_from_shortlist_markets(safety_markets: list) -> dict:
    """Build a ranking_result dict from precomputed shortlist safety_markets.

    This is used as fallback when build_safety_input returns None (no DB form,
    no JSON cache) but the shortlist builder already computed safety data.
    """
    ranking = []
    for m in safety_markets:
        ranking.append({
            "name": m.get("market", ""),
            "team_a_avg": 0.0,
            "team_b_avg": 0.0,
            "combined_avg": m.get("l10_avg", 0.0),
            "h2h_avg": m.get("h2h_avg"),
            "line": m.get("l10_avg", 0.0),  # Will use standard lines downstream
            "direction": m.get("direction", "OVER"),
            "hit_rate_l10": m.get("hit_rate_l10", "N/A"),
            "hit_rate_h2h": m.get("hit_rate_h2h", "N/A"),
            "hit_rate_l5": "N/A",
            "safety_score": m.get("safety_score", 0.0),
            "margin": m.get("margin", 0.0),
            "source": m.get("source", "shortlist"),
            "h2h_blind": m.get("h2h_blind", True),
            "one_sided": False,
            "three_way_check": {"status": "N/A"},
            "rank": 0,
        })
    # Sort by safety score descending
    ranking.sort(key=lambda x: (x["safety_score"], x["margin"]), reverse=True)
    for i, r in enumerate(ranking, 1):
        r["rank"] = i

    best = ranking[0] if ranking else None
    return {
        "ranking": ranking,
        "three_way_check": None,
        "recommended_market": best["name"] if best else None,
        "recommended_safety": best["safety_score"] if best else None,
        "warnings": ["SHORTLIST_FALLBACK: using precomputed safety from shortlist builder"],
        "markdown_ranking_table": "",
        "markdown_three_way_table": "",
        "markets_evaluated": len(ranking),
        "min_required": 3,
    }


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------

def extract_team_stats(sport: str, team_name: str) -> dict:
    """Read stats cache for a single team. DB-first with JSON cache fallback.

    Returns dict with keys: team, sport, l10_avg, l5_avg, l10_matches,
    sources, raw_cache. Returns empty markers if cache is missing.
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

    # Try DB first (team_form table)
    try:
        from db_data_loader import load_team_form_from_db
        db_form = load_team_form_from_db(team_name, sport)
        if db_form and db_form.get("form"):
            form = db_form["form"]
            stat_keys = SPORT_STAT_KEYS.get(sport, [])
            for key in stat_keys:
                if key in form.get("l10_avg", {}):
                    result["l10_avg"][key] = form["l10_avg"][key]
                if key in form.get("l5_avg", {}):
                    result["l5_avg"][key] = form["l5_avg"][key]
            result["l10_matches"] = form.get("l10_matches", [])[:10]
            result["sources"] = db_form.get("sources", ["db"])
            if result["l10_avg"]:
                result["has_data"] = True
                return result
    except Exception:
        pass

    # JSON cache fallback
    cache_file = CACHE_DIR / sport / f"{slug}.json"
    if not cache_file.exists():
        # ESPN enrichment for basketball/hockey — ALWAYS try
        if sport in ("basketball", "hockey"):
            try:
                from db_data_loader import load_espn_enrichment_for_team
                espn_data = load_espn_enrichment_for_team(team_name, sport)
                if espn_data:
                    result["espn_enrichment"] = espn_data
                    result["has_data"] = True
                    if "espn_db" not in result["sources"]:
                        result["sources"].append("espn_db")
            except Exception:
                pass

        return result

    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return result

    result["raw_cache"] = cache
    result["sources"] = cache.get("sources", [])

    form = cache.get("form", {})
    stat_keys = SPORT_STAT_KEYS.get(sport, [])

    # Percentage stats should NOT sum home+away (would yield ~100%)
    PERCENTAGE_STATS = {"possession", "fg_pct", "three_pct", "ft_pct",
                        "first_serve_pct", "faceoff_pct", "attack_pct",
                        "checkout_pct"}

    # Extract L10 and L5 averages, merging _home/_away split keys
    for period_key, target in [("l10_avg", "l10_avg"), ("l5_avg", "l5_avg")]:
        avg_data = form.get(period_key, {})
        for key in stat_keys:
            if key in avg_data:
                # Bare key exists — use directly
                result[target][key] = avg_data[key]
            else:
                # Check for _home/_away split keys (from ESPN/API enrichment)
                home_key = f"{key}_home"
                away_key = f"{key}_away"
                has_home = home_key in avg_data
                has_away = away_key in avg_data
                if has_home or has_away:
                    home_val = avg_data.get(home_key, 0)
                    away_val = avg_data.get(away_key, 0)
                    if key in PERCENTAGE_STATS:
                        # Percentage stats: keep home-only (not summed)
                        result[target][key] = home_val
                    else:
                        # Counting stats: sum home + away
                        result[target][key] = round(home_val + away_val, 2)
                    # Also preserve the split values
                    if has_home:
                        result[target][home_key] = home_val
                    if has_away:
                        result[target][away_key] = away_val

    # Extract L10 match-by-match data
    l10 = form.get("l10_matches", form.get("recent_matches", []))
    result["l10_matches"] = l10[:10] if l10 else []

    # Only mark has_data if we actually extracted meaningful stats
    if result["l10_avg"] or result["l5_avg"] or result["l10_matches"]:
        result["has_data"] = True

    # ESPN enrichment for basketball/hockey — ALWAYS load as supplement
    if sport in ("basketball", "hockey"):
        try:
            from db_data_loader import load_espn_enrichment_for_team
            espn_data = load_espn_enrichment_for_team(team_name, sport)
            if espn_data:
                result["espn_enrichment"] = espn_data
                result["has_data"] = True
                if "espn_db" not in result["sources"]:
                    result["sources"].append("espn_db")
        except Exception:
            pass

    # MoneyPuck enrichment for hockey — xG%, Corsi%, Fenwick% (free CSV, no API key)
    if sport == "hockey":
        try:
            from api_clients.moneypuck_client import get_team_stats as mp_get_team
            mp_data = mp_get_team(team_name)
            if mp_data and mp_data.get("stats"):
                result["moneypuck"] = mp_data["stats"]
                result["has_data"] = True
                if "moneypuck" not in result["sources"]:
                    result["sources"].append("moneypuck")
        except Exception:
            pass

    # LAST RESORT: Internet enrichment via data_enrichment_agent
    if not result["has_data"] and not os.environ.get("NO_ENRICH"):
        try:
            from data_enrichment_agent import enrich_team
            enrichment = enrich_team(team_name, sport)
            if enrichment.get("status") in ("enriched", "partial"):
                # Re-read from cache after enrichment saved data
                slug = result["slug"]
                cache_file = CACHE_DIR / sport / f"{slug}.json"
                if cache_file.exists():
                    try:
                        cache = json.loads(cache_file.read_text(encoding="utf-8"))
                        form = cache.get("form", {})
                        stat_keys_refresh = SPORT_STAT_KEYS.get(sport, [])
                        for key in stat_keys_refresh:
                            if key in form.get("l10_avg", {}):
                                result["l10_avg"][key] = form["l10_avg"][key]
                            if key in form.get("l5_avg", {}):
                                result["l5_avg"][key] = form["l5_avg"][key]
                        result["l10_matches"] = form.get("l10_matches", [])[:10]
                        if result["l10_avg"] or result["l5_avg"]:
                            result["has_data"] = True
                        result["sources"] = cache.get("sources", [])
                        if "enrichment-agent" not in result["sources"]:
                            result["sources"].append("enrichment-agent")
                    except (json.JSONDecodeError, OSError):
                        pass
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("Inline enrichment failed for %s: %s", team_name, e)

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

    # Try cache/DB sources first
    h2h_data = None
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
            h2h_section = cache.get("h2h", {})
            # Try exact slug, then fuzzy match
            h2h_data = h2h_section.get(slug_b)
            if not h2h_data:
                for key, val in h2h_section.items():
                    if slug_b in key or key in slug_b:
                        h2h_data = val
                        break
        except (json.JSONDecodeError, OSError):
            pass

    if h2h_data:
        meetings = h2h_data.get("matches", [])
        if meetings:
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

    # LAST RESORT: Internet H2H enrichment via data_enrichment_agent
    if not result["has_data"]:
        try:
            from data_enrichment_agent import enrich_h2h
            h2h_enriched = enrich_h2h(team_a, team_b, sport)
            if h2h_enriched.get("status") == "enriched":
                result["has_data"] = True
                result["averages"] = h2h_enriched.get("h2h_stats", {})
                result["meetings"] = [{"source": "enrichment-agent", "meeting_count": h2h_enriched.get("meetings_found", 0)}]
        except Exception:
            pass

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


def _build_league_context(sport: str, team_a: str, team_b: str) -> str:
    """§S3.11 League Context — standings, rank, points gap from DB."""
    lines = ["§S3.11 League Context"]
    try:
        from bet.db.connection import get_db
        with get_db() as conn:
            tid_a, tid_b = _resolve_team_ids(conn, team_a, team_b, sport)
            ids = [i for i in (tid_a, tid_b) if i is not None]
            if not ids:
                lines.append("⚠️ Teams not found in DB — verify league context manually")
                lines.append("")
                return "\n".join(lines)

            placeholders = ",".join("?" * len(ids))
            rows = conn.execute(
                f"SELECT t.name, s.rank, s.points, s.wins, s.draws, s.losses, s.form, s.competition_id "
                f"FROM standings s JOIN teams t ON s.team_id = t.id "
                f"WHERE s.team_id IN ({placeholders}) "
                f"ORDER BY s.updated_at DESC",
                ids,
            ).fetchall()
            if rows:
                # Deduplicate (take most recent per team)
                seen = set()
                unique_rows = []
                for row in rows:
                    if row[0] not in seen:
                        seen.add(row[0])
                        unique_rows.append(row)

                lines.append("| Team | Rank | Points | W-D-L | Form |")
                lines.append("|------|------|--------|-------|------|")
                for row in unique_rows:
                    form = row[6] if row[6] else "N/A"
                    lines.append(
                        f"| {row[0]} | {row[1]} | {row[2]} | "
                        f"{row[3]}-{row[4]}-{row[5]} | {form} |"
                    )
                # Points gap (only if both teams share the same competition)
                if len(unique_rows) >= 2 and unique_rows[0][7] == unique_rows[1][7]:
                    gap = abs((unique_rows[0][2] or 0) - (unique_rows[1][2] or 0))
                    lines.append(f"Points gap: {gap}")
            else:
                lines.append("⚠️ No standings data in DB — verify league context manually")
    except Exception as e:
        print(f"[deep_stats] League context query failed: {e}")
        lines.append("⚠️ Standings query failed — verify league context manually")
    lines.append("")
    return "\n".join(lines)


def _build_injuries_section(sport: str, team_a: str, team_b: str) -> str:
    """§S3.12 Injuries (DB) — current injuries per team from injuries table."""
    lines = ["§S3.12 Injuries (DB)"]
    try:
        from bet.db.connection import get_db
        with get_db() as conn:
            tid_a, tid_b = _resolve_team_ids(conn, team_a, team_b, sport)
            for team, tid in ((team_a, tid_a), (team_b, tid_b)):
                if tid is None:
                    lines.append(f"**{team}**: Team not found in DB")
                    continue
                rows = conn.execute(
                    "SELECT athlete_name, injury_type, status, expected_return "
                    "FROM injuries WHERE team_id = ?",
                    (tid,),
                ).fetchall()
                if rows:
                    lines.append(f"**{team}** ({len(rows)} injuries):")
                    for row in rows:
                        status = row[2] if row[2] else "OUT"
                        ret = f", return: {row[3]}" if row[3] else ""
                        lines.append(f"  - {row[0]}: {row[1]} ({status}{ret})")
                else:
                    lines.append(f"**{team}**: No injury records in DB")
    except Exception as e:
        print(f"[deep_stats] Injuries query failed: {e}")
        lines.append("⚠️ Injuries table not available — check Flashscore/Sofascore")
    lines.append("")
    return "\n".join(lines)


def _build_expert_sentiment(sport: str, team_a: str, team_b: str) -> str:
    """§S3.13 Expert Sentiment — tipster consensus + web research data."""
    lines = ["§S3.13 Expert Sentiment"]
    found_tipster = False
    try:
        from bet.db.connection import get_db
        with get_db() as conn:
            # Primary: tipster consensus table
            try:
                rows = conn.execute(
                    "SELECT consensus_market, consensus_direction, agreement_pct, total_tipsters, "
                    "statistical_picks, tipster_sources FROM tipster_consensus "
                    "WHERE (LOWER(home_team) LIKE ? AND LOWER(away_team) LIKE ?) "
                    "ORDER BY agreement_pct DESC LIMIT 3",
                    (f"%{team_a.lower()}%", f"%{team_b.lower()}%"),
                ).fetchall()
                if rows:
                    found_tipster = True
                    for row in rows:
                        market = row[0] or "N/A"
                        direction = row[1] or "N/A"
                        agreement = row[2] or 0
                        tipsters = row[3] or 0
                        stat_picks = row[4] or 0
                        signal = "🟢" if agreement >= 70 else ("🟡" if agreement >= 50 else "🔴")
                        lines.append(f"- {signal} {market} → {direction} ({agreement:.0f}% agreement, {tipsters} tipsters, {stat_picks} statistical)")
            except Exception:
                pass  # table may not exist yet

            # Supplementary: web_research_cache
            try:
                rows = conn.execute(
                    "SELECT query, summary, source_url FROM web_research_cache "
                    "WHERE (query LIKE ? OR query LIKE ?) ORDER BY created_at DESC LIMIT 3",
                    (f"%{team_a}%", f"%{team_b}%"),
                ).fetchall()
                if rows:
                    found_tipster = True
                    for row in rows:
                        summary = (row[1] or "")[:200]
                        source = row[2] or "unknown"
                        lines.append(f"- [{source}] {summary}")
            except Exception:
                pass

            if not found_tipster:
                lines.append("⚠️ No expert/tipster data cached — TIPSTER-BLIND")
    except Exception:
        lines.append("⚠️ Tipster/research data not available")
    lines.append("")
    return "\n".join(lines)


def _build_s314_espn(stats_a: dict, stats_b: dict) -> str:
    """§S3.14 ESPN Enrichment — ATS, O/U records, power index, standings."""
    lines = ["§S3.14 ESPN Enrichment"]

    espn_a = stats_a.get("espn_enrichment") or {}
    espn_b = stats_b.get("espn_enrichment") or {}

    if not espn_a and not espn_b:
        lines.append("⚠️ No ESPN enrichment data available")
        lines.append("")
        return "\n".join(lines)

    team_a = stats_a["team"]
    team_b = stats_b["team"]

    # ATS Records
    ats_a = espn_a.get("ats_record")
    ats_b = espn_b.get("ats_record")
    if ats_a or ats_b:
        lines.append("**ATS (Against The Spread):**")
        lines.append("| Team | W-L-P | Cover% | Home W-L | Away W-L |")
        lines.append("|------|-------|--------|----------|----------|")
        for team, ats in ((team_a, ats_a), (team_b, ats_b)):
            if ats:
                lines.append(
                    f"| {team} | {ats.get('wins', 0)}-{ats.get('losses', 0)}-{ats.get('pushes', 0)} "
                    f"| {ats.get('cover_pct', 0)}% "
                    f"| {ats.get('home_wins', 0)}-{ats.get('home_losses', 0)} "
                    f"| {ats.get('away_wins', 0)}-{ats.get('away_losses', 0)} |"
                )
        lines.append("")

    # O/U Records
    ou_a = espn_a.get("ou_record")
    ou_b = espn_b.get("ou_record")
    if ou_a or ou_b:
        lines.append("**Over/Under Records:**")
        lines.append("| Team | O-U-P | Over% | Home O-U | Away O-U |")
        lines.append("|------|-------|-------|----------|----------|")
        for team, ou in ((team_a, ou_a), (team_b, ou_b)):
            if ou:
                lines.append(
                    f"| {team} | {ou.get('overs', 0)}-{ou.get('unders', 0)}-{ou.get('pushes', 0)} "
                    f"| {ou.get('over_pct', 0)}% "
                    f"| {ou.get('home_overs', 0)}-{ou.get('home_unders', 0)} "
                    f"| {ou.get('away_overs', 0)}-{ou.get('away_unders', 0)} |"
                )
        lines.append("")

    # Standings (from ESPN)
    std_a = espn_a.get("standing")
    std_b = espn_b.get("standing")
    if std_a or std_b:
        lines.append("**ESPN Standings:**")
        lines.append("| Team | Rank | W-L-D | Pts | Home | Away | Form | Streak |")
        lines.append("|------|------|-------|-----|------|------|------|--------|")
        for team, std in ((team_a, std_a), (team_b, std_b)):
            if std:
                lines.append(
                    f"| {team} | {std.get('rank', 'N/A')} "
                    f"| {std.get('wins', 0)}-{std.get('losses', 0)}-{std.get('draws', 0)} "
                    f"| {std.get('points', 'N/A')} "
                    f"| {std.get('home_record', 'N/A')} "
                    f"| {std.get('away_record', 'N/A')} "
                    f"| {std.get('form', 'N/A')} "
                    f"| {std.get('streak', 'N/A')} |"
                )
        lines.append("")

    # Power Index
    pi_a = espn_a.get("power_index")
    pi_b = espn_b.get("power_index")
    if pi_a or pi_b:
        lines.append("**Power Index:**")
        for team, pi in ((team_a, pi_a), (team_b, pi_b)):
            if pi:
                lines.append(f"  - {team}: {pi}")
        lines.append("")

    if not any([ats_a, ats_b, ou_a, ou_b, std_a, std_b, pi_a, pi_b]):
        lines.append("ESPN data loaded but all sub-sections empty")
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
    shortlist_safety_markets: list | None = None,
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
    ranking_result = None
    safety_input = build_safety_input(sport, home, away, competition)
    if safety_input and safety_input.get("markets"):
        ranking_result = rank_markets(safety_input)
    else:
        # Before shortlist fallback: try enrichment (respects NO_ENRICH env var)
        if (not safety_input or not safety_input.get("markets")) and not os.environ.get("NO_ENRICH"):
            try:
                from data_enrichment_agent import enrich_team
                enrich_team(home, sport)
                enrich_team(away, sport)
                # Retry safety input after enrichment
                safety_input = build_safety_input(sport, home, away, competition)
                if safety_input and safety_input.get("markets"):
                    ranking_result = rank_markets(safety_input)
            except Exception:
                pass

    if not ranking_result and shortlist_safety_markets:
        # FALLBACK: use precomputed safety data from shortlist builder
        ranking_result = _ranking_from_shortlist_markets(shortlist_safety_markets)

    if not ranking_result:
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

    # Compute data quality
    dq = compute_data_quality(stats_a, stats_b, h2h, sport)
    # Update three_way_check in data quality if ranking has it
    tw = ranking_result.get("three_way_check")
    if tw and tw.get("alignment") and "SUPPORT" in str(tw.get("alignment", "")).upper():
        dq["breakdown"]["three_way_check"] = True
        dq["score"] += 1
        dq["label"] = "FULL" if dq["score"] >= 7 else "PARTIAL" if dq["score"] >= 4 else "MINIMAL"

    # Build all 10+ sections
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
        "s311": _build_league_context(sport, home, away),
        "s312": _build_injuries_section(sport, home, away),
        "s313": _build_expert_sentiment(sport, home, away),
        "s314": _build_s314_espn(stats_a, stats_b),
    }

    # Compose full markdown
    header = (
        f"══ CANDIDATE: {home} vs {away} | {competition} | {kickoff} "
        f"| {sport.upper()} | Data: {dq['label']} ({dq['score']}/10) ══"
    )
    md_parts = [header, ""]
    for key in ["s31", "s32", "s33", "s34", "s35", "s36", "s37", "s38", "s39", "s310",
                "s311", "s312", "s313", "s314"]:
        md_parts.append(sections[key])

    md_parts.append("══ END CANDIDATE ══\n")
    markdown = "\n".join(md_parts)

    has_data = stats_a["has_data"] or stats_b["has_data"]
    # Also mark has_data if safety_input produced markets (API cache fallback)
    if not has_data and safety_input and safety_input.get("markets"):
        has_data = True
    # Also mark has_data if shortlist fallback produced ranking
    if not has_data and ranking_result.get("ranking"):
        has_data = True

    # Build raw data for decision learning
    raw_data = {
        "team_a_l10": {
            "team": stats_a["team"],
            "l10_avg": stats_a["l10_avg"],
            "l5_avg": stats_a["l5_avg"],
            "l10_matches": stats_a["l10_matches"],
            "sources": stats_a["sources"],
        },
        "team_b_l10": {
            "team": stats_b["team"],
            "l10_avg": stats_b["l10_avg"],
            "l5_avg": stats_b["l5_avg"],
            "l10_matches": stats_b["l10_matches"],
            "sources": stats_b["sources"],
        },
        "h2h_meetings": {
            "has_data": h2h["has_data"],
            "meetings": h2h["meetings"],
            "averages": h2h["averages"],
        },
        "per_market_details": [
            {
                "name": mkt["name"],
                "line": mkt["line"],
                "direction": mkt["direction"],
                "safety_score": mkt["safety_score"],
                "combined_avg": mkt["combined_avg"],
                "h2h_avg": mkt.get("h2h_avg"),
                "hit_rate_l10": mkt["hit_rate_l10"],
                "hit_rate_h2h": mkt.get("hit_rate_h2h"),
                "margin": mkt.get("margin"),
                "three_way_check": mkt.get("three_way_check"),
                "one_sided": mkt.get("one_sided", False),
                "h2h_blind": mkt.get("h2h_blind", False),
            }
            for mkt in ranking_result.get("ranking", [])
        ],
        "safety_input": safety_input,
    }

    return {
        "sport": sport,
        "home_team": home,
        "away_team": away,
        "competition": competition,
        "kickoff": kickoff,
        "has_data": has_data,
        "data_quality": dq,
        "ranking_result": ranking_result,
        "stats_a_summary": {
            "team": stats_a["team"],
            "has_data": stats_a["has_data"],
            "l10_avg": stats_a["l10_avg"],
            "l5_avg": stats_a["l5_avg"],
            "l10_matches_count": len(stats_a["l10_matches"]),
            "sources": stats_a["sources"],
            "espn_enrichment": stats_a.get("espn_enrichment"),
        },
        "stats_b_summary": {
            "team": stats_b["team"],
            "has_data": stats_b["has_data"],
            "l10_avg": stats_b["l10_avg"],
            "l5_avg": stats_b["l5_avg"],
            "l10_matches_count": len(stats_b["l10_matches"]),
            "sources": stats_b["sources"],
            "espn_enrichment": stats_b.get("espn_enrichment"),
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
                "source": best_market.get("source", ""),
                "one_sided": best_market.get("one_sided", False),
                "h2h_blind": best_market.get("h2h_blind", False),
            }
            if best_market
            else None
        ),
        "markets_evaluated": len(ranking_result.get("ranking", [])),
        "sections": sections,
        "markdown": markdown,
        "raw_data": raw_data,
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
            "safety_markets": e.get("safety_markets"),
            "n_odds_markets": e.get("n_odds_markets", 0),
            "fixture_verified": e.get("fixture_verified", False),
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
    entries = data.get("candidates", data.get("events", []))
    candidates = []
    for e in entries:
        candidates.append({
            "sport": e.get("sport", "football"),
            "home_team": e.get("home_team", e.get("home", "")),
            "away_team": e.get("away_team", e.get("away", "")),
            "competition": e.get("competition", ""),
            "kickoff": e.get("kickoff", e.get("kickoff_cest", "")),
            "safety_markets": e.get("safety_markets", []),
            "n_odds_markets": e.get("n_odds_markets", 0),
            "fixture_verified": e.get("fixture_verified", False),
        })
    return candidates


def _load_candidates_from_db(date: str) -> list[dict]:
    """Load candidates from fixtures DB table (R2 DB-FIRST).

    Falls back to _load_candidates_from_pool() if DB is empty.
    """
    try:
        from db_data_loader import load_fixtures_from_db
        fixtures = load_fixtures_from_db(date)
        if not fixtures:
            return []
        candidates = []
        for f in fixtures:
            candidates.append({
                "sport": f.get("sport", f.get("sport_name", "football")),
                "home_team": f.get("home_team", ""),
                "away_team": f.get("away_team", ""),
                "competition": f.get("competition", f.get("competition_name", "")),
                "kickoff": f.get("kickoff", f.get("kickoff_utc", "")),
                "safety_markets": None,
                "n_odds_markets": 0,
                "fixture_verified": True,  # DB fixtures are verified
            })
        print(f"[deep_stats] Loaded {len(candidates)} candidates from DB fixtures")
        return candidates
    except Exception as e:
        print(f"[deep_stats] DB fixture loading failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_deep_stats(date: str, shortlist_path: str | None = None, top: int | None = None, no_enrich: bool = False, from_db: bool = False, gemini: bool = False) -> dict:
    """Generate S3 deep stats report for all candidates.

    Args:
        date: betting day YYYY-MM-DD
        shortlist_path: optional path to shortlist JSON (overrides pool)
        top: limit to first N candidates
        no_enrich: skip enrichment phase
        from_db: load candidates from DB fixtures table first

    Returns:
        dict with metadata and per-candidate analyses.
    """
    if shortlist_path:
        # Explicit shortlist file overrides everything
        candidates = _load_candidates_from_shortlist(shortlist_path)
        source = f"shortlist:{shortlist_path}"
    elif from_db:
        # Explicit DB-first mode
        candidates = _load_candidates_from_db(date)
        source = f"db:fixtures:{date}"
        if not candidates:
            # Fallback to JSON pool
            candidates = _load_candidates_from_pool(date)
            source = f"analysis_pool_{date}.json (DB fallback)"
    else:
        # Default: try DB first (R2), fall back to JSON pool
        candidates = _load_candidates_from_db(date)
        source = f"db:fixtures:{date}"
        if not candidates:
            candidates = _load_candidates_from_pool(date)
            source = f"analysis_pool_{date}.json (DB empty)"

    # Normalize kickoff times: bare time strings like "19:00" → full ISO
    for c in candidates:
        c["kickoff"] = normalize_kickoff(c.get("kickoff", ""), date)

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

    # ENRICHMENT-FIRST: Collect teams with missing data, attempt enrichment before analysis.
    # Previously a "SMART FILTER" dropped ~95% of candidates here. Now ALL candidates
    # proceed to analysis — enrichment fills data gaps, and partial-data events still
    # get analyzed with whatever stats exist.
    total_candidates = len(candidates)
    
    # Phase 1: Detect teams needing enrichment (no safety_markets AND no odds AND not verified)
    needs_enrichment = []
    for c in candidates:
        has_data = c.get("safety_markets") or c.get("n_odds_markets", 0) > 0 or c.get("fixture_verified")
        if not has_data:
            home = c.get("home_team", "")
            away = c.get("away_team", "")
            sport = c.get("sport", "")
            if home and away and sport:
                needs_enrichment.append({"team": home, "sport": sport, "event": c})
                needs_enrichment.append({"team": away, "sport": sport, "event": c})
    
    # Phase 2: Run batch enrichment for missing teams (if any)
    enrichment_results = {}
    if needs_enrichment and not no_enrich:
        # Deduplicate teams
        unique_teams = {}
        for item in needs_enrichment:
            key = f"{item['sport']}|{item['team']}"
            if key not in unique_teams:
                unique_teams[key] = item
        
        enrichment_list = [{"team": v["team"], "sport": v["sport"]} for v in unique_teams.values()]
        print(f"[deep_stats] Enrichment needed for {len(enrichment_list)} teams ({total_candidates - len([c for c in candidates if c.get('safety_markets') or c.get('n_odds_markets', 0) > 0 or c.get('fixture_verified')])} events without data)")
        
        try:
            from data_enrichment_agent import batch_enrich
            enrichment_results = {
                f"{r['sport']}|{r['team']}": r
                for r in batch_enrich(enrichment_list, max_workers=6)
            }
            enriched_count = sum(1 for r in enrichment_results.values() if r.get("status") == "enriched")
            partial_count = sum(1 for r in enrichment_results.values() if r.get("status") == "partial")
            print(f"[deep_stats] Enrichment complete: {enriched_count} enriched, {partial_count} partial, {len(enrichment_results) - enriched_count - partial_count} failed")
        except Exception as e:
            print(f"[deep_stats] Enrichment agent unavailable ({e}), proceeding with existing data")
    
    print(f"[deep_stats] Processing ALL {total_candidates} candidates (no smart filter)")

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
        sm = c.get("safety_markets", [])
        print(f"[deep_stats] [{i}/{len(valid)}] {home} vs {away} ({sport})")
        return analyze_candidate(sport, home, away, comp, kickoff, shortlist_safety_markets=sm or None)

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
        "candidates_without_data": len(analyses) - with_data,
        "enrichment_attempted": len(enrichment_results) if enrichment_results else 0,
        "enrichment_successful": sum(1 for r in enrichment_results.values() if r.get("status") in ("enriched", "partial")) if enrichment_results else 0,
        "analyses": analyses,
    }

    # --- Gemini deep analysis second opinion (feature flag) ---
    if gemini and analyses:
        try:
            from gemini_deep_analyst import analyze_candidate as gemini_analyze, compute_agreement_score
            print(f"[deep_stats] Gemini second opinion for {len(analyses)} candidates...")
            gemini_count = 0
            for a in analyses:
                if not a.get("has_data"):
                    continue
                candidate_dict = {
                    "home_team": a.get("home_team", ""),
                    "away_team": a.get("away_team", ""),
                    "sport": a.get("sport", ""),
                    "competition": a.get("competition", ""),
                    "kickoff": a.get("kickoff", ""),
                }
                try:
                    ga = gemini_analyze(candidate_dict, stats_data=a)
                    if ga:
                        python_top = a.get("best_market", "")
                        python_safety = a.get("data_quality", {}).get("score", 5)
                        agreement = compute_agreement_score(python_top, python_safety, ga)
                        a["gemini_analysis"] = {
                            "recommended_markets": [m.model_dump() for m in ga.recommended_markets] if ga.recommended_markets else [],
                            "upset_risk_score": ga.upset_risk_score,
                            "upset_risk_reasoning": ga.upset_risk_reasoning,
                            "overall_confidence": ga.overall_confidence,
                            "narrative": ga.narrative,
                            "agreement_score": agreement,
                        }
                        gemini_count += 1
                except Exception as e:
                    print(f"[deep_stats] Gemini failed for {candidate_dict.get('home_team')} vs {candidate_dict.get('away_team')}: {e}")
            print(f"[deep_stats] Gemini analysis complete: {gemini_count}/{len(analyses)} candidates")
            output["gemini_analyzed"] = gemini_count
        except ImportError:
            print("[deep_stats] gemini_deep_analyst not available, skipping Gemini second opinion")
        except Exception as e:
            print(f"[deep_stats] Gemini analysis failed (non-fatal): {e}")

    # Write markdown first (doesn't need fixture_ids)
    _write_markdown(output, date)

    # Dual-write: save analysis results to DB FIRST (injects fixture_id back)
    try:
        from db_data_loader import save_analysis_results_to_db
        saved = save_analysis_results_to_db(date, output["analyses"])
        print(f"[deep_stats] DB: saved {saved} analysis results")
    except Exception as e:
        print(f"[deep_stats] DB write failed (non-fatal): {e}")

    # Write JSON AFTER DB save so analyses have fixture_id injected
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
            "data_quality": a.get("data_quality"),
            "best_market": a["best_market"],
            "markets_evaluated": a["markets_evaluated"],
            "stats_a_summary": a["stats_a_summary"],
            "stats_b_summary": a["stats_b_summary"],
            "h2h_summary": a["h2h_summary"],
            "ranking": a["ranking_result"].get("ranking", []),
            "three_way_check": a["ranking_result"].get("three_way_check"),
            "warnings": a["ranking_result"].get("warnings", []),
        }
        # Preserve fixture_id if injected by DB save (needed by S4/S5/S6)
        if a.get("fixture_id"):
            json_entry["fixture_id"] = a["fixture_id"]
        json_output["analyses"].append(json_entry)

    json_path.write_text(
        json.dumps(json_output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[deep_stats] JSON: {json_path}")
    return json_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    from agent_output import AgentOutput, add_agent_args

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
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        default=False,
        help="Skip inline enrichment (use existing cache/DB data only)",
    )
    parser.add_argument(
        "--from-db",
        action="store_true",
        default=False,
        help="Load candidates from DB fixtures table (R2 DB-FIRST, ignores analysis pool JSON)",
    )
    parser.add_argument(
        "--gemini",
        action="store_true",
        default=False,
        help="Enable Gemini deep analysis as second opinion (feature flag P2)",
    )
    add_agent_args(parser)

    args = parser.parse_args()
    out = AgentOutput("s3_deep", verbose=args.verbose, stop_on_error=args.stop_on_error)

    # V5: Input contract pre-check (warning-only, never blocks)
    _contract = AgentOutput.validate_input_contract("s3_deep_stats", args.date)
    if _contract["status"] != "OK":
        for _w in _contract.get("warnings", []):
            out.warning(f"Input contract: {_w}")
        for _m in _contract.get("missing", []):
            out.warning(f"Missing input: {_m}")

    if args.no_enrich:
        os.environ["NO_ENRICH"] = "1"
    result = generate_deep_stats(
        args.date, args.shortlist, args.top,
        no_enrich=args.no_enrich, from_db=args.from_db,
        gemini=args.gemini,
    )

    if args.verbose:
        # Emit per-candidate quality summary for agent
        for a in result.get("analyses", []):
            dq = a.get("data_quality", {})
            out.candidate(
                f"{a.get('home_team', '?')} vs {a.get('away_team', '?')}",
                sport=a.get("sport", "?"),
                has_data=a.get("has_data", False),
                data_quality=dq.get("label", "?"),
                best_market=a.get("best_market", "none"),
                markets_evaluated=a.get("markets_evaluated", 0),
            )

    out.summary(
        verdict="OK" if result["candidates_with_data"] > 0 else "FAILED",
        metrics={
            "total_candidates": result["total_candidates"],
            "with_data": result["candidates_with_data"],
            "without_data": result.get("candidates_without_data", 0),
            "enrichment_attempted": result.get("enrichment_attempted", 0),
            "enrichment_successful": result.get("enrichment_successful", 0),
        },
    )


if __name__ == "__main__":
    main()
