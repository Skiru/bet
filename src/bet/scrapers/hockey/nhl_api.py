from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

import requests
from sqlalchemy import text

from bet.scrapers.base import BaseScraper, ScraperError
from bet.scrapers.models import PlayerSeasonStat


class HockeyNHLScraper(BaseScraper):
    """NHL public API scraper (api-web.nhle.com — no key required)."""

    sport = "hockey"
    source_name = "nhl-api"
    _request_delay = (1.0, 2.0)

    _BASE_URL = "https://api-web.nhle.com/v1"

    def _api_get(self, endpoint: str) -> dict:
        url = f"{self._BASE_URL}{endpoint}"
        self._rate_limit()
        resp = requests.get(url, headers=self._get_headers(), timeout=15)
        if resp.status_code != 200:
            raise ScraperError(f"NHL API HTTP {resp.status_code} for {endpoint}")
        return resp.json()

    @staticmethod
    def _nhl_season(season: str) -> str:
        """Convert '2425' → '20242025', '2025' → '20242025'."""
        if len(season) == 8:
            return season
        if len(season) == 4 and not season.startswith("20"):
            return f"20{season[:2]}20{season[2:]}"
        try:
            y = int(season)
            return f"{y - 1}{y}"
        except ValueError:
            return season

    # ------------------------------------------------------------------
    # Team season stats
    # ------------------------------------------------------------------
    def scrape_team_season_stats(self, competition: str, season: str) -> int:
        try:
            nhl_season = self._nhl_season(season)
            data = self._api_get(f"/standings/{nhl_season}")
            standings = data.get("standings", [])
            if not standings:
                return 0

            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                comp_id = self._find_or_create_competition(
                    session, sport_id, competition or "NHL", "USA/Canada", season,
                )

                stat_map = {
                    "wins": "wins", "losses": "losses", "otLosses": "ot_losses",
                    "points": "points", "gamesPlayed": "gp",
                    "goalFor": "goals_for", "goalAgainst": "goals_against",
                    "goalDifferential": "goal_diff",
                    "regulationWins": "reg_wins",
                    "homeWins": "home_wins", "homeLosses": "home_losses",
                    "roadWins": "road_wins", "roadLosses": "road_losses",
                    "shootoutWins": "so_wins", "shootoutLosses": "so_losses",
                }
                accum: dict[str, list[float]] = defaultdict(list)

                with self._track_run(session, f"team_stats/{competition}/{season}") as counts:
                    for team_data in standings:
                        team_name = team_data.get("teamName", {})
                        name = team_name.get("default", "")
                        if not name:
                            name = team_data.get("teamAbbrev", {}).get("default", "")
                        if not name:
                            continue
                        self._find_or_create_team(session, sport_id, name, "USA/Canada")

                        for api_key, db_key in stat_map.items():
                            val = team_data.get(api_key)
                            if val is None:
                                continue
                            try:
                                accum[db_key].append(float(val))
                            except (ValueError, TypeError):
                                continue

                    inserted = self._upsert_league_profiles(session, comp_id, season, accum)
                    counts["inserted"] = inserted
                session.commit()
                return inserted
        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(f"NHL team stats error: {e}") from e

    # ------------------------------------------------------------------
    # Player season stats
    # ------------------------------------------------------------------
    def scrape_player_season_stats(self, competition: str, season: str) -> int:
        try:
            nhl_season = self._nhl_season(season)
            # Skater stats — paginated
            all_skaters: list[dict] = []
            start = 0
            limit = 100
            while True:
                data = self._api_get(
                    f"/skater-stats-leaders/{nhl_season}/2"
                    f"?categories=points&limit={limit}&start={start}"
                )
                skaters = data.get("data", data.get("leaders", []))
                if not skaters:
                    # Fallback: try club-stats endpoint
                    break
                all_skaters.extend(skaters)
                if len(skaters) < limit:
                    break
                start += limit
                self._rate_limit()

            # If leaders endpoint didn't work, try club-stats-leaders
            if not all_skaters:
                data = self._api_get(f"/skater-stats-leaders/{nhl_season}/2?categories=goals,assists,points&limit=200")
                for cat_data in data.values():
                    if isinstance(cat_data, list):
                        all_skaters.extend(cat_data)

            if not all_skaters:
                return 0

            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                comp_id = self._find_or_create_competition(
                    session, sport_id, competition or "NHL", "USA/Canada", season,
                )
                now_str = datetime.now(timezone.utc).isoformat()
                inserted = 0
                updated = 0
                seen: set[str] = set()

                for sk in all_skaters:
                    pid = str(sk.get("playerId", sk.get("id", "")))
                    if not pid or pid in seen:
                        continue
                    seen.add(pid)
                    first = sk.get("firstName", {}).get("default", "")
                    last = sk.get("lastName", {}).get("default", "")
                    pname = f"{first} {last}".strip() or str(pid)
                    pos = sk.get("positionCode", "")
                    team_abbr = sk.get("teamAbbrev", {}).get("default", "")

                    ext_id = f"nhl_{pid}"
                    team_id = None
                    if team_abbr:
                        team_id = self._find_or_create_team(session, sport_id, team_abbr, "USA/Canada")
                    athlete_id = self._find_or_create_athlete(
                        session, ext_id, sport_id, pname, team_id, pos,
                    )

                    gp = int(sk.get("gamesPlayed", 0) or 0)
                    stats = {}
                    stat_keys = [
                        "goals", "assists", "points", "plusMinus", "penaltyMinutes",
                        "powerPlayGoals", "shorthandedGoals", "gameWinningGoals",
                        "shots", "shootingPctg", "avgTimeOnIce",
                    ]
                    for k in stat_keys:
                        v = sk.get(k)
                        if v is not None:
                            try:
                                stats[k.lower()] = float(v)
                            except (ValueError, TypeError):
                                pass

                    existing = session.query(PlayerSeasonStat).filter_by(
                        athlete_id=athlete_id,
                        competition_id=comp_id,
                        season=season,
                        source=self.source_name,
                    ).first()

                    if existing:
                        existing.games_played = gp
                        existing.stats_json = json.dumps(stats)
                        existing.updated_at = now_str
                        updated += 1
                    else:
                        rec = PlayerSeasonStat(
                            athlete_id=athlete_id,
                            competition_id=comp_id,
                            season=season,
                            games_played=gp,
                            stats_json=json.dumps(stats),
                            source=self.source_name,
                            updated_at=now_str,
                        )
                        session.add(rec)
                        inserted += 1
                session.commit()
                return inserted + updated
        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(f"NHL player stats error: {e}") from e

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------
    def scrape_fixtures(self, date: str) -> int:
        try:
            data = self._api_get(f"/schedule/{date}")
            game_week = data.get("gameWeek", [])
            if not game_week:
                return 0

            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                comp_id = self._find_or_create_competition(
                    session, sport_id, "NHL", "USA/Canada", "",
                )
                now_str = datetime.now(timezone.utc).isoformat()
                inserted = 0

                for day_data in game_week:
                    if day_data.get("date") != date:
                        continue
                    for game in day_data.get("games", []):
                        home_abbr = game.get("homeTeam", {}).get("abbrev", "")
                        away_abbr = game.get("awayTeam", {}).get("abbrev", "")
                        if not home_abbr or not away_abbr:
                            continue
                        home_id = self._find_or_create_team(session, sport_id, home_abbr, "USA/Canada")
                        away_id = self._find_or_create_team(session, sport_id, away_abbr, "USA/Canada")
                        ext_id = str(game.get("id", ""))
                        kickoff = game.get("startTimeUTC", "")

                        session.execute(
                            text("""
                                INSERT OR IGNORE INTO fixtures
                                (external_id, sport_id, competition_id, home_team_id, away_team_id,
                                 kickoff, status, source, fetched_at)
                                VALUES (:eid, :sid, :cid, :hid, :aid, :ko, :st, :src, :fa)
                            """),
                            {
                                "eid": ext_id, "sid": sport_id, "cid": comp_id,
                                "hid": home_id, "aid": away_id, "ko": kickoff,
                                "st": "scheduled", "src": self.source_name, "fa": now_str,
                            },
                        )
                        inserted += 1
                session.commit()
                return inserted
        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(f"NHL fixtures error: {e}") from e
