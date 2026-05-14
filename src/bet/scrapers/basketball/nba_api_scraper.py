from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import text

from bet.scrapers.base import BaseScraper, ScraperError
from bet.scrapers.models import PlayerSeasonStat
from bet.scrapers.constants import NBA_SEASONS

try:
    from nba_api.stats.endpoints import (
        leaguedashplayerstats,
        leaguedashteamstats,
        playergamelog,
    )
except ImportError:
    leaguedashplayerstats = None  # type: ignore[assignment]
    leaguedashteamstats = None  # type: ignore[assignment]
    playergamelog = None  # type: ignore[assignment]


def _nba_season(season: str) -> str:
    """Convert internal season code to NBA API format: '2425' → '2024-25'."""
    if season in NBA_SEASONS:
        return NBA_SEASONS[season]
    if "-" in season and len(season) == 7:
        return season
    # Guess: "2025" → "2024-25"
    try:
        y = int(season)
        return f"{y - 1}-{str(y)[2:]}"
    except ValueError:
        return season


class BasketballNBAScraper(BaseScraper):
    sport = "basketball"
    source_name = "nba-api"
    _request_delay = (0.6, 1.5)

    def scrape_team_season_stats(self, competition: str, season: str) -> int:
        try:
            if leaguedashteamstats is None:
                raise ScraperError("nba_api not installed")
            self._rate_limit()
            nba_season = _nba_season(season)
            resp = leaguedashteamstats.LeagueDashTeamStats(season=nba_season)
            df = resp.get_data_frames()[0]

            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                comp_id = self._find_or_create_competition(
                    session, sport_id, competition or "NBA", "USA", season,
                )
                stat_cols = [
                    "W", "L", "W_PCT", "FGM", "FGA", "FG_PCT", "FG3M", "FG3A",
                    "FG3_PCT", "FTM", "FTA", "FT_PCT", "OREB", "DREB", "REB",
                    "AST", "TOV", "STL", "BLK", "PF", "PTS",
                ]
                accum: dict[str, list[float]] = defaultdict(list)

                with self._track_run(session, f"team_stats/{competition}/{season}") as counts:
                    for _, row in df.iterrows():
                        team_name = str(row.get("TEAM_NAME", ""))
                        if not team_name:
                            continue
                        self._find_or_create_team(session, sport_id, team_name, "USA")
                        for col in stat_cols:
                            val = row.get(col)
                            if val is None:
                                continue
                            try:
                                accum[col.lower()].append(float(val))
                            except (ValueError, TypeError):
                                continue

                    inserted = self._upsert_league_profiles(session, comp_id, season, accum)
                    counts["inserted"] = inserted
                session.commit()
                return inserted
        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(f"NBA team season stats error: {e}") from e

    def scrape_player_season_stats(self, competition: str, season: str) -> int:
        try:
            if leaguedashplayerstats is None:
                raise ScraperError("nba_api not installed")
            self._rate_limit()
            nba_season = _nba_season(season)
            resp = leaguedashplayerstats.LeagueDashPlayerStats(season=nba_season)
            df = resp.get_data_frames()[0]

            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                comp_id = self._find_or_create_competition(
                    session, sport_id, competition or "NBA", "USA", season,
                )
                now_str = datetime.now(timezone.utc).isoformat()
                inserted = 0
                updated = 0

                for _, row in df.iterrows():
                    player_id = str(row.get("PLAYER_ID", ""))
                    player_name = str(row.get("PLAYER_NAME", ""))
                    if not player_id or not player_name:
                        continue

                    team_abbr = str(row.get("TEAM_ABBREVIATION", ""))
                    team_id = None
                    if team_abbr:
                        team_id = self._find_or_create_team(session, sport_id, team_abbr, "USA")

                    ext_id = f"nba_{player_id}"
                    athlete_id = self._find_or_create_athlete(
                        session, ext_id, sport_id, player_name, team_id,
                    )

                    gp = int(row.get("GP", 0) or 0)
                    gs = int(row.get("GS", 0) or 0)
                    mins = float(row.get("MIN", 0.0) or 0.0)

                    stat_keys = [
                        "PTS", "REB", "AST", "STL", "BLK", "TOV",
                        "FGM", "FGA", "FG_PCT", "FG3M", "FG3A", "FG3_PCT",
                        "FTM", "FTA", "FT_PCT", "OREB", "DREB", "PF",
                    ]
                    stats = {}
                    for k in stat_keys:
                        v = row.get(k)
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
            raise ScraperError(f"NBA player season stats error: {e}") from e

    def scrape_player_match_stats(self, competition: str, season: str) -> int:
        try:
            if playergamelog is None or leaguedashplayerstats is None:
                raise ScraperError("nba_api not installed")
            self._rate_limit()
            nba_season = _nba_season(season)
            # Get top players by minutes
            resp = leaguedashplayerstats.LeagueDashPlayerStats(season=nba_season)
            players_df = resp.get_data_frames()[0]
            players_df = players_df.sort_values("MIN", ascending=False).head(50)

            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                now_str = datetime.now(timezone.utc).isoformat()
                inserted = 0

                for _, prow in players_df.iterrows():
                    pid = str(prow.get("PLAYER_ID", ""))
                    pname = str(prow.get("PLAYER_NAME", ""))
                    if not pid:
                        continue

                    ext_id = f"nba_{pid}"
                    athlete_id = self._find_or_create_athlete(
                        session, ext_id, sport_id, pname,
                    )

                    self._rate_limit()
                    try:
                        gl = playergamelog.PlayerGameLog(
                            player_id=int(pid), season=nba_season,
                        )
                        gl_df = gl.get_data_frames()[0]
                    except Exception:
                        continue

                    for _, grow in gl_df.iterrows():
                        game_date = str(grow.get("GAME_DATE", ""))
                        matchup = str(grow.get("MATCHUP", ""))
                        wl = str(grow.get("WL", ""))
                        stat_keys = [
                            "MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV",
                            "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA",
                            "OREB", "DREB", "PF", "PLUS_MINUS",
                        ]
                        stats = {}
                        for k in stat_keys:
                            v = grow.get(k)
                            if v is not None:
                                try:
                                    stats[k.lower()] = float(v)
                                except (ValueError, TypeError):
                                    pass

                        session.execute(
                            text("""
                                INSERT OR IGNORE INTO player_gamelogs
                                (athlete_id, game_date, opponent, result, stats_json, source)
                                VALUES (:aid, :dt, :opp, :res, :stat, :src)
                            """),
                            {
                                "aid": athlete_id, "dt": game_date,
                                "opp": matchup, "res": wl,
                                "stat": json.dumps(stats), "src": self.source_name,
                            },
                        )
                        inserted += 1
                session.commit()
                return inserted
        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(f"NBA player match stats error: {e}") from e
