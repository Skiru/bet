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
import time
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
# Module imports
# ---------------------------------------------------------------------------
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))

from bet.config import get_tz
from deep_stats_report import generate_deep_stats
from gate_checker import (
    run_gate,
    _normalise_s3_to_gate_input,
    _write_json as write_gate_json,
    _write_markdown as write_gate_md,
)
from coupon_builder import (
    build_coupons,
    write_coupon_markdown,
    write_coupon_json,
    load_config as load_coupon_config,
)
from odds_evaluator import run_odds_eval as _run_odds_eval, _convert_espn_odds_to_decimal
from context_checks import run_context_checks as _run_context_checks
from upset_risk import run_upset_risk as _run_upset_risk
from tipster_xref import run_tipster_xref as _run_tipster_xref
from pipeline_summary import run_summary as _run_s10
from agent_protocol import write_step_output, read_agent_review, merge_agent_enrichments, STEP_AGENT_CONFIG

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resolve_shortlist_path(date: str) -> Path | None:
    """Resolve shortlist path, trying YYYY-MM-DD then YYYYMMDD format."""
    p = DATA_DIR / f"{date}_s2_shortlist.json"
    if p.exists():
        return p
    compact = date.replace("-", "")
    p2 = DATA_DIR / f"{compact}_s2_shortlist.json"
    if p2.exists():
        return p2
    return None


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

# Per-step timeout in seconds (prevents hanging on slow sources)
STEP_TIMEOUTS = {
    "s0_settle": 180,      # 3 min
    "s1_scan": 1200,       # 20 min (parallel per-sport scan — each sport has independent timeout)
    "s1_ingest": 180,      # 3 min (ingest scan data into stats cache)
    "s1_html_deep": 300,   # 5 min (deep HTML parsing from snapshots)
    "s1a_discover": 600,   # 10 min (DB persistence with caching)
    "s1a_espn": 300,       # 5 min (ESPN API — has internal 480s timeout, subprocess caps at 5min)
    "s1b_parallel": 600,   # 10 min (odds + weather + tipsters in parallel)
    "s1c_aggregate": 300,  # 5 min (45K events with dedup)
    "s1d_matrix": 120,     # 2 min
    "s1e_shortlist": 120,  # 2 min
    "s2_tipster": 60,      # 1 min (data loading only)
    "s2_5_enrich": 900,    # 15 min (internet enrichment with Playwright)
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
        "description": "Settle previous day (if applicable) + evaluate decisions + Betclic history analysis (§0.2 MANDATORY) + data rotation",
        "commands": [
            "python3 scripts/settle_on_finish.py --betting-day {prev_date} --no-poll",
            "python3 scripts/evaluate_decisions.py --date {prev_date}",
            "python3 scripts/analyze_betclic_learning.py",
            "python3 scripts/data_rotation.py --execute --days 30",
            "python3 scripts/build_league_profiles.py",
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
        "name": "S1-ingest: Ingest Scan Stats",
        "description": "Ingest Playwright HTML data into stats cache",
        "commands": [
            "python3 scripts/ingest_scan_stats.py",
        ],
        "outputs": [],
        "critical": False,
    },
    {
        "id": "s1_html_deep",
        "name": "S1-deep: HTML Deep Parsing",
        "description": "Deep-parse saved HTML snapshots for rich stats (corners HT/FT, dangerous attacks, match IDs, odds, team averages)",
        "commands": [
            "python3 scripts/html_deep_parser.py --date {date} --report",
        ],
        "outputs": [],
        "critical": False,
        "agent_review_required": "bet-scanner",
        "agent_task": "Validate deep parsing verdicts per domain: verify CSS selectors match current HTML, spot-check extracted values against source snapshots, flag broken profiles",
    },
    {
        "id": "s1a_discover",
        "name": "S1a: Discover Fixtures + API Stats + Tennis Enrichment",
        "description": "API fixture discovery + stats enrichment + deep tennis data (run independently of scan)",
        "commands": [
            "python3 scripts/discover_fixtures.py --date {date}",
            "python3 scripts/fetch_api_stats.py --date {date}",
            "python3 scripts/enrich_tennis_stats.py --date {date} --all-indexed",
        ],
        "outputs": [],
        "critical": False,
        "retries": 1,
    },
    {
        "id": "s1a_espn",
        "name": "S1a-ESPN: Seed ESPN Deep Data",
        "description": "Seed ATS/OU records, standings, power index, predictions from ESPN API (skip lengthy player gamelogs)",
        "commands": [
            "python3 scripts/seed_espn_data.py --skip-players",
        ],
        "outputs": [],
        "critical": False,
        "retries": 1,
    },
    {
        "id": "s1b_parallel",
        "name": "S1b: Odds + Weather + Tipsters (PARALLEL)",
        "description": "Fetch odds, weather, and tipster data concurrently",
        "python_step": "parallel_enrichment",
        "critical": False,
        "retries": 1,
    },
    {
        "id": "s1c_aggregate",
        "name": "S1c: Aggregate + Deep Analysis Pool",
        "description": "Aggregate scan results + generate analysis candidate pool",
        "commands": [
            "python3 scripts/aggregate_and_select.py --date {date}",
            "python3 scripts/deep_analysis_pool.py --date {date}",
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
        "agent_task": "Review shortlist for sport diversity (≥8 sports), KEY sport coverage (≥60% Football/Tennis/Basketball/Volleyball), verify ALL candidates are included (NO artificial caps), flag missing major leagues",
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
        "id": "s2_5_enrich",
        "name": "S2.5: Data Enrichment",
        "description": "Self-healing enrichment — fetch missing team stats from internet sources (Flashscore/Sofascore/ESPN) for shortlisted candidates without data",
        "python_step": "data_enrichment",
        "critical": False,
        "retries": 1,
        "agent_review_required": "bet-enricher",
        "agent_task": "Review enrichment yield, identify sports/leagues with persistent data gaps, suggest alternative sources for failed enrichments",
    },
    {
        "id": "s3_deep_stats",
        "name": "S3: Deep Statistical Analysis",
        "description": "Per-candidate §3.0 analysis with L10/H2H/L5 stats (enrichment-aware, no smart filter)",
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
        "name": "S7: 18-Point Advisory Gate",
        "description": "Run gate checks, assign advisory tiers (STRONG/MODERATE/WEAK/FLAGGED) — no auto-rejection",
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
# Steps skipped by --skip-scan: ONLY the Playwright browser scan + HTML parsing.
# API discovery (s1a_discover), ESPN (s1a_espn), odds/weather/tipsters (s1b_parallel),
# aggregation (s1c), matrix (s1d), and shortlist (s1e) still run — they use APIs, not browsers.
SCAN_STEP_IDS = {"s1_scan", "s1_ingest", "s1_html_deep"}


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
    # Strip trailing || true (bash ignore-failure syntax) — not needed since
    # the pipeline_step runner already handles non-critical command failures.
    ignore_failure = False
    if cmd.rstrip().endswith("|| true"):
        cmd = cmd.rstrip().removesuffix("|| true").rstrip()
        ignore_failure = True
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
            if ignore_failure:
                print(f"  ⚠ Command failed (exit {result.returncode}) — ignored (non-critical)")
                return True, output
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
# Python-driven step implementations
# ---------------------------------------------------------------------------

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


def _run_parallel_scan(date: str) -> dict:
    """Run all sport scanners in parallel with independent timeouts."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from scanners import get_all_scanners
    from scanners.domain_semaphore import DomainSemaphoreMap
    from scanners.merge_results import merge_scan_results

    semaphore_map = DomainSemaphoreMap()
    scanners = get_all_scanners()

    # Inject ZawodTyper daily URL into football scanner
    from datetime import datetime as dt
    now = dt.now(get_tz())
    pl_months = ["", "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
                 "lipca", "sierpnia", "wrzesnia", "pazdziernika", "listopada", "grudnia"]
    pl_days_list = ["", "poniedzialek", "wtorek", "sroda", "czwartek", "piatek", "sobota", "niedziela"]
    zt_url = f"https://www.zawodtyper.pl/typy-dnia-{now.day}-{pl_months[now.month]}-{pl_days_list[now.isoweekday()]}/"
    for scanner in scanners:
        if scanner.scanner_group == "football" and hasattr(scanner, "_extra_urls"):
            scanner._extra_urls.append(zt_url)
            break
    else:
        # If no _extra_urls attribute, log it
        print(f"  → ZawodTyper URL: {zt_url} (will be used in legacy fallback)")

    results = {}

    # Record per-sport sub-steps in DB
    try:
        sys.path.insert(0, str(ROOT_DIR / "src"))
        from bet.db.connection import get_db
        from bet.db.repositories import PipelineRepo
        _has_db = True
    except ImportError:
        _has_db = False

    with ThreadPoolExecutor(max_workers=len(scanners)) as executor:
        futures = {
            executor.submit(scanner.scan, date, semaphore_map): scanner.scanner_group
            for scanner in scanners
        }
        for future in as_completed(futures):
            group = futures[future]
            try:
                stats = future.result(timeout=600)  # 10 min max per scanner
                results[group] = {
                    "status": "completed",
                    "events_found": getattr(stats, "events_found", 0),
                    "sources_ok": getattr(stats, "sources_ok", 0),
                    "sources_failed": getattr(stats, "sources_failed", 0),
                    "duration_sec": getattr(stats, "duration_seconds", 0),
                    "validation_passed": getattr(stats, "validation_passed", True),
                    "gaps": getattr(stats, "gaps_description", []),
                }
                print(f"    ✓ {group}: {results[group]['events_found']} events ({results[group]['duration_sec']:.1f}s, {results[group]['sources_ok']} sources OK, {results[group]['sources_failed']} failed)")
                # Record per-sport sub-step
                if _has_db:
                    try:
                        with get_db() as conn:
                            repo = PipelineRepo(conn)
                            repo.start_step(date, f"s1_scan.{group}")
                            repo.complete_step(date, f"s1_scan.{group}", results[group])
                            conn.commit()
                    except Exception:
                        pass
            except Exception as e:
                results[group] = {"status": "failed", "error": str(e)}
                print(f"    ✗ {group}: {e}")
                if _has_db:
                    try:
                        with get_db() as conn:
                            repo = PipelineRepo(conn)
                            repo.start_step(date, f"s1_scan.{group}")
                            repo.fail_step(date, f"s1_scan.{group}", str(e))
                            conn.commit()
                    except Exception:
                        pass

    # Retry failed sport groups once with increased timeout
    failed_groups = [g for g, r in results.items() if r.get("status") == "failed"]
    if failed_groups:
        print(f"  → Retrying {len(failed_groups)} failed groups: {', '.join(failed_groups)}")
        retry_scanners = [s for s in scanners if s.scanner_group in failed_groups]
        with ThreadPoolExecutor(max_workers=len(retry_scanners)) as executor:
            futures = {
                executor.submit(scanner.scan, date, semaphore_map): scanner.scanner_group
                for scanner in retry_scanners
            }
            for future in as_completed(futures):
                group = futures[future]
                try:
                    stats = future.result(timeout=900)  # Extended timeout for retry
                    results[group] = {
                        "status": "completed",
                        "events_found": getattr(stats, "events_found", 0),
                        "sources_ok": getattr(stats, "sources_ok", 0),
                        "sources_failed": getattr(stats, "sources_failed", 0),
                        "duration_sec": getattr(stats, "duration_seconds", 0),
                        "validation_passed": getattr(stats, "validation_passed", True),
                        "gaps": getattr(stats, "gaps_description", []),
                        "retry": True,
                    }
                    print(f"    ✓ {group} (retry): {results[group]['events_found']} events")
                except Exception as e:
                    results[group]["retry_error"] = str(e)
                    print(f"    ✗ {group} (retry): {e}")

    # Merge all results into scan_summary.json
    merge_scan_results(date)
    return results


def _run_scan_events(date: str, state: dict) -> tuple[bool, str]:
    """S1: Run Playwright event scan using parallel per-sport scanners.

    Each sport scanner runs independently with its own timeout.
    Falls back to monolithic scan if per-sport scanners fail to import.
    """
    from datetime import datetime as dt

    # Try parallel sport dispatch first
    try:
        results = _run_parallel_scan(date)
        total_events = sum(r.get("events_found", 0) for r in results.values() if r.get("status") == "completed")
        completed = [g for g, r in results.items() if r.get("status") == "completed"]
        failed = [g for g, r in results.items() if r.get("status") == "failed"]

        state.setdefault("step_data", {})["s1_events"] = total_events
        state["step_data"]["s1_sport_results"] = results
        state["step_data"]["s1_completed_groups"] = completed
        state["step_data"]["s1_failed_groups"] = failed

        # Log per-sport summary
        print(f"  [parallel-sport] {len(completed)}/{len(results)} groups completed, {total_events} total events")
        if failed:
            print(f"  [parallel-sport] Failed groups: {', '.join(failed)}")

        # Record source health after scan
        _run_source_health(date)

        if not completed:
            return False, "All sport scanners failed"
        return True, f"Parallel scan: {total_events} events from {len(completed)} sport groups ({', '.join(failed)} failed)" if failed else f"Parallel scan: {total_events} events from {len(completed)} sport groups"
    except ImportError as e:
        print(f"  ⚠ Parallel scanners not available ({e}), falling back to monolithic scan")
    except Exception as e:
        print(f"  ⚠ Parallel scan failed ({e}), falling back to monolithic scan")

    # Fallback: monolithic scan (legacy behavior)
    now = dt.now(get_tz())
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
            for sport in ["football", "basketball", "hockey"]:
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

            # Save ESPN odds to DB
            try:
                from bet.db.connection import get_db
                from bet.db.repositories import OddsRepo, FixtureRepo, SportRepo
                from bet.db.models import OddsRecord as OddsRec
                with get_db() as conn:
                    odds_repo = OddsRepo(conn)
                    fixture_repo = FixtureRepo(conn)
                    sport_repo = SportRepo(conn)
                    saved_count = 0
                    for item in enrichment["odds"]:
                        odds_dec = item.get("odds_decimal", {})
                        home = item.get("home_team", item.get("home", ""))
                        away = item.get("away_team", item.get("away", ""))
                        sport_name = item.get("sport", "")
                        if not home or not away or not sport_name:
                            continue
                        sport_obj = sport_repo.get_by_name(sport_name)
                        if not sport_obj:
                            continue
                        fixture = fixture_repo.get_by_teams_and_date(
                            home, away, date, sport_obj.id
                        )
                        if not fixture:
                            continue
                        # Save moneyline odds
                        ml = odds_dec.get("moneyline", {})
                        for side in ("home", "away", "draw"):
                            if side in ml:
                                odds_repo.upsert(OddsRec(
                                    id=None,
                                    fixture_id=fixture.id,
                                    bookmaker="ESPN/DraftKings",
                                    market="h2h",
                                    selection=side,
                                    odds=ml[side],
                                ))
                                saved_count += 1
                        # Save totals odds
                        total = odds_dec.get("total", {})
                        if total.get("line"):
                            for side in ("over", "under"):
                                if side in total:
                                    odds_repo.upsert(OddsRec(
                                        id=None,
                                        fixture_id=fixture.id,
                                        bookmaker="ESPN/DraftKings",
                                        market="totals",
                                        selection=side,
                                        odds=total[side],
                                        line=float(total["line"]),
                                    ))
                                    saved_count += 1
                    conn.commit()
                    if saved_count:
                        print(f"  → ESPN DB: saved {saved_count} odds records")
            except Exception as e:
                print(f"  ⚠ ESPN DB save failed (non-fatal): {e}")

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


def _run_data_enrichment(date: str, state: dict) -> tuple[bool, str]:
    """S2.5: Self-healing data enrichment for shortlisted candidates missing stats.

    Reads the shortlist, identifies teams without cached data, and uses the
    data enrichment agent to fetch stats from internet sources (Flashscore,
    Sofascore, ESPN). Results are saved to DB + JSON cache so that S3 deep
    stats analysis can find them.
    """
    try:
        from data_enrichment_agent import batch_enrich, _detect_missing_from_shortlist
    except ImportError as e:
        return True, f"Enrichment agent not available ({e}), skipping"

    shortlist_path = resolve_shortlist_path(date)
    if not shortlist_path:
        return True, "No shortlist found, skipping enrichment"

    try:
        missing = _detect_missing_from_shortlist(date)
        if not missing:
            return True, "All shortlisted teams have data, no enrichment needed"

        print(f"  → Enriching {len(missing)} teams with missing data")
        results = batch_enrich(missing, max_workers=4)

        enriched = sum(1 for r in results if r.get("status") == "enriched")
        partial = sum(1 for r in results if r.get("status") == "partial")
        failed = sum(1 for r in results if r.get("status") == "failed")

        state.setdefault("step_data", {})["s2_5_enrichment"] = {
            "teams_attempted": len(missing),
            "enriched": enriched,
            "partial": partial,
            "failed": failed,
        }

        return True, f"Enrichment: {enriched} enriched, {partial} partial, {failed} failed (from {len(missing)} teams)"
    except Exception as e:
        return True, f"Enrichment failed (non-critical): {e}"


def _run_s3(date: str, state: dict) -> tuple[bool, str]:
    """S3: Deep Statistical Analysis with probability engine integration."""
    resolved = resolve_shortlist_path(date)
    shortlist_path = str(resolved) if resolved else None

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
    shortlist_path = resolve_shortlist_path(date)
    if shortlist_path:
        try:
            sl_data = json.loads(shortlist_path.read_text(encoding="utf-8"))
            sl_candidates = sl_data.get("candidates", sl_data.get("shortlist", []))
            # Build tipster lookup by normalized team names
            tipster_lookup: dict[str, int] = {}
            for sc in sl_candidates:
                h = (sc.get("home_team") or "").strip().lower()
                a = (sc.get("away_team") or "").strip().lower()
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
        from coupon_builder import persist_coupons_to_db
        persist_coupons_to_db(result, date)
    except Exception as e:
        print(f"  [warn] DB persist failed: {e}")

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
        from validate_coupons import validate_file
    except ImportError:
        return True, "S9: validate_coupons not available"

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


def run_python_step(step_id: str, date: str, state: dict) -> tuple[bool, str]:
    """Dispatch to the correct Python-driven pipeline step."""
    try:
        if step_id == "s1_scan":
            return _run_scan_events(date, state)
        elif step_id == "s1b_parallel":
            return _run_parallel_enrichment(date, state)
        elif step_id == "s2_tipster":
            return _run_tipster_xref(date, state)
        elif step_id == "s2_5_enrich":
            return _run_data_enrichment(date, state)
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
        state["started_at"] = datetime.now(get_tz()).isoformat()
        if version:
            state["version"] = version
    else:
        # Reset stuck "running" steps to "pending" so they re-run properly
        for sid, info in state.get("steps", {}).items():
            if isinstance(info, dict) and info.get("status") == "running":
                print(f"[resume] Resetting stuck step {sid} from 'running' to 'pending'")
                info["status"] = "pending"
                info.pop("started_at", None)

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

        # --- Agent protocol: ingest review from previous step (if any) ---
        if step_id in STEP_AGENT_CONFIG:
            # Find the previous step that has agent config
            prev_agent_steps = [s["id"] for s in steps_to_run
                                if s["id"] in STEP_AGENT_CONFIG
                                and steps_to_run.index(s) < steps_to_run.index(step)]
            if prev_agent_steps:
                prev_step_id = prev_agent_steps[-1]
                prev_review = read_agent_review(date, prev_step_id)
                if prev_review:
                    merge_agent_enrichments(state, prev_review)
                    print(f"  [agent] Loaded review from {prev_review.get('agent', '?')} for {prev_step_id}")

        print(f"\n{'─'*60}")
        print(f"[{step_id}] {step['name']}")
        print(f"  {step.get('description', '')}")
        print(f"{'─'*60}")

        step_state["status"] = "running"
        step_state["started_at"] = datetime.now(get_tz()).isoformat()
        state["current_step"] = step_id
        save_state(date, state)

        if "python_step" in step:
            success, output = run_python_step(step_id, date, state)
        elif "commands" in step and step["commands"]:
            # Skip s1d/s1e if outputs already exist AND we're in resume mode
            skip_reason = None
            if resume and step_id == "s1d_matrix" and (DATA_DIR / f"market_matrix_{date}.json").exists():
                skip_reason = "market_matrix already exists (resume mode)"
            elif resume and step_id == "s1e_shortlist" and resolve_shortlist_path(date):
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

        # Retry logic for failed non-critical steps with retries configured
        max_retries = step.get("retries", 0)
        if not success and max_retries > 0:
            backoff_delays = [5, 15, 45]  # seconds
            for attempt in range(1, max_retries + 1):
                delay = backoff_delays[min(attempt - 1, len(backoff_delays) - 1)]
                print(f"  ↻ Retry {attempt}/{max_retries} in {delay}s...")
                time.sleep(delay)

                if "python_step" in step:
                    success, output = run_python_step(step_id, date, state)
                elif "commands" in step and step["commands"]:
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

                step_state["retries_used"] = attempt
                if success:
                    print(f"  ✓ Retry {attempt} succeeded")
                    break
                else:
                    print(f"  ✗ Retry {attempt} failed")

        if success:
            step_state["status"] = "completed"
            step_state["completed_at"] = datetime.now(get_tz()).isoformat()
            step_state["output_summary"] = output[:500] if output else ""
            print(f"  ✓ {output[:200] if output else 'Done'}")

            # Resume invalidation: when a DATA-CHANGING upstream step re-runs,
            # reset downstream steps so they don't use stale data.
            # Only invalidate for steps that fundamentally change the data pipeline.
            # Supplementary steps (ESPN, weather, tipsters, enrichment) do NOT
            # invalidate — they add data but don't replace it.
            INVALIDATING_STEPS = {
                "s1_scan", "s1_ingest", "s1c_aggregate", "s1d_matrix",
                "s1e_shortlist", "s3_deep_stats", "s7_gate",
            }
            if resume and step_id in INVALIDATING_STEPS:
                step_ids = [s["id"] for s in steps_to_run]
                current_idx = step_ids.index(step_id) if step_id in step_ids else -1
                if current_idx >= 0:
                    downstream_ids = step_ids[current_idx + 1:]
                    invalidated = []
                    for ds_id in downstream_ids:
                        ds_state = state.get("steps", {}).get(ds_id, {})
                        if ds_state.get("status") == "completed":
                            ds_state["status"] = "pending"
                            ds_state["invalidated_by"] = step_id
                            invalidated.append(ds_id)
                    if invalidated:
                        print(f"  ↻ Invalidated {len(invalidated)} downstream steps: {', '.join(invalidated)}")
                        save_state(date, state)

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

                # Write structured agent input file
                step_metrics = state.get("step_data", {}).get(step_id, {})
                step_artifacts = [str(DATA_DIR / o) for o in step.get("outputs", []) if o]
                try:
                    input_path = write_step_output(date, step_id, step_metrics, step_artifacts)
                    print(f"  [agent] Wrote input: {input_path}")
                except Exception as e:
                    print(f"  [agent] Warning: failed to write input: {e}")

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
    "data": {"s0_settle", "s1_scan", "s1_ingest", "s1_html_deep", "s1a_discover", "s1a_espn", "s1b_parallel", "s1c_aggregate", "s1d_matrix", "s1e_shortlist", "s2_tipster", "s2_5_enrich"},
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
            now = datetime.now(get_tz())
            args.date = now.strftime("%Y-%m-%d")
        state = load_state(args.date)
        print_status(state)
        return

    if not args.date:
        now = datetime.now(get_tz())
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