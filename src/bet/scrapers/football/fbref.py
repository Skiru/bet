from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from sqlalchemy import text

import soccerdata as sd
from bet.scrapers.base import BaseScraper, ScraperError
from bet.scrapers.constants import FBREF_LEAGUES
from bet.scrapers.models import PlayerSeasonStat


class FootballFBrefScraper(BaseScraper):
    sport = "football"
    source_name = "fbref"
    _request_delay = (3.0, 6.0)

    # Default leagues when no competition specified
    DEFAULT_LEAGUES = list(FBREF_LEAGUES.keys())

    def _resolve_leagues(self, competition: str) -> str | list[str]:
        """Resolve leagues parameter — use defaults if empty."""
        if competition:
            return competition
        return self.DEFAULT_LEAGUES

    def scrape_team_season_stats(self, competition: str, season: str) -> int:
        try:
            self._rate_limit()
            leagues = self._resolve_leagues(competition)
            fbref = sd.FBref(leagues=leagues, seasons=season)
            df = fbref.read_team_season_stats(stat_type="standard")
            
            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                comp_id = self._find_or_create_competition(session, sport_id, competition, "", season)
                
                accum: dict[str, list[float]] = defaultdict(list)

                with self._track_run(session, f"team_stats/{competition}/{season}") as counts:
                    for index, row in df.iterrows():
                        team_name = index[2] if len(index) > 2 else (index[1] if len(index) > 1 else str(index))
                        self._find_or_create_team(session, sport_id, str(team_name))
                        
                        for col_name, value in row.items():
                            if str(col_name).startswith("url"):
                                continue
                            stat_key = "_".join([str(c).replace(" ", "_").lower() for c in col_name])
                            try:
                                fval = float(value)
                            except (ValueError, TypeError):
                                continue
                            accum[stat_key].append(fval)

                    inserted = self._upsert_league_profiles(session, comp_id, season, accum)
                    counts["inserted"] = inserted
                session.commit()
                return inserted
        except Exception as e:
            raise ScraperError(f"FBref team season stats error: {e}") from e

    def scrape_player_season_stats(self, competition: str, season: str) -> int:
        try:
            self._rate_limit()
            leagues = self._resolve_leagues(competition)
            fbref = sd.FBref(leagues=leagues, seasons=season)
            df = fbref.read_player_season_stats(stat_type="standard")
            
            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                comp_id = self._find_or_create_competition(session, sport_id, competition, "", season)
                
                inserted = 0
                updated = 0
                now_str = datetime.now(timezone.utc).isoformat()
                
                for index, row in df.iterrows():
                    # MultiIndex: (league, season, team, player)
                    team_name = index[2] if len(index) > 2 else ""
                    player_name = index[3] if len(index) > 3 else str(index)
                    
                    team_id = self._find_or_create_team(session, sport_id, str(team_name))
                    
                    # Create pseudo external_id from name and team since fbref scraper doesn't give clean ids easily
                    ext_id = f"fbref_{team_name}_{player_name}".replace(" ", "_").lower()
                    
                    pos = str(row.get(("Standard", "Pos"), ""))
                    athlete_id = self._find_or_create_athlete(
                        session, ext_id, sport_id, str(player_name), team_id, pos
                    )
                    
                    # Try to fetch existing
                    stat_record = session.query(PlayerSeasonStat).filter_by(
                        athlete_id=athlete_id,
                        competition_id=comp_id,
                        season=season,
                        source=self.source_name
                    ).first()
                    
                    mp = int(row.get(("Playing Time", "MP"), 0)) if not isinstance(row.get(("Playing Time", "MP")), float) else int(row.get(("Playing Time", "MP"), 0) or 0)
                    starts = int(row.get(("Playing Time", "Starts"), 0)) if not isinstance(row.get(("Playing Time", "Starts")), float) else int(row.get(("Playing Time", "Starts"), 0) or 0)
                    mins = float(row.get(("Playing Time", "Min"), 0.0) or 0.0)
                    
                    stats_dict = {
                        "_".join(str(c).replace(" ", "_").lower() for c in k): v 
                        for k, v in row.items() if not str(k).startswith("url")
                    }
                    stats_json = self._safe_json_dumps(stats_dict)
                    
                    if stat_record:
                        stat_record.games_played = mp
                        stat_record.games_started = starts
                        stat_record.minutes_played = mins
                        stat_record.stats_json = stats_json
                        stat_record.updated_at = now_str
                        updated += 1
                    else:
                        new_record = PlayerSeasonStat(
                            athlete_id=athlete_id,
                            competition_id=comp_id,
                            season=season,
                            games_played=mp,
                            games_started=starts,
                            minutes_played=mins,
                            stats_json=stats_json,
                            source=self.source_name,
                            updated_at=now_str
                        )
                        session.add(new_record)
                        inserted += 1
                
                session.commit()
                return inserted + updated
        except Exception as e:
            raise ScraperError(f"FBref player season stats error: {e}") from e

    def scrape_player_match_stats(self, competition: str, season: str) -> int:
        try:
            self._rate_limit()
            leagues = self._resolve_leagues(competition)
            fbref = sd.FBref(leagues=leagues, seasons=season)
            df = fbref.read_player_match_stats(stat_type="summary")
            
            with self._get_session() as session:
                sport_id = self._find_or_create_sport(session, self.sport)
                
                inserted = 0
                now_str = datetime.now(timezone.utc).isoformat()
                
                for index, row in df.iterrows():
                    team_name = index[2] if len(index) > 2 else ""
                    player_name = index[3] if len(index) > 3 else str(index)
                    match_date_str = str(index[1]) if len(index) > 1 else "" # Simplification
                    
                    team_id = self._find_or_create_team(session, sport_id, str(team_name))
                    ext_id = f"fbref_{team_name}_{player_name}".replace(" ", "_").lower()
                    pos = str(row.get(("Pos"), ""))
                    
                    athlete_id = self._find_or_create_athlete(
                        session, ext_id, sport_id, str(player_name), team_id, pos
                    )
                    
                    stats_dict = {
                        "_".join(str(c).replace(" ", "_").lower() for c in k): v 
                        for k, v in row.items() if not str(k).startswith("url")
                    }
                    
                    session.execute(
                        text("""
                        INSERT OR IGNORE INTO player_gamelogs 
                        (athlete_id, game_date, stats_json, source)
                        VALUES (:aid, :dt, :stat, :src)
                        """),
                        {
                        "aid": athlete_id, "dt": match_date_str, "stat": self._safe_json_dumps(stats_dict),
                            "src": self.source_name
                        }
                    )
                    inserted += 1
                    
                session.commit()
                return inserted
        except Exception as e:
            raise ScraperError(f"FBref player match stats error: {e}") from e

