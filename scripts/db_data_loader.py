"""Shared DB data loader with JSON fallback.

Each function tries the SQLite DB first, falls back to JSON files if DB
is empty or unavailable. Used by all pipeline analysis scripts.
"""
from copy import deepcopy
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

DATA_DIR = ROOT_DIR / "betting" / "data"

_NOW = lambda: datetime.now(timezone.utc).isoformat()

_GATE_BUCKET_STATUS = {
    "approved": "APPROVED",
    "extended_pool": "EXTENDED",
    "rejected": "REJECTED",
}


def _normalize_gate_bucket(bucket: str | None) -> str | None:
    if not bucket:
        return None
    normalized = str(bucket).strip().lower()
    if normalized == "extended":
        return "extended_pool"
    if normalized in _GATE_BUCKET_STATUS:
        return normalized
    return None


def _canonicalize_gate_bucket_status(
    *,
    status: str | None = None,
    bucket: str | None = None,
    extended_pool_reason: str | None = None,
    rejection_reasons: list[str] | None = None,
) -> tuple[str, str]:
    normalized_bucket = _normalize_gate_bucket(bucket)
    if not normalized_bucket and status:
        normalized_bucket = {
            "APPROVED": "approved",
            "EXTENDED": "extended_pool",
            "EXTENDED_POOL": "extended_pool",
            "REJECTED": "rejected",
        }.get(str(status).strip().upper())
    if not normalized_bucket:
        if extended_pool_reason:
            normalized_bucket = "extended_pool"
        elif rejection_reasons:
            normalized_bucket = "rejected"
        else:
            normalized_bucket = "approved"

    return normalized_bucket, _GATE_BUCKET_STATUS[normalized_bucket]


def _normalize_gate_result_entry(entry: dict) -> dict:
    normalized = dict(entry)

    gate_details = normalized.get("gate_details") or {}
    if not isinstance(gate_details, dict):
        gate_details = {}
    else:
        gate_details = dict(gate_details)

    rejection_reasons = normalized.get("rejection_reasons") or []
    if isinstance(rejection_reasons, str):
        rejection_reasons = [rejection_reasons]
    elif not isinstance(rejection_reasons, list):
        rejection_reasons = []
    else:
        rejection_reasons = list(rejection_reasons)

    rejection_reason = normalized.get("rejection_reason") or gate_details.get("rejection_reason")
    if rejection_reason and rejection_reason not in rejection_reasons:
        rejection_reasons.append(rejection_reason)

    extended_pool_reason = normalized.get("extended_pool_reason") or gate_details.get("extended_pool_reason")
    bucket, canonical_status = _canonicalize_gate_bucket_status(
        status=normalized.get("status"),
        bucket=normalized.get("bucket") or gate_details.get("bucket"),
        extended_pool_reason=extended_pool_reason,
        rejection_reasons=rejection_reasons,
    )

    normalized["bucket"] = bucket
    normalized["status"] = canonical_status
    gate_details["bucket"] = bucket

    if extended_pool_reason:
        normalized["extended_pool_reason"] = extended_pool_reason
        gate_details["extended_pool_reason"] = extended_pool_reason

    if rejection_reasons:
        normalized["rejection_reasons"] = rejection_reasons
        normalized["rejection_reason"] = rejection_reasons[0]
        gate_details.setdefault("rejection_reason", rejection_reasons[0])

    # Propagate pipeline metadata into gate_details_json for DB agent visibility
    if normalized.get("data_tier"):
        gate_details["data_tier"] = normalized["data_tier"]
    if normalized.get("comp_score") is not None:
        gate_details["comp_score"] = normalized["comp_score"]

    normalized["gate_details"] = gate_details
    return normalized


def _extract_gate_results_from_payload(data: dict | list, status_bucket: str | None = None) -> list[dict]:
    if isinstance(data, list):
        raw_results = data
    elif isinstance(data, dict):
        gate_results = data.get("gate_results")
        if isinstance(gate_results, dict):
            if status_bucket:
                raw_results = list(gate_results.get(status_bucket, []) or [])
            else:
                raw_results = []
                for bucket_name in ("approved", "extended_pool", "rejected"):
                    raw_results.extend(gate_results.get(bucket_name, []) or [])
        else:
            raw_results = data.get("results", []) if isinstance(data.get("results"), list) else []
    else:
        raw_results = []

    normalized_results = []
    for entry in raw_results:
        normalized = _normalize_gate_result_entry(entry)
        if status_bucket and normalized.get("bucket") != status_bucket:
            continue
        normalized_results.append(normalized)

    return normalized_results


def _is_garbage_fixture(row: dict) -> bool:
    """Detect phantom/garbage fixtures that should be excluded.

    Rejects fixtures from playwright-scan that have:
    - T00:00:00 kickoff (no real time = scanner default)
    - Garbage team names (contains 'vs', URLs, tips text, etc.)
    - Team names that are clearly page chrome, not real teams
    - Duplicate teams playing multiple matches on same date in same competition
      (indicates league schedule page scrape, not today's actual fixtures)
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


def _analysis_identity_component(value) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _analysis_identity_key(entry: dict) -> str:
    kickoff = entry.get("kickoff") or entry.get("date") or ""
    kickoff_date = str(kickoff)[:10]
    sport = _analysis_identity_component(entry.get("sport"))
    home = _analysis_identity_component(entry.get("home_team"))
    away = _analysis_identity_component(entry.get("away_team"))
    if sport and kickoff_date and home and away:
        return f"match:{sport}|{kickoff_date}|{home}|{away}"

    fixture_id = entry.get("fixture_id")
    if fixture_id not in (None, ""):
        return f"fixture:{fixture_id}"

    return ""


def _merge_analysis_candidate(base_entry: dict, overlay_entry: dict) -> dict:
    merged = deepcopy(base_entry)

    for key, value in overlay_entry.items():
        if value in (None, "", [], {}):
            continue

        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            nested = deepcopy(existing)
            for nested_key, nested_value in value.items():
                if nested_value in (None, "", [], {}):
                    continue
                nested[nested_key] = deepcopy(nested_value)
            merged[key] = nested
            continue

        merged[key] = deepcopy(value)

    return merged


def _build_stats_summary_payload(analysis: dict) -> dict:
    """Persist S3 metadata needed for DB-backed resume paths.

    S4-S6 append EV/context/upset-risk into stats_summary_json, so S3 seeds the
    base candidate metadata here to keep DB-only and mixed resume paths aligned
    with the JSON working set used by gate/build.
    """
    stats_summary = {}

    if analysis.get("stats_a_summary"):
        stats_summary["stats_a"] = deepcopy(analysis["stats_a_summary"])
    if analysis.get("stats_b_summary"):
        stats_summary["stats_b"] = deepcopy(analysis["stats_b_summary"])
    if analysis.get("h2h_summary"):
        stats_summary["h2h"] = deepcopy(analysis["h2h_summary"])
    if analysis.get("data_quality"):
        stats_summary["data_quality"] = deepcopy(analysis["data_quality"])
    if analysis.get("tipster_support"):
        stats_summary["tipster_support"] = deepcopy(analysis["tipster_support"])

    tipster_count = analysis.get("tipster_count")
    if tipster_count is None:
        tipster_count = (analysis.get("tipster_support") or {}).get("count")
    if tipster_count not in (None, ""):
        stats_summary["tipster_count"] = tipster_count

    return stats_summary


def _build_analysis_index(entries: list[dict]) -> tuple[dict[str, dict], dict[str, int]]:
    index: dict[str, dict] = {}
    duplicate_count = 0

    for position, entry in enumerate(entries):
        key = _analysis_identity_key(entry)
        if not key:
            key = f"unkeyed:{position}"
        if key in index:
            duplicate_count += 1
        index[key] = entry

    return index, {
        "input_count": len(entries),
        "unique_count": len(index),
        "duplicate_count": duplicate_count,
    }


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

                    # PHANTOM DETECTION: Filter playwright-scan fixtures where
                    # the same team appears in multiple matches on the same date.
                    # Real teams play at most 1 match per day (except double-headers
                    # in baseball/basketball). Multiple appearances = schedule page leak.
                    # Only apply to playwright-scan; API fixtures are authoritative.
                    scan_rows = [r for r in rows if r.get("source") in ("playwright-scan", "scan-expansion")]
                    api_rows = [r for r in rows if r.get("source") not in ("playwright-scan", "scan-expansion")]
                    
                    if scan_rows:
                        # Build set of teams from API fixtures (authoritative)
                        api_teams_by_sport: dict[str, set[str]] = {}
                        for r in api_rows:
                            sport_name = r.get("sport", r.get("sport_name", ""))
                            for t in (r.get("home_team", ""), r.get("away_team", "")):
                                if t:
                                    api_teams_by_sport.setdefault(sport_name, set()).add(t.lower())

                        # Count scan team appearances (with sport context)
                        from collections import Counter
                        scan_team_counts: Counter = Counter()
                        team_sport_map: dict[str, str] = {}
                        for r in scan_rows:
                            sport_name = r.get("sport", r.get("sport_name", "")).lower()
                            for t in (r.get("home_team", ""), r.get("away_team", "")):
                                if t:
                                    t_lower = t.lower()
                                    scan_team_counts[t_lower] += 1
                                    team_sport_map[t_lower] = sport_name

                        # Teams appearing beyond threshold are phantoms.
                        # Basketball/volleyball/baseball legitimately have double-headers.
                        DOUBLE_HEADER_SPORTS = {"basketball", "volleyball", "baseball"}
                        phantom_teams = set()
                        for team, count in scan_team_counts.items():
                            sport = team_sport_map.get(team, "")
                            threshold = 3 if sport in DOUBLE_HEADER_SPORTS else 2
                            if count > threshold:
                                phantom_teams.add(team)

                        if phantom_teams:
                            before_phantom = len(scan_rows)
                            scan_rows = [
                                r for r in scan_rows
                                if r.get("home_team", "").lower() not in phantom_teams
                                and r.get("away_team", "").lower() not in phantom_teams
                            ]
                            phantom_filtered = before_phantom - len(scan_rows)
                            if phantom_filtered:
                                print(f"[db_loader] Filtered {phantom_filtered} schedule-page phantom fixtures "
                                      f"({len(phantom_teams)} teams appearing in >2 scan matches)")

                        rows = api_rows + scan_rows

                print(f"[db_loader] Loaded {len(rows)} fixtures from DB for {date}")
                return rows
            else:
                print(f"[db_loader] WARNING: No fixtures found in DB for {date}. "
                      f"Run discover_events.py first.")
                return []
    except Exception as e:
        print(f"[db_loader] DB read failed for fixtures: {e}")
        return []


def load_odds_from_db(date: str) -> dict:
    """Load odds for a date from DB, fallback to JSON snapshot.

    Returns dict with "events" list in Odds-API-compatible format:
    Each event has home_team, away_team, sport, and bookmakers as a LIST of dicts
    (matching the-odds-api JSON structure that extract_markets_from_odds_api expects).
    """
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import OddsRepo

        with get_db() as conn:
            repo = OddsRepo(conn)
            odds_by_fixture = repo.get_all_for_date(date)
            if odds_by_fixture:
                # Need fixture details (home/away/sport) for the lookup key
                fixture_ids = list(odds_by_fixture.keys())
                placeholders = ",".join("?" for _ in fixture_ids)
                fixture_rows = conn.execute(
                    f"SELECT f.id, ht.name AS home_team, at.name AS away_team, s.name AS sport "
                    f"FROM fixtures f "
                    f"JOIN teams ht ON f.home_team_id = ht.id "
                    f"JOIN teams at ON f.away_team_id = at.id "
                    f"JOIN sports s ON f.sport_id = s.id "
                    f"WHERE f.id IN ({placeholders})",
                    fixture_ids,
                ).fetchall()
                fixture_map = {r["id"]: r for r in fixture_rows}

                events = []
                for fixture_id, records in odds_by_fixture.items():
                    fx = fixture_map.get(fixture_id)
                    if not fx:
                        continue
                    # Group by bookmaker → markets → outcomes (Odds-API format)
                    bm_markets: dict = {}  # bookmaker -> market_key -> outcomes
                    for r in records:
                        bk = r.bookmaker or "unknown"
                        if bk not in bm_markets:
                            bm_markets[bk] = {}
                        mkt = r.market or "h2h"
                        if mkt not in bm_markets[bk]:
                            bm_markets[bk][mkt] = []
                        outcome = {"name": r.selection, "price": r.odds}
                        if r.line is not None:
                            outcome["point"] = r.line
                        bm_markets[bk][mkt].append(outcome)

                    # Build bookmakers list in the-odds-api format
                    bookmakers_list = []
                    for bk_name, markets_dict in bm_markets.items():
                        markets_list = []
                        for mkt_key, outcomes in markets_dict.items():
                            markets_list.append({
                                "key": mkt_key,
                                "outcomes": outcomes,
                            })
                        bookmakers_list.append({
                            "key": bk_name,
                            "title": bk_name,
                            "markets": markets_list,
                        })

                    events.append({
                        "fixture_id": fixture_id,
                        "home_team": fx["home_team"],
                        "away_team": fx["away_team"],
                        "sport": fx["sport"],
                        "bookmakers": bookmakers_list,
                    })
                print(f"[db_loader] Loaded odds for {len(events)} fixtures from DB")
                return {"events": events, "total_events": len(events), "source": "db"}
            else:
                print(f"[db_loader] WARNING: No odds found in DB for {date}. "
                      f"Run fetch_odds_api.py or fetch_esports_odds.py first.")
                return {"events": [], "total_events": 0, "source": "db_empty"}
    except Exception as e:
        print(f"[db_loader] DB read failed for odds: {e}")
        return {"events": [], "total_events": 0, "source": "db_error"}


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

            # Get H2H form records for team_a vs team_b (try both directions)
            rows = conn.execute(
                "SELECT * FROM team_form WHERE team_id = ? AND h2h_opponent_id = ?",
                (ta.id, tb.id),
            ).fetchall()
            if not rows:
                # Try reverse direction
                rows = conn.execute(
                    "SELECT * FROM team_form WHERE team_id = ? AND h2h_opponent_id = ?",
                    (tb.id, ta.id),
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


def load_shortlist_from_db(date: str) -> list[dict]:
    """Load shortlist candidates from pipeline_candidates table.

    Returns list of dicts compatible with existing shortlist JSON format.
    Used by deep_stats_report.py and tipster_xref.py as primary input.
    """
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import PipelineCandidateRepo

        with get_db() as conn:
            repo = PipelineCandidateRepo(conn)
            candidates = repo.get_by_date(date)
            if candidates:
                print(f"[db_loader] Loaded {len(candidates)} candidates from pipeline_candidates table")
                return candidates
            else:
                print(f"[db_loader] No candidates in pipeline_candidates for {date}")
                return []
    except Exception as e:
        print(f"[db_loader] pipeline_candidates read failed: {e}")
        return []


def load_scan_summary_from_db(date: str | None = None) -> dict:
    """Load scan results from DB scan_results table, grouped by source_domain.

    Returns dict keyed by source_domain URL → list of event dicts,
    matching the format expected by generate_market_matrix.load_scan_summary().
    """
    try:
        from bet.db.connection import get_db

        with get_db() as conn:
            if date:
                rows = conn.execute(
                    "SELECT source_domain, home_team, away_team, sport, "
                    "competition, kickoff, raw_data "
                    "FROM scan_results WHERE betting_date = ? "
                    "ORDER BY sport, source_domain",
                    (date,),
                ).fetchall()
            else:
                # Load most recent betting_date
                latest = conn.execute(
                    "SELECT DISTINCT betting_date FROM scan_results "
                    "ORDER BY betting_date DESC LIMIT 1"
                ).fetchone()
                if not latest:
                    return {}
                rows = conn.execute(
                    "SELECT source_domain, home_team, away_team, sport, "
                    "competition, kickoff, raw_data "
                    "FROM scan_results WHERE betting_date = ? "
                    "ORDER BY sport, source_domain",
                    (latest["betting_date"],),
                ).fetchall()

            if not rows:
                return {}

            # Group by source_domain (acts as URL key for downstream compatibility)
            result: dict[str, list] = {}
            for row in rows:
                domain = row["source_domain"] or "unknown"
                item = {
                    "home": row["home_team"] or "",
                    "away": row["away_team"] or "",
                    "home_team": row["home_team"] or "",
                    "away_team": row["away_team"] or "",
                    "sport": row["sport"] or "",
                    "competition": row["competition"] or "",
                    "league": row["competition"] or "",
                    "time": row["kickoff"] or "",
                    "odds": [],
                }
                # Parse raw_data JSON if present (may contain odds)
                if row["raw_data"]:
                    try:
                        raw = json.loads(row["raw_data"])
                        if isinstance(raw, dict):
                            item["odds"] = raw.get("odds", [])
                            # Preserve any deep data (h2h, form, etc.)
                            for key in ("h2h", "form_home", "form_away", "trends", "match_info"):
                                if key in raw:
                                    item[key] = raw[key]
                    except (json.JSONDecodeError, TypeError):
                        pass

                result.setdefault(domain, []).append(item)

            print(f"[db_loader] Loaded {len(rows)} scan results from DB ({len(result)} sources)")
            return result
    except Exception as e:
        print(f"[db_loader] DB read failed for scan_results: {e}")
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


def _create_minimal_fixture(conn, sport: str, home_team: str, away_team: str,
                            kickoff: str, competition: str = "") -> int | None:
    """Create a minimal fixture entry when resolve fails. Returns fixture ID or None."""
    from bet.db.models import Fixture
    from bet.db.repositories import CompetitionRepo, FixtureRepo, SportRepo, TeamRepo

    try:
        sr = SportRepo(conn)
        s = sr.get_by_name(sport)
        if not s:
            sr.seed_defaults()
            s = sr.get_by_name(sport)
        if not s:
            return None

        tr = TeamRepo(conn)
        home = tr.find_or_create(home_team, s.id)
        away = tr.find_or_create(away_team, s.id)

        comp_id = None
        if competition:
            cr = CompetitionRepo(conn)
            comp_id = cr.find_or_create(competition, s.id)

        fixture = Fixture(
            id=None,
            sport_id=s.id,
            competition_id=comp_id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff=kickoff,
            status="scheduled",
            source="auto-created-by-s3",
            fetched_at=_NOW(),
        )
        repo = FixtureRepo(conn)
        return repo.upsert(fixture)
    except Exception as e:
        print(f"[db_loader] Failed to create minimal fixture for {home_team} vs {away_team}: {e}")
        return None


def _load_analysis_results_raw_from_db(betting_date: str) -> list[dict]:
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
                            **(
                                {
                                    "hit_rate_l10": ar.ranking_json[0].get("hit_rate_l10", "N/A"),
                                    "hit_rate_l5": ar.ranking_json[0].get("hit_rate_l5", "N/A"),
                                    "hit_rate_h2h": ar.ranking_json[0].get("hit_rate_h2h", "N/A"),
                                    "source": ar.ranking_json[0].get("source", ""),
                                    "h2h_blind": ar.ranking_json[0].get("h2h_blind", True),
                                }
                                if ar.ranking_json and isinstance(ar.ranking_json, list) and len(ar.ranking_json) > 0
                                else {}
                            ),
                        },
                        "markets_evaluated": ar.markets_evaluated,
                        "ranking": ar.ranking_json,
                        "three_way_check": ar.three_way_check_json,
                        "warnings": ar.warnings_json,
                        "stats_a_summary": stats_summary.get("stats_a", {}),
                        "stats_b_summary": stats_summary.get("stats_b", {}),
                        "h2h_summary": stats_summary.get("h2h", {}),
                        "data_quality": stats_summary.get("data_quality"),
                        "tipster_support": stats_summary.get("tipster_support", {}),
                        "tipster_count": (
                            stats_summary.get("tipster_count")
                            or (stats_summary.get("tipster_support") or {}).get("count")
                            or 0
                        ),
                        # S4/S5/S6 enrichment fields from stats_summary_json
                        "ev": stats_summary.get("ev"),
                        "ev_source": stats_summary.get("ev_source"),
                        "odds": {
                            "market_best": stats_summary.get("odds_market_best"),
                            "betclic": stats_summary.get("odds_betclic"),
                        } if stats_summary.get("odds_market_best") else {},
                        "context_flags": stats_summary.get("context_flags", []),
                        "upset_risk": stats_summary.get("upset_risk"),
                    }
                    out.append(entry)
                print(f"[db_loader] Loaded {len(out)} analysis results from DB for {betting_date}")
                return out
    except Exception as e:
        print(f"[db_loader] DB read failed for analysis results: {e}")

    return []


def _load_analysis_results_raw_from_json(betting_date: str) -> list[dict]:
    json_path = DATA_DIR / f"{betting_date}_s3_deep_stats.json"
    if not json_path.exists():
        json_path = DATA_DIR / f"s3_deep_stats_{betting_date}.json"
    if not json_path.exists():
        return []

    data = json.loads(json_path.read_text(encoding="utf-8"))
    analyses = data.get("analyses", data if isinstance(data, list) else [])
    print(f"[db_loader] Loaded {len(analyses)} analysis results from JSON fallback")
    return analyses


def load_s3_candidates_with_parity(betting_date: str) -> tuple[list[dict], dict]:
    """Load the canonical S3 candidate universe with DB/JSON parity metadata.

    JSON is the canonical universe when present because it preserves the full
    S3 shortlist-derived candidate set. DB data is overlaid onto matching JSON
    candidates so resume paths keep persisted enrichment fields without letting
    partial DB persistence silently narrow the universe.

    Returns:
        (candidates, metadata)
    """
    db_entries = _load_analysis_results_raw_from_db(betting_date)
    json_entries = _load_analysis_results_raw_from_json(betting_date)

    db_index, db_stats = _build_analysis_index(db_entries)
    json_index, json_stats = _build_analysis_index(json_entries)

    db_keys = set(db_index)
    json_keys = set(json_index)
    shared_keys = sorted(db_keys & json_keys)
    json_only_keys = sorted(json_keys - db_keys)
    db_only_keys = sorted(db_keys - json_keys)

    metadata = {
        "source": "none",
        "counts": {
            "canonical": 0,
            "json": len(json_entries),
            "db": len(db_entries),
        },
        "parity": {
            "status": "missing",
            "shared_candidates": len(shared_keys),
            "json_only_candidates": len(json_only_keys),
            "db_only_candidates": len(db_only_keys),
            "json_index": json_stats,
            "db_index": db_stats,
            "overlay_candidates": 0,
        },
    }

    if json_entries:
        if db_only_keys:
            metadata["source"] = "parity_error"
            metadata["parity"]["status"] = "mismatch"
            metadata["blocking_error"] = {
                "code": "s3_candidate_parity_mismatch",
                "message": (
                    "DB contains candidates not present in S3 JSON; refusing to choose "
                    "between divergent S3 universes"
                ),
            }
            return [], metadata

        merged_entries: list[dict] = []
        for entry in json_entries:
            key = _analysis_identity_key(entry)
            db_entry = db_index.get(key)
            merged_entries.append(
                _merge_analysis_candidate(entry, db_entry) if db_entry else deepcopy(entry)
            )

        metadata["source"] = "json_with_db_overlay" if shared_keys else "json"
        metadata["counts"]["canonical"] = len(merged_entries)
        metadata["parity"]["overlay_candidates"] = len(shared_keys)
        if not db_entries:
            metadata["parity"]["status"] = "json_only"
        else:
            metadata["parity"]["status"] = "exact" if not json_only_keys else "db_subset_of_json"
        return merged_entries, metadata

    if db_entries:
        metadata["source"] = "db"
        metadata["counts"]["canonical"] = len(db_entries)
        metadata["parity"]["status"] = "db_only"
        return deepcopy(db_entries), metadata

    return [], metadata


def load_analysis_results_from_db(betting_date: str) -> list[dict]:
    """Load S3 analysis results from DB, fallback to s3_deep_stats JSON.

    Returns list of dicts compatible with gate_checker.py input format:
    [{sport, home_team, away_team, competition, kickoff, has_data,
      best_market, markets_evaluated, ranking, three_way_check,
      warnings, stats_a_summary, stats_b_summary, h2h_summary}]
    """
    db_entries = _load_analysis_results_raw_from_db(betting_date)
    if db_entries:
        return db_entries

    analyses = _load_analysis_results_raw_from_json(betting_date)
    if analyses:
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
        skipped = 0
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
                    # Fallback: create a minimal fixture entry
                    fixture_id = _create_minimal_fixture(
                        conn,
                        a.get("sport", ""),
                        a.get("home_team", ""),
                        a.get("away_team", ""),
                        a.get("kickoff", betting_date),
                        a.get("competition", ""),
                    )
                if not fixture_id:
                    print(
                        f"[db_loader] WARN: Skipping analysis — no fixture for "
                        f"{a.get('home_team', '?')} vs {a.get('away_team', '?')} ({a.get('sport', '?')})"
                    )
                    skipped += 1
                    continue
                # Inject fixture_id back so downstream steps (S4/S5/S6) have it
                a["fixture_id"] = fixture_id

                best_market = a.get("best_market", {}) or {}
                stats_summary = _build_stats_summary_payload(a)

                result = AnalysisResult(
                    id=None,
                    fixture_id=fixture_id,
                    betting_date=betting_date,
                    has_data=bool(a.get("has_data", False)),
                    best_market_name=best_market.get("name", ""),
                    best_market_line=best_market.get("line"),
                    best_market_direction=best_market.get("direction", ""),
                    best_safety_score=best_market.get("safety_score") or 0.0,
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

        print(f"[db_loader] Saved {saved} analysis results to DB (skipped {skipped})")
        return saved
    except Exception as e:
        print(f"[db_loader] DB write failed for analysis results: {e}")
        return 0


def load_gate_results_from_db_only(betting_date: str, status: str | None = None) -> list[dict]:
    """Load S7 gate results from DB only.

    Args:
        betting_date: YYYY-MM-DD
        status: Optional filter — 'approved', 'extended', 'rejected', or None for all

    Returns list of dicts compatible with coupon_builder input format.
    """
    status_bucket = _normalize_gate_bucket(status)

    try:
        from bet.db.connection import get_db
        from bet.db.repositories import GateResultRepo

        with get_db() as conn:
            repo = GateResultRepo(conn)
            if status_bucket == "approved":
                results = repo.get_approved(betting_date)
            elif status_bucket == "extended_pool":
                results = repo.get_extended(betting_date)
            elif status_bucket == "rejected":
                results = repo.get_rejected(betting_date)
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

                    # Reconstruct advisory_tier from gate_details_json or gate_score
                    details = gr.gate_details_json or {}
                    advisory_tier = details.get("advisory_tier")
                    if not advisory_tier and gr.status == "APPROVED":
                        # Reconstruct from gate_score (18-point gate, n_failed = 18 - score)
                        # gate_score may be int or string like "14/18"
                        score_val = gr.gate_score
                        if isinstance(score_val, str) and "/" in score_val:
                            score_val = int(score_val.split("/")[0])
                        elif isinstance(score_val, str):
                            score_val = int(score_val) if score_val.isdigit() else 0
                        n_failed = 18 - int(score_val)
                        if n_failed <= 2:
                            advisory_tier = "STRONG"
                        elif n_failed <= 5:
                            advisory_tier = "MODERATE"
                        elif n_failed <= 9:
                            advisory_tier = "WEAK"
                        else:
                            advisory_tier = "FLAGGED"

                    entry = _normalize_gate_result_entry({
                        "fixture_id": gr.fixture_id,
                        "sport": row["sport"],
                        "home_team": row["home_team"],
                        "away_team": row["away_team"],
                        "competition": row["competition"],
                        "kickoff": row["kickoff"],
                        "status": gr.status,
                        "advisory_tier": advisory_tier,
                        "gate_score": gr.gate_score,
                        "best_market": {
                            "name": gr.best_market_name,
                            "line": gr.best_market_line,
                            "direction": gr.best_market_direction,
                            "safety_score": gr.best_safety_score or 0.0,
                        },
                        "ev": gr.ev,
                        "risk_tier": gr.risk_tier,
                        "gate_details": details,
                        "rejection_reasons": gr.rejection_reasons_json,
                        "source": gr.source,
                    })
                    out.append(entry)

                if out:
                    print(f"[db_loader] Loaded {len(out)} gate results from DB for {betting_date}" +
                          (f" (status={status})" if status else ""))
                    return out
    except Exception as e:
        print(f"[db_loader] DB read failed for gate results: {e}")

    return []


def load_gate_results_from_db(betting_date: str, status: str | None = None) -> list[dict]:
    """Load S7 gate results from DB, fallback to s7_gate_results JSON.

    Args:
        betting_date: YYYY-MM-DD
        status: Optional filter — 'approved', 'extended', 'rejected', or None for all

    Returns list of dicts compatible with coupon_builder input format.
    """
    status_bucket = _normalize_gate_bucket(status)
    results = load_gate_results_from_db_only(betting_date, status)
    if results:
        return results

    # JSON fallback
    json_path = DATA_DIR / f"{betting_date}_s7_gate_results.json"
    if not json_path.exists():
        json_path = DATA_DIR / f"s7_gate_results_{betting_date}.json"
    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        results_list = _extract_gate_results_from_payload(data, status_bucket)
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
        skipped_gate = 0
        with get_db() as conn:
            repo = GateResultRepo(conn)
            for r in results:
                normalized_result = _normalize_gate_result_entry(r)

                fixture_id = normalized_result.get("fixture_id")
                if not fixture_id:
                    fixture_id = _resolve_fixture_id(
                        conn,
                        normalized_result.get("sport", ""),
                        normalized_result.get("home_team", ""),
                        normalized_result.get("away_team", ""),
                        normalized_result.get("kickoff", betting_date),
                    )
                if not fixture_id:
                    fixture_id = _create_minimal_fixture(
                        conn,
                        normalized_result.get("sport", ""),
                        normalized_result.get("home_team", ""),
                        normalized_result.get("away_team", ""),
                        normalized_result.get("kickoff", betting_date),
                        normalized_result.get("competition", ""),
                    )
                if not fixture_id:
                    print(
                        f"[db_loader] WARN: Skipping gate result — no fixture for "
                        f"{normalized_result.get('home_team', '?')} vs {normalized_result.get('away_team', '?')} ({normalized_result.get('sport', '?')})"
                    )
                    skipped_gate += 1
                    continue

                best_market = normalized_result.get("best_market", {}) or {}
                # Preserve advisory_tier in gate_details_json for DB round-trip
                gate_details = normalized_result.get("gate_details", {}) or {}
                if isinstance(gate_details, dict) and normalized_result.get("advisory_tier"):
                    gate_details["advisory_tier"] = normalized_result["advisory_tier"]
                gate_result = GateResult(
                    id=None,
                    fixture_id=fixture_id,
                    betting_date=betting_date,
                    status=normalized_result.get("status", "pending"),
                    gate_score=normalized_result.get("gate_score", 0),
                    gate_details_json=gate_details,
                    best_market_name=best_market.get("name", ""),
                    best_market_line=best_market.get("line"),
                    best_market_direction=best_market.get("direction", ""),
                    best_safety_score=best_market.get("safety_score") or 0.0,
                    ev=normalized_result.get("ev"),
                    risk_tier=normalized_result.get("risk_tier", ""),
                    rejection_reasons_json=normalized_result.get("rejection_reasons", []),
                    source=normalized_result.get("source", "gate_checker"),
                    created_at=_NOW(),
                )
                repo.save(gate_result)
                saved += 1

        print(f"[db_loader] Saved {saved} gate results to DB (skipped {skipped_gate})")
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


# ---------------------------------------------------------------------------
# ESPN Enrichment Loaders
# ---------------------------------------------------------------------------

def load_espn_enrichment_for_team(team_name: str, sport: str) -> dict | None:
    """Load ESPN enrichment data for a team: ATS/OU records, standings, power index.

    Returns dict with keys: ats_record, ou_record, standing, power_index, predictions
    or None if no data available.
    """
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import (
            PowerIndexRepo,
            SportRepo,
            StandingRepo,
            TeamATSRepo,
            TeamOURepo,
            TeamRepo,
        )

        with get_db() as conn:
            sr = SportRepo(conn)
            s = sr.get_by_name(sport)
            if not s:
                return None

            tr = TeamRepo(conn)
            team = tr.resolve(team_name, s.id)
            if not team:
                return None

            result = {}

            # ATS records
            ats_repo = TeamATSRepo(conn)
            ats_records = ats_repo.get_for_team(team.id)
            if ats_records:
                r = ats_records[0]  # Most recent season
                total = r.wins + r.losses + r.pushes
                result["ats_record"] = {
                    "season": r.season,
                    "wins": r.wins,
                    "losses": r.losses,
                    "pushes": r.pushes,
                    "cover_pct": round(r.wins / total * 100, 1) if total > 0 else 0.0,
                    "home_wins": r.home_wins,
                    "home_losses": r.home_losses,
                    "away_wins": r.away_wins,
                    "away_losses": r.away_losses,
                }

            # OU records
            ou_repo = TeamOURepo(conn)
            ou_records = ou_repo.get_for_team(team.id)
            if ou_records:
                r = ou_records[0]
                total = r.overs + r.unders + r.pushes
                result["ou_record"] = {
                    "season": r.season,
                    "overs": r.overs,
                    "unders": r.unders,
                    "pushes": r.pushes,
                    "over_pct": round(r.overs / total * 100, 1) if total > 0 else 0.0,
                    "home_overs": r.home_overs,
                    "home_unders": r.home_unders,
                    "away_overs": r.away_overs,
                    "away_unders": r.away_unders,
                }

            # Standings
            standing_repo = StandingRepo(conn)
            # Get any standing for this team (any competition)
            standing_row = conn.execute(
                "SELECT * FROM standings WHERE team_id = ? ORDER BY updated_at DESC LIMIT 1",
                (team.id,),
            ).fetchone()
            if standing_row:
                result["standing"] = {
                    "rank": standing_row["rank"],
                    "wins": standing_row["wins"],
                    "losses": standing_row["losses"],
                    "draws": standing_row["draws"],
                    "points": standing_row["points"],
                    "form": standing_row["form"],
                    "home_record": f"{standing_row['home_wins']}-{standing_row['home_losses']}",
                    "away_record": f"{standing_row['away_wins']}-{standing_row['away_losses']}",
                    "streak": standing_row["streak"],
                }

            # Power index
            pi_repo = PowerIndexRepo(conn)
            pi_records = pi_repo.get_for_team(team.id)
            if pi_records:
                r = pi_records[0]
                result["power_index"] = {
                    "rating": r.rating,
                    "offensive_rating": r.offensive_rating,
                    "defensive_rating": r.defensive_rating,
                    "rank": r.rank,
                    "season": r.season,
                }

            return result if result else None

    except Exception as e:
        print(f"[db_loader] ESPN enrichment failed for {team_name}/{sport}: {e}")
    return None


def load_player_gamelogs_for_team(team_name: str, sport: str, n: int = 10) -> list[dict]:
    """Load player gamelogs for all players on a team.

    Returns list of dicts with: player_name, position, gamelogs (list of game stats).
    Useful for basketball/hockey player prop analysis and team totals patterns.
    """
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import AthleteRepo, PlayerGamelogRepo, SportRepo, TeamRepo

        with get_db() as conn:
            sr = SportRepo(conn)
            s = sr.get_by_name(sport)
            if not s:
                return []

            tr = TeamRepo(conn)
            team = tr.resolve(team_name, s.id)
            if not team:
                return []

            athlete_repo = AthleteRepo(conn)
            gamelog_repo = PlayerGamelogRepo(conn)

            athletes = athlete_repo.get_by_team(team.id)
            results = []
            for athlete in athletes:
                logs = gamelog_repo.get_last_n(athlete.id, n)
                if not logs:
                    continue
                results.append({
                    "player_name": athlete.name,
                    "position": athlete.position,
                    "status": athlete.status,
                    "gamelogs": [
                        {
                            "date": gl.game_date,
                            "opponent": gl.opponent,
                            "result": gl.result,
                            "stats": json.loads(gl.stats_json) if isinstance(gl.stats_json, str) else gl.stats_json,
                        }
                        for gl in logs
                    ],
                })
            return results

    except Exception as e:
        print(f"[db_loader] Player gamelogs failed for {team_name}/{sport}: {e}")
    return []


def load_sport_specific_cache(sport: str, team_or_player: str) -> dict | None:
    """Load sport-specific cache data. No longer used — all niche sports removed."""
    return None


# ---------------------------------------------------------------------------
# Tipster data loaders (DB-first, R2)
# ---------------------------------------------------------------------------

def load_tipster_picks_from_db(date: str) -> list[dict]:
    """Load tipster picks for a date from DB via TipsterRepo.

    Returns list of dicts with keys: source_site, tipster_name, sport, event,
    home_team, away_team, competition, market, market_type, direction, odds,
    reasoning, accuracy_pct, confidence, stats_cited.

    Falls back to JSON if DB is empty/unavailable.
    """
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import TipsterRepo
        with get_db() as conn:
            repo = TipsterRepo(conn)
            picks = repo.get_picks_by_date(date)
            if picks:
                return [
                    {
                        "source_site": p.source_site, "tipster_name": p.tipster_name,
                        "sport": p.sport, "event": p.event,
                        "home_team": p.home_team, "away_team": p.away_team,
                        "competition": p.competition, "market": p.market,
                        "market_type": p.market_type, "direction": p.direction,
                        "odds": p.odds, "reasoning": p.reasoning,
                        "accuracy_pct": p.accuracy_pct, "confidence": p.confidence,
                        "stats_cited": p.stats_cited,
                    }
                    for p in picks
                ]
    except Exception as e:
        logging.getLogger(__name__).debug("TipsterRepo DB load failed: %s", e)

    # JSON fallback
    for fname in [f"{date}_tipster_consensus.json", f"tipster_aggregation_{date}.json"]:
        path = DATA_DIR / fname
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                tips = data if isinstance(data, list) else data.get("all_picks", data.get("tips", []))
                return tips
            except (json.JSONDecodeError, OSError):
                continue
    return []


def load_tipster_consensus_from_db(date: str) -> list[dict]:
    """Load tipster consensus for a date from DB via TipsterRepo.

    Returns list of dicts with keys: event, sport, competition, home_team,
    away_team, total_tipsters, consensus_market, consensus_direction,
    agreement_pct, statistical_picks, outcome_picks, has_reasoning, tipster_sources.
    """
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import TipsterRepo
        with get_db() as conn:
            repo = TipsterRepo(conn)
            entries = repo.get_consensus_by_date(date)
            if entries:
                return [
                    {
                        "event": c.event, "sport": c.sport,
                        "competition": c.competition, "home_team": c.home_team,
                        "away_team": c.away_team, "total_tipsters": c.total_tipsters,
                        "consensus_market": c.consensus_market,
                        "consensus_direction": c.consensus_direction,
                        "agreement_pct": c.agreement_pct,
                        "statistical_picks": c.statistical_picks,
                        "outcome_picks": c.outcome_picks,
                        "has_reasoning": c.has_reasoning,
                        "tipster_sources": c.tipster_sources,
                        "confidence_adj": c.confidence_adj,
                    }
                    for c in entries
                ]
    except Exception as e:
        logging.getLogger(__name__).debug("TipsterRepo consensus DB load failed: %s", e)
    return []
