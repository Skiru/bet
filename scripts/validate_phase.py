#!/usr/bin/env python3
"""DB-first session-readiness validation for the betting pipeline.

Validates live readiness of the current betting session from DB rows and
operational JSON artifacts. Legacy ``pipeline_state`` files are treated as
optional context only and are no longer a hard prerequisite.

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
import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

DATA_DIR = Path(__file__).resolve().parent.parent / "betting" / "data"
COUPON_DIR = Path(__file__).resolve().parent.parent / "betting" / "coupons"
JOURNAL_DIR = Path(__file__).resolve().parent.parent / "betting" / "journal"
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "betting_config.json"
SCRIPTS_DIR = Path(__file__).resolve().parent
UNRESOLVED_SESSION_STATUSES = ("", "active", "open", "pending", "placed")


class Check:
    """Single validation check result."""

    def __init__(
        self,
        check_id: str,
        name: str,
        status: str,
        value: str,
        gate: bool = False,
        recovery: str = "",
    ):
        self.check_id = check_id
        self.name = name
        self.status = status
        self.value = value
        self.gate = gate
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
    from bet.db.connection import get_db

    return get_db()


def _load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return None


def _load_pipeline_step_record(date: str, step: str) -> dict | None:
    try:
        with _get_db() as db:
            row = db.execute(
                "SELECT status, stats, error_message FROM pipeline_runs WHERE date = ? AND step = ?",
                (date, step),
            ).fetchone()
    except Exception:
        return None

    if not row:
        return None

    stats_raw = row[1]
    stats = None
    if stats_raw:
        try:
            stats = json.loads(stats_raw)
        except json.JSONDecodeError:
            stats = "__MALFORMED_JSON__"

    return {
        "status": row[0],
        "stats": stats,
        "error_message": row[2] or "",
    }


def _load_pipeline_state(date: str) -> dict:
    state_path = DATA_DIR / "pipeline_state" / f"pipeline_{date}.json"
    state = _load_json(state_path)
    return state if isinstance(state, dict) else {}


def _load_config() -> dict:
    config = _load_json(CONFIG_PATH)
    return config if isinstance(config, dict) else {}


def _parse_date(date: str) -> datetime:
    return datetime.strptime(date, "%Y-%m-%d")


def _extract_iso_date(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(normalized).date().isoformat()
    except ValueError:
        match = re.search(r"\d{4}-\d{2}-\d{2}", value)
        return match.group(0) if match else None


def _previous_betting_day_window(date: str) -> tuple[str, str, str]:
    current_day = _parse_date(date).date()
    previous_day = current_day - timedelta(days=1)
    return (
        previous_day.isoformat(),
        f"{previous_day.isoformat()}T06:00:00",
        f"{date}T05:59:59",
    )


def _table_columns(db, table_name: str) -> set[str]:
    rows = _safe_rows(db, f"PRAGMA table_info({table_name})")
    return {str(row[1]) for row in rows if len(row) > 1}


def _coupon_time_expression(columns: set[str], alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    if "placed_at" in columns and "created_at" in columns:
        return f"COALESCE({prefix}placed_at, {prefix}created_at, '')"
    if "created_at" in columns:
        return f"COALESCE({prefix}created_at, '')"
    if "placed_at" in columns:
        return f"COALESCE({prefix}placed_at, '')"
    return "''"


def _load_manual_verification_count(previous_betting_day: str) -> tuple[int | None, bool]:
    ledger_path = JOURNAL_DIR / "picks-ledger.csv"
    if not ledger_path.exists():
        return None, False

    try:
        with open(ledger_path, newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            fieldnames = set(reader.fieldnames or [])
            if {"betting_day", "settlement_source"} - fieldnames:
                return None, False

            count = 0
            for row in reader:
                if row.get("betting_day") != previous_betting_day:
                    continue
                if row.get("settlement_source") == "manual_verification_required":
                    count += 1
            return count, True
    except OSError:
        return None, False


def assess_s0_readiness(date: str, *, db_getter=None, data_dir: Path | None = None) -> dict:
    previous_day, session_start, session_end = _previous_betting_day_window(date)
    summary_dir = data_dir or DATA_DIR
    summary_path = summary_dir / "betclic_learning_summary.json"
    summary = _load_json(summary_path)
    learning_summary = summary if isinstance(summary, dict) else {}
    analyzed_at = learning_summary.get("analyzed_at")
    analyzed_date = _extract_iso_date(analyzed_at)
    manual_count, manual_available = _load_manual_verification_count(previous_day)

    readiness = {
        "target_betting_day": date,
        "previous_betting_day": previous_day,
        "betting_day_window": {"start": session_start, "end": session_end},
        "db_available": True,
        "activity_detected": False,
        "coupon_counts": {"total": 0, "pending": 0, "settled": 0},
        "bet_counts": {"total": 0, "pending": 0, "settled": 0},
        "manual_verification": {"available": manual_available, "count": manual_count},
        "decision_review": {"snapshots": 0, "outcomes": 0, "missing_outcomes": 0},
        "learning_summary": {
            "path": summary_path.name,
            "exists": summary_path.exists(),
            "analyzed_at": analyzed_at,
            "analyzed_for_session_date": bool(analyzed_date and analyzed_date >= date),
            "warning": learning_summary.get("warning", ""),
            "total_coupons": int(learning_summary.get("total_coupons", 0) or 0),
        },
        "blocking_reasons": [],
        "ready": True,
    }

    db_factory = db_getter or _get_db
    try:
        with db_factory() as db:
            coupon_columns = _table_columns(db, "coupons")
            bet_columns = _table_columns(db, "bets")
            coupon_time_expr = _coupon_time_expression(coupon_columns)
            coupon_time_filter = (
                f"datetime({coupon_time_expr}) >= datetime(?) AND datetime({coupon_time_expr}) <= datetime(?)"
            )
            unresolved_placeholders = ", ".join("?" for _ in UNRESOLVED_SESSION_STATUSES)

            readiness["coupon_counts"]["total"] = int(
                _safe_scalar(
                    db,
                    f"SELECT COUNT(*) FROM coupons WHERE {coupon_time_filter}",
                    (session_start, session_end),
                )
                or 0
            )
            readiness["coupon_counts"]["pending"] = int(
                _safe_scalar(
                    db,
                    (
                        "SELECT COUNT(*) FROM coupons WHERE "
                        f"{coupon_time_filter} AND LOWER(COALESCE(status, '')) IN ({unresolved_placeholders})"
                    ),
                    (session_start, session_end, *UNRESOLVED_SESSION_STATUSES),
                )
                or 0
            )
            readiness["coupon_counts"]["settled"] = max(
                readiness["coupon_counts"]["total"] - readiness["coupon_counts"]["pending"],
                0,
            )

            if coupon_columns:
                bet_coupon_time_expr = _coupon_time_expression(coupon_columns, alias="c")
                bet_coupon_time_filter = (
                    f"datetime({bet_coupon_time_expr}) >= datetime(?) AND datetime({bet_coupon_time_expr}) <= datetime(?)"
                )
                readiness["bet_counts"]["total"] = int(
                    _safe_scalar(
                        db,
                        "SELECT COUNT(*) FROM bets b JOIN coupons c ON b.coupon_id = c.id WHERE "
                        f"{bet_coupon_time_filter}",
                        (session_start, session_end),
                    )
                    or 0
                )
                if "status" in bet_columns:
                    readiness["bet_counts"]["pending"] = int(
                        _safe_scalar(
                            db,
                            (
                                "SELECT COUNT(*) FROM bets b JOIN coupons c ON b.coupon_id = c.id WHERE "
                                f"{bet_coupon_time_filter} AND LOWER(COALESCE(b.status, '')) IN ({unresolved_placeholders})"
                            ),
                            (session_start, session_end, *UNRESOLVED_SESSION_STATUSES),
                        )
                        or 0
                    )
                readiness["bet_counts"]["settled"] = max(
                    readiness["bet_counts"]["total"] - readiness["bet_counts"]["pending"],
                    0,
                )

            readiness["decision_review"]["snapshots"] = int(
                _safe_scalar(
                    db,
                    "SELECT COUNT(*) FROM decision_snapshots WHERE betting_date = ?",
                    (previous_day,),
                )
                or 0
            )
            readiness["decision_review"]["outcomes"] = int(
                _safe_scalar(
                    db,
                    "SELECT COUNT(*) FROM decision_outcomes WHERE betting_date = ?",
                    (previous_day,),
                )
                or 0
            )
            readiness["decision_review"]["missing_outcomes"] = max(
                readiness["decision_review"]["snapshots"] - readiness["decision_review"]["outcomes"],
                0,
            )
    except Exception as exc:
        readiness["db_available"] = False
        readiness["blocking_reasons"].append(f"db_unavailable:{exc}")
        readiness["ready"] = False
        return readiness

    readiness["activity_detected"] = any(
        (
            readiness["coupon_counts"]["total"],
            readiness["bet_counts"]["total"],
            readiness["decision_review"]["snapshots"],
            readiness["decision_review"]["outcomes"],
        )
    )

    if readiness["coupon_counts"]["pending"] or readiness["bet_counts"]["pending"]:
        readiness["blocking_reasons"].append("previous_day_unsettled")

    if readiness["decision_review"]["missing_outcomes"] > 0:
        readiness["blocking_reasons"].append("decision_review_incomplete")

    learning_current = readiness["learning_summary"]["analyzed_for_session_date"]
    learning_warning = readiness["learning_summary"]["warning"]
    if readiness["activity_detected"] and (not learning_current or learning_warning):
        readiness["blocking_reasons"].append("betclic_learning_not_current")

    readiness["ready"] = not readiness["blocking_reasons"]
    return readiness


def _resolve_shortlist_path(date: str) -> Path | None:
    for name in (f"{date}_s2_shortlist.json", f"{date.replace('-', '')}_s2_shortlist.json"):
        path = DATA_DIR / name
        if path.exists():
            return path
    return None


def _load_shortlist(date: str) -> list:
    path = _resolve_shortlist_path(date)
    if not path:
        return []
    data = _load_json(path)
    if not isinstance(data, dict):
        return []
    return data.get("candidates", data.get("shortlist", []))


def _resolve_s3_path(date: str) -> Path:
    return DATA_DIR / f"{date}_s3_deep_stats.json"


def _load_s3_analyses(date: str) -> list[dict]:
    data = _load_json(_resolve_s3_path(date))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [item for item in data.get("analyses", []) if isinstance(item, dict)]
    return []


def _resolve_gate_results_path(date: str) -> Path:
    return DATA_DIR / f"{date}_s7_gate_results.json"


def _load_gate_results(date: str) -> dict | None:
    data = _load_json(_resolve_gate_results_path(date))
    return data if isinstance(data, dict) else None


def _safe_scalar(db, query: str, params: tuple = (), default=0):
    try:
        row = db.execute(query, params).fetchone()
    except Exception:
        return default
    return row[0] if row else default


def _safe_rows(db, query: str, params: tuple = ()) -> list[tuple]:
    try:
        return db.execute(query, params).fetchall()
    except Exception:
        return []


def _count_analyses_with_key(analyses: list[dict], key: str) -> int:
    return sum(1 for analysis in analyses if key in analysis)


def _analysis_has_s4_data(analysis: dict) -> bool:
    if analysis.get("ev") is not None or analysis.get("ev_source"):
        return True
    odds = analysis.get("odds") or {}
    return bool(odds.get("market_best") or odds.get("betclic"))


def _count_s4_analyses(analyses: list[dict]) -> int:
    return sum(1 for analysis in analyses if _analysis_has_s4_data(analysis))


def _has_current_gate_shape(data: dict | None) -> bool:
    if not isinstance(data, dict):
        return False
    gate_results = data.get("gate_results")
    if not isinstance(gate_results, dict):
        return False
    return all(isinstance(gate_results.get(bucket, []), list) for bucket in ("approved", "extended_pool", "rejected"))


def _json_gate_counts(data: dict | None) -> dict[str, int]:
    counts = {"approved": 0, "extended_pool": 0, "rejected": 0}
    if not _has_current_gate_shape(data):
        return counts
    gate_results = data["gate_results"]
    for bucket in counts:
        counts[bucket] = len(gate_results.get(bucket, []))
    return counts


def _db_gate_counts(db, date: str) -> dict[str, int]:
    counts = {"approved": 0, "extended_pool": 0, "rejected": 0}
    rows = _safe_rows(
        db,
        "SELECT status, COUNT(*) FROM gate_results WHERE betting_date=? GROUP BY status",
        (date,),
    )
    for status, count in rows:
        upper = str(status or "").upper()
        if upper.startswith("APPROVED"):
            counts["approved"] += count
        elif upper.startswith("EXTENDED"):
            counts["extended_pool"] += count
        else:
            counts["rejected"] += count
    return counts


def _format_gate_counts(counts: dict[str, int]) -> str:
    return (
        f"approved={counts.get('approved', 0)}, "
        f"extended_pool={counts.get('extended_pool', 0)}, "
        f"rejected={counts.get('rejected', 0)}"
    )


def _find_repeat_handoff_artifacts(date: str) -> list[Path]:
    artifacts: list[Path] = []
    for base_dir in (DATA_DIR, JOURNAL_DIR):
        for pattern in (
            f"*{date}*repeat*.json",
            f"*{date.replace('-', '')}*repeat*.json",
            f"*{date}*48h*.json",
            f"*{date.replace('-', '')}*48h*.json",
        ):
            artifacts.extend(base_dir.glob(pattern))
    unique = {str(path): path for path in artifacts}
    return sorted(unique.values())


def _parse_validate_coupons_output(stdout: str, returncode: int) -> tuple[int, str]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        summary = (stdout[:200] or "No output").strip()
        return (1 if returncode != 0 else 0), summary

    if isinstance(payload, list):
        total_failed = 0
        parts = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            failed = item.get("failed", 0) or 0
            if item.get("global_errors"):
                failed += len(item["global_errors"])
            total_failed += failed
            parts.append(f"{item.get('file', '?')}: {item.get('passed', 0)}/{item.get('coupons_found', 0)} OK")
        return total_failed, ", ".join(parts) if parts else "No coupon validation results"

    if isinstance(payload, dict):
        total_failed = payload.get("failed", 0) or 0
        if payload.get("global_errors"):
            total_failed += len(payload["global_errors"])
        summary = f"{payload.get('passed', 0)}/{payload.get('coupons_found', 0)} OK (failed: {payload.get('failed', 0)})"
        return total_failed, summary

    return (1 if returncode != 0 else 0), "Unexpected validate_coupons output shape"


def validate_data_phase(date: str) -> list[Check]:
    checks: list[Check] = []
    s0_readiness = assess_s0_readiness(date)

    manual_verification = s0_readiness["manual_verification"]
    manual_value = manual_verification["count"] if manual_verification["available"] else "unavailable"
    previous_day = s0_readiness["previous_betting_day"]

    if not s0_readiness["db_available"]:
        settlement_status = "FAIL"
        settlement_value = f"Cannot verify {previous_day}: {', '.join(s0_readiness['blocking_reasons'])}"
    else:
        settlement_status = (
            "FAIL"
            if s0_readiness["coupon_counts"]["pending"] or s0_readiness["bet_counts"]["pending"]
            else "PASS"
        )
        settlement_value = (
            f"{previous_day} pending coupons={s0_readiness['coupon_counts']['pending']}/{s0_readiness['coupon_counts']['total']}, "
            f"pending bets={s0_readiness['bet_counts']['pending']}/{s0_readiness['bet_counts']['total']}, "
            f"manual verification={manual_value}"
        )

    checks.append(
        Check(
            "S0.1",
            "Previous betting day settlement completeness",
            settlement_status,
            settlement_value,
            gate=settlement_status == "FAIL",
            recovery=f"Run: PYTHONPATH=src .venv/bin/python3 scripts/settle_on_finish.py --betting-day {previous_day}",
        )
    )

    decision_review = s0_readiness["decision_review"]
    if not s0_readiness["db_available"]:
        decision_status = "SKIP"
        decision_value = "Skipped because DB evidence for previous-day settlement is unavailable"
    elif decision_review["missing_outcomes"] > 0:
        decision_status = "FAIL"
        decision_value = (
            f"{previous_day} decision snapshots={decision_review['snapshots']}, outcomes={decision_review['outcomes']}"
        )
    elif s0_readiness["activity_detected"] and decision_review["snapshots"] == 0:
        decision_status = "WARN"
        decision_value = f"{previous_day} has no decision snapshots to evaluate"
    else:
        decision_status = "PASS"
        decision_value = (
            f"{previous_day} decision snapshots={decision_review['snapshots']}, outcomes={decision_review['outcomes']}"
        )

    checks.append(
        Check(
            "S0.2",
            "Previous betting day decision-review coverage",
            decision_status,
            decision_value,
            gate=decision_status == "FAIL",
            recovery=f"Run: PYTHONPATH=src .venv/bin/python3 scripts/evaluate_decisions.py --date {previous_day} --verbose",
        )
    )

    learning_summary = s0_readiness["learning_summary"]
    if s0_readiness["activity_detected"]:
        learning_status = "PASS" if learning_summary["analyzed_for_session_date"] and not learning_summary["warning"] else "FAIL"
        learning_value = (
            f"{learning_summary['path']} analyzed_at={learning_summary['analyzed_at'] or 'missing'}, "
            f"current_for_session={'yes' if learning_summary['analyzed_for_session_date'] else 'no'}"
        )
        if learning_summary["warning"]:
            learning_value = f"{learning_value}, warning={learning_summary['warning']}"
    else:
        learning_status = "PASS"
        learning_value = (
            f"No previous-day betting activity detected; {learning_summary['path']} "
            f"current_for_session={'yes' if learning_summary['analyzed_for_session_date'] else 'no'}"
        )

    checks.append(
        Check(
            "S0.3",
            "Betclic learning summary is current for this session",
            learning_status,
            learning_value,
            gate=learning_status == "FAIL",
            recovery="Run: PYTHONPATH=src .venv/bin/python3 scripts/analyze_betclic_learning.py",
        )
    )

    legacy_state = _load_pipeline_state(date)
    shortlist = _load_shortlist(date)
    shortlist_path = _resolve_shortlist_path(date)
    shortlist_sports = sorted({candidate.get("sport", "unknown") for candidate in shortlist if candidate.get("sport")})
    tipster_support_count = sum(1 for candidate in shortlist if candidate.get("tipster_support") or candidate.get("tipster_count"))

    checks.append(
        Check(
            "D1",
            "Legacy pipeline_state file is optional",
            "PASS",
            f"Found optional pipeline_state/pipeline_{date}.json" if legacy_state else "Absent — using live DB/file readiness instead",
        )
    )

    db_error = None
    scan_cnt = 0
    fixture_cnt = 0
    team_form_cnt = 0
    match_stats_fixture_cnt = 0
    tipster_pick_cnt = 0
    tipster_consensus_cnt = 0
    scraper_success_cnt = 0
    degraded: list[tuple] = []
    scan_sports: list[str] = []

    try:
        with _get_db() as db:
            scan_cnt = _safe_scalar(db, "SELECT COUNT(*) FROM scan_results WHERE betting_date=?", (date,))
            fixture_cnt = _safe_scalar(db, "SELECT COUNT(*) FROM fixtures WHERE DATE(kickoff)=?", (date,))
            team_form_cnt = _safe_scalar(db, "SELECT COUNT(*) FROM team_form WHERE updated_at LIKE ?", (f"{date}%",))
            match_stats_fixture_cnt = _safe_scalar(
                db,
                """
                SELECT COUNT(DISTINCT ms.fixture_id)
                FROM match_stats ms
                JOIN fixtures f ON ms.fixture_id=f.id
                WHERE DATE(f.kickoff)=?
                """,
                (date,),
            )
            tipster_pick_cnt = _safe_scalar(db, "SELECT COUNT(*) FROM tipster_picks WHERE betting_date=?", (date,))
            tipster_consensus_cnt = _safe_scalar(db, "SELECT COUNT(*) FROM tipster_consensus WHERE betting_date=?", (date,))
            scraper_success_cnt = _safe_scalar(
                db,
                "SELECT COUNT(*) FROM scraper_runs WHERE status='success' AND DATE(COALESCE(finished_at, started_at))=?",
                (date,),
            )
            degraded = _safe_rows(db, "SELECT source_name, consecutive_failures FROM source_health WHERE consecutive_failures > 5")
            scan_sports = [
                row[0]
                for row in _safe_rows(
                    db,
                    "SELECT DISTINCT sport FROM scan_results WHERE betting_date=? ORDER BY sport",
                    (date,),
                )
            ]
    except Exception as exc:
        db_error = str(exc)

    checks.append(
        Check(
            "D2",
            "DB connection available",
            "PASS" if db_error is None else "FAIL",
            "Connected to betting.db" if db_error is None else f"Error: {db_error}",
            gate=db_error is not None,
            recovery="Check betting/data/betting.db and DB schema availability",
        )
    )

    checks.append(
        Check(
            "D3",
            "S1 scan results available in DB",
            "PASS" if scan_cnt > 0 else "FAIL",
            f"{scan_cnt} rows across {len(scan_sports)} sports: {scan_sports}",
            gate=True,
            recovery=f"Run: PYTHONPATH=src .venv/bin/python3 scripts/discover_events.py --date {date} --verbose",
        )
    )

    checks.append(
        Check(
            "D4",
            "S1 fixture universe available in DB",
            "PASS" if fixture_cnt > 0 else "FAIL",
            f"{fixture_cnt} fixtures for {date}",
            gate=True,
            recovery=f"Run: PYTHONPATH=src .venv/bin/python3 scripts/discover_events.py --date {date} --verbose",
        )
    )

    market_matrix_path = DATA_DIR / f"market_matrix_{date}.json"
    market_matrix_exists = market_matrix_path.exists() and market_matrix_path.stat().st_size > 100
    checks.append(
        Check(
            "D5",
            "S1 market matrix artifact present",
            "PASS" if market_matrix_exists else "FAIL",
            f"Found {market_matrix_path.name} ({market_matrix_path.stat().st_size:,} bytes)" if market_matrix_exists else f"Missing {market_matrix_path.name}",
            gate=True,
            recovery=f"Regenerate today's market matrix for {date} before continuing",
        )
    )

    checks.append(
        Check(
            "D6",
            "S1e shortlist artifact present",
            "PASS" if shortlist else "FAIL",
            f"{len(shortlist)} candidates from {shortlist_path.name}" if shortlist_path and shortlist else f"Missing or empty shortlist for {date}",
            gate=True,
            recovery=f"Run: PYTHONPATH=src .venv/bin/python3 scripts/build_shortlist.py --date {date} --stats-first",
        )
    )

    tipster_json_exists = any(
        (DATA_DIR / name).exists() for name in (f"{date}_tipster_consensus.json", f"tipster_aggregation_{date}.json")
    )
    tipster_ready = any((tipster_pick_cnt, tipster_consensus_cnt, tipster_support_count, tipster_json_exists))
    checks.append(
        Check(
            "D7",
            "S2 tipster cross-reference readiness",
            "PASS" if tipster_ready else "WARN",
            (
                f"DB picks={tipster_pick_cnt}, DB consensus={tipster_consensus_cnt}, "
                f"shortlist tipster_support={tipster_support_count}, JSON={'yes' if tipster_json_exists else 'no'}"
            ),
            recovery=f"Run: PYTHONPATH=src .venv/bin/python3 scripts/tipster_xref.py --date {date}",
        )
    )

    checks.append(
        Check(
            "D8",
            "S2.3 scraper warehouse readiness",
            "PASS" if scraper_success_cnt > 0 else "WARN",
            f"{scraper_success_cnt} successful scraper_runs recorded for {date}",
            recovery=f"Run: PYTHONPATH=src .venv/bin/python3 scripts/run_scrapers.py --date {date} --verbose",
        )
    )

    stats_ready = team_form_cnt > 0 or match_stats_fixture_cnt > 0
    checks.append(
        Check(
            "D9",
            "S2.5 enrichment / S3-ready stats surfaces",
            "PASS" if stats_ready else "WARN",
            f"team_form rows updated today={team_form_cnt}, fixtures with match_stats={match_stats_fixture_cnt}",
            recovery=f"Run: PYTHONPATH=src .venv/bin/python3 scripts/data_enrichment_agent.py --date {date} --verbose",
        )
    )

    checks.append(
        Check(
            "D10",
            "Shortlist sport diversity",
            "PASS" if len(shortlist_sports) >= 3 else "WARN",
            f"{len(shortlist_sports)} sports in shortlist: {shortlist_sports}",
            recovery="Expand shortlist coverage if today's session looks too narrow",
        )
    )

    critical_sources = {"flashscore", "betexplorer", "api-football"}
    degraded_critical = [row for row in degraded if str(row[0]).lower() in critical_sources]
    checks.append(
        Check(
            "D11",
            "Source health has no critical degradation",
            "PASS" if not degraded_critical else "WARN",
            "All critical sources healthy" if not degraded_critical else f"Degraded critical sources: {[(row[0], row[1]) for row in degraded_critical]}",
            recovery="Review source_health and recent fetch failures before a full rerun",
        )
    )

    return checks


def validate_analysis_phase(date: str) -> list[Check]:
    checks: list[Check] = []

    analyses = _load_s3_analyses(date)
    s3_json_count = len(analyses)

    # ⛔ CRITICAL CHECK (post-mortem 2026-05-24): S3 analyzed only 3/552 candidates.
    # If S3 analyzed <20% of shortlist, something went catastrophically wrong.
    shortlist_for_s3 = _load_shortlist(date)
    if shortlist_for_s3 and s3_json_count > 0:
        coverage_pct = s3_json_count / len(shortlist_for_s3) * 100
        if coverage_pct < 20 and len(shortlist_for_s3) > 20:
            checks.append(PhaseCheck(
                "S3→S2 coverage sanity",
                "FAIL",
                f"S3 analyzed {s3_json_count}/{len(shortlist_for_s3)} candidates ({coverage_pct:.0f}%) — "
                f"CATASTROPHIC LOSS! deep_stats likely used wrong shortlist file.",
                severity="critical",
                recovery=f"Re-run: PYTHONPATH=src .venv/bin/python3 scripts/deep_stats_report.py --date {date} "
                         f"--shortlist betting/data/{date}_s2_shortlist.json --verbose",
            ))

    gate_json = _load_gate_results(date)
    json_gate_counts = _json_gate_counts(gate_json)

    db_error = None
    analysis_db_count = 0
    analysis_with_market = 0
    db_s4_count = 0
    db_context_count = 0
    db_upset_count = 0
    db_gate_counts = {"approved": 0, "extended_pool": 0, "rejected": 0}

    try:
        with _get_db() as db:
            analysis_db_count = _safe_scalar(db, "SELECT COUNT(*) FROM analysis_results WHERE betting_date=?", (date,))
            analysis_with_market = _safe_scalar(
                db,
                "SELECT COUNT(*) FROM analysis_results WHERE betting_date=? AND best_market_name IS NOT NULL AND best_market_name != ''",
                (date,),
            )
            db_s4_count = _safe_scalar(
                db,
                """
                SELECT COUNT(*) FROM analysis_results
                WHERE betting_date=?
                  AND stats_summary_json IS NOT NULL
                  AND (
                    stats_summary_json LIKE '%\"ev\"%'
                    OR stats_summary_json LIKE '%\"ev_source\"%'
                    OR stats_summary_json LIKE '%\"odds_market_best\"%'
                  )
                """,
                (date,),
            )
            db_context_count = _safe_scalar(
                db,
                "SELECT COUNT(*) FROM analysis_results WHERE betting_date=? AND stats_summary_json IS NOT NULL AND stats_summary_json LIKE '%\"context_flags\"%'",
                (date,),
            )
            db_upset_count = _safe_scalar(
                db,
                "SELECT COUNT(*) FROM analysis_results WHERE betting_date=? AND stats_summary_json IS NOT NULL AND stats_summary_json LIKE '%\"upset_risk\"%'",
                (date,),
            )
            db_gate_counts = _db_gate_counts(db, date)
    except Exception as exc:
        db_error = str(exc)

    expected_count = max(s3_json_count, analysis_db_count)
    json_s4_count = _count_s4_analyses(analyses)
    json_context_count = _count_analyses_with_key(analyses, "context_flags")
    json_upset_count = _count_analyses_with_key(analyses, "upset_risk")

    checks.append(
        Check(
            "A1",
            "S3 deep-stats universe available",
            "PASS" if expected_count > 0 else "FAIL",
            f"DB analysis_results={analysis_db_count} ({analysis_with_market} with best_market), JSON analyses={s3_json_count}",
            gate=True,
            recovery=f"Run: PYTHONPATH=src .venv/bin/python3 scripts/deep_stats_report.py --date {date} --verbose",
        )
    )

    if db_error:
        checks.append(
            Check(
                "A2",
                "DB analysis surface available",
                "WARN",
                f"DB unavailable: {db_error} — using JSON fallback evidence",
                recovery="Restore DB access so DB-first resume can be verified",
            )
        )
    else:
        if s3_json_count and analysis_db_count:
            delta = abs(s3_json_count - analysis_db_count)
            parity_pct = delta / max(s3_json_count, analysis_db_count) * 100
            status = "PASS" if parity_pct <= 20 else "WARN"
            value = f"DB={analysis_db_count}, JSON={s3_json_count} (Δ {parity_pct:.1f}%)"
        elif s3_json_count or analysis_db_count:
            status = "WARN"
            source = "JSON fallback" if s3_json_count else "DB-only"
            value = f"{source} currently carries the S3 universe (DB={analysis_db_count}, JSON={s3_json_count})"
        else:
            status = "SKIP"
            value = "No S3 data available"

        checks.append(
            Check(
                "A2",
                "S3 DB/JSON parity",
                status,
                value,
                recovery="Investigate resume drift before relying on DB-only continuation",
            )
        )

    s4_coverage = max(json_s4_count, db_s4_count)
    checks.append(
        Check(
            "A3",
            "S4 odds / EV enrichment evidence",
            "PASS" if s4_coverage > 0 else "WARN",
            f"JSON={json_s4_count}/{s3_json_count}, DB={db_s4_count}/{analysis_db_count}",
            recovery=f"Run: PYTHONPATH=src .venv/bin/python3 scripts/odds_evaluator.py --date {date} --verbose",
        )
    )

    s5_coverage = max(json_context_count, db_context_count)
    checks.append(
        Check(
            "A4",
            "S5 context enrichment coverage",
            "PASS" if expected_count > 0 and s5_coverage >= expected_count else "WARN" if s5_coverage > 0 else "FAIL",
            f"JSON={json_context_count}/{s3_json_count}, DB={db_context_count}/{analysis_db_count}",
            gate=expected_count > 0 and s5_coverage == 0,
            recovery=f"Run: PYTHONPATH=src .venv/bin/python3 scripts/context_checks.py --date {date} --verbose",
        )
    )

    s6_coverage = max(json_upset_count, db_upset_count)
    checks.append(
        Check(
            "A5",
            "S6 upset-risk coverage",
            "PASS" if expected_count > 0 and s6_coverage >= expected_count else "WARN" if s6_coverage > 0 else "FAIL",
            f"JSON={json_upset_count}/{s3_json_count}, DB={db_upset_count}/{analysis_db_count}",
            gate=expected_count > 0 and s6_coverage == 0,
            recovery=f"Run: PYTHONPATH=src .venv/bin/python3 scripts/upset_risk.py --date {date} --verbose",
        )
    )

    total_gate_results = sum(json_gate_counts.values()) or sum(db_gate_counts.values())
    checks.append(
        Check(
            "A6",
            "S7 gate results available",
            "PASS" if total_gate_results > 0 else "FAIL",
            f"DB {_format_gate_counts(db_gate_counts)} | JSON {_format_gate_counts(json_gate_counts)}",
            gate=True,
            recovery=f"Run: PYTHONPATH=src .venv/bin/python3 scripts/gate_checker.py --date {date} --verbose",
        )
    )

    gate_json_path = _resolve_gate_results_path(date)
    if gate_json_path.exists():
        checks.append(
            Check(
                "A7",
                "S7 gate JSON uses current bucket shape",
                "PASS" if _has_current_gate_shape(gate_json) else "FAIL",
                f"{gate_json_path.name} contains approved / extended_pool / rejected" if _has_current_gate_shape(gate_json) else f"{gate_json_path.name} is missing current gate_results buckets",
                gate=not _has_current_gate_shape(gate_json),
                recovery="Rewrite S7 output in the current nested gate_results shape before S8 resume",
            )
        )
    else:
        checks.append(
            Check(
                "A7",
                "S7 gate JSON uses current bucket shape",
                "WARN" if sum(db_gate_counts.values()) > 0 else "SKIP",
                "No S7 JSON fallback artifact found; DB-only resume evidence in use" if sum(db_gate_counts.values()) > 0 else "No S7 JSON artifact present",
                recovery=f"Regenerate {date}_s7_gate_results.json if JSON fallback is needed",
            )
        )

    if sum(json_gate_counts.values()) > 0 and sum(db_gate_counts.values()) > 0:
        status = "PASS" if json_gate_counts == db_gate_counts else "WARN"
        value = f"DB {_format_gate_counts(db_gate_counts)} | JSON {_format_gate_counts(json_gate_counts)}"
    elif sum(json_gate_counts.values()) > 0 or sum(db_gate_counts.values()) > 0:
        status = "WARN"
        value = f"Single-source gate resume: DB {_format_gate_counts(db_gate_counts)} | JSON {_format_gate_counts(json_gate_counts)}"
    else:
        status = "SKIP"
        value = "No gate outputs to compare"

    checks.append(
        Check(
            "A8",
            "S7 DB/JSON bucket parity",
            status,
            value,
            recovery="Resolve gate resume drift before relying on mixed DB/JSON continuation",
        )
    )

    extended_count = max(json_gate_counts.get("extended_pool", 0), db_gate_counts.get("extended_pool", 0))
    checks.append(
        Check(
            "A9",
            "R3 extended-pool bucket remains visible",
            "PASS" if extended_count > 0 else "WARN",
            f"extended_pool candidates={extended_count}",
            recovery="Confirm gate-failed but still analyzable candidates remain in extended_pool",
        )
    )

    s7_md = DATA_DIR / f"{date}_s7_gate_results.md"
    forbidden_patterns = ["rejected due to", "excluded based on", "filtered to", "only .* picks survived"]
    violations: list[str] = []
    if s7_md.exists():
        content = s7_md.read_text(errors="replace")
        for pattern in forbidden_patterns:
            violations.extend(re.findall(pattern, content, re.IGNORECASE))

    checks.append(
        Check(
            "A10",
            "R3 no auto-rejection language in S7 markdown",
            "PASS" if not violations else "FAIL",
            "Clean" if not violations else f"Found {len(violations)} violations: {violations[:3]}",
            gate=bool(violations),
            recovery="Remove auto-rejection wording and present gate-failed picks in Extended Pool instead",
        )
    )

    return checks


def validate_build_phase(date: str) -> list[Check]:
    checks: list[Check] = []
    config = _load_config()
    bankroll = config.get("bankroll_pln", config.get("working_bankroll_pln", 1000))

    coupon_files = sorted(COUPON_DIR.glob(f"{date}*.md"))
    coupon_json_path = COUPON_DIR / f"{date}.json"
    coupon_json = _load_json(coupon_json_path)
    coupon_controls = {}
    if isinstance(coupon_json, dict):
        controls = coupon_json.get("pre_coupon_controls")
        if isinstance(controls, dict):
            coupon_controls = controls
    betclic_validation_path = DATA_DIR / f"betclic_market_validation_{date}.json"
    betclic_validation = _load_json(betclic_validation_path)
    repeat_artifacts = _find_repeat_handoff_artifacts(date)
    pdf_dir = COUPON_DIR / "pdf" / date
    pdf_files = sorted(pdf_dir.glob("*.pdf")) if pdf_dir.exists() else []

    checks.append(
        Check(
            "B1",
            "S8 coupon markdown exists",
            "PASS" if coupon_files else "FAIL",
            f"{len(coupon_files)} markdown file(s): {[path.name for path in coupon_files]}",
            gate=True,
            recovery=f"Run: PYTHONPATH=src .venv/bin/python3 scripts/coupon_builder.py --date {date} --verbose",
        )
    )

    checks.append(
        Check(
            "B2",
            "S8 coupon JSON exists",
            "PASS" if coupon_json_path.exists() else "FAIL",
            f"Found {coupon_json_path.name}" if coupon_json_path.exists() else f"Missing {coupon_json_path.name}",
            gate=True,
            recovery=f"Re-run coupon_builder.py so both markdown and JSON artifacts exist for {date}",
        )
    )

    sidecar_ok = isinstance(betclic_validation, dict) and any(key in betclic_validation for key in ("validation", "events"))
    betclic_control = coupon_controls.get("betclic_market_validation") if isinstance(coupon_controls.get("betclic_market_validation"), dict) else None
    betclic_consumed = bool(betclic_control and betclic_control.get("consumed"))
    # Safely compute counts even if JSON fields are null
    validation_count = len(((betclic_validation or {}).get("validation")) or [])
    events_count = len(((betclic_validation or {}).get("events")) or [])
    consumed_mode = betclic_control.get("mode", "unknown") if isinstance(betclic_control, dict) else "unknown"
    checks.append(
        Check(
            "B3",
            "S7.5 Betclic validation sidecar present and consumed",
            "PASS" if sidecar_ok and betclic_consumed else "FAIL",
            (
                f"validation={validation_count}, events={events_count}, consumed via {consumed_mode}"
                if sidecar_ok and betclic_consumed
                else "Sidecar present but coupon_builder output does not record S7.5 consumption"
                if sidecar_ok
                else f"Missing or malformed {betclic_validation_path.name}"
            ),
            gate=True,
            recovery=f"Run: PYTHONPATH=src .venv/bin/python3 scripts/validate_betclic_markets.py --date {date}",
        )
    )

    if coupon_files:
        try:
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "validate_coupons.py"), *[str(path) for path in coupon_files], "--format", "json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            total_failed, summary = _parse_validate_coupons_output(result.stdout, result.returncode)
            checks.append(
                Check(
                    "B4",
                    "S9 coupon structural validation",
                    "PASS" if total_failed == 0 and result.returncode == 0 else "FAIL",
                    summary,
                    gate=total_failed > 0 or result.returncode != 0,
                    recovery="Fix coupon markdown structure/arithmetic, then rerun validate_coupons.py on today's files",
                )
            )
        except Exception as exc:
            checks.append(
                Check(
                    "B4",
                    "S9 coupon structural validation",
                    "FAIL",
                    f"Could not run validate_coupons.py: {exc}",
                    gate=True,
                    recovery="Restore validate_coupons.py execution before marking the build phase ready",
                )
            )
    else:
        checks.append(Check("B4", "S9 coupon structural validation", "SKIP", "No coupon markdown files to validate"))

    db_coupons = 0
    db_bets = 0
    total_stake = 0
    try:
        with _get_db() as db:
            db_coupons = _safe_scalar(
                db,
                "SELECT COUNT(*) FROM coupons WHERE created_at >= ? AND created_at < ?",
                (f"{date}T00:00:00", f"{date}T23:59:59"),
            )
            db_bets = _safe_scalar(
                db,
                "SELECT COUNT(*) FROM bets b JOIN coupons c ON b.coupon_id=c.id WHERE c.created_at >= ? AND c.created_at < ?",
                (f"{date}T00:00:00", f"{date}T23:59:59"),
            )
            total_stake = _safe_scalar(
                db,
                "SELECT COALESCE(SUM(stake_pln), 0) FROM coupons WHERE status='pending' AND created_at >= ?",
                (f"{date}T00:00:00",),
                default=0.0,
            )
    except Exception:
        pass

    checks.append(
        Check(
            "B5",
            "DB coupon persistence available",
            "PASS" if db_coupons > 0 else "WARN",
            f"DB coupons={db_coupons}, bets={db_bets}",
            recovery="Check coupon_builder DB persistence if you expect a DB-first resume later today",
        )
    )

    max_exposure = bankroll * 0.25
    checks.append(
        Check(
            "B6",
            f"Total exposure ≤ 25% bankroll ({max_exposure:.0f} PLN)",
            "PASS" if total_stake <= max_exposure else "FAIL",
            f"{float(total_stake):.2f} PLN / {max_exposure:.0f} PLN limit",
            gate=float(total_stake) > max_exposure,
            recovery="Reduce stake sizes in coupon_builder output before placing bets",
        )
    )

    disclaimer_found = False
    for coupon_file in coupon_files:
        content = coupon_file.read_text(errors="replace")
        if "warunkow" in content.lower() or "conditional" in content.lower() or "betclic" in content.lower():
            disclaimer_found = True
            break

    checks.append(
        Check(
            "B7",
            "R12 conditional disclaimer present",
            "PASS" if disclaimer_found or not coupon_files else "WARN",
            "Found disclaimer in coupon artifacts" if disclaimer_found else "Disclaimer not found in coupon markdown",
            recovery="Add the standard conditional Betclic disclaimer to today's coupon markdown",
        )
    )

    repeat_step = _load_pipeline_step_record(date, "s7_6_repeat_loss_check")
    repeat_control = coupon_controls.get("repeat_loss_handoff") if isinstance(coupon_controls.get("repeat_loss_handoff"), dict) else None
    if repeat_step is None:
        repeat_status = "FAIL"
        repeat_value = "Missing mandatory S7.6 DB handoff in pipeline_runs"
    elif repeat_step["stats"] == "__MALFORMED_JSON__":
        repeat_status = "FAIL"
        repeat_value = "Malformed S7.6 DB handoff: pipeline_runs.stats is not valid JSON"
    elif repeat_step.get("status") != "completed":
        repeat_status = "FAIL"
        repeat_value = f"S7.6 DB handoff not completed (status={repeat_step.get('status')})"
    elif not isinstance(repeat_step.get("stats"), dict):
        repeat_status = "FAIL"
        repeat_value = "Malformed S7.6 DB handoff: stats payload missing"
    elif not isinstance(repeat_step["stats"].get("findings"), list):
        repeat_status = "FAIL"
        repeat_value = "Malformed S7.6 DB handoff: findings must be a list"
    elif repeat_control and repeat_control.get("consumed"):
        artifact_note = f", artifacts={ [path.name for path in repeat_artifacts] }" if repeat_artifacts else ""
        repeat_status = "PASS"
        repeat_value = (
            f"repeat_loss_count={repeat_step['stats'].get('repeat_loss_count', 0)}, "
            f"excluded={repeat_control.get('excluded_count', 0)}{artifact_note}"
        )
    else:
        repeat_status = "FAIL"
        repeat_value = "S7.6 DB handoff exists but coupon_builder output does not record consumption"

    checks.append(
        Check(
            "B8",
            "S7.6 repeat-loss handoff present and consumed",
            repeat_status,
            repeat_value,
            gate=True,
            recovery=f"Run: PYTHONPATH=src .venv/bin/python3 scripts/check_48h_repeats.py --date {date} --format json",
        )
    )

    checks.append(
        Check(
            "B9",
            "S10 PDF output (warning-only policy)",
            "PASS" if pdf_files else "WARN",
            f"{len(pdf_files)} PDF file(s) under {pdf_dir.relative_to(COUPON_DIR.parent)}",
            recovery=f"Optional: PYTHONPATH=src .venv/bin/python3 scripts/generate_coupon_pdf.py --date {date}",
        )
    )

    return checks


def run_validation(date: str, phase: str, fmt: str = "text") -> int:
    all_checks: list[Check] = []

    if phase in ("data", "all"):
        all_checks.extend(validate_data_phase(date))
    if phase in ("analysis", "all"):
        all_checks.extend(validate_analysis_phase(date))
    if phase in ("build", "all"):
        all_checks.extend(validate_build_phase(date))

    gate_fails = [check for check in all_checks if check.status == "FAIL" and check.gate]
    s0_gate_fails = [check for check in gate_fails if check.check_id.startswith("S0")]
    execution_gate_fails = [check for check in gate_fails if not check.check_id.startswith("S0")]
    non_gate_fails = [check for check in all_checks if check.status == "FAIL" and not check.gate]
    warns = [check for check in all_checks if check.status == "WARN"]
    passes = [check for check in all_checks if check.status == "PASS"]

    if fmt == "json":
        print(
            json.dumps(
                {
                    "date": date,
                    "phase": phase,
                    "total_checks": len(all_checks),
                    "passed": len(passes),
                    "warnings": len(warns),
                    "gate_failures": len(gate_fails),
                    "s0_prerequisite_failures": len(s0_gate_fails),
                    "execution_gate_failures": len(execution_gate_fails),
                    "non_gate_failures": len(non_gate_fails),
                    "blocking": bool(gate_fails),
                    "checks": [check.to_dict() for check in all_checks],
                },
                indent=2,
            )
        )
    else:
        phase_label = phase.upper() if phase != "all" else "ALL PHASES"
        print(f"\n{'=' * 70}")
        print(f"  PHASE VALIDATION: {phase_label} — {date}")
        print(f"{'=' * 70}")
        for check in all_checks:
            print(str(check))
        print(f"\n{'─' * 70}")
        print(f"  SUMMARY: {len(passes)} PASS | {len(warns)} WARN | {len(gate_fails)} GATE FAIL | {len(non_gate_fails)} non-gate FAIL")

        if gate_fails:
            if s0_gate_fails:
                print(
                    f"\n  🚫 S0 PREREQUISITES BLOCKING — {len(s0_gate_fails)} issue(s) must be fixed before a new session proceeds:"
                )
                for check in s0_gate_fails:
                    print(f"     • {check.check_id}: {check.name}")
                    if check.recovery:
                        print(f"       ↳ {check.recovery}")
            if execution_gate_fails:
                print(
                    f"\n  🚫 S1-S10 EXECUTION GATES BLOCKING — {len(execution_gate_fails)} later-phase issue(s) remain:"
                )
                for check in execution_gate_fails:
                    print(f"     • {check.check_id}: {check.name}")
                    if check.recovery:
                        print(f"       ↳ {check.recovery}")
            print()
        elif warns:
            print(f"\n  ⚠️  NON-BLOCKING — {len(warns)} warning(s), proceed with caution")
        else:
            print("\n  ✅ ALL GATES PASS — safe to proceed")

        print(f"{'=' * 70}\n")

    if gate_fails:
        return 1
    if warns or non_gate_fails:
        return 2
    return 0


def main():
    parser = argparse.ArgumentParser(description="DB-first session readiness validation")
    parser.add_argument("--date", required=True, help="Betting date (YYYY-MM-DD)")
    parser.add_argument("--phase", required=True, choices=["data", "analysis", "build", "all"], help="Which phase to validate")
    parser.add_argument("--format", default="text", choices=["text", "json"], help="Output format")
    args = parser.parse_args()

    sys.exit(run_validation(args.date, args.phase, args.format))


if __name__ == "__main__":
    main()
