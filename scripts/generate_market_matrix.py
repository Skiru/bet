#!/usr/bin/env python3
"""Generate a comprehensive MARKET MATRIX for ALL discovered fixtures.

This script bridges the gap between fixture discovery (444+ events) and the
analysis pool (which requires cached stats and often produces 0 events).

It produces a FULL DECISION MATRIX showing:
- Every discovered fixture
- ALL available odds markets per fixture (from odds_api_snapshot, multi-source, scan data)
- Stats data when available (from cache)
- Safety scores when calculable
- NO auto-rejection — everything is shown, user decides

Output:
  betting/data/market_matrix_{date}.json
  betting/data/market_matrix_{date}.md  (human-readable matrix)

Usage:
    python3 scripts/generate_market_matrix.py --date 2026-04-29
    python3 scripts/generate_market_matrix.py --date 2026-04-29 --min-odds 1.20 --max-odds 5.00
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "betting" / "data"
CACHE_DIR = DATA_DIR / "stats_cache"

sys.path.insert(0, str(Path(__file__).parent))

try:
    from normalize_stats import build_safety_input_from_cache, SPORT_MARKETS
    from compute_safety_scores import rank_markets
except ImportError:
    build_safety_input_from_cache = None
    rank_markets = None

try:
    from utils import normalize_team_name as _normalize
except ImportError:
    from scripts.utils import normalize_team_name as _normalize


# ---------------------------------------------------------------------------
# Sport key mapping
# ---------------------------------------------------------------------------

def _sport_from_odds_key(sport_key: str) -> str:
    """Convert Odds API sport key to our sport name."""
    if not sport_key:
        return "football"
    sk = sport_key.lower()
    if "soccer" in sk:
        return "football"
    if "basketball" in sk:
        return "basketball"
    if "hockey" in sk or "icehockey" in sk:
        return "hockey"
    if "baseball" in sk:
        return "baseball"
    if "tennis" in sk:
        return "tennis"
    if "mma" in sk:
        return "mma"
    if "handball" in sk:
        return "handball"
    if "volleyball" in sk:
        return "volleyball"
    if "snooker" in sk:
        return "snooker"
    if "darts" in sk:
        return "darts"
    return "football"


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_fixtures(date: str) -> list[dict]:
    """Load discovered fixtures."""
    path = DATA_DIR / f"fixtures_{date}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("fixtures", [])


def load_odds_api_snapshot() -> dict:
    """Load odds API snapshot, return lookup by normalized key."""
    path = DATA_DIR / "odds_api_snapshot.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = []
        if isinstance(data, dict):
            if "events" in data:
                items = data["events"]
            else:
                for v in data.values():
                    if isinstance(v, list):
                        items.extend(v)
        elif isinstance(data, list):
            items = data
        lookup = {}
        for ev in items:
            home = _normalize(ev.get("home_team", ""))
            away = _normalize(ev.get("away_team", ""))
            if home and away:
                lookup[f"{home}|{away}"] = ev
        return lookup
    except (json.JSONDecodeError, OSError):
        return {}


def load_scan_summary() -> dict:
    """Load scan summary items grouped by normalized match key.

    Also returns a flat list of ALL scan items for standalone event creation.
    """
    path = DATA_DIR / "scan_summary.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        match_data = defaultdict(list)
        for url, items in data.items():
            if not isinstance(items, list):
                continue
            for item in items:
                # Extract match identifiers from scan item
                home = item.get("home", item.get("home_team", ""))
                away = item.get("away", item.get("away_team", ""))
                if home and away:
                    key = f"{_normalize(home)}|{_normalize(away)}"
                    match_data[key].append({
                        "source_url": url,
                        "raw": item.get("raw", ""),
                        "odds": item.get("odds", []),
                        "sport": item.get("sport", ""),
                        "league": item.get("league", item.get("competition", "")),
                        "home": home,
                        "away": away,
                        "time": item.get("time"),
                    })
        return dict(match_data)
    except (json.JSONDecodeError, OSError):
        return {}


def load_multi_source_odds() -> dict:
    """Load multi-source odds if available."""
    path = DATA_DIR / "odds_multi_sources.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        lookup = {}
        for ev in data.get("events", []):
            home = _normalize(ev.get("home_team", ""))
            away = _normalize(ev.get("away_team", ""))
            if home and away:
                lookup[f"{home}|{away}"] = ev
        return lookup
    except (json.JSONDecodeError, OSError):
        return {}


def load_picks_suggested() -> dict:
    """Load picks_suggested.json as lookup."""
    path = DATA_DIR / "picks_suggested.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("picks", [])
        lookup = {}
        for p in items:
            match_key = _normalize(p.get("match", ""))
            if match_key:
                lookup[match_key] = p
        return lookup
    except (json.JSONDecodeError, OSError):
        return {}


def load_analysis_pool(date: str) -> dict:
    """Load analysis pool events as lookup."""
    path = DATA_DIR / f"analysis_pool_{date}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        lookup = {}
        for ev in data.get("events", []):
            home = _normalize(ev.get("home_team", ""))
            away = _normalize(ev.get("away_team", ""))
            if home and away:
                lookup[f"{home}|{away}"] = ev
        return lookup
    except (json.JSONDecodeError, OSError):
        return {}


# ---------------------------------------------------------------------------
# Market extraction from odds data
# ---------------------------------------------------------------------------

def extract_markets_from_odds_api(odds_event: dict) -> list[dict]:
    """Extract all markets from an Odds API event with best prices."""
    markets = []
    market_best = defaultdict(lambda: {"price": 0, "bookmaker": "", "outcomes": []})

    for bm in odds_event.get("bookmakers", []):
        bm_name = bm.get("title", bm.get("key", "?"))
        for market in bm.get("markets", []):
            mkey = market.get("key", "")
            for outcome in market.get("outcomes", []):
                oname = outcome.get("name", "")
                point = outcome.get("point")
                price = outcome.get("price", 0)

                if point is not None:
                    outcome_key = f"{mkey}|{oname}|{point}"
                else:
                    outcome_key = f"{mkey}|{oname}"

                if price > market_best[outcome_key]["price"]:
                    market_best[outcome_key] = {
                        "price": price,
                        "bookmaker": bm_name,
                        "market_type": mkey,
                        "outcome": oname,
                        "point": point,
                    }

    for key, data in market_best.items():
        label = data["market_type"]
        if data["point"] is not None:
            label = f"{data['outcome']} {data['point']}"
        else:
            label = f"{data['market_type']}:{data['outcome']}"
        markets.append({
            "market": label,
            "market_type": data["market_type"],
            "outcome": data["outcome"],
            "point": data["point"],
            "best_odds": round(data["price"], 2),
            "best_bookmaker": data["bookmaker"],
            "source": "odds-api",
        })

    return markets


def extract_markets_from_scan(scan_items: list[dict]) -> list[dict]:
    """Extract odds/market hints from scan summary items."""
    markets = []
    seen = set()
    for item in scan_items:
        odds_list = item.get("odds", [])
        source_url = item.get("source_url", "")

        # Determine source domain for labeling
        source_domain = ""
        if source_url:
            try:
                source_domain = urlparse(source_url).netloc.replace("www.", "")
            except Exception:
                source_domain = source_url

        # Map odds positions to market types based on count
        # 3 odds = 1X2 (football, handball), 2 odds = ML (tennis, basketball, hockey)
        if len(odds_list) == 3:
            labels = ["1X2:Home", "1X2:Draw", "1X2:Away"]
        elif len(odds_list) == 2:
            labels = ["ML:Home", "ML:Away"]
        else:
            labels = [f"scan_odd_{i + 1}" for i in range(len(odds_list))]

        for i, odd in enumerate(odds_list):
            try:
                price = float(odd)
                if 1.01 < price < 50.0:
                    label = labels[i] if i < len(labels) else f"scan_odd_{i + 1}"
                    market_key = f"{source_domain}|{label}"
                    if market_key not in seen:
                        seen.add(market_key)
                        markets.append({
                            "market": label,
                            "market_type": "h2h" if "ML" in label or "1X2" in label else "scan",
                            "outcome": label.split(":")[-1] if ":" in label else label,
                            "point": None,
                            "best_odds": round(price, 2),
                            "best_bookmaker": source_domain,
                            "source": f"scan:{source_domain}",
                        })
            except (ValueError, TypeError):
                pass

    return markets


# ---------------------------------------------------------------------------
# Safety score integration (when cache is available)
# ---------------------------------------------------------------------------

def try_safety_analysis(sport: str, home: str, away: str, competition: str) -> dict | None:
    """Try to build safety analysis from cache. Return None on cache miss."""
    if not build_safety_input_from_cache or not rank_markets:
        return None
    try:
        safety_input = build_safety_input_from_cache(sport, home, away, competition)
        if safety_input is None:
            return None
        result = rank_markets(safety_input)
        if not result or not result.get("ranking"):
            return None
        return result
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main matrix generator
# ---------------------------------------------------------------------------

def generate_market_matrix(
    date: str,
    min_odds: float = 1.10,
    max_odds: float = 10.0,
    evening_only: bool = False,
) -> dict:
    """Generate comprehensive market matrix for all fixtures on date.

    Returns dict with:
    - metadata (date, counts, generation time)
    - events: list of event dicts, each with ALL available markets
    """
    print(f"[matrix] Loading data for {date}...")

    fixtures = load_fixtures(date)
    odds_lookup = load_odds_api_snapshot()
    scan_lookup = load_scan_summary()
    multi_odds = load_multi_source_odds()
    picks_suggested = load_picks_suggested()
    analysis_pool = load_analysis_pool(date)

    print(f"[matrix] Fixtures: {len(fixtures)}")
    print(f"[matrix] Odds API events: {len(odds_lookup)}")
    print(f"[matrix] Scan summary keys: {len(scan_lookup)}")
    print(f"[matrix] Multi-source events: {len(multi_odds)}")
    print(f"[matrix] Analysis pool events: {len(analysis_pool)}")

    # Build a set of normalized fixture keys for dedup
    fixture_keys = set()
    for fixture in fixtures:
        home = fixture.get("home_team", fixture.get("home", ""))
        away = fixture.get("away_team", fixture.get("away", ""))
        if home and away:
            fixture_keys.add(f"{_normalize(home)}|{_normalize(away)}")

    # AGGRESSIVE EXPANSION: Add scan summary events that have home/away + odds
    # but are NOT already in fixtures (these are events from Betclic, Flashscore,
    # BetExplorer etc. that the API fixture discovery didn't find)
    scan_only_events = 0
    for match_key, scan_items in scan_lookup.items():
        # Skip if already a fixture
        if match_key in fixture_keys:
            continue

        # Check if any item has odds (meaning this event is bettable)
        best_item = None
        best_odds_count = 0
        for item in scan_items:
            odds_count = len(item.get("odds", []))
            if odds_count > best_odds_count:
                best_odds_count = odds_count
                best_item = item
            elif not best_item:
                best_item = item

        if best_item and best_item.get("home") and best_item.get("away"):
            home = best_item["home"]
            away = best_item["away"]

            # Filter out non-match items (ads, page elements, tips, etc.)
            # A valid match needs: real team names (>2 chars each), not promo text
            if len(home) < 3 or len(away) < 3:
                continue
            skip_patterns = [
                "bonus", "free", "bet $", "get $", "sign up", "promo", "code ",
                "wyniki", "mecze", "typy dnia", "tips", "picks", "odds &",
                "best bets", "predictions", "opening odds", "season has",
                "analysis link", "confidence level", "line-ups", "overview",
                "head-to-head", "expert", "win tips", "correct score",
                "handicap tips", "shots tips", "behind tips",
                "#", "pln za", "transmisja", "gdzie oglądać", "stream",
            ]
            combined = f"{home} {away}".lower()
            if any(pat in combined for pat in skip_patterns):
                continue
            # Skip items where "home" is actually a league/tip label
            if home.startswith(("HOLANDIA:", "FINLANDIA:", "IZRAEL:", "Liga ")):
                continue

            fixture = {
                "sport": best_item.get("sport", "football"),
                "home_team": home,
                "away_team": away,
                "competition": best_item.get("league", ""),
                "kickoff": best_item.get("time", ""),
                "source": "scan-expansion",
            }
            fixtures.append(fixture)
            fixture_keys.add(match_key)
            scan_only_events += 1

    # Also add Odds API events not in fixtures
    odds_only_events = 0
    for okey, oev in odds_lookup.items():
        if okey not in fixture_keys:
            home = oev.get("home_team", "")
            away = oev.get("away_team", "")
            if home and away:
                fixture = {
                    "sport": _sport_from_odds_key(oev.get("sport_key", "")),
                    "home_team": home,
                    "away_team": away,
                    "competition": oev.get("sport_title", ""),
                    "kickoff": oev.get("commence_time", ""),
                    "source": "odds-api-expansion",
                }
                fixtures.append(fixture)
                fixture_keys.add(okey)
                odds_only_events += 1

    print(f"[matrix] Scan-only events added: {scan_only_events}")
    print(f"[matrix] Odds-API-only events added: {odds_only_events}")
    print(f"[matrix] Total events after expansion: {len(fixtures)}")

    events = []
    sport_counts = defaultdict(int)
    market_type_counts = defaultdict(int)

    for fixture in fixtures:
        sport = fixture.get("sport", "football")
        home = fixture.get("home_team", fixture.get("home", ""))
        away = fixture.get("away_team", fixture.get("away", ""))
        competition = fixture.get("competition", fixture.get("league", ""))
        kickoff = fixture.get("kickoff", fixture.get("date", ""))
        source = fixture.get("source", "")

        if not home or not away:
            continue

        # Evening filter
        if evening_only and kickoff:
            try:
                hour = int(kickoff.split("T")[1].split(":")[0]) if "T" in kickoff else 0
                if hour < 17:
                    continue
            except (IndexError, ValueError):
                pass

        norm_home = _normalize(home)
        norm_away = _normalize(away)
        match_key = f"{norm_home}|{norm_away}"

        # Collect ALL available markets from ALL sources
        all_markets = []

        # 1. Odds API markets
        odds_event = _fuzzy_match(match_key, odds_lookup)
        if odds_event:
            api_markets = extract_markets_from_odds_api(odds_event)
            all_markets.extend(api_markets)

        # 2. Multi-source odds
        multi_event = _fuzzy_match(match_key, multi_odds)
        if multi_event:
            best_odds = multi_event.get("best_odds", {})
            for mkt_key, mkt_data in best_odds.items():
                if isinstance(mkt_data, dict):
                    all_markets.append({
                        "market": mkt_key,
                        "market_type": "multi",
                        "outcome": mkt_key,
                        "point": None,
                        "best_odds": mkt_data.get("price", 0),
                        "best_bookmaker": mkt_data.get("bookmaker", ""),
                        "source": "multi-source",
                    })

        # 3. Scan summary data
        scan_items = _fuzzy_match(match_key, scan_lookup)
        if scan_items and isinstance(scan_items, list):
            scan_markets = extract_markets_from_scan(scan_items)
            all_markets.extend(scan_markets)

        # 4. Safety analysis from cache (deep stats when available)
        safety_result = try_safety_analysis(sport, home, away, competition)
        safety_markets = []
        if safety_result:
            for mkt in safety_result.get("ranking", []):
                safety_markets.append({
                    "market": f"{mkt['name']} {mkt.get('line', '')}",
                    "market_type": "safety_ranked",
                    "direction": mkt.get("direction", ""),
                    "safety_score": mkt.get("safety_score", 0),
                    "l10_avg": mkt.get("combined_avg"),
                    "h2h_avg": mkt.get("h2h_avg"),
                    "hit_rate_l10": mkt.get("hit_rate_l10"),
                    "hit_rate_h2h": mkt.get("hit_rate_h2h"),
                    "margin": mkt.get("margin"),
                    "h2h_blind": mkt.get("h2h_blind", False),
                    "source": "stats_cache",
                })

        # 5. Check picks_suggested for pre-computed suggestions
        suggested = _fuzzy_match_single(match_key, picks_suggested)
        suggested_info = None
        if suggested:
            suggested_info = {
                "suggested_pick": suggested.get("pick", ""),
                "suggested_odds": suggested.get("odds", 0),
                "source_count": suggested.get("source_count", 0),
            }

        # 6. Analysis pool deep data
        pool_event = _fuzzy_match(match_key, analysis_pool)
        pool_markets = []
        if pool_event:
            for pmkt in pool_event.get("all_markets", []):
                pool_markets.append({
                    "market": pmkt.get("name", ""),
                    "market_type": "analysis_pool",
                    "direction": pmkt.get("direction", ""),
                    "safety_score": pmkt.get("safety", 0),
                    "l10_avg": pmkt.get("l10_avg"),
                    "h2h_avg": pmkt.get("h2h_avg"),
                    "source": "analysis_pool",
                })

        # Determine data richness
        has_odds = bool(all_markets)
        has_safety = bool(safety_markets or pool_markets)
        has_multiple_sources = len(set(m.get("source", "") for m in all_markets)) > 1

        if has_safety and has_odds:
            data_tier = "FULL"
        elif has_odds and has_multiple_sources:
            data_tier = "ODDS_RICH"
        elif has_odds:
            data_tier = "ODDS_BASIC"
        elif has_safety:
            data_tier = "STATS_ONLY"
        else:
            data_tier = "FIXTURE_ONLY"

        sport_counts[sport] += 1

        for m in all_markets:
            mt = m.get("market_type", "unknown")
            market_type_counts[mt] += 1

        event = {
            "sport": sport,
            "competition": competition,
            "home_team": home,
            "away_team": away,
            "kickoff": kickoff,
            "data_tier": data_tier,
            "fixture_source": source,
            "odds_markets": all_markets,
            "safety_markets": safety_markets + pool_markets,
            "suggested": suggested_info,
            "total_markets_available": len(all_markets) + len(safety_markets) + len(pool_markets),
        }
        events.append(event)

    # Sort: FULL first, then ODDS_RICH, then by sport
    tier_order = {"FULL": 0, "ODDS_RICH": 1, "ODDS_BASIC": 2, "STATS_ONLY": 3, "FIXTURE_ONLY": 4}
    events.sort(key=lambda e: (tier_order.get(e["data_tier"], 5), e["sport"], e["competition"]))

    matrix = {
        "date": date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_fixtures": len(fixtures),
        "total_events_in_matrix": len(events),
        "events_with_odds": sum(1 for e in events if e["odds_markets"]),
        "events_with_safety_data": sum(1 for e in events if e["safety_markets"]),
        "sport_breakdown": dict(sport_counts),
        "market_type_counts": dict(market_type_counts),
        "data_tier_breakdown": {
            tier: sum(1 for e in events if e["data_tier"] == tier)
            for tier in ["FULL", "ODDS_RICH", "ODDS_BASIC", "STATS_ONLY", "FIXTURE_ONLY"]
        },
        "events": events,
    }

    return matrix


def _fuzzy_match(key: str, lookup: dict):
    """Fuzzy match a key against a lookup dict."""
    if key in lookup:
        return lookup[key]
    # Try substring matching
    parts = key.split("|")
    if len(parts) != 2:
        return None
    home, away = parts
    for lk, lv in lookup.items():
        lparts = lk.split("|")
        if len(lparts) != 2:
            continue
        lhome, laway = lparts
        if ((home in lhome or lhome in home) and len(home) >= 3 and
                (away in laway or laway in away) and len(away) >= 3):
            return lv
    return None


def _fuzzy_match_single(key: str, lookup: dict):
    """Fuzzy match for picks_suggested which uses space-separated keys."""
    # Try direct
    for lk, lv in lookup.items():
        norm_lk = lk.replace(" - ", "|").replace(" vs ", "|")
        if _normalize(norm_lk) == key or key in norm_lk or norm_lk in key:
            return lv
    return None


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------

def write_matrix_markdown(matrix: dict, date: str) -> Path:
    """Write human-readable market matrix."""
    lines = []
    lines.append(f"# 📊 Market Matrix — {date}")
    lines.append(f"Generated: {matrix['generated_at']}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Total fixtures discovered: **{matrix['total_fixtures']}**")
    lines.append(f"- Events in matrix: **{matrix['total_events_in_matrix']}**")
    lines.append(f"- Events WITH odds: **{matrix['events_with_odds']}**")
    lines.append(f"- Events with safety data: **{matrix['events_with_safety_data']}**")
    lines.append("")

    lines.append("### Sport Breakdown")
    lines.append("| Sport | Count |")
    lines.append("|-------|-------|")
    for sport, count in sorted(matrix["sport_breakdown"].items(), key=lambda x: -x[1]):
        lines.append(f"| {sport} | {count} |")
    lines.append("")

    lines.append("### Data Tier Breakdown")
    lines.append("| Tier | Count | Description |")
    lines.append("|------|-------|-------------|")
    tier_desc = {
        "FULL": "Odds + Safety stats + H2H",
        "ODDS_RICH": "Odds from multiple sources",
        "ODDS_BASIC": "Odds from single source",
        "STATS_ONLY": "Safety stats but no odds",
        "FIXTURE_ONLY": "Fixture discovered, no odds/stats yet",
    }
    for tier in ["FULL", "ODDS_RICH", "ODDS_BASIC", "STATS_ONLY", "FIXTURE_ONLY"]:
        count = matrix["data_tier_breakdown"].get(tier, 0)
        lines.append(f"| {tier} | {count} | {tier_desc.get(tier, '')} |")
    lines.append("")

    # Group events by sport
    by_sport = defaultdict(list)
    for event in matrix["events"]:
        by_sport[event["sport"]].append(event)

    lines.append("---")
    lines.append("")

    for sport in sorted(by_sport.keys()):
        sport_events = by_sport[sport]
        lines.append(f"## {sport.upper()} ({len(sport_events)} events)")
        lines.append("")

        for event in sport_events:
            home = event["home_team"]
            away = event["away_team"]
            comp = event["competition"]
            kickoff = event["kickoff"]
            tier = event["data_tier"]
            total_mkts = event["total_markets_available"]

            tier_emoji = {
                "FULL": "🟢", "ODDS_RICH": "🔵", "ODDS_BASIC": "🟡",
                "STATS_ONLY": "🟠", "FIXTURE_ONLY": "⚪"
            }

            lines.append(f"### {tier_emoji.get(tier, '⚪')} {home} vs {away}")
            lines.append(f"**{comp}** | {kickoff} | Tier: {tier} | Markets: {total_mkts}")
            lines.append("")

            # Odds markets table
            if event["odds_markets"]:
                lines.append("| Market | Odds | Bookmaker | Source |")
                lines.append("|--------|------|-----------|--------|")
                for mkt in event["odds_markets"]:
                    lines.append(
                        f"| {mkt['market']} | {mkt['best_odds']} | "
                        f"{mkt['best_bookmaker']} | {mkt['source']} |"
                    )
                lines.append("")

            # Safety markets table
            if event["safety_markets"]:
                lines.append("| Market | Direction | Safety | L10 avg | H2H avg | Hit L10 | Hit H2H | H2H Blind |")
                lines.append("|--------|-----------|--------|---------|---------|---------|---------|-----------|")
                for mkt in event["safety_markets"]:
                    h2h_avg = mkt.get("h2h_avg", "N/A")
                    lines.append(
                        f"| {mkt['market']} | {mkt.get('direction', '—')} | "
                        f"{mkt.get('safety_score', '—')} | {mkt.get('l10_avg', '—')} | "
                        f"{h2h_avg} | {mkt.get('hit_rate_l10', '—')} | "
                        f"{mkt.get('hit_rate_h2h', '—')} | "
                        f"{'YES' if mkt.get('h2h_blind') else 'NO'} |"
                    )
                lines.append("")

            if event.get("suggested"):
                s = event["suggested"]
                lines.append(
                    f"> 💡 Suggested: **{s['suggested_pick']}** @ {s['suggested_odds']} "
                    f"(sources: {s['source_count']})"
                )
                lines.append("")

            lines.append("---")
            lines.append("")

    md_text = "\n".join(lines)
    output_path = DATA_DIR / f"market_matrix_{date}.md"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md_text, encoding="utf-8")
    print(f"[matrix] Markdown: {output_path}")
    return output_path


def write_matrix_json(matrix: dict, date: str) -> Path:
    """Write matrix JSON."""
    output_path = DATA_DIR / f"market_matrix_{date}.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(matrix, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[matrix] JSON: {output_path} ({matrix['total_events_in_matrix']} events)")
    return output_path


# ---------------------------------------------------------------------------
# Compact decision matrix for coupon building
# ---------------------------------------------------------------------------

def generate_decision_matrix(matrix: dict, min_odds: float = 1.20, max_odds: float = 5.0) -> list[dict]:
    """Generate a compact decision matrix from the full market matrix.

    Returns a list of bettable opportunities (event + market combinations)
    sorted by data quality and odds attractiveness.
    """
    opportunities = []

    for event in matrix["events"]:
        sport = event["sport"]
        home = event["home_team"]
        away = event["away_team"]
        comp = event["competition"]
        kickoff = event["kickoff"]
        tier = event["data_tier"]

        # Each odds market = one opportunity
        for mkt in event.get("odds_markets", []):
            odds = mkt.get("best_odds", 0)
            if not (min_odds <= odds <= max_odds):
                continue

            # Find matching safety data if available
            safety_data = None
            for sm in event.get("safety_markets", []):
                sm_name = sm.get("market", "").lower()
                mkt_name = mkt.get("market", "").lower()
                if any(word in sm_name for word in mkt_name.split()):
                    safety_data = sm
                    break

            opp = {
                "sport": sport,
                "competition": comp,
                "event": f"{home} vs {away}",
                "home_team": home,
                "away_team": away,
                "kickoff": kickoff,
                "market": mkt["market"],
                "market_type": mkt["market_type"],
                "odds": odds,
                "bookmaker": mkt["best_bookmaker"],
                "data_tier": tier,
                "safety_score": safety_data["safety_score"] if safety_data else None,
                "l10_avg": safety_data.get("l10_avg") if safety_data else None,
                "h2h_avg": safety_data.get("h2h_avg") if safety_data else None,
                "direction": safety_data.get("direction") if safety_data else None,
            }
            opportunities.append(opp)

        # Also add safety-only markets (no odds yet — user can check Betclic)
        for sm in event.get("safety_markets", []):
            if sm.get("safety_score", 0) >= 0.50:
                opp = {
                    "sport": sport,
                    "competition": comp,
                    "event": f"{home} vs {away}",
                    "home_team": home,
                    "away_team": away,
                    "kickoff": kickoff,
                    "market": sm["market"],
                    "market_type": "safety_ranked",
                    "odds": None,  # User needs to check Betclic
                    "bookmaker": "check_betclic",
                    "data_tier": tier,
                    "safety_score": sm.get("safety_score"),
                    "l10_avg": sm.get("l10_avg"),
                    "h2h_avg": sm.get("h2h_avg"),
                    "direction": sm.get("direction"),
                }
                opportunities.append(opp)

    # Sort by: safety_score (desc, Nones last), then odds
    opportunities.sort(
        key=lambda o: (
            -(o["safety_score"] or 0),
            o["odds"] or 999,
        )
    )

    return opportunities


def write_decision_matrix_md(opportunities: list[dict], date: str) -> Path:
    """Write compact decision matrix markdown."""
    lines = []
    lines.append(f"# 🎯 Decision Matrix — {date}")
    lines.append(f"Total bettable opportunities: **{len(opportunities)}**")
    lines.append("")
    lines.append("> ⚠️ ALL picks shown — no auto-rejection. User decides. EV not pre-filtered.")
    lines.append("")

    # Group by sport
    by_sport = defaultdict(list)
    for opp in opportunities:
        by_sport[opp["sport"]].append(opp)

    for sport in sorted(by_sport.keys()):
        sport_opps = by_sport[sport]
        lines.append(f"## {sport.upper()} ({len(sport_opps)} opportunities)")
        lines.append("")
        lines.append(
            "| # | Event | Competition | Market | Odds | Safety | L10 | H2H | Dir | Tier |"
        )
        lines.append(
            "|---|-------|-------------|--------|------|--------|-----|-----|-----|------|"
        )
        for i, opp in enumerate(sport_opps, 1):
            odds_str = f"{opp['odds']:.2f}" if opp["odds"] else "CHECK"
            safety_str = f"{opp['safety_score']:.2f}" if opp["safety_score"] else "—"
            l10_str = f"{opp['l10_avg']}" if opp["l10_avg"] is not None else "—"
            h2h_str = f"{opp['h2h_avg']}" if opp["h2h_avg"] is not None else "—"
            dir_str = opp["direction"] or "—"
            lines.append(
                f"| {i} | {opp['event']} | {opp['competition']} | "
                f"{opp['market']} | {odds_str} | {safety_str} | "
                f"{l10_str} | {h2h_str} | {dir_str} | {opp['data_tier']} |"
            )
        lines.append("")

    md_text = "\n".join(lines)
    output_path = DATA_DIR / f"decision_matrix_{date}.md"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md_text, encoding="utf-8")
    print(f"[matrix] Decision matrix: {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate comprehensive market matrix")
    parser.add_argument("--date", help="Date YYYY-MM-DD (default: today)")
    parser.add_argument("--min-odds", type=float, default=1.20, help="Min odds filter")
    parser.add_argument("--max-odds", type=float, default=5.00, help="Max odds filter")
    parser.add_argument("--evening-only", action="store_true", help="Only events after 17:00")
    args = parser.parse_args()

    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        print(f"[matrix] ERROR: Invalid date format '{date}'. Use YYYY-MM-DD.")
        sys.exit(1)

    print(f"[matrix] Generating market matrix for {date}...")

    matrix = generate_market_matrix(
        date=date,
        min_odds=args.min_odds,
        max_odds=args.max_odds,
        evening_only=args.evening_only,
    )

    write_matrix_json(matrix, date)
    write_matrix_markdown(matrix, date)

    opportunities = generate_decision_matrix(matrix, args.min_odds, args.max_odds)
    write_decision_matrix_md(opportunities, date)

    # Print summary
    print(f"\n{'='*60}")
    print(f"MARKET MATRIX SUMMARY — {date}")
    print(f"{'='*60}")
    print(f"Total fixtures:          {matrix['total_fixtures']}")
    print(f"Events in matrix:        {matrix['total_events_in_matrix']}")
    print(f"Events with odds:        {matrix['events_with_odds']}")
    print(f"Events with safety data: {matrix['events_with_safety_data']}")
    print(f"Bettable opportunities:  {len(opportunities)}")
    print(f"\nSport breakdown:")
    for sport, count in sorted(matrix["sport_breakdown"].items(), key=lambda x: -x[1]):
        print(f"  {sport}: {count}")
    print(f"\nData tier breakdown:")
    for tier, count in matrix["data_tier_breakdown"].items():
        if count > 0:
            print(f"  {tier}: {count}")


if __name__ == "__main__":
    main()
