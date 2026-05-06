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


def _is_garbage_fixture(row: dict) -> bool:
    """Detect phantom/garbage fixtures that should be excluded.

    Rejects fixtures from playwright-scan that have:
    - T00:00:00 kickoff (no real time = scanner default)
    - Garbage team names (contains 'vs', URLs, tips text, etc.)
    - Team names that are clearly page chrome, not real teams
    """
    source = row.get("source", "")
    kickoff = row.get("kickoff", "")
    home = row.get("home_team", "")
    away = row.get("away_team", "")

    # Only filter playwright-scan; API sources are already validated
    if source not in ("playwright-scan", "scan-expansion"):
        return False

    # Reject dateless scan items (T00:00:00 = scanner default, not real kickoff)
    if "T00:00:00" in kickoff:
        return True

    # Reject garbage team names
    combined = f"{home} {away}".lower()
    garbage_patterns = [
        " vs ", "picks & odds", "odds for ", "tips ", "view prediction",
        "standings", " : ", "draw 1 x 2", "1 x 2", "elo #",
        "predictions", "best bets", "opening odds", "match stats",
        "pregame", "postgame", "season has", "analysis link",
        "confidence level", "line-ups", "overview", "head-to-head",
        "expert", "win tips", "correct score", "handicap tips",
        "today's matches", "pinned leagues", "my teams",
        "previous match day", "advancing to next round", "winner:",
        "sets legs", "there are no ", "completed",
        "typy bukmacherów", "kolejka", "wydarzenie", "bukmacherów",
        "transmisja", "gdzie oglądać", "pln za",
    ]
    if any(pat in combined for pat in garbage_patterns):
        return True

    # Reject if either team name is too short (<3) or too long (>50)
    if len(home) < 3 or len(away) < 3 or len(home) > 50 or len(away) > 50:
        return True

    return False


def load_fixtures_from_db(date: str, sport: str | None = None, include_unverified: bool = False) -> list[dict]:
    """Load fixtures for a date from DB, fallback to JSON.

    Args:
        date: Date string YYYY-MM-DD
        sport: Optional sport filter
        include_unverified: If False (default), excludes phantom playwright-scan
            fixtures with no real kickoff time. Set True for raw DB access.
    """
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

                if not include_unverified:
                    before = len(rows)
                    rows = [r for r in rows if not _is_garbage_fixture(r)]
                    filtered = before - len(rows)
                    if filtered:
                        print(f"[db_loader] Filtered {filtered} phantom fixtures ({before} → {len(rows)})")

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
                        try:
                            vals = json.loads(f.l10_values) if isinstance(f.l10_values, str) else f.l10_values
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
        from bet.db.repositories import SportRepo, TeamRepo

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

            # Get H2H form records for team_a vs team_b
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
            run = repo.get_run_status(date)
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


def _resolve_fixture_id(conn, sport: str, home_team: str, away_team: str, kickoff: str) -> int | None:
    """Resolve a fixture ID from team names + sport + kickoff date.

    Tries canonical names first, then aliases. Returns None if not found.
    """
    from bet.db.repositories import FixtureRepo, SportRepo

    sr = SportRepo(conn)
    s = sr.get_by_name(sport)
    if not s:
        return None

    # Extract date from kickoff (handle both "2026-05-05" and "2026-05-05T20:00:00")
    date = kickoff[:10] if kickoff else ""
    if not date:
        return None

    repo = FixtureRepo(conn)
    fixture = repo.get_by_teams_and_date(home_team, away_team, date, s.id)
    return fixture.id if fixture else None


def load_analysis_results_from_db(betting_date: str) -> list[dict]:
    """Load S3 analysis results from DB, fallback to s3_deep_stats JSON.

    Returns list of dicts compatible with gate_checker.py input format:
    [{sport, home_team, away_team, competition, kickoff, has_data,
      best_market, markets_evaluated, ranking, three_way_check,
      warnings, stats_a_summary, stats_b_summary, h2h_summary}]
    """
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import AnalysisResultRepo

        with get_db() as conn:
            repo = AnalysisResultRepo(conn)
            results = repo.get_by_date(betting_date)
            if results:
                out = []
                for ar in results:
                    # JOIN fixture info
                    row = conn.execute(
                        "SELECT f.kickoff, "
                        "ht.name AS home_team, at.name AS away_team, "
                        "COALESCE(s.name, '') AS sport, "
                        "COALESCE(c.name, '') AS competition "
                        "FROM fixtures f "
                        "JOIN teams ht ON f.home_team_id = ht.id "
                        "JOIN teams at ON f.away_team_id = at.id "
                        "LEFT JOIN sports s ON f.sport_id = s.id "
                        "LEFT JOIN competitions c ON f.competition_id = c.id "
                        "WHERE f.id = ?",
                        (ar.fixture_id,),
                    ).fetchone()
                    if not row:
                        continue

                    stats_summary = ar.stats_summary_json or {}
                    entry = {
                        "fixture_id": ar.fixture_id,
                        "sport": row["sport"],
                        "home_team": row["home_team"],
                        "away_team": row["away_team"],
                        "competition": row["competition"],
                        "kickoff": row["kickoff"],
                        "has_data": ar.has_data,
                        "best_market": {
                            "name": ar.best_market_name,
                            "line": ar.best_market_line,
                            "direction": ar.best_market_direction,
                            "safety_score": ar.best_safety_score,
                        },
                        "markets_evaluated": ar.markets_evaluated,
                        "ranking": ar.ranking_json,
                        "three_way_check": ar.three_way_check_json,
                        "warnings": ar.warnings_json,
                        "stats_a_summary": stats_summary.get("stats_a", {}),
                        "stats_b_summary": stats_summary.get("stats_b", {}),
                        "h2h_summary": stats_summary.get("h2h", {}),
                    }
                    out.append(entry)
                print(f"[db_loader] Loaded {len(out)} analysis results from DB for {betting_date}")
                return out
    except Exception as e:
        print(f"[db_loader] DB read failed for analysis results: {e}")

    # JSON fallback
    json_path = DATA_DIR / f"s3_deep_stats_{betting_date}.json"
    if not json_path.exists():
        # Try alternate naming without date prefix
        json_path = DATA_DIR / f"{betting_date}_s3_deep_stats.json"
    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        analyses = data.get("analyses", data if isinstance(data, list) else [])
        print(f"[db_loader] Loaded {len(analyses)} analysis results from JSON fallback")
        return analyses

    print(f"[db_loader] No analysis results found for {betting_date}")
    return []


def save_analysis_results_to_db(betting_date: str, analyses: list[dict]) -> int:
    """Write S3 analysis results to analysis_results table.

    Args:
        betting_date: YYYY-MM-DD
        analyses: list of dicts from deep_stats_report.py output

    Returns: number of rows written
    """
    if not analyses:
        return 0

    try:
        from bet.db.connection import get_db
        from bet.db.models import AnalysisResult
        from bet.db.repositories import AnalysisResultRepo

        saved = 0
        with get_db() as conn:
            repo = AnalysisResultRepo(conn)
            for a in analyses:
                # Resolve fixture_id
                fixture_id = a.get("fixture_id")
                if not fixture_id:
                    fixture_id = _resolve_fixture_id(
                        conn,
                        a.get("sport", ""),
                        a.get("home_team", ""),
                        a.get("away_team", ""),
                        a.get("kickoff", betting_date),
                    )
                if not fixture_id:
                    continue

                best_market = a.get("best_market", {}) or {}
                stats_summary = {}
                if a.get("stats_a_summary"):
                    stats_summary["stats_a"] = a["stats_a_summary"]
                if a.get("stats_b_summary"):
                    stats_summary["stats_b"] = a["stats_b_summary"]
                if a.get("h2h_summary"):
                    stats_summary["h2h"] = a["h2h_summary"]

                result = AnalysisResult(
                    id=None,
                    fixture_id=fixture_id,
                    betting_date=betting_date,
                    has_data=bool(a.get("has_data", False)),
                    best_market_name=best_market.get("name", ""),
                    best_market_line=best_market.get("line"),
                    best_market_direction=best_market.get("direction", ""),
                    best_safety_score=best_market.get("safety_score"),
                    markets_evaluated=a.get("markets_evaluated", 0),
                    ranking_json=a.get("ranking_result", {}).get("ranking", a.get("ranking", [])),
                    three_way_check_json=a.get("ranking_result", {}).get("three_way_check", a.get("three_way_check")),
                    warnings_json=a.get("ranking_result", {}).get("warnings", a.get("warnings", [])),
                    stats_summary_json=stats_summary or None,
                    source=a.get("source", "deep_stats_report"),
                    created_at=_NOW(),
                )
                repo.save(result)
                saved += 1

                # Also save raw data for decision learning
                raw_data_dict = a.get("raw_data")
                if raw_data_dict:
                    try:
                        from bet.db.models import AnalysisRawData
                        from bet.db.repositories import AnalysisRawDataRepo
                        raw_repo = AnalysisRawDataRepo(conn)
                        raw_model = AnalysisRawData(
                            id=None,
                            fixture_id=fixture_id,
                            betting_date=betting_date,
                            team_a_l10_json=raw_data_dict.get("team_a_l10", {}),
                            team_b_l10_json=raw_data_dict.get("team_b_l10", {}),
                            h2h_meetings_json=raw_data_dict.get("h2h_meetings", {}),
                            per_market_details_json=raw_data_dict.get("per_market_details", []),
                            safety_input_json=raw_data_dict.get("safety_input"),
                            created_at=_NOW(),
                        )
                        raw_repo.save(raw_model)
                    except Exception as e:
                        print(f"[db_loader] Raw data save failed for fixture {fixture_id}: {e}")

        print(f"[db_loader] Saved {saved} analysis results to DB")
        return saved
    except Exception as e:
        print(f"[db_loader] DB write failed for analysis results: {e}")
        return 0


def load_gate_results_from_db(betting_date: str, status: str | None = None) -> list[dict]:
    """Load S7 gate results from DB, fallback to s7_gate_results JSON.

    Args:
        betting_date: YYYY-MM-DD
        status: Optional filter — 'approved', 'extended', 'rejected', or None for all

    Returns list of dicts compatible with coupon_builder input format.
    """
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import GateResultRepo

        with get_db() as conn:
            repo = GateResultRepo(conn)
            if status == "approved":
                results = repo.get_approved(betting_date)
            elif status == "extended":
                results = repo.get_extended(betting_date)
            else:
                results = repo.get_by_date(betting_date)

            if results:
                out = []
                for gr in results:
                    row = conn.execute(
                        "SELECT f.kickoff, "
                        "ht.name AS home_team, at.name AS away_team, "
                        "COALESCE(s.name, '') AS sport, "
                        "COALESCE(c.name, '') AS competition "
                        "FROM fixtures f "
                        "JOIN teams ht ON f.home_team_id = ht.id "
                        "JOIN teams at ON f.away_team_id = at.id "
                        "LEFT JOIN sports s ON f.sport_id = s.id "
                        "LEFT JOIN competitions c ON f.competition_id = c.id "
                        "WHERE f.id = ?",
                        (gr.fixture_id,),
                    ).fetchone()
                    if not row:
                        continue

                    entry = {
                        "fixture_id": gr.fixture_id,
                        "sport": row["sport"],
                        "home_team": row["home_team"],
                        "away_team": row["away_team"],
                        "competition": row["competition"],
                        "kickoff": row["kickoff"],
                        "status": gr.status,
                        "gate_score": gr.gate_score,
                        "best_market": {
                            "name": gr.best_market_name,
                            "line": gr.best_market_line,
                            "direction": gr.best_market_direction,
                            "safety_score": gr.best_safety_score,
                        },
                        "ev": gr.ev,
                        "risk_tier": gr.risk_tier,
                        "gate_details": gr.gate_details_json,
                        "rejection_reasons": gr.rejection_reasons_json,
                    }
                    out.append(entry)
                print(f"[db_loader] Loaded {len(out)} gate results from DB for {betting_date}" +
                      (f" (status={status})" if status else ""))
                return out
    except Exception as e:
        print(f"[db_loader] DB read failed for gate results: {e}")

    # JSON fallback
    json_path = DATA_DIR / f"s7_gate_results_{betting_date}.json"
    if not json_path.exists():
        json_path = DATA_DIR / f"{betting_date}_s7_gate_results.json"
    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        results_list = data if isinstance(data, list) else data.get("results", [])
        if status:
            results_list = [r for r in results_list if r.get("status") == status]
        print(f"[db_loader] Loaded {len(results_list)} gate results from JSON fallback")
        return results_list

    print(f"[db_loader] No gate results found for {betting_date}")
    return []


def save_gate_results_to_db(betting_date: str, results: list[dict]) -> int:
    """Write S7 gate results to gate_results table.

    Args:
        betting_date: YYYY-MM-DD
        results: list of dicts from gate_checker.py output

    Returns: number of rows written
    """
    if not results:
        return 0

    try:
        from bet.db.connection import get_db
        from bet.db.models import GateResult
        from bet.db.repositories import GateResultRepo

        saved = 0
        with get_db() as conn:
            repo = GateResultRepo(conn)
            for r in results:
                fixture_id = r.get("fixture_id")
                if not fixture_id:
                    fixture_id = _resolve_fixture_id(
                        conn,
                        r.get("sport", ""),
                        r.get("home_team", ""),
                        r.get("away_team", ""),
                        r.get("kickoff", betting_date),
                    )
                if not fixture_id:
                    continue

                best_market = r.get("best_market", {}) or {}
                gate_result = GateResult(
                    id=None,
                    fixture_id=fixture_id,
                    betting_date=betting_date,
                    status=r.get("status", "pending"),
                    gate_score=r.get("gate_score", 0),
                    gate_details_json=r.get("gate_details", {}),
                    best_market_name=best_market.get("name", ""),
                    best_market_line=best_market.get("line"),
                    best_market_direction=best_market.get("direction", ""),
                    best_safety_score=best_market.get("safety_score"),
                    ev=r.get("ev"),
                    risk_tier=r.get("risk_tier", ""),
                    rejection_reasons_json=r.get("rejection_reasons", []),
                    source=r.get("source", "gate_checker"),
                    created_at=_NOW(),
                )
                repo.save(gate_result)
                saved += 1

        print(f"[db_loader] Saved {saved} gate results to DB")
        return saved
    except Exception as e:
        print(f"[db_loader] DB write failed for gate results: {e}")
        return 0


def load_betclic_history_from_db() -> list[dict]:
    """Load bet history from bets+coupons tables, fallback to betclic_bets_history.json.

    Returns list of dicts in the same format as betclic_bets_history.json:
    [{coupon_id, placed_at, total_odds, stake, status, pnl, picks: [...]}]
    """
    try:
        from bet.db.connection import get_db

        with get_db() as conn:
            # Query only settled coupons (skip pending pipeline-generated ones)
            coupon_rows = conn.execute(
                "SELECT * FROM coupons WHERE status IN ('won', 'lost') ORDER BY placed_at DESC"
            ).fetchall()
            if coupon_rows:
                history = []
                for c in coupon_rows:
                    bet_rows = conn.execute(
                        "SELECT b.sport, b.event_name, b.market, b.selection, "
                        "b.odds, b.status "
                        "FROM bets b WHERE b.coupon_id = ?",
                        (c["id"],),
                    ).fetchall()
                    picks = [
                        {
                            "sport": b["sport"] or "",
                            "event": b["event_name"] or "",
                            "market": b["market"] or "",
                            "selection": b["selection"] or "",
                            "odds": b["odds"],
                            "status": b["status"] or "",
                            "leg_status": b["status"] or "",  # compat alias
                        }
                        for b in bet_rows
                    ]
                    status_val = c["status"] or ""
                    stake_val = c["stake_pln"] or 0
                    pnl_val = c["pnl_pln"] or 0
                    winnings = (stake_val + pnl_val) if status_val == "won" else 0
                    history.append({
                        "coupon_id": c["coupon_id"],
                        "placed_at": c["placed_at"] or "",
                        "placed_date": c["placed_at"] or "",  # compat alias
                        "total_odds": c["total_odds"],
                        "stake": stake_val,
                        "stake_pln": stake_val,  # compat alias
                        "status": status_val,
                        "coupon_status": status_val,  # compat alias
                        "pnl": pnl_val,
                        "pnl_pln": pnl_val,  # compat alias
                        "winnings_pln": winnings,  # compat
                        "tax_free_payout_pln": winnings,  # compat
                        "is_ended": True,  # all DB records are ended
                        "expected_legs": len(picks),  # compat
                        "picks": picks,
                        "legs": picks,  # compat alias
                    })
                print(f"[db_loader] Loaded {len(history)} coupons from DB")
                return history
    except Exception as e:
        print(f"[db_loader] DB read failed for betclic history: {e}")

    # JSON fallback
    json_path = DATA_DIR / "betclic_bets_history.json"
    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        history = data if isinstance(data, list) else data.get("bets", [])
        print(f"[db_loader] Loaded {len(history)} history entries from JSON fallback")
        return history

    print("[db_loader] No betclic history found (DB empty, no JSON)")
    return []


def load_analysis_raw_data(fixture_id: int, betting_date: str) -> dict | None:
    """Load full raw analysis data for a fixture."""
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import AnalysisRawDataRepo

        with get_db() as conn:
            repo = AnalysisRawDataRepo(conn)
            raw = repo.get_by_fixture(fixture_id, betting_date)
            if raw:
                return {
                    "fixture_id": raw.fixture_id,
                    "betting_date": raw.betting_date,
                    "team_a_l10": raw.team_a_l10_json,
                    "team_b_l10": raw.team_b_l10_json,
                    "h2h_meetings": raw.h2h_meetings_json,
                    "per_market_details": raw.per_market_details_json,
                    "safety_input": raw.safety_input_json,
                }
    except Exception as e:
        print(f"[db_loader] Failed to load raw data for fixture {fixture_id}: {e}")
    return None


def load_decision_snapshot(bet_id: int) -> dict | None:
    """Load decision snapshot for a specific bet."""
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import DecisionSnapshotRepo

        with get_db() as conn:
            repo = DecisionSnapshotRepo(conn)
            snap = repo.get_by_bet(bet_id)
            if snap:
                return {
                    "bet_id": snap.bet_id,
                    "fixture_id": snap.fixture_id,
                    "betting_date": snap.betting_date,
                    "chosen_market": snap.chosen_market,
                    "chosen_line": snap.chosen_line,
                    "chosen_direction": snap.chosen_direction,
                    "safety_score": snap.safety_score,
                    "all_markets_considered": snap.all_markets_considered_json,
                    "reasoning": snap.reasoning_json,
                    "thresholds": snap.thresholds_json,
                    "flip_conditions": snap.flip_conditions_json,
                    "team_a_snapshot": snap.team_a_snapshot_json,
                    "team_b_snapshot": snap.team_b_snapshot_json,
                    "h2h_snapshot": snap.h2h_snapshot_json,
                    "three_way_check": snap.three_way_check_json,
                }
    except Exception as e:
        print(f"[db_loader] Failed to load decision snapshot for bet {bet_id}: {e}")
    return None


def save_decision_outcome(outcome_data: dict) -> bool:
    """Save a decision outcome after settlement."""
    try:
        from bet.db.connection import get_db
        from bet.db.models import DecisionOutcome
        from bet.db.repositories import DecisionOutcomeRepo

        with get_db() as conn:
            repo = DecisionOutcomeRepo(conn)
            outcome = DecisionOutcome(
                id=None,
                bet_id=outcome_data["bet_id"],
                fixture_id=outcome_data["fixture_id"],
                betting_date=outcome_data["betting_date"],
                sport=outcome_data.get("sport", ""),
                competition=outcome_data.get("competition", ""),
                market=outcome_data.get("market", ""),
                line=outcome_data.get("line"),
                direction=outcome_data.get("direction", ""),
                predicted_value=outcome_data.get("predicted_value"),
                actual_value=outcome_data.get("actual_value"),
                deviation=outcome_data.get("deviation"),
                deviation_pct=outcome_data.get("deviation_pct"),
                result=outcome_data.get("result", ""),
                prediction_accuracy_json=outcome_data.get("prediction_accuracy", {}),
                pattern_tags_json=outcome_data.get("pattern_tags", []),
                notes=outcome_data.get("notes", ""),
                created_at=_NOW(),
            )
            repo.save(outcome)
            conn.commit()
            return True
    except Exception as e:
        print(f"[db_loader] Failed to save decision outcome: {e}")
    return False


def load_decision_outcomes(sport: str | None = None, market: str | None = None, limit: int = 100) -> list[dict]:
    """Load decision outcomes for learning queries."""
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import DecisionOutcomeRepo

        with get_db() as conn:
            repo = DecisionOutcomeRepo(conn)
            if sport and market:
                outcomes = repo.get_by_sport_and_market(sport, market, limit)
            elif sport:
                outcomes = repo.get_by_sport(sport, limit)
            elif market:
                outcomes = repo.get_by_market(market, limit)
            else:
                outcomes = repo.get_all_settled(limit)
            return [
                {
                    "bet_id": o.bet_id,
                    "fixture_id": o.fixture_id,
                    "betting_date": o.betting_date,
                    "sport": o.sport,
                    "competition": o.competition,
                    "market": o.market,
                    "line": o.line,
                    "direction": o.direction,
                    "predicted_value": o.predicted_value,
                    "actual_value": o.actual_value,
                    "deviation": o.deviation,
                    "deviation_pct": o.deviation_pct,
                    "result": o.result,
                    "prediction_accuracy": o.prediction_accuracy_json,
                    "pattern_tags": o.pattern_tags_json,
                    "notes": o.notes,
                }
                for o in outcomes
            ]
    except Exception as e:
        print(f"[db_loader] Failed to load decision outcomes: {e}")
    return []


def get_deviation_stats(sport: str | None = None, market: str | None = None) -> dict:
    """Get aggregate deviation statistics for learning."""
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import DecisionOutcomeRepo

        with get_db() as conn:
            repo = DecisionOutcomeRepo(conn)
            return repo.get_deviation_stats(sport, market)
    except Exception as e:
        print(f"[db_loader] Failed to get deviation stats: {e}")
    return {"count": 0, "avg_deviation": 0.0, "avg_deviation_pct": 0.0,
            "overestimate_count": 0, "underestimate_count": 0,
            "won_count": 0, "lost_count": 0}


def get_market_bias(sport: str, market: str) -> dict | None:
    """Get the average prediction bias for a sport×market combination.

    Returns dict with bias info or None if insufficient data (n<5).
    Advisory only — NEVER used for auto-rejection.
    """
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import DecisionOutcomeRepo

        with get_db() as conn:
            repo = DecisionOutcomeRepo(conn)
            outcomes = repo.get_by_sport_and_market(sport, market, limit=200)
            with_values = [o for o in outcomes if o.actual_value is not None and o.predicted_value is not None]

            if len(with_values) < 5:
                return None

            avg_dev = sum((o.actual_value - o.predicted_value) for o in with_values) / len(with_values)
            non_zero = [o for o in with_values if o.predicted_value != 0]
            avg_dev_pct = (
                sum(((o.actual_value - o.predicted_value) / o.predicted_value * 100) for o in non_zero)
                / len(non_zero)
            ) if non_zero else 0.0

            if avg_dev_pct < -5:
                direction = "overestimate"
            elif avg_dev_pct > 5:
                direction = "underestimate"
            else:
                direction = "accurate"

            n = len(with_values)
            confidence = "high" if n >= 20 else "medium" if n >= 10 else "low"

            return {
                "sport": sport,
                "market": market,
                "count": n,
                "avg_deviation": round(avg_dev, 2),
                "avg_deviation_pct": round(avg_dev_pct, 1),
                "direction": direction,
                "confidence": confidence,
            }
    except Exception as e:
        print(f"[db_loader] Failed to get market bias for {sport}×{market}: {e}")
    return None


def get_league_adjustment(competition: str, market: str) -> float | None:
    """Get suggested adjustment factor for a league.

    Returns the average deviation_pct as a correction factor.
    E.g., if La Liga corners are overestimated by 12%, returns -0.12
    Only returns if n≥5 outcomes exist.
    Advisory only — for display to user.
    """
    try:
        from bet.db.connection import get_db

        with get_db() as conn:
            rows = conn.execute(
                "SELECT deviation_pct FROM decision_outcomes "
                "WHERE competition = ? AND market = ? "
                "AND actual_value IS NOT NULL AND predicted_value IS NOT NULL",
                (competition, market),
            ).fetchall()

            if len(rows) < 5:
                return None

            avg_pct = sum(r["deviation_pct"] for r in rows) / len(rows)
            # Return as correction factor (negative if overestimate)
            return round(-avg_pct / 100, 3)
    except Exception as e:
        print(f"[db_loader] Failed to get league adjustment for {competition}×{market}: {e}")
    return None


def get_team_pair_history(home_team: str, away_team: str) -> list[dict]:
    """Get all decision outcomes for a specific team pairing.

    Returns list of past outcomes showing prediction vs actual for this matchup.
    Advisory only — for display to user.
    """
    try:
        from bet.db.connection import get_db

        with get_db() as conn:
            # Find fixtures involving these teams (in either order)
            rows = conn.execute(
                "SELECT do.* FROM decision_outcomes do "
                "JOIN fixtures f ON do.fixture_id = f.id "
                "JOIN teams ht ON f.home_team_id = ht.id "
                "JOIN teams at ON f.away_team_id = at.id "
                "WHERE (ht.name = ? AND at.name = ?) OR (ht.name = ? AND at.name = ?) "
                "ORDER BY do.betting_date DESC",
                (home_team, away_team, away_team, home_team),
            ).fetchall()

            return [
                {
                    "bet_id": r["bet_id"],
                    "betting_date": r["betting_date"],
                    "sport": r["sport"],
                    "market": r["market"],
                    "line": r["line"],
                    "direction": r["direction"],
                    "predicted_value": r["predicted_value"],
                    "actual_value": r["actual_value"],
                    "deviation": r["deviation"],
                    "deviation_pct": r["deviation_pct"],
                    "result": r["result"],
                }
                for r in rows
            ]
    except Exception as e:
        print(f"[db_loader] Failed to get team pair history for {home_team} vs {away_team}: {e}")
    return []
