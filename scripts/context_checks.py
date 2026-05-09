#!/usr/bin/env python3
"""S5 Contextual Checks — weather, venue, referee, roster changes.

Extracted from pipeline_orchestrator.py (Phase 3.2).
"""

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

    # Load S3 candidates for enrichment
    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
    candidates = []
    if s3_path.exists():
        try:
            s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
            candidates = s3_data.get("analyses", [])
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
            for sport_name in ["football", "basketball", "hockey"]:
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

    # Enrich S3 candidates with context flags
    if candidates and s3_path.exists():
        enriched = 0
        for c in candidates:
            c_flags = []
            home = c.get("home_team", "")
            away = c.get("away_team", "")
            sport = c.get("sport", "")
            # Check weather
            for venue, flags in context_flags.items():
                if venue.lower() in (home.lower(), away.lower(), c.get("venue", "").lower()):
                    c_flags.extend([f"WEATHER:{f}" for f in flags])
            # Check injuries
            for inj_entry in injury_summary:
                if home.lower() in inj_entry.lower() or away.lower() in inj_entry.lower():
                    c_flags.append(f"INJURY:{inj_entry.split(':')[-1].strip()}")
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
