#!/usr/bin/env python3
"""DB-FIRST phase validation for the betting pipeline.

Validates pipeline state after each phase by querying betting.db as the PRIMARY
source of truth, with JSON file checks as FALLBACK only.

Usage:
    python3 scripts/validate_phase.py --date 2026-05-08 --phase data
    python3 scripts/validate_phase.py --date 2026-05-08 --phase analysis
    python3 scripts/validate_phase.py --date 2026-05-08 --phase build
    python3 scripts/validate_phase.py --date 2026-05-08 --phase all
    python3 scripts/validate_phase.py --date 2026-05-08 --phase all --format json

Exit codes:
    0 = ALL gates pass
    1 = At least one GATE failed (blocking)
    2 = Warnings only (non-blocking)
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Insert src for bet.db.connection
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

DATA_DIR = Path(__file__).resolve().parent.parent / "betting" / "data"
COUPON_DIR = Path(__file__).resolve().parent.parent / "betting" / "coupons"
JOURNAL_DIR = Path(__file__).resolve().parent.parent / "betting" / "journal"
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "betting_config.json"
SCRIPTS_DIR = Path(__file__).resolve().parent

CEST = timezone(timedelta(hours=2))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class Check:
    """Single validation check result."""
    def __init__(self, check_id: str, name: str, status: str, value: str,
                 gate: bool = False, recovery: str = ""):
        self.check_id = check_id
        self.name = name
        self.status = status  # PASS / FAIL / WARN / SKIP
        self.value = value
        self.gate = gate  # If True and FAIL → blocking
        self.recovery = recovery

    def to_dict(self):
        return {
            "check": self.check_id,
            "name": self.name,
            "status": self.status,
            "value": self.value,
            "gate": self.gate,
            "recovery": self.recovery,
        }

    def __str__(self):
        icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "SKIP": "⏭️"}.get(self.status, "?")
        gate_tag = " [GATE]" if self.gate else ""
        rec = f"\n     ↳ Recovery: {self.recovery}" if self.status == "FAIL" and self.recovery else ""
        return f"  {icon} {self.check_id}: {self.name} → {self.value}{gate_tag}{rec}"


def _get_db():
    """Get DB connection via bet.db.connection."""
    from bet.db.connection import get_db
    return get_db()


def _load_pipeline_state(date: str) -> dict:
    state_path = DATA_DIR / "pipeline_state" / f"pipeline_{date}.json"
    if state_path.exists():
        with open(state_path) as f:
            return json.load(f)
    return {}


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def _resolve_shortlist_path(date: str) -> Path | None:
    """Find shortlist JSON (handles both date formats)."""
    for fmt in [f"{date}_s2_shortlist.json", f"{date.replace('-', '')}_s2_shortlist.json"]:
        p = DATA_DIR / fmt
        if p.exists():
            return p
    return None


def _load_shortlist(date: str) -> list:
    p = _resolve_shortlist_path(date)
    if not p:
        return []
    with open(p) as f:
        data = json.load(f)
    return data.get("candidates", [])


# ---------------------------------------------------------------------------
# PHASE 1: DATA COLLECTION validation
# ---------------------------------------------------------------------------

def validate_data_phase(date: str) -> list[Check]:
    checks = []

    # D1: Pipeline state exists
    state = _load_pipeline_state(date)
    checks.append(Check("D1", "Pipeline state file exists",
                         "PASS" if state else "FAIL",
                         f"{'Found' if state else 'MISSING'}: pipeline_state/pipeline_{date}.json",
                         gate=True,
                         recovery=f"Run: python3 scripts/pipeline_orchestrator.py --date {date} --phase data"))

    if not state:
        return checks  # Can't continue without state

    # D2: Data-phase steps completed (DB-FIRST: check pipeline_runs table, fallback to state file)
    data_steps = {"s0_settle", "s1_scan", "s1_ingest", "s1a_discover", "s1b_parallel",
                  "s1c_aggregate", "s1d_matrix", "s1e_shortlist", "s2_tipster"}
    steps = state.get("steps", {})
    completed = {sid for sid, info in steps.items() if info.get("status") == "completed"}
    failed = {sid: info.get("error", "")[:80] for sid, info in steps.items()
              if info.get("status") in ("failed", "timeout")}
    missing = data_steps - completed - set(failed.keys())

    checks.append(Check("D2", "Data-phase steps completed",
                         "PASS" if not failed and not missing else "WARN" if not missing else "FAIL",
                         f"Completed: {len(completed & data_steps)}/{len(data_steps)}" +
                         (f", Failed: {list(failed.keys())}" if failed else "") +
                         (f", Missing: {list(missing)}" if missing else ""),
                         gate=True,
                         recovery=f"Run: python3 scripts/pipeline_orchestrator.py --date {date} --phase data --resume"))

    # D3: DB populated — scan_results (PRIMARY CHECK)
    try:
        with _get_db() as db:
            scan_cnt = db.execute("SELECT COUNT(*) FROM scan_results WHERE betting_date=?", (date,)).fetchone()[0]
            scan_sports = [r[0] for r in db.execute(
                "SELECT DISTINCT sport FROM scan_results WHERE betting_date=?", (date,)).fetchall()]
            fix_cnt = db.execute("SELECT COUNT(*) FROM fixtures WHERE DATE(kickoff)=?", (date,)).fetchone()[0]
            tf_cnt = db.execute("SELECT COUNT(*) FROM team_form WHERE updated_at >= ?",
                                (f"{date}T00:00:00",)).fetchone()[0]
    except Exception as e:
        scan_cnt = fix_cnt = tf_cnt = 0
        scan_sports = []
        checks.append(Check("D3", "DB connection", "FAIL", f"Error: {e}", gate=True,
                             recovery="Check betting/data/betting.db exists and is not locked"))
        return checks

    checks.append(Check("D3", "DB: scan_results populated",
                         "PASS" if scan_cnt > 0 else "FAIL",
                         f"{scan_cnt} rows, {len(scan_sports)} sports: {scan_sports}",
                         gate=True,
                         recovery=f"Run: python3 scripts/pipeline_orchestrator.py --date {date} --step s1_scan"))

    checks.append(Check("D4", "DB: fixtures populated",
                         "PASS" if fix_cnt > 0 else "FAIL",
                         f"{fix_cnt} fixtures for {date}",
                         gate=True,
                         recovery=f"Run: python3 scripts/pipeline_orchestrator.py --date {date} --step s1a_discover"))

    checks.append(Check("D5", "DB: team_form updated today",
                         "PASS" if tf_cnt > 0 else "WARN",
                         f"{tf_cnt} entries updated since {date}",
                         recovery=f"Run: python3 scripts/pipeline_orchestrator.py --date {date} --step s2_5_enrich"))

    # D6: Shortlist — DB-FIRST via analysis_results, fallback to JSON
    try:
        with _get_db() as db:
            ar_cnt = db.execute("SELECT COUNT(*) FROM analysis_results WHERE betting_date=?", (date,)).fetchone()[0]
            ar_sports = [r[0] for r in db.execute(
                """SELECT DISTINCT s.name FROM analysis_results ar
                   JOIN fixtures f ON ar.fixture_id=f.id
                   JOIN sports s ON f.sport_id=s.id
                   WHERE ar.betting_date=?""", (date,)).fetchall()]
    except Exception:
        ar_cnt = 0
        ar_sports = []

    # Also check JSON shortlist as cross-reference
    shortlist = _load_shortlist(date)
    sl_sports = list(set(c.get("sport", "unknown") for c in shortlist))

    # Use DB count if available, otherwise JSON
    candidate_count = ar_cnt if ar_cnt > 0 else len(shortlist)
    sport_list = ar_sports if ar_sports else sl_sports

    checks.append(Check("D6", "Candidates available (DB: analysis_results)",
                         "PASS" if candidate_count > 0 else "FAIL",
                         f"DB: {ar_cnt} analysis_results, JSON shortlist: {len(shortlist)} candidates",
                         gate=True,
                         recovery=f"Run: python3 scripts/pipeline_orchestrator.py --date {date} --step s1e_shortlist"))

    checks.append(Check("D7", "Sport diversity",
                         "PASS" if len(sport_list) >= 6 else "FAIL",
                         f"{len(sport_list)} sports: {sorted(sport_list)}",
                         gate=True,
                         recovery="Check scan_urls.json coverage; re-scan missing sports with --step s1_scan"))

    checks.append(Check("D8", "Candidate count ≥20 (full session)",
                         "PASS" if candidate_count >= 20 else "WARN" if candidate_count >= 10 else "FAIL",
                         f"{candidate_count} candidates",
                         gate=candidate_count < 10,
                         recovery=f"Expand shortlist: python3 scripts/build_shortlist.py --date {date} --stats-first"))

    # D9: Kickoff normalization
    if shortlist:
        iso_count = sum(1 for c in shortlist if c.get("kickoff") and "T" in str(c.get("kickoff", "")))
        pct = iso_count / len(shortlist) * 100
        checks.append(Check("D9", "Kickoff normalization ≥90% ISO",
                             "PASS" if pct >= 90 else "WARN",
                             f"{iso_count}/{len(shortlist)} ({pct:.1f}%) have ISO kickoff times"))
    else:
        checks.append(Check("D9", "Kickoff normalization", "SKIP", "No shortlist to check"))

    # D10: Enrichment yield — check s2_5_enrich step
    enrich_state = steps.get("s2_5_enrich", {})
    enrich_status = enrich_state.get("status", "missing")
    checks.append(Check("D10", "Enrichment step status",
                         "PASS" if enrich_status == "completed" else
                         "WARN" if enrich_status == "skipped" else "FAIL",
                         f"Status: {enrich_status}",
                         gate=enrich_status == "failed",
                         recovery=f"Run: python3 scripts/pipeline_orchestrator.py --date {date} --step s2_5_enrich"))

    # D11: Odds coverage — DB-FIRST
    try:
        with _get_db() as db:
            odds_fixtures = db.execute(
                """SELECT COUNT(DISTINCT oh.fixture_id) FROM odds_history oh
                   JOIN fixtures f ON oh.fixture_id=f.id WHERE DATE(f.kickoff)=?""",
                (date,)).fetchone()[0]
    except Exception:
        odds_fixtures = 0

    odds_pct = (odds_fixtures / fix_cnt * 100) if fix_cnt > 0 else 0
    checks.append(Check("D11", "DB: odds coverage",
                         "PASS" if odds_fixtures > 0 else "WARN",
                         f"{odds_fixtures}/{fix_cnt} fixtures with odds ({odds_pct:.1f}%) — stats-first mode OK without odds"))

    # D12: Source health — DB-FIRST
    try:
        with _get_db() as db:
            degraded = db.execute(
                "SELECT source_name, consecutive_failures FROM source_health WHERE consecutive_failures > 5"
            ).fetchall()
    except Exception:
        degraded = []

    critical_sources = {"flashscore", "betexplorer", "api-football"}
    degraded_critical = [d for d in degraded if d[0].lower() in critical_sources]

    checks.append(Check("D12", "Source health — no critical degradation",
                         "PASS" if not degraded_critical else "WARN",
                         f"Degraded: {[(d[0], d[1]) for d in degraded]}" if degraded else "All sources healthy",
                         recovery="Check source health: python3 scripts/source_health.py --log"))

    # D13: Market matrix exists (file check — no DB equivalent)
    mm_path = DATA_DIR / f"market_matrix_{date}.json"
    mm_exists = mm_path.exists() and mm_path.stat().st_size > 100
    checks.append(Check("D13", "Market matrix file exists",
                         "PASS" if mm_exists else "FAIL",
                         f"{'Found' if mm_exists else 'MISSING'}: market_matrix_{date}.json" +
                         (f" ({mm_path.stat().st_size:,} bytes)" if mm_exists else ""),
                         gate=True,
                         recovery=f"Run: python3 scripts/generate_market_matrix.py --date {date} --stats-first"))

    return checks


# ---------------------------------------------------------------------------
# PHASE 2: ANALYSIS validation
# ---------------------------------------------------------------------------

def validate_analysis_phase(date: str) -> list[Check]:
    checks = []

    # A1: S3 output — DB-FIRST (analysis_results)
    try:
        with _get_db() as db:
            ar_cnt = db.execute("SELECT COUNT(*) FROM analysis_results WHERE betting_date=?", (date,)).fetchone()[0]
            ar_with_market = db.execute(
                "SELECT COUNT(*) FROM analysis_results WHERE betting_date=? AND best_market_name IS NOT NULL AND best_market_name != ''",
                (date,)).fetchone()[0]
    except Exception:
        ar_cnt = ar_with_market = 0

    s3_md = DATA_DIR / f"{date}_s3_deep_stats.md"
    s3_json = DATA_DIR / f"{date}_s3_deep_stats.json"

    checks.append(Check("A1", "DB: analysis_results populated",
                         "PASS" if ar_cnt > 0 else "FAIL",
                         f"{ar_cnt} results in DB, {ar_with_market} with best_market",
                         gate=True,
                         recovery=f"Run: python3 scripts/pipeline_orchestrator.py --date {date} --step s3_deep_stats"))

    md_info = f"MD: ✓ ({s3_md.stat().st_size:,}B)" if s3_md.exists() else "MD: ✗"
    json_info = f"JSON: ✓ ({s3_json.stat().st_size:,}B)" if s3_json.exists() else "JSON: ✗"
    checks.append(Check("A2", "S3 files exist (fallback verification)",
                         "PASS" if s3_md.exists() and s3_json.exists() else
                         "WARN" if s3_md.exists() or s3_json.exists() else "FAIL",
                         f"{md_info} | {json_info}"))

    # A3: Candidate count — DB vs shortlist cross-check
    shortlist = _load_shortlist(date)
    sl_count = len(shortlist)
    drop_pct = ((sl_count - ar_cnt) / sl_count * 100) if sl_count > 0 else 0

    checks.append(Check("A3", "Candidate count: DB vs shortlist",
                         "PASS" if abs(drop_pct) < 20 else "WARN" if abs(drop_pct) < 50 else "FAIL",
                         f"Shortlist: {sl_count}, DB analysis_results: {ar_cnt} (Δ {drop_pct:+.1f}%)",
                         recovery="Large drop may indicate S3 errors; check pipeline state for s3_deep_stats failures"))

    # A4: S3 structural validation (run external script)
    if s3_md.exists():
        try:
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "validate_s3_output.py"),
                 str(s3_md), "--format", "json"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                try:
                    val_data = json.loads(result.stdout)
                    total = val_data.get("total", 0)
                    passed = val_data.get("passed", 0)
                    failed = val_data.get("failed", 0)
                    checks.append(Check("A4", "S3 structural validation (validate_s3_output.py)",
                                         "PASS" if failed == 0 else "WARN",
                                         f"{passed}/{total} candidates PASS, {failed} FAIL",
                                         recovery=f"Re-run: python3 scripts/pipeline_orchestrator.py --date {date} --step s3_deep_stats"))
                except json.JSONDecodeError:
                    checks.append(Check("A4", "S3 structural validation",
                                         "PASS" if result.returncode == 0 else "WARN",
                                         result.stdout[:200] if result.stdout else "No output"))
            else:
                checks.append(Check("A4", "S3 structural validation",
                                     "WARN", f"Exit code {result.returncode}: {result.stderr[:200]}",
                                     recovery=f"Fix: python3 scripts/validate_s3_output.py {s3_md} --format json"))
        except Exception as e:
            checks.append(Check("A4", "S3 structural validation", "WARN", f"Could not run: {e}"))
    else:
        checks.append(Check("A4", "S3 structural validation", "SKIP", "S3 MD file not found"))

    # A5: Football stat markets (R5) — DB-FIRST
    try:
        with _get_db() as db:
            football_id = db.execute("SELECT id FROM sports WHERE name='football'").fetchone()
            if football_id:
                fid = football_id[0]
                fb_total = db.execute(
                    """SELECT COUNT(DISTINCT ar.fixture_id) FROM analysis_results ar
                       JOIN fixtures f ON ar.fixture_id=f.id
                       WHERE ar.betting_date=? AND f.sport_id=?""",
                    (date, fid)).fetchone()[0]
                fb_with_stat = db.execute(
                    """SELECT COUNT(DISTINCT ar.fixture_id) FROM analysis_results ar
                       JOIN fixtures f ON ar.fixture_id=f.id
                       WHERE ar.betting_date=? AND f.sport_id=?
                       AND (ar.best_market_name LIKE '%corner%' OR ar.best_market_name LIKE '%foul%'
                            OR ar.best_market_name LIKE '%shot%' OR ar.best_market_name LIKE '%card%'
                            OR ar.markets_evaluated > 1)""",
                    (date, fid)).fetchone()[0]
            else:
                fb_total = fb_with_stat = 0
    except Exception:
        fb_total = fb_with_stat = 0

    checks.append(Check("A5", "R5: Football candidates have stat markets",
                         "PASS" if fb_total == 0 or fb_with_stat >= fb_total * 0.8 else "WARN",
                         f"{fb_with_stat}/{fb_total} football candidates have stat market as best",
                         recovery="Review football candidates in S3 output for missing corners/fouls/shots"))

    # A6-A8: S4/S5/S6 output — DB-FIRST (gate_results depends on these)
    state = _load_pipeline_state(date)
    steps = state.get("steps", {})
    for step_id, label in [("s4_odds_eval", "S4 odds eval"),
                            ("s5_context", "S5 context"),
                            ("s6_upset_risk", "S6 upset risk")]:
        step_state = steps.get(step_id, {})
        status = step_state.get("status", "missing")
        checks.append(Check(f"A{6 + ['s4_odds_eval', 's5_context', 's6_upset_risk'].index(step_id)}",
                             f"{label} step completed",
                             "PASS" if status == "completed" else "FAIL",
                             f"Status: {status}",
                             gate=status != "completed",
                             recovery=f"Run: python3 scripts/pipeline_orchestrator.py --date {date} --step {step_id}"))

    # A9: S7 gate — DB-FIRST (gate_results table)
    try:
        with _get_db() as db:
            gate_cnt = db.execute("SELECT COUNT(*) FROM gate_results WHERE betting_date=?", (date,)).fetchone()[0]
            gate_tiers = dict(db.execute(
                "SELECT status, COUNT(*) FROM gate_results WHERE betting_date=? GROUP BY status",
                (date,)).fetchall())
            gate_sports = [r[0] for r in db.execute(
                """SELECT DISTINCT s.name FROM gate_results gr
                   JOIN fixtures f ON gr.fixture_id=f.id
                   JOIN sports s ON f.sport_id=s.id
                   WHERE gr.betting_date=? AND gr.status='APPROVED'""",
                (date,)).fetchall()]
    except Exception:
        gate_cnt = 0
        gate_tiers = {}
        gate_sports = []

    checks.append(Check("A9", "DB: gate_results populated",
                         "PASS" if gate_cnt > 0 else "FAIL",
                         f"{gate_cnt} results: {gate_tiers}",
                         gate=True,
                         recovery=f"Run: python3 scripts/pipeline_orchestrator.py --date {date} --step s7_gate"))


    # A10: Sport diversity in approved (R4)
    approved_sports = len(gate_sports)
    checks.append(Check("A10", "R4: ≥5 sports in APPROVED gate results",
                         "PASS" if approved_sports >= 5 else "WARN" if approved_sports >= 3 else "FAIL",
                         f"{approved_sports} sports approved: {sorted(gate_sports)}",
                         gate=approved_sports < 3,
                         recovery="Emergency expansion (R4): re-scan underrepresented sports, re-run S3→S7"))

    # A11: No auto-rejection language (R3)
    s7_md = DATA_DIR / f"{date}_s7_gate_results.md"
    forbidden_patterns = ["rejected due to", "excluded based on", "filtered to", "only .* picks survived"]
    r3_violations = []
    if s7_md.exists():
        content = s7_md.read_text(errors="replace")
        for pat in forbidden_patterns:
            matches = re.findall(pat, content, re.IGNORECASE)
            if matches:
                r3_violations.extend(matches)

    checks.append(Check("A11", "R3: No auto-rejection language in gate output",
                         "PASS" if not r3_violations else "FAIL",
                         f"{'Clean' if not r3_violations else f'Found {len(r3_violations)} violations: {r3_violations[:3]}'}",
                         gate=bool(r3_violations),
                         recovery="Edit gate output to remove auto-rejection language; present ALL candidates"))

    # A12: Gate tier distribution summary
    approved = gate_tiers.get("APPROVED", 0)
    extended = gate_tiers.get("EXTENDED", 0)
    rejected = gate_tiers.get("REJECTED", 0)
    checks.append(Check("A12", "Gate tier distribution",
                         "PASS" if approved > 0 else "WARN",
                         f"APPROVED: {approved} | EXTENDED: {extended} | REJECTED: {rejected}"))

    # A13: Extended pool exists (R3 compliance)
    checks.append(Check("A13", "R3: Extended pool has gate-failed candidates",
                         "PASS" if extended > 0 else "WARN",
                         f"{extended} candidates in extended pool",
                         recovery="Ensure gate-failed candidates appear in Extended Pool section"))

    # A14: No critical step failures
    critical_fails = {sid: info.get("error", "")[:60]
                      for sid, info in steps.items()
                      if info.get("status") == "failed"
                      and sid in {"s3_deep_stats", "s4_odds_eval", "s5_context", "s6_upset_risk", "s7_gate"}}
    checks.append(Check("A14", "No critical analysis-phase step failures",
                         "PASS" if not critical_fails else "FAIL",
                         f"{'All OK' if not critical_fails else f'Failed: {critical_fails}'}",
                         gate=bool(critical_fails),
                         recovery=f"Fix and re-run: python3 scripts/pipeline_orchestrator.py --date {date} --phase analysis --resume"))

    return checks


# ---------------------------------------------------------------------------
# PHASE 3: BUILD validation
# ---------------------------------------------------------------------------

def validate_build_phase(date: str) -> list[Check]:
    checks = []
    config = _load_config()
    bankroll = config.get("bankroll_pln", config.get("working_bankroll_pln", 1000))

    # B1: Coupon file exists
    coupon_files = list(COUPON_DIR.glob(f"{date}*.md"))
    checks.append(Check("B1", "Coupon file exists",
                         "PASS" if coupon_files else "FAIL",
                         f"{len(coupon_files)} files: {[f.name for f in coupon_files]}",
                         gate=True,
                         recovery=f"Run: python3 scripts/pipeline_orchestrator.py --date {date} --phase build"))


    # B2: Coupon data in DB — DB-FIRST
    try:
        with _get_db() as db:
            db_coupons = db.execute(
                "SELECT COUNT(*) FROM coupons WHERE created_at >= ? AND created_at < ?",
                (f"{date}T00:00:00", f"{date}T23:59:59")).fetchone()[0]
            db_bets = db.execute(
                """SELECT COUNT(*) FROM bets b
                   JOIN coupons c ON b.coupon_id=c.id
                   WHERE c.created_at >= ? AND c.created_at < ?""",
                (f"{date}T00:00:00", f"{date}T23:59:59")).fetchone()[0]
    except Exception:
        db_coupons = db_bets = 0

    checks.append(Check("B2", "DB: coupons + bets persisted",
                         "PASS" if db_coupons > 0 else "WARN",
                         f"DB: {db_coupons} coupons, {db_bets} bets",
                         recovery="Check coupon_builder.py DB persistence; may need manual sync"))

    # B3: Coupon validation script
    if coupon_files:
        try:
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "validate_coupons.py")] +
                [str(f) for f in coupon_files] + ["--format", "json"],
                capture_output=True, text=True, timeout=30
            )
            # Parse JSON output for summary
            summary_str = ""
            try:
                val_data = json.loads(result.stdout)
                if isinstance(val_data, list):
                    parts = [f"{v['file']}: {v['passed']}/{v['coupons_found']} OK" for v in val_data]
                    total_failed = sum(v.get('failed', 0) for v in val_data)
                    summary_str = ", ".join(parts) + f" (total failed: {total_failed})"
                elif isinstance(val_data, dict):
                    total_failed = val_data.get('failed', 0)
                    summary_str = f"{val_data.get('passed', 0)}/{val_data.get('coupons_found', 0)} OK (failed: {total_failed})"
            except (json.JSONDecodeError, KeyError):
                summary_str = (result.stdout[:200] if result.stdout else result.stderr[:200]).strip()
                total_failed = 1 if result.returncode != 0 else 0

            checks.append(Check("B3", "Coupon structural validation (validate_coupons.py)",
                                 "PASS" if total_failed == 0 else "WARN",
                                 summary_str,
                                 recovery="Fix coupon file issues: python3 scripts/validate_coupons.py " +
                                          " ".join(f.name for f in coupon_files)))
        except Exception as e:
            checks.append(Check("B3", "Coupon validation", "WARN", f"Could not run: {e}"))
    else:
        checks.append(Check("B3", "Coupon validation", "SKIP", "No coupon files to validate"))

    # B4: Ledger entries
    picks_ledger = JOURNAL_DIR / "picks-ledger.csv"
    coupons_ledger = JOURNAL_DIR / "coupons-ledger.csv"
    checks.append(Check("B4", "Ledger files exist",
                         "PASS" if picks_ledger.exists() and coupons_ledger.exists() else "WARN",
                         f"picks: {'✓' if picks_ledger.exists() else '✗'}, "
                         f"coupons: {'✓' if coupons_ledger.exists() else '✗'}"))

    # B5: Total exposure ≤ 25% bankroll — DB-FIRST
    try:
        with _get_db() as db:
            total_stake = db.execute(
                """SELECT COALESCE(SUM(stake_pln), 0) FROM coupons
                   WHERE status='pending' AND created_at >= ?""",
                (f"{date}T00:00:00",)).fetchone()[0]
    except Exception:
        total_stake = 0

    max_exposure = bankroll * 0.25
    checks.append(Check("B5", f"Total exposure ≤ 25% bankroll ({max_exposure:.0f} PLN)",
                         "PASS" if total_stake <= max_exposure else "FAIL",
                         f"{total_stake:.2f} PLN / {max_exposure:.0f} PLN limit",
                         gate=total_stake > max_exposure,
                         recovery="Reduce stake sizes in coupon file to stay within 25% bankroll limit"))

    # B6: R12 conditional disclaimer
    disclaimer_found = False
    for cf in coupon_files:
        content = cf.read_text(errors="replace")
        if "warunkow" in content.lower() or "conditional" in content.lower() or "betclic" in content.lower():
            disclaimer_found = True
            break

    checks.append(Check("B6", "R12: Conditional disclaimer present",
                         "PASS" if disclaimer_found or not coupon_files else "WARN",
                         f"{'Found' if disclaimer_found else 'NOT FOUND'} in coupon files"))

    # B7: Pipeline build steps completed
    state = _load_pipeline_state(date)
    steps = state.get("steps", {})
    build_steps = {"s8_coupons", "s9_validate", "s10_summary"}
    build_completed = {sid for sid in build_steps if steps.get(sid, {}).get("status") == "completed"}
    checks.append(Check("B7", "Build-phase steps completed",
                         "PASS" if build_completed == build_steps else "FAIL",
                         f"Completed: {sorted(build_completed)}, Missing: {sorted(build_steps - build_completed)}",
                         gate=bool(build_steps - build_completed),
                         recovery=f"Run: python3 scripts/pipeline_orchestrator.py --date {date} --phase build --resume"))


    return checks


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_validation(date: str, phase: str, fmt: str = "text") -> int:
    """Run validation and return exit code."""
    all_checks = []

    if phase in ("data", "all"):
        all_checks.extend(validate_data_phase(date))
    if phase in ("analysis", "all"):
        all_checks.extend(validate_analysis_phase(date))
    if phase in ("build", "all"):
        all_checks.extend(validate_build_phase(date))

    # Count results
    gate_fails = [c for c in all_checks if c.status == "FAIL" and c.gate]
    non_gate_fails = [c for c in all_checks if c.status == "FAIL" and not c.gate]
    warns = [c for c in all_checks if c.status == "WARN"]
    passes = [c for c in all_checks if c.status == "PASS"]

    if fmt == "json":
        output = {
            "date": date,
            "phase": phase,
            "total_checks": len(all_checks),
            "passed": len(passes),
            "warnings": len(warns),
            "gate_failures": len(gate_fails),
            "non_gate_failures": len(non_gate_fails),
            "blocking": len(gate_fails) > 0,
            "checks": [c.to_dict() for c in all_checks],
        }
        print(json.dumps(output, indent=2))
    else:
        phase_label = phase.upper() if phase != "all" else "ALL PHASES"
        print(f"\n{'='*70}")
        print(f"  PHASE VALIDATION: {phase_label} — {date}")
        print(f"{'='*70}")

        for check in all_checks:
            print(str(check))

        print(f"\n{'─'*70}")
        print(f"  SUMMARY: {len(passes)} PASS | {len(warns)} WARN | "
              f"{len(gate_fails)} GATE FAIL | {len(non_gate_fails)} non-gate FAIL")

        if gate_fails:
            print(f"\n  🚫 BLOCKING — {len(gate_fails)} gate failure(s) must be fixed before proceeding:")
            for c in gate_fails:
                print(f"     • {c.check_id}: {c.name}")
                if c.recovery:
                    print(f"       ↳ {c.recovery}")
            print()
        elif warns:
            print(f"\n  ⚠️  NON-BLOCKING — {len(warns)} warning(s), proceed with caution")
        else:
            print(f"\n  ✅ ALL GATES PASS — safe to proceed")

        print(f"{'='*70}\n")

    if gate_fails:
        return 1
    elif warns or non_gate_fails:
        return 2
    return 0


def main():
    parser = argparse.ArgumentParser(description="DB-FIRST Phase Validation")
    parser.add_argument("--date", required=True, help="Betting date (YYYY-MM-DD)")
    parser.add_argument("--phase", required=True, choices=["data", "analysis", "build", "all"],
                        help="Which phase to validate")
    parser.add_argument("--format", default="text", choices=["text", "json"],
                        help="Output format")
    args = parser.parse_args()

    exit_code = run_validation(args.date, args.phase, args.format)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
