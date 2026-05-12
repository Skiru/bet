"""Site adapter for SofaScore — uses the public Sofascore API.

SofaScore is a Next.js SPA that loads events via API after page load.
The HTML rendering approach gets minimal data. Instead, this adapter
calls the Sofascore REST API directly for reliable structured data.

API endpoint: https://api.sofascore.com/api/v1/sport/{sport}/scheduled-events/{date}
Returns JSON with full event details: teams, tournament, time, status.
"""
from typing import List, Dict
from datetime import datetime, timezone, timedelta
import re

try:
    import requests as _requests
except ImportError:
    _requests = None

_SOFASCORE_API = "https://api.sofascore.com/api/v1/sport/{sport}/scheduled-events/{date}"

_SPORT_FROM_URL = {
    "football": "football",
    "soccer": "football",
    "tennis": "tennis",
    "basketball": "basketball",
    "volleyball": "volleyball",
    "hockey": "ice-hockey",
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}


def _detect_sport_from_url(url: str) -> str:
    """Detect sport slug from Sofascore URL."""
    url_lower = url.lower()
    for key, api_sport in _SPORT_FROM_URL.items():
        if f"/{key}" in url_lower:
            return api_sport
    return "football"


def _detect_date_from_url(url: str) -> str:
    """Extract date from URL or use today."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", url)
    if m:
        return m.group(1)
    return datetime.now(timezone(timedelta(hours=2))).strftime("%Y-%m-%d")


def parse(html: str, url: str) -> List[Dict]:
    """Parse Sofascore events via API. The html parameter is ignored; API is used instead."""
    if _requests is None:
        return _parse_html_fallback(html, url)

    sport = _detect_sport_from_url(url)
    date_str = _detect_date_from_url(url)
    api_url = _SOFASCORE_API.format(sport=sport, date=date_str)

    try:
        resp = _requests.get(api_url, headers=_HEADERS, timeout=15)
        if resp.status_code != 200:
            return _parse_html_fallback(html, url)
        data = resp.json()
    except Exception:
        return _parse_html_fallback(html, url)

    events = data.get("events", [])
    results = []

    for ev in events:
        home_team = ev.get("homeTeam", {})
        away_team = ev.get("awayTeam", {})
        tournament = ev.get("tournament", {})
        home = home_team.get("name", "")
        away = away_team.get("name", "")

        if not home or not away:
            continue

        # Parse start time
        start_ts = ev.get("startTimestamp", 0)
        match_time = None
        if start_ts:
            try:
                dt = datetime.fromtimestamp(start_ts, tz=timezone(timedelta(hours=2)))
                match_time = dt.strftime("%H:%M")
            except (OSError, OverflowError):
                pass

        league = tournament.get("name", "")
        country = tournament.get("category", {}).get("name", "")
        status_type = ev.get("status", {}).get("type", "")

        # Skip finished matches
        if status_type == "finished":
            continue

        entry = {
            "home": home,
            "away": away,
            "time": match_time,
            "source_url": url,
            "raw": f"{home} vs {away}",
            "source_type": "sofascore_api",
            "sport": sport.replace("ice-", ""),
        }
        if league:
            entry["league"] = f"{country} - {league}" if country else league
        if ev.get("id"):
            entry["sofascore_id"] = ev["id"]
            entry["match_url"] = f"https://api.sofascore.com/api/v1/event/{ev['id']}/statistics"

        results.append(entry)

    if results:
        from adapters import dedup_results
        return dedup_results(results)

    return _parse_html_fallback(html, url)


def _parse_html_fallback(html: str, url: str) -> List[Dict]:
    """Fallback HTML parser for when API is not available."""
    from .raw_adapter import parse as raw_parse
    return raw_parse(html, url)
