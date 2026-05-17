#!/usr/bin/env python3
"""S6 Upset Risk Scoring — sport-specific heuristics.

Extracted from pipeline_orchestrator.py (Phase 3.3).
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


def run_upset_risk(date: str, state: dict) -> tuple[bool, str]:
    """S6: Upset risk scoring per candidate with sport-specific heuristics."""
    # DB-first: load S3 analysis results (R2)
    analyses = []
    s3_data = None
    try:
        from db_data_loader import load_analysis_results_from_db
        db_results = load_analysis_results_from_db(date)
        if db_results:
            analyses = db_results
            s3_data = {"analyses": analyses}
    except Exception:
        pass

    # JSON fallback
    s3_path = DATA_DIR / f"{date}_s3_deep_stats.json"
    if not analyses:
        if not s3_path.exists():
            return True, "S6: No S3 data — skipping upset risk scoring"
        try:
            s3_data = json.loads(s3_path.read_text(encoding="utf-8"))
            analyses = s3_data.get("analyses", [])
        except (json.JSONDecodeError, OSError):
            return True, "S6: JSON read error — skipping"

    # Sport-specific upset risk thresholds
    UPSET_THRESHOLDS = {
        "football": {"safety_low": 0.55, "h2h_min": 3, "form_diverge": 0.15},
        "tennis": {"safety_low": 0.50, "h2h_min": 2, "form_diverge": 0.20},
        "basketball": {"safety_low": 0.50, "h2h_min": 3, "form_diverge": 0.10},
        "volleyball": {"safety_low": 0.50, "h2h_min": 3, "form_diverge": 0.15},
        "hockey": {"safety_low": 0.50, "h2h_min": 3, "form_diverge": 0.15},
    }
    DEFAULT_THRESHOLDS = {"safety_low": 0.50, "h2h_min": 2, "form_diverge": 0.15}

    try:
        scored = 0
        elevated = 0
        high_risk = 0

        for analysis in analyses:
            sport = analysis.get("sport", "").lower()
            thresholds = UPSET_THRESHOLDS.get(sport, DEFAULT_THRESHOLDS)
            risk_factors = []

            ranking = analysis.get("ranking", analysis.get("ranking_result", {}).get("ranking", []))
            top_market = ranking[0] if ranking else {}
            safety = top_market.get("safety_score", 0)

            # Factor 1: Low safety score (sport-specific threshold)
            if safety < thresholds["safety_low"]:
                risk_factors.append(f"safety_below_{thresholds['safety_low']} ({safety})")

            # Factor 2: L5 trend diverging from L10 (form instability)
            l5_avg = top_market.get("combined_avg_l5", top_market.get("l5_avg"))
            l10_avg = top_market.get("combined_avg", top_market.get("l10_avg"))
            if l5_avg and l10_avg and l10_avg != 0:
                divergence = abs(l5_avg - l10_avg) / abs(l10_avg)
                if divergence > thresholds["form_diverge"]:
                    direction = "declining" if l5_avg < l10_avg else "surging"
                    risk_factors.append(f"form_{direction} ({divergence:.0%} L5 vs L10)")

            # Factor 3: Missing H2H data
            h2h = analysis.get("h2h", {})
            h2h_meetings = len(h2h.get("meetings", []))
            if h2h_meetings < thresholds["h2h_min"]:
                risk_factors.append(f"h2h_insufficient ({h2h_meetings}/{thresholds['h2h_min']} meetings)")

            # Factor 4: Context flags (weather, injuries)
            context_flags = analysis.get("context_flags", [])
            if any("INJURY" in f for f in context_flags):
                risk_factors.append("key_injury_flagged")
            if any("WEATHER" in f for f in context_flags):
                risk_factors.append("adverse_weather")

            # Factor 5: No EV data (stats-first mode = higher uncertainty)
            if analysis.get("ev") is None:
                risk_factors.append("no_ev_data_statsFirst")

            # Score upset risk
            risk_count = len(risk_factors)
            if risk_count >= 3:
                risk_level = "HIGH"
                high_risk += 1
            elif risk_count >= 1:
                risk_level = "ELEVATED"
                elevated += 1
            else:
                risk_level = "LOW"

            analysis["upset_risk"] = {
                "level": risk_level,
                "factors": risk_factors,
                "factor_count": risk_count,
            }
            analysis.setdefault("flags", [])
            if risk_level != "LOW":
                analysis["flags"].append(f"upset_risk_{risk_level.lower()}")
            scored += 1

            # Verbose per-candidate output
            home = analysis.get("home_team", "?")
            away = analysis.get("away_team", "?")
            marker = {"LOW": "🟢", "ELEVATED": "🟡", "HIGH": "🔴"}[risk_level]
            print(f"    {marker} {home} vs {away} [{sport}]: {risk_level} ({risk_count} factors)")
            if risk_factors:
                for rf in risk_factors[:3]:
                    print(f"       → {rf}")

        s3_path.write_text(
            json.dumps(s3_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Save upset risk scores to analysis_results in DB
        try:
            from bet.db.connection import get_db
            from bet.db.repositories import AnalysisResultRepo, FixtureRepo, SportRepo
            with get_db() as conn:
                repo = AnalysisResultRepo(conn)
                fixture_repo = FixtureRepo(conn)
                sport_repo = SportRepo(conn)
                updated = 0
                for analysis in analyses:
                    upset = analysis.get("upset_risk")
                    if not upset:
                        continue
                    fid = analysis.get("fixture_id")
                    if not fid:
                        sport_name = analysis.get("sport", "")
                        s = sport_repo.get_by_name(sport_name) if sport_name else None
                        if s:
                            ko = analysis.get("kickoff", date)
                            f = fixture_repo.get_by_teams_and_date(
                                analysis.get("home_team", ""), analysis.get("away_team", ""),
                                ko[:10] if ko else date, s.id,
                            )
                            fid = f.id if f else None
                    if not fid:
                        print(f"  ⚠ S6 DB: fixture_id not resolved for {analysis.get('home_team', '?')} vs {analysis.get('away_team', '?')}")
                        continue
                    ar = repo.get_by_fixture(fid, date)
                    if ar:
                        summary = ar.stats_summary_json or {}
                        summary["upset_risk"] = upset
                        repo.update_stats_summary(fid, date, summary)
                        updated += 1
                conn.commit()
                if updated:
                    print(f"  → DB: updated {updated} analysis_results with upset risk")
        except Exception as e:
            print(f"  ⚠ DB upset risk update failed (non-fatal): {e}")

        return True, f"S6 completed: {scored} candidates scored — {elevated} elevated, {high_risk} high risk"
    except Exception as e:
        return True, f"S6 upset risk error: {e} — continuing without"


# ---------------------------------------------------------------------------
# CLI entry point with --verbose + AGENT_SUMMARY (R17/R19)
# ---------------------------------------------------------------------------
def main():
    from agent_output import AgentOutput, add_agent_args

    parser = argparse.ArgumentParser(
        description="S6 Upset Risk Scoring — sport-specific heuristics"
    )
    parser.add_argument("--date", required=True, help="Betting date YYYY-MM-DD")
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput("s6_upset_risk", verbose=args.verbose, stop_on_error=args.stop_on_error)

    ok, msg = run_upset_risk(args.date, {})

    # Parse metrics from message
    import re
    m = re.search(r"(\d+) candidates scored.*?(\d+) elevated.*?(\d+) high risk", msg)
    scored = int(m.group(1)) if m else 0
    elevated = int(m.group(2)) if m else 0
    high_risk = int(m.group(3)) if m else 0

    if not m:
        # Regex didn't match — error path or unexpected message format
        verdict = "PARTIAL" if ok else "FAILED"
    elif ok and high_risk == 0:
        verdict = "OK"
    elif ok:
        verdict = "PARTIAL"
    else:
        verdict = "FAILED"

    out.summary(
        verdict=verdict,
        metrics={
            "total_scored": scored,
            "low_risk": scored - elevated - high_risk,
            "elevated_risk": elevated,
            "high_risk": high_risk,
            "high_risk_pct": round(high_risk / max(scored, 1) * 100, 1),
        },
    )

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
