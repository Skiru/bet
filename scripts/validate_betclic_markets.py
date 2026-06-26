#!/usr/bin/env python3
"""Betclic market availability scanner and coupon validator."""
import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from bet.pipeline.core_integration_contracts import get_contract, require_live_integrations
from bet.pipeline.integration_artifacts import build_market_availability_artifact, write_script_evidence
from bet.scrapers.betclic import BetclicMarketChecker

logger = logging.getLogger(__name__)


def _data_dir() -> Path:
    return Path(os.environ.get("BET_PIPELINE_DATA_DIR", str(ROOT_DIR / "betting" / "data")))


def is_non_production_mode() -> bool:
    return os.environ.get("BET_PIPELINE_RUNTIME_MODE", "DRY_RUN").upper() != "PRODUCTION"


def is_protected_repo_path(path: Path | str | None) -> bool:
    if not path:
        return False
    abs_path = Path(path).resolve()
    for parent in ((ROOT_DIR / "betting" / "data").resolve(), (ROOT_DIR / "betting" / "coupons").resolve(), (ROOT_DIR / "reports").resolve()):
        try:
            abs_path.relative_to(parent)
            return True
        except ValueError:
            pass
    return False


def _block_and_exit(reason: str, input_path: str | None, output_path: Path) -> None:
    print(reason)
    write_script_evidence(
        "S7b",
        status="BLOCK",
        payload={
            "s7b_input_path": input_path,
            "s7b_json_output": str(output_path),
            "checked_market_count": 0,
            "available_market_count": 0,
            "unavailable_market_count": 0,
            "validation_status": "BLOCK",
            "runtime_mode": os.environ.get("BET_PIPELINE_RUNTIME_MODE"),
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "no_pick_edge_stake_coupon_emitted": True,
        },
        sources=("Betclic",),
        evidence_refs=(),
        no_pick_edge_stake_coupon_emitted=True,
        production_selectable=False,
        betting_decisions_enabled=False,
        blocked_reasons=(reason.split(":", 1)[0],),
    )
    raise SystemExit(5 if "_MISSING" in reason or "_PROTECTED_" in reason else 2)


def parse_coupon_picks(coupon_path: Path) -> list[dict]:
    if not coupon_path.exists():
        return []

    text = coupon_path.read_text(encoding="utf-8")
    picks = []
    for line in text.split("\n"):
        if not line.startswith("|") or line.startswith("|---") or line.startswith("| #"):
            continue
        cols = [c.strip() for c in line.split("|")]
        if len(cols) < 9:
            continue
        try:
            idx = cols[1]
            if not idx.isdigit():
                continue
            sport_emoji = cols[2]
            event = cols[3]
            market = cols[4]
            direction = cols[8] if len(cols) > 8 else ""
            sport_map = {"⚽": "football", "🎾": "tennis", "🏀": "basketball", "🏐": "volleyball", "🏒": "hockey"}
            picks.append(
                {
                    "idx": int(idx),
                    "sport": sport_map.get(sport_emoji.strip(), "unknown"),
                    "event": event,
                    "market": market,
                    "market_type": _detect_market_type(market, sport_map.get(sport_emoji.strip(), "unknown")),
                    "direction": direction,
                }
            )
        except (ValueError, IndexError):
            continue
    return picks


def _detect_market_type(market_name: str, sport: str) -> str:
    m = market_name.lower()
    if "corner" in m or "rożn" in m:
        return "corners_total"
    if "card" in m or "kartk" in m:
        return "cards_total"
    if "shot" in m and "target" in m:
        return "shots_on_target"
    if "shot" in m:
        return "shots_total"
    if "foul" in m or "faul" in m:
        return "fouls"
    if "goals total" in m or "gole" in m:
        return "goals_total"
    if "btts" in m or "oba" in m:
        return "btts"
    if "game" in m or "gem" in m:
        return "games_total"
    if "set" in m:
        return "sets_total"
    if "double fault" in m or "podwójn" in m:
        return "double_faults"
    if "ace" in m:
        return "aces"
    if "point" in m or "punkt" in m:
        return "points_total"
    if "handicap" in m:
        return "handicap"
    if "winner" in m or "wynik" in m:
        return "match_winner"
    return "unknown"


def _extract_s7_approved_entries(payload: dict | list) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise ValueError("unsupported payload type")

    if payload.get("artifact_type") == "SCRIPT_EVIDENCE":
        script_payload = payload.get("payload") or {}
        for key in ("s7_json_output", "json_output"):
            nested = script_payload.get(key)
            if nested:
                nested_path = Path(nested)
                if is_non_production_mode() and is_protected_repo_path(nested_path):
                    raise ValueError("protected nested S7 output path")
                if nested_path.exists():
                    return _extract_s7_approved_entries(json.loads(nested_path.read_text(encoding="utf-8")))

    gate_results = payload.get("gate_results")
    if isinstance(gate_results, dict):
        approved = gate_results.get("approved")
        if isinstance(approved, list):
            return [item for item in approved if isinstance(item, dict)]

    approved = payload.get("approved")
    if isinstance(approved, list):
        return [item for item in approved if isinstance(item, dict)]

    return []


def _gate_pick_to_validation_pick(entry: dict) -> dict:
    best_market = entry.get("best_market") or {}
    return {
        "idx": entry.get("fixture_id") or entry.get("id") or 0,
        "sport": entry.get("sport", "unknown"),
        "event": entry.get("event") or f"{entry.get('home_team', '')} vs {entry.get('away_team', '')}".strip(),
        "home_team": entry.get("home_team", ""),
        "away_team": entry.get("away_team", ""),
        "market": best_market.get("name") or entry.get("market") or entry.get("market_type") or "",
        "market_type": best_market.get("market_type") or entry.get("market_type") or "unknown",
        "direction": best_market.get("direction") or entry.get("direction") or "",
    }


def main():
    parser = argparse.ArgumentParser(description="Betclic market availability scanner & coupon validator")
    parser.add_argument("--date", required=True, help="Betting date (YYYY-MM-DD)")
    parser.add_argument("--sports", nargs="+", default=None, help="Sports to scan (default: all)")
    parser.add_argument("--max-events", type=int, default=0, help="Max events per sport to check (0 = all, default: 0)")
    parser.add_argument("--validate-coupon", default=None, help="Path to coupon markdown to validate")
    parser.add_argument("--input", default=None, help="Path to explicit S7 approved-picks JSON")
    parser.add_argument("--output", default=None, help="Output JSON path")
    parser.add_argument("--no-db", action="store_true", help="Skip DB persistence")
    parser.add_argument("--allow-live-network", action="store_true", help="Allow live Betclic scan in LIVE_SHADOW")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    runtime_mode = os.environ.get("BET_PIPELINE_RUNTIME_MODE", "UNMANAGED")
    output_path = Path(args.output) if args.output else _data_dir() / f"betclic_market_validation_{args.date}.json"
    if is_non_production_mode() and (is_protected_repo_path(args.input) or is_protected_repo_path(output_path)):
        _block_and_exit(
            "BLOCKED_S7B_INPUT_PROTECTED_PATH: explicit S7b input/output path is under a protected repo-local path.",
            args.input,
            output_path,
        )

    picks: list[dict] = []
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            _block_and_exit(f"BLOCKED_S7B_INPUT_MISSING: explicit S7b input not found: {input_path}", args.input, output_path)
        try:
            approved_entries = _extract_s7_approved_entries(json.loads(input_path.read_text(encoding="utf-8")))
        except Exception as exc:
            _block_and_exit(f"BLOCKED_MARKET_AVAILABILITY_MISSING: unsupported S7b input payload: {exc}", args.input, output_path)
        picks = [_gate_pick_to_validation_pick(entry) for entry in approved_entries]
        if not picks:
            _block_and_exit("BLOCKED_MARKET_AVAILABILITY_MISSING: no approved S7 picks available for market validation.", args.input, output_path)

    can_use_live_scan = bool(args.allow_live_network and runtime_mode.upper() == "LIVE_SHADOW")
    if can_use_live_scan:
        require_live_integrations("S7b")

    betclic_contract = get_contract("S7b", "Betclic")

    db_conn = None
    if not args.no_db and not is_non_production_mode():
        try:
            import sqlite3 as _sqlite3
            from bet.db.connection import DEFAULT_DB_PATH, _configure_connection

            db_conn = _sqlite3.connect(str(DEFAULT_DB_PATH))
            _configure_connection(db_conn)
        except Exception as exc:
            logger.warning(f"Could not connect to DB: {exc}")

    print(f"\n{'=' * 60}")
    print(f"  BETCLIC MARKET VALIDATION — {args.date}")
    print(f"{'=' * 60}")

    with BetclicMarketChecker(betting_date=args.date, db_conn=db_conn) as checker:
        if can_use_live_scan:
            print("\n--- Phase 1: Scanning Betclic markets ---")
            checker.scan_all_sports(sports=args.sports, max_events_per_sport=args.max_events)
            if db_conn:
                checker.save_to_db()
        else:
            print("\n--- Phase 1: Betclic live scan skipped (manual verification required) ---")

        summary = checker.build_summary()
        print(f"  Events checked: {summary['total_events']}")
        print(f"  With Statystyki: {summary['with_statistics_tab']}")
        print(f"  Without Statystyki: {summary['without_statistics_tab']}")

        validation_results = None
        if picks:
            print("\n--- Phase 2: Validating approved S7 picks ---")
            print(f"  Loaded {len(picks)} approved picks from S7 input")
            if can_use_live_scan:
                validation_results = checker.validate_picks(picks)
            else:
                validation_results = [
                    {
                        **pick,
                        "betclic_available": None,
                        "betclic_note": "Manual verification required in LIVE_SHADOW with allow-live-network.",
                        "betclic_open_markets": 0,
                    }
                    for pick in picks
                ]
        elif args.validate_coupon:
            print("\n--- Phase 2: Validating coupon picks ---")
            coupon_path = Path(args.validate_coupon)
            coupon_picks = parse_coupon_picks(coupon_path)
            print(f"  Parsed {len(coupon_picks)} picks from coupon")
            if coupon_picks:
                validation_results = checker.validate_picks(coupon_picks)

        available = [item for item in (validation_results or []) if item.get("betclic_available") is True]
        unavailable = [item for item in (validation_results or []) if item.get("betclic_available") is False]
        unknown = [item for item in (validation_results or []) if item.get("betclic_available") is None]

        if validation_results is not None:
            print(f"\n  ✅ Available: {len(available)} picks")
            print(f"  ❌ Unavailable: {len(unavailable)} picks")
            print(f"  ⚠️  Unknown: {len(unknown)} picks")

        print("\n--- Competition market profiles ---")
        if summary["competitions_with_stats"]:
            print("  ✅ WITH statistical markets:")
            for competition in sorted(summary["competitions_with_stats"]):
                print(f"     • {competition}")
        if summary["competitions_without_stats"]:
            print("  ❌ WITHOUT statistical markets:")
            for competition in sorted(summary["competitions_without_stats"]):
                print(f"     • {competition}")

        scanned_at = datetime.now(timezone.utc).isoformat()
        output_data = build_market_availability_artifact(
            date=args.date,
            scanned_at=scanned_at,
            summary=summary,
            validation=validation_results,
            events=[result.to_dict() for result in checker.results],
            runtime_mode=runtime_mode,
            timeout_seconds=betclic_contract.timeout_seconds,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  Output: {output_path}")

        checked_market_count = len(validation_results or [])
        available_market_count = len(available)
        unavailable_market_count = len(unavailable) + len(unknown)
        validation_status = "PASS" if checked_market_count > 0 and unavailable_market_count == 0 and can_use_live_scan else "BLOCK"

        evidence_path = write_script_evidence(
            "S7b",
            status=validation_status,
            payload={
                "artifact_kind": "market_availability",
                "s7b_input_path": args.input,
                "s7b_json_output": str(output_path),
                "checked_market_count": checked_market_count,
                "available_market_count": available_market_count,
                "unavailable_market_count": unavailable_market_count,
                "validation_status": validation_status,
                "runtime_mode": runtime_mode,
                "production_selectable": False,
                "betting_decisions_enabled": False,
                "no_pick_edge_stake_coupon_emitted": True,
            },
            sources=("Betclic",),
            evidence_refs=(output_path.name,),
            no_pick_edge_stake_coupon_emitted=True,
            production_selectable=False,
            betting_decisions_enabled=False,
            blocked_reasons=("BLOCKED_MARKET_AVAILABILITY_UNAVAILABLE",) if validation_status != "PASS" else (),
        )
        if evidence_path:
            print(f"  Script evidence: {evidence_path}")

    if db_conn:
        db_conn.commit()
        db_conn.close()

    checked_market_count = len(validation_results or [])
    available_market_count = len(available)
    unavailable_market_count = len(unavailable) + len(unknown)
    verdict = "OK" if checked_market_count > 0 and unavailable_market_count == 0 and can_use_live_scan else "FAILED"
    print(
        f'\nAGENT_SUMMARY:{{"verdict":"{verdict}",' 
        f'"total_events":{summary["total_events"]},' 
        f'"checked_market_count":{checked_market_count},' 
        f'"available_market_count":{available_market_count},' 
        f'"unavailable_market_count":{unavailable_market_count},' 
        f'"output":"{output_path}"}}'
    )
    if verdict != "OK":
        print("BLOCKED_MARKET_AVAILABILITY_UNAVAILABLE: market availability is missing, unavailable, or still requires manual verification.")
    sys.exit(0 if verdict == "OK" else 2)


if __name__ == "__main__":
    main()
