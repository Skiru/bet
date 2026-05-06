#!/usr/bin/env python3
"""Pipeline Orchestrator — fully automated end-to-end betting pipeline.

Runs ALL methodology steps (S0–S10) without human intervention:
S0: Settle + learn from Betclic history
S1: Full 14-sport Playwright scan + API fixture discovery
S1b: Cross-validation odds
S1c: Weather data
S1d: Market matrix generation
S1e: Ranked shortlist building
S3: Deep statistical analysis (L10/H2H/L5 per candidate)
S7: 17-point gate checks
S8: Core portfolio + combo menu coupon construction
S9: Coupon validation
S10: Final summary + artifacts

Usage:
    python3 scripts/pipeline_orchestrator.py --date 2026-05-01
    python3 scripts/pipeline_orchestrator.py --date 2026-05-01 --resume
    python3 scripts/pipeline_orchestrator.py --date 2026-05-01 --skip-scan
    python3 scripts/pipeline_orchestrator.py --date 2026-05-01 --top 50
    python3 scripts/pipeline_orchestrator.py --status
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).parent
ROOT_DIR = SCRIPTS_DIR.parent
DATA_DIR = ROOT_DIR / "betting" / "data"
COUPON_DIR = ROOT_DIR / "betting" / "coupons"
STATE_DIR = DATA_DIR / "pipeline_state"
CONFIG_PATH = ROOT_DIR / "config" / "betting_config.json"

# ---------------------------------------------------------------------------
# Module imports (dual-path for direct and package execution)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from scripts.deep_stats_report import generate_deep_stats
except ImportError:
    from deep_stats_report import generate_deep_stats

try:
    from scripts.gate_checker import (
        run_gate,
        _normalise_s3_to_gate_input,
        _write_json as write_gate_json,
        _write_markdown as write_gate_md,
    )
except ImportError:
    from gate_checker import (
        run_gate,
        _normalise_s3_to_gate_input,
        _write_json as write_gate_json,
        _write_markdown as write_gate_md,
    )

try:
    from scripts.coupon_builder import (
        build_coupons,
        write_coupon_markdown,
        write_coupon_json,
        load_config as load_coupon_config,
    )
except ImportError:
    from coupon_builder import (
        build_coupons,
        write_coupon_markdown,
        write_coupon_json,
        load_config as load_coupon_config,
    )

# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

# Per-step timeout in seconds (prevents hanging on slow sources)
STEP_TIMEOUTS = {
    "s0_settle": 180,      # 3 min
    "s1_scan": 1800,       # 30 min (Playwright scan ONLY — no enrichment)
    "s1_ingest": 180,      # 3 min (ingest scan data into stats cache)
    "s1a_discover": 300,   # 5 min
    "s1b_parallel": 600,   # 10 min (odds + weather + tipsters in parallel)
    "s1c_aggregate": 120,  # 2 min
    "s1d_matrix": 120,     # 2 min
    "s1e_shortlist": 120,  # 2 min
    "s2_tipster": 60,      # 1 min (data loading only)
    "s3_deep_stats": 600,  # 10 min (8-worker parallel analysis)
    "s4_odds_eval": 120,   # 2 min
    "s5_context": 60,      # 1 min
    "s6_upset_risk": 120,  # 2 min
    "s7_gate": 300,        # 5 min
    "s8_coupons": 120,     # 2 min
    "s9_validate": 60,     # 1 min
    "s10_summary": 30,     # 30 sec
}
DEFAULT_STEP_TIMEOUT = 600  # 10 min fallback

PIPELINE_STEPS = [
    {
        "id": "s0_settle",
        "name": "S0: Settle + Learn from History",
        "description": "Settle previous day (if applicable) + Run Betclic history analysis (§0.2 MANDATORY)",
        "commands": [
            "python3 scripts/settle_on_finish.py --betting-day {prev_date} --no-poll",
            "python3 scripts/analyze_betclic_learning.py",
        ],
        "outputs": ["betting/data/betclic_learning_summary.json"],
        "critical": True,
    },
    {
        "id": "s1_scan",
        "name": "S1: Playwright Event Scan",
        "description": "Playwright scan of 232+ seed URLs with deep-link discovery (scan ONLY — enrichment is separate)",
        "python_step": "scan_events",
        "outputs": ["betting/data/scan_summary.json"],
        "critical": True,
        "agent_review_required": "bet-scanner",
        "agent_task": "Verify 14-sport coverage, cross-validate fixtures ≥2 sources, check deep-link discovery yield, flag source failures, ensure ≥50 unique events",
    },
    {
        "id": "s1_ingest",
        "name": "S1-ingest: Ingest Scan Stats + Analysis Pool",
        "description": "Ingest Playwright HTML data into stats cache + generate analysis pool",
        "commands": [
            "python3 scripts/ingest_scan_stats.py",
            "python3 scripts/deep_analysis_pool.py --date {date}",
        ],
        "outputs": [],
        "critical": False,
    },
    {
        "id": "s1a_discover",
        "name": "S1a: Discover Fixtures + API Stats",
        "description": "API fixture discovery + stats enrichment (run independently of scan)",
        "commands": [
            "python3 scripts/discover_fixtures.py --date {date}",
            "python3 scripts/fetch_api_stats.py --date {date}",
        ],
        "outputs": [],
        "critical": False,
    },
    {
        "id": "s1b_parallel",
        "name": "S1b: Odds + Weather + Tipsters (PARALLEL)",
        "description": "Fetch odds, weather, and tipster data concurrently",
        "python_step": "parallel_enrichment",
        "critical": False,
    },
    {
        "id": "s1c_aggregate",
        "name": "S1c: Aggregate + Deep Analysis Pool",
        "description": "Aggregate scan results + generate analysis candidate pool",
        "commands": [
            "python3 scripts/aggregate_and_select.py --date {date}",
        ],
        "outputs": [],
        "critical": False,
    },
    {
        "id": "s1d_matrix",
        "name": "S1d: Market Matrix",
        "description": "Generate consolidated market matrix with tipster data",
        "commands": ["python3 scripts/generate_market_matrix.py --date {date} --stats-first"],
        "outputs": [],
        "critical": False,
    },
    {
        "id": "s1e_shortlist",
        "name": "S1e: Build Ranked Shortlist",
        "description": "Auto-rank events by data quality and competition importance",
        "commands": ["python3 scripts/build_shortlist.py --date {date} --stats-first"],
        "outputs": [],
        "critical": False,
        "agent_review_required": "bet-scanner",
        "agent_task": "Review shortlist for sport diversity (≥8 sports), KEY sport coverage (≥60% Football/Tennis/Basketball/Volleyball), verify 50-100 candidates, flag missing major leagues",
    },
    {
        "id": "s2_tipster",
        "name": "S2: Tipster Cross-Reference",
        "description": "Cross-reference picks with tipster consensus data",
        "python_step": "tipster_xref",
        "critical": False,
        "agent_review_required": "bet-scout",
        "agent_task": "Read FULL tipster arguments, assess quality, check independence, discover angles stats missed, promote watchlist picks",
    },
    {
        "id": "s3_deep_stats",
        "name": "S3: Deep Statistical Analysis",
        "description": "Per-candidate §3.0 analysis with L10/H2H/L5 stats",
        "python_step": "deep_stats",
        "agent_review_required": "bet-statistician",
        "agent_task": "Interpret safety scores, find edge mechanisms, fetch missing stats, write ANALYTICAL REASONING per candidate",
    },
    {
        "id": "s4_odds_eval",
        "name": "S4: Odds Evaluation",
        "description": "Cross-validate odds, compute EV, detect drift",
        "python_step": "odds_eval",
        "critical": False,
        "agent_review_required": "bet-valuator",
        "agent_task": "Cross-validate pricing across sources, reason about mispricing, assess edge durability, calculate relative value",
    },
    {
        "id": "s5_context",
        "name": "S5: Contextual Checks",
        "description": "Weather impact, venue, referee, roster changes",
        "python_step": "context_checks",
        "critical": False,
        "agent_review_required": "bet-challenger",
        "agent_task": "Assess REAL market impact of context flags, model motivation effects, identify compounding risk factors",
    },
    {
        "id": "s6_upset_risk",
        "name": "S6: Upset Risk Scoring",
        "description": "Score upset risk per candidate using sport-specific checklists",
        "python_step": "upset_risk",
        "critical": False,
        "agent_review_required": "bet-challenger",
        "agent_task": "Score upset risk with sport-specific contextual reasoning, apply Paradox Rule",
    },
    {
        "id": "s7_gate",
        "name": "S7: 17-Point Gate Check",
        "description": "Run gate checks, classify approved/extended/rejected",
        "python_step": "gate_check",
        "agent_review_required": "bet-challenger",
        "agent_task": "Build qualitative bear cases, audit assumptions, find historical analogies, Bayesian-update confidence",
    },
    {
        "id": "s8_coupons",
        "name": "S8: Build Coupons",
        "description": "Core portfolio + combo menu + extended pool",
        "python_step": "build_coupons",
        "agent_review_required": "bet-builder",
        "agent_task": "Review portfolio strategically, check hidden correlations, adjust stakes by conviction, V1-V10 + §S8.FINAL",
    },
    {
        "id": "s9_validate",
        "name": "S9: Validate Coupons",
        "description": "V1-V10 validation suite",
        "python_step": "validate",
        "critical": False,
    },
    {
        "id": "s10_summary",
        "name": "S10: Final Summary",
        "description": "Generate artifacts and summary report",
        "python_step": "summary",
        "critical": False,
    },
]
# Steps that skip with --skip-scan (the heavy Playwright scan + parallel enrichment)
SCAN_STEP_IDS = {"s1_scan", "s1_ingest", "s1a_discover", "s1b_parallel", "s1c_aggregate", "s1d_matrix", "s1e_shortlist"}


# ---------------------------------------------------------------------------
# Config & state helpers
# ---------------------------------------------------------------------------
def load_config() -> dict:
    """Load betting configuration."""
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_state(date: str) -> dict:
    """Load pipeline state for a date. DB first, JSON fallback."""
    # Try DB first
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT_DIR / "src"))
        from bet.db.connection import get_db
        from bet.db.repositories import PipelineRepo
        with get_db() as conn:
            repo = PipelineRepo(conn)
            db_steps = repo.get_run_status(date)
            if db_steps:
                # Build nested step dicts matching JSON format expected by
                # print_status() and the main pipeline loop.
                steps_nested = {}
                for s in db_steps:
                    step_dict = {"status": s["status"]}
                    if s.get("error_message"):
                        step_dict["error"] = s["error_message"]
                    if s.get("started_at"):
                        step_dict["started_at"] = s["started_at"]
                    if s.get("completed_at"):
                        step_dict["completed_at"] = s["completed_at"]
                    steps_nested[s["step"]] = step_dict
                state = {
                    "date": date,
                    "session": "full",
                    "version": "v1",
                    "started_at": db_steps[0]["started_at"] if db_steps else None,
                    "completed_at": None,
                    "current_step": None,
                    "steps": steps_nested,
                    "errors": [s["error_message"] for s in db_steps if s.get("error_message")],
                    "step_data": {s["step"]: s["stats"] for s in db_steps if s.get("stats")},
                    "pass_number": 1,
                }
                print(f"[pipeline] Loaded state from DB ({len(db_steps)} steps)")
                return state
    except Exception as e:
        print(f"[pipeline] DB state load failed: {e}")

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = STATE_DIR / f"pipeline_{date}.json"
    if state_file.exists():
        return json.loads(state_file.read_text(encoding="utf-8"))
    return {
        "date": date,
        "session": "full",
        "version": "v1",
        "started_at": None,
        "completed_at": None,
        "current_step": None,
        "steps": {},
        "errors": [],
        "step_data": {},
        "pass_number": 1,
    }


def save_state(date: str, state: dict):
    """Save pipeline state atomically — DB + JSON dual write."""
    # DB write
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT_DIR / "src"))
        from bet.db.connection import get_db
        from bet.db.repositories import PipelineRepo
        with get_db() as conn:
            repo = PipelineRepo(conn)
            current = state.get("current_step")
            if current:
                step_data = state.get("steps", {}).get(current, {})
                step_status = step_data.get("status", "running") if isinstance(step_data, dict) else step_data
                if step_status == "running":
                    repo.start_step(date, current)
                elif step_status == "completed":
                    stats = state.get("step_data", {}).get(current)
                    repo.complete_step(date, current, stats)
                elif step_status == "failed":
                    errors = state.get("errors", [])
                    repo.fail_step(date, current, errors[-1] if errors else "unknown")
            conn.commit()
    except Exception as e:
        print(f"[pipeline] DB state save failed: {e}")

    # JSON fallback write
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = STATE_DIR / f"pipeline_{date}.json"
    content = json.dumps(state, indent=2, ensure_ascii=False)
    fd, tmp_path = tempfile.mkstemp(dir=str(STATE_DIR), suffix=".tmp")
    closed = False
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        closed = True
        os.replace(tmp_path, str(state_file))
    except Exception:
        if not closed:
            os.close(fd)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


# ---------------------------------------------------------------------------
# Shell command runner
# ---------------------------------------------------------------------------
def run_command(cmd: str, date: str, step_id: str = "") -> tuple[bool, str]:
    """Run a shell command and return (success, output)."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return False, f"Invalid date format: {date} (expected YYYY-MM-DD)"
    cmd = cmd.replace("{date}", date)
    # Compute previous date for settlement commands
    prev_date = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    cmd = cmd.replace("{prev_date}", prev_date)
    step_timeout = STEP_TIMEOUTS.get(step_id, DEFAULT_STEP_TIMEOUT)
    print(f"  → Running: {cmd} (timeout: {step_timeout}s)")
    try:
        use_shell = cmd.strip().startswith("bash ")
        if use_shell:
            run_args = cmd
        else:
            run_args = shlex.split(cmd)
        env = os.environ.copy()
        env["PIPELINE_MANAGED"] = "1"
        result = subprocess.run(
            run_args,
            shell=use_shell,
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=step_timeout,
            env=env,
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            print(f"  ✗ Command failed (exit {result.returncode})")
            return False, output
        print(f"  ✓ Command succeeded")
        return True, output
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {step_timeout}s (step: {step_id or 'unknown'})"
    except Exception as e:
        return False, str(e)


def check_outputs(step: dict) -> list[str]:
    """Check expected output files exist AND contain meaningful data."""
    missing = []
    for output_path in step.get("outputs", []):
        full_path = ROOT_DIR / output_path
        if not full_path.exists():
            missing.append(f"{output_path} (missing)")
            continue
        # Check file is not empty
        try:
            size = full_path.stat().st_size
            if size == 0:
                missing.append(f"{output_path} (empty)")
                continue
            # For JSON files, check valid JSON with at least some content
            if output_path.endswith(".json"):
                data = json.loads(full_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and not data:
                    missing.append(f"{output_path} (empty JSON object)")
                elif isinstance(data, list) and not data:
                    missing.append(f"{output_path} (empty JSON array)")
        except (json.JSONDecodeError, OSError) as e:
            missing.append(f"{output_path} (invalid: {e})")
    return missing


# ---------------------------------------------------------------------------
# ESPN American odds → decimal conversion
# ---------------------------------------------------------------------------
def _convert_espn_odds_to_decimal(odds_data: dict) -> dict:
    """Convert ESPN American odds to decimal format.

    American odds: +X → 1 + X/100; −X → 1 + 100/X
    """
    def _american_to_decimal(american) -> float | None:
        try:
            val = float(american)
        except (ValueError, TypeError):
            return None
        if val > 0:
            return round(1 + val / 100, 3)
        elif val < 0:
            return round(1 + 100 / abs(val), 3)
        return None

    result = {}

    # Moneyline
    ml = odds_data.get("moneyline", {})
    if ml:
        result["moneyline"] = {}
        for side in ("home", "away", "draw"):
            dec = _american_to_decimal(ml.get(side))
            if dec:
                result["moneyline"][side] = dec

    # Total
    total = odds_data.get("total", {})
    if total:
        result["total"] = {"line": total.get("line", "")}
        over_dec = _american_to_decimal(total.get("over_odds"))
        under_dec = _american_to_decimal(total.get("under_odds"))
        if over_dec:
            result["total"]["over"] = over_dec
        if under_dec:
            result["total"]["under"] = under_dec

    # Spread
    spread = odds_data.get("spread", {})
    if spread:
        result["spread"] = {
            "home_line": spread.get("home_line", ""),
            "away_line": spread.get("away_line", ""),
        }
        home_dec = _american_to_decimal(spread.get("home_odds"))
        away_dec = _american_to_decimal(spread.get("away_odds"))
        if home_dec:
            result["spread"]["home"] = home_dec
        if away_dec:
            result["spread"]["away"] = away_dec

    return result


# ---------------------------------------------------------------------------
# EV injection from odds API
# ---------------------------------------------------------------------------
def _inject_ev_from_odds(candidates: list[dict], date: str):
    """Compute and inject EV into candidates using odds API snapshots.

    Sources: SQLite DB (odds_history — 97K+ rows with Betclic PL, Bet365)
    + the-odds-api (odds_api_snapshot.json) + odds-api.io (odds_api_io_snapshot.json)
    + ESPN DraftKings (espn_enrichment_{date}.json).
    EV = (probability × odds) - 1. If no odds snapshot exists, candidates
    keep ev=None and the gate handles it gracefully (stats-first mode).

    The odds_lookup stores:  key = "home|away" -> {
        "market_best": float,   # best ML/totals odds from any bookmaker
        "betclic": float|None,  # Betclic PL odds specifically
        "bet365": float|None,   # Bet365 odds
        "totals": [{line, over, under, bookmaker}],  # totals lines
    }
    """
    odds_lookup: dict[str, dict] = {}

    def _ensure_entry(key: str) -> dict:
        if key not in odds_lookup:
            odds_lookup[key] = {"market_best": 0, "betclic": None, "bet365": None, "totals": []}
        return odds_lookup[key]

    # Source 0: SQLite DB (richest source — Betclic PL + Bet365 + 10+ bookmakers)
    db_path = DATA_DIR / "betting.db"
    if db_path.exists():
        try:
            sys.path.insert(0, str(ROOT_DIR / "src"))
            from bet.db.connection import get_db

            with get_db() as conn:
                cur = conn.cursor()
                cur.execute('''
                    SELECT t1.name, t2.name, o.bookmaker, o.market, o.selection, o.odds, o.line
                    FROM odds_history o
                    JOIN fixtures f ON o.fixture_id = f.id
                    JOIN teams t1 ON f.home_team_id = t1.id
                    JOIN teams t2 ON f.away_team_id = t2.id
                    WHERE date(o.fetched_at) = ?
                ''', (date,))
                db_rows = cur.fetchall()

            # Parse DB odds: group totals lines with their over/under prices
            # DB stores totals as interleaved rows: hdp (line), over (price), under (price)
            totals_buffer: dict[str, dict] = {}  # key -> {current_line, entries}
            for home, away, bookmaker, market, selection, odds_val, line_val in db_rows:
                h = home.strip().lower()
                a = away.strip().lower()
                key = f"{h}|{a}"
                entry = _ensure_entry(key)

                bk_lower = (bookmaker or "").lower()
                is_betclic = "betclic" in bk_lower
                is_bet365 = "bet365" in bk_lower

                if market in ("h2h", "ml"):
                    # ML odds — track market_best (highest) + per-bookmaker
                    if odds_val and odds_val > entry["market_best"]:
                        entry["market_best"] = float(odds_val)
                    sel_lower = (selection or "").lower()
                    if sel_lower in ("draw", "x"):
                        pass  # Skip draw for per-bookmaker tracking
                    elif is_betclic:
                        prev_betclic = entry.get("betclic") or 0
                        if odds_val and odds_val > prev_betclic:
                            entry["betclic"] = float(odds_val)
                    elif is_bet365:
                        prev_bet365 = entry.get("bet365") or 0
                        if odds_val and odds_val > prev_bet365:
                            entry["bet365"] = float(odds_val)

                elif market == "totals":
                    sel_lower = (selection or "").lower()
                    # Format 1: standard Over/Under with line in `line` column
                    if line_val is not None and sel_lower in ("over", "under"):
                        line_f = float(line_val)
                        # Find existing entry for this line+bookmaker, or create
                        found = False
                        for tl in entry["totals"]:
                            if abs(tl.get("line", 0) - line_f) < 0.01 and tl.get("bookmaker") == bookmaker:
                                tl[sel_lower] = float(odds_val)
                                found = True
                                break
                        if not found:
                            new_tl = {"line": line_f, "bookmaker": bookmaker, "over": None, "under": None}
                            new_tl[sel_lower] = float(odds_val)
                            entry["totals"].append(new_tl)

                    # Format 2: Betclic/Bet365 interleaved hdp/over/under (no line column)
                    else:
                        buf_key = f"{key}|{bookmaker}"
                        if buf_key not in totals_buffer:
                            totals_buffer[buf_key] = {"line": None, "over": None, "under": None}
                        buf = totals_buffer[buf_key]

                        if sel_lower == "hdp":
                            # This is the line value (stored in odds column)
                            if buf["line"] is not None and buf["over"] is not None:
                                # Flush previous complete line
                                entry["totals"].append({
                                    "line": buf["line"], "over": buf["over"],
                                    "under": buf["under"], "bookmaker": bookmaker,
                                })
                            buf["line"] = float(odds_val)
                            buf["over"] = None
                            buf["under"] = None
                        elif sel_lower == "over":
                            buf["over"] = float(odds_val)
                        elif sel_lower == "under":
                            buf["under"] = float(odds_val)

                        # Flush complete line
                        if buf["line"] is not None and buf["over"] is not None and buf["under"] is not None:
                            entry["totals"].append({
                                "line": buf["line"], "over": buf["over"],
                                "under": buf["under"], "bookmaker": bookmaker,
                            })
                            totals_buffer[buf_key] = {"line": None, "over": None, "under": None}

            # Flush any remaining incomplete totals buffers (line+over without under)
            for buf_key, buf in totals_buffer.items():
                if buf["line"] is not None and buf["over"] is not None:
                    parts = buf_key.split("|")
                    bk = parts[2] if len(parts) > 2 else "unknown"
                    match_key = f"{parts[0]}|{parts[1]}" if len(parts) > 1 else buf_key
                    if match_key in odds_lookup:
                        odds_lookup[match_key]["totals"].append({
                            "line": buf["line"], "over": buf["over"],
                            "under": buf.get("under"), "bookmaker": bk,
                        })

            if db_rows:
                print(f"  → DB: loaded {len(db_rows)} odds rows → {len(odds_lookup)} fixtures")
        except Exception as e:
            print(f"  ⚠️ DB odds load failed: {e}")

    # Source 1: the-odds-api snapshot
    odds_path = DATA_DIR / "odds_api_snapshot.json"
    if odds_path.exists():
        try:
            odds_data = json.loads(odds_path.read_text(encoding="utf-8"))
            for event in odds_data if isinstance(odds_data, list) else odds_data.get("events", []):
                home = (event.get("home_team") or "").strip().lower()
                away = (event.get("away_team") or "").strip().lower()
                if not home or not away:
                    continue
                key = f"{home}|{away}"
                entry = _ensure_entry(key)

                # Try pre-computed best_odds first
                best_odds = event.get("best_odds") or event.get("odds", {}).get("market_best")
                if best_odds:
                    val = float(best_odds)
                    if val > entry["market_best"]:
                        entry["market_best"] = val

                # Parse bookmakers array (raw the-odds-api format)
                for bm in event.get("bookmakers") or []:
                    bk_title = (bm.get("title") or bm.get("key") or "").lower()
                    is_betclic = "betclic" in bk_title
                    is_bet365 = "bet365" in bk_title
                    for mkt in bm.get("markets") or []:
                        mkt_key = (mkt.get("key") or "").lower()
                        if mkt_key in ("ml", "h2h", "moneyline"):
                            for outcome in mkt.get("outcomes") or []:
                                price = outcome.get("price")
                                if not price or price <= 1.0:
                                    continue
                                if price > entry["market_best"]:
                                    entry["market_best"] = float(price)
                                side = (outcome.get("name") or "").lower()
                                if side in ("draw", "x"):
                                    continue
                                if is_betclic:
                                    prev = entry.get("betclic") or 0
                                    if price > prev:
                                        entry["betclic"] = float(price)
                                elif is_bet365:
                                    prev = entry.get("bet365") or 0
                                    if price > prev:
                                        entry["bet365"] = float(price)
                        elif mkt_key in ("totals", "over_under"):
                            for outcome in mkt.get("outcomes") or []:
                                price = outcome.get("price")
                                point = outcome.get("point")
                                side = (outcome.get("name") or "").lower()
                                if price and point is not None and side in ("over", "under"):
                                    entry["totals"].append({
                                        "line": float(point),
                                        side: float(price),
                                        "bookmaker": bm.get("title") or bm.get("key"),
                                    })

                # Load pre-computed totals from API snapshot
                api_totals = event.get("totals")
                if api_totals and isinstance(api_totals, list):
                    for tl in api_totals:
                        if tl.get("line") is not None:
                            entry["totals"].append(tl)
        except (json.JSONDecodeError, OSError):
            pass

    # Source 2: odds-api.io snapshot (265 bookmakers, more coverage)
    io_path = DATA_DIR / "odds_api_io_snapshot.json"
    if io_path.exists():
        try:
            io_data = json.loads(io_path.read_text(encoding="utf-8"))
            for event in io_data.get("events", []):
                home = (event.get("home") or "").strip().lower()
                away = (event.get("away") or "").strip().lower()
                if not home or not away:
                    continue
                key = f"{home}|{away}"
                entry = _ensure_entry(key)
                for bookie_name, markets in (event.get("bookmakers") or {}).items():
                    if not isinstance(markets, list):
                        continue
                    for market in markets:
                        if market.get("name") == "ML":
                            for odds_entry in market.get("odds", []):
                                for side in ["home", "away"]:
                                    try:
                                        val = float(odds_entry.get(side, 0))
                                        if val > entry["market_best"]:
                                            entry["market_best"] = val
                                    except (ValueError, TypeError):
                                        pass
            # Inject from value bets (pre-calculated EV!)
            for vb in io_data.get("value_bets", []):
                ev_data = vb.get("event", {})
                home = (ev_data.get("home") or "").strip().lower()
                away = (ev_data.get("away") or "").strip().lower()
                if home and away:
                    pre_ev = vb.get("expectedValue")
                    if pre_ev is not None:
                        for c in candidates:
                            ch = (c.get("home_team") or "").strip().lower()
                            ca = (c.get("away_team") or "").strip().lower()
                            if ch == home and ca == away and c.get("ev") is None:
                                c["ev"] = round(float(pre_ev), 4)
                                c["ev_source"] = "odds-api-io-value-bet"
        except (json.JSONDecodeError, OSError):
            pass

    # Source 3: ESPN DraftKings odds (free, unlimited)
    espn_path = DATA_DIR / f"espn_enrichment_{date}.json"
    if espn_path.exists():
        try:
            espn_data = json.loads(espn_path.read_text(encoding="utf-8"))
            for event in espn_data.get("odds", []):
                home = (event.get("home") or "").strip().lower()
                away = (event.get("away") or "").strip().lower()
                if not home or not away:
                    continue
                key = f"{home}|{away}"
                entry = _ensure_entry(key)
                dec_odds = event.get("odds_decimal", {}).get("moneyline", {})
                for side in ("home", "away"):
                    val = dec_odds.get(side)
                    if val and val > entry["market_best"]:
                        entry["market_best"] = val
        except (json.JSONDecodeError, OSError):
            pass

    if not odds_lookup:
        return

    injected = 0
    odds_enriched = 0
    for c in candidates:
        home = (c.get("home_team") or "").strip().lower()
        away = (c.get("away_team") or "").strip().lower()
        key = f"{home}|{away}"
        entry = odds_lookup.get(key)
        if not entry:
            continue

        # Always inject odds data (even without probability — for coupon builder)
        best_market = c.get("best_market") or {}

        # Determine which odds to use: Betclic first, then Bet365, then market_best
        betclic_odds = entry.get("betclic")
        bet365_odds = entry.get("bet365")
        market_best = entry.get("market_best", 0)
        # Pick best available odds for the candidate
        use_odds = betclic_odds or bet365_odds or (market_best if market_best > 1.0 else None)

        if use_odds:
            c.setdefault("odds", {})["market_best"] = use_odds
            if betclic_odds:
                c["odds"]["betclic"] = betclic_odds
            if bet365_odds:
                c["odds"]["bet365"] = bet365_odds
            odds_enriched += 1

        # Inject totals data for statistical market matching
        if entry.get("totals"):
            c.setdefault("odds", {})["totals"] = entry["totals"]

        # EV calculation (skip if already has EV)
        if c.get("ev") is not None:
            continue
        
        market_name = (best_market.get("name") or "").lower()
        is_ml_market = any(kw in market_name for kw in ("winner", "ml", "match winner", "moneyline", "1x2"))
        is_totals_market = any(kw in market_name for kw in ("o/u", "over", "under", "total", "corners", "fouls", "cards", "shots", "games", "sets", "frames", "points", "goals"))

        prob = best_market.get("probability")
        safety = best_market.get("safety_score")
        
        # For totals/statistical markets, try to find matching line in DB totals
        matched_odds = None
        if is_totals_market and entry.get("totals"):
            line = best_market.get("line")
            direction = (best_market.get("direction") or "").upper()
            if line is not None:
                for tl in entry["totals"]:
                    if abs(tl.get("line", 0) - float(line)) < 0.01:
                        if "OVER" in direction and tl.get("over"):
                            if matched_odds is None or tl["over"] > matched_odds:
                                matched_odds = tl["over"]
                        elif "UNDER" in direction and tl.get("under"):
                            if matched_odds is None or tl["under"] > matched_odds:
                                matched_odds = tl["under"]
        elif is_ml_market:
            # ML market — use ML odds directly
            matched_odds = use_odds
        
        # Only calculate EV when odds match the analyzed market
        p = prob or safety
        odds_for_ev = matched_odds or (use_odds if is_ml_market else None)
        if p and odds_for_ev:
            ev = round(float(p) * float(odds_for_ev) - 1, 4)
            c["ev"] = ev
            c["ev_source"] = "db+api-composite"
            injected += 1

    print(f"  → Odds enriched: {odds_enriched}/{len(candidates)} candidates")
    if injected:
        print(f"  → EV injected: {injected}/{len(candidates)} candidates")


# ---------------------------------------------------------------------------
# Python-driven step implementations
# ---------------------------------------------------------------------------

def _run_tipster_xref(date: str, state: dict) -> tuple[bool, str]:
    """S2: Cross-reference shortlist with tipster consensus data.

    Enriches shortlist candidates with tipster support, consensus %, and arguments.
    """
    tipster_path = DATA_DIR / f"tipster_aggregation_{date}.json"
    consensus_path = DATA_DIR / f"{date}_tipster_consensus.json"

    # Try both possible tipster data files
    tipster_data = None
    for tpath in [tipster_path, consensus_path]:
        if tpath.exists():
            try:
                tipster_data = json.loads(tpath.read_text(encoding="utf-8"))
                print(f"  → Loaded tipster data from {tpath.name}")
                break
            except (json.JSONDecodeError, OSError):
                continue

    if tipster_data is None:
        return True, "No tipster data available — skipping cross-reference"

    # Parse tips into a lookup
    tips = tipster_data if isinstance(tipster_data, list) else tipster_data.get("tips", [])
    tip_lookup: dict[str, list[dict]] = {}
    for tip in tips:
        home = (tip.get("home") or tip.get("home_team") or "").strip().lower()
        away = (tip.get("away") or tip.get("away_team") or "").strip().lower()
        if home and away:
            key = f"{home}|{away}"
            tip_lookup.setdefault(key, []).append(tip)

    # Load shortlist and cross-reference
    date_compact = date.replace("-", "")
    shortlist_path = DATA_DIR / f"{date_compact}_s2_shortlist.json"
    if not shortlist_path.exists():
        shortlist_path = DATA_DIR / f"{date}_s2_shortlist.json"

    matched = 0
    total = 0
    if shortlist_path.exists():
        try:
            shortlist = json.loads(shortlist_path.read_text(encoding="utf-8"))
            candidates = shortlist.get("candidates", shortlist.get("shortlist", []))
            total = len(candidates)

            for c in candidates:
                home = (c.get("home_team") or c.get("home") or "").strip().lower()
                away = (c.get("away_team") or c.get("away") or "").strip().lower()
                key = f"{home}|{away}"
                matching_tips = tip_lookup.get(key, [])
                if matching_tips:
                    matched += 1
                    tipster_names = list({t.get("tipster", t.get("source", "unknown")) for t in matching_tips})
                    consensus = len(matching_tips)
                    c["tipster_support"] = {
                        "count": consensus,
                        "tipsters": tipster_names,
                        "tips": matching_tips,
                    }
                    # Also set tipster_count directly for gate_checker compatibility
                    c["tipster_count"] = consensus
                    home_disp = c.get("home_team", c.get("home", "?"))
                    away_disp = c.get("away_team", c.get("away", "?"))
                    print(f"    ✓ {home_disp} vs {away_disp}: {consensus} tips from {', '.join(tipster_names[:3])}")

            # Save enriched shortlist
            shortlist_path.write_text(
                json.dumps(shortlist, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ⚠ Shortlist enrichment error: {e}")

    n_tips = len(tips)
    return True, f"Tipster cross-reference: {n_tips} tips loaded, {matched}/{total} shortlist candidates matched"


def _run_odds_eval(date: str, state: dict) -> tuple[bool, str]:
    """S4: Cross-validate odds, compute EV, detect drift."""
    # Load current candidates from S3 JSON output (primary — has ALL candidates)
    # IMPORTANT: Do NOT read from DB here — DB only has entries with resolved
    # fixture_ids (~166), while JSON has the full set (~1440) including
    # shortlist-fallback candidates.
    candidates = None

    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
    if s3_path.exists():
        try:
            s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
            candidates = s3_data.get("analyses", [])
            if candidates:
                print(f"  → JSON: loaded {len(candidates)} S3 analyses")
        except (json.JSONDecodeError, OSError):
            pass

    if not candidates:
        try:
            from db_data_loader import load_analysis_results_from_db
            db_analyses = load_analysis_results_from_db(date)
            if db_analyses:
                candidates = db_analyses
                print(f"  → DB fallback: loaded {len(candidates)} S3 analysis results")
        except Exception as e:
            print(f"  ⚠️ DB read also failed: {e}")

    if not candidates:
        return True, "S4: No S3 data yet — skipping EV injection"

    if not candidates:
        return True, "S4: No S3 data yet — skipping EV injection"

    try:
        _inject_ev_from_odds(candidates, date)

        # Count how many have EV and log details
        with_ev = 0
        positive_ev = 0
        for c in candidates:
            ev = c.get("ev")
            if ev is not None:
                with_ev += 1
                if ev > 0:
                    positive_ev += 1
                home = c.get("home_team", "?")
                away = c.get("away_team", "?")
                odds = (c.get("odds") or {}).get("market_best", 0)
                source = c.get("ev_source", "calculated")
                marker = "💰" if ev > 0 else "📉"
                print(f"    {marker} {home} vs {away}: EV={ev:+.1%} @{odds:.2f} ({source})")
        total = len(candidates)

        # Save back enriched data to JSON (for downstream consumers)
        s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
        if s3_path.exists():
            try:
                s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
                s3_data["analyses"] = candidates
                s3_path.write_text(
                    json.dumps(s3_data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            except (json.JSONDecodeError, OSError):
                pass

        return True, f"S4 completed: {with_ev}/{total} with EV data ({positive_ev} positive EV)"
    except Exception as e:
        return True, f"S4 odds evaluation error: {e} — continuing without"


def _run_context_checks(date: str, state: dict) -> tuple[bool, str]:
    """S5: Contextual checks — weather, venue, referee, roster changes.

    Enriches S3 candidates with contextual flags for downstream gate checks.
    """
    checks_done = []
    context_flags = {}

    # Load S3 candidates for enrichment
    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
    candidates = []
    if s3_path.exists():
        try:
            s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
            candidates = s3_data.get("analyses", [])
        except (json.JSONDecodeError, OSError):
            pass

    # Weather data — flag candidates with weather impact
    weather_path = DATA_DIR / f"weather_{date}.json"
    weather_impacts = []
    if weather_path.exists():
        try:
            weather = json.loads(weather_path.read_text(encoding="utf-8"))
            venues = weather if isinstance(weather, list) else weather.get("venues", weather.get("forecasts", {}))
            if isinstance(venues, dict):
                for venue, forecast in venues.items():
                    flags = forecast.get("flags", [])
                    if flags:
                        weather_impacts.append(f"{venue}: {', '.join(flags)}")
                        context_flags[venue] = flags
            elif isinstance(venues, list):
                for v in venues:
                    venue_name = v.get("venue", v.get("city", "unknown"))
                    flags = v.get("flags", [])
                    if flags:
                        weather_impacts.append(f"{venue_name}: {', '.join(flags)}")
                        context_flags[venue_name] = flags
            n_venues = len(venues) if isinstance(venues, (list, dict)) else 0
            n_impacted = len(weather_impacts)
            checks_done.append(f"weather: {n_venues} venues checked, {n_impacted} with impact flags")
            if weather_impacts:
                for wi in weather_impacts[:5]:
                    print(f"    🌧 {wi}")
        except (json.JSONDecodeError, OSError):
            checks_done.append("weather: load_error")
    else:
        checks_done.append("weather: unavailable")

    # ESPN injuries/roster data — flag candidates with key injuries
    espn_path = DATA_DIR / f"espn_enrichment_{date}.json"
    injury_summary = []
    if espn_path.exists():
        try:
            espn = json.loads(espn_path.read_text(encoding="utf-8"))
            injuries = espn.get("injuries", {})
            for sport, sport_injuries in injuries.items():
                if isinstance(sport_injuries, list):
                    for inj in sport_injuries:
                        team = inj.get("team", "unknown")
                        player = inj.get("player", inj.get("name", "unknown"))
                        status = inj.get("status", inj.get("type", "unknown"))
                        injury_summary.append(f"{sport}/{team}: {player} ({status})")
            n_injuries = len(injury_summary)
            checks_done.append(f"injuries: {n_injuries} entries across {len(injuries)} sports")
            if injury_summary:
                for inj in injury_summary[:8]:
                    print(f"    🏥 {inj}")
        except (json.JSONDecodeError, OSError):
            checks_done.append("injuries: load_error")
    else:
        checks_done.append("injuries: unavailable")

    # Enrich S3 candidates with context flags
    if candidates and s3_path.exists():
        enriched = 0
        for c in candidates:
            c_flags = []
            home = c.get("home_team", "")
            away = c.get("away_team", "")
            sport = c.get("sport", "")
            # Check weather
            for venue, flags in context_flags.items():
                if venue.lower() in (home.lower(), away.lower(), c.get("venue", "").lower()):
                    c_flags.extend([f"WEATHER:{f}" for f in flags])
            # Check injuries
            for inj_entry in injury_summary:
                if home.lower() in inj_entry.lower() or away.lower() in inj_entry.lower():
                    c_flags.append(f"INJURY:{inj_entry.split(':')[-1].strip()}")
            if c_flags:
                c.setdefault("context_flags", []).extend(c_flags)
                enriched += 1
                print(f"    📋 {home} vs {away}: {', '.join(c_flags[:3])}")
        if enriched:
            s3_path.write_text(
                json.dumps(s3_data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            checks_done.append(f"enriched: {enriched}/{len(candidates)} candidates with context flags")

    return True, f"S5 contextual checks: {', '.join(checks_done)}"


def _run_upset_risk(date: str, state: dict) -> tuple[bool, str]:
    """S6: Upset risk scoring per candidate with sport-specific heuristics."""
    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
    if not s3_path.exists():
        return True, "S6: No S3 data — skipping upset risk scoring"

    # Sport-specific upset risk thresholds
    UPSET_THRESHOLDS = {
        "football": {"safety_low": 0.55, "h2h_min": 3, "form_diverge": 0.15},
        "tennis": {"safety_low": 0.50, "h2h_min": 2, "form_diverge": 0.20},
        "basketball": {"safety_low": 0.50, "h2h_min": 3, "form_diverge": 0.10},
        "volleyball": {"safety_low": 0.50, "h2h_min": 3, "form_diverge": 0.15},
        "hockey": {"safety_low": 0.50, "h2h_min": 3, "form_diverge": 0.15},
        "handball": {"safety_low": 0.50, "h2h_min": 2, "form_diverge": 0.15},
        "baseball": {"safety_low": 0.45, "h2h_min": 3, "form_diverge": 0.10},
        "esports": {"safety_low": 0.45, "h2h_min": 2, "form_diverge": 0.20},
    }
    DEFAULT_THRESHOLDS = {"safety_low": 0.50, "h2h_min": 2, "form_diverge": 0.15}

    try:
        s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
        analyses = s3_data.get("analyses", [])
        scored = 0
        elevated = 0
        high_risk = 0

        for analysis in analyses:
            sport = analysis.get("sport", "").lower()
            thresholds = UPSET_THRESHOLDS.get(sport, DEFAULT_THRESHOLDS)
            risk_factors = []

            ranking = analysis.get("ranking", analysis.get("ranking_result", {}).get("ranking", []))
            top_market = ranking[0] if ranking else {}
            safety = top_market.get("safety_score", 0)

            # Factor 1: Low safety score (sport-specific threshold)
            if safety < thresholds["safety_low"]:
                risk_factors.append(f"safety_below_{thresholds['safety_low']} ({safety})")

            # Factor 2: L5 trend diverging from L10 (form instability)
            l5_avg = top_market.get("combined_avg_l5", top_market.get("l5_avg"))
            l10_avg = top_market.get("combined_avg", top_market.get("l10_avg"))
            if l5_avg and l10_avg and l10_avg != 0:
                divergence = abs(l5_avg - l10_avg) / abs(l10_avg)
                if divergence > thresholds["form_diverge"]:
                    direction = "declining" if l5_avg < l10_avg else "surging"
                    risk_factors.append(f"form_{direction} ({divergence:.0%} L5 vs L10)")

            # Factor 3: Missing H2H data
            h2h = analysis.get("h2h", {})
            h2h_meetings = len(h2h.get("meetings", []))
            if h2h_meetings < thresholds["h2h_min"]:
                risk_factors.append(f"h2h_insufficient ({h2h_meetings}/{thresholds['h2h_min']} meetings)")

            # Factor 4: Context flags (weather, injuries)
            context_flags = analysis.get("context_flags", [])
            if any("INJURY" in f for f in context_flags):
                risk_factors.append("key_injury_flagged")
            if any("WEATHER" in f for f in context_flags):
                risk_factors.append("adverse_weather")

            # Factor 5: No EV data (stats-first mode = higher uncertainty)
            if analysis.get("ev") is None:
                risk_factors.append("no_ev_data_statsFirst")

            # Score upset risk
            risk_count = len(risk_factors)
            if risk_count >= 3:
                risk_level = "HIGH"
                high_risk += 1
            elif risk_count >= 1:
                risk_level = "ELEVATED"
                elevated += 1
            else:
                risk_level = "LOW"

            analysis["upset_risk"] = {
                "level": risk_level,
                "factors": risk_factors,
                "factor_count": risk_count,
            }
            analysis.setdefault("flags", [])
            if risk_level != "LOW":
                analysis["flags"].append(f"upset_risk_{risk_level.lower()}")
            scored += 1

            # Verbose per-candidate output
            home = analysis.get("home_team", "?")
            away = analysis.get("away_team", "?")
            marker = {"LOW": "🟢", "ELEVATED": "🟡", "HIGH": "🔴"}[risk_level]
            print(f"    {marker} {home} vs {away} [{sport}]: {risk_level} ({risk_count} factors)")
            if risk_factors:
                for rf in risk_factors[:3]:
                    print(f"       → {rf}")

        s3_path.write_text(
            json.dumps(s3_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True, f"S6 completed: {scored} candidates scored — {elevated} elevated, {high_risk} high risk"
    except Exception as e:
        return True, f"S6 upset risk error: {e} — continuing without"


def _run_source_health(date: str) -> None:
    """Record source health after scan completes."""
    try:
        result = subprocess.run(
            ["python3", "scripts/source_health.py", "--log"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            print(f"  → Source health: {result.stdout.strip()}")
        else:
            print(f"  ⚠ Source health logging failed: {result.stderr[:100]}")
    except Exception as e:
        print(f"  ⚠ Source health logging error: {e}")


def _run_scan_events(date: str, state: dict) -> tuple[bool, str]:
    """S1: Run Playwright event scan ONLY (no enrichment/aggregation).

    This is the decomposed version of the monolithic bash script.
    Runs scan_events.py directly with proper timeout and resume capability.
    Enrichment, aggregation, matrix, shortlist are handled by subsequent steps.
    """
    from datetime import datetime as dt

    # Build ZawodTyper daily URL (use Warsaw timezone — project canonical TZ)
    now = dt.now(ZoneInfo("Europe/Warsaw"))
    pl_months = ["", "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
                 "lipca", "sierpnia", "wrzesnia", "pazdziernika", "listopada", "grudnia"]
    pl_days = ["", "poniedzialek", "wtorek", "sroda", "czwartek", "piatek", "sobota", "niedziela"]
    zt_day = now.day
    zt_month = now.month
    zt_dow = now.isoweekday()  # 1=Mon, 7=Sun
    zt_url = f"https://www.zawodtyper.pl/typy-dnia-{zt_day}-{pl_months[zt_month]}-{pl_days[zt_dow]}/"
    print(f"  → ZawodTyper URL: {zt_url}")

    # Run scan_events.py with deep-link discovery
    scan_cmd = (
        f'python3 scripts/scan_events.py --deep --max-deep-links 30 --workers 8'
        f' --urls-file config/scan_urls.json'
        f' --urls "{zt_url}"'
    )
    success, output = run_command(scan_cmd, date, step_id="s1_scan")

    if not success:
        # Check if scan_summary.json was still partially produced (and is fresh — today's date)
        summary_path = DATA_DIR / "scan_summary.json"
        if summary_path.exists() and summary_path.stat().st_size > 100:
            # Staleness check: file must be from today (within last 2 hours)
            import time as _time
            file_age_hours = (_time.time() - summary_path.stat().st_mtime) / 3600
            if file_age_hours > 2:
                return False, f"Scan failed and scan_summary.json is stale ({file_age_hours:.1f}h old): {output[:200]}"
            print("  ⚠ Scan had errors but produced partial results — continuing")
            state.setdefault("step_data", {})["s1_partial"] = True
            # Record source health
            _run_source_health(date)
            return True, f"Scan completed with errors (partial results saved): {output[:200]}"
        return False, output

    # Record source health after successful scan
    _run_source_health(date)

    # Count scan results
    summary_path = DATA_DIR / "scan_summary.json"
    event_count = 0
    url_count = 0
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            if isinstance(summary, dict):
                url_count = len(summary)
                for url_data in summary.values():
                    if isinstance(url_data, list):
                        event_count += len(url_data)
                    elif isinstance(url_data, dict):
                        event_count += len(url_data.get("events", []))
        except (json.JSONDecodeError, OSError):
            pass

    state.setdefault("step_data", {})["s1_events"] = event_count
    state["step_data"]["s1_urls"] = url_count

    return True, f"Scan complete: {event_count} events from {url_count} URLs"


def _run_parallel_enrichment(date: str, state: dict) -> tuple[bool, str]:
    """S1b: Run odds, weather, tipster aggregation, and ESPN enrichment in parallel.

    These tasks are independent and can run concurrently:
    1. Odds API fetch (~2 min)
    2. Weather data fetch (~1 min)
    3. Tipster aggregation (~3-5 min with parallel site fetching)
    4. ESPN DraftKings odds + injuries + form (~1 min, free/unlimited)
    """
    results = {}
    errors = []

    # Check which tasks need running (skip if already done by shell script)
    odds_needed = not (DATA_DIR / "odds_api_snapshot.json").exists()
    weather_needed = not (DATA_DIR / f"weather_{date}.json").exists()

    def run_odds():
        ok, out = run_command("python3 scripts/fetch_odds_api.py", date)
        return "odds", ok, out

    def run_odds_io():
        ok, out = run_command("python3 scripts/fetch_odds_api_io.py --date {date}", date)
        return "odds-io", ok, out

    def run_weather():
        ok, out = run_command("python3 scripts/fetch_weather.py --date {date}", date)
        return "weather", ok, out

    def run_tipsters():
        ok, out = run_command("python3 scripts/tipster_aggregator.py --date {date} --workers 5", date)
        return "tipsters", ok, out

    def run_espn_enrichment():
        """Fetch DraftKings odds, injuries, form from ESPN (free, unlimited)."""
        try:
            from api_clients.espn_adapter import ESPNMultiLeagueClient
            from api_clients.rate_limiter import RateLimiter

            rl = RateLimiter()
            enrichment = {"date": date, "odds": [], "injuries": {}, "form": {}}

            # Fetch odds for all ESPN-covered sports
            for sport in ["football", "basketball", "hockey", "baseball"]:
                client = ESPNMultiLeagueClient(sport=sport, rate_limiter=rl)
                try:
                    odds_data = client.get_scoreboard_odds(date)
                    for item in odds_data:
                        # Convert American odds to decimal for pipeline
                        converted = _convert_espn_odds_to_decimal(item.get("odds", {}))
                        item["odds_decimal"] = converted
                    enrichment["odds"].extend(odds_data)
                except Exception as e:
                    print(f"  ⚠ ESPN odds for {sport}: {e}")

                # Injuries (team sports only)
                try:
                    injuries = client.get_injuries()
                    if injuries:
                        enrichment["injuries"][sport] = injuries
                except Exception:
                    pass

            # Save enrichment data
            out_path = DATA_DIR / f"espn_enrichment_{date}.json"
            out_path.write_text(
                json.dumps(enrichment, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return "espn", True, f"ESPN: {len(enrichment['odds'])} events with odds"
        except Exception as e:
            return "espn", False, str(e)[:200]

    tasks = []
    # Always run tipsters and ESPN (they add unique data)
    tasks.append(run_tipsters)
    tasks.append(run_espn_enrichment)
    # Always try odds-io (different source from odds_api)
    tasks.append(run_odds_io)

    if odds_needed:
        tasks.append(run_odds)
    else:
        results["odds"] = {"ok": True, "output": "Skipped (file exists from S1)"}
        print("  ⏭ odds: skipped (odds_api_snapshot.json already exists)")

    if weather_needed:
        tasks.append(run_weather)
    else:
        results["weather"] = {"ok": True, "output": "Skipped (file exists from S1)"}
        print(f"  ⏭ weather: skipped (weather_{date}.json already exists)")

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(t) for t in tasks]

        for future in as_completed(futures):
            try:
                name, ok, out = future.result()
                results[name] = {"ok": ok, "output": out[:200]}
                if not ok:
                    errors.append(f"{name}: {out[:100]}")
                else:
                    print(f"  ✓ {name} completed")
            except Exception as e:
                errors.append(f"parallel task error: {str(e)[:100]}")

    parts = []
    for name in ["odds", "odds-io", "weather", "tipsters", "espn"]:
        r = results.get(name, {})
        status = "✓" if r.get("ok") else "✗"
        parts.append(f"{name}:{status}")

    msg = f"Parallel enrichment: {', '.join(parts)}"
    if errors:
        msg += f" (errors: {len(errors)})"

    state.setdefault("step_data", {})["parallel_results"] = {
        k: v.get("ok", False) for k, v in results.items()
    }

    # Non-critical — always return True (individual failures logged)
    return True, msg


def _run_s3(date: str, state: dict) -> tuple[bool, str]:
    """S3: Deep Statistical Analysis with probability engine integration."""
    # build_shortlist.py writes date as compact format (no dashes)
    date_compact = date.replace("-", "")
    shortlist_path = str(DATA_DIR / f"{date_compact}_s2_shortlist.json")
    if not Path(shortlist_path).exists():
        # Fallback: try dashed format just in case
        shortlist_path_alt = str(DATA_DIR / f"{date}_s2_shortlist.json")
        if Path(shortlist_path_alt).exists():
            shortlist_path = shortlist_path_alt
            print(f"  ⚠ Using dashed-format shortlist: {shortlist_path_alt}")
        else:
            shortlist_path = None

    top = state.get("cli_args", {}).get("top")
    result = generate_deep_stats(date, shortlist_path=shortlist_path, top=top)

    # Enrich with probability engine
    try:
        from probability_engine import enrich_ranking_with_probabilities
        s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
        if s3_path.exists():
            s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
            enriched_count = 0
            for analysis in s3_data.get("analyses", []):
                ranking = analysis.get("ranking_result")
                if ranking and ranking.get("ranking"):
                    enrich_ranking_with_probabilities(ranking)
                    enriched_count += 1
            s3_path.write_text(
                json.dumps(s3_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"  → Enriched {enriched_count} candidates with probability data")
    except ImportError:
        print("  ⚠ probability_engine not available — using safety scores only")
    except Exception as e:
        print(f"  ⚠ Probability enrichment error: {e}")

    count = result.get("candidates_with_data", 0)
    total = result.get("total_candidates", 0)

    # Verbose per-candidate summary
    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
    if s3_path.exists():
        try:
            s3_out = json.loads(s3_path.read_text(encoding="utf-8"))
            analyses = s3_out.get("analyses", [])
            sport_counts: dict[str, int] = {}
            for a in analyses:
                sport = a.get("sport", "unknown")
                sport_counts[sport] = sport_counts.get(sport, 0) + 1
                has_data = a.get("has_data", False)
                home = a.get("home_team", "?")
                away = a.get("away_team", "?")
                ranking = a.get("ranking_result", {}).get("ranking", [])
                top_market = ranking[0] if ranking else {}
                safety = top_market.get("safety_score", 0)
                market_name = top_market.get("market", "?")
                marker = "📊" if has_data else "⚠️"
                print(f"    {marker} {home} vs {away} [{sport}]: top market={market_name} safety={safety:.2f}" if has_data else f"    {marker} {home} vs {away} [{sport}]: NO DATA (cache miss)")
            if sport_counts:
                sport_summary = ", ".join(f"{s}:{c}" for s, c in sorted(sport_counts.items(), key=lambda x: -x[1]))
                print(f"  → Sport distribution: {sport_summary}")
        except Exception:
            pass

    msg = f"S3 completed: {count}/{total} candidates with stats data"

    # Stats quality gate: if 0 candidates enriched, warn loudly
    if count == 0 and total > 0:
        msg += " ⚠ ZERO candidates enriched — check API connectivity (ESPN should be unlimited)"
        print(f"  ⚠ STATS QUALITY GATE: 0/{total} candidates have stats.")
        print(f"    ESPN is free/unlimited — if this fails, check network connectivity.")
        print(f"    Pipeline continues in stats-first mode (user verifies on Betclic app).")

    state.setdefault("step_data", {})["s3_count"] = total
    state["step_data"]["s3_with_data"] = count

    # Structural validation of S3 output
    try:
        from validate_s3_output import validate_file as validate_s3_file
        s3_md_path = DATA_DIR / f"{date}_s3_deep_stats.md"
        if s3_md_path.exists():
            report = validate_s3_file(str(s3_md_path))
            if report.get("failed", 0) > 0:
                print(f"  ⚠ S3 structural issues: {report['failed']}/{report['total_candidates']} candidates failed validation")
                for c in report.get("candidates", [])[:5]:
                    if c["status"] == "FAIL":
                        print(f"    - {c['name']}: {c['errors'][0] if c['errors'] else 'unknown'}")
    except ImportError:
        pass  # validate_s3_output.py not available
    except Exception as e:
        print(f"  ⚠ S3 validation error: {e}")

    return True, msg


def _run_s7(date: str, state: dict) -> tuple[bool, str]:
    """S7: Gate Check."""
    analyses = None

    # Read from JSON first (has ALL candidates including shortlist-fallback)
    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
    if s3_path.exists():
        try:
            s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
            analyses = s3_data.get("analyses", [])
            if analyses:
                print(f"  → JSON: loaded {len(analyses)} S3 analyses for gate check")
        except (json.JSONDecodeError, OSError):
            pass

    # DB fallback
    if not analyses:
        try:
            from db_data_loader import load_analysis_results_from_db
            db_analyses = load_analysis_results_from_db(date)
            if db_analyses:
                analyses = db_analyses
                print(f"  → DB fallback: loaded {len(analyses)} S3 analysis results")
        except Exception as e:
            print(f"  ⚠️ DB read failed for S3 results: {e}")

    if not analyses:
        return False, f"S3 output not found: {s3_path}"

    # Inject tipster_count from enriched shortlist into S3 analyses
    # The tipster xref enriches the shortlist JSON but S3 doesn't propagate it
    date_compact = date.replace("-", "")
    shortlist_path = DATA_DIR / f"{date_compact}_s2_shortlist.json"
    if not shortlist_path.exists():
        shortlist_path = DATA_DIR / f"{date}_s2_shortlist.json"
    if shortlist_path.exists():
        try:
            sl_data = json.loads(shortlist_path.read_text(encoding="utf-8"))
            sl_candidates = sl_data.get("candidates", sl_data.get("shortlist", []))
            # Build tipster lookup by normalized team names
            tipster_lookup: dict[str, int] = {}
            for sc in sl_candidates:
                h = (sc.get("home_team") or sc.get("home") or "").strip().lower()
                a = (sc.get("away_team") or sc.get("away") or "").strip().lower()
                tc = sc.get("tipster_count") or (sc.get("tipster_support") or {}).get("count") or 0
                if h and a and tc:
                    tipster_lookup[f"{h}|{a}"] = tc
            # Inject into analyses
            injected = 0
            for a in analyses:
                h = (a.get("home_team") or "").strip().lower()
                aw = (a.get("away_team") or "").strip().lower()
                key = f"{h}|{aw}"
                tc = tipster_lookup.get(key, 0)
                if tc and not a.get("tipster_count"):
                    a["tipster_count"] = tc
                    injected += 1
            if injected:
                print(f"  → Injected tipster_count into {injected} S3 analyses from shortlist")
        except (json.JSONDecodeError, OSError):
            pass

    # In stats-first mode, process ALL candidates (even without enriched stats cache)
    # since the user verifies odds on Betclic app manually.
    candidates_with_data = [_normalise_s3_to_gate_input(a) for a in analyses if a.get("has_data")]
    if candidates_with_data:
        candidates = candidates_with_data
    else:
        # Stats-first fallback: gate-check all candidates with THIN data quality
        candidates = [_normalise_s3_to_gate_input(a) for a in analyses]

    if not candidates:
        return False, "No candidates for gate check"

    # EV already injected by S4 (_run_odds_eval) — no need to re-inject here

    results = run_gate(candidates, date)

    write_gate_json(results, date)
    write_gate_md(results, date)

    # Dual-write: save gate results to DB
    try:
        from db_data_loader import save_gate_results_to_db
        all_gate = []
        for bucket in ("approved", "extended_pool", "rejected"):
            all_gate.extend(results.get("gate_results", {}).get(bucket, []))
        saved = save_gate_results_to_db(date, all_gate)
        print(f"  → DB: saved {saved} gate results")
    except Exception as e:
        print(f"  ⚠️ DB write failed for gate results (non-fatal): {e}")

    s = results["summary"]
    msg = (
        f"S7 completed: {s['approved_count']} approved, "
        f"{s['extended_count']} extended, {s['rejected_count']} rejected"
    )

    # Verbose per-candidate gate results
    gate = results.get("gate_results", {})
    for pick in gate.get("approved", []):
        home = pick.get("home_team", "?")
        away = pick.get("away_team", "?")
        sport = pick.get("sport", "?")
        tier = pick.get("risk_tier", "?")
        market = (pick.get("best_market") or {}).get("market", "?")
        safety = (pick.get("best_market") or {}).get("safety_score", 0)
        print(f"    ✅ {home} vs {away} [{sport}] — {market} (safety={safety:.2f}, tier={tier})")
    for pick in gate.get("extended_pool", []):
        home = pick.get("home_team", "?")
        away = pick.get("away_team", "?")
        reason = pick.get("gate_fail_reason", "threshold")
        print(f"    📋 {home} vs {away} — EXTENDED ({reason})")
    rejected_count = len(gate.get("rejected", []))
    if rejected_count:
        print(f"    ❌ {rejected_count} candidates rejected")

    if results["gate_results"].get("expansion_needed"):
        msg += " ⚠️ EXPANSION NEEDED (sport diversity)"

    state.setdefault("step_data", {})["s7_approved"] = s["approved_count"]
    state["step_data"]["s7_extended"] = s["extended_count"]

    return True, msg


def _run_s8(date: str, state: dict) -> tuple[bool, str]:
    """S8: Build Coupons."""
    gate_data = None

    # Try DB first
    try:
        from db_data_loader import load_gate_results_from_db
        approved = load_gate_results_from_db(date, status="approved")
        extended = load_gate_results_from_db(date, status="extended")
        rejected = load_gate_results_from_db(date, status="rejected")
        if approved or extended:
            gate_data = {
                "date": date,
                "gate_results": {
                    "approved": approved or [],
                    "extended_pool": extended or [],
                    "rejected": rejected or [],
                },
                "summary": {
                    "approved_count": len(approved or []),
                    "extended_count": len(extended or []),
                    "rejected_count": len(rejected or []),
                },
            }
            print(f"  → DB: loaded {len(approved or [])} approved, {len(extended or [])} extended gate results")
    except Exception as e:
        print(f"  ⚠️ DB read failed for gate results: {e}")

    # JSON fallback
    if gate_data is None:
        gate_path = DATA_DIR / f"{date}_s7_gate_results.json"
        if not gate_path.exists():
            return False, f"S7 gate results not found: {gate_path}"
        gate_data = json.loads(gate_path.read_text(encoding="utf-8"))
    config = load_coupon_config()

    result = build_coupons(gate_data, config)

    write_coupon_markdown(result, date)
    write_coupon_json(result, date)

    # Persist to DB (dual-write)
    try:
        from scripts.coupon_builder import persist_coupons_to_db
    except ImportError:
        from coupon_builder import persist_coupons_to_db
    persist_coupons_to_db(result, date)

    if result.get("no_bet"):
        msg = f"S8: NO BET — {result.get('no_bet_reason', 'insufficient picks')}"
    else:
        core_count = len(result.get("core_coupons", []))
        combo_count = len(result.get("combos", []))
        singles_count = len(result.get("singles", []))
        summary = result.get("summary", {})
        msg = f"S8 completed: {core_count} core coupons, {combo_count} combos, {singles_count} singles"

        # Verbose coupon details
        for coup in result.get("core_coupons", []):
            legs = len(coup.get("legs", []))
            odds = coup.get("combined_odds", 0)
            stake = coup.get("stake", 0)
            tier = coup.get("tier", "?")
            print(f"    🎫 {coup.get('id', '?')}: {legs} legs @{odds:.2f} — stake {stake:.2f} PLN [{tier}]")
        if summary:
            print(f"    💰 Total spend: {summary.get('total_spend', 0):.2f} PLN | Potential return: {summary.get('total_potential_return', 0):.2f} PLN")

    state.setdefault("step_data", {})["s8_core"] = len(result.get("core_coupons", []))
    state["step_data"]["s8_combos"] = len(result.get("combos", []))
    state["step_data"]["s8_no_bet"] = result.get("no_bet", False)

    return True, msg


def _run_s9(date: str, state: dict) -> tuple[bool, str]:
    """S9: Validate coupons."""
    coupon_file = COUPON_DIR / f"{date}.md"
    if not coupon_file.exists():
        return True, "S9: No coupon file to validate (NO BET day?)"

    try:
        from scripts.validate_coupons import validate_file
    except ImportError:
        from validate_coupons import validate_file

    ledger_path = ROOT_DIR / "betting" / "journal" / "picks-ledger.csv"
    result = validate_file(coupon_file, ledger_path)

    errors = result.get("global_errors", [])
    for check in result.get("checks", []):
        errors.extend(check.get("errors", []))
    warnings = []
    for check in result.get("checks", []):
        warnings.extend(check.get("warnings", []))

    if errors:
        msg = f"S9: {len(errors)} validation errors, {len(warnings)} warnings"
        for e in errors[:5]:
            msg += f"\n  ✗ {e}"
        return False, msg

    msg = f"S9 passed: {result.get('coupons_found', 0)} coupons validated, {len(warnings)} warnings"
    return True, msg


def _run_s10(date: str, state: dict) -> tuple[bool, str]:
    """S10: Final summary with full pipeline metrics."""
    step_data = state.get("step_data", {})

    # Calculate pipeline duration
    started = state.get("started_at", "")
    now_str = datetime.now(ZoneInfo("Europe/Warsaw")).isoformat()
    duration = "?"
    if started:
        try:
            start_dt = datetime.fromisoformat(started)
            end_dt = datetime.now(ZoneInfo("Europe/Warsaw"))
            elapsed = end_dt - start_dt
            minutes = int(elapsed.total_seconds() // 60)
            seconds = int(elapsed.total_seconds() % 60)
            duration = f"{minutes}m {seconds}s"
        except Exception:
            pass

    summary_lines = [
        "",
        "═══════════════════════════════════════════════════════════",
        f"  PIPELINE COMPLETE — {date}",
        f"  Duration: {duration}",
        "═══════════════════════════════════════════════════════════",
        "",
        "📊 ANALYSIS SUMMARY:",
        f"  S3 Deep Stats: {step_data.get('s3_with_data', '?')}/{step_data.get('s3_count', '?')} candidates analyzed",
        f"  S7 Gate: {step_data.get('s7_approved', '?')} approved, {step_data.get('s7_extended', '?')} extended",
    ]

    if step_data.get("s8_no_bet"):
        summary_lines.append("  S8 Coupons: NO BET DAY")
    else:
        summary_lines.append(
            f"  S8 Coupons: {step_data.get('s8_core', '?')} core, {step_data.get('s8_combos', '?')} combos"
        )

    # Parallel enrichment results
    parallel = step_data.get("parallel_results", {})
    if parallel:
        enrichment_parts = []
        for name, ok in parallel.items():
            enrichment_parts.append(f"{name}: {'✓' if ok else '✗'}")
        summary_lines.append(f"  Enrichment: {', '.join(enrichment_parts)}")

    # Step completion status
    steps_status = state.get("steps", {})
    completed = sum(1 for v in steps_status.values() if isinstance(v, dict) and v.get("status") == "completed")
    failed = sum(1 for v in steps_status.values() if isinstance(v, dict) and v.get("status") == "failed")
    skipped = sum(1 for v in steps_status.values() if isinstance(v, dict) and v.get("status") == "skipped")
    summary_lines.extend([
        "",
        f"📋 STEPS: {completed} completed, {failed} failed, {skipped} skipped",
    ])

    # Errors summary
    errors = state.get("errors", [])
    if errors:
        summary_lines.append(f"  ⚠ {len(errors)} errors logged:")
        for err in errors[-3:]:
            summary_lines.append(f"    - {err[:120]}")

    # Build list of agent checkpoints that completed
    agent_checkpoints = []
    for step in PIPELINE_STEPS:
        agent = step.get("agent_review_required")
        if agent:
            step_status = state.get("steps", {}).get(step["id"], {}).get("status", "")
            if step_status == "completed":
                agent_checkpoints.append((step["id"], agent, step.get("agent_task", "")))

    summary_lines.extend([
        "",
        "📁 OUTPUT FILES:",
        f"  📊 betting/data/{date}_s3_deep_stats.md",
        f"  ✅ betting/data/{date}_s7_gate_results.md",
        f"  🎫 betting/coupons/{date}.md",
        f"  📦 betting/coupons/{date}.json",
    ])

    if agent_checkpoints:
        summary_lines.extend([
            "",
            "═══════════════════════════════════════════════════════════",
            "🤖 AGENT REVIEW CHECKPOINTS (MANDATORY — DO NOT SKIP)",
            "═══════════════════════════════════════════════════════════",
            "",
            "The pipeline produced RAW DATA. The orchestrator MUST now",
            "spawn specialist agents for deep analysis at each checkpoint:",
            "",
        ])
        for step_id, agent, task in agent_checkpoints:
            summary_lines.append(f"  [{step_id}] → {agent}: {task}")
        summary_lines.extend([
            "",
            "Script output is NOT final analysis. Agents add: edge",
            "discovery, cross-source verification, bear cases, strategic",
            "reasoning, and Polish-language coupon descriptions.",
            "═══════════════════════════════════════════════════════════",
        ])
    else:
        summary_lines.append("")
        summary_lines.append("═══════════════════════════════════════════════════════════")

    msg = "\n".join(summary_lines)
    print(msg)

    state["completed_at"] = now_str

    return True, msg


def run_python_step(step_id: str, date: str, state: dict) -> tuple[bool, str]:
    """Dispatch to the correct Python-driven pipeline step."""
    try:
        if step_id == "s1_scan":
            return _run_scan_events(date, state)
        elif step_id == "s1b_parallel":
            return _run_parallel_enrichment(date, state)
        elif step_id == "s2_tipster":
            return _run_tipster_xref(date, state)
        elif step_id == "s3_deep_stats":
            return _run_s3(date, state)
        elif step_id == "s4_odds_eval":
            return _run_odds_eval(date, state)
        elif step_id == "s5_context":
            return _run_context_checks(date, state)
        elif step_id == "s6_upset_risk":
            return _run_upset_risk(date, state)
        elif step_id == "s7_gate":
            return _run_s7(date, state)
        elif step_id == "s8_coupons":
            return _run_s8(date, state)
        elif step_id == "s9_validate":
            return _run_s9(date, state)
        elif step_id == "s10_summary":
            return _run_s10(date, state)
        else:
            return False, f"Unknown python step: {step_id}"
    except Exception as e:
        import traceback

        return False, f"{e}\n{traceback.format_exc()}"


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------
def print_status(state: dict):
    """Print current pipeline status."""
    print(f"\n{'='*60}")
    print(f"Pipeline Status — {state['date']}")
    print(f"{'='*60}")
    print(f"Session: {state.get('session', 'full')}")
    print(f"Version: {state.get('version', 'v1')}")
    print(f"Pass: {state.get('pass_number', 1)}")
    print(f"Started: {state.get('started_at', 'N/A')}")
    print(f"Completed: {state.get('completed_at', 'N/A')}")
    print(f"Current step: {state.get('current_step', 'N/A')}")
    print()

    for step in PIPELINE_STEPS:
        step_state = state.get("steps", {}).get(step["id"], {})
        status = step_state.get("status", "pending")
        marker = {
            "pending": "○",
            "running": "►",
            "completed": "✓",
            "failed": "✗",
            "skipped": "–",
            "completed_with_warnings": "⚠",
        }.get(status, "?")
        print(f"  {marker} {step['name']} — {status}")
        if step_state.get("error"):
            print(f"    Error: {step_state['error'][:100]}")

    errors = state.get("errors", [])
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for err in errors[-5:]:
            print(f"  - {err}")

    step_data = state.get("step_data", {})
    if step_data:
        print("\nStep data:")
        for k, v in step_data.items():
            print(f"  {k}: {v}")
    print()


# ---------------------------------------------------------------------------
# Main pipeline loop
# ---------------------------------------------------------------------------
def run_pipeline(
    date: str,
    session: str = "full",
    resume: bool = False,
    single_step: str | None = None,
    phase: str | None = None,
    version: str | None = None,
    skip_scan: bool = False,
    top: int | None = None,
):
    """Run the full pipeline or a single step/phase."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        print(f"[FATAL] Invalid date format: {date} (expected YYYY-MM-DD)")
        sys.exit(1)

    state = load_state(date)

    if not resume:
        state["session"] = session
        state["started_at"] = datetime.now(ZoneInfo("Europe/Warsaw")).isoformat()
        if version:
            state["version"] = version

    # Store CLI args for use by python steps
    state.setdefault("cli_args", {})
    if top:
        state["cli_args"]["top"] = top

    config = load_config()

    print(f"\n{'='*60}")
    print("BETTING PIPELINE ORCHESTRATOR")
    print(f"{'='*60}")
    print(f"Date: {date}")
    print(f"Session: {session}")
    print(f"Version: {state.get('version', 'v1')}")
    bankroll = config.get('bankroll_pln', config.get('working_bankroll_pln', 'N/A'))
    daily_budget = config.get('daily_exposure_range', config.get('suggested_daily_allocation_range_pln', 'N/A'))
    print(f"Bankroll: {bankroll} PLN")
    print(f"Daily budget: {daily_budget} PLN")
    print(f"Resume: {resume}")
    print(f"Skip scan: {skip_scan}")
    if top:
        print(f"Top candidates: {top}")
    print(f"{'='*60}\n")

    steps_to_run = PIPELINE_STEPS
    if single_step:
        steps_to_run = [s for s in PIPELINE_STEPS if s["id"] == single_step]
        if not steps_to_run:
            print(f"Unknown step: {single_step}")
            print(f"Available steps: {', '.join(s['id'] for s in PIPELINE_STEPS)}")
            return
    elif phase:
        phase_ids = PHASE_STEPS.get(phase, set())
        steps_to_run = [s for s in PIPELINE_STEPS if s["id"] in phase_ids]
        if not steps_to_run:
            print(f"No steps found for phase: {phase}")
            return
        print(f"[phase] Running {phase} phase: {', '.join(s['id'] for s in steps_to_run)}")

    for step in steps_to_run:
        step_id = step["id"]
        step_state = state.get("steps", {}).setdefault(step_id, {})

        # Skip already completed steps in resume mode
        if resume and step_state.get("status") == "completed":
            print(f"[skip] {step['name']} — already completed")
            continue

        # Skip scan-phase steps when --skip-scan is set
        if skip_scan and step_id in SCAN_STEP_IDS:
            step_state["status"] = "skipped"
            print(f"[skip] {step['name']} — --skip-scan")
            save_state(date, state)
            continue

        print(f"\n{'─'*60}")
        print(f"[{step_id}] {step['name']}")
        print(f"  {step.get('description', '')}")
        print(f"{'─'*60}")

        step_state["status"] = "running"
        step_state["started_at"] = datetime.now(ZoneInfo("Europe/Warsaw")).isoformat()
        state["current_step"] = step_id
        save_state(date, state)

        if "python_step" in step:
            success, output = run_python_step(step_id, date, state)
        elif "commands" in step and step["commands"]:
            # Skip s1d/s1e if outputs already exist AND we're in resume mode
            date_compact = date.replace("-", "")
            skip_reason = None
            if resume and step_id == "s1d_matrix" and (DATA_DIR / f"market_matrix_{date}.json").exists():
                skip_reason = "market_matrix already exists (resume mode)"
            elif resume and step_id == "s1e_shortlist" and (DATA_DIR / f"{date_compact}_s2_shortlist.json").exists():
                skip_reason = "shortlist already exists (resume mode)"
            if skip_reason:
                success = True
                output = f"Skipped ({skip_reason})"
                print(f"  ⏭ {output}")
            else:
                all_success = True
                outputs = []
                for cmd in step["commands"]:
                    cmd_ok, cmd_out = run_command(cmd, date, step_id=step_id)
                    outputs.append(cmd_out)
                    if not cmd_ok:
                        all_success = False
                        break
                success = all_success
                output = "\n".join(outputs)
        else:
            success = True
            output = "No-op step"

        if success:
            step_state["status"] = "completed"
            step_state["completed_at"] = datetime.now(ZoneInfo("Europe/Warsaw")).isoformat()
            step_state["output_summary"] = output[:500] if output else ""
            print(f"  ✓ {output[:200] if output else 'Done'}")

            # Print agent review banner for steps that require specialist agent analysis
            agent_required = step.get("agent_review_required")
            if agent_required:
                agent_task = step.get("agent_task", "Deep analysis required")
                print(f"\n  {'='*60}")
                print(f"  [AGENT-REVIEW-REQUIRED] Agent: {agent_required}")
                print(f"  Task: {agent_task}")
                print(f"  Step {step_id} produced RAW DATA. Orchestrator MUST now spawn")
                print(f"  the {agent_required} agent via runSubagent to perform deep analysis.")
                print(f"  Script output is NOT final — agent analysis is MANDATORY.")
                print(f"  {'='*60}\n")

            # Note: source health for s1_scan is recorded inside _run_scan_events()

            # Check expected output files for command steps
            missing = check_outputs(step)
            if missing:
                print(f"  ⚠ Missing expected outputs: {missing}")
        else:
            step_state["status"] = "failed"
            step_state["error"] = output[-500:] if output else "Unknown error"
            state["errors"].append(f"{step_id}: {output[-200:] if output else 'Error'}")

            is_critical = step.get("critical", "python_step" in step)
            if is_critical:
                print(f"\n  ✗ CRITICAL FAILURE — pipeline stopped")
                save_state(date, state)
                print_status(state)
                return
            else:
                print(f"  ⚠ Non-critical failure, continuing")

        save_state(date, state)

    print_status(state)

    completed = sum(
        1
        for s in PIPELINE_STEPS
        if state.get("steps", {}).get(s["id"], {}).get("status", "").startswith("completed")
    )
    print(f"Steps completed: {completed}/{len(PIPELINE_STEPS)}")


# ---------------------------------------------------------------------------
# Phase definitions: which steps belong to which phase
# ---------------------------------------------------------------------------
PHASE_STEPS = {
    "data": {"s0_settle", "s1_scan", "s1_ingest", "s1a_discover", "s1b_parallel", "s1c_aggregate", "s1d_matrix", "s1e_shortlist", "s2_tipster"},
    "analysis": {"s3_deep_stats", "s4_odds_eval", "s5_context", "s6_upset_risk", "s7_gate"},
    "build": {"s8_coupons", "s9_validate", "s10_summary"},
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Betting Pipeline Orchestrator")
    parser.add_argument("--date", help="Betting date (YYYY-MM-DD)")
    parser.add_argument("--session", default="full", choices=["full", "day", "night", "morning"])
    parser.add_argument("--resume", action="store_true", help="Resume from last completed step")
    parser.add_argument("--step", help="Run a single step by ID")
    parser.add_argument("--phase", choices=["data", "analysis", "build"],
                        help="Run only steps in this phase (data=S0-S2, analysis=S3-S7, build=S8-S10)")
    parser.add_argument("--version", help="Pipeline version (v1, v2, etc.)")
    parser.add_argument("--status", action="store_true", help="Show current pipeline status")
    parser.add_argument("--list-steps", action="store_true", help="List all pipeline steps")
    parser.add_argument("--skip-scan", action="store_true", help="Skip S0/S1 scan steps (re-run analysis only)")
    parser.add_argument("--top", type=int, help="Limit S3 candidates (default: all)")
    args = parser.parse_args()

    if args.list_steps:
        print("Pipeline Steps:")
        for step in PIPELINE_STEPS:
            kind = " [PY]" if "python_step" in step else " [SH]"
            critical_tag = " ★" if step.get("critical", "python_step" in step) else ""
            phase_tag = ""
            for phase_name, phase_ids in PHASE_STEPS.items():
                if step["id"] in phase_ids:
                    phase_tag = f" [{phase_name}]"
                    break
            print(f"  {step['id']:18s} {step['name']}{kind}{critical_tag}{phase_tag}")
        return

    if args.status:
        if not args.date:
            now = datetime.now(ZoneInfo("Europe/Warsaw"))
            args.date = now.strftime("%Y-%m-%d")
        state = load_state(args.date)
        print_status(state)
        return

    if not args.date:
        now = datetime.now(ZoneInfo("Europe/Warsaw"))
        args.date = now.strftime("%Y-%m-%d")

    run_pipeline(
        date=args.date,
        session=args.session,
        resume=args.resume,
        single_step=args.step,
        phase=args.phase,
        version=args.version,
        skip_scan=args.skip_scan,
        top=args.top,
    )


if __name__ == "__main__":
    main()