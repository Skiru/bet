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
        "id": "s1b_parallel",
        "name": "S1b: Odds + Weather + Tipsters (PARALLEL)",
        "description": "Fetch odds, weather, and tipster data concurrently",
        "python_step": "parallel_enrichment",
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
        "commands": ["python3 scripts/build_shortlist.py --date {date} --top 100 --stats-first"],
        "outputs": [],
        "critical": False,
    },
    {
        "id": "s3_deep_stats",
        "name": "S3: Deep Statistical Analysis",
        "description": "Per-candidate §3.0 analysis with L10/H2H/L5 stats",
        "python_step": "deep_stats",
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
    },
    {
        "id": "s10_summary",
        "name": "S10: Final Summary",
        "description": "Generate artifacts and summary report",
        "python_step": "summary",
    },
]

# IDs of scan-phase steps (skippable with --skip-scan)
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
def run_command(cmd: str, date: str) -> tuple[bool, str]:
    """Run a shell command and return (success, output)."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return False, f"Invalid date format: {date} (expected YYYY-MM-DD)"
    cmd = cmd.replace("{date}", date)
    # Compute previous date for settlement commands
    prev_date = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    cmd = cmd.replace("{prev_date}", prev_date)
    print(f"  → Running: {cmd}")
    try:
        use_shell = cmd.strip().startswith("bash ")
        if use_shell:
            run_args = cmd
        else:
            run_args = shlex.split(cmd)
        result = subprocess.run(
            run_args,
            shell=use_shell,
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=2400,
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            print(f"  ✗ Command failed (exit {result.returncode})")
            return False, output
        print(f"  ✓ Command succeeded")
        return True, output
    except subprocess.TimeoutExpired:
        return False, "Command timed out after 2400 seconds"
    except Exception as e:
        return False, str(e)


def check_outputs(step: dict) -> list[str]:
    """Check if expected output files exist."""
    missing = []
    for output_path in step.get("outputs", []):
        full_path = ROOT_DIR / output_path
        if not full_path.exists():
            missing.append(output_path)
    return missing


# ---------------------------------------------------------------------------
# EV injection from odds API
# ---------------------------------------------------------------------------
def _inject_ev_from_odds(candidates: list[dict], date: str):
    """Compute and inject EV into candidates using odds API snapshot.

    EV = (safety × odds) - 1. If no odds snapshot exists, candidates
    keep ev=None and the gate handles it gracefully (stats-first mode).
    """
    odds_path = DATA_DIR / "odds_api_snapshot.json"
    if not odds_path.exists():
        return

    try:
        odds_data = json.loads(odds_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    # Build lookup: "home|away" → best odds
    odds_lookup: dict[str, float] = {}
    for event in odds_data if isinstance(odds_data, list) else odds_data.get("events", []):
        home = (event.get("home_team") or "").strip().lower()
        away = (event.get("away_team") or "").strip().lower()
        best_odds = event.get("best_odds") or event.get("odds", {}).get("market_best")
        if home and away and best_odds:
            odds_lookup[f"{home}|{away}"] = float(best_odds)

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
        safety = (c.get("best_market") or {}).get("safety_score", 0)
        prob = (c.get("best_market") or {}).get("probability") or safety
        if prob and odds:
            ev = round(prob * odds - 1, 4)
            c["ev"] = ev
            c.setdefault("odds", {})["market_best"] = odds
            injected += 1

    if injected:
        print(f"  → Injected EV for {injected}/{len(candidates)} candidates from odds API")


# ---------------------------------------------------------------------------
# Python-driven step implementations
# ---------------------------------------------------------------------------

def _run_parallel_enrichment(date: str, state: dict) -> tuple[bool, str]:
    """S1b: Run odds, weather, and tipster aggregation in parallel.

    These three tasks are independent and can run concurrently:
    1. Odds API fetch (~2 min)
    2. Weather data fetch (~1 min)
    3. Tipster aggregation (~3-5 min with parallel site fetching)
    """
    results = {}
    errors = []

    def run_odds():
        ok, out = run_command("python3 scripts/fetch_odds_api.py", date)
        return "odds", ok, out

    def run_weather():
        ok, out = run_command("python3 scripts/fetch_weather.py --date {date}", date)
        return "weather", ok, out

    def run_tipsters():
        ok, out = run_command("python3 scripts/tipster_aggregator.py --date {date} --workers 5", date)
        return "tipsters", ok, out

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(run_odds),
            executor.submit(run_weather),
            executor.submit(run_tipsters),
        ]

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
    for name in ["odds", "weather", "tipsters"]:
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
        shortlist_path = shortlist_path_alt if Path(shortlist_path_alt).exists() else None

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

    state.setdefault("step_data", {})["s3_count"] = total
    state["step_data"]["s3_with_data"] = count

    return True, msg


def _run_s7(date: str, state: dict) -> tuple[bool, str]:
    """S7: Gate Check."""
    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
    if not s3_path.exists():
        return False, f"S3 output not found: {s3_path}"

    s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
    analyses = s3_data.get("analyses", [])

    candidates = [_normalise_s3_to_gate_input(a) for a in analyses if a.get("has_data")]

    if not candidates:
        return False, "No candidates with data for gate check"

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
        elif step_id == "s3_deep_stats":
            return _run_s3(date, state)
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
            all_success = True
            outputs = []
            for cmd in step["commands"]:
                cmd_ok, cmd_out = run_command(cmd, date)
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