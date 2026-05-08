#!/usr/bin/env python3
"""Seed SQLite database with all available ESPN data.

Pulls: standings, rosters, player gamelogs/splits, ATS/OU records,
odds, win probabilities, predictor, power index.

Usage:
    python3 scripts/seed_espn_data.py
    python3 scripts/seed_espn_data.py --sports basketball,hockey --verbose
    python3 scripts/seed_espn_data.py --skip-players --skip-rosters
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Project root
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from bet.db.connection import get_db
from bet.db.models import (
    Athlete,
    ESPNPrediction,
    OddsRecord,
    PlayerGamelog,
    PlayerSplit,
    PowerIndex,
    Standing,
    TeamATSRecord,
    TeamOURecord,
    TeamRoster,
    Transaction,
)
from bet.db.repositories import (
    AthleteRepo,
    CompetitionRepo,
    ESPNPredictionRepo,
    FixtureRepo,
    OddsRepo,
    PlayerGamelogRepo,
    PlayerSplitRepo,
    PowerIndexRepo,
    SportRepo,
    StandingRepo,
    TeamATSRepo,
    TeamOURepo,
    TeamRosterRepo,
    TeamRepo,
    TransactionRepo,
)
from bet.db.schema import init_db

# Import ESPN clients
from bet.api_clients.espn import ESPNClient, ESPN_LEAGUES, ESPN_SPORT_MAP
from bet.api_clients.espn_odds import ESPNOddsClient, ESPN_SPORT_SLUGS
from bet.api_clients.espn_stats import ESPNStatsClient
from bet.api_clients.rate_limiter import RateLimiter


# Sports that have ATS/OU data on ESPN
ATS_OU_SPORTS = {"basketball", "hockey", "baseball"}

# Sports that have player gamelogs on ESPN
GAMELOG_SPORTS = {"basketball", "hockey", "baseball"}

# Default delay between ESPN API requests (seconds)
REQUEST_DELAY = 0.3


class ESPNSeeder:
    """Orchestrates full ESPN data seeding into SQLite DB."""

    # Maximum total execution time in seconds (8 minutes)
    MAX_RUNTIME = 480

    def __init__(self, db_path: str, verbose: bool = False):
        self.db_path = db_path
        self.verbose = verbose
        self.odds_client = ESPNOddsClient()
        self.stats_client = ESPNStatsClient()
        # Map (sport_id, espn_team_id) → internal team_id for lookups
        self._team_espn_map: dict[tuple[int, str], int] = {}
        self._start_time: float = 0.0
        self.counts = {
            "standings": 0,
            "athletes": 0,
            "rosters": 0,
            "gamelogs": 0,
            "splits": 0,
            "ats_records": 0,
            "ou_records": 0,
            "odds": 0,
            "predictions": 0,
            "transactions": 0,
            "power_index": 0,
            "errors": 0,
        }

    def log(self, msg: str) -> None:
        if self.verbose:
            print(f"  [ESPN] {msg}")

    def _check_timeout(self) -> bool:
        """Return True if total runtime exceeded MAX_RUNTIME."""
        if self._start_time and (time.time() - self._start_time) > self.MAX_RUNTIME:
            elapsed = int(time.time() - self._start_time)
            print(f"  ⏱ ESPN seeder timeout after {elapsed}s (max {self.MAX_RUNTIME}s) — saving progress")
            return True
        return False

    def _delay(self):
        time.sleep(REQUEST_DELAY)

    def run(
        self,
        sports: list[str],
        leagues: dict[str, list[str]] | None = None,
        date: str = "",
        skip_rosters: bool = False,
        skip_odds: bool = False,
        skip_players: bool = False,
    ) -> dict:
        """Run full seeding pipeline."""
        if not date:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        self._start_time = time.time()
        target_leagues = leagues or {s: ESPN_LEAGUES.get(s, []) for s in sports}

        print(f"ESPN Seeder — target date: {date}")
        print(f"Sports: {', '.join(sports)}")
        print(f"Total leagues: {sum(len(v) for v in target_leagues.values())}")
        print()

        with get_db(self.db_path) as conn:
            # Ensure schema is up to date
            init_db(conn)

            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            comp_repo = CompetitionRepo(conn)
            fixture_repo = FixtureRepo(conn)
            athlete_repo = AthleteRepo(conn)
            gamelog_repo = PlayerGamelogRepo(conn)
            split_repo = PlayerSplitRepo(conn)
            standing_repo = StandingRepo(conn)
            ats_repo = TeamATSRepo(conn)
            ou_repo = TeamOURepo(conn)
            prediction_repo = ESPNPredictionRepo(conn)
            roster_repo = TeamRosterRepo(conn)
            transaction_repo = TransactionRepo(conn)
            power_repo = PowerIndexRepo(conn)
            odds_repo = OddsRepo(conn)

            # Seed default sports if needed
            sport_repo.seed_defaults()
            conn.commit()

            for sport in sports:
                if self._check_timeout():
                    print(f"  ⏱ Stopping — timeout reached after processing earlier sports")
                    break

                sport_leagues = target_leagues.get(sport, [])
                if not sport_leagues:
                    continue

                print(f"{'='*60}")
                print(f"SPORT: {sport} ({len(sport_leagues)} leagues)")
                print(f"{'='*60}")

                # Get sport DB ID
                sport_obj = sport_repo.get_by_name(sport)
                if not sport_obj:
                    continue
                sport_id = sport_obj.id

                for league in sport_leagues:
                    if self._check_timeout():
                        print(f"  ⏱ Stopping mid-sport — timeout reached")
                        conn.commit()
                        break

                    print(f"\n  League: {sport}/{league}")

                    # Phase 2: Standings (also discovers teams)
                    self._seed_standings(
                        conn, sport, league, sport_id, team_repo, standing_repo
                    )

                    # Phase 3: Rosters
                    if not skip_rosters:
                        self._seed_rosters(
                            conn, sport, league, sport_id, athlete_repo, roster_repo, transaction_repo
                        )

                    # Phase 4: ATS/OU Records
                    if sport in ATS_OU_SPORTS:
                        self._seed_ats_ou(
                            conn, sport, league, sport_id, ats_repo, ou_repo
                        )

                    # Phase 5: Odds + Predictions
                    if not skip_odds:
                        self._seed_odds_and_predictions(
                            conn, sport, league, date, odds_repo, prediction_repo
                        )

                    # Phase 6: Player Stats
                    if not skip_players and sport in GAMELOG_SPORTS:
                        self._seed_player_stats(
                            conn, sport, league, sport_id, gamelog_repo, split_repo
                        )

                    # Phase 7: Power Index
                    self._seed_power_index(
                        conn, sport, league, sport_id, power_repo
                    )

                    conn.commit()

        print(f"\n{'='*60}")
        print("SEEDING COMPLETE")
        print(f"{'='*60}")
        for key, count in self.counts.items():
            if count > 0:
                print(f"  {key}: {count}")
        return self.counts

    def _seed_standings(self, conn, sport, league, sport_id, team_repo, standing_repo):
        """Phase 2: Fetch and store league standings. Also discovers teams."""
        self.log(f"Fetching standings for {sport}/{league}")
        try:
            rl = RateLimiter()
            espn = ESPNClient(sport=ESPN_SPORT_MAP.get(sport, sport), league=league, rate_limiter=rl)
            standings_data = espn.get_standings()
            self._delay()
        except Exception as e:
            self.log(f"  Standings error: {e}")
            self.counts["errors"] += 1
            return

        if not standings_data:
            return

        # Ensure competition exists
        comp_id = self._ensure_competition(conn, league, sport_id)
        now = datetime.now(timezone.utc).isoformat()

        for entry in standings_data:
            team_name = entry.get("team_name", "")
            espn_team_id = entry.get("team_id", "")
            if not team_name:
                continue

            # Ensure team exists in DB and map ESPN ID
            team_id = self._ensure_team(
                conn, team_repo, team_name, sport_id, espn_team_id
            )

            # Parse numeric values safely
            rank = self._safe_int(entry.get("rank"))
            wins = self._safe_int(entry.get("wins"))
            draws = self._safe_int(entry.get("draws"))
            losses = self._safe_int(entry.get("losses"))
            points = self._safe_int(entry.get("points"))

            standing = Standing(
                id=None,
                competition_id=comp_id,
                team_id=team_id,
                season="",
                rank=rank,
                wins=wins,
                draws=draws,
                losses=losses,
                goals_for=0,
                goals_against=0,
                goal_diff=0,
                points=points,
                form="",
                home_wins=0,
                home_draws=0,
                home_losses=0,
                away_wins=0,
                away_draws=0,
                away_losses=0,
                streak="",
                source="espn",
                updated_at=now,
            )
            standing_repo.upsert(standing)
            self.counts["standings"] += 1

    def _seed_rosters(self, conn, sport, league, sport_id, athlete_repo, roster_repo, transaction_repo):
        """Phase 3: Fetch rosters and create athlete entries."""
        # Get all teams for this sport that have ESPN IDs
        teams_with_espn = [
            (team_id, espn_id)
            for (sid, espn_id), team_id in self._team_espn_map.items()
            if sid == sport_id and espn_id
        ]

        if not teams_with_espn:
            return

        self.log(f"Fetching rosters for {len(teams_with_espn)} teams")
        now = datetime.now(timezone.utc).isoformat()

        for team_id, espn_team_id in teams_with_espn:
            try:
                rl = RateLimiter()
                espn = ESPNClient(sport=ESPN_SPORT_MAP.get(sport, sport), league=league, rate_limiter=rl)
                roster = espn.get_team_roster(espn_team_id)
                self._delay()
            except Exception as e:
                self.log(f"  Roster error for team {espn_team_id}: {e}")
                self.counts["errors"] += 1
                continue

            for player in roster:
                athlete_ext_id = player.get("id", "")
                if not athlete_ext_id:
                    continue

                athlete = Athlete(
                    id=None,
                    external_id=athlete_ext_id,
                    sport_id=sport_id,
                    team_id=team_id,
                    name=player.get("name", ""),
                    position=player.get("position", ""),
                    jersey=player.get("jersey", ""),
                    age=player.get("age"),
                    height=player.get("height", ""),
                    weight=player.get("weight", ""),
                    status=player.get("status", "active"),
                    source="espn",
                    updated_at=now,
                )
                ath_id = athlete_repo.upsert(athlete)

                # Add to roster table
                roster_entry = TeamRoster(
                    id=None,
                    team_id=team_id,
                    athlete_id=ath_id,
                    position=player.get("position", ""),
                    jersey=player.get("jersey", ""),
                    status=player.get("status", "active"),
                    depth_rank=None,
                    season="",
                    updated_at=now,
                )
                roster_repo.upsert(roster_entry)
                self.counts["athletes"] += 1
                self.counts["rosters"] += 1

            # Also fetch transactions
            try:
                txns = espn.get_team_transactions(espn_team_id)
                self._delay()
                for txn in txns:
                    t = Transaction(
                        id=None,
                        team_id=team_id,
                        athlete_id=None,
                        transaction_type=txn.get("type", "unknown"),
                        description=txn.get("description", ""),
                        transaction_date=txn.get("date", ""),
                        source="espn",
                        fetched_at=now,
                    )
                    transaction_repo.insert(t)
                    self.counts["transactions"] += 1
            except Exception as e:
                self.log(f"  Transactions error: {e}")
                self.counts["errors"] += 1

    def _seed_ats_ou(self, conn, sport, league, sport_id, ats_repo, ou_repo):
        """Phase 4: Fetch ATS and O/U records for teams."""
        teams_with_espn = [
            (team_id, espn_id)
            for (sid, espn_id), team_id in self._team_espn_map.items()
            if sid == sport_id and espn_id
        ]

        if not teams_with_espn:
            return

        self.log(f"Fetching ATS/OU for {len(teams_with_espn)} teams")
        now = datetime.now(timezone.utc).isoformat()
        espn_sport = ESPN_SPORT_SLUGS.get(sport, sport)

        for team_id, espn_team_id in teams_with_espn:
            # ATS record
            try:
                ats_data = self.odds_client.get_team_ats(espn_sport, league, espn_team_id)
                self._delay()
                if ats_data:
                    record = TeamATSRecord(
                        id=None,
                        team_id=team_id,
                        sport_id=sport_id,
                        season=str(ats_data.get("season", "")),
                        season_type=ats_data.get("seasonType", 2),
                        wins=ats_data.get("wins", 0),
                        losses=ats_data.get("losses", 0),
                        pushes=ats_data.get("pushes", 0),
                        home_wins=ats_data.get("home", {}).get("wins", 0) if isinstance(ats_data.get("home"), dict) else 0,
                        home_losses=ats_data.get("home", {}).get("losses", 0) if isinstance(ats_data.get("home"), dict) else 0,
                        home_pushes=ats_data.get("home", {}).get("pushes", 0) if isinstance(ats_data.get("home"), dict) else 0,
                        away_wins=ats_data.get("away", {}).get("wins", 0) if isinstance(ats_data.get("away"), dict) else 0,
                        away_losses=ats_data.get("away", {}).get("losses", 0) if isinstance(ats_data.get("away"), dict) else 0,
                        away_pushes=ats_data.get("away", {}).get("pushes", 0) if isinstance(ats_data.get("away"), dict) else 0,
                        source="espn",
                        updated_at=now,
                    )
                    ats_repo.upsert(record)
                    self.counts["ats_records"] += 1
            except Exception as e:
                self.log(f"  ATS error for {espn_team_id}: {e}")
                self.counts["errors"] += 1

            # O/U record
            try:
                ou_data = self.odds_client.get_team_odds_records(espn_sport, league, espn_team_id)
                self._delay()
                if ou_data:
                    record = TeamOURecord(
                        id=None,
                        team_id=team_id,
                        sport_id=sport_id,
                        season=str(ou_data.get("season", "")),
                        season_type=ou_data.get("seasonType", 2),
                        overs=ou_data.get("overs", 0),
                        unders=ou_data.get("unders", 0),
                        pushes=ou_data.get("pushes", 0),
                        home_overs=ou_data.get("home", {}).get("overs", 0) if isinstance(ou_data.get("home"), dict) else 0,
                        home_unders=ou_data.get("home", {}).get("unders", 0) if isinstance(ou_data.get("home"), dict) else 0,
                        home_pushes=ou_data.get("home", {}).get("pushes", 0) if isinstance(ou_data.get("home"), dict) else 0,
                        away_overs=ou_data.get("away", {}).get("overs", 0) if isinstance(ou_data.get("away"), dict) else 0,
                        away_unders=ou_data.get("away", {}).get("unders", 0) if isinstance(ou_data.get("away"), dict) else 0,
                        away_pushes=ou_data.get("away", {}).get("pushes", 0) if isinstance(ou_data.get("away"), dict) else 0,
                        source="espn",
                        updated_at=now,
                    )
                    ou_repo.upsert(record)
                    self.counts["ou_records"] += 1
            except Exception as e:
                self.log(f"  O/U error for {espn_team_id}: {e}")
                self.counts["errors"] += 1

    def _seed_odds_and_predictions(self, conn, sport, league, date, odds_repo, prediction_repo):
        """Phase 5: Fetch event odds and ESPN predictions."""
        self.log(f"Fetching odds for {sport}/{league} on {date}")
        espn_sport = ESPN_SPORT_SLUGS.get(sport, sport)
        now = datetime.now(timezone.utc).isoformat()

        try:
            all_odds = self.odds_client.get_all_events_odds(espn_sport, league, date.replace("-", ""))
            self._delay()
        except Exception as e:
            self.log(f"  Odds fetch error: {e}")
            self.counts["errors"] += 1
            return

        if not all_odds:
            return

        for event_id, odds_list in all_odds.items():
            # Try to find matching fixture in DB by external_id
            fixture_row = conn.execute(
                "SELECT id FROM fixtures WHERE external_id = ?",
                (event_id,),
            ).fetchone()
            fixture_id = fixture_row["id"] if fixture_row else None

            for odds_entry in odds_list:
                if not isinstance(odds_entry, dict):
                    continue

                bookmaker = odds_entry.get("bookmaker", "ESPN")
                markets = odds_entry.get("markets", {})

                for market_type, market_data in markets.items():
                    if not isinstance(market_data, dict):
                        continue
                    for selection, odds_val in market_data.items():
                        if selection == "line":
                            continue
                        if not odds_val or not isinstance(odds_val, (int, float)):
                            continue
                        if fixture_id:
                            record = OddsRecord(
                                id=None,
                                fixture_id=fixture_id,
                                bookmaker=bookmaker,
                                market=market_type,
                                selection=selection,
                                odds=float(odds_val),
                                line=market_data.get("line"),
                                fetched_at=now,
                                is_closing=False,
                            )
                            odds_repo.upsert(record)
                            self.counts["odds"] += 1

            # Win probabilities
            if fixture_id:
                try:
                    probs = self.odds_client.get_win_probabilities(espn_sport, league, event_id, None)
                    self._delay()
                    if probs:
                        pred = ESPNPrediction(
                            id=None,
                            fixture_id=fixture_id,
                            home_win_pct=probs.get("home_win_pct"),
                            away_win_pct=probs.get("away_win_pct"),
                            tie_pct=probs.get("tie_pct"),
                            predictor_json=None,
                            power_index_home=None,
                            power_index_away=None,
                            source="espn",
                            fetched_at=now,
                        )
                        prediction_repo.upsert(pred)
                        self.counts["predictions"] += 1
                except Exception:
                    self.counts["errors"] += 1

    def _seed_player_stats(self, conn, sport, league, sport_id, gamelog_repo, split_repo):
        """Phase 6: Fetch player gamelogs and splits."""
        athletes = conn.execute(
            "SELECT id, external_id FROM athletes WHERE sport_id = ? LIMIT 200",
            (sport_id,),
        ).fetchall()

        if not athletes:
            return

        self.log(f"Fetching stats for {len(athletes)} athletes")

        for idx, ath_row in enumerate(athletes, 1):
            ath_id = ath_row["id"]
            ath_ext_id = ath_row["external_id"]

            if idx % 25 == 0 or idx == len(athletes):
                self.log(f"  Progress: {idx}/{len(athletes)} athletes processed")

            # Gamelog
            try:
                games = self.stats_client.get_player_gamelog(sport, league, ath_ext_id)
                self._delay()
                for game in games:
                    entry = PlayerGamelog(
                        id=None,
                        athlete_id=ath_id,
                        fixture_id=None,
                        game_date=game.get("date", "")[:10],
                        opponent=game.get("opponent", ""),
                        result=game.get("result", ""),
                        stats_json=json.dumps(game.get("stats", {})),
                        source="espn",
                    )
                    gamelog_repo.upsert(entry)
                    self.counts["gamelogs"] += 1
            except Exception as e:
                self.log(f"  Gamelog error for {ath_ext_id}: {e}")
                self.counts["errors"] += 1

            # Splits
            try:
                splits = self.stats_client.get_player_splits(sport, league, ath_ext_id)
                self._delay()
                now = datetime.now(timezone.utc).isoformat()
                for split_type, split_data in splits.items():
                    entry = PlayerSplit(
                        id=None,
                        athlete_id=ath_id,
                        split_type=split_type,
                        stats_json=json.dumps(split_data),
                        season="",
                        source="espn",
                        updated_at=now,
                    )
                    split_repo.upsert(entry)
                    self.counts["splits"] += 1
            except Exception as e:
                self.log(f"  Splits error for {ath_ext_id}: {e}")
                self.counts["errors"] += 1

    def _seed_power_index(self, conn, sport, league, sport_id, power_repo):
        """Phase 7: Fetch team power index ratings (league-wide call)."""
        self.log(f"Fetching power index for {sport}/{league}")
        espn_sport = ESPN_SPORT_SLUGS.get(sport, sport)
        now = datetime.now(timezone.utc).isoformat()
        season_year = datetime.now(timezone.utc).year

        try:
            pi_list = self.odds_client.get_power_index(espn_sport, league, season_year)
            self._delay()
        except Exception as e:
            self.log(f"  Power index fetch error: {e}")
            self.counts["errors"] += 1
            return

        if not pi_list:
            return

        for pi_data in pi_list:
            espn_team_id = str(pi_data.get("team_id", ""))
            if not espn_team_id:
                continue

            # Resolve to internal team_id
            team_id = self._team_espn_map.get((sport_id, espn_team_id))
            if not team_id:
                # Try to find by name
                team_name = pi_data.get("team_name", "")
                if team_name:
                    row = conn.execute(
                        "SELECT id FROM teams WHERE name = ? AND sport_id = ?",
                        (team_name, sport_id),
                    ).fetchone()
                    if row:
                        team_id = row["id"]
                        self._team_espn_map[(sport_id, espn_team_id)] = team_id

            if not team_id:
                continue

            rating = pi_data.get("bpi", 0.0)
            if not rating:
                continue

            entry = PowerIndex(
                id=None,
                team_id=team_id,
                sport_id=sport_id,
                season=str(season_year),
                rating=float(rating),
                offensive_rating=pi_data.get("offensive_rating"),
                defensive_rating=pi_data.get("defensive_rating"),
                rank=pi_data.get("rank"),
                source="espn",
                updated_at=now,
            )
            power_repo.upsert(entry)
            self.counts["power_index"] += 1

    def _ensure_competition(self, conn, league: str, sport_id: int) -> int:
        """Ensure a competition exists in DB, returning its ID."""
        # Try matching by name (ESPN league code as name)
        row = conn.execute(
            "SELECT id FROM competitions WHERE name = ? AND sport_id = ?",
            (league, sport_id),
        ).fetchone()
        if row:
            return row["id"]
        # Create new
        cur = conn.execute(
            "INSERT INTO competitions (name, sport_id, country, importance) VALUES (?, ?, ?, ?)",
            (league, sport_id, "", 3),
        )
        return cur.lastrowid

    def _ensure_team(self, conn, team_repo, name: str, sport_id: int, espn_team_id: str = "") -> int:
        """Ensure a team exists in DB, returning its ID. Tracks ESPN ID mapping."""
        # Check ESPN map first
        if espn_team_id and (sport_id, espn_team_id) in self._team_espn_map:
            return self._team_espn_map[(sport_id, espn_team_id)]

        # Try to find existing team by name
        team = team_repo.resolve(name, sport_id)
        if team:
            # Store ESPN mapping
            if espn_team_id:
                self._team_espn_map[(sport_id, espn_team_id)] = team.id
                # Also store ESPN ID in aliases if not already there
                if espn_team_id not in team.aliases:
                    new_aliases = team.aliases + [f"espn:{espn_team_id}"]
                    team_repo.update_aliases(team.id, new_aliases)
            return team.id

        # Create new team
        aliases = [f"espn:{espn_team_id}"] if espn_team_id else []
        new_team = team_repo.find_or_create(name, sport_id, aliases)
        if espn_team_id:
            self._team_espn_map[(sport_id, espn_team_id)] = new_team.id
        return new_team.id

    @staticmethod
    def _safe_int(value) -> int:
        """Convert a value to int safely, returning 0 on failure."""
        if value is None or value == "":
            return 0
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return 0


def main():
    parser = argparse.ArgumentParser(description="Seed database with ESPN data")
    parser.add_argument("--sports", default="", help="Comma-separated sports (default: all)")
    parser.add_argument("--leagues", default="", help="Comma-separated leagues (default: all for sport)")
    parser.add_argument("--skip-rosters", action="store_true", help="Skip roster fetching")
    parser.add_argument("--skip-odds", action="store_true", help="Skip odds data")
    parser.add_argument("--skip-players", action="store_true", help="Skip player gamelogs/splits")
    parser.add_argument("--date", default="", help="Target date YYYY-MM-DD (default: today)")
    parser.add_argument("--db", default=str(ROOT / "betting" / "data" / "betting.db"), help="DB path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    if args.sports:
        sports = [s.strip() for s in args.sports.split(",")]
    else:
        sports = list(ESPN_LEAGUES.keys())

    leagues = None
    if args.leagues:
        league_list = [l.strip() for l in args.leagues.split(",")]
        leagues = {s: league_list for s in sports}

    seeder = ESPNSeeder(db_path=args.db, verbose=args.verbose)
    seeder.run(
        sports=sports,
        leagues=leagues,
        date=args.date,
        skip_rosters=args.skip_rosters,
        skip_odds=args.skip_odds,
        skip_players=args.skip_players,
    )


if __name__ == "__main__":
    main()
