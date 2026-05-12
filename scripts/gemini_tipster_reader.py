#!/usr/bin/env python3
"""Gemini Tipster Reader — extracts structured picks from tipster sites via Gemini.

Replaces fragile BS4 HTML parsing with Gemini's URL reading capability.
Behind feature flag: used when tipster_aggregator.py is called with --use-gemini.

Usage:
    python3 scripts/gemini_tipster_reader.py --url URL --source NAME --date 2026-05-12
    python3 scripts/gemini_tipster_reader.py --batch --date 2026-05-12
    python3 scripts/gemini_tipster_reader.py --batch --date 2026-05-12 --sport football
"""

import argparse
import datetime
import json
import logging
import sys
import traceback
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from bet.schemas.gemini_responses import TipsterPageResult, TipsterPickExtracted
from api_clients.gemini_client import GeminiClient, GeminiNotConfiguredError, GeminiError
from agent_output import AgentOutput

logger = logging.getLogger(__name__)

# Sites matching those in tipster_aggregator.py
DEFAULT_TIPSTER_SITES = [
    {"name": "OLBG", "url": "https://www.olbg.com/betting-tips"},
    {"name": "PicksWise", "url": "https://www.pickswise.com/picks/"},
    {"name": "BetIdeas", "url": "https://betideas.com/tips/"},
    {"name": "Sportsgambler", "url": "https://www.sportsgambler.com/predictions/"},
    {"name": "Forebet", "url": "https://www.forebet.com/en/football-predictions"},
    {"name": "Feedinco", "url": "https://feedinco.com/predictions"},
    {"name": "BettingClosed", "url": "https://bettingclosed.com/predictions/"},
    {"name": "Tips180", "url": "https://www.tips180.com/free-betting-tips"},
]

EXTRACTION_PROMPT_TEMPLATE = """You are extracting betting picks from a tipster/prediction website.
Extract ALL betting picks visible on the page for date {date}.
{sport_instruction}

For each pick, identify:
- sport (football, tennis, basketball, hockey, volleyball, etc.)
- home_team and away_team (full team/player names)
- competition (league/tournament name)
- market (e.g., "Corners Over 9.5", "Total Goals Over 2.5", "Match Winner")
- market_type: "statistical" if corners/fouls/cards/shots/games/sets/points, otherwise "outcome"
- direction: OVER, UNDER, WIN, DRAW, HOME, AWAY
- selection: the full selection text as shown on the page
- odds: decimal odds if mentioned (e.g., 1.85)
- confidence: your confidence in the extraction accuracy (0.0-1.0)
- reasoning: the tipster's reasoning/analysis if provided

IMPORTANT: Statistical markets (corners, fouls, cards, shots, games, sets, points) 
are MORE VALUABLE than outcome markets (winner, ML, 1X2).

Skip ads, promotions, banners, and non-betting content.
Return only actual betting picks."""


def read_tipster_page(
    url: str,
    source_site: str,
    sport_filter: str | None = None,
    date_filter: str | None = None,
) -> TipsterPageResult:
    """Read a tipster page via Gemini and extract structured picks."""
    date_str = date_filter or datetime.datetime.now().strftime("%Y-%m-%d")
    sport_instruction = f"Focus on {sport_filter} picks." if sport_filter else ""

    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        date=date_str, sport_instruction=sport_instruction
    )

    try:
        client = GeminiClient()
        result = client.read_url(
            url=url,
            prompt=prompt,
            response_schema=TipsterPageResult,
        )

        if result.parsed and isinstance(result.parsed, TipsterPageResult):
            page = result.parsed
            page.source_name = source_site
            page.url = url
            logger.info(f"[{source_site}] Gemini extracted {len(page.picks)} picks")
            return page

        # Try parsing text as JSON fallback
        if result.text:
            try:
                page = TipsterPageResult.model_validate_json(result.text)
                page.source_name = source_site
                page.url = url
                return page
            except Exception:
                pass

        logger.warning(f"[{source_site}] No structured picks from Gemini")
        return TipsterPageResult(source_name=source_site, url=url)

    except GeminiNotConfiguredError:
        logger.warning("Gemini not configured — skipping tipster reading")
        return TipsterPageResult(source_name=source_site, url=url)
    except GeminiError as e:
        logger.error(f"[{source_site}] Gemini error: {e}")
        return TipsterPageResult(source_name=source_site, url=url)
    except Exception as e:
        logger.error(f"[{source_site}] Unexpected error: {e}")
        return TipsterPageResult(source_name=source_site, url=url)


def convert_to_tipster_pick(
    pick: TipsterPickExtracted, source_site: str, date_str: str
) -> dict:
    """Convert Gemini-extracted pick to tipster_aggregator.py TipsterPick format."""
    # Classify market type
    stat_keywords = {
        "corner", "foul", "card", "shot", "game", "set", "point",
        "frame", "ace", "block", "rebound", "assist",
    }
    market_lower = pick.market.lower()
    is_statistical = any(kw in market_lower for kw in stat_keywords)

    return {
        "source_site": source_site,
        "tipster_name": f"{source_site} (Gemini)",
        "sport": pick.sport or "unknown",
        "event": f"{pick.home_team} vs {pick.away_team}" if pick.home_team else pick.market,
        "home_team": pick.home_team or "",
        "away_team": pick.away_team or "",
        "competition": pick.competition or "",
        "market": pick.market,
        "market_type": "statistical" if is_statistical else "outcome",
        "direction": pick.direction or pick.selection or "",
        "odds": pick.odds,
        "reasoning": pick.reasoning or "",
        "accuracy_pct": None,
        "confidence": (
            "high" if pick.confidence >= 0.8
            else "medium" if pick.confidence >= 0.5
            else "low"
        ),
        "stats_cited": pick.stats_cited,
        "fetch_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def batch_read_tipster_sites(
    sites: list[dict],
    date_str: str,
    sport_filter: str | None = None,
) -> list[TipsterPageResult]:
    """Read multiple tipster sites sequentially (rate-limited)."""
    results = []
    for site in sites:
        result = read_tipster_page(
            url=site["url"],
            source_site=site["name"],
            sport_filter=sport_filter,
            date_filter=date_str,
        )
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description="Gemini Tipster Reader")
    parser.add_argument("--url", help="Specific URL to read")
    parser.add_argument("--source", help="Source site name")
    parser.add_argument("--date", default=datetime.datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--batch", action="store_true", help="Read all default sites")
    parser.add_argument("--sport", help="Sport filter")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    sites_processed = 0
    picks_extracted = 0
    issues = []

    if args.url and args.source:
        results = [read_tipster_page(args.url, args.source, args.sport, args.date)]
    elif args.batch:
        results = batch_read_tipster_sites(DEFAULT_TIPSTER_SITES, args.date, args.sport)
    else:
        print("ERROR: Provide --batch or both --url and --source", file=sys.stderr)
        sys.exit(1)

    for r in results:
        sites_processed += 1
        if r.picks:
            picks_extracted += len(r.picks)
            for p in r.picks:
                pick_dict = convert_to_tipster_pick(p, r.source_name, args.date)
                if args.verbose:
                    print(json.dumps(pick_dict, ensure_ascii=False))
        else:
            issues.append(f"No picks from {r.source_name}")

    verdict = "OK" if picks_extracted > 0 else "PARTIAL" if sites_processed > 0 else "FAILED"
    summary = {
        "verdict": verdict,
        "sites_processed": sites_processed,
        "picks_extracted": picks_extracted,
        "issues": issues,
    }
    print(f"AGENT_SUMMARY:{json.dumps(summary)}")


if __name__ == "__main__":
    main()
