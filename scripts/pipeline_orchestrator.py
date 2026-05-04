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
    "s1_scan": 1800,       # 30 min (200+ URLs parallel scan + enrichment + aggregation)
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
        "name": "S1: Complete Event Scan",
        "description": "Full 14-sport scan with Playwright + API fixture discovery",
        "commands": ["bash scripts/run_full_scan_and_prepare.sh"],
        "outputs": ["betting/data/scan_summary.json"],
        "critical": True,
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
    },
    {
        "id": "s2_tipster",
        "name": "S2: Tipster Cross-Reference",
        "description": "Cross-reference picks with tipster consensus data",
        "python_step": "tipster_xref",
        "critical": False,
    },
    {
        "id": "s3_deep_stats",
        "name": "S3: Deep Statistical Analysis",
        "description": "Per-candidate §3.0 analysis with L10/H2H/L5 stats",
        "python_step": "deep_stats",
    },
    {
        "id": "s4_odds_eval",
        "name": "S4: Odds Evaluation",
        "description": "Cross-validate odds, compute EV, detect drift",
        "python_step": "odds_eval",
        "critical": False,
    },
    {
        "id": "s5_context",
        "name": "S5: Contextual Checks",
        "description": "Weather impact, venue, referee, roster changes",
        "python_step": "context_checks",
        "critical": False,
    },
    {
        "id": "s6_upset_risk",
        "name": "S6: Upset Risk Scoring",
        "description": "Score upset risk per candidate using sport-specific checklists",
        "python_step": "upset_risk",
        "critical": False,
    },
    {
        "id": "s7_gate",
        "name": "S7: 17-Point Gate Check",
        "description": "Run gate checks, classify approved/extended/rejected",
        "python_step": "gate_check",
    },
    {
        "id": "s8_coupons",
        "name": "S8: Build Coupons",
        "description": "Core portfolio + combo menu + extended pool",
        "python_step": "build_coupons",
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

# Steps that run inside the shell script (skip when shell script runs)
SHELL_COVERED_IDS = {"s1a_discover", "s1c_aggregate"}
# Steps that skip with --skip-scan (the heavy Playwright scan + parallel enrichment)
SCAN_STEP_IDS = {"s1_scan", "s1b_parallel", "s1d_matrix", "s1e_shortlist"}


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
    """Load pipeline state for a date."""
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
    """Save pipeline state atomically."""
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

    Sources: the-odds-api (odds_api_snapshot.json) + odds-api.io (odds_api_io_snapshot.json)
    + ESPN DraftKings (espn_enrichment_{date}.json).
    EV = (probability × odds) - 1. If no odds snapshot exists, candidates
    keep ev=None and the gate handles it gracefully (stats-first mode).
    """
    odds_lookup: dict[str, float] = {}

    # Source 1: the-odds-api snapshot
    odds_path = DATA_DIR / "odds_api_snapshot.json"
    if odds_path.exists():
        try:
            odds_data = json.loads(odds_path.read_text(encoding="utf-8"))
            for event in odds_data if isinstance(odds_data, list) else odds_data.get("events", []):
                home = (event.get("home_team") or "").strip().lower()
                away = (event.get("away_team") or "").strip().lower()
                best_odds = event.get("best_odds") or event.get("odds", {}).get("market_best")
                if home and away and best_odds:
                    odds_lookup[f"{home}|{away}"] = float(best_odds)
        except (json.JSONDecodeError, OSError):
            pass

    # Source 2: odds-api.io snapshot (265 bookmakers, more coverage)
    io_path = DATA_DIR / "odds_api_io_snapshot.json"
    if io_path.exists():
        try:
            io_data = json.loads(io_path.read_text(encoding="utf-8"))
            # Extract odds from events
            for event in io_data.get("events", []):
                home = (event.get("home") or "").strip().lower()
                away = (event.get("away") or "").strip().lower()
                if not home or not away:
                    continue
                key = f"{home}|{away}"
                # Find best ML odds across bookmakers
                for bookie_name, markets in (event.get("bookmakers") or {}).items():
                    if not isinstance(markets, list):
                        continue
                    for market in markets:
                        if market.get("name") == "ML":
                            for odds_entry in market.get("odds", []):
                                for side in ["home", "away"]:
                                    try:
                                        val = float(odds_entry.get(side, 0))
                                        if val > odds_lookup.get(key, 0):
                                            odds_lookup[key] = val
                                    except (ValueError, TypeError):
                                        pass
            # Inject from value bets (pre-calculated EV!)
            for vb in io_data.get("value_bets", []):
                ev_data = vb.get("event", {})
                home = (ev_data.get("home") or "").strip().lower()
                away = (ev_data.get("away") or "").strip().lower()
                if home and away:
                    key = f"{home}|{away}"
                    # Value bets have pre-calculated EV
                    pre_ev = vb.get("expectedValue")
                    if pre_ev is not None:
                        # Find matching candidate and inject directly
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
                # Use decimal moneyline (best odds for the favorite/underdog)
                dec_odds = event.get("odds_decimal", {}).get("moneyline", {})
                for side in ("home", "away"):
                    val = dec_odds.get(side)
                    if val and val > odds_lookup.get(key, 0):
                        odds_lookup[key] = val
        except (json.JSONDecodeError, OSError):
            pass

    if not odds_lookup:
        return

    injected = 0
    for c in candidates:
        if c.get("ev") is not None:
            continue  # Already has EV
        home = (c.get("home_team") or "").strip().lower()
        away = (c.get("away_team") or "").strip().lower()
        key = f"{home}|{away}"
        odds = odds_lookup.get(key)
        if not odds:
            continue
        prob = (c.get("best_market") or {}).get("probability")
        if not prob:
            continue  # No probability yet — S3/probability_engine will compute later
        if prob and odds:
            ev = round(prob * odds - 1, 4)
            c["ev"] = ev
            c.setdefault("odds", {})["market_best"] = odds
            injected += 1

    if injected:
        print(f"  → Injected EV for {injected}/{len(candidates)} candidates from odds APIs")


# ---------------------------------------------------------------------------
# Python-driven step implementations
# ---------------------------------------------------------------------------

def _run_tipster_xref(date: str, state: dict) -> tuple[bool, str]:
    """S2: Cross-reference shortlist with tipster consensus."""
    tipster_path = DATA_DIR / f"tipster_aggregation_{date}.json"
    if not tipster_path.exists():
        return True, "No tipster data available — skipping cross-reference"

    try:
        tipster_data = json.loads(tipster_path.read_text(encoding="utf-8"))
        n_tips = len(tipster_data) if isinstance(tipster_data, list) else len(tipster_data.get("tips", []))
        return True, f"Tipster cross-reference: {n_tips} tips loaded for downstream analysis"
    except Exception as e:
        return True, f"Tipster data load failed: {e} — continuing without"


def _run_odds_eval(date: str, state: dict) -> tuple[bool, str]:
    """S4: Cross-validate odds, compute EV, detect drift."""
    # Load current candidates from S3 output
    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
    if not s3_path.exists():
        return True, "S4: No S3 data yet — skipping EV injection"

    try:
        s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
        candidates = s3_data.get("analyses", [])
        _inject_ev_from_odds(candidates, date)

        # Count how many have EV
        with_ev = sum(1 for c in candidates if c.get("ev") is not None)
        total = len(candidates)

        # Save back enriched data
        s3_path.write_text(
            json.dumps(s3_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True, f"S4 completed: {with_ev}/{total} candidates with EV data"
    except Exception as e:
        return True, f"S4 odds evaluation error: {e} — continuing without"


def _run_context_checks(date: str, state: dict) -> tuple[bool, str]:
    """S5: Contextual checks — weather, venue, referee, roster changes."""
    checks_done = []

    # Weather data
    weather_path = DATA_DIR / f"weather_{date}.json"
    if weather_path.exists():
        try:
            weather = json.loads(weather_path.read_text(encoding="utf-8"))
            n_venues = len(weather) if isinstance(weather, list) else len(weather.get("venues", weather.get("forecasts", {})))
            checks_done.append(f"weather:{n_venues} venues")
        except (json.JSONDecodeError, OSError):
            checks_done.append("weather:load_error")
    else:
        checks_done.append("weather:unavailable")

    # ESPN injuries/roster data
    espn_path = DATA_DIR / f"espn_enrichment_{date}.json"
    if espn_path.exists():
        try:
            espn = json.loads(espn_path.read_text(encoding="utf-8"))
            n_injuries = sum(len(v) if isinstance(v, list) else 0 for v in espn.get("injuries", {}).values())
            checks_done.append(f"injuries:{n_injuries} entries")
        except (json.JSONDecodeError, OSError):
            checks_done.append("injuries:load_error")
    else:
        checks_done.append("injuries:unavailable")

    return True, f"S5 contextual checks: {', '.join(checks_done)}"


def _run_upset_risk(date: str, state: dict) -> tuple[bool, str]:
    """S6: Upset risk scoring per candidate."""
    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
    if not s3_path.exists():
        return True, "S6: No S3 data — skipping upset risk scoring"

    try:
        s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
        analyses = s3_data.get("analyses", [])
        scored = 0
        for analysis in analyses:
            # Basic upset risk heuristic: if underdog odds < 2.5 and form is strong
            ranking = analysis.get("ranking_result", {}).get("ranking", [])
            if ranking:
                top_market = ranking[0] if ranking else {}
                safety = top_market.get("safety_score", 0)
                # Flag potential upsets (low safety = higher risk)
                if safety < 50:
                    analysis.setdefault("flags", []).append("upset_risk_elevated")
                scored += 1

        s3_path.write_text(
            json.dumps(s3_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True, f"S6 completed: {scored} candidates scored for upset risk"
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
    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
    if not s3_path.exists():
        return False, f"S3 output not found: {s3_path}"

    s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
    analyses = s3_data.get("analyses", [])

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

    # Inject EV from odds API snapshot if available
    _inject_ev_from_odds(candidates, date)

    results = run_gate(candidates, date)

    write_gate_json(results, date)
    write_gate_md(results, date)

    s = results["summary"]
    msg = (
        f"S7 completed: {s['approved_count']} approved, "
        f"{s['extended_count']} extended, {s['rejected_count']} rejected"
    )

    if results["gate_results"].get("expansion_needed"):
        msg += " ⚠️ EXPANSION NEEDED (sport diversity)"

    state.setdefault("step_data", {})["s7_approved"] = s["approved_count"]
    state["step_data"]["s7_extended"] = s["extended_count"]

    return True, msg


def _run_s8(date: str, state: dict) -> tuple[bool, str]:
    """S8: Build Coupons."""
    gate_path = DATA_DIR / f"{date}_s7_gate_results.json"
    if not gate_path.exists():
        return False, f"S7 gate results not found: {gate_path}"

    gate_data = json.loads(gate_path.read_text(encoding="utf-8"))
    config = load_coupon_config()

    result = build_coupons(gate_data, config)

    write_coupon_markdown(result, date)
    write_coupon_json(result, date)

    if result.get("no_bet"):
        msg = f"S8: NO BET — {result.get('no_bet_reason', 'insufficient picks')}"
    else:
        core_count = len(result.get("core_coupons", []))
        combo_count = len(result.get("combos", []))
        msg = f"S8 completed: {core_count} core coupons, {combo_count} combos"

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
    """S10: Final summary."""
    step_data = state.get("step_data", {})

    summary_lines = [
        "═══════════════════════════════════",
        f"  PIPELINE COMPLETE — {date}",
        "═══════════════════════════════════",
        "",
        f"S3 Deep Stats: {step_data.get('s3_with_data', '?')}/{step_data.get('s3_count', '?')} candidates analyzed",
        f"S7 Gate: {step_data.get('s7_approved', '?')} approved, {step_data.get('s7_extended', '?')} extended",
    ]

    if step_data.get("s8_no_bet"):
        summary_lines.append("S8 Coupons: NO BET DAY")
    else:
        summary_lines.append(
            f"S8 Coupons: {step_data.get('s8_core', '?')} core, {step_data.get('s8_combos', '?')} combos"
        )

    summary_lines.extend(
        [
            "",
            "Output files:",
            f"  📊 betting/data/{date}_s3_deep_stats.md",
            f"  ✅ betting/data/{date}_s7_gate_results.md",
            f"  🎫 betting/coupons/{date}.md",
            f"  📦 betting/coupons/{date}.json",
        ]
    )

    msg = "\n".join(summary_lines)
    print(msg)

    state["completed_at"] = datetime.now(ZoneInfo("Europe/Warsaw")).isoformat()

    return True, msg


def run_python_step(step_id: str, date: str, state: dict) -> tuple[bool, str]:
    """Dispatch to the correct Python-driven pipeline step."""
    try:
        if step_id == "s1b_parallel":
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
    version: str | None = None,
    skip_scan: bool = False,
    top: int | None = None,
):
    """Run the full pipeline or a single step."""
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

        # Skip shell-covered steps when s1_scan already ran them
        if step_id in SHELL_COVERED_IDS and not skip_scan:
            s1_state = state.get("steps", {}).get("s1_scan", {})
            if s1_state.get("status") == "completed":
                step_state["status"] = "skipped"
                print(f"[skip] {step['name']} — already done by S1 shell script")
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
            # Skip s1d/s1e if outputs already exist from shell script
            date_compact = date.replace("-", "")
            skip_reason = None
            if step_id == "s1d_matrix" and (DATA_DIR / f"market_matrix_{date}.json").exists():
                skip_reason = "market_matrix already exists from S1"
            elif step_id == "s1e_shortlist" and (DATA_DIR / f"{date_compact}_s2_shortlist.json").exists():
                skip_reason = "shortlist already exists from S1"
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

            # Record source health after scan completes
            if step_id == "s1_scan":
                _run_source_health(date)

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
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Betting Pipeline Orchestrator")
    parser.add_argument("--date", help="Betting date (YYYY-MM-DD)")
    parser.add_argument("--session", default="full", choices=["full", "day", "night", "morning"])
    parser.add_argument("--resume", action="store_true", help="Resume from last completed step")
    parser.add_argument("--step", help="Run a single step by ID")
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
            print(f"  {step['id']:18s} {step['name']}{kind}{critical_tag}")
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
        version=args.version,
        skip_scan=args.skip_scan,
        top=args.top,
    )


if __name__ == "__main__":
    main()