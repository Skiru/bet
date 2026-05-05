"""Shared DB data loader with JSON fallback.

Each function tries the SQLite DB first, falls back to JSON files if DB
is empty or unavailable. Used by all pipeline analysis scripts.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

DATA_DIR = ROOT_DIR / "betting" / "data"

_NOW = lambda: datetime.now(timezone.utc).isoformat()


def load_fixtures_from_db(date: str, sport: str | None = None) -> list[dict]:
    """Load fixtures for a date from DB, fallback to JSON."""
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import FixtureRepo, SportRepo

        with get_db() as conn:
            sport_id = None
            if sport:
                sr = SportRepo(conn)
                s = sr.get_by_name(sport)
                sport_id = s.id if s else None
            repo = FixtureRepo(conn)
            rows = repo.get_by_date_with_teams(date, sport_id)
            if rows:
                # Add 'sport' alias for 'sport_name' (JSON compat)
                for row in rows:
                    if "sport" not in row and "sport_name" in row:
                        row["sport"] = row["sport_name"]
                print(f"[db_loader] Loaded {len(rows)} fixtures from DB for {date}")
                return rows
    except Exception as e:
        print(f"[db_loader] DB read failed for fixtures: {e}")

    # JSON fallback
    json_path = DATA_DIR / f"fixtures_{date}.json"
    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        fixtures = data.get("fixtures", [])
        print(f"[db_loader] Loaded {len(fixtures)} fixtures from JSON fallback")
        return fixtures

    print(f"[db_loader] No fixtures found for {date} (DB empty, no JSON)")
    return []


def load_odds_from_db(date: str) -> dict:
    """Load odds for a date from DB, fallback to JSON snapshot.

    Returns dict keyed by a match identifier with odds data.
    """
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import OddsRepo

        with get_db() as conn:
            repo = OddsRepo(conn)
            odds_by_fixture = repo.get_all_for_date(date)
            if odds_by_fixture:
                # Convert to the format scripts expect
                events = []
                for fixture_id, records in odds_by_fixture.items():
                    # Group by bookmaker
                    bookmakers = {}
                    for r in records:
                        bk = r.bookmaker or "unknown"
                        if bk not in bookmakers:
                            bookmakers[bk] = []
                        bookmakers[bk].append({
                            "market": r.market,
                            "selection": r.selection,
                            "odds": r.odds,
                            "line": r.line,
                        })
                    events.append({
                        "fixture_id": fixture_id,
                        "bookmakers": bookmakers,
                    })
                print(f"[db_loader] Loaded odds for {len(odds_by_fixture)} fixtures from DB")
                return {"events": events, "total_events": len(events), "source": "db"}
    except Exception as e:
        print(f"[db_loader] DB read failed for odds: {e}")

    # JSON fallback
    json_path = DATA_DIR / "odds_api_snapshot.json"
    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        print(f"[db_loader] Loaded odds from JSON fallback ({data.get('total_events', 0)} events)")
        return data

    print("[db_loader] No odds data found (DB empty, no JSON)")
    return {"events": [], "total_events": 0}


def load_team_form_from_db(team_name: str, sport: str) -> dict | None:
    """Load team form (L10/L5/H2H) from DB, fallback to stats cache JSON.

    Returns data in cache-compatible format:
    {team, sport, form: {l10_avg: {stat_key: float}, l5_avg: {stat_key: float}, ...}, sources: [...]}
    """
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import SportRepo, StatsRepo, TeamRepo

        with get_db() as conn:
            sr = SportRepo(conn)
            s = sr.get_by_name(sport)
            if not s:
                raise ValueError(f"Unknown sport: {sport}")

            tr = TeamRepo(conn)
            team = tr.resolve(team_name, s.id)
            if not team:
                raise ValueError(f"Team not found: {team_name}")

            stats_repo = StatsRepo(conn)
            forms = stats_repo.get_all_form_for_team(team.id, s.id)
            if forms:
                # Convert DB format to cache-compatible format
                # DB: list of TeamForm rows, each with stat_key, l10_avg (float), l5_avg (float)
                # Cache: {form: {l10_avg: {stat_key: val}, l5_avg: {stat_key: val}, l10_matches: []}}
                result = {
                    "team": team_name,
                    "sport": sport,
                    "form": {
                        "l10_avg": {},
                        "l5_avg": {},
                        "l10_matches": [],
                    },
                    "sources": ["db"],
                }
                for f in forms:
                    if f.l10_avg is not None:
                        result["form"]["l10_avg"][f.stat_key] = f.l10_avg
                    if f.l5_avg is not None:
                        result["form"]["l5_avg"][f.stat_key] = f.l5_avg
                    # Reconstruct l10_matches from l10_values
                    if f.l10_values:
                        import json as _json
                        try:
                            vals = _json.loads(f.l10_values) if isinstance(f.l10_values, str) else f.l10_values
                            if isinstance(vals, list):
                                for i, val in enumerate(vals):
                                    while i >= len(result["form"]["l10_matches"]):
                                        result["form"]["l10_matches"].append({})
                                    result["form"]["l10_matches"][i][f.stat_key] = val
                        except Exception:
                            pass
                return result
    except Exception as e:
        print(f"[db_loader] DB read failed for team form {team_name}/{sport}: {e}")

    # JSON fallback - stats cache
    slug = re.sub(r"-+", "-", re.sub(r"[\s_]+", "-", re.sub(r"[^a-z0-9\s-]", "", team_name.lower()))).strip("-")
    cache_path = DATA_DIR / "stats_cache" / sport / f"{slug}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    return None


def load_h2h_from_db(
    team_a: str, team_b: str, sport: str
) -> dict | None:
    """Load H2H data between two teams from DB, fallback to cache."""
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import SportRepo, StatsRepo, TeamRepo

        with get_db() as conn:
            sr = SportRepo(conn)
            s = sr.get_by_name(sport)
            if not s:
                return None

            tr = TeamRepo(conn)
            ta = tr.resolve(team_a, s.id)
            tb = tr.resolve(team_b, s.id)
            if not ta or not tb:
                return None

            stats_repo = StatsRepo(conn)
            # Get H2H form records for team_a vs team_b
            h2h_forms = []
            rows = conn.execute(
                "SELECT * FROM team_form WHERE team_id = ? AND h2h_opponent_id = ?",
                (ta.id, tb.id),
            ).fetchall()
            if rows:
                return {
                    "team_a": team_a,
                    "team_b": team_b,
                    "sport": sport,
                    "h2h_records": [
                        {
                            "stat_key": r["stat_key"],
                            "h2h_values": json.loads(r["h2h_values"]),
                        }
                        for r in rows
                    ],
                }
    except Exception as e:
        print(f"[db_loader] DB read failed for H2H {team_a} vs {team_b}: {e}")

    return None


def load_scan_summary_from_db() -> dict:
    """Load scan summary from DB source_health or fallback to JSON."""
    json_path = DATA_DIR / "scan_summary.json"
    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8"))
    return {}


def load_pipeline_state(date: str) -> dict:
    """Load pipeline state from DB."""
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import PipelineRepo

        with get_db() as conn:
            repo = PipelineRepo(conn)
            run = repo.get_run(date)
            if run:
                return {
                    "date": date,
                    "steps": {
                        r["step"]: {
                            "status": r["status"],
                            "started_at": r["started_at"],
                            "completed_at": r["completed_at"],
                        }
                        for r in run
                    },
                }
    except Exception as e:
        print(f"[db_loader] DB read failed for pipeline state: {e}")

    # JSON fallback
    state_path = DATA_DIR / "pipeline_state" / f"pipeline_{date}.json"
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))

    return {"date": date, "steps": {}}
