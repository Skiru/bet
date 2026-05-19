#!/usr/bin/env python3
"""Gemini Web Research — L7a fallback using Gemini Search Grounding.

Replaces SerpAPI + Playwright chain with Gemini's native search capability.
Single Gemini call searches the web, reads results, and returns structured data.

Feature flag: Used when web_research_agent.py detects Gemini is configured.
Falls back to SerpAPI (L7b) when Gemini budget is exceeded.

Usage:
    python3 scripts/gemini_web_research.py --team "Arsenal" --sport football --need injuries,form
    python3 scripts/gemini_web_research.py --team1 "Arsenal" --team2 "Chelsea" --sport football --need h2h
    python3 scripts/gemini_web_research.py --batch --date 2026-05-12
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

from bet.schemas.gemini_responses import WebResearchResult, EventContextResult, NewsEnrichmentResult
from bet.api_clients.gemini_client import GeminiClient, GeminiNotConfiguredError, GeminiError

logger = logging.getLogger(__name__)

# Research prompts per data type
RESEARCH_PROMPTS = {
    "h2h": """Search for head-to-head statistics between {team1} and {team2} ({sport}).
Find: recent H2H meetings (last 5-10), scores, venue, key stats (corners, cards, goals).
Prefer data from: flashscore.com, soccerway.com.
Only include factual information with source URLs. Freshness matters — prefer last 12 months.""",

    "injuries": """Search for current injury and squad news for {team} ({sport}).
Find: injured players, their status (out/doubtful/questionable), injury type, expected return.
Also find: suspended players, recent call-ups or exclusions.
Prefer data from: espn.com, flashscore.com, transfermarkt.com, official team sites.
Only the most recent reports (last 7 days).""",

    "form": """Search for recent results and current form for {team} ({sport}).
Find: last 5-10 match results with scores, current league position, recent streaks.
Include: home/away form split if available, goals scored/conceded trend.
Prefer data from: flashscore.com, espn.com.""",

    "coach": """Search for coaching information about {team} ({sport}).
Find: current head coach/manager name, tenure, tactical approach, recent changes.
Include: any assistant coach changes, tactical shifts, formation preferences.
Prefer recent sources (last 30 days).""",
}


def research_team(
    team: str,
    sport: str,
    data_types: list[str],
    opponent: str | None = None,
) -> list[WebResearchResult]:
    """Research missing data for a team via Gemini Search Grounding.

    Args:
        team: Team name to research
        sport: Sport key (football, tennis, etc.)
        data_types: List of data types to research ("h2h", "injuries", "form", "coach")
        opponent: Opponent team (required for h2h)

    Returns:
        List of WebResearchResult, one per data_type
    """
    try:
        client = GeminiClient()
    except Exception:
        logger.warning("Gemini not available for web research")
        return []

    results = []
    for data_type in data_types:
        prompt_template = RESEARCH_PROMPTS.get(data_type)
        if not prompt_template:
            logger.warning(f"Unknown data_type: {data_type}")
            continue

        prompt = prompt_template.format(
            team=team,
            team1=team,
            team2=opponent or "opponent",
            sport=sport,
        )

        try:
            response = client.search_grounded_query(
                prompt=prompt,
            )

            result = WebResearchResult(
                query=prompt[:200],
                data_type=data_type,
                team=team,
                sport=sport,
                findings=_extract_findings(response.text),
                sources=[s.get("uri", "") for s in response.search_results if s.get("uri")],
                confidence=_estimate_confidence(response),
                data_freshness=_estimate_freshness(response.text),
            )
            results.append(result)
            logger.info(f"[{team}] {data_type}: {len(result.findings)} findings, confidence={result.confidence:.2f}")

        except GeminiNotConfiguredError:
            logger.warning("Gemini not configured — cannot do web research")
            break
        except GeminiError as e:
            logger.error(f"[{team}] Gemini search error for {data_type}: {e}")
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
    """Research full event context in a single Gemini search call.

    More efficient than separate calls for each data type.
    """
    prompt = f"""Search for comprehensive pre-match information about:
{home_team} vs {away_team} ({sport}, {competition or 'league match'})

Find and structure:
1. INJURIES: Which players are injured/suspended for both teams? Status and impact.
2. FORM: Recent results for both teams (last 5 matches). Winning/losing streaks.
3. MOTIVATION: Is this a crucial match? Relegation battle? Title race? Cup final?
4. H2H: Recent head-to-head meetings between these teams.
5. VENUE: Where is the match? Home advantage factors.

Use reliable sports sources. Only include factual, recent information (last 7 days for injuries, 
last 30 days for form). Cite your sources."""

    try:
        client = GeminiClient()
        response = client.search_grounded_query(prompt=prompt)

        sources = [s.get("uri", "") for s in response.search_results if s.get("uri")]

        return EventContextResult(
            home_team=home_team,
            away_team=away_team,
            sport=sport,
            competition=competition,
            sources=sources,
            motivation_factors=_extract_motivation(response.text),
        )

    except (GeminiNotConfiguredError, GeminiError) as e:
        logger.error(f"Event context research failed: {e}")
        return None


def _extract_findings(text: str) -> list[str]:
    """Extract bullet-point findings from Gemini response text."""
    if not text:
        return []
    findings = []
    for line in text.split("\n"):
        line = line.strip()
        if line and (line.startswith("-") or line.startswith("*") or line.startswith("•")):
            findings.append(line.lstrip("-*• ").strip())
        elif line and len(line) > 20 and not line.startswith("#"):
            findings.append(line)
    return findings[:20]  # Cap at 20 findings


def _estimate_confidence(response) -> float:
    """Estimate confidence based on search results and response quality."""
    score = 0.3  # Base confidence
    if response.search_results:
        score += min(len(response.search_results) * 0.1, 0.3)
    if response.text and len(response.text) > 200:
        score += 0.2
    if response.thoughts:
        score += 0.1
    return min(score, 1.0)


def _estimate_freshness(text: str) -> str:
    """Estimate data freshness from response text."""
    if not text:
        return "unknown"
    text_lower = text.lower()
    if any(w in text_lower for w in ["today", "just now", "hours ago", "this morning"]):
        return "today"
    if any(w in text_lower for w in ["yesterday", "this week", "days ago"]):
        return "this_week"
    if any(w in text_lower for w in ["last week", "this month"]):
        return "this_month"
    return "older"


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
    parser = argparse.ArgumentParser(description="Gemini Web Research (L7a)")
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
