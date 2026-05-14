from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone

from bs4 import Comment

import requests
from bs4 import BeautifulSoup
from sqlalchemy import text

from bet.scrapers.base import BaseScraper, ScraperError
from bet.scrapers.models import PlayerSeasonStat


class HockeyRefScraper(BaseScraper):
    """Hockey-Reference HTML scraper."""

    sport = "hockey"
    source_name = "hockey-reference"
    _request_delay = (3.0, 5.0)

    _BASE_URL = "https://www.hockey-reference.com"

    @staticmethod
    def _find_table(soup: BeautifulSoup, table_id: str) -> BeautifulSoup | None:
        """Find a table by id, searching inside HTML comments if necessary.

        Sports-reference sites hide tables in ``<!-- ... -->`` comment
        blocks to deter scraping.  The browser renders them via JS.
        """
        table = soup.find("table", id=table_id)
        if table is not None:
            return table
        for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
            if f'id="{table_id}"' in comment:
                inner = BeautifulSoup(comment, "html.parser")
                table = inner.find("table", id=table_id)
                if table is not None:
                    return table
        return None

    @staticmethod
    def _season_slug(season: str) -> str:
        """Convert season to hockey-ref slug: '2425' → '2025', '2025' → '2025'."""
        if len(season) == 4 and not season.startswith("20"):
            return f"20{season[2:]}"
        return season

    # ------------------------------------------------------------------
    # Team season stats
    # ------------------------------------------------------------------
    def scrape_team_season_stats(self, competition: str, season: str) -> int:
        try:
            slug = self._season_slug(season)
            url = f"{self._BASE_URL}/leagues/NHL_{slug}.html"
            self._rate_limit()
            resp = requests.get(url, headers=self._get_headers(), timeout=15)
            if resp.status_code != 200:
                raise ScraperError(f"hockey-ref HTTP {resp.status_code} for {url}")
            soup = BeautifulSoup(resp.text, "html.parser")
            table = self._find_table(soup, "stats")
            if table is None:
                return 0

            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                comp_id = self._find_or_create_competition(
                    session, sport_id, competition or "NHL", "USA/Canada", season,
                )
                accum: dict[str, list[float]] = defaultdict(list)

                thead = table.find("thead")
                headers = []
                if thead:
                    last_row = thead.find_all("tr")[-1]
                    headers = [th.get_text(strip=True) for th in last_row.find_all("th")]

                tbody = table.find("tbody")
                if tbody is None:
                    return 0

                with self._track_run(session, f"team_stats/{competition}/{season}") as counts:
                    for tr in tbody.find_all("tr"):
                        if tr.get("class") and "thead" in tr["class"]:
                            continue
                        cells = tr.find_all(["th", "td"])
                        if not cells:
                            continue
                        row_data = {
                            headers[i]: cells[i].get_text(strip=True)
                            for i in range(min(len(headers), len(cells)))
                        }
                        team_name = row_data.get("", row_data.get("Team", "")).rstrip("*")
                        if not team_name:
                            continue
                        self._find_or_create_team(session, sport_id, team_name, "USA/Canada")
                        for key, val in row_data.items():
                            if not key or key in ("Rk", "Team", ""):
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
            raise ScraperError(f"hockey-ref team stats error: {e}") from e

    # ------------------------------------------------------------------
    # Player season stats
    # ------------------------------------------------------------------
    def scrape_player_season_stats(self, competition: str, season: str) -> int:
        try:
            slug = self._season_slug(season)
            url = f"{self._BASE_URL}/leagues/NHL_{slug}_skaters.html"
            self._rate_limit()
            resp = requests.get(url, headers=self._get_headers(), timeout=15)
            if resp.status_code != 200:
                raise ScraperError(f"hockey-ref HTTP {resp.status_code} for {url}")
            soup = BeautifulSoup(resp.text, "html.parser")
            table = self._find_table(soup, "player_stats")
            if table is None:
                return 0

            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                comp_id = self._find_or_create_competition(
                    session, sport_id, competition or "NHL", "USA/Canada", season,
                )
                now_str = datetime.now(timezone.utc).isoformat()
                inserted = 0
                updated = 0

                thead = table.find("thead")
                headers = []
                if thead:
                    last_row = thead.find_all("tr")[-1]
                    headers = [th.get_text(strip=True) for th in last_row.find_all("th")]

                tbody = table.find("tbody")
                if tbody is None:
                    return 0
                for tr in tbody.find_all("tr"):
                    if tr.get("class") and "thead" in tr["class"]:
                        continue
                    cells = tr.find_all(["th", "td"])
                    if not cells:
                        continue
                    row_data = {
                        headers[i]: cells[i].get_text(strip=True)
                        for i in range(min(len(headers), len(cells)))
                    }
                    player_name = row_data.get("Player", "").rstrip("*")
                    if not player_name:
                        continue

                    player_link = cells[1].find("a") if len(cells) > 1 else None
                    slug_id = ""
                    if player_link and player_link.get("href"):
                        slug_id = player_link["href"].split("/")[-1].replace(".html", "")
                    ext_id = f"href_{slug_id}" if slug_id else f"href_{player_name.replace(' ', '_').lower()}"

                    pos = row_data.get("Pos", "")
                    team_abbr = row_data.get("Tm", "")
                    team_id = None
                    if team_abbr and team_abbr != "TOT":
                        team_id = self._find_or_create_team(session, sport_id, team_abbr, "USA/Canada")
                    athlete_id = self._find_or_create_athlete(
                        session, ext_id, sport_id, player_name, team_id, pos,
                    )

                    gp = int(float(row_data.get("GP", 0) or 0))
                    stat_map = {
                        "G": "goals", "A": "assists", "PTS": "points",
                        "+/-": "plus_minus", "PIM": "pim", "S": "shots",
                        "S%": "shooting_pct", "TOI": "toi",
                        "PPG": "pp_goals", "SHG": "sh_goals",
                        "GWG": "gw_goals", "OPS": "ops", "DPS": "dps",
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
            raise ScraperError(f"hockey-ref player stats error: {e}") from e
