#!/usr/bin/env python3
"""Pipeline Orchestrator — single entry point for the entire betting pipeline.

Wraps the bash orchestrator with Python state tracking, error recovery,
and step-by-step execution. Can resume from any step after failure.

Usage:
    python3 scripts/pipeline_orchestrator.py --date 2026-04-30
    python3 scripts/pipeline_orchestrator.py --date 2026-04-30 --session night
    python3 scripts/pipeline_orchestrator.py --date 2026-04-30 --resume
    python3 scripts/pipeline_orchestrator.py --date 2026-04-30 --step scan
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
from datetime import datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

SCRIPTS_DIR = Path(__file__).parent
ROOT_DIR = SCRIPTS_DIR.parent
DATA_DIR = ROOT_DIR / "betting" / "data"
STATE_DIR = DATA_DIR / "pipeline_state"
CONFIG_PATH = ROOT_DIR / "config" / "betting_config.json"

# Pipeline steps in order
PIPELINE_STEPS = [
    {
        "id": "s0_settle",
        "name": "S0: Settle Previous Day + Learn from History",
        "description": "Settle previous day's bets, run Betclic history analysis",
        "commands": [
            "python3 scripts/analyze_betclic_learning.py",
        ],
        "outputs": [],
        "critical": True,
    },
    {
        "id": "s1_scan",
        "name": "S1: Complete Event Scan",
        "description": "Run full multi-sport scan with deep-link discovery",
        "commands": [
            "bash scripts/run_full_scan_and_prepare.sh",
        ],
        "outputs": [
            "betting/data/scan_summary.json",
            "betting/data/scan_errors.json",
        ],
        "critical": True,
    },
    {
        "id": "s1_odds",
        "name": "S1b: Cross-Validation Odds",
        "description": "Fetch odds from The-Odds-API for cross-validation",
        "commands": [
            "python3 scripts/fetch_odds_api.py",
        ],
        "outputs": [
            "betting/data/odds_api_snapshot.json",
        ],
        "critical": False,
    },
    {
        "id": "s1_weather",
        "name": "S1c: Weather Data",
        "description": "Fetch weather for outdoor sport venues",
        "commands": [
            "python3 scripts/fetch_weather.py --date {date}",
        ],
        "outputs": [],
        "critical": False,
    },
    {
        "id": "s1_market_matrix",
        "name": "S1d: Market Matrix",
        "description": "Generate consolidated market matrix from all data sources",
        "commands": [
            "python3 scripts/generate_market_matrix.py --date {date}",
        ],
        "outputs": [],
        "critical": False,
    },
    {
        "id": "s2_shortlist",
        "name": "S2: Shortlist Filtering",
        "description": "Filter events to shortlist (agent-driven step)",
        "commands": [],  # Agent-driven
        "outputs": [],
        "critical": True,
        "agent_step": True,
    },
    {
        "id": "s3_stats",
        "name": "S3: Deep Statistical Analysis",
        "description": "Sport-specific deep analysis per candidate (agent-driven)",
        "commands": [],  # Agent-driven
        "outputs": [],
        "critical": True,
        "agent_step": True,
    },
    {
        "id": "s4_tipsters",
        "name": "S4: Tipster Deep-Dive",
        "description": "Fetch and analyze tipster arguments per candidate (agent-driven)",
        "commands": [],  # Agent-driven
        "outputs": [],
        "critical": True,
        "agent_step": True,
    },
    {
        "id": "s5_odds_ev",
        "name": "S5: Odds + EV Calculation",
        "description": "Calculate EV, Kelly stakes, price gaps (agent-driven)",
        "commands": [],  # Agent-driven
        "outputs": [],
        "critical": True,
        "agent_step": True,
    },
    {
        "id": "s6_context",
        "name": "S6: Context + Upset Risk",
        "description": "Verify context, score upset risk (agent-driven)",
        "commands": [],  # Agent-driven
        "outputs": [],
        "critical": True,
        "agent_step": True,
    },
    {
        "id": "s7_gate",
        "name": "S7: Bear Case + 17-Point Gate",
        "description": "Run gate checks, approve/reject picks (agent-driven)",
        "commands": [],  # Agent-driven
        "outputs": [],
        "critical": True,
        "agent_step": True,
    },
    {
        "id": "s3b_time",
        "name": "S3B: Time-Sensitive Data",
        "description": "Lineups, late injuries, weather, odds movement (agent-driven)",
        "commands": [],  # Agent-driven
        "outputs": [],
        "critical": False,
        "agent_step": True,
    },
    {
        "id": "s8_coupons",
        "name": "S8: Portfolio + Coupons",
        "description": "Build coupons, run V1-V10, produce artifacts (agent-driven)",
        "commands": [],  # Agent-driven
        "outputs": [],
        "critical": True,
        "agent_step": True,
    },
]


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
        "pass_number": 1,
    }


def save_state(date: str, state: dict):
    """Save pipeline state atomically."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = STATE_DIR / f"pipeline_{date}.json"
    content = json.dumps(state, indent=2, ensure_ascii=False)
    fd, tmp_path = tempfile.mkstemp(dir=str(STATE_DIR), suffix=".tmp")
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        os.replace(tmp_path, str(state_file))
    except Exception:
        os.close(fd)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def run_command(cmd: str, date: str) -> tuple[bool, str]:
    """Run a shell command and return (success, output)."""
    # Validate date format to prevent command injection
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        return False, f"Invalid date format: {date} (expected YYYY-MM-DD)"
    cmd = cmd.replace("{date}", shlex.quote(date))
    print(f"  → Running: {cmd}")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout per command
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            print(f"  ✗ Command failed (exit {result.returncode})")
            return False, output
        print(f"  ✓ Command succeeded")
        return True, output
    except subprocess.TimeoutExpired:
        return False, "Command timed out after 600 seconds"
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


def print_status(state: dict):
    """Print current pipeline status."""
    print(f"\n{'='*60}")
    print(f"Pipeline Status — {state['date']}")
    print(f"{'='*60}")
    print(f"Session: {state.get('session', 'full')}")
    print(f"Version: {state.get('version', 'v1')}")
    print(f"Pass: {state.get('pass_number', 1)}")
    print(f"Started: {state.get('started_at', 'N/A')}")
    print(f"Current step: {state.get('current_step', 'N/A')}")
    print()

    for step in PIPELINE_STEPS:
        step_state = state.get("steps", {}).get(step["id"], {})
        status = step_state.get("status", "pending")
        marker = {"pending": "○", "running": "►", "completed": "✓", "failed": "✗", "skipped": "–"}.get(status, "?")
        agent_tag = " [AGENT]" if step.get("agent_step") else ""
        print(f"  {marker} {step['name']}{agent_tag} — {status}")
        if step_state.get("error"):
            print(f"    Error: {step_state['error'][:100]}")

    errors = state.get("errors", [])
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for err in errors[-5:]:  # Show last 5
            print(f"  - {err}")
    print()


def run_pipeline(date: str, session: str = "full", resume: bool = False,
                 single_step: str = None, version: str = None):
    """Run the full pipeline or a single step."""
    # Validate date format early to prevent path traversal in state files
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        print(f"[FATAL] Invalid date format: {date} (expected YYYY-MM-DD)")
        sys.exit(1)

    state = load_state(date)

    if not resume:
        state["session"] = session
        state["started_at"] = datetime.now(ZoneInfo("Europe/Warsaw")).isoformat()
        if version:
            state["version"] = version

    config = load_config()

    print(f"\n{'='*60}")
    print(f"BETTING PIPELINE ORCHESTRATOR")
    print(f"{'='*60}")
    print(f"Date: {date}")
    print(f"Session: {session}")
    print(f"Version: {state.get('version', 'v1')}")
    print(f"Bankroll: {config.get('working_bankroll_pln', 'N/A')} PLN")
    print(f"Daily budget: {config.get('suggested_daily_allocation_range_pln', 'N/A')} PLN")
    print(f"Resume: {resume}")
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

        # Agent-driven steps — mark as ready and continue
        if step.get("agent_step"):
            step_state["status"] = "pending"
            step_state["message"] = "Agent-driven step — delegate to appropriate agent"
            state["current_step"] = step_id
            save_state(date, state)
            print(f"[agent] {step['name']} — agent-driven, marking ready")
            continue

        # Script-driven steps
        print(f"\n{'─'*40}")
        print(f"[{step_id}] {step['name']}")
        print(f"{'─'*40}")

        step_state["status"] = "running"
        step_state["started_at"] = datetime.now(ZoneInfo("Europe/Warsaw")).isoformat()
        state["current_step"] = step_id
        save_state(date, state)

        all_success = True
        outputs = []
        for cmd in step["commands"]:
            success, output = run_command(cmd, date)
            outputs.append(output)
            if not success:
                all_success = False
                if step["critical"]:
                    step_state["status"] = "failed"
                    step_state["error"] = output[-500:]  # Last 500 chars
                    state["errors"].append(f"{step_id}: {output[-200:]}")
                    save_state(date, state)
                    print(f"\n[CRITICAL] {step['name']} failed — pipeline stopped")
                    print_status(state)
                    return
                else:
                    print(f"  [WARNING] Non-critical step failed, continuing")

        # Check outputs
        missing = check_outputs(step)
        if missing:
            print(f"  [WARNING] Missing output files: {missing}")

        step_state["status"] = "completed" if all_success else "completed_with_warnings"
        step_state["completed_at"] = datetime.now(ZoneInfo("Europe/Warsaw")).isoformat()
        save_state(date, state)

    # Summary
    print_status(state)

    # Check if all script steps completed
    script_steps = [s for s in PIPELINE_STEPS if not s.get("agent_step")]
    completed = sum(1 for s in script_steps
                    if state.get("steps", {}).get(s["id"], {}).get("status", "").startswith("completed"))
    print(f"\nScript steps completed: {completed}/{len(script_steps)}")
    print(f"Agent steps remaining: {sum(1 for s in PIPELINE_STEPS if s.get('agent_step'))}")
    print(f"\nUse @bet-orchestrator to run agent-driven steps (S2-S8)")


def main():
    parser = argparse.ArgumentParser(description="Betting Pipeline Orchestrator")
    parser.add_argument("--date", help="Betting date (YYYY-MM-DD)")
    parser.add_argument("--session", default="full", choices=["full", "day", "night", "morning"])
    parser.add_argument("--resume", action="store_true", help="Resume from last completed step")
    parser.add_argument("--step", help="Run a single step by ID")
    parser.add_argument("--version", help="Pipeline version (v1, v2, etc.)")
    parser.add_argument("--status", action="store_true", help="Show current pipeline status")
    parser.add_argument("--list-steps", action="store_true", help="List all pipeline steps")
    args = parser.parse_args()

    if args.list_steps:
        print("Pipeline Steps:")
        for step in PIPELINE_STEPS:
            agent_tag = " [AGENT]" if step.get("agent_step") else " [SCRIPT]"
            critical_tag = " ★" if step["critical"] else ""
            print(f"  {step['id']:15s} {step['name']}{agent_tag}{critical_tag}")
        return

    if args.status:
        if not args.date:
            # Try today's date
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
    )


if __name__ == "__main__":
    main()
