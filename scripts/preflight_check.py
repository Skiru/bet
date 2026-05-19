#!/usr/bin/env python3
"""Pre-flight check — validates all pipeline dependencies before S1.

Run before any betting pipeline day to ensure all prerequisites are met.
Exit codes: 0=all pass, 1=warnings only, 2=blocking failure.

Usage:
    PYTHONPATH=src python3 scripts/preflight_check.py [--verbose]
"""

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from agent_output import AgentOutput, add_agent_args
import argparse


def check_api_keys() -> tuple[str, str]:
    """Check critical API keys are present and non-empty."""
    keys_path = ROOT_DIR / "config" / "api_keys.json"
    if not keys_path.exists():
        return "FAIL", "config/api_keys.json not found"
    try:
        keys = json.loads(keys_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return "FAIL", f"Cannot parse api_keys.json: {e}"

    critical = ["odds-api"]
    important = ["serpapi"]
    optional = ["gemini"]

    for k in critical:
        val = keys.get(k)
        if not val or val == "YOUR_KEY":
            return "FAIL", f"Critical API key missing: {k}"

    warnings = []
    for k in important:
        val = keys.get(k)
        if not val or val == "YOUR_KEY":
            warnings.append(f"Important API key missing: {k}")

    for k in optional:
        val = keys.get(k)
        if not val:
            warnings.append(f"Optional API key empty: {k}")

    if warnings:
        return "WARN", "; ".join(warnings)
    return "OK", "All API keys present"


def check_db_health() -> tuple[str, str]:
    """Check database exists and schema is current."""
    db_path = ROOT_DIR / "betting" / "data" / "betting.db"
    if not db_path.exists():
        return "FAIL", "betting.db not found"
    try:
        from bet.db.connection import get_db
        with get_db() as db:
            row = db.execute("SELECT COUNT(*) FROM sports").fetchone()
            if row[0] == 0:
                return "WARN", "sports table is empty — run schema migration"
            # Check schema version
            try:
                row = db.execute(
                    "SELECT value FROM pipeline_metadata WHERE key='schema_version'"
                ).fetchone()
                if row:
                    ver = int(row[0])
                    if ver < 10:
                        return "WARN", f"Schema version {ver} < 10 (run migrations)"
            except Exception:
                pass
        return "OK", "Database healthy"
    except Exception as e:
        return "FAIL", f"Database error: {e}"


def check_critical_imports() -> tuple[str, str]:
    """Check critical Python packages are importable."""
    missing = []
    for pkg in ["curl_cffi", "rapidfuzz"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        return "FAIL", f"Missing packages: {', '.join(missing)}"
    return "OK", "All critical packages available"


def check_config_valid() -> tuple[str, str]:
    """Check betting_config.json is parseable and has valid bankroll."""
    config_path = ROOT_DIR / "config" / "betting_config.json"
    if not config_path.exists():
        return "FAIL", "betting_config.json not found"
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return "FAIL", f"Config parse error: {e}"

    bankroll = cfg.get("bankroll_pln") or cfg.get("working_bankroll_pln", 0)
    if bankroll <= 0:
        return "FAIL", f"Bankroll is {bankroll} (must be > 0)"
    if bankroll < 10:
        return "WARN", f"Bankroll very low: {bankroll} PLN"
    return "OK", f"Config valid (bankroll: {bankroll} PLN)"


def check_disk_space() -> tuple[str, str]:
    """Check >100MB free disk space."""
    import shutil
    usage = shutil.disk_usage(ROOT_DIR)
    free_mb = usage.free / (1024 * 1024)
    if free_mb < 100:
        return "FAIL", f"Low disk space: {free_mb:.0f} MB free"
    return "OK", f"{free_mb:.0f} MB free"


def check_stale_fixtures() -> tuple[str, str]:
    """Check for stale pending fixtures (>7 days old)."""
    try:
        from bet.db.connection import get_db
        with get_db() as db:
            row = db.execute(
                "SELECT COUNT(*) FROM fixtures "
                "WHERE status = 'pending' AND date(kickoff) < date('now', '-7 days')"
            ).fetchone()
            stale = row[0] if row else 0
            if stale > 50:
                return "WARN", f"{stale} stale pending fixtures (>7 days old)"
            return "OK", f"{stale} stale fixtures (acceptable)"
    except Exception as e:
        return "WARN", f"Cannot check fixtures: {e}"


def main():
    parser = argparse.ArgumentParser(description="Pipeline pre-flight check")
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput("preflight", verbose=getattr(args, "verbose", False))

    checks = [
        ("API Keys", check_api_keys),
        ("Database", check_db_health),
        ("Imports", check_critical_imports),
        ("Config", check_config_valid),
        ("Disk Space", check_disk_space),
        ("Stale Fixtures", check_stale_fixtures),
    ]

    results = {}
    has_fail = False
    has_warn = False

    for name, check_fn in checks:
        status, msg = check_fn()
        results[name] = {"status": status, "message": msg}
        icon = "✅" if status == "OK" else "⚠️" if status == "WARN" else "❌"
        print(f"{icon} {name}: {msg}")
        if status == "FAIL":
            has_fail = True
        elif status == "WARN":
            has_warn = True

    print()
    if has_fail:
        print("❌ PREFLIGHT FAILED — fix blocking issues before pipeline run")
        out.summary(verdict="FAILED", metrics=results)
        sys.exit(2)
    elif has_warn:
        print("⚠️ PREFLIGHT PASSED WITH WARNINGS")
        out.summary(verdict="PARTIAL", metrics=results)
        sys.exit(1)
    else:
        print("✅ ALL PREFLIGHT CHECKS PASSED")
        out.summary(verdict="OK", metrics=results)
        sys.exit(0)


if __name__ == "__main__":
    main()
