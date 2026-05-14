from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone

import requests
from sqlalchemy import text

from bet.scrapers.base import BaseScraper, ScraperError
from bet.scrapers.models import PlayerSeasonStat
from bet.scrapers.constants import SACKMANN_ATP_URL, SACKMANN_WTA_URL


class TennisSackmannScraper(BaseScraper):
    sport = "tennis"
    source_name = "sackmann"
    _request_delay = (0.5, 1.0)

    def _csv_url(self, competition: str, season: str) -> str:
        # Season code "2425" → calendar year "2025" (Sackmann uses end-year)
        if len(season) == 4 and season.isdigit():
            year = "20" + season[2:]
        else:
            year = season
        if competition.upper() == "WTA":
            return SACKMANN_WTA_URL.format(year=year)
        return SACKMANN_ATP_URL.format(year=year)

    def _fetch_csv(self, competition: str, season: str) -> list[dict]:
        url = self._csv_url(competition, season)
        self._rate_limit()
        resp = requests.get(url, headers=self._get_headers(), timeout=30)
        if resp.status_code != 200:
            raise ScraperError(f"Sackmann CSV HTTP {resp.status_code} for {url}")
        reader = csv.DictReader(io.StringIO(resp.text))
        return list(reader)

    def scrape_team_season_stats(self, competition: str, season: str) -> int:
        # Tennis has no teams
        return 0

    def scrape_player_season_stats(self, competition: str, season: str) -> int:
        try:
            rows = self._fetch_csv(competition, season)
            if not rows:
                return 0

            # Aggregate per player
            player_agg: dict[str, dict] = defaultdict(lambda: {
                "name": "", "wins": 0, "losses": 0,
                "aces": 0, "double_faults": 0,
                "svpt": 0, "first_in": 0, "first_won": 0,
                "second_won": 0, "bp_saved": 0, "bp_faced": 0,
                "surface_wins": defaultdict(int),
                "surface_losses": defaultdict(int),
            })

            for row in rows:
                surface = row.get("surface", "").lower()
                for prefix, outcome in [("winner", "wins"), ("loser", "losses")]:
                    pid = row.get(f"{prefix}_id", "")
                    pname = row.get(f"{prefix}_name", "")
                    if not pid or not pname:
                        continue
                    p = player_agg[pid]
                    p["name"] = pname
                    p[outcome] += 1
                    p["surface_" + outcome][surface] += 1

                    stat_prefix = "w_" if prefix == "winner" else "l_"
                    for stat, key in [
                        ("ace", "aces"), ("df", "double_faults"),
                        ("svpt", "svpt"), ("1stIn", "first_in"),
                        ("1stWon", "first_won"), ("2ndWon", "second_won"),
                        ("bpSaved", "bp_saved"), ("bpFaced", "bp_faced"),
                    ]:
                        val = row.get(f"{stat_prefix}{stat}", "")
                        if val:
                            try:
                                p[key] += int(val)
                            except ValueError:
                                pass

            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                comp_id = self._find_or_create_competition(
                    session, sport_id, competition.upper(), "", season,
                )
                now_str = datetime.now(timezone.utc).isoformat()
                inserted = 0
                updated = 0

                for pid, p in player_agg.items():
                    ext_id = f"sackmann_{pid}"
                    athlete_id = self._find_or_create_athlete(
                        session, ext_id, sport_id, p["name"],
                    )

                    total_matches = p["wins"] + p["losses"]
                    first_serve_pct = (p["first_in"] / p["svpt"]) if p["svpt"] else 0.0
                    bp_saved_pct = (p["bp_saved"] / p["bp_faced"]) if p["bp_faced"] else 0.0

                    stats = {
                        "matches_won": p["wins"],
                        "matches_lost": p["losses"],
                        "aces": p["aces"],
                        "double_faults": p["double_faults"],
                        "first_serve_pct": round(first_serve_pct, 4),
                        "bp_saved_pct": round(bp_saved_pct, 4),
                        "surface_wins": dict(p["surface_wins"]),
                        "surface_losses": dict(p["surface_losses"]),
                    }

                    existing = session.query(PlayerSeasonStat).filter_by(
                        athlete_id=athlete_id,
                        competition_id=comp_id,
                        season=season,
                        source=self.source_name,
                    ).first()

                    if existing:
                        existing.games_played = total_matches
                        existing.stats_json = json.dumps(stats)
                        existing.updated_at = now_str
                        updated += 1
                    else:
                        rec = PlayerSeasonStat(
                            athlete_id=athlete_id,
                            competition_id=comp_id,
                            season=season,
                            games_played=total_matches,
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
            raise ScraperError(f"Sackmann player season stats error: {e}") from e

    def scrape_player_match_stats(self, competition: str, season: str) -> int:
        try:
            rows = self._fetch_csv(competition, season)
            if not rows:
                return 0

            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                inserted = 0

                for row in rows:
                    tourney = row.get("tourney_name", "")
                    match_date = row.get("tourney_date", "")
                    surface = row.get("surface", "")
                    score = row.get("score", "")

                    for prefix, result in [("winner", "W"), ("loser", "L")]:
                        pid = row.get(f"{prefix}_id", "")
                        pname = row.get(f"{prefix}_name", "")
                        if not pid or not pname:
                            continue
                        ext_id = f"sackmann_{pid}"
                        athlete_id = self._find_or_create_athlete(
                            session, ext_id, sport_id, pname,
                        )

                        stat_prefix = "w_" if prefix == "winner" else "l_"
                        stats: dict[str, object] = {
                            "tourney": tourney, "surface": surface, "score": score,
                        }
                        for stat, key in [
                            ("ace", "aces"), ("df", "double_faults"),
                            ("svpt", "serve_points"), ("1stIn", "first_in"),
                            ("1stWon", "first_won"), ("2ndWon", "second_won"),
                            ("bpSaved", "bp_saved"), ("bpFaced", "bp_faced"),
                        ]:
                            val = row.get(f"{stat_prefix}{stat}", "")
                            if val:
                                try:
                                    stats[key] = int(val)
                                except ValueError:
                                    pass

                        # Use tourney_date + opponent as unique game_date proxy
                        opp_prefix = "loser" if prefix == "winner" else "winner"
                        opp_name = row.get(f"{opp_prefix}_name", "")
                        game_key = f"{match_date}_{opp_name}"

                        session.execute(
                            text("""
                                INSERT OR IGNORE INTO player_gamelogs
                                (athlete_id, game_date, opponent, result, stats_json, source)
                                VALUES (:aid, :dt, :opp, :res, :stat, :src)
                            """),
                            {
                                "aid": athlete_id, "dt": game_key,
                                "opp": opp_name, "res": result,
                                "stat": json.dumps(stats), "src": self.source_name,
                            },
                        )
                        inserted += 1
                session.commit()
                return inserted
        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(f"Sackmann player match stats error: {e}") from e
