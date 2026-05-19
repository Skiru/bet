"""Google Sports client — H2H, scores, and match data via SerpAPI 'Team A vs Team B' queries.

This is a DEDICATED enrichment client that leverages SerpAPI's structured sports_results
for the specific purpose of H2H enrichment and score verification.

Data extracted per sport:
  Football/Hockey: H2H games (scores, venue, tournament, red cards, dates)
  Tennis: H2H matches (sets, rankings, tournament, stage)
  Basketball: H2H games (scores, venue, tournament)

Integration points:
  - Fallback chain: after primary sport APIs, before web_research_agent (L5.5)
  - DB: fixtures table (H2H encounters), team_form (h2h_values), match_stats
  - Budget: shares SerpAPI 250/month quota — smart targeting only (shortlisted candidates)

Usage:
  from api_clients import get_client
  client = get_client("google-sports")
  h2h = client.get_h2h_enrichment("Barcelona", "Real Sociedad", sport="football")
"""

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests

from .base_client import BaseAPIClient, CACHE_DIR
from .rate_limiter import RateLimiter
from bet.models.normalized import NormalizedFixture, NormalizedMatchStats

# Add src to path for DB access
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    from bet.db.connection import get_db
    from bet.db.repositories import TeamRepo, FixtureRepo, StatsRepo, CompetitionRepo, SportRepo
    from bet.db.models import Fixture, TeamForm
    _HAS_DB = True
except ImportError:
    _HAS_DB = False


SERPAPI_BASE = "https://serpapi.com/search.json"


@dataclass
class H2HMatch:
    """Single H2H encounter extracted from Google Sports."""
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    date: str
    tournament: str
    venue: str
    venue_kgmid: str = ""
    home_kgmid: str = ""
    away_kgmid: str = ""
    has_red_card_home: bool = False
    has_red_card_away: bool = False
    video_highlights_url: str = ""
    sport: str = "football"


@dataclass
class TennisH2HMatch:
    """Single tennis H2H match."""
    player1: str
    player2: str
    player1_ranking: str = ""
    player2_ranking: str = ""
    sets: dict = field(default_factory=dict)  # {"player1": [6,3,6], "player2": [4,6,4]}
    date: str = ""
    stage: str = ""
    tournament: str = ""
    location: str = ""
    winner: str = ""


@dataclass
class GoogleSportsEnrichment:
    """Complete enrichment result from Google Sports query."""
    query: str
    sport: str
    source: str = "google-sports"
    h2h_matches: list = field(default_factory=list)  # List of H2HMatch or TennisH2HMatch
    current_match: dict = field(default_factory=dict)  # game_spotlight data (if match is today)
    goal_scorers: list = field(default_factory=list)  # [{player, minute, team}]
    team_kgmids: dict = field(default_factory=dict)  # {team_name: kgmid}
    raw_data: dict = field(default_factory=dict)


class GoogleSportsClient(BaseAPIClient):
    """Google Sports enrichment client via SerpAPI.

    Dedicated to extracting structured sports data from Google's knowledge panels
    using the 'Team A vs Team B' query pattern.

    Budget: shares SerpAPI's 250/month free tier.
    Use only for shortlisted candidates missing H2H data from primary APIs.
    """

    TIMEOUT = 20
    # Maximum queries per pipeline run to preserve monthly budget
    MAX_QUERIES_PER_RUN = 15

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="google-sports",
            base_url=SERPAPI_BASE,
            rate_limiter=rate_limiter,
        )
        self._queries_this_run = 0

    def _build_headers(self) -> dict:
        return {"Accept": "application/json"}

    def _load_api_key(self) -> str:
        """Load SerpAPI key (shared with serpapi_client).

        Override base class to use 'serpapi' key name instead of 'google-sports'.
        """
        import os

        # Check env var first
        env_key = os.environ.get("SERPAPI_KEY", "")
        if env_key:
            return env_key

        # Then config file (use 'serpapi' key, not 'google-sports')
        try:
            config_path = PROJECT_ROOT / "config" / "api_keys.json"
            with open(config_path) as f:
                keys = json.load(f)
            return keys.get("serpapi", "")
        except (FileNotFoundError, json.JSONDecodeError):
            return ""

    def _search(self, query: str) -> dict | None:
        """Execute SerpAPI search with budget protection."""
        if not self.api_key or self.api_key == "YOUR_KEY_HERE":
            return None

        if self._queries_this_run >= self.MAX_QUERIES_PER_RUN:
            print(f"[{self.api_name}] Run budget exhausted ({self.MAX_QUERIES_PER_RUN} queries)")
            return None

        if not self.rate_limiter.can_request("serpapi"):
            print(f"[{self.api_name}] Monthly SerpAPI quota exhausted")
            return None

        # Check cache (48h TTL for H2H data — changes slowly)
        cache_key = f"google-sports/{query.lower().replace(' ', '_')[:80]}"
        cached = self._check_cache(cache_key, ttl_hours=48)
        if cached:
            return cached

        try:
            response = requests.get(
                SERPAPI_BASE,
                params={
                    "q": query,
                    "api_key": self.api_key,
                    "engine": "google",
                    "hl": "en",  # Always English for consistent parsing
                },
                timeout=self.TIMEOUT,
            )
            self.rate_limiter.record_request("serpapi", query, cost=1)
            self._queries_this_run += 1

            if response.status_code == 429:
                print(f"[{self.api_name}] Rate limited (HTTP 429)")
                return None
            if response.status_code >= 400:
                print(f"[{self.api_name}] HTTP {response.status_code}")
                return None

            data = response.json()
            self._save_cache(cache_key, data)
            return data

        except requests.exceptions.RequestException as e:
            print(f"[{self.api_name}] Request failed: {e}")
            return None

    # ─── Public API ───────────────────────────────────────────────────────

    def get_h2h_enrichment(self, team1: str, team2: str, sport: str = "football") -> GoogleSportsEnrichment:
        """Main enrichment method: query 'team1 vs team2' and extract all available data.

        Args:
            team1: First team/player name
            team2: Second team/player name
            sport: One of football, basketball, hockey, tennis, volleyball

        Returns:
            GoogleSportsEnrichment with H2H matches, current match data, goal scorers, etc.
        """
        query = f"{team1} vs {team2}"
        data = self._search(query)

        result = GoogleSportsEnrichment(query=query, sport=sport)

        if not data:
            return result

        sr = data.get("sports_results", {})
        if not sr:
            return result

        result.raw_data = sr

        if sport == "tennis":
            result.h2h_matches = self._parse_tennis_h2h(sr)
        else:
            result.h2h_matches = self._parse_team_h2h(sr, sport)

        # Extract game_spotlight (today's match with detailed data)
        spotlight = sr.get("game_spotlight", {})
        if spotlight:
            result.current_match = spotlight
            result.goal_scorers = self._extract_goal_scorers(spotlight)
            result.team_kgmids = self._extract_kgmids(spotlight)

        # Also extract kgmids from games list
        for match in result.h2h_matches:
            if hasattr(match, "home_kgmid") and match.home_kgmid:
                result.team_kgmids[match.home_team] = match.home_kgmid
            if hasattr(match, "away_kgmid") and match.away_kgmid:
                result.team_kgmids[match.away_team] = match.away_kgmid

        return result

    def get_h2h_enrichment_and_save(
        self, team1: str, team2: str, sport: str = "football"
    ) -> GoogleSportsEnrichment:
        """Get H2H enrichment AND save results to database.

        This is the primary method for pipeline integration.
        """
        enrichment = self.get_h2h_enrichment(team1, team2, sport)

        if _HAS_DB and enrichment.h2h_matches:
            self._save_to_db(enrichment, sport)

        return enrichment

    # ─── Parsing Methods ──────────────────────────────────────────────────

    def _parse_team_h2h(self, sr: dict, sport: str) -> list[H2HMatch]:
        """Parse H2H data for team sports (football, basketball, hockey)."""
        games = sr.get("games", [])
        if not games:
            return []

        matches = []
        for game in games:
            teams = game.get("teams", [])
            if len(teams) < 2:
                continue

            home = teams[0]
            away = teams[1]

            try:
                home_score = int(home.get("score", 0))
            except (ValueError, TypeError):
                home_score = 0
            try:
                away_score = int(away.get("score", 0))
            except (ValueError, TypeError):
                away_score = 0

            match = H2HMatch(
                home_team=home.get("name", ""),
                away_team=away.get("name", ""),
                home_score=home_score,
                away_score=away_score,
                date=game.get("date", ""),
                tournament=game.get("tournament", ""),
                venue=game.get("venue", ""),
                venue_kgmid=game.get("venue_kgmid", ""),
                home_kgmid=home.get("kgmid", ""),
                away_kgmid=away.get("kgmid", ""),
                has_red_card_home=home.get("red_card", False),
                has_red_card_away=away.get("red_card", False),
                video_highlights_url=game.get("video_highlights", {}).get("link", ""),
                sport=sport,
            )
            matches.append(match)

        return matches

    def _parse_tennis_h2h(self, sr: dict) -> list[TennisH2HMatch]:
        """Parse H2H data for tennis."""
        tables = sr.get("tables", {})
        if not tables:
            return []

        tournament = tables.get("title", "")
        games = tables.get("games", [])
        if not games:
            return []

        matches = []
        for game in games:
            players = game.get("players", [])
            if len(players) < 2:
                continue

            p1 = players[0]
            p2 = players[1]

            # Parse set scores
            p1_sets = []
            p2_sets = []
            for key in sorted(p1.get("sets", {}).keys()):
                try:
                    p1_sets.append(int(p1["sets"][key]))
                except (ValueError, TypeError):
                    p1_sets.append(0)
            for key in sorted(p2.get("sets", {}).keys()):
                try:
                    p2_sets.append(int(p2["sets"][key]))
                except (ValueError, TypeError):
                    p2_sets.append(0)

            # Determine winner (more sets won)
            p1_won = sum(1 for a, b in zip(p1_sets, p2_sets) if a > b)
            p2_won = sum(1 for a, b in zip(p1_sets, p2_sets) if b > a)
            winner = p1.get("name", "") if p1_won > p2_won else p2.get("name", "")

            match = TennisH2HMatch(
                player1=p1.get("name", ""),
                player2=p2.get("name", ""),
                player1_ranking=p1.get("ranking", ""),
                player2_ranking=p2.get("ranking", ""),
                sets={"player1": p1_sets, "player2": p2_sets},
                date=game.get("date", ""),
                stage=game.get("stage", ""),
                tournament=tournament,
                location=game.get("location", ""),
                winner=winner,
            )
            matches.append(match)

        return matches

    def _extract_goal_scorers(self, spotlight: dict) -> list[dict]:
        """Extract goal scorer details from game_spotlight."""
        scorers = []
        for team in spotlight.get("teams", []):
            team_name = team.get("name", "")
            for gs in team.get("goal_summary", []):
                player = gs.get("player", {})
                for goal in gs.get("goals", []):
                    time_info = goal.get("in_game_time", {})
                    minute = time_info.get("minute", 0)
                    stoppage = time_info.get("stoppage", 0)
                    scorers.append({
                        "player": player.get("name", ""),
                        "jersey_number": player.get("jersey_number", ""),
                        "position": player.get("position", ""),
                        "team": team_name,
                        "minute": minute,
                        "stoppage": stoppage,
                        "time_display": f"{minute}'+{stoppage}" if stoppage else f"{minute}'",
                    })
        return scorers

    def _extract_kgmids(self, spotlight: dict) -> dict[str, str]:
        """Extract Knowledge Graph IDs for team linking."""
        kgmids = {}
        for team in spotlight.get("teams", []):
            name = team.get("name", "")
            kgmid = team.get("kgmid", "")
            if name and kgmid:
                kgmids[name] = kgmid
        return kgmids

    # ─── Database Integration ─────────────────────────────────────────────

    def _save_to_db(self, enrichment: GoogleSportsEnrichment, sport: str) -> None:
        """Save enrichment results to database.

        Stores:
          - H2H fixtures in fixtures table
          - H2H scores in team_form (h2h_values)
          - Team kgmids as external_ids
        """
        if not _HAS_DB:
            return

        try:
            with get_db() as conn:
                team_repo = TeamRepo(conn)
                fixture_repo = FixtureRepo(conn)
                stats_repo = StatsRepo(conn)
                sport_repo = SportRepo(conn)
                comp_repo = CompetitionRepo(conn)

                # Get sport ID
                sport_obj = sport_repo.get_by_name(sport)
                if not sport_obj:
                    print(f"[{self.api_name}] Sport '{sport}' not in DB, skipping save")
                    return
                sport_id = sport_obj.id

                if sport == "tennis":
                    self._save_tennis_h2h(
                        enrichment, conn, team_repo, stats_repo, sport_id
                    )
                else:
                    self._save_team_h2h(
                        enrichment, conn, team_repo, fixture_repo,
                        stats_repo, comp_repo, sport_id
                    )

                conn.commit()
                print(f"[{self.api_name}] Saved {len(enrichment.h2h_matches)} H2H matches to DB")

        except Exception as e:
            print(f"[{self.api_name}] DB save error: {e}")

    def _save_team_h2h(
        self, enrichment, conn, team_repo, fixture_repo, stats_repo, comp_repo, sport_id
    ):
        """Save team sport H2H data to DB."""
        # We need to track goals scored BY EACH TEAM across all H2H meetings
        # (regardless of home/away position in each match).
        # First, determine who the two "sides" are from the query context.
        if not enrichment.h2h_matches:
            return

        first_match = enrichment.h2h_matches[0]
        if not isinstance(first_match, H2HMatch):
            return

        # Resolve the two teams from the first match
        team1_obj = team_repo.find_or_create(first_match.home_team, sport_id)
        team2_obj = team_repo.find_or_create(first_match.away_team, sport_id)
        team1_id = team1_obj.id
        team2_id = team2_obj.id
        team1_name = first_match.home_team
        team2_name = first_match.away_team

        # Track goals scored by each team across all meetings
        team1_goals = []  # goals scored by team1 in each H2H meeting
        team2_goals = []  # goals scored by team2 in each H2H meeting

        for match in enrichment.h2h_matches:
            if not isinstance(match, H2HMatch):
                continue

            # Resolve teams for this specific match
            home_team = team_repo.find_or_create(match.home_team, sport_id)
            away_team = team_repo.find_or_create(match.away_team, sport_id)
            home_id = home_team.id
            away_id = away_team.id

            # Resolve competition
            comp_id = None
            if match.tournament:
                comp_id = comp_repo.find_or_create(match.tournament, sport_id)

            # Parse date to ISO format (best effort)
            kickoff = self._parse_date(match.date)

            # Upsert fixture
            fixture = Fixture(
                id=None,
                external_id=f"gsports-{match.home_kgmid}-{match.away_kgmid}-{match.date}",
                sport_id=sport_id,
                competition_id=comp_id,
                home_team_id=home_id,
                away_team_id=away_id,
                kickoff=kickoff,
                status="finished",
                score_home=match.home_score,
                score_away=match.away_score,
                source="google-sports",
            )
            fixture_id = fixture_repo.upsert(fixture)

            # Save red card data as match_stats
            if match.has_red_card_home:
                stats_repo.save_match_stats(fixture_id, home_id, {"red_cards": 1}, "google-sports")
            if match.has_red_card_away:
                stats_repo.save_match_stats(fixture_id, away_id, {"red_cards": 1}, "google-sports")

            # Track goals BY TEAM IDENTITY (not by position in match)
            # Match which team is team1 vs team2 regardless of home/away slot
            if home_id == team1_id:
                team1_goals.append(match.home_score)
                team2_goals.append(match.away_score)
            elif away_id == team1_id:
                team1_goals.append(match.away_score)
                team2_goals.append(match.home_score)
            else:
                # Teams don't match (shouldn't happen) — use position
                team1_goals.append(match.home_score)
                team2_goals.append(match.away_score)

        # Save H2H form data (goals scored in H2H meetings) — only if richer than existing
        if team1_goals:
            self._save_h2h_form_if_richer(
                stats_repo, conn, team1_id, team2_id, sport_id, team1_goals
            )
        if team2_goals:
            self._save_h2h_form_if_richer(
                stats_repo, conn, team2_id, team1_id, sport_id, team2_goals
            )

    def _save_h2h_form_if_richer(
        self, stats_repo, conn, team_id: int, opponent_id: int,
        sport_id: int, h2h_values: list[int], stat_key: str = "goals_scored"
    ) -> None:
        """Save H2H team_form ONLY if we have more data than what's already stored.

        Prevents google-sports (2-3 meetings) from overwriting richer data
        from Flashscore/ESPN (5-10 meetings).
        """
        # Check existing row
        existing = conn.execute(
            "SELECT h2h_values FROM team_form "
            "WHERE team_id = ? AND stat_key = ? AND h2h_opponent_id = ?",
            (team_id, stat_key, opponent_id),
        ).fetchone()

        if existing and existing["h2h_values"]:
            try:
                existing_values = json.loads(existing["h2h_values"])
                if len(existing_values) >= len(h2h_values):
                    # Existing data is richer — don't overwrite
                    return
            except (json.JSONDecodeError, TypeError):
                pass

        # Save (new or richer data)
        h2h_form = TeamForm(
            id=None,
            team_id=team_id,
            sport_id=sport_id,
            stat_key=stat_key,
            l10_values=h2h_values[:10],
            l5_values=h2h_values[:5],
            l10_avg=sum(h2h_values[:10]) / max(len(h2h_values[:10]), 1),
            l5_avg=sum(h2h_values[:5]) / max(len(h2h_values[:5]), 1),
            h2h_values=h2h_values,
            h2h_opponent_id=opponent_id,
            trend=self._calc_trend(h2h_values),
            source="google-sports",
        )
        stats_repo.save_team_form(h2h_form)

    def _save_tennis_h2h(self, enrichment, conn, team_repo, stats_repo, sport_id):
        """Save tennis H2H data to DB as team_form with sets_won stat."""
        if not enrichment.h2h_matches:
            return

        first_match = enrichment.h2h_matches[0]
        if not isinstance(first_match, TennisH2HMatch):
            return

        p1 = team_repo.find_or_create(first_match.player1, sport_id)
        p2 = team_repo.find_or_create(first_match.player2, sport_id)

        # Track sets won by each player across all H2H meetings
        p1_sets_won = []
        p2_sets_won = []

        for match in enrichment.h2h_matches:
            if not isinstance(match, TennisH2HMatch):
                continue
            # Ensure players are in DB
            team_repo.find_or_create(match.player1, sport_id)
            team_repo.find_or_create(match.player2, sport_id)

            # Count sets won per player
            p1_s = match.sets.get("player1", [])
            p2_s = match.sets.get("player2", [])
            p1_won = sum(1 for a, b in zip(p1_s, p2_s) if a > b)
            p2_won = sum(1 for a, b in zip(p1_s, p2_s) if b > a)
            p1_sets_won.append(p1_won)
            p2_sets_won.append(p2_won)

        # Save H2H sets_won form (only if richer than existing)
        if p1_sets_won:
            self._save_h2h_form_if_richer(
                stats_repo, conn, p1.id, p2.id, sport_id, p1_sets_won,
                stat_key="sets_won",
            )
        if p2_sets_won:
            self._save_h2h_form_if_richer(
                stats_repo, conn, p2.id, p1.id, sport_id, p2_sets_won,
                stat_key="sets_won",
            )

    # ─── Utility Methods ──────────────────────────────────────────────────

    @staticmethod
    def _parse_date(date_str: str) -> str:
        """Best-effort parse of Google's date format to ISO.

        Handles: "Jan 18, 26", "Sep 28, 25", "Apr 19", "Sun, Feb 1"
        """
        if not date_str:
            return ""

        # Clean up
        date_str = date_str.strip()

        now = datetime.now()

        # Try common formats
        formats = [
            ("%b %d, %y", True),    # "Jan 18, 26" — has year
            ("%b %d, %Y", True),    # "Jan 18, 2026" — has full year
            ("%b %d", False),       # "Apr 19" — no year, assume current
            ("%a, %b %d", False),   # "Sun, Feb 1" — no year
        ]

        for fmt, has_year in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                if not has_year:
                    # No year in format — assume current year
                    # If date is > 2 months in future, it's probably last year
                    dt = dt.replace(year=now.year)
                    if (dt - now).days > 60:
                        dt = dt.replace(year=now.year - 1)
                elif dt.year < 100:
                    # Two-digit year (e.g., 26 → 2026, 25 → 2025)
                    dt = dt.replace(year=2000 + dt.year)
                return dt.strftime("%Y-%m-%dT00:00:00Z")
            except ValueError:
                continue

        return date_str  # Return as-is if parsing fails

    @staticmethod
    def _calc_trend(values: list) -> str:
        """Calculate simple trend from values list."""
        if len(values) < 3:
            return "stable"
        recent = sum(values[:3]) / 3
        older = sum(values[3:6]) / max(len(values[3:6]), 1) if len(values) > 3 else recent
        if recent > older * 1.2:
            return "up"
        elif recent < older * 0.8:
            return "down"
        return "stable"

    # ─── BaseAPIClient Interface ──────────────────────────────────────────

    def get_fixtures(self, date: str) -> list[NormalizedFixture]:
        """Not applicable — this client enriches existing fixtures."""
        return []

    def get_fixture_stats(self, fixture_id: str) -> NormalizedMatchStats | None:
        """Not applicable — use get_h2h_enrichment() instead."""
        return None

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[NormalizedFixture]:
        """Get H2H fixtures via Google Sports query."""
        enrichment = self.get_h2h_enrichment(team1_id, team2_id)
        fixtures = []
        for match in enrichment.h2h_matches[:last_n]:
            if isinstance(match, H2HMatch):
                fixtures.append(NormalizedFixture(
                    fixture_id=f"gsports-{match.home_team}-{match.away_team}-{match.date}".replace(" ", "_"),
                    source="google-sports",
                    sport=match.sport,
                    competition=match.tournament,
                    home_team=match.home_team,
                    away_team=match.away_team,
                    kickoff=self._parse_date(match.date),
                    status="FT",
                ))
        return fixtures

    def resolve_team_id(self, team_name: str, **kwargs) -> str | None:
        """Uses team names directly."""
        return team_name if team_name else None

    def is_available(self) -> bool:
        """Available if SerpAPI key is set and budget remains."""
        return (
            bool(self.api_key)
            and self.api_key != "YOUR_KEY_HERE"
            and self._queries_this_run < self.MAX_QUERIES_PER_RUN
        )

    def get_budget_status(self) -> dict:
        """Return current budget usage for this run."""
        return {
            "queries_this_run": self._queries_this_run,
            "max_per_run": self.MAX_QUERIES_PER_RUN,
            "remaining": self.MAX_QUERIES_PER_RUN - self._queries_this_run,
        }
