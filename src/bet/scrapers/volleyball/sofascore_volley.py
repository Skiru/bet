from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

import requests
from sqlalchemy import text

from bet.scrapers.base import BaseScraper, ScraperError
from bet.scrapers.models import PlayerSeasonStat


class VolleySofascoreScraper(BaseScraper):
    """SofaScore API scraper for volleyball fixtures and basic stats."""

    sport = "volleyball"
    source_name = "sofascore-volleyball"
    _request_delay = (1.5, 3.0)

    _BASE_URL = "https://api.sofascore.com/api/v1"

    # Tournament IDs for major volleyball leagues
    TOURNAMENT_IDS: dict[str, int] = {
        "plusliga": 2344,
        "serie-a": 2346,
        "superliga-turkey": 2348,
        "bundesliga": 2345,
        "champions-league": 10138,
        "nations-league-men": 12685,
    }

    def _api_get(self, endpoint: str) -> dict:
        url = f"{self._BASE_URL}{endpoint}"
        self._rate_limit()
        headers = self._get_headers()
        headers["Accept"] = "application/json"
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            raise ScraperError(f"SofaScore HTTP {resp.status_code} for {endpoint}")
        return resp.json()

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------
    def scrape_fixtures(self, date: str) -> int:
        try:
            data = self._api_get(f"/sport/volleyball/scheduled-events/{date}")
            events = data.get("events", [])
            if not events:
                return 0

            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                now_str = datetime.now(timezone.utc).isoformat()
                inserted = 0

                for ev in events:
                    tournament = ev.get("tournament", {})
                    comp_name = tournament.get("name", "Volleyball")
                    country = tournament.get("category", {}).get("name", "")
                    comp_id = self._find_or_create_competition(
                        session, sport_id, comp_name, country, "",
                    )
                    home_name = ev.get("homeTeam", {}).get("name", "")
                    away_name = ev.get("awayTeam", {}).get("name", "")
                    if not home_name or not away_name:
                        continue
                    home_id = self._find_or_create_team(session, sport_id, home_name, country)
                    away_id = self._find_or_create_team(session, sport_id, away_name, country)

                    ext_id = str(ev.get("id", ""))
                    start_ts = ev.get("startTimestamp", 0)
                    kickoff = (
                        datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat()
                        if start_ts else ""
                    )

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
            raise ScraperError(f"SofaScore volleyball fixtures error: {e}") from e

    # ------------------------------------------------------------------
    # Team season stats (standings)
    # ------------------------------------------------------------------
    def scrape_team_season_stats(self, competition: str, season: str) -> int:
        tid = self.TOURNAMENT_IDS.get(competition.lower())
        if tid is None:
            return 0
        try:
            data = self._api_get(f"/unique-tournament/{tid}/season/{season}/standings/total")
            standings = data.get("standings", [])
            if not standings:
                return 0

            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                comp_id = self._find_or_create_competition(
                    session, sport_id, competition, "", season,
                )
                accum: dict[str, list[float]] = defaultdict(list)

                with self._track_run(session, f"team_stats/{competition}/{season}") as counts:
                    for group in standings:
                        rows = group.get("rows", [])
                        for row in rows:
                            team_data = row.get("team", {})
                            team_name = team_data.get("name", "")
                            if not team_name:
                                continue
                            self._find_or_create_team(session, sport_id, team_name, "")
                            stat_map = {
                                "matches": "gp", "wins": "wins", "losses": "losses",
                                "points": "points", "setsWon": "sets_won",
                                "setsLost": "sets_lost", "pointsFor": "points_for",
                                "pointsAgainst": "points_against",
                            }
                            for api_key, db_key in stat_map.items():
                                val = row.get(api_key)
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
            raise ScraperError(f"SofaScore volleyball team stats error: {e}") from e

    # ------------------------------------------------------------------
    # Player season stats — SofaScore doesn't expose league-wide player
    # aggregates easily; return 0 (use Volleybox for player data).
    # ------------------------------------------------------------------
    def scrape_player_season_stats(self, competition: str, season: str) -> int:
        return 0
