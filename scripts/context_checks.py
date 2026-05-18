#!/usr/bin/env python3
"""S5 Contextual Checks — weather, venue, referee, roster changes.

Extracted from pipeline_orchestrator.py (Phase 3.2).
Supports --verbose + AGENT_SUMMARY for agent-driven pipeline (R17/R19).
"""

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (same as orchestrator)
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).parent
ROOT_DIR = SCRIPTS_DIR.parent
DATA_DIR = ROOT_DIR / "betting" / "data"

# Add scripts/ and src/ to path for imports
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))


def run_context_checks(date: str, state: dict) -> tuple[bool, str]:
    """S5: Contextual checks — weather, venue, referee, roster changes.

    Enriches S3 candidates with contextual flags for downstream gate checks.
    """
    checks_done = []
    context_flags = {}
    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"

    # DB-first: load S3 analysis results from DB (R2)
    candidates = []
    s3_data = None
    try:
        from db_data_loader import load_analysis_results_from_db
        db_candidates = load_analysis_results_from_db(date)
        if db_candidates:
            candidates = db_candidates
            s3_data = {"analyses": candidates}  # Maintain s3_data structure for downstream write-back
            if state.get("verbose"):
                print(f"    [context_checks] DB: loaded {len(candidates)} candidates")
    except Exception:
        pass

    # JSON fallback
    if not candidates:
        s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
        if s3_path.exists():
            try:
                s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
                candidates = s3_data.get("analyses", [])
                if state.get("verbose"):
                    print(f"    [context_checks] JSON fallback: loaded {len(candidates)} candidates")
            except (json.JSONDecodeError, OSError):
                pass

    # Weather data — flag candidates with weather impact
    weather_path = DATA_DIR / f"weather_{date}.json"
    weather_impacts = []
    # Fallback: fetch weather if not already available
    if not weather_path.exists():
        try:
            import subprocess
            subprocess.run(
                ["python3", str(Path(__file__).parent / "fetch_weather.py"), "--date", date],
                timeout=60, capture_output=True,
            )
        except Exception:
            pass
    if weather_path.exists():
        try:
            weather = json.loads(weather_path.read_text(encoding="utf-8"))
            venues = weather if isinstance(weather, list) else weather.get("venues", weather.get("forecasts", {}))
            if isinstance(venues, dict):
                for venue, forecast in venues.items():
                    flags = forecast.get("flags", [])
                    if flags:
                        weather_impacts.append(f"{venue}: {', '.join(flags)}")
                        context_flags[venue] = flags
            elif isinstance(venues, list):
                for v in venues:
                    venue_name = v.get("venue", v.get("city", "unknown"))
                    flags = v.get("flags", [])
                    if flags:
                        weather_impacts.append(f"{venue_name}: {', '.join(flags)}")
                        context_flags[venue_name] = flags
            n_venues = len(venues) if isinstance(venues, (list, dict)) else 0
            n_impacted = len(weather_impacts)
            checks_done.append(f"weather: {n_venues} venues checked, {n_impacted} with impact flags")
            if weather_impacts:
                for wi in weather_impacts[:5]:
                    print(f"    🌧 {wi}")
        except (json.JSONDecodeError, OSError):
            checks_done.append("weather: load_error")
    else:
        checks_done.append("weather: unavailable")

    # ESPN injuries/roster data — flag candidates with key injuries
    espn_path = DATA_DIR / f"espn_enrichment_{date}.json"
    injury_summary = []
    # Fallback: fetch ESPN enrichment if not already available
    if not espn_path.exists():
        try:
            from api_clients.espn_adapter import ESPNMultiLeagueClient
            from api_clients.rate_limiter import RateLimiter
            rl = RateLimiter()
            enrichment = {"date": date, "odds": [], "injuries": {}, "form": {}}
            for sport_name in ["football", "basketball", "hockey", "tennis", "volleyball"]:
                try:
                    client = ESPNMultiLeagueClient(sport=sport_name, rate_limiter=rl)
                    injuries = client.get_injuries()
                    if injuries:
                        enrichment["injuries"][sport_name] = injuries
                except Exception:
                    pass
            if enrichment["injuries"]:
                espn_path.write_text(json.dumps(enrichment, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    if espn_path.exists():
        try:
            espn = json.loads(espn_path.read_text(encoding="utf-8"))
            injuries = espn.get("injuries", {})
            for sport, sport_injuries in injuries.items():
                if isinstance(sport_injuries, list):
                    for inj in sport_injuries:
                        team = inj.get("team", "unknown")
                        player = inj.get("player", inj.get("name", "unknown"))
                        status = inj.get("status", inj.get("type", "unknown"))
                        injury_summary.append(f"{sport}/{team}: {player} ({status})")
            n_injuries = len(injury_summary)
            checks_done.append(f"injuries: {n_injuries} entries across {len(injuries)} sports")
            if injury_summary:
                for inj in injury_summary[:8]:
                    print(f"    🏥 {inj}")
        except (json.JSONDecodeError, OSError):
            checks_done.append("injuries: load_error")
    else:
        checks_done.append("injuries: unavailable")

    # Gemini news enrichment — read from team_news DB table (feature flag)
    gemini_news = {}
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import TeamNewsRepo
        with get_db() as conn:
            news_repo = TeamNewsRepo(conn)
            all_news = news_repo.get_for_date(date)
            for news in all_news:
                # Resolve team name from team_id for matching
                row = conn.execute(
                    "SELECT name FROM teams WHERE id = ?", (news.team_id,)
                ).fetchone()
                if row:
                    team_name = row["name"]
                    gemini_news[team_name.lower()] = news
                    # Add injuries from Gemini to injury_summary
                    for inj in (news.injuries_json or []):
                        player = inj.get("player_name", inj.get("player", "?"))
                        status = inj.get("status", "?")
                        injury_summary.append(f"{news.sport_id}/{team_name}: {player} ({status}) [gemini]")
        if gemini_news:
            checks_done.append(f"gemini_news: {len(gemini_news)} teams from team_news table")
        else:
            checks_done.append("gemini_news: no data for this date")
    except Exception as e:
        checks_done.append(f"gemini_news: error ({e})")

    # Enrich S3 candidates with context flags
    if candidates and s3_path.exists():
        enriched = 0
        for c in candidates:
            c_flags = []
            home = c.get("home_team", "")
            away = c.get("away_team", "")
            sport = c.get("sport", "")
            # Check weather — use substring matching for venue keys like "Liverpool vs Arsenal"
            for venue, flags in context_flags.items():
                venue_l = venue.lower()
                home_l = home.lower()
                away_l = away.lower()
                venue_of_c = c.get("venue", "").lower()
                if (home_l in venue_l or away_l in venue_l
                        or venue_l in home_l or venue_l in away_l
                        or (venue_of_c and venue_of_c in venue_l)):
                    c_flags.extend([f"WEATHER:{f}" for f in flags])
            # Check injuries
            for inj_entry in injury_summary:
                if home.lower() in inj_entry.lower() or away.lower() in inj_entry.lower():
                    c_flags.append(f"INJURY:{inj_entry.split(':')[-1].strip()}")
            # Check Gemini team news
            for team_key in [home.lower(), away.lower()]:
                news = gemini_news.get(team_key)
                if news:
                    for item in (news.coaching_json or []):
                        c_flags.append(f"COACHING:{item.get('change', item) if isinstance(item, dict) else item}")
                    for item in (news.morale_json or []):
                        c_flags.append(f"MORALE:{item.get('indicator', item) if isinstance(item, dict) else item}")
                    for item in (news.news_json or []):
                        headline = item.get("headline", item) if isinstance(item, dict) else item
                        c_flags.append(f"NEWS:{headline}")
            if c_flags:
                c.setdefault("context_flags", []).extend(c_flags)
                enriched += 1
                print(f"    📋 {home} vs {away}: {', '.join(c_flags[:3])}")
        if enriched:
            s3_path.write_text(
                json.dumps(s3_data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            checks_done.append(f"enriched: {enriched}/{len(candidates)} candidates with context flags")

    # Save context enrichments to analysis_results in DB
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import AnalysisResultRepo, FixtureRepo, SportRepo
        with get_db() as conn:
            repo = AnalysisResultRepo(conn)
            fixture_repo = FixtureRepo(conn)
            sport_repo = SportRepo(conn)
            updated = 0
            for c in candidates:
                c_flags = c.get("context_flags", [])
                if not c_flags:
                    continue
                fid = c.get("fixture_id")
                if not fid:
                    sport_name = c.get("sport", "")
                    s = sport_repo.get_by_name(sport_name) if sport_name else None
                    if s:
                        ko = c.get("kickoff", date)
                        f = fixture_repo.get_by_teams_and_date(
                            c.get("home_team", ""), c.get("away_team", ""),
                            ko[:10] if ko else date, s.id,
                        )
                        fid = f.id if f else None
                if not fid:
                    print(f"  ⚠ S5 DB: fixture_id not resolved for {c.get('home_team', '?')} vs {c.get('away_team', '?')}")
                    continue
                ar = repo.get_by_fixture(fid, date)
                if ar:
                    summary = ar.stats_summary_json or {}
                    summary["context_flags"] = c_flags
                    repo.update_stats_summary(fid, date, summary)
                    updated += 1
            conn.commit()
            if updated:
                print(f"  → DB: updated {updated} analysis_results with context flags")
    except Exception as e:
        print(f"  ⚠ DB context update failed (non-fatal): {e}")

    return True, f"S5 contextual checks: {', '.join(checks_done)}"


# ---------------------------------------------------------------------------
# CLI entry point with --verbose + AGENT_SUMMARY (R17/R19)
# ---------------------------------------------------------------------------
def main():
    from agent_output import AgentOutput, add_agent_args

    parser = argparse.ArgumentParser(
        description="S5 Contextual Checks — weather, venue, referee, roster changes"
    )
    parser.add_argument("--date", required=True, help="Betting date YYYY-MM-DD")
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput("s5_context", verbose=args.verbose, stop_on_error=args.stop_on_error)

    ok, msg = run_context_checks(args.date, {})

    # Parse checks_done from message
    import re
    weather_m = re.search(r"weather: (\d+) venues checked, (\d+) with impact", msg)
    injury_m = re.search(r"injuries: (\d+) entries across (\d+) sports", msg)
    enriched_m = re.search(r"enriched: (\d+)/(\d+) candidates", msg)

    metrics = {}
    if weather_m:
        metrics["weather_venues"] = int(weather_m.group(1))
        metrics["weather_impacted"] = int(weather_m.group(2))
    if injury_m:
        metrics["injury_entries"] = int(injury_m.group(1))
        metrics["injury_sports"] = int(injury_m.group(2))
    if enriched_m:
        metrics["enriched_candidates"] = int(enriched_m.group(1))
        metrics["total_candidates"] = int(enriched_m.group(2))

    verdict = "OK" if ok else "FAILED"
    if "unavailable" in msg or "load_error" in msg:
        verdict = "PARTIAL"

    out.summary(verdict=verdict, metrics=metrics)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
