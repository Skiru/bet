"""ESPN Hidden API client — free, no API key, no rate limits.

Provides per-game statistics for:
- Soccer (football): 28 stats per game across 36+ leagues
- Basketball (NBA/WNBA): 25 stats per game
- Hockey (NHL): 14 stats per game
- Baseball (MLB): batting/pitching/fielding stats

Base URL: http://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/
"""

from dataclasses import asdict
from datetime import datetime, timezone

import requests

from .base_client import BaseAPIClient, APIError, APINotFoundError, CACHE_DIR
from .rate_limiter import RateLimiter
from .api_football import APIFixture, APIMatchStats

# ESPN uses "soccer" not "football"
ESPN_SPORT_MAP = {
    "football": "soccer",
    "basketball": "basketball",
    "hockey": "hockey",
    "baseball": "baseball",
}

ESPN_LEAGUES = {
    "football": [
        "eng.1", "esp.1", "ger.1", "ita.1", "fra.1",
        "bra.1", "arg.1", "mex.1", "usa.1", "col.1",
        "por.1", "ned.1", "bel.1", "tur.1", "sco.1",
        "pol.1", "cze.1", "aut.1", "gre.1", "den.1",
        "nor.1", "swe.1", "sui.1", "aus.1", "jpn.1",
        "idn.1", "tha.1", "ven.1", "per.1", "bol.1",
        "par.1", "ecu.1", "uru.1",
    ],
    "basketball": ["nba", "wnba"],
    "hockey": ["nhl"],
    "baseball": ["mlb"],
}

# Competition name → ESPN league code (for football enrichment)
COMPETITION_TO_ESPN_LEAGUE = {
    "premier league": "eng.1",
    "championship": "eng.2",
    "la liga": "esp.1", "laliga": "esp.1",
    "bundesliga": "ger.1",
    "2. bundesliga": "ger.2",
    "serie a": "ita.1",
    "serie b": "ita.2",
    "ligue 1": "fra.1",
    "ligue 2": "fra.2",
    "brasileirão": "bra.1", "serie a brazil": "bra.1", "brasileiro": "bra.1",
    "mls": "usa.1", "major league soccer": "usa.1",
    "liga mx": "mex.1",
    "liga profesional": "arg.1",
    "primera a": "col.1",
    "ligapro": "ecu.1",
    "primeira liga": "por.1", "liga portugal": "por.1",
    "eredivisie": "ned.1",
    "pro league": "bel.1", "jupiler pro league": "bel.1",
    "super lig": "tur.1", "süper lig": "tur.1",
    "premiership": "sco.1", "scottish premiership": "sco.1",
    "ekstraklasa": "pol.1",
    "superliga": "den.1", "danish superliga": "den.1",
    "eliteserien": "nor.1",
    "allsvenskan": "swe.1",
    "super league": "sui.1", "swiss super league": "sui.1",
    "j.league": "jpn.1", "j1 league": "jpn.1",
    "a-league": "aus.1", "a-league men": "aus.1",
    "k league 1": "kor.1", "k league": "kor.1",
    "primera division": "uru.1",
    "primera division paraguay": "par.1",
    "primera division bolivia": "bol.1",
    "primera division peru": "per.1", "liga 1": "per.1",
    "primera division venezuela": "ven.1",
    "austrian bundesliga": "aut.1",
    "czech first league": "cze.1", "gambrinus liga": "cze.1",
    "super league greece": "gre.1",
    "thai league 1": "tha.1",
    "indonesian super league": "idn.1", "liga 1 indonesia": "idn.1",
}

# --- Stat Mappings: ESPN name → normalized key ---

SOCCER_STAT_MAP = {
    "wonCorners": "corners",
    "foulsCommitted": "fouls",
    "yellowCards": "yellow_cards",
    "redCards": "red_cards",
    "totalShots": "shots",
    "shotsOnTarget": "shots_on_target",
    "possessionPct": "possession",
    "offsides": "offsides",
    "saves": "saves",
    "totalPasses": "total_passes",
    "accuratePasses": "accurate_passes",
    "passPct": "pass_accuracy",
    "totalCrosses": "crosses",
    "accurateCrosses": "accurate_crosses",
    "totalLongBalls": "long_balls",
    "accurateLongBalls": "accurate_long_balls",
    "blockedShots": "blocked_shots",
    "effectiveTackles": "tackles_won",
    "totalTackles": "tackles",
    "tacklePct": "tackle_accuracy",
    "interceptions": "interceptions",
    "effectiveClearance": "clearances",
    "totalClearance": "total_clearances",
    "penaltyKickGoals": "penalty_goals",
    "penaltyKickShots": "penalty_attempts",
    "shotPct": "shot_accuracy",
    "crossPct": "cross_accuracy",
    "longballPct": "long_ball_accuracy",
}

NBA_STAT_MAP = {
    "totalRebounds": "rebounds",
    "offensiveRebounds": "offensive_rebounds",
    "defensiveRebounds": "defensive_rebounds",
    "assists": "assists",
    "steals": "steals",
    "blocks": "blocks",
    "turnovers": "turnovers",
    "fouls": "fouls",
    "technicalFouls": "technical_fouls",
    "flagrantFouls": "flagrant_fouls",
    "turnoverPoints": "turnover_points",
    "fastBreakPoints": "fast_break_points",
    "pointsInPaint": "points_in_paint",
    "largestLead": "largest_lead",
    "fieldGoalPct": "fg_pct",
    "threePointFieldGoalPct": "three_pct",
    "freeThrowPct": "ft_pct",
}

NHL_STAT_MAP = {
    "blockedShots": "blocks",
    "hits": "hits",
    "takeaways": "takeaways",
    "shotsTotal": "shots",
    "powerPlayGoals": "powerplay_goals",
    "powerPlayOpportunities": "power_play_opportunities",
    "powerPlayPct": "power_play_pct",
    "shortHandedGoals": "shorthanded_goals",
    "faceoffsWon": "faceoffs_won",
    "faceoffPercent": "faceoff_pct",
    "giveaways": "giveaways",
    "penalties": "penalties",
    "penaltyMinutes": "pim",
    "shootoutGoals": "shootout_goals",
}

MLB_BATTING_MAP = {
    "hits": "hits",
    "runs": "runs",
    "RBIs": "rbis",
    "homeRuns": "home_runs",
    "strikeouts": "strikeouts_batting",
    "walks": "walks",
    "stolenBases": "stolen_bases",
    "hitByPitch": "hit_by_pitch",
    "groundBalls": "ground_balls",
}

MLB_PITCHING_MAP = {
    "strikeouts": "strikeouts_pitching",
    "earnedRuns": "earned_runs",
    "hits": "hits_allowed",
    "walks": "walks_allowed",
    "saves": "saves",
    "losses": "losses",
}

# Sport → stat map lookup
_SPORT_STAT_MAPS = {
    "football": SOCCER_STAT_MAP,
    "basketball": NBA_STAT_MAP,
    "hockey": NHL_STAT_MAP,
}


def _get_stat_map(sport: str) -> dict[str, str]:
    """Return the appropriate stat map for a sport."""
    return _SPORT_STAT_MAPS.get(sport, {})


def _is_game_finished(event: dict) -> bool:
    """Determine if an ESPN event is finished.

    ESPN status.type.name can be empty for completed games.
    Use date + score presence as reliable indicator.
    """
    # Check explicit status first
    status = event.get("status", {})
    if isinstance(status, dict):
        type_info = status.get("type", {})
        if isinstance(type_info, dict):
            state = type_info.get("state", "")
            name = type_info.get("name", "")
            if state == "post" or name in (
                "STATUS_FULL_TIME", "STATUS_FINAL",
            ):
                return True

    # Fallback: date in past + score exists
    event_date_str = event.get("date", "")
    if not event_date_str:
        return False

    try:
        game_date = datetime.fromisoformat(
            event_date_str.rstrip("Z")
        ).replace(tzinfo=timezone.utc)
        is_past = game_date < datetime.now(timezone.utc)
    except (ValueError, TypeError):
        return False

    if not is_past:
        return False

    # Check for scores in competitions
    competitions = event.get("competitions", [])
    if not competitions:
        return False
    competitors = competitions[0].get("competitors", [])
    has_score = any(c.get("score") is not None for c in competitors)
    return has_score


class ESPNClient(BaseAPIClient):
    """ESPN Hidden API client — free, unlimited requests.

    Supports soccer (36+ leagues), basketball (NBA/WNBA),
    hockey (NHL), and baseball (MLB).
    """

    ESPN_BASE = "http://site.api.espn.com/apis/site/v2/sports"

    def __init__(self, sport: str, league: str, rate_limiter: RateLimiter):
        """Initialize ESPN client for a specific sport and league.

        Args:
            sport: Our sport name (football/basketball/hockey/baseball)
            league: ESPN league code (eng.1, nba, nhl, mlb, etc.)
            rate_limiter: RateLimiter instance (not used for ESPN but required by base)
        """
        self.sport = sport
        self.league = league
        self._espn_sport = ESPN_SPORT_MAP.get(sport, sport)

        base_url = f"{self.ESPN_BASE}/{self._espn_sport}/{league}"
        super().__init__(
            api_name=f"espn-{sport}",
            base_url=base_url,
            rate_limiter=rate_limiter,
        )

    def _load_api_key(self) -> str:
        """ESPN needs no API key — return sentinel so is_available() returns True."""
        return "espn-no-key"

    def _build_headers(self) -> dict:
        """No API key header needed for ESPN."""
        return {"Accept": "application/json"}

    def _request(self, endpoint: str, params: dict | None = None, cost: int = 0) -> dict:
        """Make ESPN request — skip rate limiter, still handle retries/errors."""
        url = f"{self.base_url}{endpoint}"
        last_error = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = requests.get(
                    url,
                    params=params,
                    headers=self._build_headers(),
                    timeout=self.TIMEOUT,
                )

                if response.status_code == 404:
                    raise APINotFoundError(
                        f"[{self.api_name}] Not found: {endpoint}",
                        status_code=404,
                    )
                if response.status_code >= 400:
                    raise APIError(
                        f"[{self.api_name}] HTTP {response.status_code}: {response.text[:200]}",
                        status_code=response.status_code,
                    )

                return response.json()

            except APINotFoundError:
                raise
            except APIError:
                raise
            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    import time
                    backoff = self.BACKOFF_BASE * (2 ** (attempt - 1))
                    time.sleep(backoff)

        raise APIError(
            f"[{self.api_name}] Failed after {self.MAX_RETRIES} attempts: {last_error}"
        )

    def get_fixtures(self, date: str) -> list[APIFixture]:
        """Get fixtures for a date (YYYY-MM-DD) via /scoreboard endpoint."""
        date_compact = date.replace("-", "")

        cache_key = f"espn/{self.sport}/{self.league}/fixtures/{date}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached:
            return [
                APIFixture(**f) for f in cached.get("fixtures", [])
                if isinstance(f, dict) and "external_id" in f
            ]

        try:
            data = self._request("/scoreboard", params={"dates": date_compact})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching fixtures for {date}: {e}")
            return []

        fixtures = []
        for event in data.get("events", []):
            competitions = event.get("competitions", [])
            if not competitions:
                continue

            comp = competitions[0]
            competitors = comp.get("competitors", [])
            home_name = ""
            away_name = ""
            for c in competitors:
                if c.get("homeAway") == "home":
                    home_name = c.get("team", {}).get("displayName", "")
                else:
                    away_name = c.get("team", {}).get("displayName", "")

            status = event.get("status", {})
            status_name = "scheduled"
            if isinstance(status, dict):
                type_info = status.get("type", {})
                if isinstance(type_info, dict):
                    status_name = type_info.get("name", "scheduled")

            fixture = APIFixture(
                external_id=str(event.get("id", "")),
                source=self.api_name,
                sport=self.sport,
                competition_name=event.get("season", {}).get("type", {}).get("name", self.league),
                home_team_name=home_name,
                away_team_name=away_name,
                kickoff=event.get("date", ""),
                status=status_name,
            )
            fixtures.append(fixture)

        self._save_cache(cache_key, {
            "fixtures": [asdict(f) for f in fixtures],
            "count": len(fixtures),
        })

        return fixtures

    def get_fixture_stats(self, fixture_id: str) -> list[APIMatchStats]:
        """Get match statistics via /summary endpoint.

        Maps ESPN stat names to normalized keys using sport-specific maps.
        Handles MLB's nested stat structure differently.
        """
        cache_key = f"espn/{self.sport}/{self.league}/fixture_stats/{fixture_id}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return [APIMatchStats(**ms) for ms in cached.get("stats", [])]

        try:
            data = self._request("/summary", params={"event": fixture_id})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching stats for fixture {fixture_id}: {e}")
            return []

        boxscore = data.get("boxscore", {})
        teams_data = boxscore.get("teams", [])
        if len(teams_data) < 2:
            return []

        stats: dict[str, dict[str, float]] = {}
        teams: dict[str, str] = {}

        for i, team_data in enumerate(teams_data):
            team_info = team_data.get("team", {})
            team_name = team_info.get("displayName", "")
            # Determine side from homeAway field or position
            home_away = team_data.get("homeAway", "")
            if home_away == "home":
                side = "home"
            elif home_away == "away":
                side = "away"
            else:
                side = "home" if i == 0 else "away"
            teams[side] = team_name

            team_stats_raw = team_data.get("statistics", [])

            if self.sport == "baseball":
                # MLB: nested categories with sub-stats
                self._parse_mlb_stats(team_stats_raw, side, stats)
            else:
                # Soccer/NBA/NHL: flat stat list
                self._parse_flat_stats(team_stats_raw, side, stats)

        # Extract goals/points from scores (not in boxscore stats)
        # Soccer/Hockey → "goals", Basketball → "points"
        score_key = None
        if self.sport in ("football", "hockey"):
            score_key = "goals"
        elif self.sport == "basketball":
            score_key = "points"

        if score_key:
            header = data.get("header", {})
            header_comps = header.get("competitions", [])
            if header_comps:
                for comp in header_comps[0].get("competitors", []):
                    ha = comp.get("homeAway", "")
                    score_val = comp.get("score", "")
                    if ha in ("home", "away") and score_val:
                        try:
                            stats.setdefault(score_key, {})[ha] = float(score_val)
                        except (ValueError, TypeError):
                            pass

        if not teams.get("home") or not teams.get("away"):
            return []

        result = [APIMatchStats(
            external_id=fixture_id,
            source=self.api_name,
            sport=self.sport,
            home_team_name=teams["home"],
            away_team_name=teams["away"],
            stats=stats,
        )]

        self._save_cache(cache_key, {"stats": [asdict(ms) for ms in result]})
        return result

    def _parse_flat_stats(
        self, team_stats_raw: list, side: str, stats: dict[str, dict[str, float]]
    ) -> None:
        """Parse flat statistics list (soccer, NBA, NHL)."""
        stat_map = _get_stat_map(self.sport)

        for stat_entry in team_stats_raw:
            espn_name = stat_entry.get("name", "")
            display_value = stat_entry.get("displayValue", "0")

            normalized_key = stat_map.get(espn_name)
            if not normalized_key:
                continue

            try:
                value = float(display_value.replace("%", "").strip() or "0")
            except (ValueError, TypeError):
                value = 0.0

            if normalized_key not in stats:
                stats[normalized_key] = {}
            stats[normalized_key][side] = value

    def _parse_mlb_stats(
        self, team_stats_raw: list, side: str, stats: dict[str, dict[str, float]]
    ) -> None:
        """Parse MLB nested statistics (batting/pitching/fielding categories)."""
        for category in team_stats_raw:
            cat_name = category.get("name", "").lower()
            sub_stats = category.get("stats", [])

            if cat_name == "batting":
                stat_map = MLB_BATTING_MAP
            elif cat_name == "pitching":
                stat_map = MLB_PITCHING_MAP
            else:
                continue

            for stat_entry in sub_stats:
                espn_name = stat_entry.get("name", "")
                display_value = stat_entry.get("displayValue", "0")

                normalized_key = stat_map.get(espn_name)
                if not normalized_key:
                    continue

                try:
                    value = float(display_value.replace("%", "").strip() or "0")
                except (ValueError, TypeError):
                    value = 0.0

                if normalized_key not in stats:
                    stats[normalized_key] = {}
                stats[normalized_key][side] = value

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Get H2H data — uses team schedule filtered by opponent."""
        cache_key = f"espn/{self.sport}/{self.league}/h2h/{team1_id}_{team2_id}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return cached.get("games", [])

        try:
            data = self._request(f"/teams/{team1_id}/schedule")
        except Exception:
            return []

        events = data.get("events", [])
        h2h_games = []
        for event in events:
            if not _is_game_finished(event):
                continue
            competitions = event.get("competitions", [])
            if not competitions:
                continue
            competitors = competitions[0].get("competitors", [])
            # Check if team2 is in this game
            opponent_match = any(
                str(c.get("id", "")) == str(team2_id)
                or str(c.get("team", {}).get("id", "")) == str(team2_id)
                for c in competitors
            )
            if opponent_match:
                h2h_games.append({
                    "id": event.get("id"),
                    "date": event.get("date", ""),
                    "competitors": competitors,
                })

        h2h_games.sort(key=lambda g: g.get("date", ""), reverse=True)
        result = h2h_games[:last_n]

        self._save_cache(cache_key, {"games": result})
        return result

    def resolve_team_id(self, team_name: str) -> str | None:
        """Resolve team name to ESPN team ID via /teams endpoint.

        Uses case-insensitive fuzzy matching. Results cached for 7 days.
        """
        cache_key = f"espn/{self.sport}/{self.league}/team_search/{team_name.lower().replace(' ', '_')}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return cached.get("team_id")

        try:
            data = self._request("/teams")
        except Exception:
            return None

        # ESPN returns teams in .sports[].leagues[].teams[] or .teams[]
        teams_list = []
        sports = data.get("sports", [])
        if sports:
            for sport_data in sports:
                for league_data in sport_data.get("leagues", []):
                    for team_entry in league_data.get("teams", []):
                        t = team_entry.get("team", team_entry)
                        teams_list.append(t)
        else:
            # Direct teams array
            for team_entry in data.get("teams", []):
                t = team_entry.get("team", team_entry)
                teams_list.append(t)

        # Fuzzy match: exact → contains → abbreviation
        name_lower = team_name.lower()
        best_match = None

        for t in teams_list:
            display = t.get("displayName", "").lower()
            short = t.get("shortDisplayName", "").lower()
            abbr = t.get("abbreviation", "").lower()
            location = t.get("location", "").lower()

            if display == name_lower or short == name_lower:
                best_match = t
                break
            if name_lower in display or display in name_lower:
                best_match = t
                break
            if name_lower in location or location in name_lower:
                best_match = t
            if abbr == name_lower and not best_match:
                best_match = t

        if best_match:
            tid = str(best_match.get("id", ""))
            self._save_cache(cache_key, {"team_id": tid})
            return tid

        return None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list[dict]:
        """Get last N completed fixtures for a team via /teams/{id}/schedule."""
        cache_key = f"espn/{self.sport}/{self.league}/team_fixtures/{team_id}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return cached.get("fixtures", [])

        try:
            data = self._request(f"/teams/{team_id}/schedule")
        except Exception:
            return []

        events = data.get("events", [])
        finished = []
        for event in events:
            if not _is_game_finished(event):
                continue

            competitions = event.get("competitions", [])
            if not competitions:
                continue

            comp = competitions[0]
            competitors = comp.get("competitors", [])
            home_name = ""
            away_name = ""
            score = ""
            for c in competitors:
                team_info = c.get("team", {})
                c_name = team_info.get("displayName", "")
                c_score = c.get("score", "0")
                if c.get("homeAway") == "home":
                    home_name = c_name
                    score = f"{c_score}"
                else:
                    away_name = c_name
                    score = f"{score}-{c_score}"

            finished.append({
                "id": event.get("id"),
                "date": event.get("date", ""),
                "home_team": home_name,
                "away_team": away_name,
                "score": score,
            })

        # Sort by date descending (most recent first)
        finished.sort(key=lambda f: f.get("date", ""), reverse=True)
        result = finished[:last_n]

        self._save_cache(cache_key, {"fixtures": result})
        return result

    def get_injuries(self) -> list[dict]:
        """Get injury reports for the league."""
        cache_key = f"espn/{self.sport}/{self.league}/injuries"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached:
            return cached.get("injuries", [])

        try:
            data = self._request("/injuries")
        except Exception:
            return []

        injuries = []
        for team_data in data.get("injuries", data.get("teams", [])):
            team_name = ""
            if isinstance(team_data, dict):
                team_name = team_data.get("team", {}).get("displayName", "")
                for injury in team_data.get("injuries", []):
                    injuries.append({
                        "team": team_name,
                        "player": injury.get("athlete", {}).get("displayName", ""),
                        "status": injury.get("status", ""),
                        "type": injury.get("type", {}).get("description", ""),
                    })

        self._save_cache(cache_key, {"injuries": injuries})
        return injuries


def get_espn_league_for_competition(competition_name: str) -> str | None:
    """Determine ESPN league code from a competition name.

    Returns None if competition is not in ESPN's coverage.
    """
    if not competition_name:
        return None
    name_lower = competition_name.lower().strip()
    return COMPETITION_TO_ESPN_LEAGUE.get(name_lower)
