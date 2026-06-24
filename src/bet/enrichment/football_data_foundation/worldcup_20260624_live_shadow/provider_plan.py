from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

@dataclass(frozen=True)
class ProviderPlan:
    provider_key: str
    access_mode: str
    max_requests_per_fixture: int
    max_rps: float | None
    cache_subdir: str
    required: bool
    notes: Tuple[str, ...] = field(default_factory=tuple)

    def to_json(self) -> Dict[str, Any]:
        return {
            "provider_key": self.provider_key,
            "access_mode": self.access_mode,
            "max_requests_per_fixture": self.max_requests_per_fixture,
            "max_rps": self.max_rps,
            "cache_subdir": self.cache_subdir,
            "required": self.required,
            "notes": list(self.notes),
        }


def get_sportdb_fixtures_url() -> str:
    return "https://api.sportdb.dev/api/flashscore/football/world:8/world-championship:lvUBR5F8/2026/fixtures?page=1"


def get_sportdb_results_url() -> str:
    return "https://api.sportdb.dev/api/flashscore/football/world:8/world-championship:lvUBR5F8/2026/results?page=1"


def get_sportdb_detail_url(event_id: str) -> str:
    return f"https://api.sportdb.dev/api/flashscore/match/{event_id}/details?with_events=true"


def get_sportdb_stats_url(event_id: str) -> str:
    return f"https://api.sportdb.dev/api/flashscore/match/{event_id}/stats"


def get_sportdb_lineups_url(event_id: str) -> str:
    return f"https://api.sportdb.dev/api/flashscore/match/{event_id}/lineups"


def get_sportdb_odds_url(event_id: str) -> str:
    return f"https://api.sportdb.dev/api/flashscore/match/{event_id}/odds?geoIpCode=GB&geoIpSubdivisionCode=GPENG"


def get_highlightly_matches_url(date: str) -> str:
    return f"https://soccer.highlightly.net/matches?date={date}&timezone=Etc/UTC&limit=100"


def get_highlightly_match_detail_url(match_id: str) -> str:
    return f"https://soccer.highlightly.net/matches/{match_id}"


def get_highlightly_statistics_url(match_id: str) -> str:
    return f"https://soccer.highlightly.net/statistics/{match_id}"


def get_highlightly_lineups_url(match_id: str) -> str:
    return f"https://soccer.highlightly.net/lineups/{match_id}"


def get_highlightly_events_url(match_id: str) -> str:
    return f"https://soccer.highlightly.net/events/{match_id}"


def get_api_football_fixtures_url(date: str) -> str:
    return f"https://v3.football.api-sports.io/fixtures?date={date}"


def get_api_football_detail_url(fixture_id: str) -> str:
    return f"https://v3.football.api-sports.io/fixtures?id={fixture_id}"


def get_football_data_org_matches_url(date: str) -> str:
    return f"https://api.football-data.org/v4/matches?dateFrom={date}&dateTo={date}"


def get_football_data_org_detail_url(match_id: str) -> str:
    return f"https://api.football-data.org/v4/matches/{match_id}"


def get_espn_scoreboard_url(date: str) -> str:
    date_clean = date.replace("-", "")
    return f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={date_clean}"


def get_espn_summary_url(event_id: str) -> str:
    return f"http://site.api.espn.com/apis/site/v2/sports/soccer/all/summary?event={event_id}"


def build_provider_plans() -> List[ProviderPlan]:
    return [
        ProviderPlan(
            provider_key="sportdb",
            access_mode="live_api_cache_then_replay",
            max_requests_per_fixture=8,
            max_rps=2.5,
            cache_subdir="sportdb",
            required=True,
            notes=(
                "Use dashboard-correct /api/flashscore routes",
                "Respect SportDB 2.5 RPS free limit",
            ),
        ),
        ProviderPlan(
            provider_key="highlightly",
            access_mode="live_api_cache_then_replay",
            max_requests_per_fixture=6,
            max_rps=1.0,
            cache_subdir="highlightly",
            required=True,
            notes=(
                "Use https://soccer.highlightly.net football API",
                "Match search first, detail endpoints after real ID",
            ),
        ),
        ProviderPlan(
            provider_key="api-football",
            access_mode="live_api_cache_then_replay",
            max_requests_per_fixture=6,
            max_rps=1.0,
            cache_subdir="api-football",
            required=True,
            notes=("Use existing API_FOOTBALL_KEY env mapping",),
        ),
        ProviderPlan(
            provider_key="football-data-org",
            access_mode="reference_api_cache_then_replay",
            max_requests_per_fixture=3,
            max_rps=1.0,
            cache_subdir="football-data-org",
            required=True,
            notes=("Reference/status/score only",),
        ),
        ProviderPlan(
            provider_key="espn-baseline",
            access_mode="public_reference_cache_then_replay",
            max_requests_per_fixture=3,
            max_rps=1.0,
            cache_subdir="espn-baseline",
            required=False,
            notes=("Unofficial shadow cross-check; no article/story/media text",),
        ),
    ]
