#!/usr/bin/env python3
"""LM Studio Tipster Reader — extracts structured picks from tipster sites.

Two-step approach: httpx fetches raw HTML → LM Studio extracts structured picks.
Replaces gemini_tipster_reader.py (which used Gemini's native URL reading).

Usage:
    python3 scripts/lmstudio_tipster_reader.py --batch --date 2026-05-27
    python3 scripts/lmstudio_tipster_reader.py --url URL --source NAME --date 2026-05-27
    python3 scripts/lmstudio_tipster_reader.py --batch --date 2026-05-27 --sport football
"""

import argparse
import datetime
import json
import logging
import sys
import time
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from bet.schemas.gemini_responses import TipsterPageResult, TipsterPickExtracted
from bet.api_clients.lmstudio_client import LMStudioClient, LMStudioNotAvailableError, LMStudioError

logger = logging.getLogger(__name__)

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

EXTRACTION_PROMPT = """You are extracting betting picks from a tipster/prediction website HTML.
Extract ALL betting picks visible for date {date}.
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

Statistical markets (corners, fouls, cards, shots, games, sets, points) 
are MORE VALUABLE than outcome markets (winner, ML, 1X2).

Skip ads, promotions, banners, and non-betting content.
Return only actual betting picks as a JSON object matching TipsterPageResult schema."""

# Max chars of HTML to send to LLM (avoid context overflow)
MAX_HTML_CHARS = 50000


def _fetch_page_html(url: str) -> str | None:
    """Fetch HTML content from a URL using httpx."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True)
        if resp.status_code == 200:
            return resp.text
        logger.warning(f"HTTP {resp.status_code} for {url}")
        return None
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


def _clean_html_for_llm(html: str) -> str:
    """Strip scripts, styles, and reduce HTML to meaningful text content."""
    import re

    # Remove script and style blocks
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<noscript[^>]*>.*?</noscript>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML comments
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    # Collapse whitespace
    html = re.sub(r"\s+", " ", html)

    # Truncate to max
    if len(html) > MAX_HTML_CHARS:
        html = html[:MAX_HTML_CHARS] + "\n[...TRUNCATED...]"

    return html


def read_tipster_page(
    url: str,
    source_site: str,
    sport_filter: str | None = None,
    date_filter: str | None = None,
) -> TipsterPageResult:
    """Fetch tipster page HTML and extract picks via LM Studio."""
    date_str = date_filter or datetime.datetime.now().strftime("%Y-%m-%d")

    # Step 1: Fetch HTML
    html = _fetch_page_html(url)
    if not html:
        logger.warning(f"[{source_site}] Could not fetch HTML from {url}")
        return TipsterPageResult(source_name=source_site, url=url)

    cleaned_html = _clean_html_for_llm(html)

    # Step 2: Extract picks via LM Studio
    sport_instruction = f"Focus on {sport_filter} picks." if sport_filter else ""
    prompt = EXTRACTION_PROMPT.format(date=date_str, sport_instruction=sport_instruction)

    full_prompt = f"""{prompt}

--- PAGE HTML (from {source_site}: {url}) ---
{cleaned_html}
--- END HTML ---

Extract all betting picks from this page content."""

    try:
        client = LMStudioClient()
        response = client.generate(
            prompt=full_prompt,
            response_schema=TipsterPageResult,
        )

        if response.parsed and isinstance(response.parsed, TipsterPageResult):
            page = response.parsed
            page.source_name = source_site
            page.url = url
            logger.info(f"[{source_site}] LM Studio extracted {len(page.picks)} picks")
            return page

        logger.warning(f"[{source_site}] No structured picks from LM Studio")
        return TipsterPageResult(source_name=source_site, url=url)

    except LMStudioNotAvailableError:
        logger.warning("LM Studio not available — skipping tipster reading")
        return TipsterPageResult(source_name=source_site, url=url)
    except LMStudioError as e:
        logger.error(f"[{source_site}] LM Studio error: {e}")
        return TipsterPageResult(source_name=source_site, url=url)
    except Exception as e:
        logger.error(f"[{source_site}] Unexpected error: {e}")
        return TipsterPageResult(source_name=source_site, url=url)


def convert_to_tipster_pick(
    pick: TipsterPickExtracted, source_site: str, date_str: str
) -> dict:
    """Convert extracted pick to tipster_aggregator.py TipsterPick format."""
    stat_keywords = {
        "corner", "foul", "card", "shot", "game", "set", "point",
        "frame", "ace", "block", "rebound", "assist",
    }
    market_lower = pick.market.lower()
    is_statistical = any(kw in market_lower for kw in stat_keywords)

    return {
        "source_site": source_site,
        "tipster_name": f"{source_site} (LMStudio)",
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
    """Read multiple tipster sites sequentially."""
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
    parser = argparse.ArgumentParser(description="LM Studio Tipster Reader (Local Inference)")
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

    if args.url and args.source:
        results = [read_tipster_page(args.url, args.source, args.sport, args.date)]
    elif args.batch:
        results = batch_read_tipster_sites(DEFAULT_TIPSTER_SITES, args.date, args.sport)
    else:
        print("ERROR: Provide --batch or both --url and --source", file=sys.stderr)
        sys.exit(1)

    sites_processed = 0
    picks_extracted = 0
    issues = []

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
