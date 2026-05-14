"""ESPN Hidden API client — free, no API key, no rate limits.

Provides per-game statistics for:
- Soccer (football): 28 stats per game across 36+ leagues
- Basketball (NBA/WNBA): 25 stats per game
- Hockey (NHL): 14 stats per game

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
    "tennis": "tennis",
    "volleyball": "volleyball",
}

ESPN_LEAGUES = {
    "football": [
        # Top 5 European + major leagues
        "eng.1", "esp.1", "ger.1", "ita.1", "fra.1",
        "bra.1", "arg.1", "mex.1", "usa.1", "col.1",
        "por.1", "ned.1", "bel.1", "tur.1", "sco.1",
        "pol.1", "cze.1", "aut.1", "gre.1", "den.1",
        "nor.1", "swe.1", "sui.1", "aus.1", "jpn.1",
        "idn.1", "tha.1", "ven.1", "per.1", "bol.1",
        "par.1", "ecu.1", "uru.1",
        # Second divisions
        "eng.2", "eng.3", "esp.2", "ger.2", "ita.2", "fra.2", "ned.2",
        # European cups
        "uefa.champions", "uefa.europa", "uefa.europa.conf",
        # International tournaments
        "fifa.world", "fifa.worldq.uefa", "fifa.worldq.conmebol", "fifa.worldq.afc",
        "uefa.euro", "conmebol.copa_america", "concacaf.gold",
        # Club tournaments
        "conmebol.libertadores", "conmebol.sudamericana",
        "afc.champions", "concacaf.champions",
        # More European first divisions
        "rou.1", "ukr.1", "ser.1", "cro.1", "hun.1", "bul.1",
        "svk.1", "fin.1", "isr.1", "cyp.1", "geo.1",
        "kaz.1", "uzb.1", "rus.1",
        # African
        "rsa.1", "egy.1", "mor.1", "tun.1", "nga.1",
        # Asian
        "chn.1", "ind.1", "sau.1", "uae.1", "qat.1", "kor.1",
        # Women's
        "eng.w.1", "usa.w.1", "fra.w.1",
    ],
    "basketball": ["nba", "wnba"],
    "hockey": ["nhl"],
    "tennis": ["atp", "wta"],
    "volleyball": ["fivb.m", "fivb.w", "ncaa.w", "ncaa.m"],
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
    # European cups
    "champions league": "uefa.champions", "ucl": "uefa.champions",
    "europa league": "uefa.europa", "uel": "uefa.europa",
    "conference league": "uefa.europa.conf",
    # International
    "world cup": "fifa.world",
    "euro": "uefa.euro", "european championship": "uefa.euro",
    "copa america": "conmebol.copa_america",
    "gold cup": "concacaf.gold",
    # South American clubs
    "copa libertadores": "conmebol.libertadores", "libertadores": "conmebol.libertadores",
    "copa sudamericana": "conmebol.sudamericana", "sudamericana": "conmebol.sudamericana",
    # Asian clubs
    "afc champions league": "afc.champions",
    # More European first divisions
    "romanian liga 1": "rou.1", "liga 1 romania": "rou.1",
    "ukrainian premier league": "ukr.1",
    "serbian superliga": "ser.1",
    "croatian hnl": "cro.1", "hnl": "cro.1",
    "hungarian nb i": "hun.1", "nb i": "hun.1",
    "bulgarian first league": "bul.1",
    "slovak super liga": "svk.1",
    "finnish veikkausliiga": "fin.1", "veikkausliiga": "fin.1",
    "israeli premier league": "isr.1",
    "cypriot first division": "cyp.1",
    # Middle East / Asia
    "saudi pro league": "sau.1", "saudi professional league": "sau.1",
    "uae pro league": "uae.1",
    "qatar stars league": "qat.1",
    "chinese super league": "chn.1",
    "indian super league": "ind.1", "isl": "ind.1",
    # Second divisions
    "championship": "eng.2",
    "league one": "eng.3",
    "segunda division": "esp.2", "la liga 2": "esp.2",
    "serie b": "ita.2",
    "2. bundesliga": "ger.2",
    "ligue 2": "fra.2",
    "eerste divisie": "ned.2",
    # African
    "south african premier": "rsa.1", "psl": "rsa.1",
    "egyptian premier league": "egy.1",
    "botola pro": "mor.1",
    "ligue 1 tunisie": "tun.1",
    "npfl": "nga.1", "nigerian premier league": "nga.1",
    # Women
    "wsl": "eng.w.1", "women's super league": "eng.w.1",
    "nwsl": "usa.w.1",
    "d1 arkema": "fra.w.1", "division 1 feminine": "fra.w.1",
    # Tennis tournaments
    "australian open": "atp",
    "roland garros": "atp", "french open": "atp",
    "wimbledon": "atp",
    "us open tennis": "atp",
    "internazionali bnl d'italia": "atp", "rome": "atp", "italian open": "atp",
    "madrid open": "atp",
    "indian wells": "atp", "bnp paribas open": "atp",
    "miami open": "atp",
    "monte carlo": "atp", "monte-carlo masters": "atp",
    "canadian open": "atp", "rogers cup": "atp",
    "cincinnati masters": "atp", "western & southern open": "atp",
    "shanghai masters": "atp",
    "paris masters": "atp",
    "atp finals": "atp",
    "wta finals": "wta",
    # MMA
    # (removed — sport no longer supported)
    # Volleyball
    "fivb world championship": "fivb.m",
    "fivb nations league": "fivb.m",
    "fivb men": "fivb.m",
    "fivb women": "fivb.w",
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

VOLLEYBALL_STAT_MAP = {
    "kills": "kills",
    "aces": "aces",
    "blocks": "blocks",
    "digs": "digs",
    "assists": "assists",
    "errors": "errors",
    "hittingPercentage": "hitting_pct",
    "serviceAces": "service_aces",
    "attackErrors": "attack_errors",
    "blockSolos": "block_solos",
    "blockAssists": "block_assists",
    "points": "points",
    "totalAttacks": "total_attacks",
}

# Sport → stat map lookup
_SPORT_STAT_MAPS = {
    "football": SOCCER_STAT_MAP,
    "basketball": NBA_STAT_MAP,
    "hockey": NHL_STAT_MAP,
    "volleyball": VOLLEYBALL_STAT_MAP,
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
    hockey (NHL), tennis, and volleyball.
    """

    ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

    def __init__(self, sport: str = "football", league: str = "eng.1", rate_limiter: RateLimiter | None = None):
        """Initialize ESPN client for a specific sport and league.

        Args:
            sport: Our sport name (football/basketball/hockey/tennis/volleyball)
            league: ESPN league code (eng.1, nba, nhl, mlb, etc.)
            rate_limiter: RateLimiter instance (not used for ESPN but required by base)
        """
        if rate_limiter is None:
            rate_limiter = RateLimiter()
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

        # Individual sports (tennis) have different structure
        if self.sport == "tennis":
            fixtures = self._get_individual_sport_fixtures(data, date)
            self._save_cache(cache_key, {
                "fixtures": [asdict(f) for f in fixtures],
                "count": len(fixtures),
            })
            return fixtures

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

            season = event.get("season", {})
            season_type = season.get("type", {})
            if isinstance(season_type, dict):
                comp_name = season_type.get("name", self.league)
            else:
                comp_name = season.get("slug", self.league)

            fixture = APIFixture(
                external_id=str(event.get("id", "")),
                source=self.api_name,
                sport=self.sport,
                competition_name=comp_name,
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

    def _get_individual_sport_fixtures(self, data: dict, date: str) -> list[APIFixture]:
        """Parse fixtures for individual sports (tennis).

        Tennis: events are tournaments, groupings contain singles/doubles,
                competitions are individual matches.
        """
        fixtures = []
        for event in data.get("events", []):
            event_name = event.get("name", "")

            # Tennis: matches are in groupings→competitions
            for grouping in event.get("groupings", []):
                group_name = grouping.get("grouping", {}).get("displayName", "")
                # Only singles matches (skip doubles for betting)
                if "double" in group_name.lower():
                    continue
                for comp in grouping.get("competitions", []):
                    fixture = self._parse_individual_competition(
                        comp, f"{event_name} - {group_name}"
                    )
                    if fixture:
                            fixtures.append(fixture)
        return fixtures

    def _parse_individual_competition(
        self, comp: dict, competition_name: str
    ) -> APIFixture | None:
        """Parse a single competition (match/fight) for individual sports."""
        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            return None

        # Individual sports use athlete, not team
        names = []
        for c in competitors:
            athlete = c.get("athlete", {})
            name = athlete.get("displayName", "")
            if not name:
                name = c.get("team", {}).get("displayName", "")
            names.append(name)

        if len(names) < 2 or not names[0] or not names[1]:
            return None

        status = comp.get("status", {})
        status_name = "scheduled"
        if isinstance(status, dict):
            type_info = status.get("type", {})
            if isinstance(type_info, dict):
                status_name = type_info.get("name", "scheduled")

        return APIFixture(
            external_id=str(comp.get("id", "")),
            source=self.api_name,
            sport=self.sport,
            competition_name=competition_name,
            home_team_name=names[0],
            away_team_name=names[1],
            kickoff=comp.get("date", comp.get("startDate", "")),
            status=status_name,
        )

    def get_fixture_stats(self, fixture_id: str) -> list[APIMatchStats]:
        """Get match statistics via /summary endpoint.

        Maps ESPN stat names to normalized keys using sport-specific maps.
        Handles MLB's nested stat structure differently.
        """
        cache_key = f"espn/{self.sport}/{self.league}/fixture_stats/{fixture_id}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return [APIMatchStats(**ms) for ms in cached.get("stats", [])]

        # For tennis, we get stats from scoreboard linescores
        if self.sport == "tennis":
            return self._get_tennis_match_stats(fixture_id)

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

    def _get_tennis_match_stats(self, fixture_id: str) -> list[APIMatchStats]:
        """Get tennis match stats from scoreboard linescores.

        Derives: sets_won, games_won, total_sets from set-by-set scores.
        Searches multiple days if not found on current scoreboard.
        """
        cache_key = f"espn/{self.sport}/{self.league}/fixture_stats/{fixture_id}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return [APIMatchStats(**ms) for ms in cached.get("stats", [])]

        from datetime import timedelta

        # Search across recent days to find this specific match
        today = datetime.now(timezone.utc).date()
        dates_to_search = [today - timedelta(days=d) for d in range(0, 46, 3)]

        for search_date in dates_to_search:
            date_str = search_date.strftime("%Y%m%d")
            try:
                data = self._request("/scoreboard", params={"dates": date_str})
            except Exception:
                continue

            for event in data.get("events", []):
                for grouping in event.get("groupings", []):
                    for comp in grouping.get("competitions", []):
                        if str(comp.get("id", "")) == str(fixture_id):
                            return self._extract_tennis_stats(comp, fixture_id, cache_key)
        return []

    def _extract_tennis_stats(
        self, comp: dict, fixture_id: str, cache_key: str
    ) -> list[APIMatchStats]:
        """Extract tennis statistics from a competition's linescores."""
        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            return []

        stats: dict[str, dict[str, float]] = {}
        names = {"home": "", "away": ""}

        for i, c in enumerate(competitors):
            side = "home" if i == 0 else "away"
            athlete = c.get("athlete", {})
            names[side] = athlete.get("displayName", "")

            linescores = c.get("linescores", [])
            sets_won = sum(1 for ls in linescores if ls.get("winner", False))
            games_won = sum(int(ls.get("value", 0)) for ls in linescores)
            total_sets = len(linescores)

            # Seeding/ranking
            rank = c.get("curatedRank", {}).get("current", 0)

            stats.setdefault("sets_won", {})[side] = float(sets_won)
            stats.setdefault("games_won", {})[side] = float(games_won)
            stats.setdefault("total_sets", {})[side] = float(total_sets)
            # total_games = per-player games won; consumer sums home+away for Total Games O/U market
            stats.setdefault("total_games", {})[side] = float(games_won)
            if rank and rank != "NR":
                try:
                    stats.setdefault("ranking", {})[side] = float(rank)
                except (ValueError, TypeError):
                    pass

        if not names["home"] or not names["away"]:
            return []

        result = [APIMatchStats(
            external_id=fixture_id,
            source=self.api_name,
            sport=self.sport,
            home_team_name=names["home"],
            away_team_name=names["away"],
            stats=stats,
        )]

        self._save_cache(cache_key, {"stats": [asdict(ms) for ms in result]})
        return result

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
        For individual sports (tennis/MMA), searches scoreboard for athlete IDs.
        """
        cache_key = f"espn/{self.sport}/{self.league}/team_search/{team_name.lower().replace(' ', '_')}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return cached.get("team_id")

        # For individual sports, search scoreboard for athlete IDs
        if self.sport == "tennis":
            return self._resolve_athlete_id(team_name)

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

    def _resolve_athlete_id(self, athlete_name: str) -> str | None:
        """Resolve athlete name to ESPN ID by scanning scoreboard."""
        cache_key = f"espn/{self.sport}/{self.league}/athlete_search/{athlete_name.lower().replace(' ', '_')}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return cached.get("team_id")

        try:
            data = self._request("/scoreboard")
        except Exception:
            return None

        name_lower = athlete_name.lower().strip()

        # Build athlete list from scoreboard
        athletes = []
        for event in data.get("events", []):
            # Tennis: groupings→competitions
            for grouping in event.get("groupings", []):
                for comp in grouping.get("competitions", []):
                    for c in comp.get("competitors", []):
                        ath = c.get("athlete", {})
                        if ath:
                            athletes.append({"id": str(c.get("id", "")), **ath})

        # Fuzzy match
        best_match = None
        for a in athletes:
            display = a.get("displayName", "").lower()
            short = a.get("shortName", "").lower()
            full = a.get("fullName", "").lower()

            if display == name_lower or full == name_lower:
                best_match = a
                break
            if name_lower in display or display in name_lower:
                best_match = a
                break
            # Handle "Sinner" matching "Jannik Sinner"
            if name_lower in full or name_lower.split()[-1] in display:
                if not best_match:
                    best_match = a

        if best_match:
            aid = best_match.get("id", "")
            self._save_cache(cache_key, {"team_id": aid})
            return aid

        return None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list[dict]:
        """Get last N completed fixtures for a team via /teams/{id}/schedule."""
        cache_key = f"espn/{self.sport}/{self.league}/team_fixtures/{team_id}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return cached.get("fixtures", [])

        # Individual sports: scan scoreboard for athlete matches
        if self.sport == "tennis":
            return self._get_athlete_recent_matches(team_id, last_n)

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

    def get_team_roster(self, team_id: str) -> list[dict]:
        """Get full team roster with player details.

        Returns list of players: {name, id, position, jersey, age, height, weight, status}
        """
        cache_key = f"espn/{self.sport}/{self.league}/roster/{team_id}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached:
            return cached.get("roster", [])

        try:
            data = self._request(f"/teams/{team_id}/roster")
        except Exception:
            return []

        roster = []
        # ESPN roster can be in athletes[] directly or grouped by position
        athletes = data.get("athletes", [])
        for group in athletes:
            # Group might be a position group dict or direct athlete
            items = group.get("items", [group]) if isinstance(group, dict) else [group]
            for item in items:
                if not isinstance(item, dict):
                    continue
                roster.append({
                    "id": str(item.get("id", "")),
                    "name": item.get("displayName", item.get("fullName", "")),
                    "position": item.get("position", {}).get("abbreviation", "") if isinstance(item.get("position"), dict) else str(item.get("position", "")),
                    "jersey": item.get("jersey", ""),
                    "age": item.get("age", None),
                    "height": item.get("displayHeight", ""),
                    "weight": item.get("displayWeight", ""),
                    "status": item.get("status", {}).get("type", "") if isinstance(item.get("status"), dict) else "active",
                })

        self._save_cache(cache_key, {"roster": roster})
        return roster

    def get_depth_chart(self, team_id: str) -> dict:
        """Get team depth chart (positional hierarchy).

        Returns dict mapping position → list of players in order (starter first).
        """
        cache_key = f"espn/{self.sport}/{self.league}/depthchart/{team_id}"
        cached = self._check_cache(cache_key, ttl_hours=24)
        if cached:
            return cached.get("depthchart", {})

        try:
            data = self._request(f"/teams/{team_id}/depthcharts")
        except Exception:
            return {}

        depth = {}
        items = data.get("items", [])
        for item in items:
            positions = item.get("positions", {})
            for pos_key, pos_data in positions.items():
                if isinstance(pos_data, dict):
                    athletes = pos_data.get("athletes", [])
                    depth[pos_key] = [
                        {
                            "id": str(a.get("id", "")),
                            "name": a.get("displayName", ""),
                            "rank": a.get("rank", i + 1),
                        }
                        for i, a in enumerate(athletes)
                    ]

        self._save_cache(cache_key, {"depthchart": depth})
        return depth

    def get_team_transactions(self, team_id: str, limit: int = 25) -> list[dict]:
        """Get recent team transactions (trades, signings, waivers).

        Returns list of: {date, type, description, player}
        """
        cache_key = f"espn/{self.sport}/{self.league}/transactions/{team_id}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return cached.get("transactions", [])

        try:
            data = self._request(f"/teams/{team_id}/transactions", params={"limit": str(limit)})
        except Exception:
            return []

        transactions = []
        items = data.get("items", data.get("transactions", []))
        for item in items:
            if not isinstance(item, dict):
                continue
            transactions.append({
                "date": item.get("date", ""),
                "type": item.get("type", {}).get("text", "") if isinstance(item.get("type"), dict) else str(item.get("type", "")),
                "description": item.get("text", item.get("description", "")),
                "player": item.get("athlete", {}).get("displayName", "") if isinstance(item.get("athlete"), dict) else "",
            })

        self._save_cache(cache_key, {"transactions": transactions})
        return transactions

    def _get_athlete_recent_matches(self, athlete_id: str, last_n: int = 10) -> list[dict]:
        """Get recent matches for an athlete by scanning multiple days of scoreboard.

        For tennis/MMA, ESPN only exposes match data via the scoreboard endpoint.
        We scan up to 45 days back (sampling every 3 days) to build proper L10 history.
        """
        cache_key = f"espn/{self.sport}/{self.league}/athlete_fixtures/{athlete_id}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached and len(cached.get("fixtures", [])) >= last_n:
            return cached.get("fixtures", [])

        from datetime import timedelta

        matches = []
        seen_ids: set[str] = set()
        today = datetime.now(timezone.utc).date()

        # Scan today + past 45 days (every 3 days for efficiency)
        dates_to_scan = [today - timedelta(days=d) for d in range(0, 46, 3)]

        for scan_date in dates_to_scan:
            if len(matches) >= last_n:
                break
            date_str = scan_date.strftime("%Y%m%d")
            try:
                data = self._request("/scoreboard", params={"dates": date_str})
            except Exception:
                continue

            for event in data.get("events", []):
                comps_to_check = []
                # MMA: competitions at event level
                comps_to_check.extend(event.get("competitions", []))
                # Tennis: competitions inside groupings
                for g in event.get("groupings", []):
                    comps_to_check.extend(g.get("competitions", []))

                for comp in comps_to_check:
                    comp_id = str(comp.get("id", ""))
                    if comp_id in seen_ids:
                        continue

                    competitors = comp.get("competitors", [])
                    athlete_in_match = any(
                        str(c.get("id", "")) == str(athlete_id)
                        for c in competitors
                    )
                    if not athlete_in_match:
                        continue

                    status = comp.get("status", {}).get("type", {})
                    if status.get("state") != "post":
                        continue

                    seen_ids.add(comp_id)
                    names = []
                    for c in competitors:
                        ath = c.get("athlete", {})
                        names.append(ath.get("displayName", ""))

                    matches.append({
                        "id": comp_id,
                        "date": comp.get("date", comp.get("startDate", "")),
                        "home_team": names[0] if names else "",
                        "away_team": names[1] if len(names) > 1 else "",
                    })

        matches.sort(key=lambda m: m.get("date", ""), reverse=True)
        result = matches[:last_n]
        self._save_cache(cache_key, {"fixtures": result})
        return result

    def get_standings(self) -> list[dict]:
        """Get league standings/table."""
        cache_key = f"espn/{self.sport}/{self.league}/standings"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return cached.get("standings", [])

        try:
            # v2 standings API works for ALL sports (soccer, basketball, hockey, etc.)
            url = f"https://site.api.espn.com/apis/v2/sports/{self._espn_sport}/{self.league}/standings"
            response = requests.get(url, headers=self._build_headers(), timeout=self.TIMEOUT)
            data = response.json()
        except Exception:
            return []

        standings = []
        for child in data.get("children", data.get("standings", [])):
            if isinstance(child, dict):
                entries = child.get("standings", {}).get("entries", [])
                if not entries:
                    entries = child.get("entries", [])
                for entry in entries:
                    team = entry.get("team", {})
                    stats_list = entry.get("stats", [])
                    stat_dict = {}
                    for s in stats_list:
                        stat_dict[s.get("name", "")] = s.get("value", s.get("displayValue", ""))
                    standings.append({
                        "team_id": str(team.get("id", "")),
                        "team_name": team.get("displayName", ""),
                        "rank": stat_dict.get("rank", ""),
                        "wins": stat_dict.get("wins", ""),
                        "losses": stat_dict.get("losses", ""),
                        "draws": stat_dict.get("ties", stat_dict.get("draws", "")),
                        "points": stat_dict.get("points", ""),
                        "gamesPlayed": stat_dict.get("gamesPlayed", ""),
                    })

        self._save_cache(cache_key, {"standings": standings})
        return standings

    @staticmethod
    def extract_odds_from_event(event: dict) -> dict | None:
        """Extract DraftKings odds from an ESPN scoreboard event.

        Returns dict with moneyline, total, spread in American odds format.
        Returns None if no odds available.
        """
        competitions = event.get("competitions", [])
        if not competitions:
            return None

        odds_list = competitions[0].get("odds", [])
        if not odds_list:
            return None

        # Find DraftKings odds (usually first/only)
        odds_data = None
        for o in odds_list:
            if o is not None:
                odds_data = o
                break

        if not odds_data:
            return None

        result = {"provider": "DraftKings", "source": "espn"}

        # Moneyline
        ml = odds_data.get("moneyline", {})
        if ml:
            result["moneyline"] = {
                "home": ml.get("home", {}).get("close", {}).get("odds", ""),
                "away": ml.get("away", {}).get("close", {}).get("odds", ""),
                "draw": ml.get("draw", {}).get("close", {}).get("odds", ""),
            }
            result["moneyline_open"] = {
                "home": ml.get("home", {}).get("open", {}).get("odds", ""),
                "away": ml.get("away", {}).get("open", {}).get("odds", ""),
                "draw": ml.get("draw", {}).get("open", {}).get("odds", ""),
            }

        # Totals (over/under)
        total = odds_data.get("total", {})
        if total:
            result["total"] = {
                "line": odds_data.get("overUnder", ""),
                "over_odds": total.get("over", {}).get("close", {}).get("odds", ""),
                "under_odds": total.get("under", {}).get("close", {}).get("odds", ""),
            }

        # Spread / Point Spread
        spread = odds_data.get("pointSpread", {})
        if spread:
            result["spread"] = {
                "home_line": spread.get("home", {}).get("close", {}).get("line", ""),
                "home_odds": spread.get("home", {}).get("close", {}).get("odds", ""),
                "away_line": spread.get("away", {}).get("close", {}).get("line", ""),
                "away_odds": spread.get("away", {}).get("close", {}).get("odds", ""),
            }

        return result

    @staticmethod
    def extract_form_and_records(event: dict) -> dict:
        """Extract team form strings and records from scoreboard event."""
        result = {}
        competitions = event.get("competitions", [])
        if not competitions:
            return result

        for comp in competitions[0].get("competitors", []):
            side = comp.get("homeAway", "")
            team = comp.get("team", {})
            team_name = team.get("displayName", "")
            form = comp.get("form", "")
            records = comp.get("records", [])

            record_summary = ""
            for r in records:
                if r.get("type") == "total":
                    record_summary = r.get("summary", "")
                    break

            if team_name:
                result[side] = {
                    "team": team_name,
                    "form": form,
                    "record": record_summary,
                }

        return result

    def get_cross_competition_schedule(
        self, team_id: str, future_only: bool = False
    ) -> list[dict]:
        """Get all-competition schedule for a team (soccer only).

        Uses soccer/all/teams/{id}/schedule endpoint.
        Returns matches across ALL competitions (league + cups + continental).
        """
        if self.sport != "football":
            return []

        cache_key = f"espn/{self.sport}/all/cross_schedule/{team_id}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return cached.get("events", [])

        params = {}
        if future_only:
            params["fixture"] = "true"

        try:
            url = f"{self.ESPN_BASE}/soccer/all/teams/{team_id}/schedule"
            response = requests.get(
                url, params=params, headers=self._build_headers(), timeout=self.TIMEOUT
            )
            if response.status_code >= 400:
                return []
            data = response.json()
        except Exception:
            return []

        events = []
        for event in data.get("events", []):
            competitions = event.get("competitions", [])
            if not competitions:
                continue
            comp = competitions[0]
            competitors = comp.get("competitors", [])
            home_name = ""
            away_name = ""
            score = ""
            for c in competitors:
                t = c.get("team", {})
                if c.get("homeAway") == "home":
                    home_name = t.get("displayName", "")
                    score = str(c.get("score", ""))
                else:
                    away_name = t.get("displayName", "")
                    score = f"{score}-{c.get('score', '')}"

            events.append({
                "id": event.get("id"),
                "date": event.get("date", ""),
                "name": event.get("name", ""),
                "home_team": home_name,
                "away_team": away_name,
                "score": score,
                "league": event.get("league", {}).get("abbreviation", ""),
            })

        self._save_cache(cache_key, {"events": events})
        return events


def get_espn_league_for_competition(competition_name: str) -> str | None:
    """Determine ESPN league code from a competition name.

    Returns None if competition is not in ESPN's coverage.
    """
    if not competition_name:
        return None
    name_lower = competition_name.lower().strip()
    
    # 1. Exact match
    if name_lower in COMPETITION_TO_ESPN_LEAGUE:
        return COMPETITION_TO_ESPN_LEAGUE[name_lower]
        
    # 2 & 3. Substring match
    matches = []
    for key, code in COMPETITION_TO_ESPN_LEAGUE.items():
        if key in name_lower or name_lower in key:
            matches.append((key, code))
            
    if matches:
        # Sort by length descending, pick the longest match
        matches.sort(key=lambda x: len(x[0]), reverse=True)
        return matches[0][1]
        
    return None
