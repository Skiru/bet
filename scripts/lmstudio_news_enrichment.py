#!/usr/bin/env python3
"""LM Studio News Enrichment — injuries, team news, coaching changes via Brave Search.

Two-step: Brave Search API fetches news → LM Studio structures the data.
Replaces gemini_news_enrichment.py (which used Gemini Search Grounding).

Usage:
    python3 scripts/lmstudio_news_enrichment.py --team "Arsenal" --sport football --date 2026-05-27
    python3 scripts/lmstudio_news_enrichment.py --date 2026-05-27 --verbose
"""

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from bet.resilience import atomic_json_write
from bet.schemas.gemini_responses import NewsEnrichmentResult, InjuryReport
from bet.db.connection import get_db
from bet.api_clients.lmstudio_client import LMStudioClient, LMStudioNotAvailableError, LMStudioError
from bet.api_clients.brave_search_client import BraveSearchClient

logger = logging.getLogger(__name__)

DATA_DIR = ROOT_DIR / "betting" / "data"

STRUCTURING_PROMPT = """You are a sports news analyst. Given raw news search results about a team,
extract and structure the following information:

1. INJURIES: Player name, status (out/doubtful/questionable/probable), injury type, expected return, 
   impact level (critical/high/medium/low)
2. RECENT NEWS: Important team news from the last 7 days (transfers, lineup changes, contracts)
3. COACHING: Any coaching changes, tactical shifts, or formation changes
4. MORALE: Team morale indicators (winning streak, fan support, internal conflicts)

Return a JSON object with keys:
- injuries: array of {player_name, status, injury_type, expected_return, impact, source}
- recent_news: array of strings (one sentence per news item)
- coaching_changes: array of strings
- morale_indicators: array of strings
- confidence: float 0-1 (how confident you are in the data completeness)

Only include factual information from the provided search results. Do NOT invent data."""


def enrich_team_news(
    team: str,
    sport: str,
    date: str,
) -> NewsEnrichmentResult:
    """Fetch current news, injuries, and coaching changes for a team.

    Uses Brave Search → LM Studio structuring (replaces Gemini search grounding).
    """
    try:
        brave = BraveSearchClient()
    except Exception:
        logger.warning(f"[{team}] Brave Search not available")
        return NewsEnrichmentResult(team_name=team, sport=sport)

    try:
        client = LMStudioClient()
    except LMStudioNotAvailableError:
        logger.warning(f"[{team}] LM Studio not available for news enrichment")
        return NewsEnrichmentResult(team_name=team, sport=sport)

    # Step 1: Brave Search for team news
    query = f"{team} {sport} injuries team news lineup {date}"
    try:
        search_results = brave.news_search(query, count=8)
    except Exception as e:
        logger.warning(f"[{team}] Brave news search failed: {e}")
        # Fallback to web search
        try:
            search_results = brave.search(query, count=8)
        except Exception as e2:
            logger.error(f"[{team}] All search failed: {e2}")
            return NewsEnrichmentResult(team_name=team, sport=sport)

    if not search_results:
        logger.info(f"[{team}] No search results found")
        return NewsEnrichmentResult(team_name=team, sport=sport, confidence=0.1)

    # Format search results for LLM
    search_text = _format_search_results(search_results)
    sources = [r.url for r in search_results if r.url]

    # Step 2: LM Studio structures the raw search data
    prompt = f"""{STRUCTURING_PROMPT}

--- SEARCH RESULTS for {team} ({sport}) on {date} ---
{search_text}
--- END SEARCH RESULTS ---

Structure this information into the JSON format described above."""

    try:
        response = client.generate(prompt=prompt)

        if response.text:
            parsed = _parse_structured_response(response.text, team, sport, sources)
            if parsed:
                return parsed

        logger.warning(f"[{team}] Could not structure news from LM Studio")
        return NewsEnrichmentResult(team_name=team, sport=sport, sources=sources, confidence=0.2)

    except LMStudioError as e:
        logger.error(f"[{team}] LM Studio error: {e}")
        return NewsEnrichmentResult(team_name=team, sport=sport)
    except Exception as e:
        logger.error(f"[{team}] Unexpected error: {e}")
        return NewsEnrichmentResult(team_name=team, sport=sport)


def _format_search_results(results: list) -> str:
    """Format Brave search results (SearchResult or NewsResult dataclasses) into text for LLM."""
    parts = []
    for i, r in enumerate(results[:8], 1):
        title = r.title
        description = getattr(r, "description", "") or getattr(r, "snippet", "")
        url = r.url
        age = r.age
        parts.append(f"[{i}] {title}")
        if age:
            parts.append(f"    Published: {age}")
        if description:
            parts.append(f"    {description}")
        if url:
            parts.append(f"    Source: {url}")
        parts.append("")
    return "\n".join(parts)


def _parse_structured_response(
    text: str, team: str, sport: str, sources: list[str]
) -> NewsEnrichmentResult | None:
    """Parse LLM structured response into NewsEnrichmentResult."""
    import re

    # Try to extract JSON from response
    json_match = re.search(r"\{[\s\S]*\}", text)
    if not json_match:
        return None

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError:
        return None

    injuries = []
    for inj in data.get("injuries", []):
        if isinstance(inj, dict) and inj.get("player_name"):
            injuries.append(InjuryReport(
                player_name=inj["player_name"],
                status=inj.get("status", "doubtful"),
                injury_type=inj.get("injury_type", ""),
                expected_return=inj.get("expected_return", ""),
                impact=inj.get("impact", "medium"),
                source=inj.get("source", "brave-search"),
            ))

    return NewsEnrichmentResult(
        team_name=team,
        sport=sport,
        injuries=injuries,
        recent_news=data.get("recent_news", []),
        coaching_changes=data.get("coaching_changes", []),
        morale_indicators=data.get("morale_indicators", []),
        sources=sources,
        confidence=data.get("confidence", 0.5),
    )


def batch_enrich_news(
    candidates: list[dict],
    date: str,
) -> list[NewsEnrichmentResult]:
    """Batch news enrichment for all candidates. Deduplicates teams."""
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
    for item in teams_to_enrich:
        result = enrich_team_news(item["team"], item["sport"], date)
        results.append(result)
        if result.injuries or result.recent_news:
            success_count += 1

    logger.info(f"News enrichment complete: {success_count}/{len(teams_to_enrich)} with data")
    return results


def save_news_to_db(results: list[NewsEnrichmentResult], date: str) -> int:
    """Save news enrichment results to team_news DB table."""
    saved = 0
    try:
        with get_db() as conn:
            for r in results:
                if not r.injuries and not r.recent_news:
                    continue

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
                        "lmstudio+brave",
                    ),
                )
                saved += 1
    except Exception as e:
        logger.error(f"DB save error: {e}")

    logger.info(f"Saved {saved} team news records to DB")
    return saved


def main():
    parser = argparse.ArgumentParser(description="LM Studio News Enrichment (Brave + Local LLM)")
    parser.add_argument("--team", help="Specific team to enrich")
    parser.add_argument("--sport", default="football")
    parser.add_argument("--date", default=datetime.datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    if args.team:
        result = enrich_team_news(args.team, args.sport, args.date)
        results = [result]
    else:
        # Load shortlist and enrich all teams
        shortlist_file = DATA_DIR / f"{args.date}_s2_shortlist.json"
        if not shortlist_file.exists():
            logger.error(f"Shortlist not found: {shortlist_file}")
            sys.exit(1)

        candidates = json.loads(shortlist_file.read_text(encoding="utf-8"))
        if isinstance(candidates, dict):
            candidates = candidates.get("candidates", candidates.get("events", []))

        results = batch_enrich_news(candidates, args.date)

    # Save to DB
    saved = save_news_to_db(results, args.date)

    # Save JSON output
    output_file = DATA_DIR / f"{args.date}_news_enrichment.json"
    output_data = [r.model_dump() for r in results if r.injuries or r.recent_news]
    atomic_json_write(output_file, output_data)

    with_data = sum(1 for r in results if r.injuries or r.recent_news)
    summary = {
        "verdict": "OK" if with_data > 0 else "PARTIAL",
        "teams_processed": len(results),
        "teams_with_data": with_data,
        "db_records_saved": saved,
        "output_file": str(output_file),
    }
    print(f"AGENT_SUMMARY:{json.dumps(summary)}")


if __name__ == "__main__":
    main()
