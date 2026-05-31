#!/usr/bin/env python3
"""Web Research Agent — L7 fallback for missing betting data.

When all API/scraping fallback chains (L1-L6) fail to find H2H, injury,
form, or coach data, this agent searches the open web as last resort.

Rate limits:
  - SerpAPI: max 5 searches per pipeline run (100/month budget)
  - Playwright: max 10 searches per pipeline run
  - Priority: data that upgrades MINIMAL → PARTIAL quality

Usage:
  python3 scripts/web_research_agent.py --team1 "Arsenal" --team2 "Chelsea" --sport football --need h2h
  python3 scripts/web_research_agent.py --team "Arsenal" --sport football --need injuries
"""

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

# Path setup for bet.db imports
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from bet.resilience import atomic_json_write

from bet.db.connection import get_db  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATA_DIR = _ROOT / "betting" / "data"
COUNTER_FILE = DATA_DIR / ".web_research_counter.json"
CACHE_TTL_HOURS = 6

# Rate limits per pipeline run (daily reset)
MAX_SERP_SEARCHES = 5
MAX_PLAYWRIGHT_SEARCHES = 10

# Search query templates per data_type
SEARCH_TEMPLATES = {
    "h2h": '"{team1} vs {team2}" head to head statistics {sport}',
    "injuries": '"{team}" injuries squad news {sport}',
    "form": '"{team}" recent results fixtures {sport}',
    "coach": '"{team}" coach manager {sport}',
}

# Preferred domains per data_type (tried in order)
# NOTE: flashscore.com REMOVED — requires curl_cffi + entity resolution, not urllib
PREFERRED_DOMAINS = {
    "h2h": ["sofascore.com", "soccerway.com"],
    "injuries": ["espn.com", "transfermarkt.com"],
    "form": ["sofascore.com", "soccerway.com"],
    "coach": ["transfermarkt.com", "sofascore.com"],
}


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
def _load_counter() -> dict:
    """Load daily counter from file, reset if new day."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if COUNTER_FILE.exists():
        try:
            data = json.loads(COUNTER_FILE.read_text(encoding="utf-8"))
            if data.get("date") == today:
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"date": today, "serp_count": 0, "playwright_count": 0}


def _save_counter(counter: dict) -> None:
    """Save counter to file."""
    COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    atomic_json_write(COUNTER_FILE, counter)


def _can_use_serp(counter: dict) -> bool:
    return counter.get("serp_count", 0) < MAX_SERP_SEARCHES


def _can_use_playwright(counter: dict) -> bool:
    return counter.get("playwright_count", 0) < MAX_PLAYWRIGHT_SEARCHES


def _increment_counter(counter: dict, method: str) -> None:
    """Increment and save counter for the given method."""
    if method == "serp":
        counter["serp_count"] = counter.get("serp_count", 0) + 1
    elif method == "playwright":
        counter["playwright_count"] = counter.get("playwright_count", 0) + 1
    _save_counter(counter)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------
def _query_hash(query_text: str) -> str:
    """MD5 hash of query string for cache lookup."""
    return hashlib.md5(query_text.encode("utf-8")).hexdigest()


def _check_cache(query_text: str, data_type: str, db_path=None) -> dict | None:
    """Check web_research_cache for a fresh cached result (< CACHE_TTL_HOURS)."""
    qhash = _query_hash(query_text)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=CACHE_TTL_HOURS)).isoformat()

    try:
        db_kwargs = {"db_path": db_path} if db_path else {}
        with get_db(**db_kwargs) as conn:
            row = conn.execute(
                """SELECT result_json, source_urls, confidence
                   FROM web_research_cache
                   WHERE query_hash = ? AND data_type = ? AND created_at > ?
                   ORDER BY created_at DESC LIMIT 1""",
                (qhash, data_type, cutoff),
            ).fetchone()
            if row:
                return {
                    "data": json.loads(row["result_json"]) if row["result_json"] else {},
                    "source_url": row["source_urls"] or "",
                    "confidence": row["confidence"] or 0.0,
                    "cached": True,
                }
    except Exception as exc:
        logger.warning("Cache lookup failed: %s", exc)

    return None


def _save_to_cache(
    query_text: str, data_type: str, result: dict, source_url: str, confidence: float, db_path=None
) -> None:
    """Save result to web_research_cache table."""
    qhash = _query_hash(query_text)
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(hours=CACHE_TTL_HOURS)).isoformat()

    try:
        db_kwargs = {"db_path": db_path} if db_path else {}
        with get_db(**db_kwargs) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO web_research_cache
                   (query_hash, query_text, data_type, result_json, source_urls,
                    confidence, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (qhash, query_text, data_type, json.dumps(result, ensure_ascii=False),
                 source_url, confidence, now, expires),
            )
    except Exception as exc:
        logger.warning("Cache save failed: %s", exc)


# ---------------------------------------------------------------------------
# Web fetching
# ---------------------------------------------------------------------------
def _fetch_via_playwright(url: str) -> str | None:
    """Fetch URL via HTTP (Playwright removed in Beast Mode migration)."""
    return _fetch_via_urllib(url)


def _fetch_via_urllib(url: str) -> str | None:
    """Simple urllib fallback fetcher."""
    try:
        import urllib.request

        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("urllib fetch failed for %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Parsers — extract structured data from HTML
# ---------------------------------------------------------------------------
def _parse_h2h_data(html: str, team1: str, team2: str, sport: str) -> dict:
    """Extract H2H statistics from HTML page."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("BeautifulSoup not available, returning raw text extraction")
        return _extract_numbers_from_text(html)

    soup = BeautifulSoup(html, "html.parser")
    data = {"meetings": [], "stats": {}}

    # Look for score patterns (e.g., "2 - 1", "3:0")
    score_pattern = re.compile(r"(\d+)\s*[-:]\s*(\d+)")

    # Extract match results from common H2H page structures
    for el in soup.find_all(["div", "span", "td"], string=score_pattern):
        text = el.get_text(strip=True)
        match = score_pattern.search(text)
        if match:
            data["meetings"].append({
                "score": f"{match.group(1)}-{match.group(2)}",
                "home_goals": int(match.group(1)),
                "away_goals": int(match.group(2)),
            })

    # Look for stat summaries (corners, cards, etc.)
    stat_keywords = ["corner", "card", "foul", "shot", "goal", "possession"]
    for kw in stat_keywords:
        for el in soup.find_all(string=re.compile(kw, re.IGNORECASE)):
            parent = el.parent
            if parent:
                nums = re.findall(r"\d+\.?\d*", parent.get_text())
                if nums:
                    data["stats"][kw + "s"] = [float(n) for n in nums[:10]]

    return data


def _parse_injury_data(html: str, team: str, sport: str) -> dict:
    """Extract injury/squad news from HTML."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    injuries = []

    # Common injury status keywords
    status_map = {
        "out": "OUT",
        "doubtful": "DOUBTFUL",
        "questionable": "QUESTIONABLE",
        "probable": "PROBABLE",
        "injured": "OUT",
        "suspended": "OUT",
        "day-to-day": "QUESTIONABLE",
    }

    for el in soup.find_all(["tr", "div", "li"]):
        text = el.get_text(separator=" ", strip=True).lower()
        for keyword, status in status_map.items():
            if keyword in text:
                # Try to extract player name (usually the first proper noun)
                name_match = re.search(r"([A-Z][a-z]+ [A-Z][a-z]+)", el.get_text(strip=True))
                injuries.append({
                    "athlete": name_match.group(1) if name_match else "Unknown",
                    "status": status,
                    "detail": text[:200],
                })
                break

    return {"injuries": injuries, "count": len(injuries)}


def _parse_form_data(html: str, team: str, sport: str) -> dict:
    """Extract recent form/results from HTML."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    results = []

    score_pattern = re.compile(r"(\d+)\s*[-:]\s*(\d+)")
    for el in soup.find_all(["div", "tr", "li"]):
        text = el.get_text(strip=True)
        match = score_pattern.search(text)
        if match and len(text) < 300:
            results.append({
                "score": f"{match.group(1)}-{match.group(2)}",
                "text": text[:150],
            })
            if len(results) >= 10:
                break

    return {"recent_results": results, "count": len(results)}


def _parse_coach_data(html: str, team: str, sport: str) -> dict:
    """Extract coach/manager information from HTML."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {}

    soup = BeautifulSoup(html, "html.parser")

    # Look for coach/manager mentions
    coach_keywords = ["coach", "manager", "head coach", "trainer", "trener"]
    for kw in coach_keywords:
        for el in soup.find_all(string=re.compile(kw, re.IGNORECASE)):
            parent = el.parent
            if parent:
                text = parent.get_text(strip=True)
                # Try to extract name near the keyword
                name_match = re.search(
                    r"(?:coach|manager|trainer|trener)[:\s]+([A-Z][a-zé]+ [A-Z][a-zé]+)",
                    text, re.IGNORECASE,
                )
                if name_match:
                    return {"coach_name": name_match.group(1), "raw_text": text[:200]}

    return {}


def _extract_numbers_from_text(html: str) -> dict:
    """Fallback: extract any number patterns from raw text."""
    text = re.sub(r"<[^>]+>", " ", html)
    nums = re.findall(r"\d+\.?\d*", text[:5000])
    return {"raw_numbers": [float(n) for n in nums[:50]]}


# ---------------------------------------------------------------------------
# Search strategy builders
# ---------------------------------------------------------------------------
def _build_search_urls(data_type: str, sport: str, team1: str, team2: str | None = None) -> list[str]:
    """Build direct URLs to try for the given data_type."""
    urls = []
    team_slug = re.sub(r"[^a-z0-9]+", "-", team1.lower()).strip("-")

    if data_type == "h2h" and team2:
        team2_slug = re.sub(r"[^a-z0-9]+", "-", team2.lower()).strip("-")
        urls.extend([
            # Flashscore /h2h/ path does NOT exist — use sofascore and soccerway instead
            f"https://www.sofascore.com/team/{sport}/{team_slug}/h2h/{team2_slug}",
            f"https://www.soccerway.com/matches/head2head/{team_slug}/{team2_slug}/",
        ])
    elif data_type == "injuries":
        urls.extend([
            f"https://www.espn.com/{sport}/team/injuries/_/name/{team_slug}",
            f"https://www.transfermarkt.com/{team_slug}/verletzungen/verein/",
        ])
    elif data_type == "form":
        urls.extend([
            f"https://www.sofascore.com/team/{sport}/{team_slug}",
            f"https://www.soccerway.com/teams/{sport}/{team_slug}/",
        ])
    elif data_type == "coach":
        urls.extend([
            f"https://www.transfermarkt.com/{team_slug}/startseite/verein/",
            f"https://www.sofascore.com/team/{sport}/{team_slug}",
        ])

    return urls


_PARSERS = {
    "h2h": _parse_h2h_data,
    "injuries": _parse_injury_data,
    "form": _parse_form_data,
    "coach": _parse_coach_data,
}


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------
def research_missing_data(
    team1: str,
    team2: str | None = None,
    sport: str = "football",
    data_type: str = "h2h",
    db_path=None,
    use_gemini: bool = True,
) -> dict:
    """Search for missing data as L7 fallback.

    Args:
        team1: Primary team name.
        team2: Opponent team name (required for h2h).
        sport: Sport identifier.
        data_type: One of 'h2h', 'injuries', 'form', 'coach'.
        db_path: Optional DB path override.
        use_gemini: Try Gemini Search Grounding first (L7a), then SerpAPI/Playwright (L7b).

    Returns:
        {data: {...}, source_url: str, confidence: float, cached: bool}
    """
    if data_type not in SEARCH_TEMPLATES:
        return {"data": {}, "source_url": "", "confidence": 0.0, "cached": False,
                "error": f"Unknown data_type: {data_type}"}

    # Build query string
    query_text = SEARCH_TEMPLATES[data_type].format(
        team1=team1, team2=team2 or "", team=team1, sport=sport,
    )

    # Check cache first
    cached = _check_cache(query_text, data_type, db_path=db_path)
    if cached:
        logger.info("Cache hit for %s query: %s", data_type, query_text[:60])
        return cached

    # --- L7a: Try LM Studio + Brave Search first (feature flag) ---
    if use_gemini:
        try:
            from lmstudio_web_research import research_team
            lmstudio_results = research_team(
                team=team1,
                sport=sport,
                data_types=[data_type],
                opponent=team2,
            )
            if lmstudio_results and lmstudio_results[0].findings:
                gr = lmstudio_results[0]
                parsed = {"findings": gr.findings, "source": "lmstudio+brave"}
                result = {
                    "data": parsed,
                    "source_url": gr.sources[0] if gr.sources else "lmstudio+brave",
                    "confidence": gr.confidence,
                    "cached": False,
                    "method": "lmstudio",
                }
                _save_to_cache(query_text, data_type, parsed,
                               result["source_url"], gr.confidence, db_path=db_path)
                logger.info("L7a (LMStudio) success: %s %s (confidence=%.2f)",
                            data_type, team1, gr.confidence)
                return result
            else:
                logger.info("L7a (LMStudio): no findings for %s %s — trying L7b",
                            data_type, team1)
        except ImportError:
            logger.debug("lmstudio_web_research not available — skipping L7a")
        except Exception as e:
            logger.warning("L7a (LMStudio) failed: %s — falling back to L7b", e)

    # --- L7b: Original SerpAPI + Playwright path ---
    # Load rate counter
    counter = _load_counter()

    # Try direct URLs first via Playwright
    urls = _build_search_urls(data_type, sport, team1, team2)
    parser_fn = _PARSERS.get(data_type, lambda *a: {})

    for url in urls:
        if not _can_use_playwright(counter):
            logger.warning("Playwright rate limit reached (%d/%d)",
                           counter.get("playwright_count", 0), MAX_PLAYWRIGHT_SEARCHES)
            break

        logger.info("L7 trying: %s", url)
        _increment_counter(counter, "playwright")
        time.sleep(1.5)  # Courtesy delay

        html = _fetch_via_playwright(url)
        if not html:
            continue

        if data_type == "h2h":
            parsed = parser_fn(html, team1, team2 or "", sport)
        else:
            parsed = parser_fn(html, team1, sport)

        if parsed and (parsed.get("meetings") or parsed.get("injuries")
                       or parsed.get("recent_results") or parsed.get("coach_name")
                       or parsed.get("stats")):
            confidence = _estimate_confidence(parsed, data_type)
            result = {"data": parsed, "source_url": url, "confidence": confidence, "cached": False}
            _save_to_cache(query_text, data_type, parsed, url, confidence, db_path=db_path)
            logger.info("L7 success: %s from %s (confidence=%.2f)", data_type, url, confidence)
            return result

    # All direct URLs failed
    logger.info("L7: all direct URLs exhausted for %s %s", data_type, team1)
    return {"data": {}, "source_url": "", "confidence": 0.0, "cached": False,
            "error": "No data found from any web source"}


def _estimate_confidence(parsed: dict, data_type: str) -> float:
    """Estimate confidence of parsed web data (0.0 - 1.0)."""
    if data_type == "h2h":
        meetings = len(parsed.get("meetings", []))
        stats = len(parsed.get("stats", {}))
        if meetings >= 5 and stats >= 2:
            return 0.7
        elif meetings >= 3:
            return 0.5
        elif meetings >= 1 or stats >= 1:
            return 0.3
        return 0.1

    elif data_type == "injuries":
        count = parsed.get("count", 0)
        return min(0.8, 0.3 + count * 0.1)

    elif data_type == "form":
        count = parsed.get("count", 0)
        if count >= 5:
            return 0.6
        elif count >= 3:
            return 0.4
        return 0.2

    elif data_type == "coach":
        if parsed.get("coach_name"):
            return 0.7
        return 0.2

    return 0.1


# ---------------------------------------------------------------------------
# Batch integration
# ---------------------------------------------------------------------------
def fill_data_gaps(candidates: list[dict], db_path=None) -> list[dict]:
    """Attempt to fill missing data for MINIMAL-quality candidates.

    Takes a list of candidate dicts (from shortlist or deep stats), checks
    which are MINIMAL quality, and tries to upgrade them via web research.
    Prioritizes candidates closest to PARTIAL threshold.

    Args:
        candidates: List of candidate dicts with keys like
                    {team_a, team_b, sport, quality, missing_data}.
        db_path: Optional DB path override.

    Returns:
        List of enrichment result dicts.
    """
    counter = _load_counter()
    results = []

    # Filter to MINIMAL quality candidates and sort by closest to PARTIAL
    minimal = [
        c for c in candidates
        if c.get("quality", "").upper() in ("MINIMAL", "NONE", "")
    ]

    # Prioritize by number of missing fields (fewer missing = closer to PARTIAL)
    minimal.sort(key=lambda c: len(c.get("missing_data", [])))

    for candidate in minimal:
        # Stop if rate limits exhausted
        if not _can_use_playwright(counter):
            logger.warning("Rate limits exhausted, stopping fill_data_gaps")
            break

        team_a = candidate.get("team_a") or candidate.get("home_team") or candidate.get("home", "")
        team_b = candidate.get("team_b") or candidate.get("away_team") or candidate.get("away", "")
        sport = candidate.get("sport", "football")
        missing = candidate.get("missing_data", [])

        candidate_results = {"team_a": team_a, "team_b": team_b, "sport": sport, "filled": []}

        for data_type in missing:
            if data_type not in SEARCH_TEMPLATES:
                continue

            counter = _load_counter()
            if not _can_use_playwright(counter):
                break

            if data_type == "h2h" and team_a and team_b:
                res = research_missing_data(team_a, team_b, sport, data_type, db_path=db_path)
            elif data_type in ("injuries", "form", "coach") and team_a:
                res = research_missing_data(team_a, sport=sport, data_type=data_type, db_path=db_path)
            else:
                continue

            if res.get("data") and not res.get("error"):
                candidate_results["filled"].append(data_type)

        results.append(candidate_results)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Web Research Agent — L7 fallback for missing betting data",
    )
    parser.add_argument("--team1", help="Primary team name")
    parser.add_argument("--team2", help="Opponent team name (for h2h)")
    parser.add_argument("--team", help="Alias for --team1 (single-team queries)")
    parser.add_argument("--sport", default="football", help="Sport (default: football)")
    parser.add_argument("--need", required=True, choices=["h2h", "injuries", "form", "coach"],
                        help="Type of data needed")
    parser.add_argument("--db-path", help="Override DB path")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    team1 = args.team1 or args.team
    if not team1:
        print("ERROR: --team1 or --team required", file=sys.stderr)
        sys.exit(1)

    if args.need == "h2h" and not args.team2:
        print("ERROR: --team2 required for h2h lookup", file=sys.stderr)
        sys.exit(1)

    result = research_missing_data(
        team1=team1,
        team2=args.team2,
        sport=args.sport,
        data_type=args.need,
        db_path=args.db_path,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
