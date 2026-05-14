from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from sqlalchemy import text

from bet.scrapers.base import BaseScraper, ScraperError
from bet.scrapers.models import PlayerSeasonStat


class BasketballBRefScraper(BaseScraper):
    sport = "basketball"
    source_name = "basketball-reference"
    _request_delay = (3.0, 5.0)

    _BASE_URL = "https://www.basketball-reference.com"

    @staticmethod
    def _season_year(season: str) -> int:
        """Convert season code to bball-ref year: '2425' → 2025, '2025' → 2025."""
        if len(season) == 4 and not season.startswith("20"):
            return 2000 + int(season[2:])
        return int(season)

    # ------------------------------------------------------------------
    # Team season stats
    # ------------------------------------------------------------------
    def scrape_team_season_stats(self, competition: str, season: str) -> int:
        try:
            year = self._season_year(season)
            url = f"{self._BASE_URL}/leagues/NBA_{year}.html"
            self._rate_limit()
            resp = requests.get(url, headers=self._get_headers(), timeout=15)
            if resp.status_code != 200:
                raise ScraperError(f"bball-ref HTTP {resp.status_code} for {url}")
            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table", id="per_game-team")
            if table is None:
                raise ScraperError("Could not find per_game-team table")

            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                comp_id = self._find_or_create_competition(
                    session, sport_id, competition or "NBA", "USA", season,
                )
                accum: dict[str, list[float]] = defaultdict(list)

                thead = table.find("thead")
                headers = [th.get_text(strip=True) for th in thead.find_all("th")] if thead else []

                tbody = table.find("tbody")
                if tbody is None:
                    return 0

                with self._track_run(session, f"team_stats/{competition}/{season}") as counts:
                    for tr in tbody.find_all("tr"):
                        cells = tr.find_all(["th", "td"])
                        if not cells:
                            continue
                        row_data = {headers[i]: cells[i].get_text(strip=True) for i in range(min(len(headers), len(cells)))}
                        team_name = row_data.get("Team", "").rstrip("*")
                        if not team_name:
                            continue
                        self._find_or_create_team(session, sport_id, team_name, "USA")
                        for key, val in row_data.items():
                            if key in ("Rk", "Team", ""):
                                continue
                            try:
                                fval = float(val)
                            except (ValueError, TypeError):
                                continue
                            sk = re.sub(r"[^a-z0-9_]", "_", key.lower()).strip("_")
                            accum[sk].append(fval)

                    inserted = self._upsert_league_profiles(session, comp_id, season, accum)
                    counts["inserted"] = inserted
                session.commit()
                return inserted
        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(f"bball-ref team stats error: {e}") from e

    # ------------------------------------------------------------------
    # Player season stats
    # ------------------------------------------------------------------
    def scrape_player_season_stats(self, competition: str, season: str) -> int:
        try:
            year = self._season_year(season)
            url = f"{self._BASE_URL}/leagues/NBA_{year}_per_game.html"
            self._rate_limit()
            resp = requests.get(url, headers=self._get_headers(), timeout=15)
            if resp.status_code != 200:
                raise ScraperError(f"bball-ref HTTP {resp.status_code} for {url}")
            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table", id="per_game_stats")
            if table is None:
                raise ScraperError("Could not find per_game_stats table")

            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                comp_id = self._find_or_create_competition(
                    session, sport_id, competition or "NBA", "USA", season,
                )
                now_str = datetime.now(timezone.utc).isoformat()
                inserted = 0
                updated = 0

                thead = table.find("thead")
                headers = [th.get_text(strip=True) for th in thead.find_all("th")] if thead else []

                tbody = table.find("tbody")
                if tbody is None:
                    return 0
                for tr in tbody.find_all("tr"):
                    if tr.get("class") and "thead" in tr["class"]:
                        continue  # skip repeated header rows
                    cells = tr.find_all(["th", "td"])
                    if not cells:
                        continue
                    row_data = {headers[i]: cells[i].get_text(strip=True) for i in range(min(len(headers), len(cells)))}

                    player_name = row_data.get("Player", "").rstrip("*")
                    if not player_name:
                        continue

                    # Extract slug from href
                    player_link = cells[1].find("a") if len(cells) > 1 else None
                    slug = ""
                    if player_link and player_link.get("href"):
                        slug = player_link["href"].split("/")[-1].replace(".html", "")
                    ext_id = f"bref_{slug}" if slug else f"bref_{player_name.replace(' ', '_').lower()}"

                    pos = row_data.get("Pos", "")
                    team_abbr = row_data.get("Tm", "")
                    team_id = None
                    if team_abbr and team_abbr != "TOT":
                        team_id = self._find_or_create_team(session, sport_id, team_abbr, "USA")

                    athlete_id = self._find_or_create_athlete(
                        session, ext_id, sport_id, player_name, team_id, pos,
                    )

                    gp = int(float(row_data.get("G", 0) or 0))
                    gs = int(float(row_data.get("GS", 0) or 0))
                    mpg = float(row_data.get("MP", 0) or 0)
                    mins = mpg * gp

                    stat_map = {
                        "PTS/G": "pts", "TRB": "reb", "AST": "ast",
                        "STL": "stl", "BLK": "blk", "TOV": "tov",
                        "FG%": "fg_pct", "3P%": "three_pct", "FT%": "ft_pct",
                        "FG": "fgm", "FGA": "fga", "3P": "fg3m", "3PA": "fg3a",
                        "FT": "ftm", "FTA": "fta", "ORB": "oreb", "DRB": "dreb",
                        "PF": "pf", "MP": "mpg",
                    }
                    stats: dict[str, float] = {}
                    for html_col, db_key in stat_map.items():
                        v = row_data.get(html_col)
                        if v:
                            try:
                                stats[db_key] = float(v)
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
                        existing.games_started = gs
                        existing.minutes_played = mins
                        existing.stats_json = json.dumps(stats)
                        existing.updated_at = now_str
                        updated += 1
                    else:
                        rec = PlayerSeasonStat(
                            athlete_id=athlete_id,
                            competition_id=comp_id,
                            season=season,
                            games_played=gp,
                            games_started=gs,
                            minutes_played=mins,
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
            raise ScraperError(f"bball-ref player stats error: {e}") from e
