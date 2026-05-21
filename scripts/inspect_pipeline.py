#!/usr/bin/env python3
"""Pipeline state inspector — read-only diagnostic tool for agents.

Replaces complex `python3 -c "..."` one-liners that garble in fish terminal.
Each step handler queries DB (R2 DB-FIRST) and checks JSON files to produce
a structured diagnostic snapshot.

Usage:
    python3 scripts/inspect_pipeline.py --step s1 --date 2026-05-11
    python3 scripts/inspect_pipeline.py --step s3 --date 2026-05-11 --verbose
    python3 scripts/inspect_pipeline.py --step all --date 2026-05-11

Steps: s0 (settlement/learning readiness + DB health), s1 (scan), s1e (shortlist), s2 (enrichment),
       s3 (deep stats), s7 (gate), s8 (coupons), all

Exit codes: 0 = healthy, 1 = partial/warnings, 2 = critical gaps
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from agent_output import AgentOutput, add_agent_args
from db_data_loader import load_s3_candidates_with_parity
from validate_phase import assess_s0_readiness
from bet.stats.fallback_chains import RICH_COMPLETION_POLICY
from bet.stats.rich_coverage import BASELINE_SOURCE, classify_rich_coverage, summarize_rich_coverage

DATA_DIR = ROOT / "betting" / "data"
COUPON_DIR = ROOT / "betting" / "coupons"
CONFIG_DIR = ROOT / "config"

FOOTBALL_RICH_KEYS = {
    "corners",
    "yellow_cards",
    "red_cards",
    "shots",
    "shots_on_target",
    "fouls",
    "possession",
}


# ---------------------------------------------------------------------------
# DB helper (safe — handles missing DB gracefully)
# ---------------------------------------------------------------------------

def _get_db():
    """Get DB context manager, returns None on import/connection failure."""
    try:
        from bet.db.connection import get_db
        # Return the context manager directly — callers use `with _get_db() as conn:`
        # Test that it can be entered by doing a quick probe
        ctx = get_db()
        conn = ctx.__enter__()
        # Connection works — close it and return a fresh context
        ctx.__exit__(None, None, None)
        return get_db()
    except Exception as e:
        print(f"[inspect] ⚠ DB unavailable: {e}", file=sys.stderr)
        return None


def _safe_query(conn, sql, params=(), default=None):
    """Execute SQL safely, return result or default on error."""
    if conn is None:
        return default
    try:
        return conn.execute(sql, params).fetchall()
    except Exception as e:
        print(f"[inspect] query failed: {e!r} | sql={sql[:80]}", file=sys.stderr)
        return default


def _safe_fetchone(conn, sql, params=(), default=None):
    """Execute SQL safely, return single value or default."""
    if conn is None:
        return default
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else default
    except Exception as e:
        print(f"[inspect] query failed: {e!r} | sql={sql[:80]}", file=sys.stderr)
        return default


def _file_exists(relative_path: str, date: str) -> bool:
    """Check if a data file exists (with {date} substitution)."""
    path = ROOT / relative_path.replace("{date}", date)
    return path.exists()


def _load_json(relative_path: str, date: str) -> dict | list | None:
    """Load JSON file safely, return None on failure."""
    path = ROOT / relative_path.replace("{date}", date)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _normalize_shortlist_events(shortlist) -> list[dict]:
    events: list[dict] = []
    if not shortlist:
        return events

    candidates = shortlist if isinstance(shortlist, list) else shortlist.get("candidates", [])
    for candidate in candidates:
        event = candidate[1] if isinstance(candidate, (list, tuple)) and len(candidate) >= 2 else candidate
        if isinstance(event, dict):
            events.append(event)

    return events


def _collect_shortlist_teams_by_sport(shortlist) -> dict[str, set[str]]:
    teams_by_sport: dict[str, set[str]] = {}
    for event in _normalize_shortlist_events(shortlist):
        sport = event.get("sport", "")
        if not sport:
            continue
        for team_key in ("home_team", "away_team"):
            team_name = event.get(team_key) or event.get(team_key.replace("_team", ""), "")
            if team_name:
                teams_by_sport.setdefault(sport, set()).add(team_name)

    return teams_by_sport


def _build_count_parity(
    *,
    json_counts: dict[str, int] | None,
    db_counts: dict[str, int] | None,
    keys: tuple[str, ...],
    json_available: bool,
    db_available: bool,
) -> dict:
    normalized_json = {key: int((json_counts or {}).get(key, 0) or 0) for key in keys}
    normalized_db = {key: int((db_counts or {}).get(key, 0) or 0) for key in keys}

    if json_available and db_available:
        status = "exact" if normalized_json == normalized_db else "mismatch"
    elif json_available and any(normalized_json.values()):
        status = "json_only"
    elif db_available and any(normalized_db.values()):
        status = "db_only"
    else:
        status = "missing"

    return {
        "status": status,
        "json_available": json_available,
        "db_available": db_available,
        "json_counts": normalized_json,
        "db_counts": normalized_db,
        "mismatched_keys": [key for key in keys if normalized_json[key] != normalized_db[key]],
    }


def _summarize_scraper_runs(conn, date: str) -> dict:
    success_by_sport = {
        row[0]: row[1]
        for row in _safe_query(
            conn,
            "SELECT sport, COUNT(*) FROM scraper_runs "
            "WHERE LOWER(status) = 'success' AND DATE(COALESCE(finished_at, started_at)) = ? "
            "GROUP BY sport ORDER BY sport",
            (date,),
            default=[],
        )
    }
    failed_by_sport = {
        row[0]: row[1]
        for row in _safe_query(
            conn,
            "SELECT sport, COUNT(*) FROM scraper_runs "
            "WHERE LOWER(status) = 'failed' AND DATE(COALESCE(finished_at, started_at)) = ? "
            "GROUP BY sport ORDER BY sport",
            (date,),
            default=[],
        )
    }

    warehouse_rows = _safe_query(
        conn,
        "SELECT COALESCE(SUM(records_scraped), 0), COALESCE(SUM(records_inserted), 0), COALESCE(SUM(records_updated), 0) "
        "FROM scraper_runs WHERE DATE(COALESCE(finished_at, started_at)) = ?",
        (date,),
        default=None,
    )
    warehouse_metrics_available = bool(warehouse_rows)
    if warehouse_rows:
        records_scraped, records_inserted, records_updated = warehouse_rows[0]
    else:
        records_scraped = records_inserted = records_updated = 0

    success_runs = sum(success_by_sport.values())
    failed_runs = sum(failed_by_sport.values())
    observed_changes = int(records_scraped or 0) + int(records_inserted or 0) + int(records_updated or 0)

    return {
        "success_runs": success_runs,
        "failed_runs": failed_runs,
        "success_by_sport": success_by_sport,
        "failed_by_sport": failed_by_sport,
        "records_scraped": int(records_scraped or 0),
        "records_inserted": int(records_inserted or 0),
        "records_updated": int(records_updated or 0),
        "warehouse_metrics_available": warehouse_metrics_available,
        "warehouse_changes_observed": observed_changes,
        "warehouse_improved": bool(success_runs and (observed_changes > 0 or not warehouse_metrics_available)),
    }


def _gate_bucket_counts_from_json(payload: dict | None) -> dict[str, int]:
    gate_results = payload.get("gate_results", {}) if isinstance(payload, dict) else {}
    return {
        "approved": len(gate_results.get("approved", []) or []),
        "extended_pool": len(gate_results.get("extended_pool", []) or []),
        "rejected": len(gate_results.get("rejected", []) or []),
    }


def _gate_bucket_counts_from_db(conn, date: str) -> tuple[dict[str, int], bool]:
    rows = _safe_query(
        conn,
        "SELECT UPPER(COALESCE(status, '')), COUNT(*) FROM gate_results "
        "WHERE betting_date = ? GROUP BY UPPER(COALESCE(status, ''))",
        (date,),
        default=None,
    )
    if rows is None:
        return {}, False

    counts = {"approved": 0, "extended_pool": 0, "rejected": 0}
    status_map = {
        "APPROVED": "approved",
        "EXTENDED": "extended_pool",
        "EXTENDED_POOL": "extended_pool",
        "REJECTED": "rejected",
    }
    for status, count in rows:
        bucket = status_map.get(str(status or "").strip().upper())
        if bucket:
            counts[bucket] += int(count or 0)

    return counts, True


def _coupon_json_snapshot(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {
            "core_coupons": 0,
            "combos": 0,
            "singles": 0,
            "persisted_coupons": 0,
            "persisted_legs": 0,
        }

    core = list(payload.get("core_coupons", []) or [])
    combos = list(payload.get("combos", []) or [])
    singles = list(payload.get("singles", []) or [])
    persisted = core + combos + singles

    return {
        "core_coupons": len(core),
        "combos": len(combos),
        "singles": len(singles),
        "persisted_coupons": len(persisted),
        "persisted_legs": sum(len(coupon.get("legs", []) or []) for coupon in persisted),
    }


def _coupon_db_snapshot(conn, date: str) -> tuple[list[tuple], bool]:
    rows = _safe_query(
        conn,
        "SELECT id, coupon_id, coupon_type, total_odds, stake_pln, status "
        "FROM coupons WHERE coupon_id LIKE ? ORDER BY id",
        (f"CP-{date}%",),
        default=None,
    )
    if rows:
        return rows, True

    fallback_rows = _safe_query(
        conn,
        "SELECT id, coupon_id, coupon_type, total_odds, stake_pln, status "
        "FROM coupons WHERE substr(COALESCE(placed_at, created_at, ''), 1, 10) = ? "
        "OR substr(created_at, 1, 10) = ? ORDER BY id",
        (date, date),
        default=None,
    )
    if fallback_rows is None:
        return [], False
    return fallback_rows, True


# ---------------------------------------------------------------------------
# Step Handlers
# ---------------------------------------------------------------------------

def inspect_s0(date: str, out: AgentOutput) -> dict:
    """S0: previous-day settlement/learning readiness plus DB health census."""
    metrics = {
        "session_readiness": assess_s0_readiness(date, db_getter=_get_db, data_dir=DATA_DIR)
    }
    conn_ctx = _get_db()
    if conn_ctx is None:
        out.error("Cannot connect to betting.db", recoverable=False)
        metrics["db_available"] = False
        metrics["_verdict"] = "FAILED"
        out.summary(verdict="FAILED", metrics=metrics)
        return metrics

    with conn_ctx as conn:
        # Table census
        tables = _safe_query(conn,
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
            default=[])
        table_names = [r[0] for r in tables]
        metrics["tables_total"] = len(table_names)

        # Row counts for key tables
        key_tables = [
            "sports", "teams", "competitions", "fixtures", "team_form",
            "analysis_results", "gate_results", "coupons", "bets",
            "scan_results", "source_health", "standings", "league_profiles",
            "odds_history", "pipeline_runs",
        ]
        table_counts = {}
        for t in key_tables:
            if t in table_names:
                count = _safe_fetchone(conn, f"SELECT COUNT(*) FROM {t}", default=0)
                table_counts[t] = count
            else:
                table_counts[t] = "MISSING"
        metrics["table_counts"] = table_counts

        # Date-specific counts
        date_counts = {}
        for t in ["fixtures", "scan_results", "analysis_results", "gate_results"]:
            if t in table_names:
                if t == "fixtures":
                    count = _safe_fetchone(conn,
                        f"SELECT COUNT(*) FROM {t} WHERE date(kickoff) = ?", (date,), default=0)
                else:
                    count = _safe_fetchone(conn,
                        f"SELECT COUNT(*) FROM {t} WHERE betting_date = ?", (date,), default=0)
                date_counts[t] = count or 0
        metrics["date_counts"] = date_counts

        # Source health
        failing = _safe_query(conn,
            "SELECT source_name, consecutive_failures FROM source_health "
            "WHERE consecutive_failures > 2 ORDER BY consecutive_failures DESC LIMIT 5",
            default=[])
        metrics["failing_sources"] = [
            {"source": r[0], "consecutive_failures": r[1]} for r in failing
        ]

    if not metrics["session_readiness"].get("ready", True):
        verdict = "FAILED"
    else:
        verdict = "OK" if metrics.get("tables_total", 0) >= 15 else "PARTIAL"
    metrics["_verdict"] = verdict
    out.summary(verdict=verdict, metrics=metrics)
    return metrics


def inspect_s1(date: str, out: AgentOutput) -> dict:
    """S1: Scan results — sport distribution, source health, fixture counts."""
    metrics = {}

    # Check files
    metrics["discovery_events_exists"] = _file_exists(f"betting/data/{date}_s1_events.json", date)
    metrics["market_matrix_exists"] = _file_exists(
        "betting/data/market_matrix_{date}.json", date)

    conn_ctx = _get_db()
    if conn_ctx is None:
        out.warning("DB unavailable — file-only inspection")
        metrics["_verdict"] = "PARTIAL"
        out.summary(verdict="PARTIAL", metrics=metrics)
        return metrics

    with conn_ctx as conn:
        # Scan results by sport
        rows = _safe_query(conn,
            "SELECT sport, COUNT(*) FROM scan_results "
            "WHERE betting_date = ? GROUP BY sport ORDER BY COUNT(*) DESC",
            (date,), default=[])
        sport_dist = {r[0]: r[1] for r in rows}
        metrics["discovery_events_by_sport"] = sport_dist
        metrics["total_discovery_events"] = sum(sport_dist.values())

        # Fixture count
        metrics["fixtures"] = _safe_fetchone(conn,
            "SELECT COUNT(*) FROM fixtures WHERE date(kickoff) = ?",
            (date,), default=0)

        # Scan run stats
        runs = _safe_query(conn,
            "SELECT sport, events_found, sources_ok, sources_failed "
            "FROM scan_run_stats WHERE betting_date = ? ORDER BY sport",
            (date,), default=[])
        metrics["scan_runs"] = [
            {"sport": r[0], "events": r[1], "ok": r[2], "failed": r[3]}
            for r in runs
        ]

        # Source health top failures
        failing = _safe_query(conn,
            "SELECT source_name, total_failures, total_requests, "
            "ROUND(total_failures*100.0/MAX(total_requests,1),1) "
            "FROM source_health WHERE total_failures > 0 "
            "ORDER BY total_failures DESC LIMIT 5",
            default=[])
        metrics["top_failing_sources"] = [
            {"source": r[0], "failures": r[1], "requests": r[2], "pct": r[3]}
            for r in failing
        ]

    verdict = "OK"
    if metrics["total_discovery_events"] == 0:
        verdict = "FAILED"
    elif len(sport_dist) < 3:
        verdict = "PARTIAL"

    metrics["_verdict"] = verdict
    out.summary(verdict=verdict, metrics=metrics)
    return metrics


def inspect_s1e(date: str, out: AgentOutput) -> dict:
    """S1e: Shortlist — candidate count, sport distribution, data quality."""
    metrics = {}

    shortlist = _load_json("betting/data/{date}_s2_shortlist.json", date)
    if shortlist is None:
        out.error(f"Shortlist not found: betting/data/{date}_s2_shortlist.json")
        out.summary(verdict="FAILED", metrics={"shortlist_exists": False})
        return {"shortlist_exists": False, "_verdict": "FAILED"}

    candidates = shortlist if isinstance(shortlist, list) else shortlist.get("candidates", [])

    # Handle candidates format: can be [(score, event), ...] or [event, ...]
    events = []
    for c in candidates:
        if isinstance(c, (list, tuple)) and len(c) >= 2:
            events.append(c[1] if isinstance(c[1], dict) else c)
        elif isinstance(c, dict):
            events.append(c)

    metrics["total_candidates"] = len(events)
    metrics["sport_distribution"] = dict(Counter(
        e.get("sport", "unknown") for e in events
    ))

    # Data tier distribution
    tiers = Counter(e.get("data_tier", "unknown") for e in events)
    metrics["data_tier_distribution"] = dict(tiers)

    # Top 5 candidates
    metrics["top_5"] = [
        {
            "event": f"{e.get('home_team') or e.get('home', '?')} vs {e.get('away_team') or e.get('away', '?')}",
            "sport": e.get("sport", "?"),
            "competition": e.get("competition", "?"),
        }
        for e in events[:5]
    ]

    verdict = "OK"
    if len(events) == 0:
        verdict = "FAILED"
    elif len(events) < 20:
        verdict = "PARTIAL"

    metrics["_verdict"] = verdict
    out.summary(verdict=verdict, metrics=metrics)
    return metrics


def inspect_s2(date: str, out: AgentOutput) -> dict:
    """S2/S2.5: Enrichment — team_form coverage vs shortlist teams."""
    metrics = {}

    # Load shortlist to know expected teams
    shortlist = _load_json("betting/data/{date}_s2_shortlist.json", date)
    shortlist_teams_by_sport = _collect_shortlist_teams_by_sport(shortlist)
    metrics["shortlist_teams_count"] = sum(len(teams) for teams in shortlist_teams_by_sport.values())
    metrics["shortlist_teams_by_sport"] = {
        sport: len(teams) for sport, teams in sorted(shortlist_teams_by_sport.items())
    }

    conn_ctx = _get_db()
    if conn_ctx is None:
        out.warning("DB unavailable")
        metrics["_verdict"] = "PARTIAL"
        out.summary(verdict="PARTIAL", metrics=metrics)
        return metrics

    with conn_ctx as conn:
        # team_form coverage by sport
        rows = _safe_query(conn,
            "SELECT s.name as sport, COUNT(DISTINCT tf.team_id) as teams "
            "FROM team_form tf JOIN sports s ON tf.sport_id = s.id "
            "GROUP BY s.name ORDER BY teams DESC",
            default=[])
        metrics["team_form_by_sport"] = {r[0]: r[1] for r in rows}
        metrics["total_teams_with_form"] = sum(r[1] for r in rows)

        # Unique stat keys available
        stat_keys = _safe_query(conn,
            "SELECT stat_key, COUNT(*) FROM team_form GROUP BY stat_key ORDER BY COUNT(*) DESC LIMIT 10",
            default=[])
        metrics["top_stat_keys"] = {r[0]: r[1] for r in stat_keys}

        scraper_summary = _summarize_scraper_runs(conn, date)
        metrics["scraper_success"] = scraper_summary

        rich_completion_by_sport = {}
        all_team_details = []
        bucket_counts = Counter()
        tracked_sports = sorted(set(shortlist_teams_by_sport) | set(RICH_COMPLETION_POLICY))
        for sport in tracked_sports:
            policy = RICH_COMPLETION_POLICY.get(sport)
            sport_id = _safe_fetchone(conn, "SELECT id FROM sports WHERE name = ?", (sport,), default=None)
            team_names = sorted(shortlist_teams_by_sport.get(sport, set()))
            team_details = []
            if sport_id is not None:
                allowed_sources = None
                required_keys = []
                baseline_sources = None
                if policy:
                    allowed_sources = {policy["canonical_source"], *policy["supporting_sources"]}
                    required_keys = policy["required_rich_keys"]
                    baseline_sources = policy.get("baseline_sources")
                elif sport == "football":
                    required_keys = sorted(FOOTBALL_RICH_KEYS)
                    baseline_sources = {BASELINE_SOURCE}

                for team_name in team_names:
                    rows = _safe_query(
                        conn,
                        "SELECT tf.stat_key, tf.source "
                        "FROM team_form tf "
                        "JOIN teams t ON t.id = tf.team_id "
                        "WHERE t.name = ? AND tf.sport_id = ?",
                        (team_name, sport_id),
                        default=[],
                    )
                    if required_keys:
                        detail = classify_rich_coverage(
                            rows,
                            required_keys,
                            allowed_sources,
                            baseline_sources=baseline_sources,
                        )
                    else:
                        detail = {
                            "bucket": "partial" if rows else "no_data",
                            "eligible": bool(rows),
                            "stat_keys": sorted({str(row[0]) for row in rows if row and row[0]}),
                            "sources": sorted({str(row[1]) for row in rows if row and row[1]}),
                            "rich_keys_found": [],
                            "missing_rich_keys": [],
                        }
                    detail["team"] = team_name
                    detail["sport"] = sport
                    detail["team_form_rows"] = len(rows)
                    team_details.append(detail)
                    all_team_details.append(detail)
                    bucket_counts[detail["bucket"]] += 1

            summary = summarize_rich_coverage(team_details)
            rich_completion_by_sport[sport] = summary
            metrics[f"{sport}_rich_eligible"] = summary["eligible"]
            metrics[f"{sport}_completed"] = summary["rich"]
            metrics[f"{sport}_still_missing_rich"] = summary["eligible"] + summary["no_data"]
            metrics[f"{sport}_team_completeness"] = summary["team_details"]

        metrics["rich_completion_by_sport"] = rich_completion_by_sport

    teams_with_any_data = sum(1 for detail in all_team_details if detail.get("team_form_rows", 0) > 0)
    no_data_details = [detail for detail in all_team_details if detail.get("bucket") == "no_data"]
    still_missing_details = [detail for detail in all_team_details if detail.get("bucket") != "rich"]
    total_shortlist_teams = metrics["shortlist_teams_count"]

    metrics["shortlist_bucket_counts"] = {
        "rich": bucket_counts.get("rich", 0),
        "baseline_only": bucket_counts.get("baseline_only", 0),
        "partial": bucket_counts.get("partial", 0),
        "no_data": bucket_counts.get("no_data", 0),
    }
    metrics["shortlist_team_details"] = all_team_details
    metrics["still_missing_shortlist_teams"] = still_missing_details
    metrics["no_data_shortlist_teams"] = no_data_details
    metrics["team_form_readiness"] = {
        "teams_with_any_data": teams_with_any_data,
        "teams_missing_any_data": max(total_shortlist_teams - teams_with_any_data, 0),
        "coverage_rate": round((teams_with_any_data / total_shortlist_teams) * 100, 1) if total_shortlist_teams else 0.0,
    }
    metrics["s3_readiness"] = {
        "ready": bool(total_shortlist_teams) and not no_data_details,
        "ready_teams": total_shortlist_teams - len(no_data_details),
        "blocked_teams": len(no_data_details),
    }
    metrics["readiness_signals"] = {
        "warehouse_improved": metrics["scraper_success"]["warehouse_improved"],
        "s3_ready": metrics["s3_readiness"]["ready"],
        "rich_ready": bool(total_shortlist_teams) and metrics["shortlist_bucket_counts"]["rich"] == total_shortlist_teams,
    }

    if total_shortlist_teams and metrics["s3_readiness"]["ready"]:
        verdict = "OK"
    elif metrics.get("total_teams_with_form", 0) > 0 or metrics["scraper_success"]["success_runs"] > 0:
        verdict = "PARTIAL"
    else:
        verdict = "FAILED"

    metrics["_verdict"] = verdict
    out.summary(verdict=verdict, metrics=metrics)
    return metrics


def inspect_s3(date: str, out: AgentOutput) -> dict:
    """S3: Deep stats — analysis quality, data coverage, market depth."""
    metrics = {}

    # Check file
    stats = _load_json("betting/data/{date}_s3_deep_stats.json", date)
    metrics["output_file_exists"] = stats is not None

    _, parity_metadata = load_s3_candidates_with_parity(date)
    metrics["canonical_candidate_count"] = parity_metadata.get("counts", {}).get("canonical", 0)
    metrics["db_json_parity"] = {
        "source": parity_metadata.get("source", "none"),
        **parity_metadata.get("parity", {}),
    }
    if parity_metadata.get("blocking_error"):
        metrics["parity_blocking_error"] = parity_metadata["blocking_error"]

    if stats:
        analyses = stats.get("analyses", [])
        metrics["total_candidates"] = stats.get("total_candidates", len(analyses))
        metrics["with_data"] = stats.get("candidates_with_data", 0)
        metrics["without_data"] = stats.get("candidates_without_data", 0)

        # Safety score distribution
        scores = [a.get("best_safety_score", 0) for a in analyses if a.get("has_data")]
        if scores:
            metrics["avg_safety_score"] = round(sum(scores) / len(scores), 2)
            metrics["max_safety_score"] = round(max(scores), 2)
            metrics["min_safety_score"] = round(min(scores), 2)
            metrics["scores_above_6"] = sum(1 for s in scores if s >= 6)
            metrics["scores_above_7"] = sum(1 for s in scores if s >= 7)

        # Data quality distribution
        dq_labels = Counter(
            a.get("data_quality", {}).get("label", "unknown")
            for a in analyses
        )
        metrics["data_quality_distribution"] = dict(dq_labels)

        # Markets evaluated per candidate
        market_counts = [a.get("markets_evaluated", 0) for a in analyses if a.get("has_data")]
        if market_counts:
            metrics["avg_markets_evaluated"] = round(sum(market_counts) / len(market_counts), 1)

        # Sport distribution
        sport_dist = Counter(a.get("sport", "unknown") for a in analyses)
        metrics["sport_distribution"] = dict(sport_dist)

    # Also check DB
    conn_ctx = _get_db()
    if conn_ctx:
        with conn_ctx as conn:
            db_count = _safe_fetchone(conn,
                "SELECT COUNT(*) FROM analysis_results WHERE betting_date = ?",
                (date,), default=0)
            metrics["db_analysis_count"] = db_count

    verdict = "OK"
    if not stats and metrics["canonical_candidate_count"] == 0:
        verdict = "FAILED"
    elif stats and metrics.get("with_data", 0) == 0:
        verdict = "FAILED"
    elif metrics["db_json_parity"].get("status") == "mismatch":
        verdict = "PARTIAL"
    elif stats and metrics.get("avg_safety_score", 0) < 4:
        verdict = "PARTIAL"
    elif not stats and metrics["canonical_candidate_count"] > 0:
        verdict = "PARTIAL"

    metrics["_verdict"] = verdict
    out.summary(verdict=verdict, metrics=metrics)
    return metrics


def inspect_s7(date: str, out: AgentOutput) -> dict:
    """S7: Gate results — tier distribution, approval rates."""
    metrics = {}

    gate = _load_json("betting/data/{date}_s7_gate_results.json", date)
    metrics["output_file_exists"] = gate is not None
    json_bucket_counts = _gate_bucket_counts_from_json(gate)
    metrics["json_bucket_counts"] = json_bucket_counts

    if gate:
        gr = gate.get("gate_results", {})

        metrics["approved_count"] = len(gr.get("approved", []))
        metrics["extended_count"] = len(gr.get("extended_pool", []))
        metrics["rejected_count"] = len(gr.get("rejected", []))
        metrics["total_evaluated"] = (
            metrics["approved_count"] + metrics["extended_count"] + metrics["rejected_count"]
        )

        # Tier distribution within approved
        tiers = Counter()
        for pick in gr.get("approved", []):
            status = pick.get("status", pick.get("gate_status", "unknown"))
            tiers[status] += 1
        metrics["tier_distribution"] = dict(tiers)

        # Sport diversity in approved
        sports = Counter(
            pick.get("sport", "unknown") for pick in gr.get("approved", [])
        )
        metrics["approved_sport_distribution"] = dict(sports)

        # Gate score stats
        scores = [
            pick.get("gate_score", 0) for pick in gr.get("approved", [])
        ]
        if scores:
            metrics["avg_gate_score"] = round(sum(scores) / len(scores), 1)
            metrics["min_gate_score"] = min(scores)

    # DB check
    conn_ctx = _get_db()
    db_bucket_counts = {"approved": 0, "extended_pool": 0, "rejected": 0}
    db_available = False
    if conn_ctx:
        with conn_ctx as conn:
            db_count = _safe_fetchone(conn,
                "SELECT COUNT(*) FROM gate_results WHERE betting_date = ?",
                (date,), default=0)
            metrics["db_gate_count"] = db_count
            db_bucket_counts, db_available = _gate_bucket_counts_from_db(conn, date)

    metrics["db_bucket_counts"] = db_bucket_counts
    metrics["db_json_parity"] = _build_count_parity(
        json_counts=json_bucket_counts,
        db_counts=db_bucket_counts,
        keys=("approved", "extended_pool", "rejected"),
        json_available=gate is not None,
        db_available=db_available,
    )

    verdict = "OK"
    if not gate and not any(db_bucket_counts.values()):
        verdict = "FAILED"
    elif metrics.get("approved_count", 0) == 0:
        verdict = "PARTIAL"
    elif metrics["db_json_parity"]["status"] == "mismatch":
        verdict = "PARTIAL"

    metrics["_verdict"] = verdict
    out.summary(verdict=verdict, metrics=metrics)
    return metrics


def inspect_s8(date: str, out: AgentOutput) -> dict:
    """S8: Coupons — count, legs, stakes, risk tiers."""
    metrics = {}

    # Check coupon files
    coupon_files = list(COUPON_DIR.glob(f"{date}*.md"))
    metrics["coupon_files"] = len(coupon_files)
    metrics["coupon_filenames"] = [f.name for f in coupon_files]
    coupon_json = _load_json("betting/coupons/{date}.json", date)
    metrics["coupon_json_exists"] = coupon_json is not None
    metrics["json_coupon_counts"] = _coupon_json_snapshot(coupon_json)

    # DB check
    conn_ctx = _get_db()
    db_available = False
    if conn_ctx:
        with conn_ctx as conn:
            coupons, db_available = _coupon_db_snapshot(conn, date)
            metrics["db_coupons"] = len(coupons)
            metrics["coupon_details"] = [
                {
                    "id": r[1], "type": r[2],
                    "odds": r[3], "stake": r[4], "status": r[5],
                }
                for r in coupons
            ]
            metrics["db_coupon_type_counts"] = dict(Counter(
                (r[2] or "unknown") for r in coupons
            ))

            # Bets per coupon
            coupon_ids = [r[0] for r in coupons]
            if coupon_ids:
                placeholders = ",".join("?" for _ in coupon_ids)
                bets_count = _safe_fetchone(conn,
                    f"SELECT COUNT(*) FROM bets WHERE coupon_id IN ({placeholders})",
                    tuple(coupon_ids), default=0)
            else:
                bets_count = 0
            metrics["total_legs"] = bets_count

            # Total stake
            total_stake = sum(float(r[4] or 0) for r in coupons)
            metrics["total_stake_pln"] = total_stake or 0

    metrics["db_json_parity"] = _build_count_parity(
        json_counts={
            "persisted_coupons": metrics["json_coupon_counts"]["persisted_coupons"],
            "persisted_legs": metrics["json_coupon_counts"]["persisted_legs"],
        },
        db_counts={
            "persisted_coupons": metrics.get("db_coupons", 0),
            "persisted_legs": metrics.get("total_legs", 0),
        },
        keys=("persisted_coupons", "persisted_legs"),
        json_available=coupon_json is not None,
        db_available=db_available,
    )

    # Bankroll check
    config = _load_json("config/betting_config.json", date)
    if config:
        bankroll = config.get("bankroll", 0)
        metrics["bankroll"] = bankroll
        if bankroll > 0 and metrics.get("total_stake_pln", 0) > 0:
            metrics["stake_pct_of_bankroll"] = round(
                metrics["total_stake_pln"] / bankroll * 100, 1
            )

    verdict = "OK"
    if metrics.get("coupon_files", 0) == 0 and metrics.get("db_coupons", 0) == 0:
        verdict = "FAILED"
    elif metrics.get("total_legs", 0) == 0:
        verdict = "PARTIAL"
    elif metrics["db_json_parity"]["status"] == "mismatch":
        verdict = "PARTIAL"

    metrics["_verdict"] = verdict
    out.summary(verdict=verdict, metrics=metrics)
    return metrics


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

STEP_HANDLERS = {
    "s0": ("Settlement/Learning Readiness + DB Health", inspect_s0),
    "s1": ("Scan Results", inspect_s1),
    "s1e": ("Shortlist", inspect_s1e),
    "s2": ("Enrichment", inspect_s2),
    "s3": ("Deep Stats", inspect_s3),
    "s7": ("Gate Results", inspect_s7),
    "s8": ("Coupons", inspect_s8),
}


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline state inspector — read-only diagnostic tool"
    )
    parser.add_argument(
        "--step",
        choices=list(STEP_HANDLERS.keys()) + ["all"],
        required=True,
        help="Pipeline step to inspect (or 'all')",
    )
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Betting day YYYY-MM-DD (default: today)",
    )
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput("inspect", verbose=args.verbose, stop_on_error=args.stop_on_error)

    verdict_rank = {"OK": 0, "PARTIAL": 1, "FAILED": 2}

    if args.step == "all":
        all_metrics = {}
        worst_verdict = "OK"
        for step_id, (label, handler) in STEP_HANDLERS.items():
            print(f"\n{'='*60}")
            print(f"  {step_id.upper()}: {label}")
            print(f"{'='*60}")
            step_out = AgentOutput(
                f"inspect_{step_id}", verbose=args.verbose,
                stop_on_error=args.stop_on_error,
            )
            m = handler(args.date, step_out)
            all_metrics[step_id] = m
            # Track worst verdict from handler's output
            step_verdict = m.get("_verdict", "OK") if isinstance(m, dict) else "OK"
            if verdict_rank.get(step_verdict, 0) > verdict_rank[worst_verdict]:
                worst_verdict = step_verdict

        out.summary(
            verdict=worst_verdict,
            metrics={"steps_inspected": list(STEP_HANDLERS.keys()), **all_metrics},
        )
        # Exit code reflects overall health
        if worst_verdict == "FAILED":
            sys.exit(2)
        elif worst_verdict == "PARTIAL":
            sys.exit(1)
    else:
        label, handler = STEP_HANDLERS[args.step]
        print(f"\n{'='*60}")
        print(f"  {args.step.upper()}: {label} — {args.date}")
        print(f"{'='*60}")
        m = handler(args.date, out)
        # Exit code reflects step health
        step_verdict = m.get("_verdict", "OK") if isinstance(m, dict) else "OK"
        if step_verdict == "FAILED":
            sys.exit(2)
        elif step_verdict == "PARTIAL":
            sys.exit(1)


if __name__ == "__main__":
    main()
