#!/usr/bin/env python3
"""Gemini News Enrichment — injury reports, team news, coaching changes via Search Grounding.

Fills the L2.5 gap in the pipeline — provides structured news/injury data
that feeds into context_checks.py (S5) for context flags.

Feature flag: Controlled by --news flag in data_enrichment_agent.py.
Skipped when Gemini is not configured or budget exceeded.

Usage:
    python3 scripts/gemini_news_enrichment.py --team "Arsenal" --sport football --date 2026-05-12
    python3 scripts/gemini_news_enrichment.py --date 2026-05-12 --verbose
"""

import argparse
import datetime
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from bet.schemas.gemini_responses import NewsEnrichmentResult, InjuryReport
from bet.db.connection import get_db
from bet.api_clients.gemini_client import GeminiClient, GeminiNotConfiguredError, GeminiError

logger = logging.getLogger(__name__)

DATA_DIR = ROOT_DIR / "betting" / "data"

NEWS_PROMPT_TEMPLATE = """Search for the latest team news and injury updates for {team} ({sport}).

Return structured information about:
1. INJURIES: Player name, status (out/doubtful/questionable/probable), injury type, expected return date, impact level (critical/high/medium/low)
2. RECENT NEWS: Important team news from the last 7 days (transfers, lineup changes, contract situations)
3. COACHING: Any coaching changes, tactical shifts, or formation changes
4. MORALE: Team morale indicators (winning streak, fan support, internal conflicts, contract disputes)

Only include factual, sourced information. Prefer: espn.com, flashscore.com, 
transfermarkt.com, official team sites. Date: {date}."""


def enrich_team_news(
    team: str,
    sport: str,
    date: str,
) -> NewsEnrichmentResult:
    """Fetch current news, injuries, and coaching changes for a team.

    Uses Gemini with search grounding to find and structure team news.
    Results saved to DB for downstream use by context_checks.py (S5).
    """
    try:
        client = GeminiClient()
    except Exception:
        logger.warning(f"[{team}] Gemini not available for news enrichment")
        return NewsEnrichmentResult(team_name=team, sport=sport)

    prompt = NEWS_PROMPT_TEMPLATE.format(team=team, sport=sport, date=date)

    try:
        response = client.search_grounded_query(prompt=prompt)
        text = response.text or ""

        # Parse structured data from response
        injuries = _parse_injuries(text)
        news = _parse_news(text)
        coaching = _parse_coaching(text)
        morale = _parse_morale(text)
        sources = [s.get("uri", "") for s in response.search_results if s.get("uri")]

        result = NewsEnrichmentResult(
            team_name=team,
            sport=sport,
            injuries=injuries,
            recent_news=news,
            coaching_changes=coaching,
            morale_indicators=morale,
            sources=sources,
            confidence=_calculate_confidence(response),
        )

        logger.info(
            f"[{team}] News: {len(injuries)} injuries, {len(news)} news items, "
            f"confidence={result.confidence:.2f}"
        )
        return result

    except GeminiNotConfiguredError:
        logger.warning("Gemini not configured")
        return NewsEnrichmentResult(team_name=team, sport=sport)
    except GeminiError as e:
        logger.error(f"[{team}] Gemini error: {e}")
        return NewsEnrichmentResult(team_name=team, sport=sport)
    except Exception as e:
        logger.error(f"[{team}] Unexpected error: {e}")
        return NewsEnrichmentResult(team_name=team, sport=sport)


def batch_enrich_news(
    candidates: list[dict],
    date: str,
    max_workers: int = 2,
) -> list[NewsEnrichmentResult]:
    """Batch news enrichment for all candidates in shortlist.

    Deduplicates teams across fixtures. Rate-limited via GeminiClient.
    """
    # Deduplicate teams
    seen_teams = set()
    teams_to_enrich = []
    for c in candidates:
        for team_key in ["home_team", "away_team", "team_a", "team_b"]:
            team = c.get(team_key, "")
            sport = c.get("sport", "football")
            if team and team not in seen_teams:
                seen_teams.add(team)
                teams_to_enrich.append({"team": team, "sport": sport})

    logger.info(f"Enriching news for {len(teams_to_enrich)} unique teams")

    results = []
    success_count = 0
    empty_count = 0
    error_count = 0
    # Sequential to respect rate limits (Gemini search is expensive)
    for item in teams_to_enrich:
        result = enrich_team_news(item["team"], item["sport"], date)
        results.append(result)
        if result.injuries or result.recent_news:
            success_count += 1
        elif result.confidence == 0:
            error_count += 1
        else:
            empty_count += 1

    logger.info(
        f"News enrichment complete: {success_count} with data, "
        f"{empty_count} empty, {error_count} errors out of {len(teams_to_enrich)} teams"
    )

    return results


def save_news_to_db(results: list[NewsEnrichmentResult], date: str) -> int:
    """Save news enrichment results to team_news DB table.

    Returns count of saved records.
    """
    saved = 0
    try:
        with get_db() as conn:
            for r in results:
                if not r.injuries and not r.recent_news:
                    continue  # Skip empty results

                # Resolve team_id and sport_id (best effort)
                team_row = conn.execute(
                    "SELECT id FROM teams WHERE LOWER(name) = LOWER(?) LIMIT 1",
                    (r.team_name,),
                ).fetchone()
                sport_row = conn.execute(
                    "SELECT id FROM sports WHERE LOWER(name) = LOWER(?) LIMIT 1",
                    (r.sport or "football",),
                ).fetchone()

                team_id = team_row["id"] if team_row else 0
                sport_id = sport_row["id"] if sport_row else 1

                now = datetime.datetime.now(datetime.timezone.utc).isoformat()

                conn.execute(
                    """INSERT OR REPLACE INTO team_news
                    (team_id, sport_id, betting_date, injuries_json, news_json,
                     coaching_json, morale_json, sources_json, confidence, fetched_at, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        team_id,
                        sport_id,
                        date,
                        json.dumps([i.model_dump() for i in r.injuries]),
                        json.dumps(r.recent_news),
                        json.dumps(r.coaching_changes),
                        json.dumps(r.morale_indicators),
                        json.dumps(r.sources),
                        r.confidence,
                        now,
                        "gemini",
                    ),
                )
                saved += 1
    except Exception as e:
        logger.error(f"DB save error: {e}")

    logger.info(f"Saved {saved} team news records to DB")
    return saved


def _parse_injuries(text: str) -> list[InjuryReport]:
    """Parse injury reports from Gemini response text."""
    injuries = []
    if not text:
        return injuries

    # Look for injury-related content
    in_injury_section = False
    for line in text.split("\n"):
        line = line.strip()
        line_lower = line.lower()

        # Detect injury section headers
        if any(kw in line_lower for kw in ["injur", "squad news", "team news", "absent"]):
            in_injury_section = True
            continue

        # Detect section change
        if in_injury_section and line.startswith("#"):
            in_injury_section = False
            continue

        if not in_injury_section or not line:
            continue

        # Try to parse player injury from line
        line_clean = line.lstrip("-*•> ").strip()
        if len(line_clean) < 5:
            continue

        # Determine status from keywords
        status = "doubtful"
        if any(kw in line_lower for kw in ["out", "ruled out", "sidelined", "miss"]):
            status = "out"
        elif any(kw in line_lower for kw in ["doubtful", "doubt", "uncertain"]):
            status = "doubtful"
        elif any(kw in line_lower for kw in ["questionable", "50-50", "fitness test"]):
            status = "questionable"
        elif any(kw in line_lower for kw in ["probable", "expected to play", "available"]):
            status = "probable"

        # Determine impact
        impact = "medium"
        if any(kw in line_lower for kw in ["key player", "captain", "star", "top scorer"]):
            impact = "critical"
        elif any(kw in line_lower for kw in ["starter", "regular", "important"]):
            impact = "high"

        # Use first part as player name (heuristic)
        parts = line_clean.split("—") if "—" in line_clean else line_clean.split("-", 1)
        player_name = parts[0].strip()[:50]  # Cap length

        injuries.append(InjuryReport(
            player_name=player_name,
            status=status,
            injury_type="",
            expected_return="",
            impact=impact,
            source="gemini-search",
        ))

    return injuries[:15]  # Cap at 15


def _parse_news(text: str) -> list[str]:
    """Parse recent news items from Gemini response."""
    if not text:
        return []
    news = []
    in_news = False
    for line in text.split("\n"):
        line = line.strip()
        if any(kw in line.lower() for kw in ["recent news", "team news", "latest"]):
            in_news = True
            continue
        if in_news and line.startswith("#"):
            in_news = False
            continue
        if in_news and line and len(line) > 10:
            news.append(line.lstrip("-*•> ").strip())
    return news[:10]


def _parse_coaching(text: str) -> list[str]:
    """Parse coaching changes from Gemini response."""
    if not text:
        return []
    items = []
    for line in text.split("\n"):
        line_lower = line.lower().strip()
        if any(kw in line_lower for kw in ["coach", "manager", "tactical", "formation"]):
            clean = line.strip().lstrip("-*•> ")
            if len(clean) > 10:
                items.append(clean)
    return items[:5]


def _parse_morale(text: str) -> list[str]:
    """Parse morale indicators from Gemini response."""
    if not text:
        return []
    items = []
    keywords = ["morale", "confidence", "streak", "momentum", "spirit", "pressure", "tension"]
    for line in text.split("\n"):
        if any(kw in line.lower() for kw in keywords):
            clean = line.strip().lstrip("-*•> ")
            if len(clean) > 10:
                items.append(clean)
    return items[:5]


def _calculate_confidence(response) -> float:
    """Calculate confidence score from response quality."""
    score = 0.3
    if response.search_results:
        score += min(len(response.search_results) * 0.1, 0.3)
    if response.text and len(response.text) > 300:
        score += 0.2
    if response.thoughts:
        score += 0.1
    return min(score, 1.0)


def main():
    parser = argparse.ArgumentParser(description="Gemini News Enrichment")
    parser.add_argument("--team", help="Single team to enrich")
    parser.add_argument("--sport", default="football")
    parser.add_argument("--date", default=datetime.datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--shortlist", help="Path to shortlist JSON for batch mode")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    if args.team:
        results = [enrich_team_news(args.team, args.sport, args.date)]
    elif args.shortlist:
        shortlist_path = Path(args.shortlist)
        if not shortlist_path.exists():
            # Try date-based default
            shortlist_path = DATA_DIR / f"{args.date}_s2_shortlist.json"
        if shortlist_path.exists():
            data = json.loads(shortlist_path.read_text(encoding="utf-8"))
            candidates = data.get("candidates", data.get("shortlist", []))
            results = batch_enrich_news(candidates, args.date)
        else:
            print(f"ERROR: Shortlist not found at {shortlist_path}", file=sys.stderr)
            sys.exit(1)
    else:
        # Default: load today's shortlist
        shortlist_path = DATA_DIR / f"{args.date}_s2_shortlist.json"
        if shortlist_path.exists():
            data = json.loads(shortlist_path.read_text(encoding="utf-8"))
            candidates = data.get("candidates", data.get("shortlist", []))
            results = batch_enrich_news(candidates, args.date)
        else:
            print("ERROR: Provide --team or ensure shortlist exists", file=sys.stderr)
            sys.exit(1)

    # Save to DB
    saved = save_news_to_db(results, args.date)

    # Report
    total_injuries = sum(len(r.injuries) for r in results)
    total_news = sum(len(r.recent_news) for r in results)
    teams_with_data = sum(1 for r in results if r.injuries or r.recent_news)

    if args.verbose:
        for r in results:
            if r.injuries or r.recent_news:
                print(json.dumps(r.model_dump(), ensure_ascii=False, indent=2))

    summary = {
        "verdict": "OK" if teams_with_data > 0 else "PARTIAL",
        "teams_processed": len(results),
        "teams_with_data": teams_with_data,
        "total_injuries": total_injuries,
        "total_news": total_news,
        "saved_to_db": saved,
    }
    print(f"AGENT_SUMMARY:{json.dumps(summary)}")


if __name__ == "__main__":
    main()
