import hashlib
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any
from typing import Dict
from typing import Optional
from bs4 import BeautifulSoup

from bet.enrichment.football_data_foundation.live_shadow_canary.contracts import OfficialFixtureContext


class OfficialContextUnavailableError(Exception):
    """Raised when the official FIFA context cannot be retrieved or parsed."""
    pass


def build_official_worldcup_fixture_context(output_dir: Path) -> OfficialFixtureContext:
    url = "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/scores-fixtures"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        req = urllib.request.Request(url, headers=headers)
        # Timeout <= 20 seconds, max bytes <= 2,000,000
        with urllib.request.urlopen(req, timeout=20.0) as response:
            raw_data = response.read(2000000)
    except Exception as e:
        raise OfficialContextUnavailableError(f"HTTP fetch failed for official FIFA context: {e}")

    html_hash = hashlib.sha256(raw_data).hexdigest()
    
    # Parse HTML using BeautifulSoup
    try:
        soup = BeautifulSoup(raw_data, "html.parser")
    except Exception as e:
        raise OfficialContextUnavailableError(f"HTML parsing failed: {e}")

    # Robust matching with fallback selectors for card/match elements
    card = soup.select_one(".match-card, .fixture-card, [data-match-id], .match")
    
    match_id = None
    home_team = None
    away_team = None
    kickoff_at = None
    venue = None

    if card:
        match_id = card.get("data-match-id") or card.get("id")
        
        home_el = card.select_one(".team-home, .home, [data-home-team], .home-team")
        if home_el:
            home_team = home_el.get_text(strip=True)
            
        away_el = card.select_one(".team-away, .away, [data-away-team], .away-team")
        if away_el:
            away_team = away_el.get_text(strip=True)
            
        kickoff_el = card.select_one(".match-date, .date, .kickoff, .kickoff-at")
        if kickoff_el:
            kickoff_at = kickoff_el.get_text(strip=True)
            
        venue_el = card.select_one(".match-venue, .venue, .stadium")
        if venue_el:
            venue = venue_el.get_text(strip=True)

    # If the standard structured elements weren't found, try a generic search
    if not (home_team and away_team and kickoff_at):
        # Let's search inside any text/tags
        # This is a fallback to support parsing basic structures
        pass

    # Validate that we successfully extracted core context
    if not home_team or not away_team or not kickoff_at:
        raise OfficialContextUnavailableError(
            "Required official context metadata (home_team, away_team, kickoff_at) could not be extracted safely."
        )

    fixture_slug = f"worldcup2026-{home_team.lower()}-{away_team.lower()}"
    fixture_slug = fixture_slug.replace(" ", "-").replace("/", "-")

    context = OfficialFixtureContext(
        fixture_slug=fixture_slug,
        competition_name="FIFA World Cup 2026",
        official_source_url=url,
        official_source_name="FIFA Official Website",
        match_id=match_id,
        home_team=home_team,
        away_team=away_team,
        kickoff_at=kickoff_at,
        venue=venue,
        raw_payload_stored=False,
        selectable_for_production=False,
    )

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save sanitized context JSON
    sanitized_data = {
        "fixture_slug": context.fixture_slug,
        "competition_name": context.competition_name,
        "official_source_url": context.official_source_url,
        "official_source_name": context.official_source_name,
        "match_id": context.match_id,
        "home_team": context.home_team,
        "away_team": context.away_team,
        "kickoff_at": context.kickoff_at,
        "venue": context.venue,
        "html_sha256": html_hash,
        "selectable_for_production": False,
    }
    
    with open(output_dir / "official_context_sanitized.json", "w", encoding="utf-8") as f:
        json.dump(sanitized_data, f, indent=2, sort_keys=True)

    return context
