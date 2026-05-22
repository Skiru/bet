#!/usr/bin/env python3
"""S5 Contextual Checks — weather, venue, referee, roster changes, competition significance.

Extracted from pipeline_orchestrator.py (Phase 3.2).
Supports --verbose + AGENT_SUMMARY for agent-driven pipeline (R17/R19).
"""

import argparse
import json
import re
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


# ---------------------------------------------------------------------------
# Fixture Significance Scoring — Competition Intelligence for S7 agent
# ---------------------------------------------------------------------------

# Competition stage keywords → significance multiplier for safety scores
KNOCKOUT_MARKERS = re.compile(
    r"\b(playoffs?|knockouts?|elimination|finals?|semifinals?|semi-finals?|quarter.?finals?|"
    r"round\s*of\s*\d+|play.?offs?|postseason)\b", re.I
)
GROUP_STAGE_MARKERS = re.compile(
    r"\b(group\s+(stage|phase|[a-h])|pool\s+(stage|[a-d])|round\s*robin)\b", re.I
)
CUP_MARKERS = re.compile(
    r"\b(cup|copa|coupe|pokal|taça|coppa|puchar|pohár|кубок)\b", re.I
)
FRIENDLY_MARKERS = re.compile(
    r"\b(friendl(?:y|ies)|amistoso|amical|exhibition|preseason|pre-season|club\s*friendly)\b", re.I
)

# High-prestige tournaments where patterns differ from regular leagues
PRESTIGE_TOURNAMENTS = {
    # Football
    "champions league", "europa league", "conference league", "copa libertadores",
    "copa sudamericana", "world cup", "euro 202", "african cup", "copa america",
    "nations league", "fa cup", "copa del rey", "dfb pokal", "coppa italia",
    "coupe de france", "carabao cup",
    # Tennis
    "grand slam", "australian open", "roland garros", "french open", "wimbledon",
    "us open", "atp finals", "wta finals",
    # Basketball
    "nba playoffs", "nba finals", "euroleague", "fiba",
    # Hockey
    "stanley cup", "nhl playoffs", "iihf",
    # Volleyball
    "nations league", "world championship", "olympic",
}

# Stakes detection — keywords indicating high-stakes context
RELEGATION_MARKERS = re.compile(
    r"\b(relegation|spadek|abstieg|descenso|retrocessão|degradation)\b", re.I
)
PROMOTION_MARKERS = re.compile(
    r"\b(promotion|awans|aufstieg|ascenso|promoção|montée)\b", re.I
)


def compute_fixture_significance(candidate: dict) -> dict:
    """Compute fixture significance for a candidate.

    Returns a dict with:
      - competition_type: league|cup|tournament_knockout|tournament_group|friendly|unknown
      - significance_score: 1-10 (10 = highest stakes)
      - competition_multiplier: float for safety adjustment (0.70 - 1.20)
      - flags: list of significance flags
      - notes: human-readable explanation
    """
    competition = (candidate.get("competition") or "").lower()
    sport = (candidate.get("sport") or "").lower()
    flags = []
    notes = []

    # 1. Detect competition type (ORDER MATTERS — most specific first)
    comp_type = "league"  # default
    if FRIENDLY_MARKERS.search(competition):
        comp_type = "friendly"
        flags.append("FRIENDLY")
        notes.append("Friendly/exhibition — unpredictable lineups, low motivation")
    elif KNOCKOUT_MARKERS.search(competition):
        comp_type = "tournament_knockout"
        flags.append("KNOCKOUT_STAGE")
        notes.append("Knockout stage — conservative tactics, fewer open-play stats")
    elif GROUP_STAGE_MARKERS.search(competition):
        comp_type = "tournament_group"
        flags.append("GROUP_STAGE")
        notes.append("Group stage — teams need points, more aggressive")
    elif CUP_MARKERS.search(competition):
        comp_type = "cup"
        flags.append("CUP")
        notes.append("Cup competition — may differ from league patterns")

    # 2. Prestige detection — ALSO overrides comp_type for known tournaments
    is_prestige = any(t in competition for t in PRESTIGE_TOURNAMENTS)
    if is_prestige:
        flags.append("HIGH_PRESTIGE")
        notes.append(f"High-prestige competition: {competition}")
        # Champions League / Europa League / Cup competitions without "cup" in name
        # that are clearly not regular leagues
        if comp_type == "league" and any(
            t in competition for t in (
                "champions league", "europa league", "conference league",
                "copa libertadores", "copa sudamericana", "nations league",
                "nba playoffs", "nhl playoffs", "stanley cup",
                "euroleague", "atp finals", "wta finals",
            )
        ):
            # These are cup/tournament competitions even without "cup" keyword
            if "playoff" in competition or "final" in competition:
                comp_type = "tournament_knockout"
                if "KNOCKOUT_STAGE" not in flags:
                    flags.append("KNOCKOUT_STAGE")
            else:
                comp_type = "cup"
                if "CUP" not in flags:
                    flags.append("CUP")

    # 3. Stakes detection (from standings/league context)
    # Check if team positions suggest high stakes
    home_pos = candidate.get("home_position") or candidate.get("standings", {}).get("home_rank")
    away_pos = candidate.get("away_position") or candidate.get("standings", {}).get("away_rank")

    # Rivalry detection — same city/region teams
    home = (candidate.get("home_team") or "").lower()
    away = (candidate.get("away_team") or "").lower()
    # Simple city-based derby detection
    if _is_derby(home, away):
        flags.append("DERBY")
        notes.append("Derby/rivalry — H2H more predictive than L10, emotional factor")

    # 4. Compute significance score (1-10)
    score = 5  # baseline for regular league
    if comp_type == "friendly":
        score = 2
    elif comp_type == "tournament_knockout":
        score = 8
        if is_prestige:
            score = 9
    elif comp_type == "tournament_group":
        score = 6
    elif comp_type == "cup":
        score = 6
        if is_prestige:
            score = 8

    if "DERBY" in flags:
        score = min(10, score + 1)

    # 5. Compute competition multiplier for safety score adjustment
    # This tells the S7 agent how to adjust raw safety scores
    multiplier = 1.0
    if comp_type == "tournament_knockout":
        if sport == "football":
            multiplier = 0.85  # OVER markets less reliable in knockouts
        elif sport in ("basketball", "hockey"):
            multiplier = 0.90  # Playoff pace drops
        elif sport == "tennis":
            multiplier = 1.15  # Grand Slam best-of-5 = MORE games
    elif comp_type == "friendly":
        multiplier = 0.70  # Very unreliable
    elif "DERBY" in flags:
        multiplier = 1.0  # Neutral on safety, but H2H weight should double

    return {
        "competition_type": comp_type,
        "significance_score": score,
        "competition_multiplier": multiplier,
        "flags": flags,
        "notes": "; ".join(notes) if notes else "Regular league fixture",
        "is_prestige": is_prestige,
        "is_derby": "DERBY" in flags,
    }


def _is_derby(home: str, away: str) -> bool:
    """Simple derby detection based on shared city/region keywords."""
    # Known derby pairs (partial matches)
    derby_pairs = [
        ("real madrid", "atletico"), ("barcelona", "espanyol"),
        ("milan", "inter"), ("roma", "lazio"), ("juventus", "torino"),
        ("liverpool", "everton"), ("manchester united", "manchester city"),
        ("arsenal", "tottenham"), ("celtic", "rangers"),
        ("benfica", "sporting"), ("porto", "benfica"),
        ("boca", "river"), ("flamengo", "fluminense"),
        ("galatasaray", "fenerbahce"), ("besiktas", "galatasaray"),
        ("dortmund", "schalke"), ("bayern", "dortmund"),
        ("psg", "marseille"), ("lyon", "saint-etienne"),
        ("ajax", "feyenoord"), ("psv", "ajax"),
        ("lakers", "celtics"), ("lakers", "clippers"),
        ("yankees", "red sox"), ("cubs", "white sox"),
    ]
    for a, b in derby_pairs:
        if (a in home and b in away) or (b in home and a in away):
            return True
    # Same city heuristic: first word matches and len > 3
    home_city = home.split()[0] if home else ""
    away_city = away.split()[0] if away else ""
    if home_city and away_city and home_city == away_city and len(home_city) > 3:
        return True
    return False


# ---------------------------------------------------------------------------
# Data Completeness Validation — NO DEFAULTS rule (R19)
# ---------------------------------------------------------------------------

SYNTHETIC_MARKERS = re.compile(
    r"\b(estimated|~\d|approx|expected|average for|avg for|league avg|"
    r"assumed|probably|likely around|typically)\b", re.I
)


def validate_data_completeness(candidate: dict) -> dict:
    """Check if a candidate's stats are ALL measured (no defaults/estimates).

    Returns:
        {
            "is_complete": bool,
            "data_gaps": [str],    # list of identified gaps
            "synthetic_flags": [str],  # detected synthetic/estimated language
            "data_quality_override": str | None,  # "MINIMAL" if gaps found
            "max_tier": str,  # "CORE" | "EXTENDED_POOL" based on completeness
        }
    """
    gaps = []
    synthetic = []

    # Check reasoning/data fields for synthetic language
    for field in ("reasoning", "data", "edge", "notes"):
        text = candidate.get(field, "")
        if text and SYNTHETIC_MARKERS.search(text):
            matches = SYNTHETIC_MARKERS.findall(text)
            synthetic.append(f"{field}: contains synthetic markers {matches}")

    # Check if both teams have measured stats in a combined market
    market = (candidate.get("market") or "").lower()
    is_combined = any(kw in market for kw in ("total", "over", "under", "combined"))

    data_text = candidate.get("data", "")
    if is_combined and data_text:
        # Look for "not available", "not directly available", "estimated"
        if re.search(r"not (directly )?available|no data|N/A|unknown", data_text, re.I):
            gaps.append("Combined market with missing team data — cannot compute valid total")

        # Check if only ONE team's stats are cited (home OR away, not both)
        home_team = (candidate.get("home_team") or "").lower()
        away_team = (candidate.get("away_team") or "").lower()
        data_lower = data_text.lower()
        # For combined markets, both teams should have measured stats
        has_home_stat = bool(home_team and home_team[:4] in data_lower) or "_home" in data_lower
        has_away_stat = bool(away_team and away_team[:4] in data_lower) or "_away" in data_lower
        if not has_home_stat and has_away_stat:
            gaps.append(f"Combined market but only away team stats cited — home team data MISSING")
        elif has_home_stat and not has_away_stat:
            gaps.append(f"Combined market but only home team stats cited — away team data MISSING")

    # Check for cross-league data usage without explicit flag
    competition = (candidate.get("competition") or candidate.get("comp") or "").lower()
    if data_text and re.search(r"2\.\s*(bundesliga|division|liga)", data_text, re.I):
        if "playoff" in competition or "promotion" in competition:
            gaps.append("Cross-league stats applied to higher-tier playoff — transferability unverified")

    is_complete = len(gaps) == 0 and len(synthetic) == 0
    quality_override = None if is_complete else "MINIMAL"
    max_tier = "CORE" if is_complete else "EXTENDED_POOL"

    return {
        "is_complete": is_complete,
        "data_gaps": gaps,
        "synthetic_flags": synthetic,
        "data_quality_override": quality_override,
        "max_tier": max_tier,
    }



def run_context_checks(date: str, state: dict) -> tuple[bool, str]:
    """S5: Contextual checks — weather, venue, referee, roster changes.

    Enriches S3 candidates with contextual flags for downstream gate checks.
    """
    checks_done = []
    context_flags = {}
    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"

    candidates = []
    s3_data = None
    try:
        from db_data_loader import load_s3_candidates_with_parity

        candidates, candidate_load = load_s3_candidates_with_parity(date)
        state["candidate_load"] = candidate_load
        if candidate_load.get("blocking_error"):
            error = candidate_load["blocking_error"]
            return False, (
                "S5 candidate parity failure: "
                f"{error.get('message', 'unknown error')} "
                f"(json={candidate_load['counts']['json']}, db={candidate_load['counts']['db']})"
            )

        if candidates:
            s3_data = {"analyses": candidates}
            if state.get("verbose"):
                print(
                    "    [context_checks] candidate load: "
                    f"source={candidate_load['source']} "
                    f"status={candidate_load['parity']['status']} "
                    f"json={candidate_load['counts']['json']} "
                    f"db={candidate_load['counts']['db']} "
                    f"canonical={candidate_load['counts']['canonical']}"
                )
    except Exception as e:
        return False, f"S5 candidate load error: {e}"

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
            from bet.api_clients.espn_adapter import ESPNMultiLeagueClient
            from bet.api_clients.rate_limiter import RateLimiter
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
    significance_scored = 0
    if candidates and s3_path.exists():
        enriched = 0
        for c in candidates:
            c_flags = []
            home = c.get("home_team", "")
            away = c.get("away_team", "")
            sport = c.get("sport", "")

            # --- COMPETITION SIGNIFICANCE (new) ---
            significance = compute_fixture_significance(c)
            c["fixture_significance"] = significance
            significance_scored += 1
            for flag in significance.get("flags", []):
                c_flags.append(f"SIGNIFICANCE:{flag}")
            if significance.get("competition_multiplier", 1.0) != 1.0:
                c_flags.append(f"COMP_MULT:{significance['competition_multiplier']:.2f}")

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
        if significance_scored:
            checks_done.append(f"significance: {significance_scored} candidates scored")

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

    state = {}
    ok, msg = run_context_checks(args.date, state)

    # Parse checks_done from message
    weather_m = re.search(r"weather: (\d+) venues checked, (\d+) with impact", msg)
    injury_m = re.search(r"injuries: (\d+) entries across (\d+) sports", msg)
    enriched_m = re.search(r"enriched: (\d+)/(\d+) candidates", msg)
    significance_m = re.search(r"significance: (\d+) candidates scored", msg)

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
    if significance_m:
        metrics["significance_scored"] = int(significance_m.group(1))

    candidate_load = state.get("candidate_load") or {}
    metrics["input_source"] = candidate_load.get("source", "none")
    metrics["input_status"] = candidate_load.get("parity", {}).get("status", "missing")
    metrics["input_json_candidates"] = candidate_load.get("counts", {}).get("json", 0)
    metrics["input_db_candidates"] = candidate_load.get("counts", {}).get("db", 0)
    metrics["input_canonical_candidates"] = candidate_load.get("counts", {}).get("canonical", 0)

    verdict = "OK" if ok else "FAILED"
    if "unavailable" in msg or "load_error" in msg:
        verdict = "PARTIAL"

    out.summary(verdict=verdict, metrics=metrics)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
