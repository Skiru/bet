import re
from typing import Any, Dict, List
from bet.enrichment.football_data_foundation.live_response_corpus_capture.http_capture import safe_http_get


def make_safe_slug(text: str) -> str:
    """
    Generate a safe, lowercase, alphanumeric-and-hyphen-only string.
    """
    cleaned = text.lower().strip()
    cleaned = re.sub(r"[^a-z0-9\s-]", "", cleaned)
    cleaned = re.sub(r"[\s-]+", "-", cleaned)
    return cleaned


def parse_fifa_html(html_text: str) -> Dict[str, str] | None:
    """
    Parse team names and details from FIFA Match Centre HTML.
    Does not use BeautifulSoup or other non-stdlib parsers if we want robustness,
    or we can use simple regex to avoid extra dependencies.
    """
    # Simple regex parsing
    home_match = re.search(r'class="[^"]*(?:team-home|home-team|home)[^"]*"[^>]*>([^<]+)', html_text)
    away_match = re.search(r'class="[^"]*(?:team-away|away-team|away)[^"]*"[^>]*>([^<]+)', html_text)
    
    home_team = home_match.group(1).strip() if home_match else None
    away_team = away_match.group(1).strip() if away_match else None
    
    if home_team and away_team:
        return {
            "home_team": home_team,
            "away_team": away_team,
        }
    return None


def get_official_seed_candidate() -> Dict[str, Any]:
    """
    Return the audited official seed candidate when live parse is unavailable.
    """
    return {
        "fixture_slug": "worldcup2026-norway-senegal",
        "home_team": "Norway",
        "away_team": "Senegal",
        "competition": "FIFA World Cup 2026",
        "kickoff_at": "2026-06-23T18:00:00Z",
        "source_url": "https://www.fifa.com/en/match-centre/match/17/285023/289273/400021491",
        "match_id": "400021491",
        "is_seed": True,
    }


def discover_canary_fixtures(max_fixtures: int = 3) -> List[Dict[str, Any]]:
    """
    Discover at least one World Cup 2026 canary fixture candidate.
    Uses safe HTTP fetch of FIFA official page, parsing it on the fly.
    If parsing fails/HTTP fails, falls back to audited official seed candidate.
    """
    url = "https://www.fifa.com/en/match-centre/match/17/285023/289273/400021491"
    
    # Perform safe GET
    status_code, body, err = safe_http_get(url, timeout=5.0)
    
    if status_code == 200 and isinstance(body, str) and ("[BLOCKED_HTML]" not in body):
        parsed = parse_fifa_html(body)
        if parsed and parsed.get("home_team") and parsed.get("away_team"):
            home = parsed["home_team"]
            away = parsed["away_team"]
            slug = f"worldcup2026-{make_safe_slug(home)}-{make_safe_slug(away)}"
            
            fixture = {
                "fixture_slug": slug,
                "home_team": home,
                "away_team": away,
                "competition": "FIFA World Cup 2026",
                "kickoff_at": "2026-06-23T18:00:00Z",
                "source_url": url,
                "match_id": "400021491",
                "is_seed": False,
            }
            return [fixture]

    # Fallback to audited official seed candidate
    return [get_official_seed_candidate()]
