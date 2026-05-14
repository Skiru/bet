"""ESPN multi-sport scraper — wraps ESPNClient for the new scrapers module.

Covers all 5 core sports: football, basketball, hockey, tennis, volleyball.
Uses the free ESPN Site API (no key required, no rate limits).

Writes to: league_profiles, player_season_stats, scraper_runs, + lookup tables.
"""
from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import text

from bet.scrapers.base import BaseScraper, ScraperError
from bet.scrapers.models import PlayerSeasonStat

logger = logging.getLogger(__name__)

# ESPN sport name → our sport name (for display)
_OUR_SPORT_MAP = {
    "football": "football",
    "basketball": "basketball",
    "hockey": "hockey",
    "tennis": "tennis",
    "volleyball": "volleyball",
}


def _safe_float(val, default: float = 0.0) -> float:
    """Convert a value to float safely."""
    if val is None:
        return default
    try:
        f = float(str(val).replace("%", "").strip() or "0")
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


class BaseESPNScraper(BaseScraper):
    """Base ESPN scraper — shared logic for all sports.

    Subclasses set `sport` and optionally override behaviour.
    Each subclass wraps ESPNClient, iterating over leagues to scrape
    team-level and player-level stats, then writing results to DB.
    """

    source_name = "espn"
    _request_delay = (0.2, 0.5)  # ESPN has no rate limits — be polite

    def _get_espn_client(self, league: str):
        """Create an ESPNClient for the given league."""
        from bet.api_clients.espn import ESPNClient
        from bet.api_clients.rate_limiter import RateLimiter

        return ESPNClient(
            sport=self.sport,
            league=league,
            rate_limiter=RateLimiter(),
        )

    def _resolve_leagues(self, competition: str) -> list[str]:
        """Resolve competition name → list of ESPN league codes to scrape."""
        from bet.api_clients.espn import (
            ESPN_LEAGUES,
            get_espn_league_for_competition,
        )

        # If competition maps to a specific ESPN league, use it
        league = get_espn_league_for_competition(competition)
        if league:
            return [league]

        # If competition matches an ESPN league code directly (e.g. "eng.1")
        all_leagues = ESPN_LEAGUES.get(self.sport, [])
        if competition in all_leagues:
            return [competition]

        # Fallback: scrape ALL known leagues for this sport
        return all_leagues

    # ------------------------------------------------------------------
    # Team season stats (league_profiles)
    # ------------------------------------------------------------------
    def scrape_team_season_stats(self, competition: str, season: str) -> int:
        """Scrape team-level stats by fetching recent fixtures for each team.

        For each team in the league standings, fetches last 10 completed
        fixtures via ESPNClient.get_team_last_fixtures(), then
        ESPNClient.get_fixture_stats() for each fixture. Aggregates
        per-stat averages and writes to league_profiles.
        """
        leagues = self._resolve_leagues(competition)
        total_inserted = 0

        for league_code in leagues:
            try:
                inserted = self._scrape_league_team_stats(
                    competition, season, league_code
                )
                total_inserted += inserted
            except ScraperError:
                raise
            except Exception as e:
                logger.warning(
                    "ESPN team stats failed for %s/%s: %s",
                    self.sport, league_code, e,
                )

        return total_inserted

    def _scrape_league_team_stats(
        self, competition: str, season: str, league_code: str
    ) -> int:
        """Scrape team stats for a single ESPN league."""
        client = self._get_espn_client(league_code)

        # Get teams from standings
        standings = client.get_standings()
        if not standings:
            logger.debug("ESPN: no standings for %s/%s", self.sport, league_code)
            return 0

        with self._get_session() as session:
            sport_id = self._find_or_create_sport(session, self.sport)
            comp_name = competition or league_code
            comp_id = self._find_or_create_competition(
                session, sport_id, comp_name, "", season,
            )
            accum: dict[str, list[float]] = defaultdict(list)
            teams_processed = 0

            with self._track_run(
                session, f"team_stats/{self.sport}/{league_code}/{season}"
            ) as counts:
                for entry in standings:
                    team_name = entry.get("team_name", "")
                    team_id_espn = entry.get("team_id", "")
                    if not team_name or not team_id_espn:
                        continue

                    self._find_or_create_team(session, sport_id, team_name, "")

                    # Get last 10 fixtures and their stats
                    fixtures = client.get_team_last_fixtures(team_id_espn, last_n=10)
                    team_accum: dict[str, list[float]] = defaultdict(list)

                    for fix in fixtures:
                        fix_id = fix.get("id")
                        if not fix_id:
                            continue

                        self._rate_limit()
                        match_stats_list = client.get_fixture_stats(str(fix_id))
                        if not match_stats_list:
                            continue

                        ms = match_stats_list[0]
                        stats = ms.stats if hasattr(ms, "stats") else {}

                        # Determine which side this team is on
                        home_name = (
                            ms.home_team_name
                            if hasattr(ms, "home_team_name")
                            else ""
                        )
                        away_name = (
                            ms.away_team_name
                            if hasattr(ms, "away_team_name")
                            else ""
                        )
                        if team_name.lower() in home_name.lower():
                            side = "home"
                        elif team_name.lower() in away_name.lower():
                            side = "away"
                        else:
                            # Fuzzy: check if any word from team_name appears
                            side = self._guess_side(team_name, home_name, away_name)

                        for stat_key, side_vals in stats.items():
                            if isinstance(side_vals, dict) and side in side_vals:
                                val = _safe_float(side_vals[side])
                                team_accum[stat_key].append(val)

                    # Aggregate team values into league-level accumulator
                    for sk, vals in team_accum.items():
                        if vals:
                            avg = sum(vals) / len(vals)
                            accum[sk].append(avg)

                    teams_processed += 1
                    counts["scraped"] = teams_processed

                if accum:
                    inserted = self._upsert_league_profiles(
                        session, comp_id, season, accum
                    )
                    counts["inserted"] = inserted
                else:
                    inserted = 0

            session.commit()
            logger.info(
                "ESPN team stats: %s/%s — %d teams, %d profiles written",
                self.sport, league_code, teams_processed, inserted,
            )
            return inserted

    @staticmethod
    def _guess_side(team_name: str, home: str, away: str) -> str:
        """Fuzzy side detection — find which competitor matches team_name."""
        tn = team_name.lower().split()
        h = home.lower()
        a = away.lower()
        home_score = sum(1 for w in tn if w in h)
        away_score = sum(1 for w in tn if w in a)
        return "home" if home_score >= away_score else "away"

    # ------------------------------------------------------------------
    # Player season stats
    # ------------------------------------------------------------------
    def scrape_player_season_stats(self, competition: str, season: str) -> int:
        """Scrape player-level stats from ESPN.

        Only available for team sports with roster endpoints
        (basketball, hockey). Football/tennis/volleyball lack ESPN
        player gamelogs.
        """
        if self.sport not in ("basketball", "hockey"):
            logger.debug(
                "ESPN: player stats not available for %s", self.sport,
            )
            return 0

        leagues = self._resolve_leagues(competition)
        total_inserted = 0

        for league_code in leagues:
            try:
                inserted = self._scrape_league_player_stats(
                    competition, season, league_code,
                )
                total_inserted += inserted
            except Exception as e:
                logger.warning(
                    "ESPN player stats failed for %s/%s: %s",
                    self.sport, league_code, e,
                )

        return total_inserted

    def _scrape_league_player_stats(
        self, competition: str, season: str, league_code: str,
    ) -> int:
        """Scrape player stats for a single league via roster + team stats."""
        client = self._get_espn_client(league_code)

        standings = client.get_standings()
        if not standings:
            return 0

        with self._get_session() as session:
            sport_id = self._find_or_create_sport(session, self.sport)
            comp_name = competition or league_code
            comp_id = self._find_or_create_competition(
                session, sport_id, comp_name, "", season,
            )
            now_str = datetime.now(timezone.utc).isoformat()
            inserted = 0

            with self._track_run(
                session, f"player_stats/{self.sport}/{league_code}/{season}"
            ) as counts:
                for entry in standings:
                    team_name = entry.get("team_name", "")
                    team_id_espn = entry.get("team_id", "")
                    if not team_name or not team_id_espn:
                        continue

                    db_team_id = self._find_or_create_team(
                        session, sport_id, team_name, "",
                    )

                    self._rate_limit()
                    roster = client.get_team_roster(team_id_espn)

                    for player in roster:
                        p_name = player.get("name", "")
                        p_id = player.get("id", "")
                        if not p_name:
                            continue

                        ext_id = f"espn_{self.sport}_{p_id}" if p_id else f"espn_{p_name.replace(' ', '_').lower()}"
                        position = player.get("position", "")

                        athlete_id = self._find_or_create_athlete(
                            session, ext_id, sport_id, p_name,
                            db_team_id, position,
                        )

                        # Build stats from roster info (limited)
                        stats_dict = {}
                        if player.get("age"):
                            stats_dict["age"] = player["age"]

                        # Check for existing entry
                        existing = session.execute(
                            text("""
                                SELECT id FROM player_season_stats
                                WHERE athlete_id = :aid AND season = :s AND source = :src
                            """),
                            {"aid": athlete_id, "s": season, "src": "espn"},
                        ).fetchone()

                        if existing:
                            session.execute(
                                text("""
                                    UPDATE player_season_stats
                                    SET stats_json = :sj, updated_at = :upd
                                    WHERE id = :pid
                                """),
                                {
                                    "sj": json.dumps(stats_dict),
                                    "upd": now_str,
                                    "pid": existing[0],
                                },
                            )
                        else:
                            pss = PlayerSeasonStat(
                                athlete_id=athlete_id,
                                competition_id=comp_id,
                                season=season,
                                stats_json=json.dumps(stats_dict),
                                source="espn",
                                updated_at=now_str,
                            )
                            session.add(pss)
                            inserted += 1

                    counts["scraped"] += len(roster)

                counts["inserted"] = inserted

            session.commit()
            logger.info(
                "ESPN player stats: %s/%s — %d players written",
                self.sport, league_code, inserted,
            )
            return inserted


# =====================================================================
# Sport-specific subclasses (thin — just set sport)
# =====================================================================


class FootballESPNScraper(BaseESPNScraper):
    """ESPN scraper for football (soccer).

    Provides: corners, fouls, yellow_cards, shots, shots_on_target,
    possession, offsides, saves, passes, crosses, goals, and more
    (28 stat keys per match across 36+ leagues).
    """

    sport = "football"


class BasketballESPNScraper(BaseESPNScraper):
    """ESPN scraper for basketball (NBA/WNBA).

    Team stats: rebounds, assists, steals, blocks, turnovers, FG%, 3P%, FT%.
    Player stats: roster with positions (gamelogs via bball_ref are deeper).
    """

    sport = "basketball"


class HockeyESPNScraper(BaseESPNScraper):
    """ESPN scraper for hockey (NHL).

    Team stats: shots, hits, blocks, takeaways, giveaways, power play,
    faceoffs, penalties. Player stats: roster with positions.
    """

    sport = "hockey"


class TennisESPNScraper(BaseESPNScraper):
    """ESPN scraper for tennis (ATP/WTA).

    Team stats: sets_won, games_won, total_sets, total_games, ranking.
    ESPN is the ONLY structured API for tennis stats in the pipeline.
    """

    sport = "tennis"

    def scrape_team_season_stats(self, competition: str, season: str) -> int:
        """Tennis scraping via scoreboard — athletes not teams.

        Overrides base: instead of standings → fixtures → stats,
        scans scoreboard across date range to collect match stats.
        """
        leagues = self._resolve_leagues(competition)
        total_inserted = 0

        for league_code in leagues:
            try:
                inserted = self._scrape_tennis_stats(
                    competition, season, league_code,
                )
                total_inserted += inserted
            except Exception as e:
                logger.warning("ESPN tennis stats failed for %s: %s", league_code, e)

        return total_inserted

    def _scrape_tennis_stats(
        self, competition: str, season: str, league_code: str,
    ) -> int:
        """Scrape tennis match stats from scoreboard linescores."""
        from datetime import timedelta

        client = self._get_espn_client(league_code)

        with self._get_session() as session:
            sport_id = self._find_or_create_sport(session, self.sport)
            comp_id = self._find_or_create_competition(
                session, sport_id, competition or league_code, "", season,
            )
            accum: dict[str, list[float]] = defaultdict(list)
            matches_found = 0

            with self._track_run(
                session, f"team_stats/tennis/{league_code}/{season}"
            ) as counts:
                today = datetime.now(timezone.utc).date()
                dates = [today - timedelta(days=d) for d in range(0, 30, 2)]

                for scan_date in dates:
                    date_str = scan_date.strftime("%Y-%m-%d")
                    fixtures = client.get_fixtures(date_str)

                    for fix in fixtures:
                        fix_id = fix.external_id if hasattr(fix, "external_id") else ""
                        if not fix_id:
                            continue

                        self._rate_limit()
                        stats_list = client.get_fixture_stats(str(fix_id))
                        if not stats_list:
                            continue

                        ms = stats_list[0]
                        stats = ms.stats if hasattr(ms, "stats") else {}

                        for stat_key, side_vals in stats.items():
                            if isinstance(side_vals, dict):
                                for side in ("home", "away"):
                                    if side in side_vals:
                                        val = _safe_float(side_vals[side])
                                        accum[stat_key].append(val)

                        matches_found += 1

                counts["scraped"] = matches_found

                if accum:
                    inserted = self._upsert_league_profiles(
                        session, comp_id, season, accum,
                    )
                    counts["inserted"] = inserted
                else:
                    inserted = 0

            session.commit()
            logger.info(
                "ESPN tennis: %s — %d matches, %d profiles",
                league_code, matches_found, inserted,
            )
            return inserted


class VolleyballESPNScraper(BaseESPNScraper):
    """ESPN scraper for volleyball (FIVB/NCAA).

    Team stats: kills, aces, blocks, digs, assists, errors, hitting_pct.
    """

    sport = "volleyball"
