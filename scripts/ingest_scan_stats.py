#!/usr/bin/env python3
"""Ingest Playwright scan data into stats_cache.

Reads betting/data/scan_summary.json, transforms adapter-specific output
into the standard stats_cache format, and writes via build_stats_cache.

CLI: python3 scripts/ingest_scan_stats.py [--date YYYY-MM-DD] [--dry-run]
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_stats_cache import (
    CACHE_DIR,
    create_team_cache_entry,
    now_iso,
    read_cache,
    slugify,
    update_cache,
    validate_sport,
    _compute_stat_averages,
    _compute_combined_stat_averages,
)

# --- DB dual-write (optional) ---
try:
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from bet.db.connection import get_db
    from bet.db.repositories import SportRepo, TeamRepo, StatsRepo
    from bet.db.models import TeamForm
    _HAS_DB = True
except ImportError:
    _HAS_DB = False

SCAN_SUMMARY_PATH = Path(__file__).parent.parent / "betting" / "data" / "scan_summary.json"

# Minimum API-sourced L10 matches before we skip overwriting form with scan data
API_FORM_THRESHOLD = 5


# ---------------------------------------------------------------------------
# Source detection
# ---------------------------------------------------------------------------

_SOURCE_PATTERNS = [
    ("scores24.live", re.compile(r"scores24\.live", re.I)),
    ("forebet.com", re.compile(r"forebet\.com", re.I)),
    ("betexplorer.com", re.compile(r"betexplorer\.com", re.I)),
    ("oddsportal.com", re.compile(r"oddsportal\.com", re.I)),
    ("flashscore.com", re.compile(r"flashscore\.com", re.I)),
    ("sofascore.com", re.compile(r"sofascore\.com", re.I)),
    ("soccerway.com", re.compile(r"soccerway\.com", re.I)),
    ("hltv.org", re.compile(r"hltv\.org", re.I)),
    ("tennisexplorer.com", re.compile(r"tennisexplorer\.com", re.I)),
    ("tennisabstract.com", re.compile(r"tennisabstract\.com", re.I)),
    ("basketball-reference.com", re.compile(r"basketball-reference\.com", re.I)),
    ("hockey-reference.com", re.compile(r"hockey-reference\.com", re.I)),
    ("covers.com", re.compile(r"covers\.com", re.I)),
    ("totalcorner.com", re.compile(r"totalcorner\.com", re.I)),
    ("soccerstats.com", re.compile(r"soccerstats\.com", re.I)),
    ("whoscored.com", re.compile(r"whoscored\.com", re.I)),
]


def detect_source(url: str, event: dict) -> str:
    """Detect the source adapter from URL or event metadata."""
    # Event-level override
    src = event.get("source", "")
    if src:
        return src

    for name, pattern in _SOURCE_PATTERNS:
        if pattern.search(url):
            return name

    return "unknown"


# ---------------------------------------------------------------------------
# Sport-specific score parsers
# ---------------------------------------------------------------------------

def _parse_volleyball_scores(scores: list) -> dict:
    """[sets_t1, sets_t2, s1_t1, s1_t2, s2_t1, s2_t2, ...]"""
    if len(scores) < 2:
        return {}
    stats = {"sets_won": {"home": int(scores[0]), "away": int(scores[1])}}
    set_scores = scores[2:]
    home_pts, away_pts = 0, 0
    for i in range(0, len(set_scores) - 1, 2):
        home_pts += int(set_scores[i])
        away_pts += int(set_scores[i + 1])
    if home_pts or away_pts:
        stats["total_points"] = {"home": home_pts, "away": away_pts}
        stats["points"] = {"home": home_pts, "away": away_pts}
    return stats


def _parse_tennis_scores(scores: list) -> dict:
    """[sets_t1, sets_t2, s1_t1, s1_t2, s2_t1, s2_t2, ...]"""
    if len(scores) < 2:
        return {}
    stats = {"sets_won": {"home": int(scores[0]), "away": int(scores[1])}}
    set_scores = scores[2:]
    home_games, away_games = 0, 0
    for i in range(0, len(set_scores) - 1, 2):
        home_games += int(set_scores[i])
        away_games += int(set_scores[i + 1])
    if home_games or away_games:
        stats["games_won"] = {"home": home_games, "away": away_games}
        stats["total_games"] = {"home": home_games, "away": away_games}
    return stats


def _parse_football_scores(scores: list) -> dict:
    """[goals_t1, goals_t2] or [goals_t1, goals_t2, ht_t1, ht_t2]"""
    if len(scores) < 2:
        return {}
    return {"goals": {"home": int(scores[0]), "away": int(scores[1])}}


def _parse_basketball_scores(scores: list) -> dict:
    """[pts_t1, pts_t2] or [pts_t1, pts_t2, q1_t1, q1_t2, ...]"""
    if len(scores) < 2:
        return {}
    return {"points": {"home": int(scores[0]), "away": int(scores[1])}}


def _parse_hockey_scores(scores: list) -> dict:
    """[goals_t1, goals_t2]"""
    if len(scores) < 2:
        return {}
    return {"goals": {"home": int(scores[0]), "away": int(scores[1])}}


SCORE_PARSERS = {
    "volleyball": _parse_volleyball_scores,
    "tennis": _parse_tennis_scores,
    "football": _parse_football_scores,
    "basketball": _parse_basketball_scores,
    "hockey": _parse_hockey_scores,
}


def parse_scores(sport: str, scores: list) -> dict:
    """Route to sport-specific score parser. Returns stat dict."""
    parser = SCORE_PARSERS.get(sport)
    if not parser:
        return {}
    try:
        return parser([int(s) if isinstance(s, (int, float, str)) and str(s).lstrip("-").isdigit() else 0 for s in scores])
    except (ValueError, IndexError, TypeError):
        return {}


# ---------------------------------------------------------------------------
# Form / H2H extraction from scan event
# ---------------------------------------------------------------------------

def _extract_form_matches(form_list: list, sport: str, team: str) -> list[dict]:
    """Convert scan form data into cache-compatible l10_matches entries."""
    matches = []
    for idx, entry in enumerate(form_list or []):
        scores = entry.get("scores", [])
        stats = parse_scores(sport, scores)
        if not stats and scores:
            # Fallback: treat first two as main score
            stats = parse_scores(sport, scores[:2])
        opponent = entry.get("opponent", "Unknown")
        result_str = entry.get("result") or ""
        was_away = False  # default home perspective
        # If there's an explicit "away" flag, honour it
        if entry.get("was_away"):
            was_away = True
        match_entry = {
            "date": entry.get("date", ""),
            "opponent": opponent,
            "fixture_id": f"scan-form-{idx}",
            "stats": stats,
            "was_away": was_away,
        }
        matches.append(match_entry)
    # Sort by date descending
    matches.sort(key=lambda m: m.get("date", ""), reverse=True)
    return matches[:10]


def _extract_h2h_matches(h2h_data: dict, sport: str) -> list[dict]:
    """Convert scan H2H matches into cache-compatible entries."""
    raw_matches = h2h_data.get("matches", [])
    entries = []
    for idx, m in enumerate(raw_matches):
        scores = m.get("scores", [])
        stats = parse_scores(sport, scores)
        entries.append({
            "date": m.get("date", ""),
            "fixture_id": f"scan-h2h-{idx}",
            "stats": stats,
        })
    entries.sort(key=lambda e: e.get("date", ""), reverse=True)
    return entries


# ---------------------------------------------------------------------------
# Main ingestion per event
# ---------------------------------------------------------------------------

def _should_overwrite_form(existing: dict | None) -> bool:
    """Check if existing cache has enough API-sourced form data."""
    if not existing:
        return True
    form = existing.get("form", {})
    l10 = form.get("l10_matches", [])
    sources = existing.get("sources", [])
    # If there are enough API-sourced matches, don't overwrite
    api_matches = sum(
        1 for m in l10
        if not str(m.get("fixture_id", "")).startswith("scan-")
    )
    return api_matches < API_FORM_THRESHOLD


def ingest_event(
    url: str,
    event: dict,
    dry_run: bool = False,
    summary: dict | None = None,
) -> bool:
    """Ingest a single scan event into stats_cache.

    Returns True if data was written (or would be in dry-run).
    """
    sport = event.get("sport", "")
    home = event.get("home", "")
    away = event.get("away", "")
    source = detect_source(url, event)
    source_tag = f"{source}-scan"

    if not sport or not home:
        return False

    try:
        sport = validate_sport(sport)
    except ValueError:
        print(f"[ingest] SKIP invalid sport '{sport}' from {url}")
        return False

    if summary is not None:
        if sport not in summary:
            summary[sport] = {"teams_ingested": 0, "h2h_added": 0, "form_added": 0}

    wrote_any = False

    # --- Process HOME team ---
    wrote_any |= _ingest_team_side(
        sport=sport,
        team=home,
        opponent=away,
        form_raw=event.get("form_home", []),
        h2h_raw=event.get("h2h", {}),
        odds_raw=event.get("odds", {}),
        source_tag=source_tag,
        is_home=True,
        dry_run=dry_run,
        summary=summary,
    )

    # --- Process AWAY team ---
    if away:
        wrote_any |= _ingest_team_side(
            sport=sport,
            team=away,
            opponent=home,
            form_raw=event.get("form_away", []),
            h2h_raw=event.get("h2h", {}),
            odds_raw=event.get("odds", {}),
            source_tag=source_tag,
            is_home=False,
            dry_run=dry_run,
            summary=summary,
        )

    return wrote_any


def _ingest_team_side(
    sport: str,
    team: str,
    opponent: str,
    form_raw: list,
    h2h_raw: dict,
    odds_raw: dict,
    source_tag: str,
    is_home: bool,
    dry_run: bool,
    summary: dict | None,
) -> bool:
    """Ingest data for one team side (home or away) of an event."""
    if not team:
        return False

    existing = read_cache(sport, team)
    existing_sources = existing.get("sources", []) if existing else []
    existing_h2h = existing.get("h2h", {}) if existing else {}

    # --- Form data ---
    form_matches = _extract_form_matches(form_raw, sport, team)
    overwrite_form = _should_overwrite_form(existing)

    form_data = {}
    form_added = 0
    if form_matches and overwrite_form:
        form_data = {
            "l10_matches": form_matches,
            "l10_avg": _compute_stat_averages(form_matches),
            "l5_avg": _compute_stat_averages(form_matches[:5]),
            "recent_matches": form_matches,
        }
        form_added = len(form_matches)
    elif existing and existing.get("form"):
        # Preserve existing form
        form_data = existing["form"]

    # --- H2H data ---
    h2h_data = dict(existing_h2h)
    h2h_added = 0
    if h2h_raw and opponent:
        h2h_matches = _extract_h2h_matches(h2h_raw, sport)
        if h2h_matches:
            opp_slug = slugify(opponent)
            # Merge: add scan H2H alongside existing
            if opp_slug not in h2h_data:
                h2h_avg = _compute_combined_stat_averages(h2h_matches)
                h2h_data[opp_slug] = {
                    "last_updated": now_iso(),
                    "matches": h2h_matches,
                    "avg": h2h_avg,
                }
                h2h_added = len(h2h_matches)
            else:
                # Existing H2H — merge new matches by date dedup
                existing_dates = {
                    m.get("date") for m in h2h_data[opp_slug].get("matches", [])
                }
                new_matches = [
                    m for m in h2h_matches if m.get("date") not in existing_dates
                ]
                if new_matches:
                    merged = h2h_data[opp_slug].get("matches", []) + new_matches
                    merged.sort(key=lambda m: m.get("date", ""), reverse=True)
                    h2h_data[opp_slug]["matches"] = merged
                    h2h_data[opp_slug]["avg"] = _compute_combined_stat_averages(merged)
                    h2h_data[opp_slug]["last_updated"] = now_iso()
                    h2h_added = len(new_matches)

    # --- Odds ---
    scan_odds = {}
    if odds_raw:
        if isinstance(odds_raw, list):
            # BetExplorer format: ["2.00", "3.18", "3.65"] → w1/x/w2 or w1/w2
            try:
                float_odds = [float(o) for o in odds_raw if o]
            except (ValueError, TypeError):
                float_odds = []
            if len(float_odds) == 3:
                scan_odds = {"w1": float_odds[0], "x": float_odds[1], "w2": float_odds[2]}
            elif len(float_odds) == 2:
                scan_odds = {"w1": float_odds[0], "w2": float_odds[1]}
        elif isinstance(odds_raw, dict):
            for key in ("w1", "w2", "x", "draw"):
                if key in odds_raw and odds_raw[key]:
                    scan_odds[key] = odds_raw[key]
            if odds_raw.get("handicap_lines"):
                scan_odds["handicap_lines"] = odds_raw["handicap_lines"]
            if odds_raw.get("total_lines"):
                scan_odds["total_lines"] = odds_raw["total_lines"]

    # --- Build sources list ---
    sources = list(set(existing_sources + [source_tag]))

    # --- Construct log message ---
    parts = []
    if form_added:
        parts.append(f"form ({form_added} matches)")
    if h2h_added:
        parts.append(f"H2H vs {opponent} ({h2h_added} matches)")
    if scan_odds:
        parts.append(f"odds ({len(scan_odds)} keys)")

    if not parts:
        return False

    log_detail = ", ".join(parts)

    if dry_run:
        print(f"[ingest] DRY-RUN {sport}/{slugify(team)}: {log_detail}")
    else:
        entry = create_team_cache_entry(
            team=team,
            sport=sport,
            form_data=form_data if form_data else {},
            h2h_data=h2h_data,
            sources=sources,
        )
        if scan_odds:
            entry["scan_odds"] = scan_odds

        update_cache(sport, team, entry)

        # Dual-write to DB
        if _HAS_DB:
            try:
                from build_stats_cache import _persist_to_db
                _persist_to_db(sport, team, entry)
            except Exception:
                pass

        print(f"[ingest] {sport}/{slugify(team)}: {log_detail} → cached")

    # Update summary
    if summary is not None and sport in summary:
        summary[sport]["teams_ingested"] += 1
        summary[sport]["h2h_added"] += h2h_added
        summary[sport]["form_added"] += form_added

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(scan_path: Path, dry_run: bool = False, target_date: str | None = None) -> dict:
    """Run full ingestion from scan_summary.json.

    Returns summary dict: {sport: {teams_ingested, h2h_added, form_added}}.
    """
    if not scan_path.exists():
        print(f"[ingest] ERROR: scan file not found: {scan_path}", file=sys.stderr)
        return {}

    try:
        raw = json.loads(scan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[ingest] ERROR: invalid JSON in {scan_path}: {exc}", file=sys.stderr)
        return {}

    if not isinstance(raw, dict):
        print(f"[ingest] ERROR: expected dict in {scan_path}, got {type(raw).__name__}", file=sys.stderr)
        return {}

    summary: dict = {}
    total_events = 0
    ingested_events = 0
    errors = 0

    for url, events in raw.items():
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue

            # Optional date filter
            if target_date:
                event_date = (
                    event.get("match_info", {}).get("date", "")
                    or event.get("date", "")
                )
                if event_date and event_date != target_date:
                    continue

            total_events += 1
            try:
                if ingest_event(url, event, dry_run=dry_run, summary=summary):
                    ingested_events += 1
            except Exception as exc:
                errors += 1
                sport = event.get("sport", "?")
                home = event.get("home", "?")
                print(f"[ingest] ERROR processing {sport}/{home} from {url}: {exc}", file=sys.stderr)

    # Print summary
    mode = "DRY-RUN " if dry_run else ""
    print(f"\n[ingest] {mode}DONE — {ingested_events}/{total_events} events ingested, {errors} errors")
    for sport, counts in sorted(summary.items()):
        print(
            f"  {sport}: "
            f"{counts['teams_ingested']} teams, "
            f"{counts['h2h_added']} H2H matches, "
            f"{counts['form_added']} form matches"
        )

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Ingest Playwright scan data into stats_cache"
    )
    parser.add_argument(
        "--date",
        help="Only ingest events for this date (YYYY-MM-DD)",
        default=None,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate without writing to cache",
    )
    parser.add_argument(
        "--scan-file",
        type=Path,
        default=SCAN_SUMMARY_PATH,
        help="Path to scan_summary.json (default: betting/data/scan_summary.json)",
    )
    args = parser.parse_args()

    # Validate date format
    if args.date:
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"[ingest] ERROR: invalid date format '{args.date}', expected YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)

    run(args.scan_file, dry_run=args.dry_run, target_date=args.date)


if __name__ == "__main__":
    main()
