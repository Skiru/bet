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


class VolleyboxScraper(BaseScraper):
    """Volleybox.net HTML scraper for volleyball team and player stats."""

    sport = "volleyball"
    source_name = "volleybox"
    _request_delay = (3.0, 5.0)

    _BASE_URL = "https://volleybox.net"

    # Map known competition slugs to Volleybox URLs
    LEAGUE_SLUGS: dict[str, str] = {
        "plusliga": "/competition/polish-plusliga-men",
        "serie-a": "/competition/italian-serie-a-men",
        "superliga": "/competition/turkish-superliga-men",
        "bundesliga": "/competition/german-bundesliga-men",
        "ligue-a": "/competition/french-ligue-a-men",
        "champions-league": "/competition/cev-champions-league-men",
    }

    def _get_league_url(self, competition: str, season: str) -> str:
        slug = self.LEAGUE_SLUGS.get(competition.lower(), f"/competition/{competition}")
        return f"{self._BASE_URL}{slug}/{season}"

    # ------------------------------------------------------------------
    # Team season stats
    # ------------------------------------------------------------------
    def scrape_team_season_stats(self, competition: str, season: str) -> int:
        try:
            url = self._get_league_url(competition, season)
            self._rate_limit()
            resp = requests.get(url, headers=self._get_headers(), timeout=15)
            if resp.status_code != 200:
                raise ScraperError(f"Volleybox HTTP {resp.status_code} for {url}")
            soup = BeautifulSoup(resp.text, "html.parser")

            standings_table = soup.find("table", class_=re.compile(r"standing|ranking"))
            if standings_table is None:
                standings_table = soup.find("table")
            if standings_table is None:
                return 0

            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                comp_id = self._find_or_create_competition(
                    session, sport_id, competition, "", season,
                )
                accum: dict[str, list[float]] = defaultdict(list)

                thead = standings_table.find("thead")
                headers: list[str] = []
                if thead:
                    for th in thead.find_all("th"):
                        headers.append(th.get_text(strip=True))

                tbody = standings_table.find("tbody")
                rows = tbody.find_all("tr") if tbody else standings_table.find_all("tr")[1:]

                with self._track_run(session, f"team_stats/{competition}/{season}") as counts:
                    for tr in rows:
                        cells = tr.find_all(["th", "td"])
                        if len(cells) < 3:
                            continue
                        row_data: dict[str, str] = {}
                        for i, cell in enumerate(cells):
                            key = headers[i] if i < len(headers) else f"col_{i}"
                            row_data[key] = cell.get_text(strip=True)

                        team_name = row_data.get("Team", "")
                        if not team_name:
                            for k, v in row_data.items():
                                if k.lower() in ("team", "club", "name"):
                                    team_name = v
                                    break
                        if not team_name and len(cells) >= 2:
                            team_name = cells[1].get_text(strip=True)
                        if not team_name:
                            continue
                        self._find_or_create_team(session, sport_id, team_name, "")

                        for key, val in row_data.items():
                            if not key or key.lower() in ("rk", "#", "team", "club", "name"):
                                continue
                            try:
                                fval = float(val.replace(",", "."))
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
            raise ScraperError(f"Volleybox team stats error: {e}") from e

    # ------------------------------------------------------------------
    # Player season stats
    # ------------------------------------------------------------------
    def scrape_player_season_stats(self, competition: str, season: str) -> int:
        try:
            url = self._get_league_url(competition, season) + "/players"
            self._rate_limit()
            resp = requests.get(url, headers=self._get_headers(), timeout=15)
            if resp.status_code != 200:
                raise ScraperError(f"Volleybox HTTP {resp.status_code} for {url}")
            soup = BeautifulSoup(resp.text, "html.parser")

            table = soup.find("table", class_=re.compile(r"player|stat"))
            if table is None:
                table = soup.find("table")
            if table is None:
                return 0

            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                comp_id = self._find_or_create_competition(
                    session, sport_id, competition, "", season,
                )
                now_str = datetime.now(timezone.utc).isoformat()
                inserted = 0
                updated = 0

                thead = table.find("thead")
                headers: list[str] = []
                if thead:
                    last_row = thead.find_all("tr")[-1]
                    for th in last_row.find_all("th"):
                        headers.append(th.get_text(strip=True))

                tbody = table.find("tbody")
                rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]
                for tr in rows:
                    cells = tr.find_all(["th", "td"])
                    if len(cells) < 3:
                        continue
                    row_data: dict[str, str] = {}
                    for i, cell in enumerate(cells):
                        key = headers[i] if i < len(headers) else f"col_{i}"
                        row_data[key] = cell.get_text(strip=True)

                    player_name = row_data.get("Player", "")
                    if not player_name:
                        for k, v in row_data.items():
                            if k.lower() in ("player", "name"):
                                player_name = v
                                break
                    if not player_name:
                        continue

                    player_link = None
                    for cell in cells:
                        a = cell.find("a")
                        if a and a.get("href"):
                            player_link = a["href"]
                            break
                    slug_id = player_link.split("/")[-1] if player_link else player_name.replace(" ", "_").lower()
                    ext_id = f"vbox_{slug_id}"

                    pos = row_data.get("Pos", row_data.get("Position", ""))
                    team_name = row_data.get("Team", row_data.get("Club", ""))
                    team_id = None
                    if team_name:
                        team_id = self._find_or_create_team(session, sport_id, team_name, "")
                    athlete_id = self._find_or_create_athlete(
                        session, ext_id, sport_id, player_name, team_id, pos,
                    )

                    gp = 0
                    for gp_key in ("GP", "M", "Matches", "Games"):
                        if gp_key in row_data:
                            try:
                                gp = int(float(row_data[gp_key]))
                            except (ValueError, TypeError):
                                pass
                            break

                    stat_map = {
                        "Pts": "points", "Srv": "serve_points", "Att": "attack_points",
                        "Blk": "block_points", "Aces": "aces", "Ace": "aces",
                        "Err": "errors", "Att%": "attack_pct",
                        "Rec%": "reception_pct", "Set": "sets_played",
                    }
                    stats: dict[str, float] = {}
                    for html_col, db_key in stat_map.items():
                        v = row_data.get(html_col)
                        if v:
                            try:
                                stats[db_key] = float(v.replace(",", ".").rstrip("%"))
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
            raise ScraperError(f"Volleybox player stats error: {e}") from e
