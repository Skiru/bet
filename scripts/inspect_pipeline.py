#!/usr/bin/env python3
"""Pipeline state inspector — read-only diagnostic tool for agents.

Replaces complex `python3 -c "..."` one-liners that garble in fish terminal.
Each step handler queries DB (R2 DB-FIRST) and checks JSON files to produce
a structured diagnostic snapshot.

Usage:
    python3 scripts/inspect_pipeline.py --step s1 --date 2026-05-11
    python3 scripts/inspect_pipeline.py --step s3 --date 2026-05-11 --verbose
    python3 scripts/inspect_pipeline.py --step all --date 2026-05-11

Steps: s0 (DB health), s1 (scan), s1e (shortlist), s2 (enrichment),
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

DATA_DIR = ROOT / "betting" / "data"
COUPON_DIR = ROOT / "betting" / "coupons"
CONFIG_DIR = ROOT / "config"


# ---------------------------------------------------------------------------
# DB helper (safe — handles missing DB gracefully)
# ---------------------------------------------------------------------------

def _get_db():
    """Get DB connection, returns None on failure."""
    try:
        from bet.db.connection import get_db
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
    except Exception:
        return default


def _safe_fetchone(conn, sql, params=(), default=None):
    """Execute SQL safely, return single value or default."""
    if conn is None:
        return default
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else default
    except Exception:
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


# ---------------------------------------------------------------------------
# Step Handlers
# ---------------------------------------------------------------------------

def inspect_s0(date: str, out: AgentOutput) -> dict:
    """S0: DB health check — table census and basic integrity."""
    metrics = {}
    conn_ctx = _get_db()
    if conn_ctx is None:
        out.error("Cannot connect to betting.db", recoverable=False)
        return {"db_available": False}

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
                # Try betting_date first, then date(kickoff_utc) for fixtures
                count = _safe_fetchone(conn,
                    f"SELECT COUNT(*) FROM {t} WHERE betting_date = ?", (date,), default=None)
                if count is None and t == "fixtures":
                    count = _safe_fetchone(conn,
                        f"SELECT COUNT(*) FROM {t} WHERE date(kickoff_utc) = ?", (date,), default=0)
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

    out.summary(
        verdict="OK" if metrics.get("tables_total", 0) >= 15 else "PARTIAL",
        metrics=metrics,
    )
    return metrics


def inspect_s1(date: str, out: AgentOutput) -> dict:
    """S1: Scan results — sport distribution, source health, fixture counts."""
    metrics = {}

    # Check files
    metrics["scan_summary_exists"] = _file_exists("betting/data/scan_summary.json", date)
    metrics["market_matrix_exists"] = _file_exists(
        "betting/data/market_matrix_{date}.json", date)

    conn_ctx = _get_db()
    if conn_ctx is None:
        out.warning("DB unavailable — file-only inspection")
        out.summary(verdict="PARTIAL", metrics=metrics)
        return metrics

    with conn_ctx as conn:
        # Scan results by sport
        rows = _safe_query(conn,
            "SELECT sport, COUNT(*) FROM scan_results "
            "WHERE betting_date = ? GROUP BY sport ORDER BY COUNT(*) DESC",
            (date,), default=[])
        sport_dist = {r[0]: r[1] for r in rows}
        metrics["scan_events_by_sport"] = sport_dist
        metrics["total_scan_events"] = sum(sport_dist.values())

        # Fixture count
        metrics["fixtures"] = _safe_fetchone(conn,
            "SELECT COUNT(*) FROM fixtures WHERE date(kickoff_utc) = ?",
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
    if metrics["total_scan_events"] == 0:
        verdict = "FAILED"
    elif len(sport_dist) < 3:
        verdict = "PARTIAL"

    out.summary(verdict=verdict, metrics=metrics)
    return metrics


def inspect_s1e(date: str, out: AgentOutput) -> dict:
    """S1e: Shortlist — candidate count, sport distribution, data quality."""
    metrics = {}

    shortlist = _load_json("betting/data/{date}_s2_shortlist.json", date)
    if shortlist is None:
        out.error(f"Shortlist not found: betting/data/{date}_s2_shortlist.json")
        out.summary(verdict="FAILED", metrics={"shortlist_exists": False})
        return {"shortlist_exists": False}

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
            "event": f"{e.get('home_team', '?')} vs {e.get('away_team', '?')}",
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

    out.summary(verdict=verdict, metrics=metrics)
    return metrics


def inspect_s2(date: str, out: AgentOutput) -> dict:
    """S2/S2.5: Enrichment — team_form coverage vs shortlist teams."""
    metrics = {}

    # Load shortlist to know expected teams
    shortlist = _load_json("betting/data/{date}_s2_shortlist.json", date)
    shortlist_teams = set()
    if shortlist:
        candidates = shortlist if isinstance(shortlist, list) else shortlist.get("candidates", [])
        for c in candidates:
            ev = c[1] if isinstance(c, (list, tuple)) and len(c) >= 2 else c
            if isinstance(ev, dict):
                shortlist_teams.add(ev.get("home_team", ""))
                shortlist_teams.add(ev.get("away_team", ""))
        shortlist_teams.discard("")
    metrics["shortlist_teams_count"] = len(shortlist_teams)

    conn_ctx = _get_db()
    if conn_ctx is None:
        out.warning("DB unavailable")
        out.summary(verdict="PARTIAL", metrics=metrics)
        return metrics

    with conn_ctx as conn:
        # team_form coverage by sport
        rows = _safe_query(conn,
            "SELECT s.name as sport, COUNT(DISTINCT tf.team_name) as teams "
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

    out.summary(
        verdict="OK" if metrics.get("total_teams_with_form", 0) > 0 else "PARTIAL",
        metrics=metrics,
    )
    return metrics


def inspect_s3(date: str, out: AgentOutput) -> dict:
    """S3: Deep stats — analysis quality, data coverage, market depth."""
    metrics = {}

    # Check file
    stats = _load_json("betting/data/{date}_s3_deep_stats.json", date)
    metrics["output_file_exists"] = stats is not None

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
    if not stats:
        verdict = "FAILED"
    elif metrics.get("with_data", 0) == 0:
        verdict = "FAILED"
    elif metrics.get("avg_safety_score", 0) < 4:
        verdict = "PARTIAL"

    out.summary(verdict=verdict, metrics=metrics)
    return metrics


def inspect_s7(date: str, out: AgentOutput) -> dict:
    """S7: Gate results — tier distribution, approval rates."""
    metrics = {}

    gate = _load_json("betting/data/{date}_s7_gate_results.json", date)
    metrics["output_file_exists"] = gate is not None

    if gate:
        gr = gate.get("gate_results", {})
        summary = gate.get("summary", {})

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
    if conn_ctx:
        with conn_ctx as conn:
            db_count = _safe_fetchone(conn,
                "SELECT COUNT(*) FROM gate_results WHERE betting_date = ?",
                (date,), default=0)
            metrics["db_gate_count"] = db_count

    verdict = "OK"
    if not gate:
        verdict = "FAILED"
    elif metrics.get("approved_count", 0) == 0:
        verdict = "PARTIAL"

    out.summary(verdict=verdict, metrics=metrics)
    return metrics


def inspect_s8(date: str, out: AgentOutput) -> dict:
    """S8: Coupons — count, legs, stakes, risk tiers."""
    metrics = {}

    # Check coupon files
    coupon_files = list(COUPON_DIR.glob(f"{date}*.md"))
    metrics["coupon_files"] = len(coupon_files)
    metrics["coupon_filenames"] = [f.name for f in coupon_files]

    # DB check
    conn_ctx = _get_db()
    if conn_ctx:
        with conn_ctx as conn:
            # Coupons
            coupons = _safe_query(conn,
                "SELECT coupon_id, coupon_type, total_odds, stake_pln, status "
                "FROM coupons WHERE coupon_id LIKE ?",
                (f"C-{date.replace('-', '')}%",), default=[])
            metrics["db_coupons"] = len(coupons)
            metrics["coupon_details"] = [
                {
                    "id": r[0], "type": r[1],
                    "odds": r[2], "stake": r[3], "status": r[4],
                }
                for r in coupons
            ]

            # Bets per coupon
            bets_count = _safe_fetchone(conn,
                "SELECT COUNT(*) FROM bets WHERE coupon_id IN "
                "(SELECT id FROM coupons WHERE coupon_id LIKE ?)",
                (f"C-{date.replace('-', '')}%",), default=0)
            metrics["total_legs"] = bets_count

            # Total stake
            total_stake = _safe_fetchone(conn,
                "SELECT SUM(stake_pln) FROM coupons WHERE coupon_id LIKE ?",
                (f"C-{date.replace('-', '')}%",), default=0)
            metrics["total_stake_pln"] = total_stake or 0

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

    out.summary(verdict=verdict, metrics=metrics)
    return metrics


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

STEP_HANDLERS = {
    "s0": ("DB Health Check", inspect_s0),
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
            # Track worst verdict
            # (summary was already printed by handler via step_out)

        out.summary(
            verdict="OK",
            metrics={"steps_inspected": list(STEP_HANDLERS.keys())},
        )
    else:
        label, handler = STEP_HANDLERS[args.step]
        print(f"\n{'='*60}")
        print(f"  {args.step.upper()}: {label} — {args.date}")
        print(f"{'='*60}")
        handler(args.date, out)


if __name__ == "__main__":
    main()
