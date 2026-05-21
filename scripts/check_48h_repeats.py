#!/usr/bin/env python3
"""48-hour repeat pick detector — finds same team+market losses in recent history.

Reads picks-ledger.csv and identifies picks in the last 48 hours with the same
team+market combination that resulted in a loss. These are flagged for the S7 gate
(§7.5 point #14: "48h repeat check — same team+market lost → HARD REJECT").
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "betting" / "data"
DEFAULT_LEDGER_PATH = ROOT_DIR / "betting" / "journal" / "picks-ledger.csv"
REPEAT_LOSS_STEP = "s7_6_repeat_loss_check"

# Ensure src/ is importable when the script is executed directly.
sys.path.insert(0, str(ROOT_DIR / "src"))


def normalize_team(name: str) -> str:
    """Normalize team name for fuzzy matching."""
    name = name.lower().strip()
    name = re.sub(r"\s+", " ", name)
    # Remove common suffixes/prefixes
    for token in ["fc ", "sc ", "ac ", "ss ", "bv ", "ud ", "sv ", "tsv ", "vfb "]:
        if name.startswith(token):
            name = name[len(token):]
    for token in [" fc", " sc", " ac", " cf"]:
        if name.endswith(token):
            name = name[: -len(token)]
    return name.strip()


def normalize_market(market: str) -> str:
    """Normalize market type for matching."""
    market = market.lower().strip()
    market = re.sub(r"\s+", " ", market)
    # Normalize common variants
    market = market.replace("over ", "o").replace("under ", "u")
    market = market.replace("o/u ", "").replace("over/under ", "")
    return market


def fuzzy_match(a: str, b: str, threshold: float = 0.75) -> bool:
    """Check if two strings match above a similarity threshold."""
    return SequenceMatcher(None, a, b).ratio() >= threshold


def load_recent_losses(
    ledger_path: Path, hours: int = 48
) -> list[dict]:
    """Read picks-ledger.csv and filter to status=loss within last N hours."""
    if not ledger_path.exists():
        return []

    cutoff = datetime.now() - timedelta(hours=hours)
    losses = []

    with open(ledger_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status", "").strip().lower() != "loss":
                continue

            # Parse betting_day
            betting_day = row.get("betting_day", "").strip()
            if not betting_day:
                continue
            try:
                # Treat betting_day as end-of-day to ensure full 48h calendar coverage
                day_dt = datetime.strptime(betting_day, "%Y-%m-%d") + timedelta(hours=23, minutes=59)
            except ValueError:
                continue

            if day_dt < cutoff:
                continue

            # Extract team names from event field
            event = row.get("event", "").strip()
            teams = extract_teams(event)

            losses.append({
                "betting_day": betting_day,
                "pick_id": row.get("pick_id", "").strip(),
                "event": event,
                "sport": row.get("sport", "").strip(),
                "market": row.get("market", "").strip(),
                "selection": row.get("selection", "").strip(),
                "teams": teams,
                "teams_normalized": [normalize_team(t) for t in teams],
                "market_normalized": normalize_market(row.get("market", "")),
                "days_ago": (datetime.now() - day_dt).days,
            })

    return losses


def extract_teams(event: str) -> list[str]:
    """Extract team/player names from event string."""
    # Try "Team A vs Team B" pattern
    match = re.match(r"(.+?)\s+(?:vs\.?|@)\s+(.+?)(?:\s*\(|$)", event, re.IGNORECASE)
    if match:
        return [match.group(1).strip(), match.group(2).strip()]
    # Fallback: split by common separators
    for sep in [" vs ", " vs. ", " @ ", " - "]:
        if sep in event.lower():
            idx = event.lower().index(sep)
            return [event[:idx].strip(), event[idx + len(sep):].strip()]
    return [event]


def find_repeats(
    check_teams: list[str],
    recent_losses: list[dict],
    check_market: str | None = None,
) -> list[dict]:
    """Find matching team+market combinations in recent losses."""
    warnings = []
    check_teams_norm = [normalize_team(t) for t in check_teams]
    check_market_norm = normalize_market(check_market) if check_market else None

    for loss in recent_losses:
        for check_team in check_teams_norm:
            for loss_team in loss["teams_normalized"]:
                if fuzzy_match(check_team, loss_team):
                    # Team matches — check market if provided
                    if check_market_norm:
                        if not fuzzy_match(check_market_norm, loss["market_normalized"], 0.6):
                            continue

                    warnings.append({
                        "team": check_team,
                        "matched_team": loss_team,
                        "market": loss["market"],
                        "selection": loss["selection"],
                        "lost_on": loss["betting_day"],
                        "pick_id": loss["pick_id"],
                        "event": loss["event"],
                        "sport": loss["sport"],
                        "days_ago": loss["days_ago"],
                        "action": "HARD REJECT per §7.5 #14",
                    })

    return warnings


def parse_shortlist_teams(shortlist_path: Path) -> list[str]:
    """Extract team names from shortlist markdown file."""
    if not shortlist_path.exists():
        return []

    text = shortlist_path.read_text(encoding="utf-8")
    teams = set()

    # Look for "X vs Y" patterns
    for match in re.finditer(
        r"([A-ZÀ-Ža-zà-ž0-9\s.'&\-]+?)\s+vs\.?\s+([A-ZÀ-Ža-zà-ž0-9\s.'&\-]+?)(?:\s*[\|(]|$)",
        text,
        re.MULTILINE,
    ):
        teams.add(match.group(1).strip())
        teams.add(match.group(2).strip())

    return list(teams)


def _candidate_market_name(candidate: dict) -> str:
    best_market = candidate.get("best_market") or {}
    return (
        best_market.get("name")
        or candidate.get("market_type")
        or candidate.get("market")
        or ""
    )


def _extract_gate_candidates(payload: dict | list) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        raise ValueError("Gate input payload must be a dict or list")

    gate_results = payload.get("gate_results")
    if isinstance(gate_results, dict):
        approved = gate_results.get("approved", []) or []
        extended = gate_results.get("extended_pool", []) or []
        return [item for item in approved + extended if isinstance(item, dict)]

    legacy_results = payload.get("results")
    if isinstance(legacy_results, list):
        return [item for item in legacy_results if isinstance(item, dict)]

    raise ValueError("Gate input payload missing gate_results buckets")


def load_gate_candidates(date: str, input_path: Path | None = None) -> tuple[list[dict], str]:
    """Load the S7 build universe for repeat-loss checks.

    Returns a tuple of (candidates, source), where source is one of
    ``input_json``, ``db``, or ``json``.
    """
    if input_path is not None:
        if not input_path.exists():
            raise FileNotFoundError(f"Gate input not found: {input_path}")
        with open(input_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        return _extract_gate_candidates(payload), "input_json"

    from db_data_loader import load_gate_results_from_db_only

    approved_db = load_gate_results_from_db_only(date, status="approved")
    extended_db = load_gate_results_from_db_only(date, status="extended")
    if approved_db or extended_db:
        return approved_db + extended_db, "db"

    for json_path in (DATA_DIR / f"{date}_s7_gate_results.json", DATA_DIR / f"s7_gate_results_{date}.json"):
        if not json_path.exists():
            continue
        with open(json_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        return _extract_gate_candidates(payload), "json"

    raise FileNotFoundError(f"No S7 gate results found for {date}. Run gate_checker.py first.")


def find_repeat_loss_candidates(candidates: list[dict], recent_losses: list[dict]) -> list[dict]:
    """Return same team+market repeat-loss findings for the given candidates."""
    findings: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for candidate in candidates:
        market_name = _candidate_market_name(candidate)
        home_team = candidate.get("home_team", "")
        away_team = candidate.get("away_team", "")
        teams = [team for team in (home_team, away_team) if team]
        if not teams or not market_name:
            continue

        matches = find_repeats(teams, recent_losses, market_name)
        for match in matches:
            event_key = f"{normalize_team(home_team)}|{normalize_team(away_team)}"
            match_key = (event_key, normalize_market(market_name), match.get("pick_id", ""))
            if match_key in seen:
                continue
            seen.add(match_key)
            findings.append(
                {
                    "fixture_id": candidate.get("fixture_id"),
                    "sport": candidate.get("sport", ""),
                    "home_team": home_team,
                    "away_team": away_team,
                    "competition": candidate.get("competition", ""),
                    "market_name": market_name,
                    "market_normalized": normalize_market(market_name),
                    "event_key": event_key,
                    "reason": "Same team+market lost within 48h — HARD REJECT",
                    "matched_loss": match,
                    "action": "HARD_REJECT",
                }
            )

    return findings


def build_repeat_loss_payload(
    *,
    date: str,
    hours: int,
    recent_losses: list[dict],
    candidates: list[dict],
    findings: list[dict],
    candidate_source: str,
    artifact_path: Path,
) -> dict:
    return {
        "date": date,
        "step": REPEAT_LOSS_STEP,
        "window_hours": hours,
        "candidate_source": candidate_source,
        "artifact_path": str(artifact_path),
        "checked_candidates_count": len(candidates),
        "recent_losses_count": len(recent_losses),
        "repeat_loss_count": len(findings),
        "clear": len(findings) == 0,
        "findings": findings,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


def _persist_pipeline_handoff(date: str, payload: dict) -> None:
    from bet.db.connection import get_db
    from bet.db.repositories import PipelineRepo

    with get_db() as conn:
        repo = PipelineRepo(conn)
        repo.complete_step(date, REPEAT_LOSS_STEP, stats=payload)
        conn.commit()


def _record_pipeline_start(date: str) -> None:
    from bet.db.connection import get_db
    from bet.db.repositories import PipelineRepo

    with get_db() as conn:
        repo = PipelineRepo(conn)
        repo.start_step(date, REPEAT_LOSS_STEP)
        conn.commit()


def _record_pipeline_failure(date: str, error: str) -> None:
    from bet.db.connection import get_db
    from bet.db.repositories import PipelineRepo

    with get_db() as conn:
        repo = PipelineRepo(conn)
        repo.fail_step(date, REPEAT_LOSS_STEP, error)
        conn.commit()


def load_repeat_loss_handoff(date: str) -> dict | None:
    """Load the canonical S7.6 handoff from pipeline_runs.

    Returns ``None`` when the step has not completed for the date.
    Raises ``ValueError`` when a completed record exists but is malformed.
    """
    from bet.db.connection import get_db
    from bet.db.repositories import PipelineRepo

    with get_db() as conn:
        record = PipelineRepo(conn).get_step(date, REPEAT_LOSS_STEP)

    if record is None:
        return None

    if record.get("status") != "completed":
        raise ValueError(
            f"S7.6 handoff for {date} is not complete (status={record.get('status')})"
        )

    payload = record.get("stats")
    if not isinstance(payload, dict):
        raise ValueError(f"Malformed S7.6 handoff for {date}: stats payload missing")
    if payload.get("date") != date:
        raise ValueError(f"Malformed S7.6 handoff for {date}: unexpected payload date")
    findings = payload.get("findings")
    if not isinstance(findings, list):
        raise ValueError(f"Malformed S7.6 handoff for {date}: findings must be a list")
    if not isinstance(payload.get("repeat_loss_count"), int):
        raise ValueError(f"Malformed S7.6 handoff for {date}: repeat_loss_count must be an int")
    if payload.get("repeat_loss_count") != len(findings):
        raise ValueError(f"Malformed S7.6 handoff for {date}: repeat_loss_count does not match findings")
    return payload


def main():
    from agent_output import AgentOutput, add_agent_args

    parser = argparse.ArgumentParser(
        description="Detect 48-hour repeat team+market losses in picks-ledger."
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Betting day YYYY-MM-DD. In pipeline mode, loads today's S7 gate universe and persists a durable handoff.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Optional S7 gate results JSON override for pipeline mode.",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=DEFAULT_LEDGER_PATH,
        help="Path to picks-ledger.csv",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=48,
        help="Lookback window in hours (default: 48)",
    )
    parser.add_argument(
        "--teams",
        type=str,
        default=None,
        help="Comma-separated team names to check (e.g., 'Liverpool,Arsenal')",
    )
    parser.add_argument(
        "--shortlist",
        type=Path,
        default=None,
        help="Path to shortlist markdown file to extract team names",
    )
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional artifact path for pipeline mode. Default: betting/data/repeat_loss_handoff_{date}.json",
    )
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput("s7_6_repeats", verbose=args.verbose, stop_on_error=args.stop_on_error)

    pipeline_mode = bool(args.date or args.input)
    if args.input and not args.date:
        parser.error("--input requires --date so the durable handoff can be persisted")

    if pipeline_mode and args.date:
        _record_pipeline_start(args.date)

    try:
        recent_losses = load_recent_losses(args.ledger, args.hours)

        if pipeline_mode:
            candidates, candidate_source = load_gate_candidates(args.date, args.input)
            findings = find_repeat_loss_candidates(candidates, recent_losses)
            artifact_path = args.output or (DATA_DIR / f"repeat_loss_handoff_{args.date}.json")
            artifact_path.parent.mkdir(parents=True, exist_ok=True)

            payload = build_repeat_loss_payload(
                date=args.date,
                hours=args.hours,
                recent_losses=recent_losses,
                candidates=candidates,
                findings=findings,
                candidate_source=candidate_source,
                artifact_path=artifact_path,
            )
            artifact_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            _persist_pipeline_handoff(args.date, payload)

            if args.verbose:
                out.event(
                    "repeat_loss_handoff",
                    date=args.date,
                    candidate_source=candidate_source,
                    checked_candidates=payload["checked_candidates_count"],
                    recent_losses=payload["recent_losses_count"],
                    repeat_loss_count=payload["repeat_loss_count"],
                    artifact=artifact_path.name,
                )

            if args.format == "text":
                print("═══ 48h Repeat Check (pipeline mode) ═══")
                print(
                    f"Candidates checked: {payload['checked_candidates_count']} | "
                    f"Recent losses: {payload['recent_losses_count']}"
                )
                if findings:
                    print(f"\n⚠️  REPEAT LOSSES FOUND: {len(findings)}")
                    for finding in findings:
                        match = finding["matched_loss"]
                        print(
                            f"  ✗ {finding['home_team']} vs {finding['away_team']} × "
                            f"{finding['market_name']} — lost {match['lost_on']} ({match['pick_id']})"
                        )
                else:
                    print("\n✓ No repeat-loss exclusions found. Clear to proceed.")
            else:
                print(json.dumps(payload, indent=2, ensure_ascii=False))

            out.summary(
                verdict="PARTIAL" if findings else "OK",
                metrics={
                    "date": args.date,
                    "candidate_source": candidate_source,
                    "checked_candidates": payload["checked_candidates_count"],
                    "recent_losses": payload["recent_losses_count"],
                    "repeat_loss_count": payload["repeat_loss_count"],
                    "artifact": artifact_path.name,
                },
            )
            sys.exit(1 if findings else 0)

        result = {
            "window_hours": args.hours,
            "recent_losses_count": len(recent_losses),
            "repeats_found": 0,
            "warnings": [],
        }

        if not recent_losses:
            if args.format == "text":
                print(f"No losses found in last {args.hours}h. Clear to proceed.")
            else:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            out.summary(
                verdict="OK",
                metrics={
                    "recent_losses": 0,
                    "repeats_found": 0,
                    "mode": "ad_hoc",
                },
            )
            sys.exit(0)

        if not args.teams and not args.shortlist:
            if args.format == "text":
                print(f"═══ Recent Losses (last {args.hours}h) ═══")
                for loss in recent_losses:
                    print(
                        f"  {loss['betting_day']} | {loss['pick_id']} | "
                        f"{loss['event']} | {loss['market']} | {loss['selection']}"
                    )
                print(f"\nTotal: {len(recent_losses)} losses")
                print("Use --teams or --shortlist to check for repeats.")
            else:
                result["recent_losses"] = recent_losses
                print(json.dumps(result, indent=2, ensure_ascii=False))
            out.summary(
                verdict="OK",
                metrics={
                    "recent_losses": len(recent_losses),
                    "repeats_found": 0,
                    "mode": "ad_hoc",
                },
            )
            sys.exit(0)

        check_teams = []
        if args.teams:
            check_teams = [t.strip() for t in args.teams.split(",")]
        elif args.shortlist:
            check_teams = parse_shortlist_teams(args.shortlist)

        if not check_teams:
            if args.format == "text":
                print("No teams to check.")
            else:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            out.summary(
                verdict="OK",
                metrics={
                    "recent_losses": len(recent_losses),
                    "repeats_found": 0,
                    "mode": "ad_hoc",
                },
            )
            sys.exit(0)

        warnings = find_repeats(check_teams, recent_losses)

        seen = set()
        unique_warnings = []
        for w in warnings:
            key = (w["team"], w["market"], w["pick_id"])
            if key not in seen:
                seen.add(key)
                unique_warnings.append(w)

        result["repeats_found"] = len(unique_warnings)
        result["warnings"] = unique_warnings

        if args.format == "text":
            print(f"═══ 48h Repeat Check ═══")
            print(f"Teams checked: {len(check_teams)} | Recent losses: {len(recent_losses)}")
            if unique_warnings:
                print(f"\n⚠️  REPEATS FOUND: {len(unique_warnings)}")
                for w in unique_warnings:
                    print(
                        f"  ✗ {w['team']} × {w['market']} — lost {w['lost_on']} "
                        f"({w['pick_id']}) → {w['action']}"
                    )
            else:
                print("\n✓ No repeats found. Clear to proceed.")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))

        out.summary(
            verdict="PARTIAL" if unique_warnings else "OK",
            metrics={
                "recent_losses": len(recent_losses),
                "repeats_found": len(unique_warnings),
                "mode": "ad_hoc",
            },
        )
        sys.exit(1 if unique_warnings else 0)
    except Exception as exc:
        if pipeline_mode and args.date:
            _record_pipeline_failure(args.date, str(exc))
        out.error(str(exc), recoverable=False)
        out.summary(
            verdict="FAILED",
            metrics={
                "date": args.date,
                "mode": "pipeline" if pipeline_mode else "ad_hoc",
                "error": str(exc),
            },
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
