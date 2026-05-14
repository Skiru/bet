from __future__ import annotations

import json
from datetime import datetime, timezone

import requests
from sqlalchemy import text

from bet.scrapers.base import BaseScraper, ScraperError


class TennisSofascoreScraper(BaseScraper):
    sport = "tennis"
    source_name = "sofascore-tennis"
    _request_delay = (2.0, 4.0)

    _BASE_URL = "https://api.sofascore.com/api/v1"

    def _api_get(self, endpoint: str) -> dict:
        url = f"{self._BASE_URL}{endpoint}"
        self._rate_limit()
        headers = self._get_headers()
        headers["Accept"] = "application/json"
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 403:
            raise ScraperError(f"SofaScore 403 Forbidden for {endpoint}")
        if resp.status_code == 429:
            raise ScraperError(f"SofaScore 429 Rate Limited for {endpoint}")
        if resp.status_code != 200:
            raise ScraperError(f"SofaScore HTTP {resp.status_code} for {endpoint}")
        return resp.json()

    def scrape_team_season_stats(self, competition: str, season: str) -> int:
        # Tennis has no teams
        return 0

    def scrape_player_season_stats(self, competition: str, season: str) -> int:
        # SofaScore tennis doesn't expose season aggregates easily
        return 0

    def scrape_player_match_stats(self, competition: str, season: str) -> int:
        # Would require iterating finished events — heavy. Keep as future enhancement.
        return 0

    def scrape_fixtures(self, date: str) -> int:
        """Fetch scheduled tennis events for a given date."""
        try:
            data = self._api_get(f"/sport/tennis/scheduled-events/{date}")
            events = data.get("events", [])
            if not events:
                return 0

            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                now_str = datetime.now(timezone.utc).isoformat()
                inserted = 0

                for ev in events:
                    tournament = ev.get("tournament", {})
                    tourn_name = tournament.get("name", "Unknown")
                    tourn_country = tournament.get("category", {}).get("name", "")
                    comp_id = self._find_or_create_competition(
                        session, sport_id, tourn_name, tourn_country, "",
                    )

                    home = ev.get("homeTeam", {})
                    away = ev.get("awayTeam", {})
                    home_name = home.get("name", "")
                    away_name = away.get("name", "")
                    if not home_name or not away_name:
                        continue

                    home_id = self._find_or_create_team(session, sport_id, home_name)
                    away_id = self._find_or_create_team(session, sport_id, away_name)

                    start_ts = ev.get("startTimestamp", 0)
                    kickoff = datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat() if start_ts else ""
                    ext_id = str(ev.get("id", ""))
                    status_code = ev.get("status", {}).get("type", "notstarted")
                    status = "scheduled" if status_code == "notstarted" else status_code

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
                            "st": status, "src": self.source_name, "fa": now_str,
                        },
                    )
                    inserted += 1
                session.commit()
                return inserted
        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(f"SofaScore tennis fixtures error: {e}") from e
