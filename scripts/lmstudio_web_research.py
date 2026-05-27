#!/usr/bin/env python3
"""LM Studio Web Research — Brave Search + local LLM synthesis.

Replaces gemini_web_research.py with two-step pattern:
1. Brave Search API fetches live web results
2. LM Studio (Gemma 4 31B) synthesizes results into structured data

Usage:
    python3 scripts/lmstudio_web_research.py --team "Arsenal" --sport football --need injuries,form
    python3 scripts/lmstudio_web_research.py --team1 "Arsenal" --team2 "Chelsea" --sport football --need h2h
    python3 scripts/lmstudio_web_research.py --batch --date 2026-05-27
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

from bet.schemas.llm_responses import WebResearchResult, EventContextResult
from bet.api_clients.lmstudio_client import LMStudioClient, LMStudioNotAvailableError, LMStudioError
from bet.api_clients.brave_search_client import BraveSearchClient, BraveSearchError

logger = logging.getLogger(__name__)

# Search query templates per data type
SEARCH_QUERIES = {
    "h2h": "{team1} vs {team2} head to head {sport} recent results statistics",
    "injuries": "{team} injuries squad news {sport} today",
    "form": "{team} recent results form {sport} last 5 matches",
    "coach": "{team} coach manager tactics {sport} 2026",
}

# Synthesis prompts per data type
SYNTHESIS_PROMPTS = {
    "h2h": """Extract head-to-head statistics between {team1} and {team2} ({sport}).
Return: recent H2H meetings (last 5-10), scores, venue, key stats (corners, cards, goals).
Only include factual information from the search results. Be specific with numbers.""",

    "injuries": """Extract current injury and squad news for {team} ({sport}).
Return: injured players (name, status: out/doubtful/questionable, injury type, expected return).
Also: suspended players, recent call-ups or exclusions.
Only the most recent reports.""",

    "form": """Extract recent results and current form for {team} ({sport}).
Return: last 5-10 match results with scores, current league position, recent streaks.
Include: home/away form split if available, goals scored/conceded trend.""",

    "coach": """Extract coaching information about {team} ({sport}).
Return: current head coach/manager name, tenure, tactical approach, recent changes.
Include: formation preferences, any tactical shifts.""",
}


def research_team(
    team: str,
    sport: str,
    data_types: list[str],
    opponent: str | None = None,
) -> list[WebResearchResult]:
    """Research missing data for a team via Brave Search + LMStudio.

    Args:
        team: Team name to research
        sport: Sport key (football, tennis, etc.)
        data_types: List of data types to research ("h2h", "injuries", "form", "coach")
        opponent: Opponent team (required for h2h)

    Returns:
        List of WebResearchResult, one per data_type
    """
    try:
        lmstudio = LMStudioClient()
        brave = BraveSearchClient()
    except (LMStudioNotAvailableError, Exception) as e:
        logger.warning(f"LMStudio or Brave not available: {e}")
        return []

    results = []
    for data_type in data_types:
        query_template = SEARCH_QUERIES.get(data_type)
        synthesis_template = SYNTHESIS_PROMPTS.get(data_type)
        if not query_template or not synthesis_template:
            logger.warning(f"Unknown data_type: {data_type}")
            continue

        query = query_template.format(
            team=team, team1=team, team2=opponent or "opponent", sport=sport
        )
        synthesis_prompt = synthesis_template.format(
            team=team, team1=team, team2=opponent or "opponent", sport=sport
        )

        try:
            # Step 1: Brave Search
            search_results = brave.search(query, count=5, freshness="pw")

            if not search_results:
                search_results = brave.search(query, count=5, freshness=None)

            sources = [r.url for r in search_results]
            context = [f"[{i+1}] {r.title}\n{r.snippet}" for i, r in enumerate(search_results)]

            # Step 2: LMStudio synthesis
            response = lmstudio.generate_with_context(
                prompt=synthesis_prompt,
                context=context,
                system_prompt="You are a sports data extraction assistant. Return factual findings only.",
            )

            result = WebResearchResult(
                query=query[:200],
                data_type=data_type,
                team=team,
                sport=sport,
                findings=_extract_findings(response.text),
                sources=sources,
                confidence=_estimate_confidence(search_results, response.text),
                data_freshness=_estimate_freshness(search_results),
            )
            results.append(result)
            logger.info(f"[{team}] {data_type}: {len(result.findings)} findings, confidence={result.confidence:.2f}")

        except (LMStudioError, BraveSearchError) as e:
            logger.error(f"[{team}] Research error for {data_type}: {e}")
            continue
        except Exception as e:
            logger.error(f"[{team}] Unexpected error for {data_type}: {e}")
            continue

    return results


def research_event_context(
    home_team: str,
    away_team: str,
    sport: str,
    competition: str = "",
) -> EventContextResult | None:
    """Research full event context via Brave Search + LMStudio."""
    try:
        lmstudio = LMStudioClient()
        brave = BraveSearchClient()
    except Exception as e:
        logger.error(f"Event context research failed (init): {e}")
        return None

    query = f"{home_team} vs {away_team} {sport} {competition} preview match"
    synthesis_prompt = f"""Extract comprehensive pre-match information about:
{home_team} vs {away_team} ({sport}, {competition or 'league match'})

From the search results, structure:
1. INJURIES: Which players are injured/suspended for both teams?
2. FORM: Recent results for both teams (last 5 matches).
3. MOTIVATION: Is this a crucial match? Relegation? Title race? Cup final?
4. H2H: Recent head-to-head meetings.
5. VENUE: Where is the match? Home advantage factors."""

    try:
        search_results = brave.search(query, count=7, freshness="pw")
        sources = [r.url for r in search_results]
        context = [f"[{i+1}] {r.title}\n{r.snippet}" for i, r in enumerate(search_results)]

        response = lmstudio.generate_with_context(
            prompt=synthesis_prompt,
            context=context,
            system_prompt="You are a sports analyst. Extract factual pre-match information.",
        )

        return EventContextResult(
            home_team=home_team,
            away_team=away_team,
            sport=sport,
            competition=competition,
            sources=sources,
            motivation_factors=_extract_motivation(response.text),
        )

    except Exception as e:
        logger.error(f"Event context research failed: {e}")
        return None


def _extract_findings(text: str) -> list[str]:
    """Extract findings from LMStudio response."""
    if not text:
        return []
    findings = []
    for line in text.split("\n"):
        line = line.strip()
        if line and (line.startswith("-") or line.startswith("*") or line.startswith("•")):
            findings.append(line.lstrip("-*• ").strip())
        elif line and len(line) > 20 and not line.startswith("#"):
            findings.append(line)
    return findings[:20]


def _estimate_confidence(search_results: list, text: str) -> float:
    """Estimate confidence based on search results quality."""
    score = 0.3
    if search_results:
        score += min(len(search_results) * 0.1, 0.3)
    if text and len(text) > 200:
        score += 0.2
    if text and len(text) > 500:
        score += 0.1
    return min(score, 1.0)


def _estimate_freshness(search_results: list) -> str:
    """Estimate data freshness from search result ages."""
    if not search_results:
        return "unknown"
    ages = [r.age for r in search_results if hasattr(r, "age") and r.age]
    if not ages:
        return "unknown"
    for age in ages:
        if "hour" in age or "minute" in age:
            return "today"
        if "day" in age and any(c.isdigit() and int(c) <= 2 for c in age if c.isdigit()):
            return "this_week"
    return "this_week"


def _extract_motivation(text: str) -> list[str]:
    """Extract motivation factors from event context text."""
    if not text:
        return []
    keywords = [
        "relegation", "title", "champion", "final", "must-win", "dead rubber",
        "derby", "rivalry", "revenge", "unbeaten", "streak", "pressure",
        "qualification", "promotion", "knockout", "elimination",
    ]
    factors = []
    for line in text.split("\n"):
        line_lower = line.lower()
        if any(kw in line_lower for kw in keywords):
            factors.append(line.strip().lstrip("-*• "))
    return factors[:10]


def main():
    parser = argparse.ArgumentParser(description="LM Studio Web Research (Brave + Local LLM)")
    parser.add_argument("--team", help="Team to research")
    parser.add_argument("--team1", help="Home team (for H2H)")
    parser.add_argument("--team2", help="Away team (for H2H)")
    parser.add_argument("--sport", default="football")
    parser.add_argument("--need", help="Comma-separated data types: h2h,injuries,form,coach")
    parser.add_argument("--date", default=datetime.datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    data_types = args.need.split(",") if args.need else ["injuries", "form"]
    team = args.team or args.team1 or ""
    opponent = args.team2

    if not team:
        print("ERROR: Provide --team or --team1", file=sys.stderr)
        sys.exit(1)

    results = research_team(team, args.sport, data_types, opponent)

    total_findings = sum(len(r.findings) for r in results)
    for r in results:
        if args.verbose:
            print(json.dumps(r.model_dump(), ensure_ascii=False, indent=2))

    summary = {
        "verdict": "OK" if total_findings > 0 else "PARTIAL",
        "team": team,
        "sport": args.sport,
        "data_types_researched": len(results),
        "total_findings": total_findings,
        "sources_found": sum(len(r.sources) for r in results),
    }
    print(f"AGENT_SUMMARY:{json.dumps(summary)}")


if __name__ == "__main__":
    main()
